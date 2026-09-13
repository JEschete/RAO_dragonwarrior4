from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

from PIL import Image, ImageDraw

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

WORLD_COLORS = (
    (85, 151, 83),
    (198, 176, 94),
    (151, 132, 84),
    (104, 111, 116),
    (42, 104, 66),
    (45, 102, 159),
    (93, 72, 117),
    (185, 193, 183),
    (206, 121, 73),
    (102, 167, 157),
    (205, 203, 163),
    (118, 89, 66),
    (150, 168, 184),
    (75, 75, 82),
    (217, 184, 88),
    (183, 78, 71),
)


def render_area_map(
    tiles: tuple[tuple[int, ...], ...],
    graphics: AreaGraphics,
    output: Path,
) -> None:
    image = Image.new("RGB", (len(tiles[0]) * 16, len(tiles) * 16))
    pixels = image.load()
    assert pixels is not None
    for map_y, row in enumerate(tiles):
        for map_x, encoded_tile in enumerate(row):
            tile = encoded_tile & 0x1F
            if tile >= len(graphics.metatiles):
                raise ValueError(f"DW4 map references unavailable tile ${tile:02X}")
            colors = (0x0F,) + graphics.palette[
                graphics.attributes[tile] * 3:graphics.attributes[tile] * 3 + 3
            ]
            for quadrant, pattern_id in enumerate(graphics.metatiles[tile]):
                _draw_pattern(
                    pixels,
                    map_x * 16 + (quadrant & 1) * 8,
                    map_y * 16 + (quadrant >> 1) * 8,
                    graphics.patterns[pattern_id],
                    colors,
                )
    _save_png(image, output)


def render_world_map(
    tiles: tuple[tuple[int, ...], ...],
    output: Path,
    tile_pixels: int = 4,
) -> None:
    image = Image.new(
        "RGB",
        (len(tiles[0]) * tile_pixels, len(tiles) * tile_pixels),
        WORLD_COLORS[5],
    )
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            left = x * tile_pixels
            top = y * tile_pixels
            color = WORLD_COLORS[tile % len(WORLD_COLORS)]
            draw.rectangle(
                (left, top, left + tile_pixels - 1, top + tile_pixels - 1),
                fill=color,
            )
            if tile in {2, 3} and tile_pixels >= 4:
                draw.line(
                    (left, top + tile_pixels - 1, left + tile_pixels // 2, top),
                    fill=(220, 216, 194),
                )
            elif tile == 4 and tile_pixels >= 4:
                draw.point((left + tile_pixels // 2, top + 1), fill=(24, 66, 44))
            elif tile == 5 and (x + y) % 2 == 0:
                draw.line(
                    (left, top + tile_pixels - 1, left + tile_pixels - 1, top + tile_pixels - 1),
                    fill=(73, 137, 188),
                )
    _save_png(image, output)


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