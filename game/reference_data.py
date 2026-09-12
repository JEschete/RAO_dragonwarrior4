from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re


DATA_CRYSTAL_ROOT = "https://datacrystal.tcrf.net/wiki/Dragon_Warrior_IV_(NES)"


@dataclass(frozen=True, slots=True)
class ReferenceSource:
    title: str
    filename: str
    url: str
    purpose: str
    available: bool = False


@dataclass(frozen=True, slots=True)
class TreasureRecord:
    flag_index: int
    map_id: int
    submap: int
    description: str
    reward: str

    def is_open(self, treasure_flags: bytes) -> bool:
        byte_index, bit = divmod(self.flag_index, 8)
        return byte_index < len(treasure_flags) and bool(
            treasure_flags[byte_index] & (1 << bit)
        )


REFERENCE_SOURCE_SPECS = (
    (
        "Game and cartridge profile",
        "Dragon Warrior IV (NES) - Data Crystal.htm",
        DATA_CRYSTAL_ROOT,
        "MMC1 layout, ROM size, releases, and known whole-file hashes",
    ),
    (
        "ROM map",
        "Dragon Warrior IV (NES)_ROM map - Data Crystal.htm",
        f"{DATA_CRYSTAL_ROOT}/ROM_map",
        "Map pointers, tilesets, graphics, palettes, and overworld rows",
    ),
    (
        "RAM map",
        "Dragon Warrior IV (NES)_RAM map - Data Crystal.htm",
        f"{DATA_CRYSTAL_ROOT}/RAM_map",
        "US map identity and live party/progression fields",
    ),
    (
        "SRAM map",
        "Dragon Warrior IV (NES)_SRAM map - Data Crystal.htm",
        f"{DATA_CRYSTAL_ROOT}/SRAM_map",
        "Persistent party, chapter, gold, tactics, and return locations",
    ),
    (
        "Map data format",
        "Dragon Warrior IV (NES)_Map Data Format - Data Crystal.htm",
        f"{DATA_CRYSTAL_ROOT}/Map_Data_Format",
        "Indoor map bitstream commands, dimensions, roofs, and smoothing",
    ),
    (
        "Map list",
        "Dragon Warrior IV (NES)_Map List - Data Crystal.htm",
        f"{DATA_CRYSTAL_ROOT}/Map_List",
        "Canonical names for maps 00 through 48",
    ),
    (
        "Text table",
        "Dragon Warrior IV (NES)_TBL - Data Crystal.htm",
        f"{DATA_CRYSTAL_ROOT}/TBL",
        "English character encoding used by names and dialogue",
    ),
    (
        "Tile behaviors",
        "Dragon Warrior IV (NES)_Tile Behaviors - Data Crystal.htm",
        f"{DATA_CRYSTAL_ROOT}/Tile_Behaviors",
        "Walkability and map-feature legend",
    ),
    (
        "Values and submaps",
        "Dragon Warrior IV (NES)_Values - Data Crystal.htm",
        f"{DATA_CRYSTAL_ROOT}/Values",
        "Chapters, tactics, time phases, items, and detailed submap names",
    ),
    (
        "RetroAchievements code notes",
        "Code Notes - Dragon Quest IV_ Michibikareshi Monotachi · RetroAchievements.htm",
        "https://retroachievements.org/game/4612",
        "Japanese-layout coordinates and independently observed live fields",
    ),
)


MAP_NAMES = (
    "Keeleon",
    "Santeem",
    "Burland",
    "Dire Palace",
    "Endor",
    "Bonmalmo",
    "Branca",
    "Soretta",
    "Gardenbur",
    "Stancia",
    "Aktemto",
    "Riverton",
    "Bazaar",
    "Mintos",
    "Tempe",
    "Frenor",
    "Aneaux",
    "Haville",
    "Izmit",
    "Surene",
    "Hometown",
    "Monbaraba",
    "Lakanaba",
    "Kievs",
    "Foxville",
    "Seaside Village",
    "Gottside",
    "Rosaville",
    "Secret Playground Entrance",
    "House of Prophecy",
    "Shrine to Endor",
    "Shrine northwest of Endor",
    "Woodsman's Shack",
    "Desert Inn",
    "Small Medal King",
    "Shrine North of Soretta",
    "Small Island Shack",
    "Royal Crypt Entrance",
    "Last Refuge",
    "SW Barrier Shrine",
    "SE Barrier Shrine",
    "NW Barrier Shrine",
    "Final Cave Entrance",
    "Travel Door near Riverton",
    "Shrine of Colossus Exterior",
    "Aktemto Mine",
    "Shrine of Breaking Waves",
    "Padaquea Cave",
    "Bakor's Hideout",
    "Sphere of Silence Cave",
    "Golden Bracelet Cave",
    "Secret Playground Dungeon",
    "Cascade Cave",
    "Final Cave",
    "Iron Safe Cave",
    "Cave of Betrayal",
    "Silver Statuette Cave",
    "Branca-Izmit Tunnel",
    "Branca-Endor Tunnel",
    "Royal Crypt Dungeon",
    "Necrosaro's Lair",
    "Zenithian Tower",
    "Outside Zenithia",
    "Birdsong Tower",
    "World Tree",
    "Loch Tower",
    "Lighthouse",
    "Konenber",
    "NE Barrier Shrine",
    "Necrosaro's Palace",
    "Zenithia",
    "Shrine of the Horn",
    "Shrine of Colossus Dungeon",
)

