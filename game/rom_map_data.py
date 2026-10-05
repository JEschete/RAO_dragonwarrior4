from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from .reference_data import map_title
from .rom_reader import RomReader


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


class RomMapData(RomReader):
    """Map identities, logical tile decoding, graphics, and bounded layout caching."""

    def _initialize_map_data(self, submap_names: dict[tuple[int, int], str] | None) -> None:
        self._submap_names = submap_names or {}
        self._descriptors = self._index_area_maps()
        self._descriptor_by_key = {item.key: item for item in self._descriptors}
        self._area_cache: dict[int, tuple[tuple[tuple[int, ...], ...], AreaGraphics]] = {}
        self._cache_lock = RLock()

    @property
    def area_maps(self) -> tuple[AreaMapDescriptor, ...]:
        return self._descriptors

    def _place(self, map_id: int, submap: int) -> str:
        return map_title(map_id, submap, getattr(self, "_submap_names", None))

    def has_area(self, map_id: int, submap: int) -> bool:
        return area_key(map_id, submap) in self._descriptor_by_key

    def descriptor(self, map_id: int, submap: int) -> AreaMapDescriptor | None:
        return self._descriptor_by_key.get(area_key(map_id, submap))

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
