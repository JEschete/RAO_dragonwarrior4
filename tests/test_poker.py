import os
from pathlib import Path
from random import Random

import pytest

from game.poker import (
    PAYOUT_MULTIPLIERS, PokerTable, classify_hand, double_advice, poker_open,
    next_double_guaranteed, read_poker_table, recommend_hold, redraw_hand, validate_deck,
)


HAND_CASES = (
    ((0, 36, 40, 44, 48), 0),
    ((4, 5, 6, 7, 52), 1),
    ((4, 8, 12, 16, 20), 2),
    ((4, 5, 6, 7, 12), 3),
    ((4, 5, 6, 12, 13), 4),
    ((4, 16, 24, 32, 44), 5),
    ((4, 9, 14, 19, 20), 6),
    ((4, 5, 6, 12, 20), 7),
    ((4, 5, 12, 13, 20), 8),
    ((4, 5, 12, 20, 28), None),
    ((0, 36, 40, 44, 52), 2),
    ((36, 40, 44, 48, 52), 2),
    ((0, 4, 12, 17, 52), 6),
    ((4, 5, 12, 13, 52), 4),
    ((4, 5, 6, 12, 52), 3),
    ((4, 5, 12, 20, 52), 7),
    ((0, 37, 42, 47, 48), 6),
    ((0, 5, 10, 15, 16), 6),
)


@pytest.mark.parametrize("cards,category", HAND_CASES)
def test_hand_categories_and_native_payouts(cards, category) -> None:
    hand = classify_hand(cards)
    assert hand.category == category
    assert hand.multiplier == (PAYOUT_MULTIPLIERS[category] if category is not None else 0)
    assert hand.name


@pytest.mark.parametrize("cards", ((0, 1, 2, 3), (0, 1, 2, 3, 53), (0, 0, 2, 3, 4), (False, 1, 2, 3, 4)))
def test_invalid_hands_are_rejected(cards) -> None:
    with pytest.raises(ValueError, match="five distinct cards"):
        classify_hand(cards)


@pytest.fixture(scope="module")
def poker_prg() -> bytes:
    pytest.importorskip("py65.devices.mpu6502")
    from game.rom_reader import RomReader

    configured = os.environ.get("RAO_DW4_TEST_ROM")
    path = Path(configured) if configured else Path(__file__).parents[1] / "resources/DW4_Disassembly/build/arena/Dragon Warrior IV (USA).nes"
    if not path.is_file():
        if configured:
            pytest.fail("RAO_DW4_TEST_ROM does not identify an available ROM")
        pytest.skip("Set RAO_DW4_TEST_ROM to run the original poker classifier")
    reader = RomReader()
    reader._load_cartridge(path)
    return reader._data[reader._prg_offset:reader._prg_offset + 0x80000]


def native_category(prg: bytes, cards: tuple[int, ...]) -> int | None:
    from py65.devices.mpu6502 import MPU

    memory = [0] * 0x10000
    memory[0x8000:0xC000] = prg[0x5C000:0x60000]
    memory[0xC000:] = prg[0x7C000:0x80000]
    memory[0x7600:0x7605] = cards
    cpu = MPU(memory=memory, pc=0x81F2)
    cpu.stPushWord(0x5FFF)
    for _ in range(5000):
        if cpu.pc == 0x6000:
            return memory[0x81] if cpu.p & 1 else None
        cpu.step()
    pytest.fail("Original poker classifier exceeded its instruction budget")


def test_classifier_and_payout_table_match_original_rom(poker_prg: bytes) -> None:
    table = poker_prg[0x5C1C5:0x5C1D7]
    assert tuple(int.from_bytes(table[offset:offset + 2], "little")
                 for offset in range(0, len(table), 2)) == PAYOUT_MULTIPLIERS
    random = Random(0x17)
    hands = [cards for cards, _ in HAND_CASES]
    hands.extend(tuple(random.sample(range(53), 5)) for _ in range(256))
    hands.extend((*random.sample(range(52), 4), 52) for _ in range(256))
    for cards in hands:
        assert classify_hand(cards).category == native_category(poker_prg, cards), cards


def deck_with(cards: tuple[int, ...]) -> bytes:
    return bytes((*cards, *(card for card in range(53) if card not in cards)))


