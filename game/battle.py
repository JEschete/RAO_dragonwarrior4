from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from .reference_data import decode_text


BATTLE_MEMORY_ADDRESS = 0x7200
BATTLE_MEMORY_SIZE = 0xA0
BATTLE_TEXT_ADDRESS = 0x06AA
BATTLE_TEXT_SIZE = 0xC2
ENEMY_RECORD_OFFSETS = (0x74, 0x82, 0x90)
_APPEARANCE_PATTERN = re.compile(r"([A-Z][A-Za-z' -]*?) appears[.!]")


@dataclass(frozen=True, slots=True)
class BattleEnemyState:
    slot: int
    monster_id: int | None
    group_code: int
    hp: int
    mp: int
    agility: int
    attack: int
    defense: int
    status: int
    name: str | None = None

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        return f"Enemy group {self.slot + 1}"

    @property
    def coherent(self) -> bool:
        return self.hp > 0 and any((self.agility, self.attack, self.defense))


@dataclass(frozen=True, slots=True)
class BattleState:
    available: bool
    active: bool
    reward_gold: int
    reward_experience: int
    enemies: tuple[BattleEnemyState, ...]
    detector_evidence: str

    @classmethod
    def unavailable(cls, reason: str = "Battle memory unavailable") -> BattleState:
        return cls(False, False, 0, 0, (), reason)


def observed_monster_names(ram: bytes) -> dict[int, str]:
    if len(ram) < BATTLE_TEXT_ADDRESS + BATTLE_TEXT_SIZE:
        return {}
    monster_ids = tuple(value for value in ram[0x440:0x442] if value != 0xFF)
    text_end = BATTLE_TEXT_ADDRESS + BATTLE_TEXT_SIZE
    battle_text = decode_text(ram[BATTLE_TEXT_ADDRESS:text_end])
    names = tuple(
        " ".join(match.group(1).split())
        for match in _APPEARANCE_PATTERN.finditer(battle_text)
    )
    if (
        not monster_ids
        or len(names) != len(monster_ids)
        or _APPEARANCE_PATTERN.sub("", battle_text).strip()
    ):
        return {}
    observed: dict[int, str] = {}
    for monster_id, name in zip(monster_ids, names, strict=True):
        if monster_id in observed and observed[monster_id] != name:
            return {}
        observed[monster_id] = name
    return observed


def read_battle_state(
    ram: bytes,
    battle_memory: bytes,
    monster_name: Callable[[int], str | None] | None = None,
) -> BattleState:
    if len(ram) < 0x442:
        raise ValueError("DW4 system RAM is incomplete for battle decoding")
    if len(battle_memory) < BATTLE_MEMORY_SIZE:
        raise ValueError("DW4 battle memory snapshot is incomplete")
    monster_ids: tuple[int | None, ...] = (
        None if ram[0x440] == 0xFF else ram[0x440],
        None if ram[0x441] == 0xFF else ram[0x441],
        None,
    )
    enemies = tuple(
        BattleEnemyState(
            slot,
            monster_ids[slot],
            battle_memory[offset + 0x0D],
            int.from_bytes(battle_memory[offset + 0x0A:offset + 0x0C], "little"),
            battle_memory[offset + 0x0C],
            battle_memory[offset],
            battle_memory[offset + 1],
            battle_memory[offset + 3],
            battle_memory[offset + 6],
            (
                monster_name(monster_ids[slot])
                if monster_name is not None and monster_ids[slot] is not None
                else None
            ),
        )
        for slot, offset in enumerate(ENEMY_RECORD_OFFSETS)
    )
    active = any(enemy.coherent for enemy in enemies)
    return BattleState(
        True,
        active,
        int.from_bytes(battle_memory[1:3], "little"),
        int.from_bytes(battle_memory[3:6], "little"),
        enemies,
        (
            "Conservative detector: at least one documented enemy slot has "
            "positive HP and nonzero combat stats"
        ),
    )