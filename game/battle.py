from __future__ import annotations

from dataclasses import dataclass


BATTLE_MEMORY_ADDRESS = 0x7200
BATTLE_MEMORY_SIZE = 0xA0
ENEMY_RECORD_OFFSETS = (0x74, 0x82, 0x90)


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

    @property
    def label(self) -> str:
        if self.monster_id is None:
            return f"Enemy group {self.slot + 1}"
        return f"Monster ${self.monster_id:02X}"

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


def read_battle_state(ram: bytes, battle_memory: bytes) -> BattleState:
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