def test_recommendation_checks_every_mask_and_preserves_equal_best_current_holds() -> None:
    deck = deck_with((0, 36, 40, 44, 48))
    result = recommend_hold(deck)
    assert result.mask == 31 and result.held_slots == (1, 2, 3, 4, 5)
    assert result.cards == tuple(deck[:5]) and result.hand.multiplier == 500
    random = Random(17)
    for _ in range(64):
        deck = bytes(random.sample(range(53), 53))
        result = recommend_hold(deck)
        expected = max(classify_hand(redraw_hand(deck, mask)).multiplier for mask in range(32))
        assert result.hand.multiplier == expected
        for mask in result.equivalent_masks:
            assert recommend_hold(deck, mask).mask == mask


def test_redraw_replacements_follow_discarded_positions_not_original_positions() -> None:
    deck = bytes(range(53))
    assert redraw_hand(deck, 0b10101) == (0, 5, 2, 6, 4)
    assert redraw_hand(deck, 0) == (5, 6, 7, 8, 9)
    assert redraw_hand(deck, 31) == (0, 1, 2, 3, 4)


@pytest.mark.parametrize("deck", (b"", bytes(range(52)), bytes(range(52)) + b"\x00", bytes(range(54))))
def test_partial_or_mid_shuffle_decks_are_rejected(deck: bytes) -> None:
    with pytest.raises(ValueError, match="stable 53-card"):
        validate_deck(deck)


@pytest.mark.parametrize("cards,outcomes,choice", (
    ((44, 48, 0, 52, 40), ("Win", "Win", "Win", "Lose"), 1),
    ((0, 48, 1, 52, 40), ("Lose", "Tie", "Win", "Lose"), 3),
    ((0, 48, 1, 2, 40), ("Lose", "Tie", "Tie", "Lose"), 2),
    ((0, 48, 44, 40, 36), ("Lose", "Lose", "Lose", "Lose"), None),
    ((52, 0, 1, 2, 3), ("Lose", "Lose", "Lose", "Lose"), None),
))
def test_double_advice_handles_aces_jokers_ties_and_unavoidable_losses(cards, outcomes, choice) -> None:
    advice = double_advice(deck_with(cards))
    assert advice.outcomes == outcomes and advice.choice == choice


def test_every_redraw_mask_matches_original_card_swap_loop(poker_prg: bytes) -> None:
    from py65.devices.mpu6502 import MPU

    random = Random(0x8EEE)
    for _ in range(8):
        deck = bytes(random.sample(range(53), 53))
        for mask in range(32):
            memory = [0] * 0x10000
            memory[0x8000:0xC000] = poker_prg[0x5C000:0x60000]
            memory[0x7600:0x7635] = deck
            memory[0x2F:0x34] = [int(bool(mask & (1 << slot))) for slot in range(5)]
            cpu = MPU(memory=memory, pc=0x8EEE)
            for _ in range(256):
                if cpu.pc == 0x8F0C:
                    break
                cpu.step()
            assert cpu.pc == 0x8F0C
            assert tuple(memory[0x7600:0x7605]) == redraw_hand(deck, mask)


def test_double_outcomes_match_original_comparison_instructions(poker_prg: bytes) -> None:
    from py65.devices.mpu6502 import MPU

    for dealer in range(52):
        for candidate in range(53):
            if dealer == candidate:
                continue
            memory = [0] * 0x10000
            memory[0x8000:0xC000] = poker_prg[0x5C000:0x60000]
            cards = (dealer, candidate, *(card for card in range(53) if card not in (dealer, candidate)))
            deck = bytes(cards)
            memory[0x7600:0x7635] = deck
            memory[0x2F] = 1
            cpu = MPU(memory=memory, pc=0x87FD)
            for _ in range(128):
                if cpu.pc in (0x8827, 0x8838, 0x8861):
                    break
                cpu.step()
            expected = {0x8827: "Lose", 0x8838: "Tie", 0x8861: "Win"}
            assert cpu.pc in expected
            assert double_advice(deck).outcomes[0] == expected[cpu.pc]


