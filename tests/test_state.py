import pytest
from dataclasses import replace

from game.state import InventoryItemState, read_state
from game.shops import compare_equipment, shop_currency
from game.objectives import chapter_objectives, chapter_transition_losses


class FakeAssets:
    region = "US"

    def __init__(self, areas: set[tuple[int, int]]) -> None:
        self.areas = areas

    def has_area(self, map_id: int, submap: int) -> bool:
        return (map_id, submap) in self.areas


def test_reads_us_location_party_and_persistent_progress() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x28] = 0x0E
    ram[0x41] = 0x80
    ram[0x63:0x65] = bytes((0x04, 0x06))
    ram[0x44:0x46] = bytes((12, 9))
    wram = bytearray(0x300)
    wram[0x157:0x15A] = (12345).to_bytes(3, "little")
    wram[0x15A:0x15C] = bytes((4, 2))
    wram[0x15D:0x165] = bytes((0x2E, 0x1F, 0x0E, 0x0F, 0xFF, 0, 0, 0))
    wram[0x16A:0x16E] = bytes((0x80, 0x87, 0x81, 0x06))
    wram[0x25D] = 0b10110000
    wram[0x28E] = 0b00000011
    wram[0x2A2] = 17
    wram[0x2AD:0x2B0] = (54321).to_bytes(3, "little")
    wram[0x2ED] = 0x84
    hero = 1
    wram[hero] = 0xA0
    wram[hero + 1:hero + 3] = (51).to_bytes(2, "little")
    wram[hero + 3:hero + 5] = (12).to_bytes(2, "little")
    wram[hero + 5] = 8
    wram[hero + 12:hero + 14] = (60).to_bytes(2, "little")
    wram[hero + 14:hero + 16] = (19).to_bytes(2, "little")
    wram[hero + 16:hero + 19] = (777).to_bytes(3, "little")
    wram[hero + 6:hero + 11] = bytes((18, 21, 24, 27, 30))
    wram[hero + 19:hero + 27] = bytes((0x80, 0x53) + (0xFF,) * 6)
    wram[hero + 27:hero + 30] = bytes((0b01000100, 0, 0b00000100))

    state = read_state(
        bytes(ram),
        bytes(wram),
        FakeAssets({(0x04, 0x06)}),
        {(0x04, 0x06): "Endor Throne Room"},
    )

    assert state.location.title == "Endor Throne Room"
    assert (state.location.x, state.location.y) == (12, 9)
    assert state.location.memory_region == "US"
    assert not state.location.is_world
    assert state.chapter_name == "Chapter 5 · Hero"
    assert state.tactics_name == "Offensive"
    assert state.gold == 12345
    assert state.casino_coins == 54321
    assert state.time_name == "Night"
    assert state.treasure_flags[0] == 0b10110000
    assert state.treasure_opened == 3
    assert state.has_boat and state.has_balloon
    assert state.small_medals == 17
    assert tuple(character.character_id for character in state.characters if character.active) == (0, 1, 7)
    assert state.characters[0].name == "Jude"
    assert state.characters[0].hp == 51
    assert state.characters[0].max_hp == 60
    assert state.characters[0].poisoned
    assert (
        state.characters[0].strength,
        state.characters[0].agility,
        state.characters[0].vitality,
        state.characters[0].intelligence,
        state.characters[0].luck,
    ) == (18, 21, 24, 27, 30)
    assert tuple(
        (item.item_id, item.name, item.category, item.equipped)
        for item in state.characters[0].items
    ) == (
        (0x00, "Cypress Stick", "weapon", True),
        (0x53, "Medical Herb", "item", False),
    )
    assert tuple(
        (spell.name, spell.usage) for spell in state.characters[0].spells
    ) == (
        ("Blaze", "battle"),
        ("Firebal", "battle"),
        ("Return", "field"),
    )


def test_uses_japanese_code_note_location_when_region_marker_is_jp() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0
    ram[0x28] = 0x03
    ram[0x44:0x46] = bytes((7, 11))

    assets = FakeAssets({(0x03, 0)})
    assets.region = "Japan"
    state = read_state(bytes(ram), bytes(0x300), assets)

    assert state.location.map_id == 0x03
    assert state.location.submap == 0
    assert "JP code note" in state.location.evidence


