from __future__ import annotations

from dataclasses import dataclass


ENTITY_MEMORY_ADDRESS = 0x6F60
ENTITY_MEMORY_SIZE = 0x1A0
ENTITY_FIRST_SLOT = 0x06
ENTITY_LAST_SLOT = 0x1F


@dataclass(frozen=True, slots=True)
class MapEntityState:
    slot: int
    x: int
    y: int
    facing: int
    descriptor: int
    behavior_state: int
    runtime_flags: int


def read_map_entities(memory: bytes) -> tuple[MapEntityState, ...]:
    if len(memory) < ENTITY_MEMORY_SIZE:
        raise ValueError("DW4 map entity memory snapshot is incomplete")
    entities = []
    for slot in range(ENTITY_FIRST_SLOT, ENTITY_LAST_SLOT + 1):
        descriptor = memory[0xC0 + slot]
        if descriptor == 0xFF:
            continue
        x = memory[slot]
        y = memory[0x20 + slot]
        if x == 0xFF or y == 0xFF:
            continue
        entities.append(
            MapEntityState(
                slot,
                x,
                y,
                memory[0x80 + slot],
                descriptor,
                memory[0xE0 + slot],
                memory[0x180 + slot],
            )
        )
    return tuple(entities)