import pytest
from pathlib import Path

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
    battle[6:10] = bytes((0x12, 0x34, 0xFF, 0xFF))
    battle[1:3] = (25).to_bytes(2, "little")
    battle[3:6] = (300).to_bytes(3, "little")
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 0))
    battle[0x82:0x90] = bytes((9, 15, 0, 12, 0, 0, 2, 0, 0, 0, 46, 0, 7, 1))

    state = read_battle_state(
        bytes(ram),
        bytes(battle),
        monster_name=lambda monster_id: {0x12: "Slime"}.get(monster_id),
    )

    assert state.available
    assert state.active
    assert state.reward_gold == 25
    assert state.reward_experience == 300
    assert len(state.enemies) == 8
    assert state.enemies[0].monster_id == 0x12
    assert state.enemies[0].label == "Slime"
    assert state.enemies[0].hp == 45
    assert state.enemies[0].mp == 6
    assert state.enemies[0].attack == 14
    assert state.enemies[0].defense == 11
    assert state.enemies[1].monster_id == 0x34
    assert state.enemies[1].group_code == 1


@pytest.mark.parametrize("mp, infinite", ((0xFE, False), (0xFF, True)))
def test_native_infinite_mp_is_not_an_ordinary_numeric_pool(mp: int, infinite: bool) -> None:
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 0xC0, 0, 0, 0, 30, 0, mp, 0))
    state = read_battle_state(bytes(0x800), bytes(battle), context_flags=0x80,
                              monster_vitals=lambda identifier: (45, mp))
    assert state.enemies[0].infinite_mp is infinite
    assert state.enemies[0].mp == mp


def test_named_enemy_conditions_do_not_interpret_presence_flags_as_paralysis() -> None:
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 0xC0, 0, 0, 0, 30, 0, 3, 0))
    state = read_battle_state(bytes(0x800), bytes(battle), context_flags=0x80)
    assert state.enemies[0].conditions == ()
    battle[0x74 + 5] = 0x0D
    battle[0x74 + 6] |= 0x20
    state = read_battle_state(bytes(0x800), bytes(battle), context_flags=0x80)
    assert state.enemies[0].conditions == ("Sleeping", "Confused", "Silenced", "Paralyzed")


def test_necrosaro_phase_keeps_setup_name_and_current_profile_vitals_separate() -> None:
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[6] = 0xD2
    battle[7:10] = bytes((255, 255, 255))
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 0xC0, 0, 0, 0, 30, 0, 3, 0))
    names = lambda identity: "Necrosaro" if identity == 0xAE else "Other profile"
    state = read_battle_state(bytes(0x800), bytes(battle), names, context_flags=0x80,
                              monster_vitals=lambda identity: (1200, 255) if identity == 0xD2 else (400, 10),
                              setup_monster_ids=bytes((0xAE, 255, 255, 255)))
    assert state.enemies[0].name == "Necrosaro"
    assert state.enemies[0].monster_id == 0xD2 and state.enemies[0].max_hp == 1200
    assert read_battle_state(bytes(0x800), bytes(battle), names).enemies[0].name == "Other profile"
    assert not read_battle_state(bytes(0x800), bytes(battle), names,
                                 setup_monster_ids=bytes((0, 255, 255, 255))).active


def test_scripted_scene_workspace_does_not_become_coherent_ghost_enemies() -> None:
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[6:10] = bytes((3, 2, 4, 2))
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 0xC0, 0, 0, 0, 30, 0, 3, 0))
    state = read_battle_state(bytes(0x800), bytes(battle), context_flags=0x80,
                              setup_monster_ids=bytes((0xB3, 0x29, 255, 255)))
    assert not state.active and state.enemies == ()
    assert "shared scene workspace" in state.detector_evidence


def test_scripted_loss_context_edges_never_reintroduce_reused_enemy_workspace() -> None:
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[6:10] = bytes((3, 3, 1, 0x43))
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 0xC0, 0, 0, 0, 30, 0, 3, 0))
    for context in (0x80, 0, 0x80, 0):
        state = read_battle_state(bytes(0x800), bytes(battle), context_flags=context,
                                  setup_monster_ids=bytes((0xBB, 255, 255, 255)))
        assert not state.active and state.enemies == ()


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
    battle[6:10] = bytes((0x03, 0xFF, 0xFF, 0xFF))
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))

    state = read_battle_state(bytes(ram), bytes(battle))

    assert state.enemies[0].label == "Enemy slot 1"


def test_zero_is_a_valid_monster_id() -> None:
    ram = bytearray(0x800)
    ram[0x440:0x442] = bytes((0x00, 0xFF))
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[6:10] = bytes((0x00, 0xFF, 0xFF, 0xFF))
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 8, 0, 0, 0))

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


def test_decodes_full_width_native_attack_and_defense() -> None:
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 44, 1, 144, 1, 0, 0xC0, 0, 0, 0, 45, 0, 6, 0))
    state = read_battle_state(bytes(0x800), bytes(battle), context_flags=0x80)
    assert state.active
    assert state.enemies[0].attack == 300
    assert state.enemies[0].defense == 400


def test_field_context_clears_stale_enemy_records() -> None:
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 0xC0, 0, 0, 0, 45, 0, 6, 0))
    state = read_battle_state(bytes(0x800), bytes(battle), context_flags=0)
    assert state.available
    assert not state.active
    assert state.enemies == ()