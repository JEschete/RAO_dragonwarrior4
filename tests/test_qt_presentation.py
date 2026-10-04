from pathlib import Path
from unittest.mock import Mock
from dataclasses import replace

import pytest
from PIL import Image

from game.adapter import Adapter
from game.battle import BATTLE_MEMORY_SIZE
from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.presentation.qt import PanelDocumentUpdate, PanelDocumentView
from retroarch_overlay.models import MapDocument, MapLayer, MapPosition, OverlaySnapshot, PanelAction, PanelSection
from retroarch_overlay.presentation.qt.map_view import QtMapView

from test_adapter import FakeMemory, ROOT, memory


def _adapter(tmp_path: Path) -> Adapter:
    return Adapter(
        GameContext(
            settings={},
            repository_root=ROOT,
            state_directory=tmp_path,
        )
    )


def test_loading_area_keeps_open_atlas_without_recording_a_stale_position() -> None:
    from retroarch_overlay.presentation.qt.overlay_window import QtOverlayWindow

    document = MapDocument("DW4 Atlas", ())
    window = Mock()
    host = Mock(_map_document=document, _map_window=window, _minimap_window=None,
                _hero_paths_title=document.title, _hero_paths={}, _settings=None)
    snapshot = OverlaySnapshot("DW4", "Loading area", (), map_document=document)
    QtOverlayWindow._sync_map_tools(host, snapshot)
    host._clear_map_tools.assert_not_called()
    host._destroy_map_windows.assert_not_called()
    host._map_retire_timer.start.assert_not_called()
    host._map_retire_timer.stop.assert_called_once()
    window.update_map.assert_not_called()
    assert host._map_document is document and host._map_position is None
    assert host._hero_paths == {}


@pytest.mark.parametrize("theme", ("light", "dark"))
@pytest.mark.parametrize("width", (360, 760))
def test_bestiary_and_guide_render_with_search_at_overlay_widths(qtbot, tmp_path: Path, theme: str, width: int) -> None:
    from game.battle import BattleState
    from game.state import read_state
    from test_adapter import _monster
    from retroarch_overlay.presentation.theme import THEME_PALETTES

    assets = Mock(region="US")
    assets.indexed_name.return_value = "Medical Herb"
    assets.monster_definition.side_effect = lambda identity: _monster(
        f"Monster {identity}", max_hp=1200 if identity == 7 else 8,
        drop_item_id=0x53, drop_denominator=32,
        resistances=(("Blaze", "Susceptible"), ("Sleep", "Partial resistance"),
                     ("Stopspell", "Strong resistance"), ("Beat", "Immune")))
    instance = Adapter(GameContext(repository_root=ROOT), assets)
    view = PanelDocumentView()
    view.resize(width, 900)
    view.set_theme(theme)
    qtbot.addWidget(view)
    view.show()
    bestiary = replace(instance._bestiary_section(BattleState.unavailable(), (3, 7)), collapsible=False)
    guide = replace(instance._guide_section(read_state(memory().ram, memory().wram)), collapsible=False)
    for section in (bestiary, guide):
        view.set_snapshot(OverlaySnapshot("DW4", "Town", (section,)))
        widget = view.section_widget(view.state.section_views[0].identity)
        qtbot.waitUntil(lambda: widget.width() > 0)
        qtbot.waitUntil(lambda: not widget._fit_timer.isActive() and not widget.row_view._fit_timer.isActive())
        assert widget.width() <= width
        if section.key == "guide":
            assert widget.document_contents.count() > 100
            widget.document_search.setText("Burland")
            assert widget.document_next.isEnabled()
            browser_image = widget.document_browser.viewport().grab().toImage()
            assert browser_image.pixelColor(2, 2).name() == THEME_PALETTES[theme]["background"]
            assert widget.document_browser.palette().color(widget.palette().ColorRole.Link).name() == THEME_PALETTES[theme]["accent"]
            link = widget.document_browser.document().find("Introduction")
            assert link.charFormat().foreground().color().name() == THEME_PALETTES[theme]["accent"]
            controls = (widget.document_search, widget.document_match_count,
                        widget.document_previous, widget.document_next)
            for index, control in enumerate(controls):
                assert all(not control.geometry().intersects(other.geometry()) for other in controls[index + 1:])
        image = view.grab().toImage()
        assert image.deviceIndependentSize().width() == pytest.approx(width)
        path = tmp_path / f"{section.key}-{width}-{theme}.png"
        assert image.save(str(path))
        print(f"Overlay screenshot: {path}")


