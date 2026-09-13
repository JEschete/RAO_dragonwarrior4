import json
from pathlib import Path

import pytest

from game.dashboard_presentation import (
    active_encounter_text,
    combat_analytics_lines,
    feature_is_complete,
    feature_status,
    party_detail_lines,
    retroachievements_summary,
)
from game.dashboard_bridge import DashboardBridge
from game.dashboard_model import DashboardModel
from game.dashboard_presentation import live_presentation, static_presentation
from game.reference_data import reference_sources
from game.rom_assets import WORLD_MAP_SPECS
from game.state import read_state
from retroarch_overlay.core.retroachievements import RAProgress
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
        "schema_version": 1,
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
                "strength": 18,
                "agility": 21,
                "vitality": 24,
                "intelligence": 27,
                "luck": 30,
                "items": [
                    {
                        "item_id": 0,
                        "name": "Cypress Stick",
                        "category": "weapon",
                        "equipped": True,
                    },
                    {
                        "item_id": 83,
                        "name": "Medical Herb",
                        "category": "item",
                        "equipped": False,
                    },
                ],
                "spells": [
                    {"name": "Blaze", "usage": "battle"},
                    {"name": "Return", "usage": "field"},
                ],
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
            "archive_root": str(tmp_path.parent / "encounters"),
            "archive_format": "One JSON file per completed combat",
            "analytics": {
                "total_encounters": 4,
                "session_encounters": 2,
                "win_rate": 0.75,
                "reward_experience": 1200,
                "reward_gold": 340,
                "locations": [{"name": "Endor", "encounters": 3}],
                "enemies": [
                    {"monster_id": 18, "label": "Monster $12", "encounters": 2}
                ],
            },
        },
    }
    static["presentation"] = static_presentation(WORLD_MAP_SPECS)
    live["presentation"] = live_presentation(static, live)
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
    assert controls["world_map"] == "world"
    assert controls["completed_features"] == []
    assert controls["completed_features_by_playthrough"] == {}
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


def test_malformed_controls_do_not_block_live_publication(tmp_path: Path) -> None:
    bridge = DashboardBridge(
        tmp_path,
        ROOT,
        {"schema_version": 1},
        launch=False,
    )
    bridge.controls_path.write_text("{partial", encoding="utf-8")

    assert bridge.publish({"schema_version": 1, "mode": "area"})
    assert json.loads(bridge.live_path.read_text(encoding="utf-8"))["mode"] == (
        "area"
    )


def test_bridge_launches_one_generic_qt_sidecar(tmp_path: Path, monkeypatch) -> None:
    launches = []

    class Process:
        def poll(self):
            return None

    def launch(*args, **kwargs):
        launches.append((args, kwargs))
        return Process()

    bridge = DashboardBridge(
        tmp_path,
        ROOT,
        {"schema_version": 1},
        launch=True,
    )
    monkeypatch.setattr("game.dashboard_bridge.subprocess.Popen", launch)

    bridge.publish({"schema_version": 1, "mode": "area"})
    bridge.publish({"schema_version": 1, "mode": "world"})

    assert len(launches) == 1
    command = launches[0][0][0]
    assert command[1:3] == (
        "-m",
        "retroarch_overlay.presentation.qt.dashboard_main",
    )
    assert command[3:] == ("--state-dir", str(bridge.root))


def test_bridge_close_escalates_a_hung_sidecar_with_bounded_waits(tmp_path: Path) -> None:
    class Process:
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False
            self.waits = []

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            self.waits.append(timeout)
            if len(self.waits) == 1:
                raise __import__("subprocess").TimeoutExpired("dashboard", timeout)
            return 0

    bridge = DashboardBridge(
        tmp_path,
        ROOT,
        {"schema_version": 1},
        launch=False,
    )
    process = Process()
    bridge._process = process

    bridge.close()

    assert process.terminated
    assert process.killed
    assert process.waits == [1.0, 1.0]


def test_bridge_throttles_crash_restarts_without_blocking_publication(
    tmp_path: Path,
    monkeypatch,
) -> None:
    now = [10.0]
    launches = []

    class Process:
        running = True

        def poll(self):
            return None if self.running else 1

    def launch(*_args, **_kwargs):
        process = Process()
        launches.append(process)
        return process

    bridge = DashboardBridge(
        tmp_path,
        ROOT,
        {"schema_version": 1},
        launch=True,
        restart_delay_seconds=2.0,
    )
    monkeypatch.setattr("game.dashboard_bridge.time.monotonic", lambda: now[0])
    monkeypatch.setattr("game.dashboard_bridge.subprocess.Popen", launch)

    assert bridge.publish({"schema_version": 1, "value": 1})
    launches[0].running = False
    now[0] = 11.0
    assert bridge.publish({"schema_version": 1, "value": 2})
    assert len(launches) == 1
    now[0] = 12.1
    assert bridge.publish({"schema_version": 1, "value": 3})
    assert len(launches) == 2


