import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from game.rom_assets import (
    AreaGraphics,
    AreaMapDescriptor,
    DragonWarrior4RomAssets,
    MdecDecoder,
    WORLD_MAP_SPECS,
    _rom_region,
    area_key,
    decode_world_row,
)
from game.reference_data import TreasureRecord
from map_renderer import NES_PALETTE, render_area_map, render_world_map


PRG_OFFSET = 16
PRG_SIZE = 0x80000


def cpu_offset(bank: int, address: int) -> int:
    return PRG_OFFSET + bank * 0x4000 + address - 0x8000


def synthetic_rom() -> bytearray:
    data = bytearray(PRG_OFFSET + PRG_SIZE)
    data[:4] = b"NES\x1a"
    data[4] = 32
    information_address = 0xB121
    for map_id in range(0x49):
        count = 9 if map_id == 0x2D else 6 if map_id == 0x45 else 1
        pointer = cpu_offset(0x17, 0xB08D + map_id * 2)
        data[pointer:pointer + 2] = information_address.to_bytes(2, "little")
        information = cpu_offset(0x17, information_address)
        for submap in range(count):
            entry = information + submap * 3
            data[entry:entry + 3] = bytes((0, 0x00, 0x80))
        data[information + count * 3] = 0xFF
        information_address += count * 3 + 1
    for bank in (0x09, 0x0A, 0x0B):
        data[cpu_offset(bank, 0x8000):cpu_offset(bank, 0x8000) + 3] = bytes((1, 1, 0))
    return data


def discard_area_renderer(
    tiles: tuple[tuple[int, ...], ...],
    graphics: AreaGraphics,
    output: Path,
) -> None:
    return None


def discard_world_renderer(
    tiles: tuple[tuple[int, ...], ...],
    output: Path,
    tile_pixels: int,
) -> None:
    return None


def bitstream(bits: str) -> bytes:
    padded = bits + "0" * (-len(bits) % 8)
    return bytes(
        int(padded[index:index + 8], 2)
        for index in range(0, len(padded), 8)
    )