@pytest.mark.parametrize("width", (360, 760))
def test_guide_shortcuts_wrap_as_buttons_and_combat_columns_clear(qtbot, tmp_path: Path, width: int) -> None:
    from game.battle import BattleState
    from game.state import read_state
    from retroarch_overlay.models import PanelColumn, PanelRow

    view = PanelDocumentView()
    view.set_theme("light")
    view.resize(width, 760)
    qtbot.addWidget(view)
    view.show()
    shortcuts = tuple(PanelAction(label, label, (), key=f"jump-{index}", document_anchor="chapter")
                      for index, label in enumerate(("Chapter 1", "Current area", "Bosses")))
    guide = PanelSection("Guide", (), key="guide", markdown="# Chapter\n\nWalkthrough", actions=shortcuts)
    view.set_snapshot(OverlaySnapshot("DW4", "Town", (guide,)))
    widget = view.section_widget(view.state.section_views[0].identity)
    qtbot.waitUntil(lambda: widget._actions_host.height() > 0)
    buttons = [widget.action_widget(action.identity) for action in view.state.section_views[0].actions]
    assert all(button.instant and not widget._actions_layout.is_full_row(button) for button in buttons)
    assert all(not button.toggle_button.isCheckable() for button in buttons)
    for index, button in enumerate(buttons):
        assert 0 <= button.geometry().left() and button.geometry().right() < widget._actions_host.width()
        assert all(not button.geometry().intersects(other.geometry()) for other in buttons[index + 1:])

    instance = _adapter(tmp_path)
    state = read_state(memory().ram, memory().wram)
    field = instance._combatants_section(state, BattleState.unavailable())
    battle = replace(field, columns=field.columns + (PanelColumn("enemies", "Enemies", (PanelRow("Slime"),)),))
    view.set_snapshot(OverlaySnapshot("DW4", "Combat", (battle,)))
    widget = view.section_widget(view.state.section_views[0].identity)
    assert len(widget._column_widgets) == 2
    view.set_snapshot(OverlaySnapshot("DW4", "Town", (field,)))
    assert set(widget._column_widgets) == {"party"}
    qtbot.waitUntil(lambda: widget._column_widgets["party"][0].width() == widget.columns_host.width())


def test_alternate_map_views_change_pixels_and_refresh_selected_view(qtbot, tmp_path: Path) -> None:
    cutaway = tmp_path / "cutaway.png"
    roof = tmp_path / "roof.png"
    changed = tmp_path / "roof-night.png"
    for path, color in ((cutaway, "red"), (roof, "green"), (changed, "blue")):
        Image.new("RGB", (64, 64), color).save(path)
    variant = MapLayer("area-roofs", "Roofs", "Town", roof)
    layer = MapLayer("area", "Town", "Town", cutaway, image_variants=(variant,))
    view = QtMapView(MapDocument("Town", (layer,)))
    qtbot.addWidget(view)
    view.resize(360, 360)
    view.show()
    view.set_image_view("Roofs")
    assert view.image_view == "Roofs"
    assert view._pixmap.toImage().pixelColor(0, 0).name() == "#008000"
    view.set_zoom(2)
    view.update_document(MapDocument("Town", (replace(layer, image_variants=(replace(variant, image_path=changed),)),)))
    assert view.image_view == "Roofs" and view.zoom == 2
    assert view._pixmap.toImage().pixelColor(0, 0).name() == "#0000ff"
    view.set_image_view("Cutaway")
    assert view._pixmap.toImage().pixelColor(0, 0).name() == "#ff0000"


