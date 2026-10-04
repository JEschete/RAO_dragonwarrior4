import pytest

from game.map_entities import ENTITY_MEMORY_SIZE, read_map_entities, read_world_vehicles


def test_reads_visible_entities_after_inactive_slot_holes() -> None:
    memory = bytearray(ENTITY_MEMORY_SIZE)
    memory[0xC0 + 6:0xC0 + 32] = bytes((0xFF,)) * 26
    memory[0xC0 + 6] = 0x12
    memory[0xC0 + 8] = 0x83
    memory[6] = 11
    memory[8] = 22
    memory[0x20 + 6] = 7
    memory[0x20 + 8] = 9
    memory[0x80 + 6] = 9
    memory[0xA0 + 6] = 2
    memory[0xE0 + 6] = 0x11
    memory[0x180 + 6] = 0x40

    entities = read_map_entities(bytes(memory))

    assert len(entities) == 2
    assert (
        entities[0].slot,
        entities[0].x,
        entities[0].y,
        entities[0].facing,
        entities[0].descriptor,
        entities[0].behavior_state,
        entities[0].runtime_flags,
    ) == (6, 11, 7, 2, 0x12, 0x11, 0x40)
    assert entities[0].graphics_slot == 9
    assert (entities[1].slot, entities[1].x, entities[1].y, entities[1].descriptor) == (
        8,
        22,
        9,
        0x83,
    )


def test_native_visibility_and_room_class_do_not_use_graphics_or_runtime_flags() -> None:
    memory = bytearray(ENTITY_MEMORY_SIZE)
    memory[6] = 4
    memory[0xC6] = 2
    memory[0x86] = 0x90
    memory[0x186] = 0x90
    rooms = bytearray(32)
    rooms[6] = 0x7F
    actor = next(actor for actor in read_map_entities(bytes(memory), bytes(rooms)) if actor.slot == 6)
    assert actor.visible and actor.room_class == 0x60
    memory[0xC6] = 0x12
    actor = next(actor for actor in read_map_entities(bytes(memory), bytes(rooms)) if actor.slot == 6)
    assert not actor.visible


def test_rejects_incomplete_map_entity_memory() -> None:
    with pytest.raises(ValueError, match="entity memory"):
        read_map_entities(bytes(12))


@pytest.mark.parametrize("world,expected", ((0, ("Boat", "Balloon")), (1, ("Balloon",)), (3, ("Boat",))))
def test_world_vehicle_slots_follow_native_world_and_acquisition_rules(world: int, expected: tuple[str, ...]) -> None:
    memory = bytearray(ENTITY_MEMORY_SIZE)
    memory[6:8] = bytes((20, 30))
    memory[0x26:0x28] = bytes((10, 15))
    memory[0x86:0x88] = bytes((6, 7))
    assert tuple(title for title, _, _ in read_world_vehicles(bytes(memory), world, True, True)) == expected
    assert read_world_vehicles(bytes(memory), world, False, False) == ()
    memory[0xC6] = 0x80
    assert all(title != "Boat" for title, _, _ in read_world_vehicles(bytes(memory), world, True, True))


def test_world_vehicles_reject_stale_graphics_and_nonwrapping_bounds() -> None:
    memory = bytearray(ENTITY_MEMORY_SIZE)
    memory[6] = 65
    memory[0x26] = 10
    memory[0x86] = 6
    assert read_world_vehicles(bytes(memory), 3, True, False) == ()
    memory[6] = 20
    memory[0x86] = 0
    assert read_world_vehicles(bytes(memory), 0, True, False) == ()


def test_empty_entity_memory_does_not_invent_actors() -> None:
    assert read_map_entities(bytes(ENTITY_MEMORY_SIZE)) == ()