from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from .reference_data import decode_text


BATTLE_MEMORY_ADDRESS = 0x7200
BATTLE_MEMORY_SIZE = 0xE4
BATTLE_CONTEXT_ADDRESS = 0x6BDE
BATTLE_TEXT_ADDRESS = 0x06AA
BATTLE_TEXT_SIZE = 0xC2
ENEMY_RECORD_OFFSETS = tuple(range(0x74, BATTLE_MEMORY_SIZE, 0x0E))
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
    max_hp: int | None = None
    max_mp: int | None = None
    infinite_mp: bool = False
    conditions: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        return f"Enemy slot {self.slot + 1}"

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
    arena: bool = False
    arena_wager: int | None = None
    arena_odds: tuple[tuple[int, int], ...] = ()
    arena_selection: int | None = None

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
    *,
    context_flags: int | None = None,
    monster_vitals: Callable[[int], tuple[int, int] | None] | None = None,
    setup_monster_ids: bytes = b"",
) -> BattleState:
    if len(ram) < 0x442:
        raise ValueError("DW4 system RAM is incomplete for battle decoding")
    if len(battle_memory) < BATTLE_MEMORY_SIZE:
        raise ValueError("DW4 battle memory snapshot is incomplete")
    if context_flags is not None and not context_flags & 0x80:
        return BattleState(True, False, 0, 0, (), "Native field engine context")
    monster_groups = battle_memory[0x06:0x0A]
    if len(setup_monster_ids) == 4:
        for group, profile in enumerate(monster_groups):
            if profile == 0xFF:
                continue
            phase_profile = group == 0 and setup_monster_ids[0] == 0xAE and 0xCD <= profile <= 0xD2
            if profile != setup_monster_ids[group] and not phase_profile:
                return BattleState(True, False, 0, 0, (), "Native setup/group identity inconsistent; shared scene workspace")
    enemies = []
    for slot, offset in enumerate(ENEMY_RECORD_OFFSETS):
        group_code = battle_memory[offset + 0x0D]
        raw_monster_id = monster_groups[group_code & 0x03]
        monster_id = None if raw_monster_id == 0xFF else raw_monster_id
        name_id = monster_id
        if monster_id is not None and 0xCD <= monster_id <= 0xD2 and len(setup_monster_ids) == 4 and setup_monster_ids[0] == 0xAE and group_code & 3 == 0:
            name_id = 0xAE
        vitals = (
            monster_vitals(monster_id)
            if monster_vitals is not None and monster_id is not None
            else None
        )
        enemies.append(
            BattleEnemyState(
            slot,
            monster_id,
            group_code,
            int.from_bytes(battle_memory[offset + 0x0A:offset + 0x0C], "little"),
            battle_memory[offset + 0x0C],
            battle_memory[offset],
            int.from_bytes(battle_memory[offset + 1:offset + 3], "little"),
            int.from_bytes(battle_memory[offset + 3:offset + 5], "little"),
            battle_memory[offset + 6],
            (
                monster_name(name_id)
                if monster_name is not None and monster_id is not None
                else None
            ),
            vitals[0] if vitals is not None else None,
            vitals[1] if vitals is not None else None,
            battle_memory[offset + 0x0C] == 0xFF,
            tuple(label for label, enabled in (
                ("Sleeping", battle_memory[offset + 5] & 0x01),
                ("Confused", battle_memory[offset + 5] & 0x04),
                ("Silenced", battle_memory[offset + 5] & 0x08),
                ("Paralyzed", battle_memory[offset + 6] & 0x20),
            ) if enabled),
            )
        )
    enemy_states = tuple(enemies)
    active = any(enemy.coherent for enemy in enemy_states)
    if context_flags is not None:
        active = active and bool(context_flags & 0x80)
        if not context_flags & 0x80:
            enemy_states = ()
    return BattleState(
        True,
        active,
        int.from_bytes(battle_memory[1:3], "little"),
        int.from_bytes(battle_memory[3:6], "little"),
        enemy_states,
        (
            "Native engine context plus coherent live combatant records"
            if context_flags is not None
            else "Coherent live combatant records; engine context not supplied"
        ),
    )