def test_map_target_action_dispatch_and_manual_browse_do_not_move_the_player(qtbot, tmp_path: Path) -> None:
    image = tmp_path / "map.png"
    Image.new("RGB", (64, 64), "green").save(image)
    home = MapLayer("home", "Home", "Town", image, map_id=1)
    destination = MapLayer("destination", "Destination", "Town", image, map_id=2)
    map_view = QtMapView(MapDocument("Atlas", (home, destination)))
    qtbot.addWidget(map_view)
    actual = MapPosition("Town", 1, 1, 1)
    map_view.update_map(actual)
    map_view.browse_layer("destination")
    map_view.update_map(actual)
    assert map_view.layer_key == "destination"
    assert map_view.position is None and map_view.player_scene_positions == ()
    map_view.follow_player()
    map_view.update_map(actual)
    assert map_view.layer_key == "home" and map_view.position == actual
    view = PanelDocumentView()
    qtbot.addWidget(view)
    action = PanelAction("Map: Destination", "Destination", (), key="return-map", map_layer_key="destination")
    view.set_snapshot(OverlaySnapshot("DW4", "Home", (PanelSection("Journey", (), actions=(action,), key="journey"),)))
    identity = view.state.section_views[0].actions[0].identity
    with qtbot.waitSignal(view.map_navigation_requested) as signal:
        view._toggle_action(identity)
    assert signal.args == ["destination"]


def test_native_frame_changes_do_not_redraw_static_map_until_selected(qtbot, tmp_path: Path) -> None:
    static = tmp_path / "static.png"
    first = tmp_path / "frame-first.png"
    second = tmp_path / "frame-second.png"
    for path, color in ((static, "red"), (first, "green"), (second, "blue")):
        Image.new("RGB", (64, 64), color).save(path)
    frame = MapLayer("world-frame", "Native frame", "World", first)
    layer = MapLayer("world", "World", "World", static, image_variants=(frame,))
    view = QtMapView(MapDocument("Atlas", (layer,)))
    qtbot.addWidget(view)
    view.update_map(MapPosition("World", 0, 1, 1, True))
    builds = view.static_build_count
    changed = replace(layer, image_variants=(replace(frame, image_path=second),))
    view.update_document(MapDocument("Atlas", (changed,)))
    assert view.static_build_count == builds
    assert view._pixmap.toImage().pixelColor(0, 0).name() == "#ff0000"
    view.set_image_view("Native frame")
    assert view._pixmap.toImage().pixelColor(0, 0).name() == "#0000ff"


