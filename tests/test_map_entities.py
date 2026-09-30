import pytest

from game.map_entities import ENTITY_MEMORY_SIZE, read_map_entities


def test_reads_visible_entities_after_inactive_slot_holes() -> None:
    memory = bytearray(ENTITY_MEMORY_SIZE)
    memory[0xC0 + 6:0xC0 + 32] = bytes((0xFF,)) * 26
    memory[0xC0 + 6] = 0x12
    memory[0xC0 + 8] = 0x83
    memory[6] = 11
    memory[8] = 22
    memory[0x20 + 6] = 7
    memory[0x20 + 8] = 9
    memory[0x80 + 6] = 0x2A
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
    ) == (6, 11, 7, 0x2A, 0x12, 0x11, 0x40)
    assert (entities[1].slot, entities[1].x, entities[1].y, entities[1].descriptor) == (
        8,
        22,
        9,
        0x83,
    )


def test_rejects_incomplete_map_entity_memory() -> None:
    with pytest.raises(ValueError, match="entity memory"):
        read_map_entities(bytes(12))