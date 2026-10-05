from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal, Protocol


DECK_SIZE = 53
JOKER = 52
DECK_ADDRESS = 0x7600
PokerPhase = Literal["wager", "hold", "double", "collect", "waiting"]
HAND_NAMES = (
    "Royal flush", "Five of a kind", "Straight flush", "Four of a kind",
    "Full house", "Flush", "Straight", "Three of a kind", "Two pair",
)
PAYOUT_MULTIPLIERS = (500, 100, 50, 20, 8, 5, 4, 2, 1)
STRAIGHTS = tuple(frozenset(range(start, start + 5)) for start in range(9)) + (
    frozenset((0, 9, 10, 11, 12)),
)


class PokerMemoryReader(Protocol):
    def read_memory(self, address: int, size: int) -> bytes: ...


@dataclass(frozen=True, slots=True)
class PokerHand:
    category: int | None

    @property
    def name(self) -> str:
        return HAND_NAMES[self.category] if self.category is not None else "No payout"

    @property
    def multiplier(self) -> int:
        return PAYOUT_MULTIPLIERS[self.category] if self.category is not None else 0


def classify_hand(cards: tuple[int, ...]) -> PokerHand:
    if (len(cards) != 5 or any(isinstance(card, bool) or not isinstance(card, int)
                               or not 0 <= card < DECK_SIZE for card in cards)
            or len(set(cards)) != 5):
        raise ValueError("A poker hand requires five distinct cards from the 53-card deck")
    ordinary = tuple(card for card in cards if card != JOKER)
    jokers = 5 - len(ordinary)
    ranks = Counter(card >> 2 for card in ordinary)
    flush = len({card & 3 for card in ordinary}) == 1
    straight = len(ranks) == len(ordinary) and any(ranks.keys() <= window for window in STRAIGHTS)
    counts = sorted(ranks.values(), reverse=True)
    if not jokers and flush and ranks.keys() == STRAIGHTS[-1]:
        category = 0
    elif counts[0] + jokers == 5:
        category = 1
    elif flush and straight:
        category = 2
    elif counts[0] + jokers == 4:
        category = 3
    elif counts == [3, 2] or jokers and counts == [2, 2]:
        category = 4
    elif flush:
        category = 5
    elif straight:
        category = 6
    elif counts[0] + jokers == 3:
        category = 7
    elif counts == [2, 2, 1]:
        category = 8
    else:
        category = None
    return PokerHand(category)


@dataclass(frozen=True, slots=True)
class HoldRecommendation:
    mask: int
    cards: tuple[int, ...]
    hand: PokerHand
    equivalent_masks: tuple[int, ...]

    @property
    def held_slots(self) -> tuple[int, ...]:
        return tuple(slot + 1 for slot in range(5) if self.mask & (1 << slot))


@dataclass(frozen=True, slots=True)
class DoubleAdvice:
    outcomes: tuple[Literal["Win", "Tie", "Lose"], ...]
    choice: int | None


def validate_deck(deck: bytes) -> None:
    if len(deck) != DECK_SIZE or set(deck) != set(range(DECK_SIZE)):
        raise ValueError("Waiting for a complete, stable 53-card poker deck")


def redraw_hand(deck: bytes, mask: int) -> tuple[int, ...]:
    validate_deck(deck)
    if isinstance(mask, bool) or not isinstance(mask, int) or not 0 <= mask < 32:
        raise ValueError("A hold mask must select zero through five card positions")
    cards = list(deck[:5])
    next_card = 5
    for slot in range(5):
        if not mask & (1 << slot):
            cards[slot] = deck[next_card]
            next_card += 1
    return tuple(cards)


def recommend_hold(deck: bytes, current_mask: int = 0) -> HoldRecommendation:
    outcomes = tuple((mask, redraw_hand(deck, mask)) for mask in range(32))
    scored = tuple((mask, cards, classify_hand(cards)) for mask, cards in outcomes)
    mask, cards, hand = max(scored, key=lambda option: (
        option[2].multiplier, -(option[0] ^ current_mask).bit_count(), option[0].bit_count(), -option[0],
    ))
    return HoldRecommendation(mask, cards, hand, tuple(
        candidate for candidate, _, result in scored if result.multiplier == hand.multiplier
    ))


def double_advice(deck: bytes) -> DoubleAdvice:
    validate_deck(deck)
    if deck[0] == JOKER:
        return DoubleAdvice(("Lose",) * 4, None)
    dealer = _double_rank(deck[0])
    outcomes: tuple[Literal["Win", "Tie", "Lose"], ...] = tuple(
        "Win" if _double_rank(card) > dealer else "Tie" if _double_rank(card) == dealer else "Lose"
        for card in deck[1:5]
    )
    for outcome in ("Win", "Tie"):
        if outcome in outcomes:
            return DoubleAdvice(outcomes, outcomes.index(outcome) + 1)
    return DoubleAdvice(outcomes, None)


