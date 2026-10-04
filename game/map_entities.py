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
    graphics_slot: int = 0
    script_pointer: int = 0
    room_class: int | None = None

    @property
    def visible(self) -> bool:
        return not self.descriptor & 0x90


def read_world_vehicles(memory: bytes, world_selector: int, has_boat: bool,
                        has_balloon: bool) -> tuple[tuple[str, int, int], ...]:
    if len(memory) < ENTITY_MEMORY_SIZE:
        raise ValueError("DW4 world vehicle memory snapshot is incomplete")
    if world_selector not in {0, 1, 3} or not any(memory):
        return ()
    width, height = (256, 256) if world_selector == 0 else (64, 64) if world_selector == 1 else (64, 54)
    vehicles = []
    for title, slot, acquired, worlds in (("Boat", 6, has_boat, {0, 3}),
                                           ("Balloon", 7, has_balloon, {0, 1})):
        if not acquired or world_selector not in worlds or memory[0xC0 + slot] & 0x90:
            continue
        if memory[0x80 + slot] != slot:
            continue
        x, y = memory[slot], memory[0x20 + slot]
        if 0 <= x < width and 0 <= y < height:
            vehicles.append((title, x, y))
    return tuple(vehicles)


def read_map_entities(memory: bytes, room_classes: bytes = b"") -> tuple[MapEntityState, ...]:
    if len(memory) < ENTITY_MEMORY_SIZE:
        raise ValueError("DW4 map entity memory snapshot is incomplete")
    if not any(memory):
        return ()
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
                memory[0xA0 + slot] & 3,
                descriptor,
                memory[0xE0 + slot],
                memory[0x180 + slot],
                memory[0x80 + slot],
                memory[0x120 + slot] | (memory[0x100 + slot] << 8),
                room_classes[slot] & 0xE0 if slot < len(room_classes) else None,
            )
        )
    return tuple(entities)