import json
from pathlib import Path
import tkinter as tk
from PIL import Image

from dashboard import (
    feature_is_complete,
    feature_status,
    map_transform,
    window_dimensions,
    workspace_render_signature,
)
from game.dashboard_bridge import DashboardBridge
from game.dashboard_model import DashboardModel
from game.reference_data import reference_sources
from game.state import read_state
from retroarch_overlay.models import MapOverlay, MapWaypoint


ROOT = Path(__file__).parents[1]


def dashboard_documents(tmp_path: Path) -> tuple[dict, dict]:
    static = {
        "schema_version": 1,
        "game": "Dragon Warrior IV",
        "workspaces": [
            "atlas",
            "party",
            "journey",
            "journal",
            "encounters",
            "archive",
        ],
        "maps": [],
        "chapters": ["Chapter 1", "Chapter 2", "Chapter 3", "Chapter 4", "Chapter 5"],
        "sources": [],
        "tile_behaviors": [],
    }
    live = {
        "mode": "area",
        "location": {
            "title": "Endor",
            "map_key": "area-04-00",
            "image_path": "",
            "x": 4,
            "y": 8,
        },
        "atlas": {
            "features": [
                {
                    "id": "area-04-00:collectibles:2:3",
                    "x": 2,
                    "y": 3,
                    "title": "Agility Seed",
                    "detail": "Available\nLeft chest",
                    "kind": "collectibles",
                    "completed": False,
                    "marker": "treasure",
                }
            ]
        },
        "party": [
            {
                "character_id": 0,
                "name": "Hero",
                "active": True,
                "alive": True,
                "poisoned": False,
                "paralyzed": False,
                "level": 8,
                "hp": 40,
                "max_hp": 50,
                "mp": 12,
                "max_mp": 20,
                "experience": 100,
                "items": [],
            }
        ],
        "journey": {
            "chapter": 4,
            "chapter_name": "Chapter 5",
            "gold": 100,
            "casino_coins": 0,
            "small_medals": 2,
            "treasure_opened": 1,
            "treasure_total": 216,
            "has_boat": True,
            "has_balloon": False,
            "time_name": "Day",
            "tactics": "Normal",
            "return_locations": ["Endor"],
        },
        "reference": {},
        "dialogue": "Welcome to Endor.",
        "journal": [
            {
                "entry_id": "entry-1",
                "text": "Welcome to Endor.",
                "location": "Endor",
                "map_id": 4,
                "submap": 0,
                "first_seen": "2026-09-09T12:00:00+00:00",
                "last_seen": "2026-09-09T12:00:00+00:00",
                "seen_count": 1,
            }
        ],
        "combat": {
            "memory_available": True,
            "battle_active": False,
            "detector_evidence": "test detector",
            "active": None,
            "recent": [],
            "archive_format": "One JSON file per completed combat",
        },
    }
    (tmp_path / "static.json").write_text(json.dumps(static), encoding="utf-8")
    (tmp_path / "live.json").write_text(json.dumps(live), encoding="utf-8")
    (tmp_path / "controls.json").write_text(
        json.dumps({"workspace": "atlas", "dashboard_open": True}),
        encoding="utf-8",
    )
    return static, live


def test_bridge_deduplicates_live_documents_and_round_trips_controls(
    tmp_path: Path,
) -> None:
    bridge = DashboardBridge(
        tmp_path,
        ROOT,
        {"schema_version": 1, "game": "Dragon Warrior IV"},
        launch=False,
    )

    assert bridge.publish({"mode": "area", "value": 1})
    first_timestamp = bridge.live_path.stat().st_mtime_ns
    assert not bridge.publish({"value": 1, "mode": "area"})
    assert bridge.live_path.stat().st_mtime_ns == first_timestamp
    controls = bridge.controls()
    assert controls["workspace"] == "atlas"
    assert controls["completed_features"] == []
    assert controls["dashboard_open"] is True


def test_closed_dashboard_is_not_relaunched(tmp_path: Path, monkeypatch) -> None:
    launches = []
    bridge = DashboardBridge(
        tmp_path,
        ROOT,
        {"schema_version": 1},
        launch=True,
    )
    controls = bridge.controls()
    controls["dashboard_open"] = False
    bridge.controls_path.write_text(json.dumps(controls), encoding="utf-8")
    monkeypatch.setattr(
        "game.dashboard_bridge.subprocess.Popen",
        lambda *args, **kwargs: launches.append((args, kwargs)),
    )

    bridge.publish({"mode": "area"})

    assert launches == []