def test_us_overworld_is_detected_from_empty_tileset_despite_stale_town_id() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x28] = 0x00
    ram[0x63:0x65] = bytes((0x12, 0x00))
    ram[0x42:0x44] = bytes((154, 23))
    ram[0x44:0x46] = bytes((28, 8))

    state = read_state(bytes(ram), bytes(0x300), FakeAssets({(0x12, 0x00)}))

    assert state.location.is_world
    assert state.location.title == "Main World"
    assert (state.location.x, state.location.y) == (154, 23)
    assert "selector" in state.location.evidence


def test_us_world_selector_chooses_gottside_and_underworld_layers() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x28] = 0

    ram[0x65] = 1
    gottside = read_state(bytes(ram), bytes(0x300))
    ram[0x65] = 3
    underworld = read_state(bytes(ram), bytes(0x300))

    assert (gottside.location.title, gottside.location.area) == (
        "Gottside",
        "Gottside",
    )
    assert (underworld.location.title, underworld.location.area) == (
        "Underworld",
        "Underworld",
    )


def test_us_indoor_location_never_uses_japanese_map_id_note() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x28] = 0x0D
    ram[0x41] = 0x80
    ram[0x63:0x65] = bytes((0x02, 0x01))
    ram[0x44:0x46] = bytes((23, 25))

    state = read_state(bytes(ram), bytes(0x300), FakeAssets({(0x02, 0x01), (0x0D, 0x00)}))

    assert (state.location.map_id, state.location.submap) == (0x02, 0x01)
    assert not state.location.is_world


def test_unknown_indoor_map_does_not_fall_back_to_world_coordinates() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x28] = 0x0B
    ram[0x41] = 0x80
    ram[0x63:0x65] = bytes((0xFF, 0xFF))
    ram[0x42:0x44] = bytes((201, 99))

    state = read_state(bytes(ram), bytes(0x300), FakeAssets(set()))

    assert not state.location.is_world
    assert state.location.area == "Unknown"
    assert (state.location.x, state.location.y) == (0, 0)


def test_local_map_flag_survives_a_battle_tileset_change() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x41] = 0x80
    ram[0x28] = 0
    ram[0x63:0x65] = bytes((2, 1))
    ram[0x44:0x46] = bytes((8, 9))
    state = read_state(bytes(ram), bytes(0x300), FakeAssets({(2, 1)}))
    assert not state.location.is_world
    assert (state.location.x, state.location.y) == (8, 9)


def test_rejects_incomplete_memory_snapshots() -> None:
    try:
        read_state(bytes(0x100), bytes(0x300))
    except ValueError as error:
        assert "system RAM" in str(error)
    else:
        raise AssertionError("incomplete RAM should fail")


def test_active_party_preserves_native_formation_order() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    wram = bytearray(0x300)
    wram[0x16A:0x16E] = bytes((0x87, 0x86, 0x81, 0))
    state = read_state(bytes(ram), bytes(wram))
    assert tuple(character.character_id for character in state.active_party) == (7, 6, 1)


def test_active_guest_uses_six_byte_record_and_verified_profile() -> None:
    wram = bytearray(0x300)
    wram[0x16A:0x16E] = bytes((0x86, 0x89, 0, 0))
    wram[0x10F:0x115] = bytes((0x80, 70, 0, 12, 0, 0xC5))
    state = read_state(bytes(0x800), bytes(wram), guest_profile=lambda identifier: ("Healie", 80, 30))
    assert tuple(character.character_id for character in state.active_party) == (6, 9)
    guest = state.active_party[1]
    assert guest.name == "Healie"
    assert guest.guest
    assert (guest.hp, guest.max_hp, guest.mp, guest.max_mp) == (70, 80, 12, 30)


def test_available_roster_includes_reserves_but_not_old_leveled_records() -> None:
    wram = bytearray(0x300)
    wram[0x16A] = 0x80
    wram[0x172:0x174] = bytes((0x87, 0x81))
    wram[1 + 6 * 30 + 5] = 20
    wram[0x15C] = 1
    wram[0x25B:0x25D] = (123).to_bytes(2, "little")
    state = read_state(bytes(0x800), bytes(wram))
    assert tuple(character.character_id for character in state.available_party) == (0, 7, 1)
    assert not state.characters[6].available
    assert state.hero_female
    assert state.vault_gold == 123000


def test_alternate_active_roster_uses_native_state_flags() -> None:
    wram = bytearray(0x300)
    wram[0x18E] = 0x80
    wram[0x16A] = 0x80
    wram[0x16E:0x170] = bytes((0x87, 0x81))
    state = read_state(bytes(0x800), bytes(wram))
    assert state.party_ids == (7, 1)