def test_failed_atomic_publish_preserves_previous_document(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "live.json"
    path.write_bytes(b"previous\n")
    monkeypatch.setattr(
        "game.dashboard_bridge.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        DashboardBridge._write_bytes(path, b"replacement\n")

    assert path.read_bytes() == b"previous\n"
    assert tuple(tmp_path.glob("live.json.*.tmp")) == ()


def test_bridge_normalizes_unknown_world_map(tmp_path: Path) -> None:
    root = tmp_path / "dashboard"
    root.mkdir()
    root.joinpath("controls.json").write_text(
        json.dumps({"world_map": "unknown"}),
        encoding="utf-8",
    )

    bridge = DashboardBridge(
        tmp_path,
        ROOT,
        {"schema_version": 1},
        launch=False,
    )

    assert bridge.controls()["world_map"] == "world"


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
    assert sum(source["available"] for source in static["sources"]) == sum(
        (ROOT / "resources" / source["filename"]).is_file()
        for source in static["sources"]
    )
    assert len(static["tile_behaviors"]) >= 20
    assert static["atlas"]["error"] == "ROM not configured"
    assert live["location"]["map_key"] == "area-04-06"
    assert live["journey"]["chapter_name"] == "Chapter 5 · Hero"
    assert live["reference"]["saved_pages"] == 10
    workspace_specs = static["presentation"]["workspaces"]
    assert [value["kind"] for value in workspace_specs] == [
        "map",
        "cards",
        "overview",
        "records",
        "records",
        "overview",
    ]
    assert set(live["presentation"]["workspaces"]) == {
        "atlas",
        "party",
        "journey",
        "journal",
        "encounters",
        "archive",
    }
    assert live["presentation"]["workspaces"]["atlas"]["map"]["key"] == (
        "area-04-06"
    )
    assert live["presentation"]["workspaces"]["party"]["cards"][0]["title"] == (
        "Hero"
    )


def test_model_builds_schema_valid_waiting_document() -> None:
    waiting = DashboardModel.waiting_document("Memory descriptor unavailable")

    assert waiting["schema_version"] == 1
    assert waiting["mode"] == "waiting"
    assert waiting["presentation"]["status"]["detail"] == (
        "Memory descriptor unavailable"
    )
    assert waiting["presentation"]["workspaces"] == {}


def test_party_details_and_retroachievements_are_presentable(tmp_path: Path) -> None:
    _, live = dashboard_documents(tmp_path)
    stats, inventory, battle_spells, field_spells = party_detail_lines(
        live["party"][0]
    )

    assert stats == "STR 18  ·  AGI 21  ·  VIT 24  ·  INT 27  ·  LUCK 30"
    assert inventory == "Equipped: Weapon: Cypress Stick\nPack: Medical Herb"
    assert battle_spells == "Battle: Blaze"
    assert field_spells == "Field: Return"
    assert retroachievements_summary(
        {
            "retroachievements": {
                "username": "Jude",
                "unlocked": 12,
                "total": 43,
                "points": 80,
                "total_points": 360,
            }
        }
    ) == ("12/43 unlocked · 80/360 points", "Account: Jude")
    assert combat_analytics_lines(live["combat"]["analytics"]) == (
        "4 lifetime / 2 this session / 75% victories / 1,200 XP / 340 gold",
        "Endor (3)",
        "Monster $12 (2)",
    )


def test_model_serializes_complete_achievement_catalog() -> None:
    model = DashboardModel(
        None,
        (),
        RAProgress("Jude", frozenset({52318, 52319})),
    )

    progress = model.static_document()["retroachievements"]

    assert progress["unlocked"] == 2
    assert progress["total"] == 43
    assert progress["points"] == 15
    assert progress["total_points"] == 360
    assert sum(value["unlocked"] for value in progress["achievements"]) == 2
    assert "Highest ATK Monster $12 14" in active_encounter_text(
        {
            "location": "Endor",
            "frame_count": 3,
            "enemies": [
                {
                    "label": "Monster $12",
                    "final_hp": 30,
                    "attack": 14,
                    "agility": 8,
                }
            ],
        }
    )


def test_model_assigns_stable_feature_ids() -> None:
    state = read_state(bytes(0x800), bytes(0x300))
    model = DashboardModel(None, reference_sources(ROOT), None)
    overlay = MapOverlay(
        "area-00-00",
        (MapWaypoint(4, 7, "Agility Seed", "Available", "collectibles"),),
    )

    feature = model.dynamic_document(state, overlay)["atlas"]["features"][0]

    assert feature["id"] == "area-00-00:collectibles:4:7"
    assert feature["distance"] == 11
    assert feature["direction"] == "south-east"


@pytest.mark.parametrize("world_map_key", tuple(WORLD_MAP_SPECS))
def test_model_honors_explicit_world_layer_selection(
    tmp_path: Path,
    world_map_key: str,
) -> None:
    class Assets:
        region = "US"

        def render_world_map(self, key: str) -> Path:
            return tmp_path / f"{key}.png"

    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x63:0x65] = bytes((0xFF, 0xFF))
    ram[0x42:0x44] = bytes((12, 8))
    state = read_state(bytes(ram), bytes(0x300))

    live = DashboardModel(Assets(), (), None).dynamic_document(
        state,
        None,
        world_map_key=world_map_key,
    )

    assert live["location"]["map_key"] == world_map_key
    assert live["location"]["title"] == WORLD_MAP_SPECS[world_map_key][0]
    assert live["location"]["image_path"] == str(
        tmp_path / f"{world_map_key}.png"
    )
    assert "selected in companion" in live["location"]["evidence"]


def test_feature_completion_combines_game_and_manual_state() -> None:
    available = {"id": "chest-1", "completed": False}
    looted = {"id": "chest-2", "completed": True}

    assert not feature_is_complete(available, set())
    assert feature_status(available, set()) == "AVAILABLE"
    assert feature_is_complete(available, {"chest-1"})
    assert feature_status(available, {"chest-1"}) == "MARKED COMPLETE"
    assert feature_is_complete(looted, set())
    assert feature_status(looted, set()) == "LOOTED IN GAME"