def test_model_builds_all_workspaces_from_saved_pages_and_live_state() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x63:0x65] = bytes((0x04, 0x06))
    wram = bytearray(0x300)
    wram[0x15A] = 4
    state = read_state(bytes(ram), bytes(wram))
    model = DashboardModel(None, reference_sources(ROOT), None, "ROM not configured")

    static = model.static_document()
    live = model.dynamic_document(state, None)

    assert static["workspaces"] == [
        "atlas",
        "party",
        "journey",
        "journal",
        "encounters",
        "archive",
    ]
    assert len(static["sources"]) == 10
    assert all(source["available"] for source in static["sources"])
    assert len(static["tile_behaviors"]) >= 20
    assert static["atlas"]["error"] == "ROM not configured"
    assert live["location"]["map_key"] == "area-04-06"
    assert live["journey"]["chapter_name"] == "Chapter 5 · Hero"
    assert live["reference"]["saved_pages"] == 10


def test_model_assigns_stable_feature_ids() -> None:
    state = read_state(bytes(0x800), bytes(0x300))
    model = DashboardModel(None, reference_sources(ROOT), None)
    overlay = MapOverlay(
        "area-00-00",
        (MapWaypoint(4, 7, "Agility Seed", "Available", "collectibles"),),
    )

    feature = model.dynamic_document(state, overlay)["atlas"]["features"][0]

    assert feature["id"] == "area-00-00:collectibles:4:7"


def test_atlas_signature_ignores_player_motion_but_not_map_changes() -> None:
    first = {
        "mode": "area",
        "location": {
            "title": "Endor",
            "map_key": "area-04-00",
            "x": 4,
            "y": 8,
        },
        "atlas": {"features": []},
        "reference": {},
    }
    moved = json.loads(json.dumps(first))
    moved["location"].update(x=10, y=12)
    moved["dialogue"] = "The king awaits beyond the throne room."
    changed = json.loads(json.dumps(moved))
    changed["location"]["map_key"] = "area-04-01"

    assert workspace_render_signature("atlas", first) == workspace_render_signature(
        "atlas", moved
    )
    assert workspace_render_signature("atlas", first) != workspace_render_signature(
        "atlas", changed
    )


def test_workspace_signatures_ignore_volatile_values() -> None:
    first = {
        "party": [
            {
                "character_id": 0,
                "name": "Hero",
                "active": True,
                "hp": 40,
                "mp": 12,
                "level": 8,
            }
        ],
        "journey": {
            "chapter": 4,
            "gold": 100,
            "time_name": "Day",
            "treasure_opened": 2,
        },
        "journal": [],
    }
    changed = json.loads(json.dumps(first))
    changed["party"][0].update(hp=12, mp=4, level=9)
    changed["journey"].update(gold=999, time_name="Night", treasure_opened=3)
    changed["journal"].append({"entry_id": "one", "text": "A new line"})

    assert workspace_render_signature("party", first) == workspace_render_signature(
        "party", changed
    )
    assert workspace_render_signature("journey", first) == workspace_render_signature(
        "journey", changed
    )
    assert workspace_render_signature("journal", first) == workspace_render_signature(
        "journal", changed
    )

    changed["party"][0]["active"] = False
    changed["journey"]["chapter"] = 3
    assert workspace_render_signature("party", first) != workspace_render_signature(
        "party", changed
    )
    assert workspace_render_signature("journey", first) != workspace_render_signature(
        "journey", changed
    )


def test_feature_completion_combines_game_and_manual_state() -> None:
    available = {"id": "chest-1", "completed": False}
    looted = {"id": "chest-2", "completed": True}

    assert not feature_is_complete(available, set())
    assert feature_status(available, set()) == "AVAILABLE"
    assert feature_is_complete(available, {"chest-1"})
    assert feature_status(available, {"chest-1"}) == "MARKED COMPLETE"
    assert feature_is_complete(looted, set())
    assert feature_status(looted, set()) == "LOOTED IN GAME"