class MdecDecoderTests(unittest.TestCase):
    def test_decodes_documented_five_bit_tile_header(self) -> None:
        data = bytes((2, 1, 0b110_00000)) + bitstream(
            "11010"
            "00" "00000" "00" "1"
            "00"
        )

        decoder = MdecDecoder(data, 0)

        self.assertEqual(decoder.decode(), ((0x1A, 0x1A),))

    def test_decodes_command_fallthrough_to_direct_write(self) -> None:
        data = bytes((2, 2, 0b000_00000)) + bitstream(
            "01"
            "00" "10"
            "11" "10"
            "00" "00" "00" "1"
            "00"
        )

        decoder = MdecDecoder(data, 0)

        self.assertEqual(decoder.decode(), ((1, 1), (2, 1)))

    def test_clips_out_of_bounds_direct_write(self) -> None:
        data = bytes((2, 1, 0)) + bitstream(
            "01"
            "00" "10"
            "10" "1" "01"
            "0"
            "1" "11" "1"
            "00" "00" "00" "1"
            "00"
        )

        self.assertEqual(MdecDecoder(data, 0).decode(), ((1, 2),))

    def test_normalizes_reversed_fill_rectangle_endpoints(self) -> None:
        data = bytes((3, 2, 0)) + bitstream(
            "01"
            "00" "10"
            "01" "101" "001"
            "00" "00" "00" "1"
            "00"
        )

        self.assertEqual(
            MdecDecoder(data, 0).decode(),
            ((1, 2, 2), (1, 2, 2)),
        )

    def test_rejects_unreasonable_dimensions(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid DW4 map dimensions"):
            MdecDecoder(bytes((255, 1, 0b110_00000)), 0)

    def test_header_encodes_tile_widths_from_two_through_five_bits(self) -> None:
        self.assertEqual(MdecDecoder(bytes((1, 1, 0x00, 0)), 0)._tile_bits, 2)
        self.assertEqual(MdecDecoder(bytes((1, 1, 0x40, 0)), 0)._tile_bits, 3)
        self.assertEqual(MdecDecoder(bytes((1, 1, 0x80, 0)), 0)._tile_bits, 4)
        self.assertEqual(MdecDecoder(bytes((1, 1, 0xC0, 0)), 0)._tile_bits, 5)

    def test_large_brush_roof_fill_paints_single_overlay_tiles(self) -> None:
        data = bytes((4, 4, 0b000_00000)) + bitstream(
            "01"
            "00" "00" "00" "1"
            "01"
            "00" "1" "00" "0" "0" "1" "0"
            "01" "0000" "1111"
            "00" "0" "00" "1"
        )

        tiles = MdecDecoder(data, 0).decode()

        self.assertEqual(tiles[:2], ((0x21, 0x21, 1, 1), (0x21, 0x21, 1, 1)))
        self.assertEqual(tiles[2:], ((1, 1, 1, 1), (1, 1, 1, 1)))


class WorldMapDecoderTests(unittest.TestCase):
    def test_decodes_runs_and_extended_literal_tiles(self) -> None:
        data = bytes((0x02, 0x43, 0xE8, 0xE1))

        self.assertEqual(
            decode_world_row(data, 0, 10),
            (0, 0, 0, 2, 2, 2, 2, 8, 7, 7),
        )

    def test_world_extents_follow_pointer_table_boundaries(self) -> None:
        self.assertEqual(WORLD_MAP_SPECS["world"][4:6], (256, 256))
        self.assertEqual(WORLD_MAP_SPECS["gottside"][4:6], (64, 64))
        self.assertEqual(WORLD_MAP_SPECS["underworld"][4:6], (64, 54))


class RomAtlasTests(unittest.TestCase):
    def test_region_falls_back_to_verified_headerless_us_hash(self) -> None:
        self.assertEqual(
            _rom_region(
                "33690b361265c840fda965418adf3143",
                "d8a1d610c93b96ad98e55e09dfcc7533",
            ),
            "US",
        )

    def test_indexes_submaps_and_documented_bank_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rom = root / "dw4.nes"
            rom.write_bytes(synthetic_rom())

            assets = DragonWarrior4RomAssets(
                rom,
                root / "state",
                discard_area_renderer,
                discard_world_renderer,
            )

            self.assertEqual(len(assets.area_maps), 86)
            self.assertEqual(assets.descriptor(0x2D, 7).data_bank, 0x09)
            self.assertEqual(assets.descriptor(0x2D, 8).data_bank, 0x0A)
            self.assertEqual(assets.descriptor(0x45, 4).data_bank, 0x0A)
            self.assertEqual(assets.descriptor(0x45, 5).data_bank, 0x0B)
            self.assertFalse(assets.has_area(0x45, 6))

    def test_layers_are_lazy_and_use_composite_submap_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rom = root / "dw4.nes"
            rom.write_bytes(synthetic_rom())
            area_renderer = Mock()
            world_renderer = Mock()
            assets = DragonWarrior4RomAssets(
                rom,
                root / "state",
                area_renderer,
                world_renderer,
                {(0, 0): "Keeleon - Outside"},
            )

            layers = assets.map_layers()

            self.assertEqual(len(layers), 89)
            self.assertEqual(layers[0].title, "Main World")
            self.assertEqual(layers[3].map_id, area_key(0, 0))
            self.assertEqual(layers[3].title, "Keeleon - Outside")
            self.assertIsNotNone(layers[3].image_loader)
            area_renderer.assert_not_called()
            world_renderer.assert_not_called()

    def test_area_stream_uses_documented_cross_bank_continuations(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        bank_09_end = cpu_offset(0x09, 0xBFFE)
        bank_0a_end = cpu_offset(0x0A, 0xBFFE)
        assets._data[bank_09_end:bank_09_end + 2] = bytes((1, 2))
        assets._data[cpu_offset(0x0A, 0x8000):cpu_offset(0x0A, 0x8000) + 2] = bytes((3, 4))
        assets._data[bank_0a_end:bank_0a_end + 2] = bytes((5, 6))

        from_bank_09 = assets._area_stream(
            AreaMapDescriptor(0x2D, 7, 0, 1, 1, 0x09, bank_09_end)
        )
        from_bank_0a = assets._area_stream(
            AreaMapDescriptor(0x45, 4, 0, 1, 1, 0x0A, bank_0a_end)
        )

        self.assertEqual(from_bank_09[:4], bytes((1, 2, 3, 4)))
        self.assertEqual(from_bank_0a[:4], bytes((5, 6, 3, 4)))

    def test_tileset_synthesizes_native_patterns_behaviors_and_palette(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        tileset = cpu_offset(0x08, 0x8ADB)
        for logical_tile in range(32):
            assets._data[tileset + logical_tile * 2:tileset + logical_tile * 2 + 2] = bytes(
                ((1 << 5) | (2 << 3), 0)
            )
        physical = cpu_offset(0x08, 0xA80D)
        assets._data[physical:physical + 3] = bytes((0, 0, 0x04))
        deltas = cpu_offset(0x08, 0xA1BB)
        assets._data[deltas:deltas + 3] = bytes((1, 1, 1))
        for pattern_id in range(4):
            offset = cpu_offset(0x0C, 0x8000 + pattern_id * 16)
            assets._data[offset:offset + 16] = bytes((pattern_id,)) * 16
        assets._data[cpu_offset(0x0E, 0xBB53)] = 0xFF
        assets._data[cpu_offset(0x0E, 0xBB88)] = 0
        assets._data[cpu_offset(0x0E, 0xBC0A):cpu_offset(0x0E, 0xBC0A) + 4] = bytes(
            (0, 1, 2, 3)
        )
        assets._data[cpu_offset(0x0E, 0xBCE2):cpu_offset(0x0E, 0xBCE2) + 12] = bytes(
            range(12)
        )
        descriptor = AreaMapDescriptor(0, 0, 0, 1, 1, 9, cpu_offset(9, 0x8000))

        graphics = assets._area_graphics(descriptor)

        self.assertEqual(graphics.metatiles[0], (0, 1, 2, 3))
        self.assertEqual(tuple(pattern[0] for pattern in graphics.patterns[:4]), (0, 1, 2, 3))
        self.assertEqual(graphics.attributes[0], 2)
        self.assertEqual(graphics.behaviors[0], 0x04)
        self.assertEqual(graphics.smoothing[0], 1)
        self.assertEqual(graphics.palette, tuple(range(12)))

    def test_animated_pattern_can_reference_fixed_final_prg_bank(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        table = cpu_offset(0x08, 0xAEB7)
        assets._data[table:table + 2] = (0xED07).to_bytes(2, "little")
        fixed = PRG_OFFSET + 0x1F * 0x4000 + 0x2D07
        for pattern_id in range(4):
            assets._data[fixed + pattern_id * 16:fixed + (pattern_id + 1) * 16] = bytes(
                (pattern_id + 1,)
            ) * 16

        patterns = assets._tile_patterns(0, 0, 0x0E)

        self.assertEqual(tuple(pattern[0] for pattern in patterns), (1, 2, 3, 4))

    def test_smoothing_changes_exposed_wall_to_front_tile(self) -> None:
        smoothing = (1, 5, 0) + (0,) * 29

        result = DragonWarrior4RomAssets._apply_smoothing(
            ((0,), (2,)),
            smoothing,
        )

        self.assertEqual(result, ((1,), (2,)))

    def test_single_chest_marker_has_exact_reward_and_live_status(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(2, 1, 0, 1, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        graphics = AreaGraphics(
            ((0, 0, 0, 0),),
            (0,),
            (bytes(16),),
            (0,) * 12,
            (0x04,),
            (0,),
        )
        assets._area_layout = Mock(return_value=(((0,),), graphics))
        record = TreasureRecord(0, 2, 1, "Left chest", "Agility Seed")

        available = assets.feature_overlay(2, 1, (record,), bytes(27))
        looted = assets.feature_overlay(2, 1, (record,), bytes((1,)) + bytes(26))

        self.assertIsNotNone(available)
        self.assertEqual(available.waypoints[0].title, "Agility Seed")
        self.assertIn("Available", available.waypoints[0].detail)
        self.assertFalse(available.waypoints[0].completed)
        self.assertTrue(looted.waypoints[0].completed)

    def test_ambiguous_chests_show_all_floor_rewards_without_pairing(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(3, 2, 0, 2, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        graphics = AreaGraphics(
            ((0, 0, 0, 0),),
            (0,),
            (bytes(16),),
            (0,) * 12,
            (0x04,),
            (0,),
        )
        assets._area_layout = Mock(return_value=(((0, 0),), graphics))
        records = (
            TreasureRecord(1, 3, 2, "Top chest", "Small Medal"),
            TreasureRecord(2, 3, 2, "Bottom chest", "Aeolus' Shield"),
        )

        overlay = assets.feature_overlay(3, 2, records, bytes(27))

        self.assertIsNotNone(overlay)
        self.assertEqual(len(overlay.waypoints), 2)
        self.assertTrue(all("exact chest positions are not mapped" in point.detail for point in overlay.waypoints))
        self.assertTrue(all("Small Medal" in point.detail for point in overlay.waypoints))
        self.assertTrue(all("Aeolus' Shield" in point.detail for point in overlay.waypoints))

    def test_feature_overlay_distinguishes_entrances_services_and_locks(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(3, 1, 0, 3, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        graphics = AreaGraphics(
            ((0, 0, 0, 0),),
            (0,),
            (bytes(16),),
            (0,) * 12,
            (0x06, 0x31, 0x95),
            (0,),
        )
        assets._area_layout = Mock(return_value=(((0, 1, 2),), graphics))

        overlay = assets.feature_overlay(3, 1)

        self.assertIsNotNone(overlay)
        self.assertEqual(
            tuple((point.kind, point.marker) for point in overlay.waypoints),
            (
                ("entrance", "entrance"),
                ("services", "service"),
                ("locks", "lock"),
            ),
        )

    def test_world_rows_follow_four_byte_pointer_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = synthetic_rom()
            row_data = cpu_offset(0x0B, 0x8000)
            data[row_data:row_data + 2] = bytes((0x1F, 0x1F))
            table = cpu_offset(0x0B, 0xAB65)
            for row in range(64):
                data[table + row * 4:table + row * 4 + 4] = bytes((0x00, 0x80, 2, 2))
            rom = root / "dw4.nes"
            rom.write_bytes(data)
            renderer = Mock()
            assets = DragonWarrior4RomAssets(
                rom,
                root / "state",
                discard_area_renderer,
                renderer,
            )

            assets.render_world_map("gottside")

            rows, _, tile_pixels = renderer.call_args.args
            self.assertEqual(len(rows), 64)
            self.assertEqual(rows[0], (0,) * 64)
            self.assertEqual(tile_pixels, 6)


class RendererTests(unittest.TestCase):
    def test_area_renderer_uses_nes_pattern_planes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "area.png"
            pattern = bytes((0x80,) + (0,) * 7 + (0x40,) + (0,) * 7)
            graphics = AreaGraphics(
                ((0, 0, 0, 0),),
                (0,),
                (pattern,),
                (0x30, 0x17, 0x10) * 4,
                (0,),
                (0,),
            )

            render_area_map(((0,),), graphics, output)

            from PIL import Image

            with Image.open(output) as image:
                self.assertEqual(image.size, (16, 16))
                self.assertEqual(image.getpixel((0, 0)), NES_PALETTE[0x30])
                self.assertEqual(image.getpixel((1, 0)), NES_PALETTE[0x17])

    def test_world_renderer_creates_stable_cartographic_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "world.png"

            render_world_map(((0, 5), (3, 4)), output, 4)

            from PIL import Image

            with Image.open(output) as image:
                self.assertEqual(image.size, (8, 8))
                self.assertNotEqual(image.getpixel((0, 0)), image.getpixel((4, 0)))

    def test_failed_map_write_does_not_leave_a_cached_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "maps" / "area.png"
            graphics = AreaGraphics(
                ((0, 0, 0, 0),),
                (0,),
                (bytes(16),),
                (0x0F, 0x10, 0x20) * 4,
                (0,),
                (0,),
            )

            def fail_after_partial_write(
                _image: Image.Image,
                path: Path,
                **_kwargs,
            ) -> None:
                Path(path).write_bytes(b"partial")
                raise OSError("render interrupted")

            with patch.object(Image.Image, "save", fail_after_partial_write):
                with self.assertRaisesRegex(OSError, "render interrupted"):
                    render_area_map(((0,),), graphics, output)

            self.assertFalse(output.exists())
            self.assertEqual(tuple(output.parent.iterdir()), ())


if __name__ == "__main__":
    unittest.main()