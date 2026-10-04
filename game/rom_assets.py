from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import RLock
from typing import Callable

from PIL import Image, UnidentifiedImageError

from retroarch_overlay.models import MapLayer, MapOverlay, MapWaypoint

from .reference_data import TILE_BEHAVIORS, decode_text, item_name, map_title


MAX_MAP_DIMENSION = 128
MAX_DECODE_OPERATIONS = 1_000_000
MAP_COUNT = 0x49
MAP_INFO_POINTER_BANK = 0x17
MAP_INFO_POINTER_ADDRESS = 0xB08D
MAP_ROUTING_BANK = 0x08
MAP_ROUTING_ADDRESS = 0xB7F9
WORLD_POSITION_BANK = 0x0E
WORLD_POSITION_ADDRESS = 0xBE0B
WORLD_POSITION_LIMIT = 100
TILESET_BANK = 0x08
TILESET_ADDRESS = 0x8ADB
TILESET_COUNT = 51
TILE_DESCRIPTOR_ADDRESS = 0xA80D
TILE_INCREMENT_ADDRESS = 0xA1BB
EXPLICIT_PATTERN_ADDRESS = 0xA28D
ANIMATED_PATTERN_ADDRESS = 0xAEB7
PALETTE_BANK = 0x0E
PALETTE_OVERRIDE_MAP_ADDRESS = 0xBB53
PALETTE_OVERRIDE_VALUE_ADDRESS = 0xBB67
PALETTE_OVERRIDE_SUBMAP_ADDRESS = 0xBB75
PALETTE_NUMBER_ADDRESS = 0xBB88
PALETTE_SET_ADDRESS = 0xBC0A
PALETTE_COLOR_ADDRESS = 0xBCE2
GRAPHICS_BASES = {
    0: (0x0C, 0x8000),
    1: (0x0D, 0x7F01),
    2: (0x0D, 0x9E14),
}
# Verified live: US $0028 reads 0 on the overworld, and tileset 0 holds its
# water, grass, forest, mountain, town, and castle metatiles.
WORLD_TILESET = 0
NO_PALETTE_OVERRIDE_MAP = 0xFF
# Bank 1E search data (US layout). Furniture records are map, submap, x, y,
# item, flag byte relative to $6273, and flag bit mask. Search records are map,
# submap, x, y, and a handler value; values $A0-$AA are item searches whose low
# nibble selects a flag bit from $6272 and an item from the table at $BDB3.
HIDDEN_TABLE_BANK = 0x1E
FURNITURE_TABLE_ADDRESS = 0xBCED
SEARCH_TABLE_ADDRESS = 0xBF59
SEARCH_ITEM_TABLE_ADDRESS = 0xBDB3
CHEST_DIRECTORY_ADDRESS = 0xBDC2
CHEST_VALUE_ADDRESS = 0xBEB9
CHEST_DIRECTORY_LIMIT = 82
SPECIAL_CHEST_VALUES = frozenset((0xFF, 0xFE, 0xFD, 0xEF, 0xEE, 0xE3, 0xE2, 0xE0))
FURNITURE_FLAG_BYTE = 22
SEARCH_FLAG_BYTE = 21
HIDDEN_TABLE_LIMIT = 64
WORLD_PALETTE_BANK = 0x1E
WORLD_PALETTE_ADDRESS = 0xA2E3
WORLD_PALETTE_SIZE = 12
WORLD_MAP_SPECS = {
    "world": ("Main World", "World", 0x0B, 0xA590, 256, 256, 16, 0),
    "gottside": ("Gottside", "Gottside", 0x0B, 0xAB65, 64, 64, 16, 1),
    "underworld": ("Underworld", "Underworld", 0x0B, 0xAE89, 64, 54, 16, 3),
}
WORLD_KEY_BY_SELECTOR = {0: "world", 1: "gottside", 3: "underworld"}
WORLD_MARKER_BY_TILE = {
    0x00: "water-location",
    0x03: "settlement",
    0x04: "special-location",
    0x08: "tunnel",
    0x0B: "cave",
    0x0C: "shrine",
    0x10: "town",
    0x11: "tower",
    0x12: "castle",
}
WORLD_MARKER_OVERRIDES = {
    ("underworld", 0x07): "palace",
    ("underworld", 0x12): "palace",
    ("underworld", 0x1D): "lair",
    ("underworld", 0x1E): "lair",
}
# Bank 08 $B675 lists $08 $09 $26 $25 $0F $0A $06 as the walking-transition
# behaviors; $07 and $0C are the remaining exit markers drawn on the atlas.
ENTRANCE_BEHAVIORS = frozenset((0x06, 0x07, 0x08, 0x09, 0x0A, 0x0C, 0x0F, 0x25, 0x26))
PITFALL_BEHAVIORS = frozenset((0x05, 0x0B))
DOOR_BEHAVIORS = frozenset((0x94, 0x95, 0x96, 0x97, 0xA0))
HAZARD_DETAILS = {
    0x01: "Damages the party each step",
    0x02: "Damages the party each step",
    0x05: "Drops you to the floor below",
    0x0B: "Drops you to the floor below",
    0x10: "Pushes you north",
    0x11: "Pushes you east",
    0x12: "Pushes you south",
    0x13: "Pushes you west",
}
DOOR_KEY_DETAILS = {
    "thief-door": "Needs the Thief's Key",
    "magic-door": "Needs the Magic Key",
    "final-door": "Needs the Final Key",
}


def _rom_region(full_hash: str, content_hash: str) -> str:
    full_regions = {
        "e45105e8f82d8aa29b39260fd531498d": "US",
        "65be0515383394a096084d4921c353f4": "Japan",
    }
    content_regions = {
        "d8a1d610c93b96ad98e55e09dfcc7533": "US",
    }
    return full_regions.get(
        full_hash,
        content_regions.get(content_hash, "Unknown or patched"),
    )


def _extractor_version(*renderers: object) -> str:
    paths = {Path(__file__)}
    for renderer in renderers:
        module = inspect.getmodule(renderer)
        path = getattr(module, "__file__", None)
        if path:
            paths.add(Path(path))
    digest = hashlib.sha256()
    for item in sorted(paths, key=str):
        try:
            digest.update(item.read_bytes())
        except OSError:
            digest.update(str(item).encode("utf-8"))
    return digest.hexdigest()[:12]


def area_key(map_id: int, submap: int) -> int:
    return (map_id << 8) | submap


def _world_destination_marker(key: str, tile: int) -> str:
    return WORLD_MARKER_OVERRIDES.get(
        (key, tile),
        WORLD_MARKER_BY_TILE.get(tile, "location"),
    )


@dataclass(frozen=True, slots=True)
class AreaMapDescriptor:
    map_id: int
    submap: int
    tileset: int
    width: int
    height: int
    data_bank: int
    data_offset: int

    @property
    def key(self) -> int:
        return area_key(self.map_id, self.submap)


@dataclass(frozen=True, slots=True)
class AreaGraphics:
    metatiles: tuple[tuple[int, int, int, int], ...]
    attributes: tuple[int, ...]
    patterns: tuple[bytes, ...]
    palette: tuple[int, ...]
    behaviors: tuple[int, ...]
    smoothing: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MonsterDefinition:
    monster_id: int
    name: str
    max_hp: int
    max_mp: int
    agility: int
    attack: int
    defense: int
    experience: int
    gold: int
    drop_item_id: int | None
    drop_denominator: int | None = None
    resistances: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FormationChance:
    label: str
    monster_ids: tuple[int, ...]
    chance: int
    fixed_group: bool


@dataclass(slots=True)
class _Reachability:
    source: bytes | None
    behaviors: bytes
    reached: set[tuple[int, int]]
    positions: set[tuple[int, int]]
    seeded: bool


def _flood_reachable(behaviors: bytes, width: int, height: int,
                     reached: set[tuple[int, int]], seeds: set[tuple[int, int]]) -> None:
    stack = [(x, y) for x, y in seeds if (x, y) not in reached
             and 0 <= x < width and 0 <= y < height
             and (not behaviors[y * width + x] & 0x80 or behaviors[y * width + x] in DOOR_BEHAVIORS)]
    reached.update(stack)
    while stack:
        x, y = stack.pop()
        if behaviors[y * width + x] in PITFALL_BEHAVIORS:
            continue
        for step_x, step_y in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if not 0 <= step_x < width or not 0 <= step_y < height or (step_x, step_y) in reached:
                continue
            behavior = behaviors[step_y * width + step_x]
            if not behavior & 0x80 or behavior in DOOR_BEHAVIORS:
                reached.add((step_x, step_y))
                stack.append((step_x, step_y))


def _selection_counts(weights: tuple[int, ...]) -> tuple[int, ...]:
    total = sum(weights)
    if not weights or not 0 < total <= 255:
        return ()
    counts = [0] * len(weights)
    for random_byte in range(256):
        roll = random_byte if total == 255 else random_byte * total >> 8
        cumulative = 0
        for index, weight in enumerate(weights):
            cumulative += weight
            if cumulative >= roll:
                counts[index] += 1
                break
    return tuple(counts)


class _BitReader:
    def __init__(self, data: bytes, offset: int) -> None:
        self._data = data
        self._bit_offset = offset * 8

    def read(self, count: int) -> int:
        if count < 0 or self._bit_offset + count > len(self._data) * 8:
            raise ValueError("Truncated DW4 map bitstream")
        value = 0
        for _ in range(count):
            byte_offset, bit = divmod(self._bit_offset, 8)
            value = (value << 1) | ((self._data[byte_offset] >> (7 - bit)) & 1)
            self._bit_offset += 1
        return value


class MdecDecoder:
    def __init__(self, data: bytes, offset: int) -> None:
        if offset < 0 or offset + 3 > len(data):
            raise ValueError("DW4 map offset is outside the ROM")
        self._reader = _BitReader(data, offset)
        self.width = self._reader.read(8)
        self.height = self._reader.read(8)
        header = self._reader.read(8)
        if not 0 < self.width <= MAX_MAP_DIMENSION or not 0 < self.height <= MAX_MAP_DIMENSION:
            raise ValueError(f"Invalid DW4 map dimensions: {self.width}x{self.height}")
        self._pointer_bits = (self.width * self.height - 1).bit_length()
        self._tile_bits = ((header >> 6) & 0x03) + 2
        self.border_tile = header & 0x1F
        clear_tile = self._reader.read(self._tile_bits)
        self.tiles = [[clear_tile for _ in range(self.width)] for _ in range(self.height)]
        self._operations = 0

    def decode(self) -> tuple[tuple[int, ...], ...]:
        self._run(roof_mode=False)
        roof_bits = self._reader.read(2)
        if roof_bits:
            self._tile_bits = roof_bits
            self._run(roof_mode=True)
        return tuple(tuple(row) for row in self.tiles)

    def _run(self, roof_mode: bool) -> None:
        brush = (0,)
        large = False
        stack: list[tuple[int, int, int]] = []
        while True:
            command = self._reader.read(2)
            if command == 0:
                brush = (self._reader.read(self._tile_bits),)
                large = False
                command = self._reader.read(2)
                if command:
                    pass
                elif self._reader.read(1):
                    return
                else:
                    brush += tuple(self._reader.read(self._tile_bits) for _ in range(3))
                    large = True
                    continue
            if command == 1:
                first_x, first_y = self._point()
                second_x, second_y = self._point()
                left, right = sorted((first_x, second_x))
                top, bottom = sorted((first_y, second_y))
                columns, rows = right - left, bottom - top
                if large:
                    columns //= 2
                    rows //= 2
                stride = 1 if roof_mode else (2 if large else 1)
                for row in range(rows + 1):
                    for column in range(columns + 1):
                        self._emit(
                            left + column * stride,
                            top + row * stride,
                            brush,
                            large and not roof_mode,
                            roof_mode,
                        )
                continue
            if command == 2:
                x, y = self._point()
                self._emit(x, y, brush, large, roof_mode)
                direction = self._reader.read(2)
                while True:
                    if self._reader.read(1):
                        operation = self._reader.read(2)
                        if operation == 0:
                            direction = (direction + 1) & 3
                        elif operation == 1:
                            direction = (direction - 1) & 3
                        elif operation == 2:
                            stack.append((x, y, direction))
                            direction = (direction + (1 if self._reader.read(1) == 0 else -1)) & 3
                        elif self._reader.read(1) == 0:
                            x, y = self._point()
                            self._emit(x, y, brush, large, roof_mode)
                            direction = self._reader.read(2)
                            continue
                        elif stack:
                            x, y, direction = stack.pop()
                            continue
                        else:
                            break
                    stride = 2 if large else 1
                    if direction == 0:
                        y -= stride
                    elif direction == 1:
                        x += stride
                    elif direction == 2:
                        y += stride
                    else:
                        x -= stride
                    self._emit(x, y, brush, large, roof_mode)
                continue
            if command == 3:
                x, y = self._point()
                self._emit(x, y, brush, large, roof_mode)

    def _point(self) -> tuple[int, int]:
        pointer = self._reader.read(self._pointer_bits)
        return pointer % self.width, pointer // self.width

    def _emit(
        self,
        x: int,
        y: int,
        brush: tuple[int, ...],
        large: bool,
        roof_mode: bool,
    ) -> None:
        points = ((x, y, brush[0]),)
        if large:
            points = (
                (x, y, brush[0]),
                (x + 1, y, brush[1]),
                (x, y + 1, brush[2]),
                (x + 1, y + 1, brush[3]),
            )
        for target_x, target_y, tile in points:
            self._operations += 1
            if self._operations > MAX_DECODE_OPERATIONS:
                raise ValueError("DW4 map operation limit exceeded")
            if not 0 <= target_x < self.width or not 0 <= target_y < self.height:
                continue
            if roof_mode:
                self.tiles[target_y][target_x] = (self.tiles[target_y][target_x] & 0x1F) | (tile << 5)
            else:
                self.tiles[target_y][target_x] = tile


