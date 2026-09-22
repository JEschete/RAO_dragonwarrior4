from __future__ import annotations

import hashlib
import inspect
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from retroarch_overlay.models import MapLayer, MapOverlay, MapWaypoint

from .reference_data import TILE_BEHAVIORS, TreasureRecord, item_name, map_title


MAX_MAP_DIMENSION = 128
MAX_DECODE_OPERATIONS = 1_000_000
MAP_COUNT = 0x49
MAP_INFO_POINTER_BANK = 0x17
MAP_INFO_POINTER_ADDRESS = 0xB08D
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
FURNITURE_FLAG_BYTE = 22
SEARCH_FLAG_BYTE = 21
HIDDEN_TABLE_LIMIT = 64
POSITION_WORDS = ("left", "middle", "right")
WORLD_MAP_SPECS = {
    "world": ("Main World", "World", 0x0B, 0xA590, 256, 256, 16),
    "gottside": ("Gottside", "Gottside", 0x0B, 0xAB65, 64, 64, 16),
    "underworld": ("Underworld", "Underworld", 0x0B, 0xAE89, 64, 54, 16),
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


def _scripted_hidden(
    documented: tuple[TreasureRecord, ...],
    found: list[HiddenTreasure],
    spots: list[tuple[int, int, int, int]],
) -> tuple[HiddenTreasure, ...]:
    """Pairs scripted search spots with the documented items left on each floor.

    Scripted handlers do not expose their item or flag in a table, so a floor is
    resolved only when its unclaimed documented items match the spot count and,
    for several spots, their left/middle/right wording orders them by column.
    """
    resolved = []
    for floor in dict.fromkeys((map_id, submap) for map_id, submap, _, _ in spots):
        positions = sorted(
            (x, y) for map_id, submap, x, y in spots if (map_id, submap) == floor
        )
        claimed = {
            treasure.reward
            for treasure in found
            if (treasure.map_id, treasure.submap) == floor
        }
        records = [
            record
            for record in documented
            if (record.map_id, record.submap) == floor and record.reward not in claimed
        ]
        if not records or len(records) != len(positions):
            continue
        if len(records) > 1:
            ranks = [
                next(
                    (
                        rank
                        for rank, word in enumerate(POSITION_WORDS)
                        if f"{word} " in record.description.casefold()
                    ),
                    None,
                )
                for record in records
            ]
            if None in ranks or len(set(ranks)) != len(ranks):
                continue
            records = [record for _, record in sorted(zip(ranks, records))]
        resolved.extend(
            HiddenTreasure(
                floor[0],
                floor[1],
                x,
                y,
                record.flag_index,
                record.reward,
                record.description,
            )
            for (x, y), record in zip(positions, records)
        )
    return tuple(resolved)


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


class DragonWarrior4RomAssets:
    def __init__(
        self,
        rom_path: Path,
        state_directory: Path,
        area_renderer: Callable[[tuple[tuple[int, ...], ...], AreaGraphics, Path], None],
        world_renderer: Callable[[tuple[tuple[int, ...], ...], AreaGraphics, Path], None],
        submap_names: dict[tuple[int, int], str] | None = None,
    ) -> None:
        data = rom_path.read_bytes()
        if len(data) < 16 or data[:4] != b"NES\x1a":
            raise ValueError("Configured file is not an iNES ROM")
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
        self._discard_stale_caches(versions)
        self._area_renderer = area_renderer
        self._world_renderer = world_renderer
        self._submap_names = submap_names or {}
        self._descriptors = self._index_area_maps()
        self._descriptor_by_key = {item.key: item for item in self._descriptors}
        self._area_cache: dict[int, tuple[tuple[tuple[int, ...], ...], AreaGraphics]] = {}
        self._hidden_treasures: tuple[HiddenTreasure, ...] | None = None

    @property
    def area_maps(self) -> tuple[AreaMapDescriptor, ...]:
        return self._descriptors

    def has_area(self, map_id: int, submap: int) -> bool:
        return area_key(map_id, submap) in self._descriptor_by_key

    def descriptor(self, map_id: int, submap: int) -> AreaMapDescriptor | None:
        return self._descriptor_by_key.get(area_key(map_id, submap))

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

    def world_layers(self) -> tuple[MapLayer, ...]:
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
                anchor_x=tile_pixels // 2,
                anchor_y=tile_pixels // 2,
                image_loader=lambda map_key=key: self.render_world_map(map_key),
            )
            for key, (title, area, _, _, width, height, tile_pixels) in WORLD_MAP_SPECS.items()
        )

    def render_area_map(self, key: int) -> Path:
        descriptor = self._descriptor_by_key.get(key)
        if descriptor is None:
            raise ValueError(f"DW4 area map 0x{key:04X} is unavailable")
        output = (
            self.cache_directory
            / "maps"
            / f"area-{descriptor.map_id:02x}-{descriptor.submap:02x}.png"
        )
        if output.is_file():
            return output
        tiles, graphics = self._area_layout(descriptor)
        self._area_renderer(tiles, graphics, output)
        self._write_manifest()
        return output

    def render_world_map(self, key: str) -> Path:
        try:
            _, _, bank, pointer_table, width, height, _ = WORLD_MAP_SPECS[key]
        except KeyError as error:
            raise ValueError(f"Unknown DW4 world map: {key}") from error
        output = self.cache_directory / "maps" / f"{key}.png"
        if output.is_file():
            return output
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
        graphics = self._area_graphics(
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
        self._world_renderer(tuple(rows), graphics, output)
        self._write_manifest()
        return output

    def feature_overlay(
        self,
        map_id: int,
        submap: int,
        treasure_records: tuple[TreasureRecord, ...] = (),
        treasure_flags: bytes = b"",
    ) -> MapOverlay | None:
        descriptor = self.descriptor(map_id, submap)
        if descriptor is None:
            return None
        tiles, graphics = self._area_layout(descriptor)
        floor_treasures = tuple(
            record
            for record in treasure_records
            if (record.map_id, record.submap) == (map_id, submap)
            and record.container == "chest"
        )
        chest_positions = tuple(
            (x, y)
            for y, row in enumerate(tiles)
            for x, encoded_tile in enumerate(row)
            if graphics.behaviors[encoded_tile & 0x1F] == 0x04
        )
        points = [
            self._hidden_point(treasure, tiles, graphics, treasure_flags)
            for treasure in self.hidden_treasures(treasure_records)
            if (treasure.map_id, treasure.submap) == (map_id, submap)
        ]
        for y, row in enumerate(tiles):
            for x, encoded_tile in enumerate(row):
                tile = encoded_tile & 0x1F
                if tile >= len(graphics.behaviors):
                    continue
                behavior = graphics.behaviors[tile]
                title = TILE_BEHAVIORS.get(behavior)
                if title is None:
                    continue
                if behavior == 0x04:
                    kind, marker = "collectibles", "treasure"
                    exact = (
                        floor_treasures[0]
                        if len(floor_treasures) == len(chest_positions) == 1
                        else None
                    )
                    if exact is not None:
                        opened = exact.is_open(treasure_flags)
                        title = exact.reward
                        detail = (
                            f"{'Looted' if opened else 'Available'}\n"
                            f"{exact.description}"
                        )
                        completed = opened
                    elif floor_treasures:
                        detail = (
                            "Documented rewards on this floor; exact chest positions "
                            "are not mapped:\n"
                            + "\n".join(
                                f"{'Looted' if record.is_open(treasure_flags) else 'Available'}: "
                                f"{record.reward} — {record.description}"
                                for record in floor_treasures
                            )
                        )
                        completed = False
                    else:
                        detail = "Contents are not documented in the saved treasure table"
                        completed = False
                elif behavior in {0x06, 0x07, 0x08, 0x09, 0x0A, 0x0C}:
                    kind = "entrance"
                    marker = "stairs" if behavior in {0x08, 0x09} else "entrance"
                    detail = f"ROM tile behavior ${behavior:02X}"
                    completed = False
                elif behavior == 0x31:
                    kind, marker = "services", "service"
                    detail = f"ROM tile behavior ${behavior:02X}"
                    completed = False
                elif behavior in {0x95, 0x96}:
                    kind, marker = "locks", "lock"
                    detail = f"ROM tile behavior ${behavior:02X}"
                    completed = False
                else:
                    continue
                points.append(
                    MapWaypoint(
                        x,
                        y,
                        title,
                        detail,
                        kind,
                        completed,
                        marker=marker,
                    )
                )
        if not points:
            return None
        return MapOverlay(
            f"area-{map_id:02x}-{submap:02x}",
            tuple(points),
        )

    def hidden_treasures(
        self,
        treasure_records: tuple[TreasureRecord, ...] = (),
    ) -> tuple[HiddenTreasure, ...]:
        """Hidden drawer, pot, and search items with their exact ROM positions."""
        if self._hidden_treasures is None:
            try:
                self._hidden_treasures = self._read_hidden_treasures(treasure_records)
            except (IndexError, ValueError):
                self._hidden_treasures = ()
        return self._hidden_treasures

    def _read_hidden_treasures(
        self,
        treasure_records: tuple[TreasureRecord, ...],
    ) -> tuple[HiddenTreasure, ...]:
        if self.region != "US":
            return ()
        documented = tuple(
            record for record in treasure_records if record.container != "chest"
        )
        found: list[HiddenTreasure] = []
        for map_id, submap, x, y, item_id, flag_byte, mask in self._hidden_rows(
            FURNITURE_TABLE_ADDRESS, 7
        ):
            if mask.bit_count() != 1:
                raise ValueError("Unexpected DW4 furniture flag mask")
            flag = (FURNITURE_FLAG_BYTE + flag_byte) * 8 + mask.bit_length() - 1
            found.append(
                self._documented_hidden(
                    documented, map_id, submap, x, y, flag, _hidden_reward(item_id)
                )
            )
        special: list[tuple[int, int, int, int]] = []
        for map_id, submap, x, y, value in self._hidden_rows(SEARCH_TABLE_ADDRESS, 5):
            if 0xA0 <= value <= 0xAA:
                index = value & 0x0F
                flag = (SEARCH_FLAG_BYTE + (index >> 3)) * 8 + 7 - (index & 0x07)
                item_id = self._cpu_byte(
                    HIDDEN_TABLE_BANK, SEARCH_ITEM_TABLE_ADDRESS + index
                )
                found.append(
                    self._documented_hidden(
                        documented, map_id, submap, x, y, flag, _hidden_reward(item_id)
                    )
                )
            else:
                special.append((map_id, submap, x, y))
        found.extend(_scripted_hidden(documented, found, special))
        return tuple(found)

    def _hidden_rows(self, address: int, width: int) -> tuple[bytes, ...]:
        rows = []
        while self._cpu_byte(HIDDEN_TABLE_BANK, address) != 0xFF:
            if len(rows) >= HIDDEN_TABLE_LIMIT:
                raise ValueError("DW4 hidden treasure table is unterminated")
            start = self._prg_offset + HIDDEN_TABLE_BANK * 0x4000 + address - 0x8000
            row = self._data[start:start + width]
            if len(row) != width or not self.has_area(row[0], row[1]):
                raise ValueError("DW4 hidden treasure table does not match this ROM")
            rows.append(row)
            address += width
        return tuple(rows)

    def _cpu_byte(self, bank: int, address: int) -> int:
        return self._data[self._prg_offset + bank * 0x4000 + address - 0x8000]

    def _documented_hidden(
        self,
        documented: tuple[TreasureRecord, ...],
        map_id: int,
        submap: int,
        x: int,
        y: int,
        flag: int,
        reward: str,
    ) -> HiddenTreasure:
        # The saved table has a few wrong flags and submaps, so match on the item
        # and floor, letting an identical flag break ties or excuse a submap typo.
        candidates = [
            record
            for record in documented
            if record.map_id == map_id
            and record.reward == reward
            and (record.submap == submap or record.flag_index == flag)
        ]
        same_flag = [record for record in candidates if record.flag_index == flag]
        candidates = same_flag or candidates
        description = (
            candidates[0].description
            if len(candidates) == 1
            else f"{map_title(map_id, submap, self._submap_names)} ({x},{y})"
        )
        return HiddenTreasure(map_id, submap, x, y, flag, reward, description)

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
        place = {0xAA: "In a pot", 0xAB: "In a drawer"}.get(behavior, "Search here")
        opened = treasure.is_open(treasure_flags)
        return MapWaypoint(
            treasure.x,
            treasure.y,
            treasure.reward,
            f"{place} · {'Looted' if opened else 'Available'}\n{treasure.description}",
            "collectibles",
            opened,
            marker="item",
        )

    def _area_layout(
        self, descriptor: AreaMapDescriptor
    ) -> tuple[tuple[tuple[int, ...], ...], AreaGraphics]:
        cached = self._area_cache.get(descriptor.key)
        if cached is not None:
            return cached
        decoder = MdecDecoder(self._area_stream(descriptor), 0)
        graphics = self._area_graphics(descriptor)
        layout = (self._apply_smoothing(decoder.decode(), graphics.smoothing), graphics)
        self._area_cache[descriptor.key] = layout
        return layout

    def _area_stream(self, descriptor: AreaMapDescriptor) -> bytes:
        bank_start = self._prg_offset + descriptor.data_bank * 0x4000
        bank_end = bank_start + 0x4000
        if not bank_start <= descriptor.data_offset < bank_end:
            raise ValueError("DW4 area map offset is outside its selected bank")
        continuation_bank = (
            descriptor.data_bank + 1
            if descriptor.data_bank == 0x09
            else descriptor.data_bank
        )
        continuation_start = self._prg_offset + continuation_bank * 0x4000
        continuation_end = continuation_start + 0x4000
        return bytes(
            self._data[descriptor.data_offset:bank_end]
            + self._data[continuation_start:continuation_end]
        )

    def _area_graphics(self, descriptor: AreaMapDescriptor) -> AreaGraphics:
        tileset = self._cpu_address(TILESET_BANK, TILESET_ADDRESS)
        start = tileset + descriptor.tileset * 64
        patterns: list[bytes] = []
        metatiles = []
        attributes = []
        behaviors = []
        smoothing = []
        descriptor_table = self._cpu_address(TILESET_BANK, TILE_DESCRIPTOR_ADDRESS)
        for logical_tile in range(32):
            flags, low = self._data[start + logical_tile * 2:start + logical_tile * 2 + 2]
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

    def _area_palette(self, descriptor: AreaMapDescriptor) -> tuple[int, ...]:
        selector = descriptor.tileset
        force_day = False
        force_night = False
        map_table = self._cpu_address(PALETTE_BANK, PALETTE_OVERRIDE_MAP_ADDRESS)
        value_table = self._cpu_address(PALETTE_BANK, PALETTE_OVERRIDE_VALUE_ADDRESS)
        submap_table = self._cpu_address(PALETTE_BANK, PALETTE_OVERRIDE_SUBMAP_ADDRESS)
        for index in range(0x20):
            map_id = self._data[map_table + index]
            if map_id & 0x80:
                break
            submap = self._data[submap_table + index]
            if map_id != descriptor.map_id or submap not in {descriptor.submap, 0xFF}:
                continue
            if index < 0x0E:
                selector = self._data[value_table + index]
            elif index in {0x0F, 0x10}:
                force_night = True
            elif index >= 0x11:
                force_day = True
            break
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

    def _discard_stale_caches(self, versions: Path) -> None:
        try:
            stale = [
                item
                for item in versions.iterdir()
                if item.is_dir() and item.name != self.cache_directory.name
            ]
        except OSError:
            return
        for item in stale:
            shutil.rmtree(item, ignore_errors=True)

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