def test_overworld_snapshot_preserves_live_party_columns_across_values(
    qtbot,
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    game_memory = memory()
    first = adapter.snapshot(game_memory)
    view = PanelDocumentView()
    view.resize(440, 760)
    qtbot.addWidget(view)
    view.show()

    view.set_snapshot(first, content_scope="dw4-test-rom")
    view.set_active_role("party")

    assert {section.section.key for section in view.state.section_views} == {"combatants"}
    party = view.state.section_views[0]
    party_widget = view.section_widget(party.identity)
    assert party_widget is not None
    assert party.open
    assert not party_widget.header_button.isVisible()
    party_rows = party_widget._column_widgets["party"][2]

    wram = bytearray(game_memory.wram)
    wram[2:4] = (25).to_bytes(2, "little")
    game_memory.wram = bytes(wram)
    update = view.set_snapshot(
        adapter.snapshot(game_memory),
        content_scope="dw4-test-rom",
    )
    updated_party = next(
        section for section in view.state.section_views if section.section.key == "combatants"
    )

    assert update == PanelDocumentUpdate.VALUES
    assert view.section_widget(updated_party.identity) is party_widget
    assert updated_party.open
    assert party_widget._column_widgets["party"][2] is party_rows
    assert party_rows.row_model.rows[0].meters[0].value == 25
    assert party_rows.row_model.rows[0].meters[0].maximum == 50


def test_battle_snapshot_renders_keyed_urgent_section(qtbot, tmp_path: Path) -> None:
    game_memory = memory()
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory.battle = bytes(battle)
    game_memory.context_flags = 0x80
    snapshot = _adapter(tmp_path).snapshot(game_memory)
    view = PanelDocumentView()
    qtbot.addWidget(view)
    view.show()

    view.set_snapshot(snapshot, content_scope="dw4-battle")
    view.set_active_role("urgent")

    assert [section.section.key for section in view.state.section_views] == ["combatants", "guide"]
    battle_view = next(
        section
        for section in view.state.section_views
        if section.section.key == "combatants"
    )
    assert battle_view.section.role == "urgent"
    widget = view.section_widget(battle_view.identity)
    assert widget is not None
    assert widget._column_widgets["enemies"][2].row_model.rowCount() == 1
    assert battle_view.actions == ()


def test_memory_failure_renders_as_urgent_qt_diagnostic(qtbot, tmp_path: Path) -> None:
    failing_memory = FakeMemory(b"", b"")
    snapshot = _adapter(tmp_path).snapshot(failing_memory)
    view = PanelDocumentView()
    qtbot.addWidget(view)

    view.set_snapshot(snapshot, content_scope="dw4-memory-failure")
    view.set_active_role("urgent")

    assert [section.section.key for section in view.state.section_views] == [
        "memory-access", "guide"
    ]
    assert snapshot.sections[0].alert


@pytest.mark.parametrize("width", (360, 760))
def test_two_panel_vitals_render_without_overlapping_at_overlay_widths(qtbot, tmp_path: Path, width: int) -> None:
    game_memory = memory()
    wram = bytearray(game_memory.wram)
    for identifier in (0, 1, 7):
        start = 1 + identifier * 30
        wram[start] = 0x80
        wram[start + 5] = 16
        wram[start + 1:start + 3] = (35).to_bytes(2, "little")
        wram[start + 3:start + 5] = (12).to_bytes(2, "little")
        wram[start + 12:start + 14] = (60).to_bytes(2, "little")
        wram[start + 14:start + 16] = (24).to_bytes(2, "little")
    game_memory.wram = bytes(wram)
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[6:10] = bytes((3, 0xFF, 0xFF, 0xFF))
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 0xC0, 0, 0, 0, 30, 0, 3, 0))
    game_memory.battle = bytes(battle)
    game_memory.context_flags = 0x80
    assets = Mock()
    assets.region = "US"
    assets.has_area.return_value = True
    assets.feature_overlay.return_value = None
    assets.tile_transition_routes.return_value = ()
    assets.conditional_search_overlay.return_value = None
    assets.town_shops.return_value = ()
    assets.monster_name.return_value = "Giant Worm"
    assets.monster_vitals.return_value = (45, 6)
    assets.monster_definition.return_value = None
    assets.return_destinations.return_value = ()
    assets.diagnostics = ()
    assets.spell_milestones.return_value = ()
    assets.collectible_catalog.return_value = ()
    assets.encounter_pool.return_value = None
    assets.indoor_encounter_pool.return_value = None
    snapshot = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path), assets).snapshot(game_memory)
    view = PanelDocumentView()
    view.resize(width, 720)
    qtbot.addWidget(view)
    view.show()
    view.set_snapshot(snapshot)
    widget = view.section_widget(view.state.section_views[0].identity)
    assert widget is not None
    qtbot.waitUntil(lambda: widget._column_widgets["party"][0].width() > 0)
    party, _, party_rows = widget._column_widgets["party"]
    enemies, _, enemy_rows = widget._column_widgets["enemies"]
    assert party.geometry().right() < enemies.geometry().left()
    assert enemy_rows.row_model.rows[0].meters[0].maximum == 45
    image = view.grab().toImage()
    assert not image.isNull()
    colors = {image.pixelColor(horizontal, vertical).name()
              for vertical in range(0, min(350, image.height()), 3)
              for horizontal in range(0, image.width(), 3)}
    assert "#198754" in colors
    assert "#087ca7" in colors
    assert image.save(str(tmp_path / f"dw4-overlay-{width}.png"))