from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from retroarch_overlay.core.contracts import MemoryReader
from retroarch_overlay.models import MapDocument, MapOverlay, MapRegion, MapWaypoint
from retroarch_overlay.retroarch import RetroArchError

from .battle import BattleState
from .map_entities import ENTITY_MEMORY_ADDRESS, ENTITY_MEMORY_SIZE, read_map_entities, read_world_vehicles
from .reference_data import map_title
from .rom_assets import DragonWarrior4RomAssets
from .state import DragonWarrior4State


MEMORY_ERRORS = (RetroArchError, RuntimeError, OSError, ValueError)


@dataclass(frozen=True, slots=True)
class MapCapture:
    live_area: tuple[int, bytes] | None
    overlays: tuple[MapOverlay, ...]


class MapSnapshot:
    def __init__(self, map_document: MapDocument | None) -> None:
        self._display_context: tuple | None = None
        self._display_document = map_document

    def capture(
        self, memory: MemoryReader, state: DragonWarrior4State, ram: bytes, wram: bytes, battle: BattleState, *,
        assets: DragonWarrior4RomAssets | None, submap_names: dict[tuple[int, int], str], log: Callable[[str], None],
    ) -> MapCapture:
        live_area = None
        feature_overlay = None
        conditional_overlay = None
        if assets is not None and not state.location.is_world:
            try:
                descriptor = assets.descriptor(state.location.map_id, state.location.submap)
                if (
                    not battle.active and descriptor is not None
                    and (ram[0x3F], ram[0x40]) == (descriptor.width, descriptor.height)
                    and descriptor.width * descriptor.height <= 0x800
                ):
                    live_tiles = memory.read_memory(0x7800, descriptor.width * descriptor.height)
                    if len(live_tiles) != descriptor.width * descriptor.height:
                        raise ValueError("Live map snapshot is incomplete")
                    if (
                        memory.read_memory(0x3F, 3) != ram[0x3F:0x42]
                        or memory.read_memory(0x63, 3) != ram[0x63:0x66]
                    ):
                        raise ValueError("Discarded live map tiles during a floor transition")
                    live_area = descriptor.key, live_tiles
                feature_overlay = assets.feature_overlay(
                    state.location.map_id, state.location.submap, state.treasure_flags,
                    live_area[1] if live_area is not None else None,
                    frozenset(item.item_id for character in state.active_party for item in character.items),
                    frozenset(item.item_id for character in state.available_party if not character.active for item in character.items),
                    state.chapter,
                    state.reserve_accessible,
                    state.chapter == 3 and any(character.character_id == 9 and character.alive and not character.paralyzed
                                               for character in (state.available_party if state.reserve_accessible else state.active_party)),
                    frozenset((1, 2)) if wram[0x27F] & 0x40 else frozenset(),
                    event_flags=state.event_flags,
                    position=(state.location.x, state.location.y),
                )
                roster = state.available_party if state.reserve_accessible else state.active_party
                conditional_overlay = assets.conditional_search_overlay(
                    state.location.map_id, state.location.submap, state.event_flags, state.treasure_flags,
                    frozenset(item.item_id for character in roster for item in character.items), state.chapter, ram[0x3D] & 3,
                    live_area[1] if live_area is not None else None)
                walking_routes = assets.tile_transition_routes(
                    state.location.map_id, state.location.submap, state.time_value, wram[0x2AA],
                    state.event_flags, live_area[1] if live_area is not None else None)
                if feature_overlay is not None and walking_routes:
                    destinations = {(route.x, route.y): route for route in walking_routes}
                    points = []
                    for point in feature_overlay.waypoints:
                        route = destinations.get((point.x, point.y))
                        if route is not None:
                            destination = map_title(route.destination_key >> 8, route.destination_key & 255, submap_names)
                            point = replace(point, detail=" · ".join(
                                part for part in (point.detail, f"Leads to {destination}") if part))
                        points.append(point)
                    feature_overlay = replace(feature_overlay, waypoints=tuple(points))
            except (*MEMORY_ERRORS, IndexError) as error:
                log(f"Map objects unavailable: {error}")
        entity_overlay = self.entity_overlay(memory, state, ram, battle, assets=assets)
        overlays = tuple(
            value for value in (feature_overlay, conditional_overlay, entity_overlay,
                                self.vehicle_overlay(memory, state, ram, battle))
            if value is not None
        )
        return MapCapture(live_area, overlays)

    def display(
        self, memory: MemoryReader, state: DragonWarrior4State, ram: bytes, wram: bytes, battle: BattleState,
        capture: MapCapture, current_zone: tuple[str, MapRegion] | None, *,
        assets: DragonWarrior4RomAssets | None, map_document: MapDocument | None,
    ) -> MapDocument | None:
        live_area = capture.live_area
        if assets is not None and map_document is not None:
            reveal_area = (state.location.layer_id, ram[0x520]) if not state.location.is_world and ram[0x7BA] == 4 and ram[0x520] < 32 else None
            palette_frame = assets.native_palette_frame(ram) if not battle.active else None
            animated_layer = (_layer_key(state), palette_frame) if palette_frame is not None else None
            pattern_layer = None
            if not battle.active and ram[0x573]:
                try:
                    updates = assets.native_pattern_frame(ram, memory.read_memory(0x7600, 136))
                    if updates:
                        pattern_layer = (_layer_key(state), updates)
                except MEMORY_ERRORS:
                    pass
            context = (int(state.time_value >= 0x78), ram[0x65] == 3, bool(wram[0x293] & 0x10), live_area, reveal_area, animated_layer, pattern_layer, current_zone)
            if context != self._display_context:
                layers = assets.display_layers(map_document.layers, state.time_value, ram[0x65], wram[0x293], live_area, reveal_area, animated_layer, pattern_layer)
                if current_zone is not None:
                    layers = tuple(replace(layer, regions=layer.regions + (current_zone[1],))
                                   if layer.key == current_zone[0] else layer for layer in layers)
                self._display_document = MapDocument(
                    map_document.title,
                    layers,
                    map_document.overlay_kinds,
                )
                self._display_context = context
        return self._display_document

    def entity_overlay(self, memory: MemoryReader, state: DragonWarrior4State,
                        ram: bytes, battle: BattleState, *, assets: DragonWarrior4RomAssets | None) -> MapOverlay | None:
        if assets is None or state.location.is_world or state.location.area == "Unknown" or battle.active:
            return None
        descriptor = assets.descriptor(state.location.map_id, state.location.submap)
        if descriptor is None:
            return None
        try:
            entities = read_map_entities(memory.read_memory(ENTITY_MEMORY_ADDRESS, ENTITY_MEMORY_SIZE),
                                         memory.read_memory(0x7140, 32))
            roles = assets.map_actor_roles(ram[0x67], int.from_bytes(ram[0x3A:0x3C], "little"), state.time_value)
        except (*MEMORY_ERRORS, IndexError):
            return None
        points = tuple(
            MapWaypoint(entity.x, entity.y, roles[entity.slot - 6][0], kind="services" if roles[entity.slot - 6][1] in {"shop", "service", "healing"} else "entities",
                        marker=roles[entity.slot - 6][1])
            for entity in entities
            if entity.slot - 6 < len(roles) and 0 <= entity.x < descriptor.width and 0 <= entity.y < descriptor.height
            and entity.visible and entity.room_class == ram[0x46] & 0xE0
        )
        return MapOverlay(_layer_key(state), points) if points else None

    def vehicle_overlay(self, memory: MemoryReader, state: DragonWarrior4State,
                         ram: bytes, battle: BattleState) -> MapOverlay | None:
        if not state.location.is_world or state.location.memory_region != "US" or battle.active:
            return None
        try:
            vehicles = read_world_vehicles(memory.read_memory(ENTITY_MEMORY_ADDRESS, ENTITY_MEMORY_SIZE),
                                           ram[0x65], state.has_boat, state.has_balloon)
        except MEMORY_ERRORS:
            return None
        points = tuple(MapWaypoint(x, y, title, "Where you left it", "entities",
                                   marker=title.casefold()) for title, x, y in vehicles)
        return MapOverlay(_layer_key(state), points) if points else None

    def encounter_rate(
        self, memory: MemoryReader, state: DragonWarrior4State, wram: bytes, zone: int, *,
        assets: DragonWarrior4RomAssets | None,
    ) -> tuple[int | None, str]:
        if assets is None:
            return None, ""
        try:
            timing = memory.read_memory(0x6E41, 2)
            terrain = memory.read_memory(0x7140, 1)
            scent = memory.read_memory(0x6BEB, 1)
            if len(timing) != 2 or len(terrain) != 1 or len(scent) != 1:
                raise ValueError("Incomplete encounter rate inputs")
            threshold, detail = assets.land_encounter_threshold(
                zone, terrain[0], state.time_value, timing[1], timing[0], wram[0x2D5], scent[0])
        except MEMORY_ERRORS:
            return None, ""
        return threshold, detail


def _layer_key(state: DragonWarrior4State) -> str:
    if state.location.is_world:
        return {"World": "world", "Gottside": "gottside", "Underworld": "underworld"}.get(state.location.area, "world")
    return f"area-{state.location.map_id:02x}-{state.location.submap:02x}"
