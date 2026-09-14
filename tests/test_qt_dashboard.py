import json
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt

from game.dashboard_bridge import DashboardBridge
from game.dashboard_presentation import live_presentation
from retroarch_overlay.app.dashboard import DashboardStore
from retroarch_overlay.presentation.qt import (
    QtDashboardCardsView,
    QtDashboardMapView,
    QtDashboardOverviewView,
    QtDashboardRecordsView,
    QtDashboardWindow,
)

from test_dashboard import dashboard_documents


def _window(qtbot, tmp_path: Path) -> tuple[QtDashboardWindow, DashboardStore]:
    dashboard_documents(tmp_path)
    store = DashboardStore(tmp_path)
    window = QtDashboardWindow(store, poll_interval_ms=10_000)
    qtbot.addWidget(window)
    window.show()
    return window, store


def test_real_documents_render_all_six_qt_workspaces(qtbot, tmp_path: Path) -> None:
    window, _ = _window(qtbot, tmp_path)

    assert window.workspace_keys == (
        "atlas",
        "party",
        "journey",
        "journal",
        "encounters",
        "archive",
    )
    assert isinstance(window.workspace_widget("atlas"), QtDashboardMapView)
    party = window.workspace_widget("party")
    journey = window.workspace_widget("journey")
    journal = window.workspace_widget("journal")
    encounters = window.workspace_widget("encounters")
    archive = window.workspace_widget("archive")
    assert isinstance(party, QtDashboardCardsView)
    assert isinstance(journey, QtDashboardOverviewView)
    assert isinstance(journal, QtDashboardRecordsView)
    assert isinstance(encounters, QtDashboardRecordsView)
    assert isinstance(archive, QtDashboardOverviewView)
    assert party._labels[("0", "HP")].text() == "HP  40 / 50"
    assert journey._metric_values["Gold"].text() == "100"
    assert journal.record_count == 1
    assert "Welcome to Endor" in journal.detail.toPlainText()
    assert archive._row_values[("evidence", "Live memory")].text() == "Unknown"


def test_companion_uses_compact_navigation_at_single_screen_rail_width(
    qtbot,
    tmp_path: Path,
) -> None:
    window, _ = _window(qtbot, tmp_path)
    window.resize(440, 700)
    qtbot.wait(1)
    window.select_workspace("encounters")
    encounters = window.workspace_widget("encounters")

    assert window.width() <= 440
    assert window.sidebar.isHidden()
    assert window.workspace_combo.isVisible()
    assert isinstance(encounters, QtDashboardRecordsView)
    assert encounters.splitter.orientation() == Qt.Orientation.Vertical


def test_real_atlas_renders_player_feature_and_manual_completion(
    qtbot,
    tmp_path: Path,
) -> None:
    static, live = dashboard_documents(tmp_path)
    image_path = tmp_path / "endor.png"
    Image.new("RGB", (256, 256), (44, 103, 66)).save(image_path)
    static["maps"] = [
        {
            "key": "area-04-00",
            "title": "Endor",
            "area": "Dungeon / town",
            "path": str(image_path),
            "map_id": 0x0400,
            "width": 16,
            "height": 16,
            "tile_width": 16,
            "tile_height": 16,
            "anchor_x": 0,
            "anchor_y": 0,
            "wraps": False,
        }
    ]
    live["location"]["image_path"] = str(image_path)
    live["presentation"] = live_presentation(static, live)
    (tmp_path / "static.json").write_text(json.dumps(static), encoding="utf-8")
    (tmp_path / "live.json").write_text(json.dumps(live), encoding="utf-8")
    store = DashboardStore(tmp_path)
    window = QtDashboardWindow(store, poll_interval_ms=10_000)
    qtbot.addWidget(window)
    atlas = window.workspace_widget("atlas")
    assert isinstance(atlas, QtDashboardMapView)
    assert atlas.map_view is not None

    assert atlas.map_view.layer_key == "area-04-00"
    assert atlas.map_view.image_item_count == 1
    assert atlas.map_view.player_scene_positions == ((64.0, 128.0),)
    assert atlas.feature_count == 1
    assert atlas.context._row_values[("dialogue", "Dialogue")].text() == (
        "Welcome to Endor."
    )
    assert "AVAILABLE" in atlas.features.item(0).toolTip()
    assert "collectibles" in atlas.map_view.available_overlay_kinds
    assert set(atlas._kind_checks) == {
        "objective",
        "collectibles",
        "entrance",
        "services",
        "locks",
        "connections",
        "npcs",
        "encounters",
    }
    atlas._kind_checks["collectibles"].setChecked(False)
    assert atlas.features.item(0).isHidden()
    assert not atlas.map_view.overlay_visibility["collectibles"]
    atlas._kind_checks["collectibles"].setChecked(True)
    atlas.features.item(0).setCheckState(Qt.CheckState.Checked)
    assert store.completed_ids("") == {
        "area-04-00:collectibles:2:3"
    }
    assert "MARKED COMPLETE" in atlas.features.item(0).toolTip()
    dialogue = atlas.context._row_values[("dialogue", "Dialogue")]
    atlas.open_popout()
    assert atlas._popout is not None
    popout = atlas._popout
    player_item = popout.view._player_items[0]
    before = player_item.pos()

    live["location"].update(x=5, y=9)
    live["dialogue"] = "The tournament begins."
    live["presentation"] = live_presentation(static, live)
    store.live_path.write_text(json.dumps(live), encoding="utf-8")
    window.poll()

    assert atlas._popout is popout
    assert popout.view._player_items[0] is player_item
    assert popout.view._player_items[0].pos() != before
    assert atlas.context._row_values[("dialogue", "Dialogue")] is dialogue
    assert dialogue.text() == "The tournament begins."