class PokerMemory:
    def __init__(self) -> None:
        self.ram = bytearray(0x800)
        self.ram[0x1F] = 8
        self.ram[0x63:0x65] = bytes((4, 1))
        self.ram[0x553] = 0x80
        self.ram[0x5FC] = 10
        self.ram[0xF6] = 0x3D
        self.ram[0x595] = 4
        self.ram[0x2E] = 1
        self.ram[0x36] = 10
        self.ram[0x200:0x208] = bytes((0x90, 1, 0, 8, 0x90, 2, 0, 16))
        self.deck = deck_with((0, 36, 40, 44, 48))
        self.requests: list[tuple[int, int]] = []

    def read_memory(self, address: int, size: int) -> bytes:
        self.requests.append((address, size))
        assert size <= 4096
        if address == 0:
            return bytes(self.ram[:size])
        assert address == 0x7600
        return self.deck[:size]


def test_live_reader_captures_whole_deck_and_hold_flags_without_writes() -> None:
    memory = PokerMemory()
    memory.ram[0x2F:0x34] = bytes((3, 0, 2, 1, 255))
    table = read_poker_table(memory, bytes(memory.ram))
    assert table.phase == "hold" and table.wager == 10
    assert table.deck == memory.deck and table.held_mask == 0b11001
    assert memory.requests == [(0x7600, 53), (0, 0x800), (0x7600, 53)]


@pytest.mark.parametrize("address,value", ((0x1F, 0), (0x64, 6), (0x553, 0), (0x5FC, 0)))
def test_stale_poker_data_outside_the_table_never_triggers_reads(address: int, value: int) -> None:
    memory = PokerMemory()
    memory.ram[address] = value
    assert not poker_open(bytes(memory.ram))
    assert read_poker_table(memory, bytes(memory.ram)) is None
    assert memory.requests == []


@pytest.mark.parametrize("workspace,y,x,phase", (
    (1, 0x90, 8, "hold"), (1, 0xA0, 104, "hold"),
    (0, 0x90, 56, "double"), (0, 0xA0, 0x50, "collect"),
    (1, 0xA0, 0x88, "collect"), (0, 0xF7, 56, "waiting"),
    (0, 0x90, 8, "waiting"), (2, 0x90, 56, "waiting"),
))
def test_poker_phase_requires_native_workspace_and_cursor(workspace: int, y: int, x: int, phase: str) -> None:
    memory = PokerMemory()
    memory.ram[0x2E] = workspace
    memory.ram[0x200:0x208] = bytes((y, 1, 0, x, y, 2, 0, x + 8))
    assert read_poker_table(memory, bytes(memory.ram)).phase == phase


def test_wager_phase_uses_native_input_setup_not_inline_message_number() -> None:
    memory = PokerMemory()
    memory.ram[0x2E] = 0
    memory.ram[0x34] = 1
    memory.ram[0x200] = memory.ram[0x204] = 0xF7
    assert read_poker_table(memory, bytes(memory.ram)).phase == "wager"


def test_live_king_ace_jack_six_two_table_tracks_held_count_and_exact_draw() -> None:
    from game.adapter import Adapter
    from retroarch_overlay.core.contracts import GameContext

    memory = PokerMemory()
    memory.deck = deck_with((50, 3, 41, 20, 7, 44, 5, 18, 6, 51))
    memory.ram[0x2E] = 4
    memory.ram[0x36] = 100
    instance = Adapter(GameContext())
    table = read_poker_table(memory, bytes(memory.ram))
    assert table.phase == "hold"
    section = instance._poker_section(table, 1951)
    assert section.rows[1].text == "Hold 5 · Replace 1, 2, 3, 4"
    assert "Three of a kind" in section.rows[2].text and "200 coins" in section.rows[2].text
    assert "0 held · 5 to draw" in section.rows[3].text
    memory.ram[0x33] = 1
    table = read_poker_table(memory, bytes(memory.ram))
    section = instance._poker_section(table, 1951)
    assert section.rows[1].text == "Draw"
    assert "1 held · 4 to draw · Three of a kind · 200 coins" in section.rows[3].text


def test_capture_uses_latest_holds_and_rejects_changing_deck() -> None:
    memory = PokerMemory()
    captured = bytes(memory.ram)
    memory.ram[0x2F] = 1
    table = read_poker_table(memory, captured)
    assert table.phase == "hold" and table.held_mask == 1
    memory = PokerMemory()
    original = memory.read_memory

    def changing(address: int, size: int) -> bytes:
        result = original(address, size)
        if address == 0:
            memory.deck = bytes(reversed(memory.deck))
        return result

    memory.read_memory = changing
    with pytest.raises(ValueError, match="settle"):
        read_poker_table(memory, bytes(memory.ram))


