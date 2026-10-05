from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable

from PIL import Image, UnidentifiedImageError

from retroarch_overlay.models import MapLayer, MapWaypoint

from .reference_data import map_title
from .rom_map_data import (
    AreaGraphics,
    AreaMapDescriptor,
    MAP_COUNT,
    MAP_ROUTING_ADDRESS,
    MAP_ROUTING_BANK,
    NO_PALETTE_OVERRIDE_MAP,
    RomMapData,
    WORLD_KEY_BY_SELECTOR,
    WORLD_MAP_SPECS,
    WORLD_PALETTE_ADDRESS,
    WORLD_PALETTE_BANK,
    WORLD_PALETTE_SIZE,
    WORLD_POSITION_ADDRESS,
    WORLD_POSITION_BANK,
    WORLD_POSITION_LIMIT,
    WORLD_TILESET,
    _world_destination_marker,
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


class RomMaps(RomMapData):
    """Atlas layers, native-frame rendering, and versioned image-cache metadata."""

    cache_directory: Path
    extractor_version: str

    def _initialize_maps(
        self,
        area_renderer: Callable[[tuple[tuple[int, ...], ...], AreaGraphics, Path], None],
        world_renderer: Callable[[tuple[tuple[int, ...], ...], AreaGraphics, Path], None],
    ) -> None:
        self._area_renderer = area_renderer
        self._world_renderer = world_renderer
        self._room_classes: dict[int, tuple[int, ...]] = {}
        self._display_layers_cache: dict[str, MapLayer] = {}

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