CHAPTERS = (
    "Chapter 1 · Ragnar",
    "Chapter 2 · Alena, Cristo, and Brey",
    "Chapter 3 · Taloon",
    "Chapter 4 · Mara and Nara",
    "Chapter 5 · Hero",
)

TACTICS = (
    "Normal",
    "Save MP",
    "Offensive",
    "Defensive",
    "Try Out",
    "Use No MP",
)

PARTY_NAMES = (
    "Hero",
    "Cristo",
    "Nara",
    "Mara",
    "Brey",
    "Taloon",
    "Ragnar",
    "Alena",
)

RETURN_LOCATIONS = (
    "Branca",
    "Endor",
    "Bonmalmo",
    "Aneaux",
    "Konenber",
    "Mintos",
    "Soretta",
    "Keeleon",
    "Haville",
    "Monbaraba",
    "Santeem",
    "Tempe",
    "Stancia",
    "Burland",
    "Izmit",
    "Gardenbur",
    "Rosaville",
    "Riverton",
    "Dire Palace",
    "Aktemto",
    "Gottside",
    "Zenithia",
    "Last Refuge",
)

TILE_BEHAVIORS = {
    0x00: "Walkable",
    0x01: "Poison swamp",
    0x02: "Barrier",
    0x04: "Treasure chest",
    0x05: "Pitfall",
    0x06: "Exit",
    0x07: "Exit",
    0x08: "Stairs up",
    0x09: "Stairs down",
    0x0A: "Travel door",
    0x0B: "Pitfall",
    0x0C: "Exit",
    0x10: "Up arrow",
    0x11: "Right arrow",
    0x12: "Down arrow",
    0x13: "Left arrow",
    0x24: "Opened big door",
    0x31: "Healing tile",
    0x80: "Wall",
    0x83: "Water",
    0x94: "Unlocked door",
    0x95: "Thief's Key door",
    0x96: "Magic Key door",
    0xA0: "Big door",
    0xA7: "Desk",
    0xA8: "Sign",
    0xA9: "Bookshelf",
    0xAB: "Chest of drawers",
}