@pytest.mark.parametrize("double", (False, True))
def test_cursor_movement_does_not_suppress_card_advice(double: bool) -> None:
    memory = PokerMemory()
    memory.ram[0x2E] = 0 if double else 1
    memory.ram[0x200:0x208] = bytes((0x90, 1, 0, 56, 0x90, 2, 0, 64))
    captured = bytes(memory.ram)
    memory.ram[0x29] = 2
    memory.ram[0x203] = 104
    memory.ram[0x207] = 112
    memory.ram[0x34] = 0x80
    table = read_poker_table(memory, captured)
    assert table.phase == ("double" if double else "hold") and table.cursor == 2


def test_confirming_a_card_still_rejects_capture_during_phase_transition() -> None:
    memory = PokerMemory()
    captured = bytes(memory.ram)
    memory.ram[0x200] = memory.ram[0x204] = 0xF7
    with pytest.raises(ValueError, match="settle"):
        read_poker_table(memory, captured)


def test_native_frame_update_flags_do_not_reject_double_or_nothing_capture() -> None:
    from game.adapter import Adapter
    from retroarch_overlay.core.contracts import GameContext

    memory = PokerMemory()
    memory.deck = deck_with((5, 22, 23, 4, 39, 1, 25, 8, 24, 7))
    memory.ram[0x2E] = 0
    memory.ram[0x36:0x39] = (200).to_bytes(3, "little")
    memory.ram[0x200:0x208] = bytes((0x90, 1, 0, 56, 0x90, 2, 0, 64))
    captured = bytes(memory.ram)
    memory.ram[0x1F] |= 4
    table = read_poker_table(memory, captured)
    assert table.phase == "double" and table.wager == 200
    section = Adapter(GameContext())._poker_section(table, 1951)
    assert section.rows[1].text == "Choose card 1 · Win 400 coins"
    assert [row.chips[0].text for row in section.columns[0].rows] == ["Win", "Win", "Tie", "Win"]


@pytest.mark.parametrize("first_blink,second_blink", ((False, True), (True, False), (True, True)))
def test_double_card_advice_survives_native_payout_blink_without_using_temporary_stake(first_blink, second_blink) -> None:
    from game.adapter import Adapter
    from retroarch_overlay.core.contracts import GameContext

    memory = PokerMemory()
    memory.deck = deck_with((5, 22, 23, 4, 39, 1, 25, 8, 24, 7))
    memory.ram[0x2E] = 0
    memory.ram[0x7E] = 1
    memory.ram[0x7F] = 128 if first_blink else 0
    memory.ram[0x36] = 100 if first_blink else 200
    memory.ram[0x200:0x208] = bytes((0x90, 1, 0, 56, 0x90, 2, 0, 64))
    captured = bytes(memory.ram)
    memory.ram[0x7F] = 128 if second_blink else 0
    memory.ram[0x36] = 100 if second_blink else 200
    table = read_poker_table(memory, captured)
    assert table.phase == "double"
    assert table.wager == (None if first_blink and second_blink else 200)
    section = Adapter(GameContext())._poker_section(table, 1951)
    assert section.rows[1].text == ("Choose card 1 · Win" if table.wager is None else "Choose card 1 · Win 400 coins")


def test_real_stake_change_still_rejects_capture() -> None:
    memory = PokerMemory()
    captured = bytes(memory.ram)
    memory.ram[0x36] = 20
    with pytest.raises(ValueError, match="stake to settle"):
        read_poker_table(memory, captured)


@pytest.mark.parametrize("current_round,schedule,safe", (
    (1, (2, 3, 4), True), (2, (2, 3, 4), False), (3, (2, 3, 4), False),
    (4, (2, 3, 4), False), (5, (2, 3, 4), True),
    (7, (1, 2, 0), True), (8, (1, 2, 0), False), (9, (1, 2, 0), False),
    (8, (1, 2, 3), True), (1, (1, 1, 1), False), (2, (1, 1, 1), True),
    (1, None, None), (0, (2, 3, 4), None), (1, (8, 2, 3), None),
))
def test_safe_stop_uses_next_round_index_and_fails_closed(current_round, schedule, safe) -> None:
    table = PokerTable("collect", round=current_round, double_schedule=schedule)
    assert next_double_guaranteed(table) is safe