def _double_rank(card: int) -> int:
    if card == JOKER:
        return 254
    rank = card >> 2
    return rank - 1 if rank else 12


@dataclass(frozen=True, slots=True)
class PokerTable:
    phase: PokerPhase
    deck: bytes = b""
    wager: int | None = 0
    held_mask: int = 0
    cursor: int = 0
    round: int = 0
    detail: str = ""
    double_schedule: tuple[int, int, int] | None = None


def next_double_guaranteed(table: PokerTable) -> bool | None:
    schedule = table.double_schedule
    if (table.phase not in ("double", "collect") or table.round < 1 or schedule is None
            or len(schedule) != 3 or any(not 0 <= index < 8 for index in schedule)):
        return None
    return (table.round & 7) not in schedule


def poker_open(ram: bytes) -> bool:
    return (len(ram) == 0x800 and ram[0x63:0x65] == bytes((4, 1))
            and bool(ram[0x1F] & 8) and ram[0x553] == 0x80 and ram[0x5FC] == 0x0A)


def _table_key(ram: bytes) -> bytes:
    return (bytes((ram[0x1F] & 8,)) + ram[0x2E:0x2F] + ram[0x63:0x65]
            + ram[0x82:0x86] + ram[0xF6:0xF7]
            + ram[0x553:0x554] + ram[0x595:0x596] + ram[0x5FC:0x5FD])


def _table_phase(ram: bytes, deck: bytes) -> PokerPhase:
    cursor = ram[0x200:0x208]
    valid_cursor = cursor[1:3] == bytes((1, 0)) and cursor[5:7] == bytes((2, 0))
    if valid_cursor and cursor[0] == cursor[4] and cursor[7] == cursor[3] + 8:
        suit_mask = 255 if deck[0] == JOKER else 1 << (deck[0] & 3)
        if (ram[0x2E] == suit_mask and cursor[0] in (0x90, 0xA0)
                and cursor[3] in (8, 56, 104, 152, 200)):
            return "hold"
        if ram[0x2E] == 0 and cursor[0] == 0x90 and cursor[3] in (56, 104, 152, 200):
            return "double"
        if cursor[0] == 0xA0 and cursor[3] in (0x50, 0x88) and ram[0xF6] == 0x3D:
            return "collect"
    if ram[0x2E] == 0 and ram[0x34] == 1 and ram[0x595] == 4:
        return "wager"
    return "waiting"


def _table_wager(ram: bytes, phase: PokerPhase) -> int | None:
    if phase in ("double", "collect") and ram[0x7E] and ram[0x7F] & 0x80:
        return None
    return int.from_bytes(ram[0x36:0x39], "little")


def read_poker_table(memory: PokerMemoryReader, ram: bytes) -> PokerTable | None:
    if not poker_open(ram):
        return None
    deck = memory.read_memory(DECK_ADDRESS, DECK_SIZE)
    confirmed = memory.read_memory(0, 0x800)
    if len(confirmed) != 0x800:
        raise ValueError("Waiting for a complete poker table read")
    if not poker_open(confirmed):
        return None
    if _table_key(ram) != _table_key(confirmed) or deck != memory.read_memory(DECK_ADDRESS, DECK_SIZE):
        raise ValueError("Waiting for the poker table to settle")
    validate_deck(deck)
    phase = _table_phase(confirmed, deck)
    if _table_phase(ram, deck) != phase:
        raise ValueError("Waiting for the poker table to settle")
    first_wager, wager = _table_wager(ram, phase), _table_wager(confirmed, phase)
    if first_wager is not None and wager is not None and first_wager != wager:
        raise ValueError("Waiting for the poker stake to settle")
    wager = wager if wager is not None else first_wager
    if phase in ("wager", "hold") and (wager is None or not 1 <= wager <= 100):
        phase = "waiting"
    elif phase in ("double", "collect") and wager is not None and not 1 <= wager < 100_000:
        phase = "waiting"
    schedule = (confirmed[0x83], confirmed[0x84], confirmed[0x85])
    initialized = phase in ("double", "collect") and confirmed[0x2E] == 0 and max(schedule) < 8
    return PokerTable(
        phase, deck, wager,
        sum((flag & 1) << slot for slot, flag in enumerate(confirmed[0x2F:0x34])),
        confirmed[0x29], confirmed[0x82] + 1,
        double_schedule=schedule if initialized else None,
    )


def card_label(card: int) -> str:
    if card == JOKER:
        return "Joker"
    ranks = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
    return f"{ranks[card >> 2]} / suit {(card & 3) + 1}"