def test_volatile_live_update_uses_retained_widgets_instead_of_rebuild() -> None:
    class Widget:
        def configure(self, **_values) -> None:
            return None

    dashboard = object.__new__(__import__("dashboard").CompanionDashboard)
    dashboard.workspace = "atlas"
    dashboard.location_label = Widget()
    dashboard.mode_label = Widget()
    dashboard.source_label = Widget()
    dashboard.live = {
        "mode": "area",
        "location": {
            "title": "Endor",
            "map_key": "area-04-00",
            "x": 4,
            "y": 8,
        },
        "atlas": {"features": []},
        "reference": {},
        "dialogue": "First line",
    }
    dashboard._render_signature = workspace_render_signature(
        "atlas",
        dashboard.live,
    )
    calls = {"render": 0, "update": 0}
    dashboard._render_workspace = lambda: calls.__setitem__(
        "render",
        calls["render"] + 1,
    )
    dashboard._update_dynamic_workspace = lambda: calls.__setitem__(
        "update",
        calls["update"] + 1,
    )
    dashboard.live["location"].update(x=10, y=12)
    dashboard.live["dialogue"] = "Second line"

    dashboard._on_live_update()

    assert calls == {"render": 0, "update": 1}


def test_manual_feature_completion_persists_to_controls(tmp_path: Path) -> None:
    from dashboard import CompanionDashboard

    dashboard = object.__new__(CompanionDashboard)
    dashboard.controls_path = tmp_path / "controls.json"
    dashboard.controls = {"completed_features": []}
    dashboard.live = {
        "atlas": {
            "features": [
                {
                    "id": "area-04-00:collectibles:2:3",
                    "kind": "collectibles",
                    "completed": False,
                }
            ]
        }
    }
    dashboard._selected_feature_id = None
    dashboard._update_atlas = lambda: None

    dashboard._toggle_feature("area-04-00:collectibles:2:3")

    persisted = json.loads(dashboard.controls_path.read_text(encoding="utf-8"))
    assert persisted["completed_features"] == [
        "area-04-00:collectibles:2:3"
    ]

    dashboard._toggle_feature("area-04-00:collectibles:2:3")
    persisted = json.loads(dashboard.controls_path.read_text(encoding="utf-8"))
    assert persisted["completed_features"] == []


def test_map_transform_fits_then_centers_zoom_on_player() -> None:
    scale, origin = map_transform((1000, 500), (500, 500), (750, 250), 1.0)
    assert scale == 0.5
    assert origin == (0.0, 125.0)

    scale, origin = map_transform((1000, 500), (500, 500), (750, 250), 2.0)
    assert scale == 1.0
    assert origin == (-500.0, 0.0)


def test_window_dimensions_scale_for_dpi_and_stay_on_screen() -> None:
    assert window_dimensions(2560, 1440, 2.0) == (1890, 1185, 1440, 930)
    assert window_dimensions(1366, 768, 96 / 72) == (1257, 676, 960, 620)


def test_tk_atlas_retains_workspace_and_updates_dialogue_in_place(tmp_path: Path) -> None:
    from dashboard import CompanionDashboard

    _, live = dashboard_documents(tmp_path)
    try:
        dashboard = CompanionDashboard(tmp_path)
    except tk.TclError:
        return
    try:
        dashboard.live = live
        dashboard._render_workspace()
        dashboard.root.update_idletasks()
        workspace_frame = dashboard.workspace_host.winfo_children()[0]
        dialogue_label = dashboard._dynamic_widgets["dialogue"]

        dashboard.live["location"].update(x=9, y=12)
        dashboard.live["dialogue"] = "The tournament begins."
        dashboard._on_live_update()
        dashboard.root.update_idletasks()

        assert dashboard.workspace_host.winfo_children()[0] is workspace_frame
        assert dialogue_label.cget("text") == "The tournament begins."
        dashboard._show_feature_tooltip("area-04-00:collectibles:2:3")
        assert dashboard._dynamic_widgets["feature_detail_title"].cget("text") == "Agility Seed"
        assert "Left chest" in dashboard._dynamic_widgets["feature_detail_text"].cget("text")
        assert dashboard._tooltip_label is not None
        assert "Agility Seed" in dashboard._tooltip_label.cget("text")
        assert "AVAILABLE" in dashboard._tooltip_label.cget("text")
        assert "Left chest" in dashboard._tooltip_label.cget("text")
        dashboard._toggle_selected_feature()
        assert "area-04-00:collectibles:2:3" in dashboard._completed_feature_ids()
    finally:
        dashboard._close()