@pytest.mark.parametrize("initialized", (False, True))
def test_reader_distinguishes_first_offer_from_initialized_double_schedule(initialized: bool) -> None:
    memory = PokerMemory()
    memory.ram[0x200:0x208] = bytes((0xA0, 1, 0, 80, 0xA0, 2, 0, 88))
    memory.ram[0x2E] = 0 if initialized else 1
    memory.ram[0x82:0x86] = bytes((0, 2, 3, 4))
    table = read_poker_table(memory, bytes(memory.ram))
    assert table.phase == "collect" and table.round == 1
    assert table.double_schedule == ((2, 3, 4) if initialized else None)
    assert next_double_guaranteed(table) is (True if initialized else None)


def test_changing_special_round_schedule_rejects_capture() -> None:
    memory = PokerMemory()
    captured = bytes(memory.ram)
    memory.ram[0x83] = 2
    with pytest.raises(ValueError, match="settle"):
        read_poker_table(memory, captured)


@pytest.mark.parametrize("schedule,action,reason", (
    ((2, 3, 4), "Continue double-or-nothing", "Next round has a guaranteed winning choice"),
    ((1, 3, 4), "Collect 200 coins", "Next round is not guaranteed · Stop here"),
    (None, "Collect 200 coins", "Next round is not dealt yet · Safety unknown"),
))
def test_collection_prompt_shows_actionable_safe_stop_advice(schedule, action, reason) -> None:
    from game.adapter import Adapter
    from retroarch_overlay.core.contracts import GameContext

    table = PokerTable("collect", bytes(range(53)), 200, round=1, double_schedule=schedule)
    section = Adapter(GameContext())._poker_section(table, 780551)
    assert section.rows[0].text == "Coins 780,551 · At stake 200"
    assert section.rows[1].text == action and section.rows[2].text == reason


def test_card_choice_also_shows_when_to_stop_after_winning() -> None:
    from game.adapter import Adapter
    from retroarch_overlay.core.contracts import GameContext

    deck = deck_with((5, 22, 23, 4, 39))
    instance = Adapter(GameContext())
    table = PokerTable("double", deck, 200, round=1, double_schedule=(2, 3, 4))
    section = instance._poker_section(table, 780551)
    assert section.rows[1].text == "Choose card 1 · Win 400 coins"
    assert section.rows[3].text == "After winning: continue"
    table = PokerTable("double", deck, 200, round=1, double_schedule=(1, 3, 4))
    assert instance._poker_section(table, 780551).rows[3].text == "After winning: collect"


def native_arranged_deck(prg: bytes, deck: bytes, round_index: int, schedule: tuple[int, int, int], seed: int) -> bytes:
    from py65.devices.mpu6502 import MPU

    memory = [0] * 0x10000
    memory[0x8000:0xC000] = prg[0x5C000:0x60000]
    memory[0xC000:] = prg[0x7C000:0x80000]
    memory[0x7600:0x7635] = deck
    memory[0x82:0x86] = [round_index, *schedule]
    memory[0x12:0x14] = [seed & 255, seed >> 8]
    cpu = MPU(memory=memory, pc=0x86BC)
    cpu.stPushWord(0x5FFF)
    for _ in range(5000):
        if cpu.pc == 0x6000:
            return bytes(memory[0x7600:0x7635])
        cpu.step()
    pytest.fail("Original poker round arrangement exceeded its instruction budget")


def test_safe_rounds_guarantee_winning_choice_in_original_rom_for_every_cycle_position(poker_prg: bytes) -> None:
    random = Random(0x86BC)
    for schedule in ((1, 2, 3), (0, 0, 0), (7, 7, 7), (0, 3, 7)):
        for round_index in range(8):
            table = PokerTable("collect", round=round_index or 8, double_schedule=schedule)
            for _ in range(16):
                deck = bytes(random.sample(range(53), 53))
                arranged = native_arranged_deck(poker_prg, deck, round_index, schedule, random.randrange(65536))
                assert set(arranged) == set(deck)
                if next_double_guaranteed(table):
                    advice = double_advice(arranged)
                    assert advice.choice is not None and advice.outcomes[advice.choice - 1] == "Win"


