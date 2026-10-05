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
from .rom_reader import RomReader, _rom_region
from .rom_map_data import (
    ANIMATED_PATTERN_ADDRESS,
    AreaGraphics,
    AreaMapDescriptor,
    EXPLICIT_PATTERN_ADDRESS,
    GRAPHICS_BASES,
    MAP_COUNT,
    MAP_INFO_POINTER_ADDRESS,
    MAP_INFO_POINTER_BANK,
    MAP_ROUTING_ADDRESS,
    MAP_ROUTING_BANK,
    MAX_DECODE_OPERATIONS,
    MAX_MAP_DIMENSION,
    MdecDecoder,
    NO_PALETTE_OVERRIDE_MAP,
    PALETTE_BANK,
    PALETTE_COLOR_ADDRESS,
    PALETTE_NUMBER_ADDRESS,
    PALETTE_OVERRIDE_MAP_ADDRESS,
    PALETTE_OVERRIDE_SUBMAP_ADDRESS,
    PALETTE_OVERRIDE_VALUE_ADDRESS,
    PALETTE_SET_ADDRESS,
    RomMapData,
    TILESET_ADDRESS,
    TILESET_BANK,
    TILESET_COUNT,
    TILE_DESCRIPTOR_ADDRESS,
    TILE_INCREMENT_ADDRESS,
    WORLD_KEY_BY_SELECTOR,
    WORLD_MAP_SPECS,
    WORLD_MARKER_BY_TILE,
    WORLD_MARKER_OVERRIDES,
    WORLD_PALETTE_ADDRESS,
    WORLD_PALETTE_BANK,
    WORLD_PALETTE_SIZE,
    WORLD_POSITION_ADDRESS,
    WORLD_POSITION_BANK,
    WORLD_POSITION_LIMIT,
    WORLD_TILESET,
    _BitReader,
    _world_destination_marker,
    area_key,
    decode_world_point,
    decode_world_row,
)
from .rom_maps import (
    RomMaps,
    _valid_cached_image,
)
from .rom_catalog import (
    FormationChance,
    MonsterDefinition,
    RomCatalog,
    _selection_counts,
)
from .rom_features import (
    CHEST_DIRECTORY_ADDRESS,
    CHEST_DIRECTORY_LIMIT,
    CHEST_VALUE_ADDRESS,
    CollectibleDefinition,
    ConditionalSearch,
    DOOR_BEHAVIORS,
    DOOR_KEY_DETAILS,
    ENTRANCE_BEHAVIORS,
    ExitRoute,
    FURNITURE_FLAG_BYTE,
    FURNITURE_TABLE_ADDRESS,
    FeatureTemplate,
    HAZARD_DETAILS,
    HIDDEN_TABLE_BANK,
    HIDDEN_TABLE_LIMIT,
    HiddenTreasure,
    PITFALL_BEHAVIORS,
    RomFeatures,
    SEARCH_FLAG_BYTE,
    SEARCH_ITEM_TABLE_ADDRESS,
    SEARCH_TABLE_ADDRESS,
    SPECIAL_CHEST_VALUES,
    _Reachability,
    _chest_reward,
    _flood_reachable,
    _gold_reward,
    _hidden_reward,
    _msb_flag,
)


def _extractor_version(*renderers: object) -> str:
    paths = {Path(__file__).with_name(name) for name in (
        "rom_assets.py", "rom_reader.py", "rom_map_data.py", "rom_maps.py",
        "rom_catalog.py", "rom_features.py",
    )}
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


class DragonWarrior4RomAssets(RomMaps, RomCatalog, RomFeatures):
    """Compatibility surface sharing one reader and map-data state across domains."""

    def __init__(
        self,
        rom_path: Path,
        state_directory: Path,
        area_renderer: Callable[[tuple[tuple[int, ...], ...], AreaGraphics, Path], None],
        world_renderer: Callable[[tuple[tuple[int, ...], ...], AreaGraphics, Path], None],
        submap_names: dict[tuple[int, int], str] | None = None,
    ) -> None:
        full_hash = self._load_cartridge(rom_path)
        self.region = _rom_region(full_hash, self.content_hash)
        self.extractor_version = _extractor_version(area_renderer, world_renderer)
        versions = state_directory / "generated-assets" / self.content_hash
        self.cache_directory = versions / f"v{self.extractor_version}"
        self._initialize_map_data(submap_names)
        self._initialize_maps(area_renderer, world_renderer)
        self._initialize_catalog()
        self._initialize_features()
        self._diagnostics = {}