def test_shop_comparison_is_per_character_and_uses_equipped_item() -> None:
    class Catalog:
        def equipment_bonus(self, item_id: int) -> int:
            return (2, 7, 12)[item_id]

        def equipment_traits(self, item_id: int) -> tuple[int, int, int]:
            return (0, 0, 0)

        def equipment_eligible(self, item_id: int, character_id: int, hero_female: bool = False) -> bool:
            return character_id != 7

    wram = bytearray(0x300)
    wram[7] = 18
    wram[20:28] = bytes((0x80,)) + bytes((0xFF,)) * 7
    hero = read_state(bytes(0x800), bytes(wram)).characters[0]
    result = compare_equipment(Catalog(), 2, hero)
    assert (result.current_value, result.candidate_value, result.delta, result.verdict) == (20, 30, 10, "Upgrade")
    assert result.current_item == "Cypress Stick"
    reserve = replace(hero, character_id=6, name="Ragnar", strength=30)
    other = compare_equipment(Catalog(), 2, reserve)
    assert (other.current_value, other.candidate_value, other.delta) == (32, 42, 10)
    assert compare_equipment(Catalog(), 2, replace(hero, character_id=7)).verdict == "Cannot equip"


def test_lighthouse_objective_requires_native_request_or_completion_and_current_chapter() -> None:
    wram = bytearray(0x300)
    wram[0x15A] = 4
    wram[0x293] = 0x20
    state = read_state(bytes(0x800), bytes(wram))
    objectives = chapter_objectives(state)
    assert len(objectives) == 1 and not objectives[0].completed
    assert objectives[0].layer_key == "area-42-00"
    wram[0x293] |= 0x10
    assert chapter_objectives(read_state(bytes(0x800), bytes(wram)))[0].completed
    assert all(objective.key != "lighthouse-fire" for objective in chapter_objectives(replace(state, chapter=2)))


def test_birdsong_retrieval_requires_request_and_eligible_carried_item() -> None:
    state = read_state(bytes(0x800), bytes(0x300))
    events = bytearray(50)
    events[8] = 0x0C
    events[11] = 2
    state = replace(state, chapter=1, event_flags=bytes(events), party_ids=(0,))
    retrieval = next(objective for objective in chapter_objectives(state) if objective.key == "birdsong-nectar")
    assert not retrieval.completed and retrieval.layer_key == "area-3f-00"
    hero = replace(state.characters[0], items=(InventoryItemState(0x75, "Birdsong Nectar", "item", False),))
    state = replace(state, characters=(hero, *state.characters[1:]))
    assert next(objective for objective in chapter_objectives(state) if objective.key == "birdsong-nectar").completed
    events[8] = 2
    assert all(objective.key != "birdsong-nectar" for objective in chapter_objectives(replace(state, event_flags=bytes(events))))


def test_padequia_completion_uses_reunion_bit_not_request_or_roster_levels() -> None:
    state = read_state(bytes(0x800), bytes(0x300))
    events = bytearray(50)
    events[0x17] = 0x10
    state = replace(state, chapter=4, event_flags=bytes(events))
    assert not chapter_objectives(state)[0].completed
    events[0x16] = 8
    assert chapter_objectives(replace(state, event_flags=bytes(events)))[0].completed


def test_tournament_round_counter_does_not_fabricate_victory_completion() -> None:
    state = read_state(bytes(0x800), bytes(0x300))
    events = bytearray(50)
    events[10] = 0x20
    events[12] = 4
    state = replace(state, chapter=1, event_flags=bytes(events))
    objective = next(objective for objective in chapter_objectives(state) if objective.key == "endor-tournament")
    assert not objective.completed and "4 of 4" in objective.hint and objective.progress == 1.0
    events[9] = 0x40
    assert next(objective for objective in chapter_objectives(replace(state, event_flags=bytes(events)))
                if objective.key == "endor-tournament").completed
    assert all(objective.key != "endor-tournament" for objective in chapter_objectives(replace(state, chapter=4)))


