from pathlib import Path

from game.adapter import Adapter
from game.battle import BATTLE_MEMORY_SIZE
from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.presentation.qt import PanelDocumentUpdate, PanelDocumentView

from test_adapter import FakeMemory, ROOT, memory


def _adapter(tmp_path: Path) -> Adapter:
    return Adapter(
        GameContext(
            settings={"dashboard": False},
            repository_root=ROOT,
            state_directory=tmp_path,
        )
    )


def test_overworld_snapshot_preserves_qt_party_details_across_live_values(
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

    assert {section.section.key for section in view.state.section_views} == {
        "party",
        "resources",
    }
    party = next(
        section for section in view.state.section_views if section.section.key == "party"
    )
    party_widget = view.section_widget(party.identity)
    assert party_widget is not None
    action_widget = party_widget.action_widget(party.actions[0].identity)
    assert action_widget is not None
    action_widget.toggle_button.click()

    wram = bytearray(game_memory.wram)
    wram[2:4] = (25).to_bytes(2, "little")
    game_memory.wram = bytes(wram)
    update = view.set_snapshot(
        adapter.snapshot(game_memory),
        content_scope="dw4-test-rom",
    )
    updated_party = next(
        section for section in view.state.section_views if section.section.key == "party"
    )

    assert update == PanelDocumentUpdate.VALUES
    assert view.section_widget(updated_party.identity) is party_widget
    assert updated_party.actions[0].expanded
    assert "HP 25/50" in updated_party.rows[0].text


def test_battle_snapshot_renders_keyed_urgent_section(qtbot, tmp_path: Path) -> None:
    game_memory = memory()
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory.battle = bytes(battle)
    snapshot = _adapter(tmp_path).snapshot(game_memory)
    view = PanelDocumentView()
    qtbot.addWidget(view)
    view.show()

    view.set_snapshot(snapshot, content_scope="dw4-battle")
    view.set_active_role("urgent")

    assert [section.section.key for section in view.state.section_views] == [
        "battle",
        "atlas-confidence",
    ]
    battle_view = next(
        section
        for section in view.state.section_views
        if section.section.key == "battle"
    )
    assert battle_view.section.role == "urgent"
    widget = view.section_widget(battle_view.identity)
    assert widget is not None
    assert widget.action_widget(battle_view.actions[0].identity) is not None


def test_memory_failure_renders_as_urgent_qt_diagnostic(qtbot, tmp_path: Path) -> None:
    failing_memory = FakeMemory(b"", b"")
    snapshot = _adapter(tmp_path).snapshot(failing_memory)
    view = PanelDocumentView()
    qtbot.addWidget(view)

    view.set_snapshot(snapshot, content_scope="dw4-memory-failure")
    view.set_active_role("urgent")

    assert [section.section.key for section in view.state.section_views] == [
        "memory-access"
    ]
    assert snapshot.sections[0].alert