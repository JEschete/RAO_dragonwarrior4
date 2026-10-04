from dataclasses import replace
from unittest.mock import Mock

import pytest

from game.adapter import Adapter
from game.arena import ArenaPrediction, PredictionStatus
from game.battle import BattleState
from game.state import read_state
from retroarch_overlay.core.contracts import GameContext


class ArenaMemory:
    def __init__(self) -> None:
        self.ram = bytearray(0x800)
        self.ram[0x63:0x65] = bytes((4, 1))
        self.ram[0xF6] = 0x6B
        self.ram[0x7B5:0x7B7] = bytes((0x39, 0x6E))
        self.workspace = bytearray(0x2000)
        self.workspace[0xE45:0xE49] = bytes((0, 0, 1, 255))
        self.workspace[0xE39:0xE41] = bytes((2, 3, 4, 0, 1, 2, 3, 0))
        self.workspace[0xE83] = 10

    def read_memory(self, address: int, size: int) -> bytes:
        if size > 4096:
            raise ValueError("RetroArch limits reads to 4096 bytes")
        if address < 0x800:
            return bytes(self.ram[address:address + size])
        return bytes(self.workspace[address - 0x6000:address - 0x6000 + size])


def adapter() -> Adapter:
    assets = Mock()
    assets.monster_name.side_effect = lambda identifier: f"Monster {identifier}"
    assets.arena_payout.return_value = 21
    assets.arena_program.return_value = bytes(0x80000)
    return Adapter(GameContext(), assets)


def test_button_queues_capture_without_network_reads_on_the_ui_thread() -> None:
    instance = adapter()
    memory = ArenaMemory()
    instance._arena_predictor = Mock(status=PredictionStatus())
    battle = instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    assert battle.arena and not battle.active
    instance._arena_predictor.start.assert_not_called()
    section = instance._arena_section(read_state(bytes(0x800), bytes(0x300)), battle)
    assert len(section.actions) == 1
    assert section.actions[0].key == "arena-predict"
    assert not any("Entry 4" in row.text for row in section.rows)
    memory.read_memory = Mock(wraps=memory.read_memory)
    section.actions[0].command()
    memory.read_memory.assert_not_called()
    instance._arena_predictor.start.assert_not_called()
    pending = instance._arena_section(read_state(bytes(0x800), bytes(0x300)), battle)
    assert pending.actions[0].key == "arena-cancel" and pending.rows[-1].text == "Capturing matchup"
    instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor.start.assert_called_once_with(
        bytes(0x80000), bytes(memory.ram), bytes(memory.workspace), simulations=100)


def test_custom_count_is_locked_during_capture_and_drives_progress() -> None:
    instance = adapter()
    memory = ArenaMemory()
    instance._arena_predictor = Mock(status=PredictionStatus())
    battle = instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    field = instance._arena_section(read_state(bytes(0x800), bytes(0x300)), battle).inputs[0]
    assert field.label == "Simulations" and field.value == 100 and field.enabled
    field.command(1000)
    instance.predict_arena()
    instance.set_arena_simulations(500)
    assert instance._arena_simulations == 1000
    pending = instance._arena_section(read_state(bytes(0x800), bytes(0x300)), battle)
    assert not pending.inputs[0].enabled
    instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor.start.assert_called_once_with(
        bytes(0x80000), bytes(memory.ram), bytes(memory.workspace), simulations=1000)
    instance._arena_predictor.status = PredictionStatus(running=True, completed=250, simulations=1000)
    running = instance._arena_section(read_state(bytes(0x800), bytes(0x300)), battle)
    assert not running.inputs[0].enabled
    assert any(row.text == "Simulating 250/1,000" and row.progress == 0.25 for row in running.rows)


def test_prediction_displays_slot_chances_and_draws_and_clears_outside_arena() -> None:
    instance = adapter()
    memory = ArenaMemory()
    battle = instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor._status = PredictionStatus(
        completed=100, result=ArenaPrediction((0, 0, 1, 255), (20, 30, 40, 0), 10))
    section = instance._arena_section(read_state(bytes(0x800), bytes(0x300)), battle)
    assert any("Entry 1 · Monster 0 · 2.1x · 20% win chance" == row.text for row in section.rows)
    assert any("Entry 2 · Monster 0 · 3.2x · 30% win chance" == row.text for row in section.rows)
    assert any("Draw 10% · 100 simulations" == row.text for row in section.rows)
    assert all(not row.tooltip for row in section.rows)
    memory.ram[0xF6] = 0
    assert not instance._with_arena(memory, bytes(memory.ram), replace(battle, arena=False)).arena
    assert instance._arena_key is None
    assert instance._arena_predictor.status.result is None


def test_changing_matchup_cancels_old_results_and_rejects_stale_click() -> None:
    instance = adapter()
    memory = ArenaMemory()
    instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor = Mock(status=PredictionStatus())
    instance.predict_arena()
    memory.workspace[0xE45] = 7
    instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor.start.assert_not_called()
    instance._arena_predictor.cancel.assert_called_once()
    assert instance._arena_requested is None