def test_tunnel_affordability_does_not_replace_native_completion_flag() -> None:
    state = read_state(bytes(0x800), bytes(0x300))
    state = replace(state, chapter=2, gold=60000)
    objective = chapter_objectives(state)[0]
    assert objective.key == "branca-tunnel" and not objective.completed
    assert "enough gold" in objective.hint and objective.progress == 1.0
    short = chapter_objectives(replace(state, gold=15000))[0]
    assert "45,000 more to go" in short.hint and short.progress == 0.25
    events = bytearray(state.event_flags)
    events[12] = 0x40
    assert chapter_objectives(replace(state, gold=0, event_flags=bytes(events)))[0].completed


def test_flying_shoes_retrieval_is_chapter_scoped_and_uses_eligible_possession() -> None:
    state = replace(read_state(bytes(0x800), bytes(0x300)), party_ids=(6,), available_ids=(6,))
    objective = chapter_objectives(state)[0]
    assert objective.key == "flying-shoes" and objective.layer_key == "area-33-03" and not objective.completed
    characters = list(state.characters)
    characters[6] = replace(characters[6], items=(InventoryItemState(0x6C, "Flying Shoes", "item", False),))
    assert chapter_objectives(replace(state, characters=tuple(characters)))[0].completed
    assert all(objective.key != "flying-shoes" for objective in chapter_objectives(replace(state, chapter=4)))


def test_chapter_four_item_retrieval_does_not_infer_confrontation_completion() -> None:
    state = replace(read_state(bytes(0x800), bytes(0x300)), chapter=3, party_ids=(2,), available_ids=(2,))
    objectives = chapter_objectives(state)
    assert {objective.layer_key for objective in objectives} == {"area-31-03", "area-2d-02"}
    assert all(not objective.completed for objective in objectives)
    characters = list(state.characters)
    characters[2] = replace(characters[2], items=(InventoryItemState(0x5D, "Sphere of Silence", "item", False),))
    objectives = chapter_objectives(replace(state, characters=tuple(characters)))
    assert objectives[0].completed and not objectives[1].completed
    assert all("native" not in objective.hint.casefold() for objective in objectives)


def test_objective_hints_use_player_language_in_every_chapter() -> None:
    base = read_state(bytes(0x800), bytes(0x300))
    events = bytearray(50)
    events[8], events[10], events[11], events[0x17], events[0x18] = 0x0C, 0x20, 2, 0x10, 0x20
    for chapter in range(5):
        state = replace(base, chapter=chapter, event_flags=bytes(events), party_ids=(0,), available_ids=(0,))
        objectives = chapter_objectives(state)
        assert objectives
        for objective in objectives:
            text = f"{objective.title} {objective.destination} {objective.hint}".casefold()
            assert objective.hint
            assert not any(word in text for word in ("native", "flag", "event", "floor 0", " x ", "(9,8)"))


def test_chapter_end_losses_only_list_currently_carried_removed_items() -> None:
    state = read_state(bytes(0x800), bytes(0x300))
    character = replace(state.characters[0], items=(InventoryItemState(0x6C, "Flying Shoes", "item", False),))
    state = replace(state, available_ids=(0,), characters=(character, *state.characters[1:]))
    assert chapter_transition_losses(state) == ("Flying Shoes",)
    assert chapter_transition_losses(replace(state, chapter=4)) == ()
    assert chapter_transition_losses(replace(state, available_ids=())) == ()
    empty = replace(character, items=())
    assert chapter_transition_losses(replace(state, characters=(empty, *state.characters[1:]))) == ()


def test_transformation_shape_is_sprite_identity_and_expires_without_stale_name() -> None:
    state = read_state(bytes(0x800), bytes(0x300))
    active = replace(state, transform_steps=120, transform_shape=0xA5)
    assert active.transformation_kind == "NPC appearance"
    assert active.transformation_sprite_id == 0x25
    character = replace(active, transform_shape=5)
    assert character.transformation_kind == "Character appearance"
    expired = replace(active, transform_steps=0)
    assert expired.transformation_kind is None and expired.transformation_sprite_id is None


def test_equipment_comparison_reports_lost_recovery_even_with_higher_attack() -> None:
    class Catalog:
        def equipment_bonus(self, item_id: int) -> int:
            return 100 if item_id == 0x1B else 90

        def equipment_traits(self, item_id: int) -> tuple[int, int, int]:
            return (0, 0, 0)

        def equipment_eligible(self, item_id: int, character_id: int, hero_female: bool = False) -> bool:
            return True

        def equipment_passives(self, item_id: int) -> tuple[str, ...]:
            return ("Eligible hit recovery: floor(damage/4)+1 HP",) if item_id == 0x1C else ()

    weapon = InventoryItemState(0x1C, "Sword of Miracles", "weapon", True)
    hero = replace(read_state(bytes(0x800), bytes(0x300)).characters[0], strength=20, items=(weapon,))
    result = compare_equipment(Catalog(), 0x1B, hero)
    assert result.delta == 10
    assert result.verdict == "Upgrade with tradeoff"
    assert any(note.startswith("Loses: Eligible hit recovery") for note in result.notes)