def _hidden_reward(item_id: int) -> str:
    name = item_name(item_id)
    return "Hidden item" if name.startswith("Item $") else name


def _gold_reward(value: int) -> str:
    return f"{(value & 0x7F) * 40:,} Gold"


def _chest_reward(value: int) -> tuple[str, str]:
    if value < 0x80:
        return item_name(value), ""
    if value not in SPECIAL_CHEST_VALUES:
        return _gold_reward(value), ""
    if value == 0xFF:
        return "Empty chest", "Empty"
    if value in {0xFE, 0xFD}:
        return ("Mimic chest" if value == 0xFE else "Man-eater chest"), "Trap: starts a battle"
    item_id = {0xEF: 0x52, 0xEE: 0x6B, 0xE3: 0x67, 0xE2: 0x7E, 0xE0: 0x6F}[value]
    return item_name(item_id), "Story reward"


def _msb_flag(flags: bytes, index: int) -> bool:
    byte_index, bit = divmod(index, 8)
    return byte_index < len(flags) and bool(flags[byte_index] & (0x80 >> bit))


def decode_world_point(data: bytes, offset: int, x: int, middle_entry: int = 0,
                       right_entry: int = 0) -> int:
    if not 0 <= x < 256:
        raise ValueError("DW4 world point is outside the native byte coordinate")
    reverse = bool(x & 0x40)
    entry = right_entry if x >= 0xC0 else middle_entry if x >= 0x40 else 0
    cursor = offset + entry
    position = (255 if x & 0x80 else 127) if reverse else (127 if x & 0x80 else -1)
    for _ in range(256):
        if reverse:
            cursor -= 1
        if not 0 <= cursor < len(data):
            raise ValueError("Truncated DW4 world-map point scan")
        value = data[cursor]
        terrain, run = value >> 5, (value & 0x1F) + 1
        if terrain == 7 and value & 0x1F >= 8:
            terrain, run = value - 0xE0, 1
        position = position - run if reverse else position + run
        if position < x if reverse else position >= x:
            return terrain
        if not reverse:
            cursor += 1
    raise ValueError("DW4 world-map point scan exceeded its native row bound")


def decode_world_row(data: bytes, offset: int, width: int) -> tuple[int, ...]:
    tiles = []
    while len(tiles) < width:
        if offset >= len(data):
            raise ValueError("Truncated DW4 world-map row")
        value = data[offset]
        offset += 1
        terrain = value >> 5
        run_length = (value & 0x1F) + 1
        if terrain == 7 and (value & 0x1F) >= 8:
            terrain = value - 0xE0
            run_length = 1
        tiles.extend((terrain,) * min(run_length, width - len(tiles)))
    return tuple(tiles)


@dataclass(frozen=True, slots=True)
class HiddenTreasure:
    map_id: int
    submap: int
    x: int
    y: int
    flag_index: int
    reward: str
    description: str

    def is_open(self, treasure_flags: bytes) -> bool:
        byte_index, bit = divmod(self.flag_index, 8)
        return byte_index < len(treasure_flags) and bool(
            treasure_flags[byte_index] & (1 << bit)
        )


@dataclass(frozen=True, slots=True)
class FeatureTemplate:
    waypoint: MapWaypoint
    flag_index: int | None = None
    least_significant_first: bool = False
    behavior: int | None = None
    reward_handler: int | None = None


@dataclass(frozen=True, slots=True)
class CollectibleDefinition:
    flag_byte: int
    flag_mask: int
    item_id: int | None
    reward: str

    def collected(self, flags: bytes) -> bool | None:
        return bool(flags[self.flag_byte] & self.flag_mask) if self.flag_byte < len(flags) else None


@dataclass(frozen=True, slots=True)
class ExitRoute:
    source_key: int
    destination_key: int
    x: int | None
    y: int | None
    width: int
    height: int
    destination_x: int | None
    destination_y: int | None
    destination_world: str = ""
    direction: int | None = None
    arrival_note: str = ""

    @property
    def layer_key(self) -> str:
        return self.destination_world or f"area-{self.destination_key >> 8:02x}-{self.destination_key & 0xFF:02x}"


@dataclass(frozen=True, slots=True)
class ConditionalSearch:
    x: int
    y: int
    item_id: int | None
    handler: int
    flag_mask: int = 0
    required_facing: int | None = None


