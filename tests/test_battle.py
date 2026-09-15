import pytest

from game.battle import (
    BATTLE_MEMORY_SIZE,
    BATTLE_TEXT_ADDRESS,
    observed_monster_names,
    read_battle_state,
)


def encoded_text(value: str) -> bytes:
    return bytes(
        0
        if character == " "
        else ord(character) - ord("a") + 0x0B
        if character.islower()
        else ord(character) - ord("A") + 0x25
        if character.isupper()
        else 0x78
        if character == "."
        else 0x6E
        for character in value
    )


def test_decodes_documented_enemy_slots_and_rewards() -> None:
    ram = bytearray(0x800)
    ram[0x440:0x442] = bytes((0x12, 0x34))
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[1:3] = (25).to_bytes(2, "little")
    battle[3:6] = (300).to_bytes(3, "little")
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))

    state = read_battle_state(
        bytes(ram),
        bytes(battle),
        monster_name=lambda monster_id: {0x12: "Slime"}.get(monster_id),
    )

    assert state.available
    assert state.active
    assert state.reward_gold == 25
    assert state.reward_experience == 300
    assert state.enemies[0].monster_id == 0x12
    assert state.enemies[0].label == "Slime"
    assert state.enemies[0].hp == 45
    assert state.enemies[0].mp == 6
    assert state.enemies[0].attack == 14
    assert state.enemies[0].defense == 11


def test_observes_monster_names_from_complete_battle_introduction() -> None:
    ram = bytearray(0x800)
    ram[0x440:0x442] = bytes((0x03, 0x00))
    introduction = encoded_text("Giant Worm appears.     Slime appears.")
    ram[BATTLE_TEXT_ADDRESS:BATTLE_TEXT_ADDRESS + len(introduction)] = introduction

    assert observed_monster_names(bytes(ram)) == {
        0x03: "Giant Worm",
        0x00: "Slime",
    }


def test_ignores_incomplete_battle_introduction() -> None:
    ram = bytearray(0x800)
    ram[0x440:0x442] = bytes((0x03, 0x04))
    introduction = encoded_text("Giant Worm appears.")
    ram[BATTLE_TEXT_ADDRESS:BATTLE_TEXT_ADDRESS + len(introduction)] = introduction

    assert observed_monster_names(bytes(ram)) == {}


def test_ignores_stale_text_after_battle_introduction() -> None:
    ram = bytearray(0x800)
    ram[0x440:0x442] = bytes((0x03, 0xFF))
    text = encoded_text("Giant Worm appears. Ragnar attacks!")
    ram[BATTLE_TEXT_ADDRESS:BATTLE_TEXT_ADDRESS + len(text)] = text

    assert observed_monster_names(bytes(ram)) == {}


def test_unresolved_monster_id_is_not_shown_as_hex() -> None:
    ram = bytearray(0x800)
    ram[0x440] = 0x03
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))

    state = read_battle_state(bytes(ram), bytes(battle))

    assert state.enemies[0].label == "Enemy group 1"


def test_zero_is_a_valid_monster_id() -> None:
    ram = bytearray(0x800)
    ram[0x440:0x442] = bytes((0x00, 0xFF))
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 8, 0, 0, 1))

    state = read_battle_state(
        bytes(ram),
        bytes(battle),
        monster_name=lambda monster_id: {0x00: "Slime"}.get(monster_id),
    )

    assert state.enemies[0].monster_id == 0x00
    assert state.enemies[0].label == "Slime"


def test_requires_positive_hp_and_coherent_stats_to_open_combat() -> None:
    ram = bytes(0x800)
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x7E:0x80] = (99).to_bytes(2, "little")

    state = read_battle_state(ram, bytes(battle))

    assert not state.active


def test_rejects_incomplete_battle_memory() -> None:
    with pytest.raises(ValueError, match="battle memory"):
        read_battle_state(bytes(0x800), bytes(12))