def test_equipment_comparison_reports_lost_native_protection() -> None:
    class Catalog:
        def equipment_bonus(self, item_id: int) -> int:
            return 10 if item_id == 0x32 else 20

        def equipment_traits(self, item_id: int) -> tuple[int, int, int]:
            return (0, 0, 0)

        def equipment_eligible(self, item_id: int, character_id: int, hero_female: bool = False) -> bool:
            return True

        def equipment_protection(self, item_id: int) -> tuple[tuple[str, int], ...]:
            return (("Breath damage", 170),) if item_id == 0x32 else ()

    armor = InventoryItemState(0x32, "Dragon Mail", "armor", True)
    hero = replace(read_state(bytes(0x800), bytes(0x300)).characters[0], agility=20, items=(armor,))
    result = compare_equipment(Catalog(), 0x33, hero)
    assert result.delta == 10
    assert result.verdict == "Upgrade with tradeoff"
    assert "Breath damage taken +34%" in result.notes


def test_native_armor_priority_masks_shield_protection_gain() -> None:
    class Catalog:
        def equipment_bonus(self, item_id: int) -> int:
            return 10

        def equipment_traits(self, item_id: int) -> tuple[int, int, int]:
            return (0, 0, 0)

        def equipment_eligible(self, item_id: int, character_id: int, hero_female: bool = False) -> bool:
            return True

        def equipment_protection(self, item_id: int) -> tuple[tuple[str, int], ...]:
            return (("Breath damage", 170),) if item_id == 0x43 else ()

    armor = InventoryItemState(0x24, "Clothes", "armor", True)
    shield = InventoryItemState(0x3D, "Leather Shield", "shield", True)
    hero = replace(read_state(bytes(0x800), bytes(0x300)).characters[0], items=(armor, shield))
    masked = compare_equipment(Catalog(), 0x43, hero)
    assert not any("Breath damage" in note for note in masked.notes)
    unmasked = compare_equipment(Catalog(), 0x43, replace(hero, items=(shield,)))
    assert "Breath damage taken -34%" in unmasked.notes


def test_meteorite_armband_uses_native_agility_cap_and_armor_override() -> None:
    class Catalog:
        def equipment_bonus(self, item_id: int) -> int:
            return 0

        def equipment_traits(self, item_id: int) -> tuple[int, int, int]:
            return (0, 0, 0)

        def equipment_eligible(self, item_id: int, character_id: int, hero_female: bool = False) -> bool:
            return True

    hero = replace(read_state(bytes(0x800), bytes(0x300)).characters[0], agility=150, items=())
    result = compare_equipment(Catalog(), 0x50, hero)
    assert (result.stat, result.current_value, result.candidate_value, result.delta) == ("AGI", 150, 255, 105)
    other = InventoryItemState(0x4F, "Other accessory", "accessory", True)
    result = compare_equipment(Catalog(), 0x50, replace(hero, items=(other,)))
    assert (result.current_value, result.candidate_value, result.delta) == (150, 255, 105)
    armor = InventoryItemState(0x3C, "Demon Armor", "armor", True)
    blocked = compare_equipment(Catalog(), 0x50, replace(hero, items=(armor,)))
    assert (blocked.current_value, blocked.candidate_value, blocked.delta) == (0, 0, 0)


@pytest.mark.parametrize("map_id,submap,currency", ((2, 0, "gold"), (4, 1, "casino coins"), (0x22, 0, "medals")))
def test_native_shop_currency_is_not_always_carried_gold(map_id: int, submap: int, currency: str) -> None:
    assert shop_currency(map_id, submap) == currency


@pytest.mark.parametrize("gold", (65535, 65536, 99999))
def test_carried_gold_uses_all_three_native_bytes(gold: int) -> None:
    wram = bytearray(0x300)
    wram[0x157:0x15A] = gold.to_bytes(3, "little")
    assert read_state(bytes(0x800), bytes(wram)).gold == gold