def test_tk_journal_updates_list_without_rebuilding_workspace(tmp_path: Path) -> None:
    from dashboard import CompanionDashboard

    _, live = dashboard_documents(tmp_path)
    try:
        dashboard = CompanionDashboard(tmp_path)
    except tk.TclError:
        return
    try:
        dashboard.live = live
        dashboard._select_workspace("journal")
        dashboard.root.update_idletasks()
        workspace_frame = dashboard.workspace_host.winfo_children()[0]
        journal_list = dashboard._dynamic_widgets["journal_list"]
        assert journal_list.size() == 1

        dashboard.live["journal"].append(
            {
                "entry_id": "entry-2",
                "text": "The tournament begins.",
                "location": "Endor Arena",
                "map_id": 4,
                "submap": 7,
                "first_seen": "2026-09-09T12:01:00+00:00",
                "last_seen": "2026-09-09T12:01:00+00:00",
                "seen_count": 1,
            }
        )
        dashboard._on_live_update()
        dashboard.root.update_idletasks()

        assert dashboard.workspace_host.winfo_children()[0] is workspace_frame
        assert journal_list.size() == 2
        assert "Endor Arena" in journal_list.get(0)
    finally:
        dashboard._close()


def test_tk_popout_map_retains_scene_while_player_moves(tmp_path: Path) -> None:
    from dashboard import CompanionDashboard

    static, live = dashboard_documents(tmp_path)
    image_path = tmp_path / "map.png"
    Image.new("RGB", (64, 64), "#386c50").save(image_path)
    static["maps"] = [
        {
            "key": "area-04-00",
            "title": "Endor",
            "path": str(image_path),
            "width": 4,
            "height": 4,
            "tile_width": 16,
            "tile_height": 16,
        }
    ]
    live["location"]["image_path"] = str(image_path)
    (tmp_path / "static.json").write_text(json.dumps(static), encoding="utf-8")
    (tmp_path / "live.json").write_text(json.dumps(live), encoding="utf-8")
    try:
        dashboard = CompanionDashboard(tmp_path)
    except tk.TclError:
        return
    try:
        dashboard.live = live
        dashboard._render_workspace()
        dashboard._open_map_popout()
        dashboard.root.update()
        assert dashboard._map_popout is not None
        popout = dashboard._map_popout
        player_item = dashboard._popout_items["player_outer"]
        before = dashboard._popout_canvas.coords(player_item)

        dashboard.live["location"].update(x=2, y=1)
        dashboard._on_live_update()
        dashboard.root.update_idletasks()

        assert dashboard._map_popout is popout
        assert dashboard._popout_items["player_outer"] == player_item
        assert dashboard._popout_canvas.coords(player_item) != before
    finally:
        dashboard._close()


def test_tk_combat_log_lazily_loads_selected_encounter_json(tmp_path: Path) -> None:
    from dashboard import CompanionDashboard

    _, live = dashboard_documents(tmp_path)
    encounter_id = "20260909T130000.000000Z-deadbeef"
    ended_at = "2026-09-09T13:00:04+00:00"
    summary = {
        "encounter_id": encounter_id,
        "started_at": "2026-09-09T13:00:00+00:00",
        "ended_at": ended_at,
        "duration_seconds": 4.0,
        "outcome": "victory",
        "start_location": "Endor",
        "end_location": "Endor",
        "reward_gold": 25,
        "reward_experience": 300,
        "enemy_count": 1,
        "enemy_labels": ["Monster $12"],
        "sample_count": 3,
    }
    record = {
        **summary,
        "schema_version": 1,
        "outcome_evidence": ["Documented battle reward counters increased"],
        "observed_gold_gain": 25,
        "observed_experience_gain": 300,
        "party_start": [{"character_id": 0, "name": "Hero", "hp": 40, "mp": 12}],
        "party_end": [{"character_id": 0, "name": "Hero", "hp": 30, "mp": 8}],
        "enemies": [
            {
                "label": "Monster $12",
                "starting_hp": 45,
                "final_hp": 0,
                "lowest_hp": 0,
                "attack": 14,
                "defense": 11,
                "agility": 8,
            }
        ],
        "timeline": [{}, {}, {}],
        "detector_evidence": "test detector",
    }
    archive = tmp_path.parent / "encounters" / "2026" / "09" / "09"
    archive.mkdir(parents=True)
    (archive / f"{encounter_id}.json").write_text(
        json.dumps(record),
        encoding="utf-8",
    )
    live["combat"]["recent"] = [summary]
    try:
        dashboard = CompanionDashboard(tmp_path)
    except tk.TclError:
        return
    try:
        dashboard.live = live
        dashboard._select_workspace("encounters")
        dashboard.root.update_idletasks()

        encounter_list = dashboard._dynamic_widgets["encounter_list"]
        detail = dashboard._dynamic_widgets["encounter_detail"]
        assert encounter_list.size() == 1
        assert "VICTORY" in encounter_list.get(0)
        assert "Monster $12: HP 45 → 0" in detail.get("1.0", "end")
        assert "300 XP / 25 gold" in detail.get("1.0", "end")
    finally:
        dashboard._close()