def test_world_selector_is_declared_by_plugin_and_persisted_by_qt(
    qtbot,
    tmp_path: Path,
) -> None:
    window, store = _window(qtbot, tmp_path)
    atlas = window.workspace_widget("atlas")
    assert isinstance(atlas, QtDashboardMapView)
    selector = atlas.choice_boxes["world_map"]

    selector.setCurrentIndex(selector.findData("underworld"))

    controls = json.loads(store.controls_path.read_text(encoding="utf-8"))
    assert controls["world_map"] == "underworld"


def test_journal_growth_updates_the_retained_qt_workspace(
    qtbot,
    tmp_path: Path,
) -> None:
    static, live = dashboard_documents(tmp_path)
    store = DashboardStore(tmp_path)
    window = QtDashboardWindow(store, poll_interval_ms=10_000)
    qtbot.addWidget(window)
    journal = window.workspace_widget("journal")
    assert isinstance(journal, QtDashboardRecordsView)

    live["journal"].append(
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
    live["presentation"] = live_presentation(static, live)
    store.live_path.write_text(json.dumps(live), encoding="utf-8")
    window.poll()

    assert window.workspace_widget("journal") is journal
    assert journal.record_count == 2
    assert "Endor Arena" in journal.list.item(0).text()


def test_combat_log_lazily_loads_the_full_encounter_record(
    qtbot,
    tmp_path: Path,
) -> None:
    static, live = dashboard_documents(tmp_path)
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
        "enemies": [{"label": "Monster $12", "starting_hp": 45, "final_hp": 0}],
        "timeline": [{}, {}, {}],
    }
    archive = tmp_path.parent / "encounters" / "2026" / "09" / "09"
    archive.mkdir(parents=True)
    (archive / f"{encounter_id}.json").write_text(
        json.dumps(record),
        encoding="utf-8",
    )
    live["combat"]["archive_root"] = str(tmp_path.parent / "encounters")
    live["combat"]["recent"] = [summary]
    live["presentation"] = live_presentation(static, live)
    (tmp_path / "live.json").write_text(json.dumps(live), encoding="utf-8")
    store = DashboardStore(tmp_path)
    window = QtDashboardWindow(store, poll_interval_ms=10_000)
    qtbot.addWidget(window)
    encounters = window.workspace_widget("encounters")
    assert isinstance(encounters, QtDashboardRecordsView)

    assert encounters.record_count == 1
    assert "VICTORY" in encounters.list.item(0).text()
    assert "300 XP / 25 gold" in encounters.detail.toPlainText()
    assert '"starting_hp": 45' in encounters.detail.toPlainText()


def test_closing_real_qt_window_suppresses_bridge_relaunch(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_directory = tmp_path / "state"
    bridge = DashboardBridge(
        state_directory,
        Path(__file__).parents[1],
        {"schema_version": 1},
        launch=True,
    )
    assert bridge.root is not None
    _, live = dashboard_documents(bridge.root)
    store = DashboardStore(bridge.root)
    window = QtDashboardWindow(store, poll_interval_ms=10_000)
    qtbot.addWidget(window)
    window.close()
    launches = []
    monkeypatch.setattr(
        "game.dashboard_bridge.subprocess.Popen",
        lambda *args, **kwargs: launches.append((args, kwargs)),
    )

    bridge.publish(live)

    assert launches == []