class DragonWarrior4RomAssets:
    def __init__(
        self,
        rom_path: Path,
        state_directory: Path,
        area_renderer: Callable[[tuple[tuple[int, ...], ...], AreaGraphics, Path], None],
        world_renderer: Callable[[tuple[tuple[int, ...], ...], AreaGraphics, Path], None],
        submap_names: dict[tuple[int, int], str] | None = None,
    ) -> None:
        if rom_path.stat().st_size > 0x100000:
            raise ValueError("Configured DW4 ROM exceeds the supported cartridge size")
        data = rom_path.read_bytes()
        if len(data) < 16 or data[:4] != b"NES\x1a":
            raise ValueError("Configured file is not an iNES ROM")
        nes2 = data[7] & 0x0C == 8
        mapper = (data[6] >> 4) | (data[7] & 0xF0) | ((data[8] & 0x0F) << 8 if nes2 else 0)
        if mapper != 1 or data[5] or (nes2 and (data[9] & 0x0F or data[8] >> 4)):
            raise ValueError("DW4 requires the supported MMC1 cartridge with CHR RAM")
        trainer_size = 512 if data[6] & 0x04 else 0
        self._prg_offset = 16 + trainer_size
        prg_size = data[4] * 0x4000
        if prg_size != 0x80000 or self._prg_offset + prg_size > len(data):
            raise ValueError("Dragon Warrior IV requires 32 16-KiB PRG pages")
        self._data = data
        self.content_hash = hashlib.md5(
            data[self._prg_offset:self._prg_offset + prg_size],
            usedforsecurity=False,
        ).hexdigest()
        full_hash = hashlib.md5(data, usedforsecurity=False).hexdigest()
        self.region = _rom_region(full_hash, self.content_hash)
        self.extractor_version = _extractor_version(area_renderer, world_renderer)
        versions = state_directory / "generated-assets" / self.content_hash
        self.cache_directory = versions / f"v{self.extractor_version}"
        self._area_renderer = area_renderer
        self._world_renderer = world_renderer
        self._submap_names = submap_names or {}
        self._descriptors = self._index_area_maps()
        self._descriptor_by_key = {item.key: item for item in self._descriptors}
        self._area_cache: dict[int, tuple[tuple[tuple[int, ...], ...], AreaGraphics]] = {}
        self._hidden_treasures: tuple[HiddenTreasure, ...] | None = None
        self._name_cache: dict[tuple[int, int], str] = {}
        self._cache_lock = RLock()
        self._feature_templates: dict[int, tuple[FeatureTemplate, ...]] = {}
        self._collectible_catalog: tuple[CollectibleDefinition, ...] | None = None
        self._room_classes: dict[int, tuple[int, ...]] = {}
        self._diagnostics: dict[str, str] = {}
        self._exit_routes: tuple[ExitRoute, ...] | None = None
        self._display_layers_cache: dict[str, MapLayer] = {}
        self._reachability: dict[int, _Reachability] = {}
        self._arrivals: dict[int, tuple[tuple[int, int], ...]] | None = None

    @property
    def area_maps(self) -> tuple[AreaMapDescriptor, ...]:
        return self._descriptors

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(getattr(self, "_diagnostics", {}).values())

    def _record_diagnostic(self, identity: str, detail: str) -> None:
        if not hasattr(self, "_diagnostics"):
            self._diagnostics = {}
        self._diagnostics[identity] = detail

    def _place(self, map_id: int, submap: int) -> str:
        return map_title(map_id, submap, getattr(self, "_submap_names", None))

    def has_area(self, map_id: int, submap: int) -> bool:
        return area_key(map_id, submap) in self._descriptor_by_key

    def descriptor(self, map_id: int, submap: int) -> AreaMapDescriptor | None:
        return self._descriptor_by_key.get(area_key(map_id, submap))

    def encounter_pool(self, chapter: int, world: int, x: int, y: int,
                       time_value: int, travel_mode: int = 0) -> tuple[int, tuple[tuple[str, int], ...]] | None:
        if self.region != "US" or travel_mode != 0 or world not in WORLD_KEY_BY_SELECTOR:
            return None
        if chapter == 4 and world:
            zone = (0x35 if y < 12 else 0x34) if world == 1 else 0x36
        else:
            pointer_address = 0xA245 if chapter == 4 else 0xA243 if chapter == 2 else 0xA241
            grid = int.from_bytes(self._cpu_bytes(0x18, pointer_address, 2), "little")
            zone = self._cpu_byte(0x18, grid + (y & 0xF0) + (x >> 4)) & 0x3F
        return self._formation_pool(zone, 0x3FBE if time_value >= 0x78 else 0x1BEF)

    def land_encounter_threshold(self, zone: int, terrain: int, time_value: int, step_count: int,
                                 repel_count: int, party_strength: int, scent_count: int) -> tuple[int | None, str]:
        if self.region != "US" or not 0 <= zone < 64:
            return None, "Encounter rate unavailable"
        if any(not 0 <= value <= 255 for value in (terrain, time_value, step_count, repel_count, party_strength, scent_count)):
            raise ValueError("Invalid native encounter threshold input")
        if terrain >= 8:
            return 0, "No random encounters on this terrain"
        pointer = int.from_bytes(self._cpu_bytes(0x18, 0xA239, 2), "little")
        control, repel_strength = self._cpu_bytes(0x18, pointer + zone * 16, 2)
        base = self._cpu_byte(0x18, 0xA340 + (control >> 5))
        factor = self._cpu_byte(0x18, 0xA33D + step_count) if step_count < 3 else 16
        rate = base * factor
        coefficient = self._cpu_byte(0x18, 0xA27B + terrain) if time_value < 0x78 else 0
        if not coefficient:
            coefficient = self._cpu_byte(0x18, 0xA283 + terrain)
        rate = ((rate * coefficient) & 0xFFFF) >> 8
        remaining = repel_count & 0x7F
        if remaining == 1:
            return 0, "Repel is active and wears off next step"
        if remaining > 1:
            difference = party_strength - repel_strength
            if difference >= 5:
                return 0, "Repel is keeping monsters away"
            if difference > 0:
                rate = (rate * self._cpu_byte(0x18, 0xA348 + difference - 1)) >> 8
        if scent_count:
            rate = min(256, rate * 4)
        return rate, ""

    def indoor_encounter_pool(self, chapter: int, map_id: int, submap: int) -> tuple[int, tuple[tuple[str, int], ...]] | None:
        if self.region != "US" or not self.has_area(map_id, submap):
            return None
        directory = 0xA23D if chapter == 4 else 0xA23B
        pointer = int.from_bytes(self._cpu_bytes(0x18, directory, 2), "little")
        for _ in range(MAP_COUNT):
            current = self._cpu_byte(0x18, pointer)
            if current == 0xFF:
                return None
            if current >= MAP_COUNT:
                raise ValueError("Invalid DW4 indoor encounter map identity")
            count = self._cpu_byte(0x18, 0xA474 + current)
            if not 0 < count <= MAX_MAP_DIMENSION:
                raise ValueError("Invalid DW4 indoor encounter stride")
            if current == map_id:
                if not 0 <= submap < count:
                    return None
                zone = self._cpu_byte(0x18, pointer + submap + 1)
                return None if zone == 0xFF else self._formation_pool(zone, 0x3FFF)
            pointer += count + 1
        raise ValueError("DW4 indoor encounter directory is unterminated")

    def _formation_slots(self, zone: int, mask: int) -> tuple[FormationChance, ...]:
        """One entry per selectable formation slot; chance holds the slot's raw weight."""
        pointer = int.from_bytes(self._cpu_bytes(0x18, 0xA239, 2), "little")
        record = self._cpu_bytes(0x18, pointer + zone * 16, 16)
        weights = self._cpu_bytes(0x18, 0xA28D + ((record[0] >> 2) & 7) * 18, 14)
        slots = []
        for ordinal, monster_id in enumerate(record[2:]):
            if monster_id == 0xFF or not mask & (1 << ordinal):
                continue
            if ordinal >= 12:
                group_pointer = int.from_bytes(self._cpu_bytes(0x18, 0xA237, 2), "little")
                group = self._cpu_bytes(0x18, group_pointer + monster_id * 6, 6)
                members = tuple(identifier for identifier in group[2:] if identifier != 0xFF)
                names = tuple(self.monster_name(identifier) for identifier in members)
                if not names or any(name is None for name in names):
                    raise ValueError("DW4 predefined formation contains an unknown monster")
                label = " + ".join(f"{name} x{names.count(name)}" if names.count(name) > 1 else name
                                   for name in dict.fromkeys(names))
                slots.append(FormationChance(label, members, weights[ordinal], True))
                continue
            name = self.monster_name(monster_id)
            if name:
                slots.append(FormationChance(name, (monster_id,), weights[ordinal], False))
        return tuple(slots)

    def _formation_entries(self, zone: int, mask: int) -> tuple[tuple[str, int], ...]:
        return tuple((slot.label, slot.chance) for slot in self._formation_slots(zone, mask))

    def _formation_pool(self, zone: int, mask: int) -> tuple[int, tuple[tuple[str, int], ...]]:
        pool = {}
        for name, weight in self._formation_entries(zone, mask):
            if weight:
                pool[name] = pool.get(name, 0) + weight
        return zone, tuple(pool.items())

    def formation_entry_chances(self, zone: int, mask: int) -> tuple[tuple[str, int], ...]:
        entries = self._formation_entries(zone, mask)
        chances = {}
        for (name, _), count in zip(entries, _selection_counts(tuple(weight for _, weight in entries))):
            if count:
                chances[name] = chances.get(name, 0) + count
        return tuple(chances.items())

    def formation_chances(self, zone: int, mask: int) -> tuple[FormationChance, ...]:
        slots = self._formation_slots(zone, mask)
        merged: dict[tuple[bool, tuple[int, ...]], FormationChance] = {}
        for slot, count in zip(slots, _selection_counts(tuple(slot.chance for slot in slots))):
            if not count:
                continue
            identity = slot.fixed_group, slot.monster_ids
            previous = merged.get(identity)
            merged[identity] = replace(slot, chance=count + (previous.chance if previous is not None else 0))
        return tuple(sorted(merged.values(), key=lambda entry: -entry.chance))

    def experience_threshold(self, growth_id: int, level: int) -> int | None:
        if self.region != "US":
            return None
        from .growth import experience_threshold
        return experience_threshold(self._cpu_bytes, growth_id, level)

    def spell_milestones(self, character_id: int) -> tuple[tuple[str, int, bool], ...]:
        if self.region != "US" or character_id & 7 >= 5 or not 0 <= character_id <= 8:
            return ()
        character_id &= 7
        mask_pointer = int.from_bytes(self._cpu_bytes(0x12, 0xA10B + character_id * 2, 2), "little")
        level_pointer = int.from_bytes(self._cpu_bytes(0x12, 0xA117 + character_id * 2, 2), "little")
        mask = int.from_bytes(self._cpu_bytes(0x12, mask_pointer, 8), "little")
        levels = self._cpu_bytes(0x12, level_pointer, mask.bit_count())
        result = []
        ordinal = 0
        for spell_id in range(64):
            if not mask & (1 << spell_id):
                continue
            descriptor = levels[ordinal]
            ordinal += 1
            name = self.indexed_name(0, spell_id)
            if name:
                result.append((name, descriptor & 0x7F, bool(descriptor & 0x80)))
        return tuple(sorted(result, key=lambda value: (value[1], value[0])))

    def monster_vitals(self, monster_id: int) -> tuple[int, int] | None:
        if self.region != "US" or not 0 <= monster_id < 214:
            return None
        record = self._cpu_bytes(0x18, 0x8046 + monster_id * 22, 22)
        maximum_hp = record[4] | ((record[15] & 0x03) << 8)
        return 1200 if maximum_hp == 0x03FF else maximum_hp, record[3]

    def arena_program(self) -> bytes:
        if self.region != "US":
            raise ValueError("Arena prediction requires the verified US ROM")
        return self._data[self._prg_offset:self._prg_offset + 0x80000]

    def monster_name(self, monster_id: int) -> str | None:
        return self.indexed_name(9, monster_id) if self.region == "US" and 0 <= monster_id < 214 else None

    def monster_definition(self, monster_id: int) -> MonsterDefinition | None:
        vitals = self.monster_vitals(monster_id)
        if vitals is None:
            return None
        record = self._cpu_bytes(0x18, 0x8046 + monster_id * 22, 22)
        drop = record[8] & 0x7F
        rank = record[20] & 7
        threshold = self._cpu_byte(0x12, 0x9285 + rank)
        denominator = 1 if rank == 0 else (256 // threshold) * (16 if rank == 7 else 1)
        resistance_names = ("Susceptible", "Partial resistance", "Strong resistance", "Immune")
        resistances = []
        for spell_id in range(64):
            category = self._cpu_byte(0x13, 0xB80B + spell_id) & 0x1F
            if category >= 15:
                continue
            selector = self._cpu_byte(0x13, 0xB736 + category)
            resistance = (record[15 + selector // 4] >> ((selector & 3) * 2)) & 3
            name = self.indexed_name(0, spell_id)
            if name:
                resistances.append((name, resistance_names[resistance]))
        return MonsterDefinition(
            monster_id, self.monster_name(monster_id) or "Unknown monster", *vitals,
            record[2], record[5] | ((record[16] & 3) << 8),
            record[6] | ((record[17] & 3) << 8), int.from_bytes(record[:2], "little"),
            record[7] | ((record[18] & 3) << 8), None if drop == 0x7F else drop,
            None if drop == 0x7F else denominator, tuple(resistances),
        )

    def guest_profile(self, monster_id: int) -> tuple[str, int, int] | None:
        vitals = self.monster_vitals(monster_id)
        if vitals is None:
            return None
        name = self.indexed_name(7, monster_id - 0xC5 + 7) if 0xC5 <= monster_id <= 0xCD else self.monster_name(monster_id)
        return (name or "Guest", *vitals)

    def town_shops(self, map_id: int, time_value: int = 0, special_stock: bytes = b"\0\0\0") -> tuple[tuple[int, int, tuple[int, ...]], ...]:
        if self.region != "US":
            return ()
        shops = []
        pointers = tuple(int.from_bytes(self._cpu_bytes(0x18, 0x802C + index * 2, 2), "little")
                         for index in range(3))
        for shop_type in range(1, 4):
            pointer = pointers[shop_type - 1]
            end = min((address for address in (*pointers, 0xB5C2) if address > pointer), default=0xB5C2)
            for _ in range(128):
                if pointer >= end:
                    break
                entry_map = self._cpu_byte(0x18, pointer)
                if entry_map == 0xFF:
                    break
                submap = self._cpu_byte(0x18, pointer + 1)
                pointer += 2
                items = []
                for _ in range(8):
                    if pointer >= end:
                        raise ValueError("DW4 shop stock crosses its directory boundary")
                    value = self._cpu_byte(0x18, pointer)
                    pointer += 1
                    if value & 0x7F != 0x7F:
                        items.append(value & 0x7F)
                    if value & 0x80:
                        break
                else:
                    raise ValueError("DW4 shop stock is unterminated")
                if entry_map != map_id:
                    continue
                if (map_id, submap, shop_type) == (0x16, 0, 1):
                    additions = self._cpu_bytes(0x15, 0xA479, 3)
                    items.extend(item for item, count in zip(additions, special_stock[:3]) if count)
                if (map_id, submap, shop_type) == (9, 0, 1) and time_value < 0x78:
                    items = [6, 0x23, 7, 0x10]
                if items:
                    shops.append((submap, shop_type, tuple(dict.fromkeys(items))))
            else:
                raise ValueError("DW4 shop directory exceeds its native bounds")
        return tuple(shops)

    def equipment_bonus(self, item_id: int) -> int:
        if self.region != "US" or not 0 <= item_id <= 0x50:
            raise ValueError("Unsupported DW4 equipment identity")
        return self._cpu_byte(0x10, 0x9DE0 + item_id)

    def equipment_traits(self, item_id: int) -> tuple[int, int, int]:
        if self.region != "US" or not 0 <= item_id <= 0x50:
            raise ValueError("Unsupported DW4 equipment identity")
        action = self._cpu_byte(0x10, 0x8D63 + item_id)
        return (self._cpu_byte(0x10, 0x8CE4 + item_id) & 0xFC, action & 0x3F, action & 0xC0)

    def equipment_passives(self, item_id: int) -> tuple[str, ...]:
        if self.region != "US":
            return ()
        if item_id in {0x0E, 0x15}:
            targets = (0x75, 0x5C, 0xA8) if item_id == 0x0E else tuple(self._cpu_bytes(0x11, 0xA73F, 8))
            names = ", ".join(name for name in map(self.monster_name, targets) if name) or "certain monsters"
            return (f"Always deals 2 damage to {names}" if item_id == 0x0E else f"Deals 1.5x damage to {names}",)
        return {
            0x0F: ("Deals 1 damage, with about a 1 in 8 instant-kill chance against susceptible enemies",),
            0x12: ("Misses about 2 attacks in 3",),
            0x13: ("Hurts you for a quarter of damage dealt, rounded down, plus 1 HP",),
            0x16: ("Attacks again if the target survives the first hit",),
            0x1C: ("Heals you for a quarter of damage dealt, rounded down, plus 1 HP",),
            0x33: ("Dodges about 1 in 6 physical hits",),
            0x36: ("Absorbs the MP of about 1 in 8 spells cast at you, while you have MP remaining",),
            0x38: ("Half the time, returns about a quarter of an ordinary physical hit to the attacker",),
            0x3C: ("Agility drops to 0",),
            0x1F: ("Defense drops to 0",),
            0x41: ("Returns a quarter of attack-spell damage, rounded down, plus 1 HP to the caster",),
            0x50: ("Doubles agility",),
        }.get(item_id, ())

    def equipment_protection(self, item_id: int) -> tuple[tuple[str, int], ...]:
        if self.region != "US" or not 0 <= item_id <= 0x50:
            return ()
        identities = self._cpu_bytes(0x13, 0xB540, 7)
        if item_id not in identities:
            return ()
        ordinal = identities.index(item_id)
        packed = self._cpu_byte(0x13, 0xB547 + ordinal // 2)
        mask = (packed >> (4 if ordinal & 1 else 0)) & 0x0F
        categories = ("Fire/explosion damage", "Ice damage", "Wind damage", "Breath damage")
        return tuple((category, 0xAA) for bit, category in enumerate(categories) if mask & (1 << bit))

    def equipment_eligible(self, item_id: int, character_id: int, hero_female: bool = False) -> bool:
        if self.region != "US" or not 0 <= character_id < 8 or not 0 <= item_id < 0x53:
            return False
        if item_id in {0x30, 0x31, 0x3B, 0x4D} and character_id not in {2, 3, 7}:
            if character_id != 0 or not hero_female:
                return False
        return bool(self._cpu_byte(0x10, 0x8C65 + item_id) & (1 << character_id))

    def arena_payout(self, amount: int, integer: int, fraction: int) -> int | None:
        if self.region != "US" or not 0 <= amount <= 50 or not 0 <= integer <= 255 or not 0 <= fraction < 10:
            return None
        coefficient = self._cpu_byte(0x18, 0xA97B + fraction)
        return amount * integer + ((amount * coefficient + 128) >> 8)

    def item_price(self, item_id: int, map_id: int, submap: int) -> int:
        if self.region != "US" or not 0 <= item_id < 0x7F:
            raise ValueError("Unsupported DW4 price identity")
        if map_id == 0x18 and item_id in {6, 0x79}:
            return 10 if item_id == 6 else 2
        if map_id == 0x22:
            return {0x17: 1, 0x4E: 4, 0x1C: 6}.get(item_id, 20)
        if (map_id, submap) == (4, 1):
            for offset in range(0, 18, 3):
                record = self._cpu_bytes(0x15, 0xB34D + offset, 3)
                if record[0] == item_id:
                    return int.from_bytes(record[1:3], "little")
        flags = self._cpu_byte(0x10, 0x8CE4 + item_id)
        return (self._cpu_byte(0x10, 0x8DE2 + item_id) & 0x7F) * (10 ** (flags & 3))

    def return_destinations(self, chapter: int, flags: bytes) -> tuple[tuple[int, str], ...]:
        if self.region != "US":
            return ()
        address = 0x95C3 if chapter >= 4 else 0x95B4
        result = []
        for index in range(40):
            map_id = self._cpu_byte(0x10, address + index)
            if map_id == 0xFF:
                return tuple(result)
            byte_index, bit = divmod(index, 8)
            if byte_index < len(flags) and flags[byte_index] & (1 << bit):
                result.append((map_id, map_title(map_id, 0, self._submap_names)))
        raise ValueError("DW4 Return destination directory is unterminated")

    def map_actor_roles(self, bank: int, pointer: int, time_value: int) -> tuple[tuple[str, str], ...]:
        if self.region != "US" or bank not in {5, 0x1C} or not 0x8000 <= pointer < 0xBFD8:
            return ()
        roles = []
        for _ in range(128):
            if not 0x8000 <= pointer < 0xBFD8:
                raise ValueError("DW4 entity record leaves its data bank")
            flags = self._cpu_byte(bank, pointer)
            if flags == 0:
                return tuple(roles)
            size = 7
            if flags & 0x18 == 0x18:
                size += int(not flags & 1) + int(not flags & 2) + (2 if not flags & 4 else 0)
            record = self._cpu_bytes(bank, pointer, size)
            night = time_value >= 0x78
            visible = bool(flags & (8 if night else 0x10))
            if visible:
                if night and not flags & 2:
                    high = record[1] & 3
                    low = record[7 if flags & 1 else 8]
                else:
                    high = (record[1] & 0x1C) >> 2
                    low = record[4]
                selector = low | (high << 8)
                roles.append({
                    1: ("Weapon merchant", "shop"),
                    2: ("Item merchant", "shop"),
                    3: ("Armor merchant", "shop"),
                    4: ("Vault keeper", "service"),
                    5: ("House of Healing", "healing"),
                    6: ("Innkeeper", "healing"),
                }.get(selector, ("NPC", "npc")))
            pointer += size
            for mask in (0x10, 8):
                if flags & mask:
                    pointer += self._cpu_byte(bank, pointer) + 1
            if len(roles) > 26:
                raise ValueError("DW4 entity record exceeds native runtime slots")
        raise ValueError("DW4 entity record is unterminated")

    def indexed_name(self, category: int, index: int) -> str:
        if self.region != "US" or not 0 <= category <= 10 or not 0 <= index < 255:
            raise ValueError("Unsupported DW4 native name identity")
        cache = getattr(self, "_name_cache", None)
        if cache is None:
            cache = self._name_cache = {}
        identity = category, index
        if identity in cache:
            return cache[identity]
        pointer = int.from_bytes(self._cpu_bytes(0x0B, 0xB057 + category * 2, 2), "little")
        for _ in range(index):
            pointer += self._cpu_byte(0x0B, pointer) + 1
        length = self._cpu_byte(0x0B, pointer)
        if not 0 < length <= 24:
            raise ValueError("Invalid DW4 native name record length")
        threshold = self._cpu_byte(0x0B, 0xBC40)
        if not 0 < threshold <= 0x80:
            raise ValueError("Invalid DW4 native name dictionary")
        symbols = []
        for encoded in self._cpu_bytes(0x0B, pointer + 1, length):
            symbols.extend(
                (encoded,) if encoded < threshold
                else self._cpu_bytes(0x0B, 0xBC63 + (encoded - threshold) * 2, 2)
            )
        decoded = []
        state = 8
        for symbol in symbols:
            if symbol >= threshold:
                raise ValueError("Invalid DW4 native name symbol")
            raw = self._cpu_byte(0x0B, 0xBC41 + symbol)
            delta = (raw - 0x7E) & 0xFF if raw & 0x80 else int(raw == 0)
            decision = self._cpu_byte(0x0B, 0xB034 + ((state + delta) & 0xFF))
            action = decision & 7
            if action:
                decoded.append(0 if action == 1 else (raw + (0x1A if action >= 3 else 0)) & 0xFF)
            state = decision & 0x18
        if len(decoded) > 24:
            raise ValueError("DW4 native name exceeds its text scratch capacity")
        name = decode_text(bytes(decoded))
        cache[identity] = name
        return name

    def map_layers(self) -> tuple[MapLayer, ...]:
        layers = list(self.world_layers())
        layers.extend(
            MapLayer(
                f"area-{descriptor.map_id:02x}-{descriptor.submap:02x}",
                map_title(descriptor.map_id, descriptor.submap, self._submap_names),
                "Dungeon / town",
                self.cache_directory
                / "maps"
                / f"area-{descriptor.map_id:02x}-{descriptor.submap:02x}.png",
                source_url=(
                    "https://datacrystal.tcrf.net/wiki/"
                    "Dragon_Warrior_IV_(NES)/ROM_map"
                ),
                credit="Generated locally from the configured ROM",
                wrap_width=descriptor.width,
                wrap_height=descriptor.height,
                anchor_x=8,
                anchor_y=8,
                map_id=descriptor.key,
                image_loader=(
                    lambda key=descriptor.key: self.render_area_map(key)
                ),
            )
            for descriptor in self._descriptors
        )
        return tuple(layers)

    def native_pattern_frame(self, ram: bytes, metatile_indices: bytes) -> tuple[tuple[int, bytes], ...]:
        if self.region != "US" or len(ram) < 0x58F or len(metatile_indices) != 34 * 4 or ram[0x28] in {0, 0x18}:
            return ()
        if ram[0x3E] and ram[0x58E] >= 2:
            return ()
        pending_tiles = set()
        if ram[0x1F] & 0x20:
            cursor = 0x300
            for _ in range(ram[0x50B]):
                if cursor + 3 > 0x400:
                    return ()
                high = ram[cursor]
                length = (ram[cursor + 1] or 256) if high & 0x80 else 1
                address = ((high & 0x3F) << 8) | ram[cursor + (2 if high & 0x80 else 1)]
                cursor += (3 if high & 0x80 else 2) + length
                if cursor > 0x400:
                    return ()
                if 0x1000 <= address < 0x2000:
                    pending_tiles.update(range((address - 0x1000) // 16,
                                               (address - 0x1000 + length + 15) // 16))
        updates = {}
        schedule = []
        for group in range(8):
            age = (ram[0x3C] - (15 - group * 2)) & 0x0F
            if age == 0 and pending_tiles.intersection(range(ram[0x574 + group], ram[0x574 + group] + 4)):
                age += 16
            schedule.append((age, group))
        for age, group in sorted(schedule, reverse=True):
            if not ram[0x573] & (0x80 >> group):
                continue
            destination = ram[0x574 + group]
            if destination == 0:
                continue
            source = ram[0x584 + group] | (ram[0x57C + group] << 8)
            last_update = (ram[0x3C] - age) & 0xFF
            phase_offset = (last_update & ram[0x58D]) * 4
            source += phase_offset
            if not 0x8000 <= source <= 0xBFC0:
                continue
            patterns = self._cpu_bytes(0x1D, source, 64)
            for local_index, ppu_index in enumerate(metatile_indices):
                if destination <= ppu_index < destination + 4:
                    offset = (ppu_index - destination) * 16
                    updates[local_index] = patterns[offset:offset + 16]
        return tuple(sorted(updates.items()))

    def native_palette_frame(self, ram: bytes) -> tuple[int, ...] | None:
        if self.region != "US" or len(ram) < 0x609 or ram[0x28] not in {0, 0x18}:
            return None
        colors = tuple(ram[0x5FD:0x609])
        if not any(colors) or any(color > 0x3F for color in colors):
            return None
        return colors

    def display_layers(
        self, layers: tuple[MapLayer, ...], time_value: int, world_selector: int, story_flags: int,
        live_area: tuple[int, bytes] | None = None,
        reveal_area: tuple[int, int] | None = None,
        animated_layer: tuple[str, tuple[int, ...]] | None = None,
        pattern_layer: tuple[str, tuple[tuple[int, bytes], ...]] | None = None,
    ) -> tuple[MapLayer, ...]:
        context = (int(time_value >= 0x78), world_selector == 3, bool(story_flags & 0x10))
        suffix = f"p{context[0]}{int(context[1])}{int(context[2])}"
        result = []
        for layer in layers:
            if layer.map_id is None:
                if animated_layer is not None and animated_layer[0] == layer.key:
                    palette = animated_layer[1]
                    variant = replace(layer, key=f"{layer.key}-native-frame", title="Live frame",
                                      image_path=layer.image_path.with_stem(f"{layer.image_path.stem}-native-palette-" + bytes(palette).hex()),
                                      image_loader=lambda identity=layer.key, colors=palette: self.render_world_map(identity, colors))
                    result.append(replace(layer, image_variants=(variant,)))
                else:
                    result.append(layer)
                continue
            key = layer.map_id
            pattern_updates = pattern_layer[1] if pattern_layer is not None and pattern_layer[0] == layer.key else ()
            reveal_tile = reveal_area[1] if reveal_area is not None and reveal_area[0] == key else None
            live_tiles = live_area[1] if live_area is not None and live_area[0] == key else None
            tile_suffix = "-live-" + hashlib.sha256(live_tiles).hexdigest()[:12] if live_tiles is not None else ""
            if reveal_tile is not None:
                tile_suffix += f"-reveal-{reveal_tile:02x}"
            classes = self._room_classes.get(key)
            if classes is None:
                tiles = self._area_layout(self._descriptor_by_key[key])[0]
                classes = self._room_classes[key] = tuple(sorted({value & 0xE0 for row in tiles for value in row}))
            if live_tiles is not None:
                classes = tuple(sorted({value & 0xE0 for value in live_tiles}))
            variants = ()
            if any(classes):
                variants = tuple(replace(
                    layer, key=f"{layer.key}-room-{room:02x}",
                    title="Roofs" if room == 0 else f"Interior {room >> 5}",
                    image_path=layer.image_path.with_stem(f"{layer.image_path.stem}-{suffix}-room-{room:02x}{tile_suffix}"),
                    image_loader=lambda identity=key, values=context, data=live_tiles, selected=room, revealed=reveal_tile:
                        self.render_area_map(identity, values, data, selected, revealed),
                ) for room in sorted({0, *classes}))
            if animated_layer is not None and animated_layer[0] == layer.key or pattern_updates:
                palette = animated_layer[1] if animated_layer is not None and animated_layer[0] == layer.key else None
                frame_key = hashlib.sha256(repr((palette, pattern_updates)).encode("ascii")).hexdigest()[:12]
                variants += (replace(layer, key=f"{layer.key}-native-frame", title="Live frame",
                                     image_path=layer.image_path.with_stem(f"{layer.image_path.stem}-{suffix}{tile_suffix}-native-frame-{frame_key}"),
                                     image_loader=lambda identity=key, values=context, data=live_tiles, colors=palette, updates=pattern_updates:
                                         self.render_area_map(identity, values, data, live_palette=colors, pattern_updates=updates)),)
            result.append(replace(
                layer,
                image_path=layer.image_path.with_stem(f"{layer.image_path.stem}-{suffix}{tile_suffix}"),
                image_loader=lambda identity=key, values=context, tiles=live_tiles: self.render_area_map(identity, values, tiles),
                image_variants=variants,
            ))
        previous = getattr(self, "_display_layers_cache", {})
        reconciled = []
        for layer in result:
            old = previous.get(layer.key)
            variants = []
            old_variants = {variant.key: variant for variant in old.image_variants} if old is not None else {}
            for variant in layer.image_variants:
                old_variant = old_variants.get(variant.key)
                if old_variant is not None and old_variant.image_path == variant.image_path:
                    variant = replace(variant, image_loader=old_variant.image_loader)
                variants.append(variant)
            if old is not None and old.image_path == layer.image_path:
                layer = replace(layer, image_loader=old.image_loader)
            reconciled.append(replace(layer, image_variants=tuple(variants)))
        self._display_layers_cache = {layer.key: layer for layer in reconciled}
        return tuple(reconciled)

    def world_layers(self) -> tuple[MapLayer, ...]:
        waypoints = self._world_destination_waypoints()
        return tuple(
            MapLayer(
                key,
                title,
                area,
                self.cache_directory / "maps" / f"{key}.png",
                source_url=(
                    "https://datacrystal.tcrf.net/wiki/"
                    "Dragon_Warrior_IV_(NES)/ROM_map#Overworld_Map_Data_and_Pointers"
                ),
                credit="Generated locally from the configured ROM",
                tile_width=tile_pixels,
                tile_height=tile_pixels,
                wrap_width=width,
                wrap_height=height,
                wraps=key == "world",
                anchor_x=tile_pixels // 2,
                anchor_y=tile_pixels // 2,
                waypoints=waypoints[key],
                image_loader=lambda map_key=key: self.render_world_map(map_key),
            )
            for key, (
                title,
                area,
                _,
                _,
                width,
                height,
                tile_pixels,
                _,
            ) in WORLD_MAP_SPECS.items()
        )

    def _world_destination_waypoints(self) -> dict[str, tuple[MapWaypoint, ...]]:
        routes = {}
        address = MAP_ROUTING_ADDRESS
        for _ in range(MAP_COUNT + 1):
            record = self._cpu_bytes(MAP_ROUTING_BANK, address, 5)
            if record[0] == 0xFF:
                break
            if record[0] >= MAP_COUNT:
                raise ValueError("DW4 map routing record has an invalid map identity")
            routes[record[0]] = record
            address += 5
        else:
            raise ValueError("DW4 map routing table is unterminated")

        points: dict[str, list[MapWaypoint]] = {
            key: [] for key in WORLD_MAP_SPECS
        }
        address = WORLD_POSITION_ADDRESS
        for _ in range(WORLD_POSITION_LIMIT):
            record = self._cpu_bytes(WORLD_POSITION_BANK, address, 3)
            if record[0] == 0xFF:
                break
            map_id, x, y = record
            route = routes.get(map_id)
            if route is not None:
                selector = (route[1] & 0x60) >> 5
                key = WORLD_KEY_BY_SELECTOR.get(selector)
                if key is not None:
                    submap = route[1] & 0x1F
                    width, height = WORLD_MAP_SPECS[key][4:6]
                    if not 0 <= y < height or not 0 <= x < width:
                        raise ValueError("DW4 world destination coordinates are outside their layer")
                    tile = self.world_tile(key, x, y) & 0x1F
                    points[key].append(
                        MapWaypoint(
                            x,
                            y,
                            map_title(map_id, submap, self._submap_names),
                            "",
                            "entrance",
                            marker=_world_destination_marker(key, tile),
                        )
                    )
            address += 3
        else:
            raise ValueError("DW4 world destination table is unterminated")
        return {key: tuple(values) for key, values in points.items()}

    def render_area_map(self, key: int, palette_context: tuple[int, bool, bool] | None = None,
                        live_tiles: bytes | None = None, room_class: int | None = None,
                        reveal_tile: int | None = None, live_palette: tuple[int, ...] | None = None,
                        pattern_updates: tuple[tuple[int, bytes], ...] = ()) -> Path:
        descriptor = self._descriptor_by_key.get(key)
        if descriptor is None:
            raise ValueError(f"DW4 area map 0x{key:04X} is unavailable")
        output = (
            self.cache_directory
            / "maps"
            / f"area-{descriptor.map_id:02x}-{descriptor.submap:02x}.png"
        )
        if palette_context is not None:
            output = output.with_stem(f"{output.stem}-p{palette_context[0]}{int(palette_context[1])}{int(palette_context[2])}")
        if room_class is not None:
            if room_class not in range(0, 0x100, 0x20):
                raise ValueError("Unsupported DW4 room class")
            output = output.with_stem(f"{output.stem}-room-{room_class:02x}")
        if reveal_tile is not None:
            if not 0 <= reveal_tile < 32:
                raise ValueError("Unsupported DW4 reveal tile")
            output = output.with_stem(f"{output.stem}-reveal-{reveal_tile:02x}")
        if live_palette is not None:
            if len(live_palette) != 12 or any(not 0 <= color <= 0x3F for color in live_palette):
                raise ValueError("Invalid DW4 native palette frame")
            output = output.with_stem(f"{output.stem}-native-palette-" + bytes(live_palette).hex())
        if pattern_updates:
            digest = hashlib.sha256(repr(pattern_updates).encode("ascii")).hexdigest()[:12]
            output = output.with_stem(f"{output.stem}-patterns-{digest}")
        if live_tiles is not None:
            if len(live_tiles) != descriptor.width * descriptor.height or len(live_tiles) > 0x800:
                raise ValueError("DW4 live map tiles do not match the verified SRAM buffer")
            output = output.with_stem(f"{output.stem}-live-{hashlib.sha256(live_tiles).hexdigest()[:12]}")
        if _valid_cached_image(output, descriptor.width * 16, descriptor.height * 16):
            return output
        tiles, graphics = self._area_layout(descriptor)
        if live_tiles is not None:
            tiles = tuple(tuple(live_tiles[start:start + descriptor.width])
                          for start in range(0, len(live_tiles), descriptor.width))
            tiles = self._apply_smoothing(tiles, graphics.smoothing)
        if palette_context is not None:
            graphics = replace(graphics, palette=self._area_palette(descriptor, palette_context))
        if live_palette is not None:
            graphics = replace(graphics, palette=live_palette)
        if pattern_updates:
            patterns = list(graphics.patterns)
            for index, pattern in pattern_updates:
                if not 0 <= index < len(patterns) or len(pattern) != 16:
                    raise ValueError("Invalid DW4 native pattern frame")
                patterns[index] = pattern
            graphics = replace(graphics, patterns=tuple(patterns))
        if room_class is None:
            self._area_renderer(tiles, graphics, output)
        else:
            self._area_renderer(tiles, graphics, output, room_class=room_class, reveal_tile=reveal_tile)
        self._write_manifest()
        return output

    def render_world_map(self, key: str, live_palette: tuple[int, ...] | None = None) -> Path:
        try:
            _, _, bank, pointer_table, width, height, _, selector = WORLD_MAP_SPECS[key]
        except KeyError as error:
            raise ValueError(f"Unknown DW4 world map: {key}") from error
        output = self.cache_directory / "maps" / f"{key}.png"
        if live_palette is not None:
            if len(live_palette) != 12 or any(not 0 <= color <= 0x3F for color in live_palette):
                raise ValueError("Invalid DW4 native palette frame")
            output = output.with_stem(f"{output.stem}-native-palette-" + bytes(live_palette).hex())
        if _valid_cached_image(output, width * 16, height * 16):
            return output
        rows = self._world_rows(key)
        base_graphics = self._area_graphics(
            AreaMapDescriptor(
                NO_PALETTE_OVERRIDE_MAP,
                NO_PALETTE_OVERRIDE_MAP,
                WORLD_TILESET,
                width,
                height,
                bank,
                pointer_table,
            )
        )
        palette_offset = self._cpu_address(
            WORLD_PALETTE_BANK,
            WORLD_PALETTE_ADDRESS + (8 if selector == 3 else 0) * WORLD_PALETTE_SIZE,
        )
        graphics = AreaGraphics(
            base_graphics.metatiles,
            base_graphics.attributes,
            base_graphics.patterns,
            live_palette if live_palette is not None else tuple(self._data[palette_offset:palette_offset + WORLD_PALETTE_SIZE]),
            base_graphics.behaviors,
            base_graphics.smoothing,
        )
        self._world_renderer(rows, graphics, output)
        self._write_manifest()
        return output

    def transition_records(self) -> dict[int, tuple[tuple[int, int | None, int | None], ...]]:
        if self.region != "US":
            return {}
        cached = getattr(self, "_transition_records", None)
        if cached is not None:
            return cached
        pointer = int.from_bytes(self._cpu_bytes(8, 0xB974, 2), "little")
        records = {}
        for _ in range(MAP_COUNT + 1):
            map_id = self._cpu_byte(8, pointer)
            pointer += 1
            if map_id == 255:
                self._transition_records = records
                return records
            if not 0 <= map_id < MAP_COUNT:
                raise ValueError("Invalid native transition map identity")
            floor = 0
            entries = []
            for _ in range(1024):
                control = self._cpu_byte(8, pointer)
                if control == 255:
                    pointer += 1
                    break
                mode = control & 0x60
                size = 1 if mode == 0 else 3 if mode == 0x20 else 2
                data = self._cpu_bytes(8, pointer, size)
                entries.append((control & 0x7F, data[1] if size > 1 else None,
                                data[2] if size == 3 else map_id))
                pointer += size
                if control & 0x80:
                    if floor >= 32:
                        raise ValueError("Native transition floor exceeds its bound")
                    records[area_key(map_id, floor)] = tuple(entries)
                    entries = []
                    floor += 1
            else:
                raise ValueError("Native transition map records are unterminated")
            if entries:
                raise ValueError("Native transition floor has no terminator")
        raise ValueError("Native transition directory is unterminated")

    def _transition_tiles(self, descriptor: AreaMapDescriptor, live_tiles: bytes | None = None) -> tuple[tuple[int, int], ...]:
        codes = []
        for offset in range(16):
            code = self._cpu_byte(8, 0xB675 + offset)
            if code == 0:
                break
            codes.append(code)
        else:
            raise ValueError("Native transition behavior list is unterminated")
        rows, graphics = self._area_layout(descriptor)
        if live_tiles is not None:
            if len(live_tiles) != descriptor.width * descriptor.height:
                raise ValueError("Incomplete native transition tile buffer")
            rows = tuple(tuple(live_tiles[start:start + descriptor.width]) for start in range(0, len(live_tiles), descriptor.width))
        return tuple((x, y) for y, row in enumerate(rows) for x, tile in enumerate(row)
                     if graphics.behaviors[tile & 31] & 0x7F in codes)

    def tile_transition_routes(self, map_id: int, submap: int, time_value: int = 0, story_flags: int = 0,
                               event_flags: bytes = b"", live_tiles: bytes | None = None) -> tuple[ExitRoute, ...]:
        descriptor = self.descriptor(map_id, submap)
        if self.region != "US" or descriptor is None:
            return ()
        key = descriptor.key
        records = self.transition_records().get(key, ())
        sources = self._transition_tiles(descriptor, live_tiles)
        routes = []
        for ordinal in range(28):
            pointer = 0xB681 + ordinal * 9
            source_map = self._cpu_byte(8, pointer)
            if source_map == 255:
                break
            record = self._cpu_bytes(8, pointer, 9)
            if (record[0], record[1]) != (map_id, submap):
                continue
            target = self.descriptor(record[4], record[5])
            if target is None or not 0 <= record[6] < target.width or not 0 <= record[7] < target.height:
                raise ValueError("Native coordinate transition destination is invalid")
            routes.append(ExitRoute(key, target.key, record[2], record[3], 1, 1, record[6], record[7]))
        else:
            raise ValueError("Native coordinate transition table is unterminated")
        if not sources and len(records) == 1 and records[0][0] == 0:
            return tuple(routes)
        if len(sources) != len(records):
            self._record_diagnostic(f"transition-{key}", f"{self._place(map_id, submap)}: some exit destinations are not known")
            return tuple(routes)
        for (x, y), (control, arrival, target_map) in zip(sources, records, strict=True):
            if any(route.x == x and route.y == y for route in routes):
                continue
            if control & 0x60 not in {0x20, 0x60} or arrival is None or target_map is None:
                continue
            floor = control & 31
            if target_map == 0x36 and floor == 1 and story_flags & 0x80:
                floor = 2
                arrival += int(1 <= arrival < 4)
            elif target_map == 0x38 and floor == 1 and arrival == 0 and story_flags & 0x20:
                floor = 2
            elif target_map == 0x45 and floor == 4 and arrival in {0, 4} and story_flags & 0x10:
                floor, arrival = 6, 5 if arrival == 4 else arrival
            elif target_map == 0x45 and floor == 5 and arrival == 2 and story_flags & 2:
                floor, arrival = 7, 3
            elif target_map == 0x3A and floor == 1 and story_flags & 8:
                floor = 0
            elif target_map == 0x19 and floor == 0 and time_value >= 0x78:
                floor = 1
            elif target_map == 0x15 and floor == 3 and time_value < 0x78:
                floor = 2
            elif target_map == 0x2D and floor == 3:
                if len(event_flags) <= 26:
                    continue
                if not event_flags[26] & 1:
                    floor, arrival = 2, 0
            elif target_map == 0x14 and floor == 0 and story_flags & 1:
                floor, arrival = 2, 0
            target = self.descriptor(target_map, floor)
            if target is None:
                raise ValueError("Native walking transition destination is outside the atlas")
            destinations = self._transition_tiles(target)
            if not 0 <= arrival < len(destinations):
                self._record_diagnostic(f"arrival-{key}-{x}-{y}", f"{self._place(map_id, submap)}: one exit destination is not known")
                continue
            destination_x, destination_y = destinations[arrival]
            if target_map == 0x18:
                if len(event_flags) <= 5:
                    continue
                if event_flags[5] & 2:
                    target = self.descriptor(target_map, 1)
                    if target is None:
                        raise ValueError("Native ghost-town arrival is outside the atlas")
                    destination_x, destination_y = 0, 15
            routes.append(ExitRoute(key, target.key, x, y, 1, 1, destination_x, destination_y))
        return tuple(routes)

    def exit_routes(self, map_id: int, submap: int) -> tuple[ExitRoute, ...]:
        if self.region != "US":
            return ()
        if self._exit_routes is None:
            pointer = int.from_bytes(self._cpu_bytes(0x12, 0xB970, 2), "little")
            routes = []
            for _ in range(256):
                source_map = self._cpu_byte(0x12, pointer)
                if source_map == 0xFF:
                    self._exit_routes = tuple(routes)
                    break
                source_floor = self._cpu_byte(0x12, pointer + 1)
                pointer += 2
                for _ in range(32):
                    source_x = source_y = None
                    width = height = 1
                    more = False
                    if source_floor & 0x80:
                        encoded_x, source_y = self._cpu_bytes(0x12, pointer, 2)
                        source_x, source_y = encoded_x & 0x3F, source_y & 0x3F
                        pointer += 2
                        more = bool(encoded_x & 0x40)
                        if encoded_x & 0x80:
                            extent = self._cpu_byte(0x12, pointer)
                            pointer += 1
                            width, height = (extent & 0x0F) + 1, (extent >> 4) + 1
                    destination = self._cpu_byte(0x12, pointer)
                    pointer += 1
                    destination_x = destination_y = None
                    if not destination & 0x80:
                        destination_x, destination_y = self._cpu_bytes(0x12, pointer, 2)
                        destination_x &= 0x3F
                        pointer += 2
                    source = area_key(source_map, source_floor & 0x7F)
                    target = area_key(source_map, destination & 0x7F)
                    special_source = source_map in {0x1C, 0x3E, 0x46, 0x3F, 0x41} or source_map == 0x36 and source_floor & 0x7F == 1
                    if not special_source and source in self._descriptor_by_key and target in self._descriptor_by_key:
                        routes.append(ExitRoute(source, target, source_x, source_y, width, height,
                                                destination_x, destination_y))
                    if not more:
                        break
                else:
                    raise ValueError("DW4 exit record exceeds its continuation bound")
            else:
                raise ValueError("DW4 exit route table is unterminated")
        key = area_key(map_id, submap)
        if map_id == 0x1C and area_key(0x33, 0) in self._descriptor_by_key:
            return (ExitRoute(key, area_key(0x33, 0), None, None, 1, 1, 23, 3),)
        if map_id == 0x36 and submap == 1 and area_key(0x36, 3) in self._descriptor_by_key:
            return (ExitRoute(key, area_key(0x36, 3), None, None, 1, 1, 8, 15),)
        if map_id == 0x41:
            return (ExitRoute(key, -1, None, None, 1, 1, None, None, "world", arrival_note=
                              "Lands south of where you entered: 3 steps in Chapter 1, otherwise 2"),)
        if map_id in {0x3E, 0x46}:
            routes = []
            for direction in range(4):
                x, y = self._cpu_bytes(0x12, 0xB8C6 + direction * 2, 2)
                routes.append(ExitRoute(key, -1, None, None, 1, 1, x, y, "gottside", direction))
            if map_id == 0x46:
                routes.append(ExitRoute(key, -1, 35, 29, 1, 1, 19, 17, "gottside"))
            return tuple(routes)
        if map_id == 0x3F and submap == 1 and area_key(0x3F, 2) in self._descriptor_by_key:
            descriptor = self._descriptor_by_key.get(key)
            if descriptor is None:
                return ()
            target = area_key(0x3F, 2)
            rectangles = ((11, 0, descriptor.width - 11, 6, 10, 6),
                          (3, 0, min(8, descriptor.width - 3), 7, 5, 6),
                          (11, 6, descriptor.width - 11, 1, 5, 6),
                          (0, 0, min(3, descriptor.width), 17, 6, 10),
                          (3, 7, descriptor.width - 3, 10, 6, 10))
            return tuple(ExitRoute(key, target, x, y, width, min(height, descriptor.height - y), dx, dy)
                         for x, y, width, height, dx, dy in rectangles
                         if width > 0 and y < descriptor.height)
        return tuple(route for route in self._exit_routes if route.source_key == key)

    def world_tile(self, key: str, x: int, y: int) -> int:
        if key not in WORLD_MAP_SPECS:
            raise ValueError("Unknown DW4 world map")
        _, _, bank, table, width, height, _, _ = WORLD_MAP_SPECS[key]
        if key == "world":
            x, y = x % width, y % height
        if not 0 <= x < width or not 0 <= y < height:
            raise ValueError("DW4 world tile coordinate is outside its layer")
        record = self._cpu_bytes(bank, table + y * 4, 4)
        pointer = int.from_bytes(record[:2], "little")
        if not 0x8000 <= pointer < 0xC000:
            raise ValueError("DW4 world row has an invalid pointer")
        start = self._prg_offset + bank * 0x4000
        data = self._data[start:start + 0x4000]
        return decode_world_point(data, pointer - 0x8000, x, record[2], record[3])

    def _world_rows(self, key: str) -> tuple[tuple[int, ...], ...]:
        try:
            _, _, bank, pointer_table, width, height, _, _ = WORLD_MAP_SPECS[key]
        except KeyError as error:
            raise ValueError(f"Unknown DW4 world map: {key}") from error
        table = self._cpu_address(bank, pointer_table)
        rows = []
        for row in range(height):
            entry = table + row * 4
            pointer = int.from_bytes(self._data[entry:entry + 2], "little")
            if not 0x8000 <= pointer < 0xC000:
                raise ValueError(f"{key} row {row} has an invalid pointer")
            rows.append(
                decode_world_row(
                    self._data,
                    self._cpu_address(bank, pointer),
                    width,
                )
            )
        return tuple(rows)

    def feature_overlay(
        self,
        map_id: int,
        submap: int,
        treasure_flags: bytes = b"",
        live_tiles: bytes | None = None,
        active_keys: frozenset[int] | None = None,
        reserve_keys: frozenset[int] = frozenset(),
        chapter: int | None = None,
        reserve_accessible: bool | None = None,
        companion_magic_access: bool | None = None,
        protected_hazards: frozenset[int] = frozenset(),
        event_flags: bytes = b"",
        *,
        position: tuple[int, int] | None = None,
    ) -> MapOverlay | None:
        descriptor = self.descriptor(map_id, submap)
        if descriptor is None:
            return None
        if not hasattr(self, "_cache_lock"):
            self._cache_lock = RLock()
        if not hasattr(self, "_feature_templates"):
            self._feature_templates = {}
        with self._cache_lock:
            templates = self._feature_templates.get(descriptor.key)
            if templates is None:
                self._build_feature_overlay(map_id, submap)
                templates = self._feature_templates.get(descriptor.key, ())
            points = []
            graphics = self._area_layout(descriptor)[1] if live_tiles is not None else None
            reachable = (self._reachable_tiles(descriptor, live_tiles, position)
                         if any(template.waypoint.kind == "hazards" for template in templates) else None)
            for template in templates:
                point = template.waypoint
                if not 0 <= point.x < descriptor.width or not 0 <= point.y < descriptor.height:
                    continue
                if point.kind == "hazards":
                    if reachable is not None and (point.x, point.y) not in reachable:
                        continue
                    if template.behavior in protected_hazards:
                        point = replace(point, detail="StepGuard is protecting the party", marker="hazard-protected")
                if template.flag_index is not None:
                    byte_index, bit = divmod(template.flag_index, 8)
                    mask = (1 << bit) if template.least_significant_first else (0x80 >> bit)
                    completed = bool(treasure_flags[byte_index] & mask) if byte_index < len(treasure_flags) else None
                    state = "Looted" if completed else "Available" if completed is False else "Not known yet"
                    detail = point.detail.replace("Available", state)
                    point = replace(point, completed=completed, detail=detail,
                                    marker="chest-unknown" if completed is None and point.marker == "chest" else point.marker)
                if template.reward_handler == 0xE2 and point.completed is not True:
                    if len(event_flags) <= 0x18:
                        point = replace(point, detail=point.detail.replace("Available", "Not known yet"), marker="chest-unknown")
                    elif event_flags[0x18] & 1:
                        point = replace(point, detail=point.detail.replace("Available", "No longer available"), marker="chest-unknown")
                if live_tiles is not None and graphics is not None and point.kind in {"locks", "entrance", "collectibles"}:
                    if len(live_tiles) != descriptor.width * descriptor.height:
                        raise ValueError("Incomplete DW4 live feature tile snapshot")
                    if not 0 <= point.x < descriptor.width or not 0 <= point.y < descriptor.height:
                        points.append(point)
                        continue
                    tile = live_tiles[point.y * descriptor.width + point.x] & 0x1F
                    behavior = graphics.behaviors[tile]
                    if point.kind == "locks" and behavior not in {0x95, 0x96, 0x97, 0xA0}:
                        point = replace(point, title="Opened door", detail="Open", completed=True, marker="exit")
                    elif point.marker in {"chest", "chest-unknown"} and behavior != 4:
                        original = template.waypoint.detail
                        point = replace(point, completed=True,
                                        detail=original.replace("Available", "Looted") if "Available" in original else "Looted")
                if point.kind == "locks" and point.completed is not True and active_keys is not None:
                    accepted = {"thief-door": {0x71, 0x72, 0x73}, "magic-door": {0x72, 0x73},
                                "final-door": {0x73}}.get(point.marker, set())
                    if accepted & active_keys:
                        point = replace(point, detail="You have the key", marker="door-ready")
                    elif reserve_accessible is True and accepted & reserve_keys:
                        point = replace(point, detail="A reserve party member has the key", marker="door-ready")
                    elif companion_magic_access is True and point.marker == "magic-door":
                        point = replace(point, detail="A companion can open this door", marker="door-ready")
                    elif (reserve_accessible is None and accepted & reserve_keys) or (companion_magic_access is None and chapter == 3 and point.marker == "magic-door"):
                        point = replace(point, detail="May need a key you do not have yet", marker="door-unknown")
                    else:
                        point = replace(point, detail=DOOR_KEY_DETAILS.get(point.marker, "Needs a key"))
                points.append(point)
            return MapOverlay(f"area-{map_id:02x}-{submap:02x}", tuple(points)) if points else None

    def _reachable_tiles(self, descriptor: AreaMapDescriptor, live_tiles: bytes | None,
                         position: tuple[int, int] | None) -> set[tuple[int, int]] | None:
        """Tiles the party can step on from a known way in; None when the floor has no such starting point."""
        width, height = descriptor.width, descriptor.height
        if live_tiles is not None and len(live_tiles) != width * height:
            live_tiles = None
        cache = getattr(self, "_reachability", None)
        if cache is None:
            cache = self._reachability = {}
        state = cache.pop(descriptor.key, None)
        if state is None or state.source != live_tiles:
            rows, graphics = self._area_layout(descriptor)
            codes = graphics.behaviors
            tiles = live_tiles if live_tiles is not None else [tile for row in rows for tile in row]
            behaviors = bytes(codes[tile & 0x1F] if tile & 0x1F < len(codes) else 0x80 for tile in tiles)
            seeds = set(state.positions) if state is not None else set()
            for index, behavior in enumerate(behaviors):
                y, x = divmod(index, width)
                if behavior in ENTRANCE_BEHAVIORS:
                    seeds.add((x, y))
            seeds.update((x, y) for x, y in self._arrival_points(descriptor.key)
                         if 0 <= x < width and 0 <= y < height)
            state = _Reachability(live_tiles, behaviors, set(), set(state.positions) if state is not None else set(), bool(seeds))
            _flood_reachable(behaviors, width, height, state.reached, seeds)
        cache[descriptor.key] = state
        while len(cache) > 16:
            cache.pop(next(iter(cache)))
        if position is not None and 0 <= position[0] < width and 0 <= position[1] < height and position not in state.reached:
            state.positions.add(position)
            state.seeded = True
            _flood_reachable(state.behaviors, width, height, state.reached, {position})
        return state.reached if state.seeded else None

    def _arrival_points(self, key: int) -> tuple[tuple[int, int], ...]:
        arrivals = getattr(self, "_arrivals", None)
        if arrivals is None:
            found: dict[int, set[tuple[int, int]]] = {}
            if getattr(self, "region", None) == "US":
                try:
                    for descriptor in tuple(self._descriptor_by_key.values()):
                        for route in self.exit_routes(descriptor.map_id, descriptor.submap):
                            if not route.destination_world and route.destination_x is not None and route.destination_y is not None:
                                found.setdefault(route.destination_key, set()).add((route.destination_x, route.destination_y))
                    for ordinal in range(MAP_COUNT):
                        map_id, floor, x, y = self._cpu_bytes(MAP_ROUTING_BANK, MAP_ROUTING_ADDRESS + ordinal * 5, 4)
                        if map_id == 0xFF:
                            break
                        found.setdefault(area_key(map_id, floor & 0x1F), set()).add((x, y))
                    for ordinal in range(28):
                        record = self._cpu_bytes(8, 0xB681 + ordinal * 9, 9)
                        if record[0] == 0xFF:
                            break
                        found.setdefault(area_key(record[4], record[5]), set()).add((record[6], record[7]))
                except ValueError:
                    pass
            arrivals = self._arrivals = {area: tuple(sorted(points)) for area, points in found.items()}
        return arrivals.get(key, ())

    def _build_feature_overlay(
        self,
        map_id: int,
        submap: int,
        treasure_flags: bytes = b"",
    ) -> MapOverlay | None:
        descriptor = self.descriptor(map_id, submap)
        if descriptor is None:
            return None
        tiles, graphics = self._area_layout(descriptor)
        chest_positions = tuple(
            (x, y)
            for y, row in enumerate(tiles)
            for x, encoded_tile in enumerate(row)
            if graphics.behaviors[encoded_tile & 0x1F] == 0x04
        )
        chest_records = self._chest_records(map_id, submap) if chest_positions else ()
        exact_chests = len(chest_positions) == len(chest_records)
        chest_index = 0
        points = [
            FeatureTemplate(self._hidden_point(treasure, tiles, graphics, b""), treasure.flag_index, True)
            for treasure in self.hidden_treasures()
            if (treasure.map_id, treasure.submap) == (map_id, submap)
        ]
        for y, row in enumerate(tiles):
            for x, encoded_tile in enumerate(row):
                tile = encoded_tile & 0x1F
                if tile >= len(graphics.behaviors):
                    continue
                behavior = graphics.behaviors[tile]
                flag_index = None
                reward_handler = None
                title = TILE_BEHAVIORS.get(behavior)
                if title is None:
                    continue
                if behavior == 0x04:
                    kind, marker = "collectibles", "chest"
                    if exact_chests:
                        flag_index, value = chest_records[chest_index]
                        reward_handler = value if value >= 0xE0 else None
                        completed = _msb_flag(treasure_flags, flag_index)
                        title, value_detail = _chest_reward(value)
                        if value in {0xFE, 0xFD}:
                            marker = "encounter"
                        detail = " · ".join(part for part in (
                            value_detail.strip(" ·"), "Looted" if completed else "Available") if part)
                    else:
                        detail = "Chest"
                        completed = None
                        marker = "chest-unknown"
                    chest_index += 1
                elif behavior in {0x06, 0x07, 0x0C}:
                    kind = "entrance"
                    marker = "exit"
                    detail = "Leaves this area"
                    completed = False
                elif behavior in {0x08, 0x09}:
                    kind = "entrance"
                    marker = "stairs-up" if behavior == 0x08 else "stairs-down"
                    detail = "Stairs up" if behavior == 0x08 else "Stairs down"
                    completed = False
                elif behavior == 0x0A:
                    kind = "entrance"
                    marker = "travel-door"
                    detail = "Travel door"
                    completed = False
                elif behavior in {0x95, 0x96, 0x97}:
                    kind = "locks"
                    marker = {0x95: "thief-door", 0x96: "magic-door", 0x97: "final-door"}[behavior]
                    detail = DOOR_KEY_DETAILS[marker]
                    completed = False
                elif behavior in {0x01, 0x02, 0x05, 0x0B, 0x10, 0x11, 0x12, 0x13}:
                    kind = "hazards"
                    marker = "hazard" if behavior in {0x01, 0x02, 0x05, 0x0B} else {
                        0x10: "forced-up", 0x11: "forced-right", 0x12: "forced-down", 0x13: "forced-left",
                    }[behavior]
                    detail = ("Damages the party while walking" if behavior in {0x01, 0x02} else
                              "Pitfall" if marker == "hazard" else
                              "Moves the party " + {0x10: "up", 0x11: "right", 0x12: "down", 0x13: "left"}[behavior])
                    completed = False
                else:
                    continue
                points.append(
                    FeatureTemplate(MapWaypoint(
                        x,
                        y,
                        title,
                        detail,
                        kind,
                        completed,
                        marker=marker,
                    ), flag_index, False, behavior, reward_handler)
                )
        self._feature_templates[descriptor.key] = tuple(points)
        while len(self._feature_templates) > 16:
            self._feature_templates.pop(next(iter(self._feature_templates)))
        if not points:
            return None
        return MapOverlay(
            f"area-{map_id:02x}-{submap:02x}",
            tuple(template.waypoint for template in points),
        )

    def _chest_records(
        self,
        map_id: int,
        submap: int,
    ) -> tuple[tuple[int, int], ...]:
        if getattr(self, "region", "US") != "US":
            return ()
        address = CHEST_DIRECTORY_ADDRESS
        value_offset = 0
        target = map_id, submap
        for _ in range(CHEST_DIRECTORY_LIMIT):
            record = self._cpu_bytes(HIDDEN_TABLE_BANK, address, 3)
            if record[0] == 0xFF:
                return ()
            record_map, record_submap, count = record
            if (record_map, record_submap) >= target:
                values = self._cpu_bytes(
                    HIDDEN_TABLE_BANK,
                    CHEST_VALUE_ADDRESS + value_offset,
                    count,
                )
                return tuple(
                    (value_offset + index, value)
                    for index, value in enumerate(values)
                )
            value_offset += count
            address += 3
        return ()

    def conditional_search_overlay(self, map_id: int, submap: int, event_flags: bytes,
                                   treasure_flags: bytes, held_items: frozenset[int],
                                   chapter: int, facing: int, live_tiles: bytes | None = None) -> MapOverlay | None:
        if getattr(self, "region", "US") != "US":
            return None
        rules = {0xE8: (0x75, 0, None), 0xE9: (0x62, 8, 0),
                 0xE1: (0x6A, 0x10, None), 0xF1: (0x65, 0x20, None),
                 0xE7: (0x26, 4, 0), 0xE6: (0x53, 2, 0), 0xE5: (None, 1, 0)}
        events = {0xEE: "Return Iron Safe", 0xED: "Open search passage", 0xEC: "Reveal concealed passage",
                  0xEA: "Travel passage", 0xE4: "Open paired passage tiles"}
        descriptor = self.descriptor(map_id, submap)
        if descriptor is None:
            return None
        if live_tiles is not None and len(live_tiles) != descriptor.width * descriptor.height:
            raise ValueError("Incomplete DW4 conditional search tile snapshot")
        points = []
        for current_map, current_floor, x, y, handler in self._hidden_rows(SEARCH_TABLE_ADDRESS, 5):
            if (current_map, current_floor) != (map_id, submap) or handler not in rules and handler not in events:
                continue
            if not 0 <= x < descriptor.width or not 0 <= y < descriptor.height:
                continue
            if handler in events:
                prerequisites = []
                completed = None
                if handler in {0xED, 0xEC}:
                    required_facing = 0 if handler == 0xED else 1
                    if facing != required_facing:
                        prerequisites.append("Face north" if required_facing == 0 else "Face east")
                    target_x, target_y = (20, 11) if handler == 0xED else (14, 4)
                    if live_tiles is not None and target_x < descriptor.width and target_y < descriptor.height:
                        completed = live_tiles[target_y * descriptor.width + target_x] & 0x1F == 3
                    else:
                        prerequisites.append("Target tile state unknown")
                if handler in {0xED, 0xE4}:
                    flag_index, mask = (2, 4) if handler == 0xED else (15, 2)
                    if len(event_flags) <= flag_index:
                        prerequisites.append("Passage status not known yet")
                    elif not event_flags[flag_index] & mask:
                        prerequisites.append("The passage is not unlocked yet")
                if handler == 0xEE:
                    prerequisites.append("Return the Iron Safe" if 0x6B in held_items else "Bring the Iron Safe")
                if handler == 0xEA:
                    prerequisites.append("Enter the passage")
                detail = "Passage open" if completed else "; ".join(prerequisites) if prerequisites else "Ready"
                points.append(MapWaypoint(x, y, events[handler], detail, "entrance", completed,
                                          marker="exit" if completed else "search-conditional"))
                continue
            item_id, flag_mask, required_facing = rules[handler]
            rule = ConditionalSearch(x, y, item_id, handler, flag_mask, required_facing)
            completed = bool(treasure_flags[26] & rule.flag_mask) if rule.flag_mask and len(treasure_flags) > 26 else None
            blockers = []
            if rule.flag_mask and len(treasure_flags) <= 26:
                blockers.append("Collection state unknown")
            if rule.required_facing is not None and facing != rule.required_facing:
                blockers.append("Face north before searching")
            if handler == 0xE8:
                if len(event_flags) <= 11:
                    blockers.append("Event prerequisites unknown")
                else:
                    if not event_flags[11] & 2:
                        blockers.append("Requires the Nectar story event")
                    if event_flags[8] & 2:
                        blockers.append("King's voice event is already completed")
                if 0x75 in held_items:
                    blockers.append("Nectar is already carried in the eligible roster")
            if handler == 0xF1 and chapter != 4:
                blockers.append("Mystic Acorns branch requires Chapter 5")
            detail = "Collected" if completed else "; ".join(blockers) if blockers else "Search here"
            title = item_name(rule.item_id) if rule.item_id is not None else "50 Gold"
            points.append(MapWaypoint(x, y, title, detail, "collectibles", completed,
                                      marker="search-conditional" if blockers or completed is None else "search"))
        return MapOverlay(f"area-{map_id:02x}-{submap:02x}", tuple(points)) if points else None

    def collectible_catalog(self) -> tuple[CollectibleDefinition, ...]:
        if self.region != "US":
            return ()
        if self._collectible_catalog is not None:
            return self._collectible_catalog
        found = {}
        value_offset = 0
        special_items = {0xEF: 0x52, 0xEE: 0x6B, 0xE3: 0x67, 0xE2: 0x7E, 0xE0: 0x6F}
        for ordinal in range(CHEST_DIRECTORY_LIMIT):
            record = self._cpu_bytes(HIDDEN_TABLE_BANK, CHEST_DIRECTORY_ADDRESS + ordinal * 3, 3)
            if record[0] == 0xFF:
                break
            for value in self._cpu_bytes(HIDDEN_TABLE_BANK, CHEST_VALUE_ADDRESS + value_offset, record[2]):
                byte_index, bit = divmod(value_offset, 8)
                value_offset += 1
                if value in {0xFF, 0xFE, 0xFD}:
                    continue
                item_id = value if value < 0x80 else special_items.get(value)
                definition = CollectibleDefinition(byte_index, 0x80 >> bit, item_id, _chest_reward(value)[0])
                found[(definition.flag_byte, definition.flag_mask)] = definition
        else:
            if self._cpu_byte(HIDDEN_TABLE_BANK, CHEST_DIRECTORY_ADDRESS + CHEST_DIRECTORY_LIMIT * 3) != 0xFF:
                raise ValueError("DW4 collectible chest directory is unterminated")
        for ordinal, (map_id, submap, x, y, item_id, flag_byte, mask) in enumerate(self._hidden_rows(FURNITURE_TABLE_ADDRESS, 7)):
            if mask.bit_count() != 1 or FURNITURE_FLAG_BYTE + flag_byte >= 27:
                self._record_diagnostic(f"furniture-{map_id}-{submap}-{x}-{y}-{ordinal}",
                                        f"Skipped invalid furniture pickup flag in map {map_id:02X}:{submap:02X} at ({x},{y}); other rewards remain available")
                continue
            definition = CollectibleDefinition(FURNITURE_FLAG_BYTE + flag_byte, mask, item_id, _hidden_reward(item_id))
            found[(definition.flag_byte, definition.flag_mask)] = definition
        for _, _, _, _, value in self._hidden_rows(SEARCH_TABLE_ADDRESS, 5):
            conditional = {0xE9: (0x62, 8), 0xE1: (0x6A, 0x10), 0xF1: (0x65, 0x20),
                           0xE7: (0x26, 4), 0xE6: (0x53, 2), 0xE5: (None, 1)}.get(value)
            if conditional is not None:
                item_id, mask = conditional
                definition = CollectibleDefinition(26, mask, item_id,
                                                   item_name(item_id) if item_id is not None else "50 Gold")
                found[(definition.flag_byte, definition.flag_mask)] = definition
                continue
            if not 0xA0 <= value <= 0xAA:
                continue
            index = value & 0x0F
            item_id = self._cpu_byte(HIDDEN_TABLE_BANK, SEARCH_ITEM_TABLE_ADDRESS + index)
            definition = CollectibleDefinition(SEARCH_FLAG_BYTE + index // 8, 0x80 >> (index & 7),
                                               item_id if item_id < 0x80 else None,
                                               _hidden_reward(item_id) if item_id < 0x80 else _gold_reward(item_id))
            found[(definition.flag_byte, definition.flag_mask)] = definition
        self._collectible_catalog = tuple(found.values())
        return self._collectible_catalog

    def hidden_treasures(
        self,
    ) -> tuple[HiddenTreasure, ...]:
        """Hidden drawer, pot, and search items with their exact ROM positions."""
        if self._hidden_treasures is None:
            self._hidden_treasures = self._read_hidden_treasures()
        return self._hidden_treasures

    def _read_hidden_treasures(
        self,
    ) -> tuple[HiddenTreasure, ...]:
        if self.region != "US":
            return ()
        found: list[HiddenTreasure] = []
        for ordinal, (map_id, submap, x, y, item_id, flag_byte, mask) in enumerate(self._hidden_rows(
            FURNITURE_TABLE_ADDRESS, 7
        )):
            if mask.bit_count() != 1 or FURNITURE_FLAG_BYTE + flag_byte >= 27:
                self._record_diagnostic(f"furniture-{map_id}-{submap}-{x}-{y}-{ordinal}",
                                        f"Skipped invalid furniture pickup flag in map {map_id:02X}:{submap:02X} at ({x},{y}); other rewards remain available")
                continue
            flag = (FURNITURE_FLAG_BYTE + flag_byte) * 8 + mask.bit_length() - 1
            found.append(
                HiddenTreasure(
                    map_id,
                    submap,
                    x,
                    y,
                    flag,
                    _hidden_reward(item_id),
                    f"ROM furniture record at ({x},{y})",
                )
            )
        for map_id, submap, x, y, value in self._hidden_rows(SEARCH_TABLE_ADDRESS, 5):
            if 0xA0 <= value <= 0xAA:
                index = value & 0x0F
                flag = (SEARCH_FLAG_BYTE + (index >> 3)) * 8 + 7 - (index & 0x07)
                item_id = self._cpu_byte(
                    HIDDEN_TABLE_BANK, SEARCH_ITEM_TABLE_ADDRESS + index
                )
                reward = (
                    _gold_reward(item_id)
                    if item_id & 0x80
                    else _hidden_reward(item_id)
                )
                found.append(
                    HiddenTreasure(
                        map_id,
                        submap,
                        x,
                        y,
                        flag,
                        reward,
                        f"ROM search record at ({x},{y})",
                    )
                )
        return tuple(found)

    def _hidden_rows(self, address: int, width: int) -> tuple[bytes, ...]:
        rows = []
        examined = 0
        while self._cpu_byte(HIDDEN_TABLE_BANK, address) != 0xFF:
            if examined >= HIDDEN_TABLE_LIMIT:
                raise ValueError("DW4 hidden treasure table is unterminated")
            examined += 1
            start = self._prg_offset + HIDDEN_TABLE_BANK * 0x4000 + address - 0x8000
            row = self._data[start:start + width]
            if len(row) != width:
                raise ValueError("DW4 hidden treasure table is truncated")
            if not self.has_area(row[0], row[1]):
                self._record_diagnostic(f"hidden-row-{address}", "Skipped hidden reward with an unknown map identity; other fixed-width records remain available")
            else:
                rows.append(row)
            address += width
        return tuple(rows)

    def _cpu_byte(self, bank: int, address: int) -> int:
        return self._cpu_bytes(bank, address, 1)[0]

    def _cpu_bytes(self, bank: int, address: int, size: int) -> bytes:
        start = self._cpu_address(bank, address)
        if size < 0 or address + size > 0xC000 or start + size > self._prg_offset + 0x80000:
            raise ValueError("DW4 ROM table leaves its declared PRG bank")
        result = bytes(self._data[start:start + size])
        if len(result) != size:
            raise ValueError("DW4 ROM table is truncated")
        return result

    @staticmethod
    def _hidden_point(
        treasure: HiddenTreasure,
        tiles: tuple[tuple[int, ...], ...],
        graphics: AreaGraphics,
        treasure_flags: bytes,
    ) -> MapWaypoint:
        behavior = (
            graphics.behaviors[tiles[treasure.y][treasure.x] & 0x1F]
            if 0 <= treasure.y < len(tiles) and 0 <= treasure.x < len(tiles[treasure.y])
            else None
        )
        place, marker = {
            0xAA: ("In a pot", "pot"),
            0xAB: ("In a drawer", "drawer"),
        }.get(behavior, ("Search here", "search"))
        opened = treasure.is_open(treasure_flags)
        return MapWaypoint(
            treasure.x,
            treasure.y,
            treasure.reward,
            f"{place} · {'Looted' if opened else 'Available'}",
            "collectibles",
            opened,
            marker=marker,
        )

    def _area_layout(
        self, descriptor: AreaMapDescriptor
    ) -> tuple[tuple[tuple[int, ...], ...], AreaGraphics]:
        with self._cache_lock:
            cached = self._area_cache.get(descriptor.key)
            if cached is not None:
                self._area_cache.pop(descriptor.key)
                self._area_cache[descriptor.key] = cached
                return cached
            decoder = MdecDecoder(self._area_stream(descriptor), 0)
            graphics = self._area_graphics(descriptor)
            layout = (self._apply_smoothing(decoder.decode(), graphics.smoothing), graphics)
            self._area_cache[descriptor.key] = layout
            while len(self._area_cache) > 16:
                self._area_cache.pop(next(iter(self._area_cache)))
            return layout

    def _area_stream(self, descriptor: AreaMapDescriptor) -> bytes:
        bank_start = self._prg_offset + descriptor.data_bank * 0x4000
        bank_end = bank_start + 0x3FD8
        if (
            not 0x09 <= descriptor.data_bank <= 0x0B
            or not bank_start <= descriptor.data_offset < bank_end
        ):
            raise ValueError("DW4 area map offset is outside its selected bank")
        chunks = [self._data[descriptor.data_offset:bank_end]]
        for bank in range(descriptor.data_bank + 1, 0x0C):
            start = self._prg_offset + bank * 0x4000
            chunks.append(self._data[start + (0x12 if bank == 0x0B else 0):start + 0x3FD8])
        return b"".join(chunks)

    def _area_graphics(self, descriptor: AreaMapDescriptor) -> AreaGraphics:
        tileset = self._cpu_address(TILESET_BANK, TILESET_ADDRESS)
        start = tileset + descriptor.tileset * 64
        patterns: list[bytes] = []
        metatiles = []
        attributes = []
        behaviors = []
        smoothing = []
        descriptor_table = self._cpu_address(TILESET_BANK, TILE_DESCRIPTOR_ADDRESS)
        for logical_tile in range(34):
            entry = start + logical_tile * 2 if logical_tile < 32 else self._cpu_address(TILESET_BANK, 0x8ABB + (logical_tile - 32) * 2)
            flags, low = self._data[entry:entry + 2]
            descriptor_id = ((flags & 0x07) << 8) | low
            physical = descriptor_table + descriptor_id * 3
            pattern_low, pattern_flags, behavior = self._data[physical:physical + 3]
            page = (pattern_flags >> 2) & 0x03
            shape = pattern_flags >> 4
            pattern_id = pattern_low | ((pattern_flags & 0x03) << 8)
            tile_patterns = self._tile_patterns(page, pattern_id, shape)
            first = len(patterns)
            patterns.extend(tile_patterns)
            metatiles.append((first, first + 1, first + 2, first + 3))
            smoothing.append(flags >> 5)
            attributes.append((flags >> 3) & 0x03)
            behaviors.append(behavior)
        return AreaGraphics(
            tuple(metatiles),
            tuple(attributes),
            tuple(patterns),
            self._area_palette(descriptor),
            tuple(behaviors),
            tuple(smoothing),
        )

    def _tile_patterns(self, page: int, pattern_id: int, shape: int) -> tuple[bytes, ...]:
        try:
            graphics_bank, base_address = GRAPHICS_BASES[page]
        except KeyError as error:
            raise ValueError(f"Unsupported DW4 graphics page: {page}") from error
        if shape == 0x0F:
            table = self._cpu_address(TILESET_BANK, EXPLICIT_PATTERN_ADDRESS)
            pointers = tuple(
                int.from_bytes(
                    self._data[table + pattern_id * 8 + index * 2:table + pattern_id * 8 + index * 2 + 2],
                    "little",
                )
                for index in range(4)
            )
            offsets = tuple(
                self._graphics_address(graphics_bank, pointer)
                for pointer in pointers
            )
        elif shape == 0x0E:
            graphics_bank = 0x1D
            table = self._cpu_address(TILESET_BANK, ANIMATED_PATTERN_ADDRESS)
            pointer = int.from_bytes(
                self._data[table + pattern_id * 2:table + pattern_id * 2 + 2],
                "little",
            )
            first = self._graphics_address(graphics_bank, pointer)
            offsets = tuple(first + index * 16 for index in range(4))
        else:
            if shape > 0x0D:
                raise ValueError(f"Unsupported DW4 tile increment pattern: {shape}")
            first = self._cpu_address(
                graphics_bank,
                base_address + pattern_id * 16,
                allow_previous_bank=True,
            )
            deltas = self._cpu_address(TILESET_BANK, TILE_INCREMENT_ADDRESS) + shape * 3
            offsets_list = [first]
            current = first
            for index in range(3):
                delta = int.from_bytes(
                    self._data[deltas + index:deltas + index + 1],
                    "little",
                    signed=True,
                )
                current += delta * 16
                offsets_list.append(current)
            offsets = tuple(offsets_list)
        result = tuple(bytes(self._data[offset:offset + 16]) for offset in offsets)
        if any(len(pattern) != 16 for pattern in result):
            raise ValueError("DW4 tile graphics point outside the ROM")
        return result

    def _area_palette(
        self, descriptor: AreaMapDescriptor, context: tuple[int, bool, bool] | None = None,
    ) -> tuple[int, ...]:
        selector = descriptor.tileset
        force_day = False
        force_night = False
        night = bool(context[0]) if context is not None else False
        special_world = bool(context[1]) if context is not None else False
        story_override = bool(context[2]) if context is not None else False
        if special_world:
            night = True
        map_table = self._cpu_address(PALETTE_BANK, PALETTE_OVERRIDE_MAP_ADDRESS)
        value_table = self._cpu_address(PALETTE_BANK, PALETTE_OVERRIDE_VALUE_ADDRESS)
        submap_table = self._cpu_address(PALETTE_BANK, PALETTE_OVERRIDE_SUBMAP_ADDRESS)
        for index in range(0x20):
            if special_world:
                break
            map_id = self._data[map_table + index]
            if map_id & 0x80:
                break
            submap = self._data[submap_table + index]
            if map_id != descriptor.map_id or submap not in {descriptor.submap, 0xFF}:
                continue
            if index < 0x0E:
                selector = self._data[value_table + index]
            elif index == 0x0E and story_override:
                selector = 0x36
            elif index in {0x0F, 0x10}:
                force_night = True
            elif index >= 0x11:
                force_day = True
            break
        if force_night or force_day:
            night = force_night and not force_day
        number_table = self._cpu_address(PALETTE_BANK, PALETTE_NUMBER_ADDRESS)
        palette_number = self._data[number_table + selector * 2 + int(night)]
        set_table = self._cpu_address(PALETTE_BANK, PALETTE_SET_ADDRESS)
        color_table = self._cpu_address(PALETTE_BANK, PALETTE_COLOR_ADDRESS)
        colors = []
        for color_set in self._data[set_table + palette_number * 4:set_table + palette_number * 4 + 4]:
            start = color_table + color_set * 3
            colors.extend(self._data[start:start + 3])
        if len(colors) != 12:
            raise ValueError("Truncated DW4 map palette")
        return tuple(colors)

    @staticmethod
    def _apply_smoothing(
        tiles: tuple[tuple[int, ...], ...],
        smoothing: tuple[int, ...],
    ) -> tuple[tuple[int, ...], ...]:
        if len(smoothing) < 32:
            return tiles
        front_tiles = {
            group - 4: tile
            for tile, group in enumerate(smoothing)
            if 5 <= group <= 7
        }
        if not front_tiles:
            return tiles
        result = [list(row) for row in tiles]
        for y, row in enumerate(tiles):
            for x, encoded_tile in enumerate(row):
                tile = encoded_tile & 0x1F
                group = smoothing[tile]
                if group not in front_tiles:
                    continue
                below_group = 0
                if y + 1 < len(tiles):
                    below_tile = tiles[y + 1][x] & 0x1F
                    below_group = smoothing[below_tile]
                if below_group == 0:
                    result[y][x] = (encoded_tile & 0xE0) | front_tiles[group]
        return tuple(tuple(row) for row in result)

    def _index_area_maps(self) -> tuple[AreaMapDescriptor, ...]:
        pointer_table = self._cpu_address(
            MAP_INFO_POINTER_BANK,
            MAP_INFO_POINTER_ADDRESS,
        )
        descriptors = []
        for map_id in range(MAP_COUNT):
            pointer = int.from_bytes(
                self._data[pointer_table + map_id * 2:pointer_table + map_id * 2 + 2],
                "little",
            )
            if not 0x8000 <= pointer < 0xC000:
                raise ValueError(f"DW4 map 0x{map_id:02X} has an invalid information pointer")
            information = self._cpu_address(MAP_INFO_POINTER_BANK, pointer)
            for submap in range(64):
                entry = information + submap * 3
                if self._data[entry] == 0xFF:
                    break
                tileset = self._data[entry] & 0x3F
                if tileset >= TILESET_COUNT:
                    raise ValueError(f"DW4 map 0x{map_id:02X}:{submap:02X} has an invalid tileset")
                data_address = int.from_bytes(self._data[entry + 1:entry + 3], "little")
                data_bank = self._area_data_bank(map_id, submap)
                data_offset = self._cpu_address(data_bank, data_address)
                width, height = self._data[data_offset:data_offset + 2]
                if not 0 < width <= MAX_MAP_DIMENSION or not 0 < height <= MAX_MAP_DIMENSION:
                    raise ValueError(f"DW4 map 0x{map_id:02X}:{submap:02X} has invalid dimensions")
                descriptors.append(
                    AreaMapDescriptor(
                        map_id,
                        submap,
                        tileset,
                        width,
                        height,
                        data_bank,
                        data_offset,
                    )
                )
            else:
                raise ValueError(f"DW4 map 0x{map_id:02X} exceeds the submap limit")
        return tuple(descriptors)

    @staticmethod
    def _area_data_bank(map_id: int, submap: int) -> int:
        if map_id < 0x2D or (map_id == 0x2D and submap < 8):
            return 0x09
        if map_id < 0x45 or (map_id == 0x45 and submap < 5):
            return 0x0A
        return 0x0B

    def _cpu_address(
        self,
        bank: int,
        address: int,
        *,
        allow_previous_bank: bool = False,
    ) -> int:
        minimum = 0x7F00 if allow_previous_bank else 0x8000
        if not minimum <= address < 0xC000:
            raise ValueError(f"Invalid CPU address ${address:04X} for PRG bank {bank:02X}")
        offset = self._prg_offset + bank * 0x4000 + address - 0x8000
        if offset < self._prg_offset or offset >= self._prg_offset + 0x80000:
            raise ValueError("DW4 ROM bank address is outside PRG data")
        return offset

    def _graphics_address(self, bank: int, address: int) -> int:
        if 0xC000 <= address <= 0xFFFF:
            offset = self._prg_offset + 0x1F * 0x4000 + address - 0xC000
            if offset >= self._prg_offset + 0x80000:
                raise ValueError("DW4 fixed-bank graphics address is outside PRG data")
            return offset
        return self._cpu_address(bank, address, allow_previous_bank=True)

    def _write_manifest(self) -> None:
        path = self.cache_directory / "metadata.json"
        if path.is_file():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "extractor_version": self.extractor_version,
                    "rom_hash": self.content_hash,
                    "region": self.region,
                    "area_maps": [asdict(item) for item in self._descriptors],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def _valid_cached_image(path: Path, width: int, height: int) -> bool:
    if not path.is_file():
        return False
    try:
        with Image.open(path) as image:
            valid = image.format == "PNG" and image.size == (width, height)
            image.verify()
            return valid
    except (OSError, UnidentifiedImageError, ValueError):
        return False