def test_running_prediction_has_progress_and_no_duplicate_start_button() -> None:
    instance = adapter()
    memory = ArenaMemory()
    battle = instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor._status = PredictionStatus(running=True, completed=23)
    section = instance._arena_section(read_state(bytes(0x800), bytes(0x300)), battle)
    assert len(section.actions) == 1 and section.actions[0].key == "arena-cancel"
    assert any(row.text == "Simulating 23/100" and row.progress == 0.23 for row in section.rows)


def test_cancel_before_capture_keeps_the_matchup_and_reenables_count() -> None:
    instance = adapter()
    memory = ArenaMemory()
    battle = instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    key = instance._arena_key
    instance.set_arena_simulations(1000)
    instance.predict_arena()
    pending = instance._arena_section(read_state(bytes(0x800), bytes(0x300)), battle)
    pending.actions[0].command()
    assert instance._arena_requested is None and instance._arena_key == key
    section = instance._arena_section(read_state(bytes(0x800), bytes(0x300)), battle)
    assert section.inputs[0].enabled and section.inputs[0].value == 1000
    assert section.actions[0].key == "arena-predict"


def test_stale_arena_battle_flag_cannot_show_predictor_outside_arena() -> None:
    instance = adapter()
    memory = ArenaMemory()
    battle = instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor._status = PredictionStatus(running=True, completed=23)
    memory.ram[0x64] = 0
    outside = instance._with_arena(memory, bytes(memory.ram), replace(battle, active=True))
    assert not outside.arena and outside.arena_odds == ()
    assert outside.arena_selection is None and outside.arena_wager is None
    assert instance._arena_key is None and instance._arena_memory is None
    assert not instance._arena_predictor.status.running


@pytest.mark.parametrize("address", (0, 0x6000, 0x7000))
def test_partial_capture_is_rejected_before_worker_starts(address: int) -> None:
    instance = adapter()
    memory = ArenaMemory()
    instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor = Mock(status=PredictionStatus())
    original_read = memory.read_memory
    memory.read_memory = lambda start, size: original_read(start, size)[:-1] if start == address else original_read(start, size)
    instance.predict_arena()
    instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor.start.assert_not_called()
    instance._arena_predictor.fail.assert_called_once_with("The arena memory capture is incomplete")


@pytest.mark.parametrize("theme", ("light", "dark"))
@pytest.mark.parametrize("width", (360, 760))
def test_qt_button_dispatch_and_estimate_rendering(qtbot, tmp_path, width: int, theme: str) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QPushButton, QSpinBox
    from retroarch_overlay.models import OverlaySnapshot
    from retroarch_overlay.presentation.qt import PanelDocumentView

    instance = adapter()
    memory = ArenaMemory()
    instance._arena_predictor = Mock(status=PredictionStatus())
    battle = instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    state = read_state(bytes(0x800), bytes(0x300))
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    view = PanelDocumentView()
    view.setFont(QFont("Segoe UI", 10))
    view.set_theme(theme)
    qtbot.addWidget(view)
    view.resize(width, 760)
    view.show()
    view.set_snapshot(OverlaySnapshot("DW4", "Monster arena", (instance._arena_section(state, battle),)))
    view.set_active_role("urgent")
    buttons = [button for button in view.findChildren(QPushButton) if button.text() == "Estimate win chances"]
    assert len(buttons) == 1
    qtbot.waitUntil(buttons[0].isVisible)
    count = view.findChild(QSpinBox, "arena-simulations")
    assert count is not None and count.value() == 100
    count.setFocus()
    qtbot.waitUntil(count.hasFocus)
    count.lineEdit().selectAll()
    qtbot.keyClicks(count.lineEdit(), "1000")
    view.set_snapshot(OverlaySnapshot("DW4", "Monster arena", (instance._arena_section(state, battle),)))
    assert count.lineEdit().text() == "1000"
    qtbot.mouseClick(buttons[0], Qt.MouseButton.LeftButton)
    assert instance._arena_simulations == 1000
    instance._arena_predictor.start.assert_not_called()
    instance._with_arena(memory, bytes(memory.ram), BattleState.unavailable())
    instance._arena_predictor.start.assert_called_once_with(
        bytes(0x80000), bytes(memory.ram), bytes(memory.workspace), simulations=1000)
    instance._arena_predictor.status = PredictionStatus(
        completed=1000, simulations=1000, result=ArenaPrediction((0, 0, 1, 255), (200, 300, 400, 0), 100, 1000))
    view.set_snapshot(OverlaySnapshot("DW4", "Monster arena", (instance._arena_section(state, battle),)))
    section = view.state.section_views[0]
    assert any("40% win chance" in row.text for row in section.rows)
    image = view.grab().toImage()
    assert image.deviceIndependentSize().width() == pytest.approx(width) and image.height() > 0
    assert len({image.pixelColor(column, line).name() for column in range(0, image.width(), 10)
                for line in range(0, image.height(), 10)}) > 3
    screenshot = tmp_path / f"arena-{width}-{theme}.png"
    assert image.save(str(screenshot))
    print(f"Arena screenshot: {screenshot}")