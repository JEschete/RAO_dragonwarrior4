import pytest

from game.battle import BATTLE_MEMORY_SIZE, read_battle_state


def test_decodes_documented_enemy_slots_and_rewards() -> None:
    ram = bytearray(0x800)
    ram[0x440:0x442] = bytes((0x12, 0x34))
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[1:3] = (25).to_bytes(2, "little")
    battle[3:6] = (300).to_bytes(3, "little")
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))

    state = read_battle_state(bytes(ram), bytes(battle))

    assert state.available
    assert state.active
    assert state.reward_gold == 25
    assert state.reward_experience == 300
    assert state.enemies[0].monster_id == 0x12
    assert state.enemies[0].label == "Monster $12"
    assert state.enemies[0].hp == 45
    assert state.enemies[0].mp == 6
    assert state.enemies[0].attack == 14
    assert state.enemies[0].defense == 11


def test_requires_positive_hp_and_coherent_stats_to_open_combat() -> None:
    ram = bytes(0x800)
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x7E:0x80] = (99).to_bytes(2, "little")

    state = read_battle_state(ram, bytes(battle))

    assert not state.active


def test_rejects_incomplete_battle_memory() -> None:
    with pytest.raises(ValueError, match="battle memory"):
        read_battle_state(bytes(0x800), bytes(12))