@pytest.mark.parametrize("schedule,cards", (
    ((1, 2, 3), (0, 36, 40, 44, 48)),
    ((5, 6, 1), (12, 4, 5, 8, 9)),
    ((1, 1, 1), (52, 36, 40, 44, 48)),
))
def test_original_special_rounds_can_be_unwinnable_and_are_never_marked_safe(poker_prg: bytes, schedule, cards) -> None:
    table = PokerTable("collect", round=1, double_schedule=schedule)
    assert next_double_guaranteed(table) is False
    for seed in range(16):
        arranged = native_arranged_deck(poker_prg, deck_with(cards), 1, schedule, seed)
        assert double_advice(arranged).choice is None


def test_presentation_exposes_exact_holds_all_hidden_choices_and_full_deck() -> None:
    from game.adapter import Adapter
    from retroarch_overlay.core.contracts import GameContext

    instance = Adapter(GameContext())
    section = instance._poker_section(PokerTable("hold", deck_with((0, 36, 40, 44, 48)), 10), 1000)
    assert section.key == "poker" and section.role == "urgent"
    assert section.rows[1].text == "Hold 1, 2, 3, 4, 5 · Replace none"
    assert "5,000 coins" in section.rows[2].text
    assert len(section.columns[0].rows) == 5 and len(section.actions[0].rows) == 53
    assert section.actions[0].command is None
    section = instance._poker_section(PokerTable("double", deck_with((0, 48, 1, 52, 40)), 100), 1000)
    assert section.rows[1].text == "Choose card 3 · Win 200 coins"
    assert [row.chips[0].text for row in section.columns[0].rows] == ["Lose", "Tie", "Win", "Lose"]
    section = instance._poker_section(PokerTable("collect", bytes(range(53)), 200), 1000)
    assert section.rows[1].text == "Collect 200 coins"
    assert "not dealt yet" in section.rows[2].text


@pytest.mark.parametrize("width", (360, 760))
@pytest.mark.parametrize("theme", ("light", "dark"))
@pytest.mark.parametrize("phase", ("hold", "double", "collect", "collect-safe", "collect-stop"))
def test_poker_panel_renders_cards_and_advice_at_narrow_and_wide_sizes(qtbot, tmp_path, width: int, theme: str, phase: str) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QPushButton
    from game.adapter import Adapter
    from retroarch_overlay.core.contracts import GameContext
    from retroarch_overlay.models import OverlaySnapshot
    from retroarch_overlay.presentation.qt import PanelDocumentView

    deck = deck_with((50, 3, 41, 20, 7, 44, 5, 18, 6, 51)) if phase == "hold" else deck_with((0, 48, 1, 52, 40))
    schedule = (2, 3, 4) if phase == "collect-safe" else (1, 3, 4) if phase == "collect-stop" else None
    table = PokerTable("collect" if phase.startswith("collect") else phase, deck,
                       100 if phase == "hold" else 6400, round=1, double_schedule=schedule)
    section = Adapter(GameContext())._poker_section(table, 1951)
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    view = PanelDocumentView()
    view.setFont(QFont("Segoe UI", 10))
    view.set_theme(theme)
    qtbot.addWidget(view)
    view.resize(width, 760)
    view.show()
    view.set_snapshot(OverlaySnapshot("DW4", "Poker", (section,)))
    view.set_active_role("urgent")
    buttons = [button for button in view.findChildren(QPushButton) if button.accessibleName().startswith("Deck order;")]
    assert len(buttons) == 1
    qtbot.waitUntil(buttons[0].isVisible)
    assert any(row.text.startswith(("Hold 5", "Choose card 3", "Collect 6,400", "Continue double-or-nothing"))
               for row in view.state.section_views[0].rows)
    image = view.grab().toImage()
    assert image.deviceIndependentSize().width() == pytest.approx(width)
    assert len({image.pixelColor(column, line).name() for column in range(0, image.width(), 10)
                for line in range(0, image.height(), 10)}) > 3
    screenshot = tmp_path / f"poker-{phase}-{width}-{theme}.png"
    assert image.save(str(screenshot))
    print(f"Poker screenshot: {screenshot}")
    qtbot.mouseClick(buttons[0], Qt.MouseButton.LeftButton)
    assert len(view.state.section_views[0].actions[0].rows) == 53