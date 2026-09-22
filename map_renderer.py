from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from game.rom_assets import AreaGraphics


NES_PALETTE = (
    (84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136),
    (68, 0, 100), (92, 0, 48), (84, 4, 0), (60, 24, 0),
    (32, 42, 0), (8, 58, 0), (0, 64, 0), (0, 60, 0),
    (0, 50, 60), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (152, 150, 152), (8, 76, 196), (48, 50, 236), (92, 30, 228),
    (136, 20, 176), (160, 20, 100), (152, 34, 32), (120, 60, 0),
    (84, 90, 0), (40, 114, 0), (8, 124, 0), (0, 118, 40),
    (0, 102, 120), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (236, 238, 236), (76, 154, 236), (120, 124, 236), (176, 98, 236),
    (228, 84, 236), (236, 88, 180), (236, 106, 100), (212, 136, 32),
    (160, 170, 0), (116, 196, 0), (76, 208, 32), (56, 204, 108),
    (56, 180, 204), (60, 60, 60), (0, 0, 0), (0, 0, 0),
    (236, 238, 236), (168, 204, 236), (188, 188, 236), (212, 178, 236),
    (236, 174, 236), (236, 174, 212), (236, 180, 176), (228, 196, 144),
    (204, 210, 120), (180, 222, 120), (168, 226, 144), (152, 226, 180),
    (160, 214, 228), (160, 162, 160), (0, 0, 0), (0, 0, 0),
)

def render_area_map(
    tiles: tuple[tuple[int, ...], ...],
    graphics: AreaGraphics,
    output: Path,
) -> None:
    image = Image.new("RGB", (len(tiles[0]) * 16, len(tiles) * 16))
    tile_images: dict[int, Image.Image] = {}
    for map_y, row in enumerate(tiles):
        for map_x, encoded_tile in enumerate(row):
            tile = encoded_tile & 0x1F
            tile_image = tile_images.get(tile)
            if tile_image is None:
                tile_image = tile_images[tile] = _tile_image(tile, graphics)
            image.paste(tile_image, (map_x * 16, map_y * 16))
    _save_png(image, output)


def render_world_map(
    tiles: tuple[tuple[int, ...], ...],
    graphics: AreaGraphics,
    output: Path,
) -> None:
    """Outdoor layers draw with the overworld tileset, just like area maps."""
    render_area_map(tiles, graphics, output)


def _tile_image(tile: int, graphics: AreaGraphics) -> Image.Image:
    if tile >= len(graphics.metatiles):
        raise ValueError(f"DW4 map references unavailable tile ${tile:02X}")
    image = Image.new("RGB", (16, 16))
    pixels = image.load()
    assert pixels is not None
    colors = (0x0F,) + graphics.palette[
        graphics.attributes[tile] * 3:graphics.attributes[tile] * 3 + 3
    ]
    for quadrant, pattern_id in enumerate(graphics.metatiles[tile]):
        _draw_pattern(
            pixels,
            (quadrant & 1) * 8,
            (quadrant >> 1) * 8,
            graphics.patterns[pattern_id],
            colors,
        )
    return image


def _save_png(image: Image.Image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        image.save(temporary, format="PNG", optimize=True)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _draw_pattern(
    pixels: Any,
    origin_x: int,
    origin_y: int,
    pattern: bytes,
    colors: tuple[int, ...],
) -> None:
    if len(pattern) != 16 or len(colors) != 4:
        raise ValueError("DW4 NES pattern or palette is incomplete")
    for y in range(8):
        low, high = pattern[y], pattern[y + 8]
        for x in range(8):
            shift = 7 - x
            color = ((low >> shift) & 1) | (((high >> shift) & 1) << 1)
            pixels[origin_x + x, origin_y + y] = NES_PALETTE[colors[color] & 0x3F]