class _SubmapTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_maps = False
        self.in_table = False
        self.in_cell = False
        self.row: list[str] = []
        self.cell: list[str] = []
        self.names: dict[tuple[int, int], str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id") == "Maps":
            self.in_maps = True
        elif self.in_maps and tag == "table" and not self.in_table:
            self.in_table = True
        elif self.in_table and tag in {"td", "th"}:
            self.in_cell = True
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag in {"td", "th"} and self.in_cell:
            self.row.append(" ".join("".join(self.cell).split()))
            self.in_cell = False
        elif self.in_table and tag == "tr":
            self._finish_row()
        elif self.in_table and tag == "table":
            self._finish_row()
            self.in_table = False
            self.in_maps = False

    def _finish_row(self) -> None:
        if len(self.row) >= 3:
            try:
                map_id = int(self.row[0].removeprefix("$"), 16)
                submap = int(self.row[1].removeprefix("$"), 16)
            except ValueError:
                pass
            else:
                if self.row[2]:
                    self.names[(map_id, submap)] = self.row[2]
        self.row = []


class _TreasureTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_treasure_list = False
        self.in_table = False
        self.in_cell = False
        self.row: list[str] = []
        self.cell: list[str] = []
        self.records: list[TreasureRecord] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id") == "Full_List":
            self.in_treasure_list = True
        elif self.in_treasure_list and tag == "table" and not self.in_table:
            self.in_table = True
        elif self.in_table and tag in {"td", "th"}:
            self.in_cell = True
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag in {"td", "th"} and self.in_cell:
            self.row.append(" ".join("".join(self.cell).split()))
            self.in_cell = False
        elif self.in_table and tag == "tr":
            self._finish_row()
        elif self.in_table and tag == "table":
            self._finish_row()
            self.in_table = False
            self.in_treasure_list = False

    def _finish_row(self) -> None:
        if len(self.row) >= 7 and self.row[0] == "Treasure":
            address = re.search(
                r"\$([0-9a-fA-F]{4})\s*#\s*([01_]{8,})",
                self.row[1],
            )
            try:
                map_id = int(self.row[3].removeprefix("$"), 16)
                submap = int(self.row[4].removeprefix("$"), 16)
            except ValueError:
                pass
            else:
                if (
                    address is not None
                    and self.row[5] != "..."
                    and self.row[6] != "..."
                ):
                    ram_address = int(address.group(1), 16)
                    mask = int(address.group(2).replace("_", ""), 2)
                    if 0x625D <= ram_address <= 0x6277 and mask.bit_count() == 1:
                        self.records.append(
                            TreasureRecord(
                                (ram_address - 0x625D) * 8
                                + (mask.bit_length() - 1),
                                map_id,
                                submap,
                                self.row[5],
                                self.row[6],
                            )
                        )
        self.row = []


def reference_sources(repository_root: Path | None) -> tuple[ReferenceSource, ...]:
    resources = repository_root / "resources" if repository_root is not None else None
    return tuple(
        ReferenceSource(
            title,
            filename,
            url,
            purpose,
            resources is not None and (resources / filename).is_file(),
        )
        for title, filename, url, purpose in REFERENCE_SOURCE_SPECS
    )


def load_submap_names(repository_root: Path | None) -> dict[tuple[int, int], str]:
    if repository_root is None:
        return {}
    path = repository_root / "resources" / REFERENCE_SOURCE_SPECS[8][1]
    try:
        document = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    parser = _SubmapTableParser()
    parser.feed(document)
    return parser.names


def load_treasure_records(
    repository_root: Path | None,
) -> tuple[TreasureRecord, ...]:
    if repository_root is None:
        return ()
    path = repository_root / "resources" / REFERENCE_SOURCE_SPECS[2][1]
    try:
        document = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    parser = _TreasureTableParser()
    parser.feed(document)
    return tuple(parser.records)


def map_title(
    map_id: int,
    submap: int,
    submap_names: dict[tuple[int, int], str] | None = None,
) -> str:
    if submap_names is not None and (map_id, submap) in submap_names:
        return submap_names[(map_id, submap)]
    base = MAP_NAMES[map_id] if 0 <= map_id < len(MAP_NAMES) else f"Map ${map_id:02X}"
    return base if submap == 0 else f"{base} · Submap {submap + 1}"


def time_of_day(value: int) -> str:
    if value <= 0x77:
        return "Day"
    if value <= 0x7B:
        return "Afternoon"
    if value <= 0x7F:
        return "Dusk"
    if value <= 0x83:
        return "Evening"
    if value <= 0xBF:
        return "Night"
    if value <= 0xC3:
        return "Pre-dawn"
    if value <= 0xC7:
        return "Dawn"
    if value <= 0xCB:
        return "Morning"
    return "Unknown"


def decode_text(data: bytes) -> str:
    punctuation = {
        0x65: "-",
        0x66: '"',
        0x67: '"',
        0x68: "'",
        0x69: "'",
        0x6A: "'",
        0x6B: "'",
        0x6C: ".'",
        0x6D: "?",
        0x6E: "!",
        0x6F: "-",
        0x71: ":",
        0x72: "...",
        0x75: "(",
        0x76: ")",
        0x77: ",",
        0x78: ".",
    }
    result = []
    for value in data:
        if value in {0xFF, 0x80, 0x81}:
            break
        if value == 0:
            result.append(" ")
        elif 0x01 <= value <= 0x0A:
            result.append(chr(ord("0") + value - 1))
        elif 0x0B <= value <= 0x24:
            result.append(chr(ord("a") + value - 0x0B))
        elif 0x25 <= value <= 0x3E:
            result.append(chr(ord("A") + value - 0x25))
        elif value in punctuation:
            result.append(punctuation[value])
    return "".join(result).strip()