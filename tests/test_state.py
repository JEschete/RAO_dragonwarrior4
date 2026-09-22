from game.state import read_state


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
    ram[0x63:0x65] = bytes((0x04, 0x06))
    ram[0x44:0x46] = bytes((12, 9))
    wram = bytearray(0x300)
    wram[0x157:0x15A] = (12345).to_bytes(3, "little")
    wram[0x15A:0x15C] = bytes((4, 2))
    wram[0x15D:0x165] = bytes((0x2E, 0x1F, 0x0E, 0x0F, 0xFF, 0, 0, 0))
    wram[0x16A:0x16E] = bytes((0, 7, 1, 7))
    wram[0x165] = 0b00000011
    wram[0x25D] = 0b10110000
    wram[0x28E] = 0b00000011
    wram[0x2A2] = 17
    wram[0x2AD:0x2B0] = (54321).to_bytes(3, "little")
    wram[0x2ED] = 0x84
    wram[0x2E7:0x2EA] = bytes((3, 2, 1))
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
    assert state.return_locations == ("Branca", "Endor")
    assert state.treasure_flags[0] == 0b10110000
    assert state.treasure_opened == 3
    assert state.has_boat and state.has_balloon
    assert state.small_medals == 17
    assert state.taloon_shop_stock == (
        ("Boomerang", 3),
        ("Chain Sickle", 2),
        ("Sword of Malice", 1),
    )
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

    state = read_state(bytes(ram), bytes(0x300), FakeAssets({(0x03, 0)}))

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
    assert "tileset" in state.location.evidence


def test_us_indoor_location_never_uses_japanese_map_id_note() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x28] = 0x0D
    ram[0x63:0x65] = bytes((0x02, 0x01))
    ram[0x44:0x46] = bytes((23, 25))

    state = read_state(bytes(ram), bytes(0x300), FakeAssets({(0x02, 0x01), (0x0D, 0x00)}))

    assert (state.location.map_id, state.location.submap) == (0x02, 0x01)
    assert not state.location.is_world


def test_falls_back_to_world_coordinates_without_matching_area() -> None:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x28] = 0x0B
    ram[0x63:0x65] = bytes((0xFF, 0xFF))
    ram[0x42:0x44] = bytes((201, 99))

    state = read_state(bytes(ram), bytes(0x300), FakeAssets(set()))

    assert state.location.is_world
    assert state.location.area == "World"
    assert (state.location.x, state.location.y) == (201, 99)


def test_rejects_incomplete_memory_snapshots() -> None:
    try:
        read_state(bytes(0x100), bytes(0x300))
    except ValueError as error:
        assert "system RAM" in str(error)
    else:
        raise AssertionError("incomplete RAM should fail")