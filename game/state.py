from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .reference_data import (
    CHAPTERS,
    PARTY_NAMES,
    RETURN_LOCATIONS,
    SpellDefinition,
    TACTICS,
    decode_text,
    item_category,
    item_name,
    learned_spells,
    map_title,
    time_of_day,
)
from .rom_assets import area_key


RAM_SIZE = 0x0800
WRAM_ADDRESS = 0x6000
WRAM_SIZE = 0x0300


class AreaCatalog(Protocol):
    region: str

    def has_area(self, map_id: int, submap: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class LocationState:
    title: str
    area: str
    map_id: int
    submap: int
    x: int
    y: int
    is_world: bool
    layer_id: int
    memory_region: str
    evidence: str


@dataclass(frozen=True, slots=True)
class InventoryItemState:
    item_id: int
    name: str
    category: str
    equipped: bool


@dataclass(frozen=True, slots=True)
class CharacterState:
    character_id: int
    name: str
    active: bool
    alive: bool
    poisoned: bool
    paralyzed: bool
    level: int
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    experience: int
    strength: int
    agility: int
    vitality: int
    intelligence: int
    luck: int
    items: tuple[InventoryItemState, ...]
    spells: tuple[SpellDefinition, ...]


@dataclass(frozen=True, slots=True)
class DragonWarrior4State:
    location: LocationState
    chapter: int
    chapter_name: str
    tactics: int
    tactics_name: str
    gold: int
    casino_coins: int
    time_value: int
    time_name: str
    characters: tuple[CharacterState, ...]
    return_locations: tuple[str, ...]
    treasure_flags: bytes
    treasure_opened: int
    treasure_total: int
    has_boat: bool
    has_balloon: bool
    small_medals: int
    taloon_shop_stock: tuple[tuple[str, int], ...]
    dialogue: str


def read_state(
    ram: bytes,
    wram: bytes,
    assets: AreaCatalog | None = None,
    submap_names: dict[tuple[int, int], str] | None = None,
) -> DragonWarrior4State:
    if len(ram) < RAM_SIZE:
        raise ValueError("DW4 system RAM snapshot is incomplete")
    if len(wram) < WRAM_SIZE:
        raise ValueError("DW4 work RAM snapshot is incomplete")

    party_ids = _party_ids(wram)
    hero_name = decode_text(wram[0x15D:0x165])
    characters = tuple(
        _character(wram, character_id, party_ids, hero_name)
        for character_id in range(len(PARTY_NAMES))
    )
    chapter = wram[0x15A]
    tactics = wram[0x15B]
    treasure = wram[0x25D:0x278]
    time_value = wram[0x2ED]
    return_flags = int.from_bytes(wram[0x165:0x168], "little")
    return DragonWarrior4State(
        _location(ram, assets, submap_names),
        chapter,
        CHAPTERS[chapter] if chapter < len(CHAPTERS) else f"Chapter value ${chapter:02X}",
        tactics,
        TACTICS[tactics] if tactics < len(TACTICS) else f"Tactics value ${tactics:02X}",
        int.from_bytes(wram[0x157:0x15A], "little"),
        int.from_bytes(wram[0x2AD:0x2B0], "little"),
        time_value,
        time_of_day(time_value),
        characters,
        tuple(
            name
            for index, name in enumerate(RETURN_LOCATIONS)
            if return_flags & (1 << index)
        ),
        bytes(treasure),
        sum(value.bit_count() for value in treasure),
        len(treasure) * 8,
        bool(wram[0x28E] & 0x01),
        bool(wram[0x28E] & 0x02),
        wram[0x2A2],
        (
            ("Boomerang", wram[0x2E7]),
            ("Chain Sickle", wram[0x2E8]),
            ("Sword of Malice", wram[0x2E9]),
        ),
        decode_text(ram[0x6AA:0x76C]),
    )


def _party_ids(wram: bytes) -> tuple[int, ...]:
    result = []
    for value in wram[0x16A:0x16E]:
        character_id = value & 0x7F
        if character_id < len(PARTY_NAMES) and character_id not in result:
            result.append(character_id)
    return tuple(result)


def _character(
    wram: bytes,
    character_id: int,
    party_ids: tuple[int, ...],
    hero_name: str,
) -> CharacterState:
    start = 1 + character_id * 30
    record = wram[start:start + 30]
    flags = record[0]
    name = hero_name if character_id == 0 and hero_name else PARTY_NAMES[character_id]
    items = tuple(
        InventoryItemState(
            value & 0x7F,
            item_name(value & 0x7F),
            item_category(value & 0x7F),
            bool(value & 0x80),
        )
        for value in record[19:27]
        if value & 0x7F != 0x7F
    )
    return CharacterState(
        character_id,
        name,
        character_id in party_ids,
        bool(flags & 0x80),
        bool(flags & 0x20),
        bool(flags & 0x40),
        record[5],
        int.from_bytes(record[1:3], "little"),
        int.from_bytes(record[12:14], "little"),
        int.from_bytes(record[3:5], "little"),
        int.from_bytes(record[14:16], "little"),
        int.from_bytes(record[16:19], "little"),
        record[6],
        record[7],
        record[8],
        record[9],
        record[10],
        items,
        learned_spells(character_id, record[27:30]),
    )


def _location(
    ram: bytes,
    assets: AreaCatalog | None,
    submap_names: dict[tuple[int, int], str] | None,
) -> LocationState:
    marker = ram[0x58F]
    memory_region = "US" if marker == 0x10 else "Japan" if marker == 0 else "Unknown"
    us_candidate = (
        ram[0x63],
        ram[0x64],
        "Data Crystal US RAM map ($0063/$0064)",
    )
    jp_candidate = (
        ram[0x28],
        0,
        "RetroAchievements JP code note ($0028; submap unavailable)",
    )
    candidates = (
        (jp_candidate, us_candidate)
        if memory_region == "Japan"
        else (us_candidate, jp_candidate)
    )
    for map_id, submap, evidence in candidates:
        if assets is not None and assets.has_area(map_id, submap):
            return LocationState(
                map_title(map_id, submap, submap_names),
                "Dungeon / town",
                map_id,
                submap,
                ram[0x44],
                ram[0x45],
                False,
                area_key(map_id, submap),
                memory_region,
                evidence,
            )

    map_id, submap, evidence = candidates[0]
    if assets is None and map_id < 0x49:
        return LocationState(
            map_title(map_id, submap, submap_names),
            "Dungeon / town",
            map_id,
            submap,
            ram[0x44],
            ram[0x45],
            False,
            area_key(map_id, submap),
            memory_region,
            evidence,
        )
    return LocationState(
        "Main World",
        "World",
        map_id,
        submap,
        ram[0x42],
        ram[0x43],
        True,
        -1,
        memory_region,
        f"{evidence}; no documented indoor descriptor matched",
    )