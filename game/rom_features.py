from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock

from retroarch_overlay.models import MapOverlay, MapWaypoint

from .reference_data import TILE_BEHAVIORS, item_name
from .rom_map_data import (
    AreaGraphics,
    AreaMapDescriptor,
    MAP_COUNT,
    MAP_ROUTING_ADDRESS,
    MAP_ROUTING_BANK,
    RomMapData,
    area_key,
)


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


class RomFeatures(RomMapData):
    """Map-local rewards, live feature projection, reachability, and directed routes."""

    def _initialize_features(self) -> None:
        self._hidden_treasures: tuple[HiddenTreasure, ...] | None = None
        self._feature_templates: dict[int, tuple[FeatureTemplate, ...]] = {}
        self._collectible_catalog: tuple[CollectibleDefinition, ...] | None = None
        self._exit_routes: tuple[ExitRoute, ...] | None = None
        self._reachability: dict[int, _Reachability] = {}
        self._arrivals: dict[int, tuple[tuple[int, int], ...]] | None = None

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
