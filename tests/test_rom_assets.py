import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from game.rom_assets import (
    AreaGraphics,
    AreaMapDescriptor,
    DragonWarrior4RomAssets,
    FeatureTemplate,
    HiddenTreasure,
    MdecDecoder,
    WORLD_MAP_SPECS,
    _rom_region,
    _world_destination_marker,
    _valid_cached_image,
    _chest_reward,
    area_key,
    decode_world_row,
    decode_world_point,
)
from game.reference_data import ITEM_NAMES
from retroarch_overlay.models import MapWaypoint, MapLayer
from map_renderer import NES_PALETTE, render_area_map, render_world_map


PRG_OFFSET = 16
PRG_SIZE = 0x80000


def cpu_offset(bank: int, address: int) -> int:
    return PRG_OFFSET + bank * 0x4000 + address - 0x8000


def synthetic_rom() -> bytearray:
    data = bytearray(PRG_OFFSET + PRG_SIZE)
    data[:4] = b"NES\x1a"
    data[4] = 32
    data[6:8] = bytes((0x12, 8))
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
    data[cpu_offset(0x08, 0xB7F9)] = 0xFF
    data[cpu_offset(0x0E, 0xBE0B)] = 0xFF
    data[cpu_offset(0x1E, 0xBDC2)] = 0xFF
    return data


def discard_area_renderer(
    tiles: tuple[tuple[int, ...], ...],
    graphics: AreaGraphics,
    output: Path,
) -> None:
    return None


def discard_world_renderer(
    tiles: tuple[tuple[int, ...], ...],
    graphics: AreaGraphics,
    output: Path,
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
        self.assertEqual(
            tuple(spec[7] for spec in WORLD_MAP_SPECS.values()),
            (0, 1, 3),
        )

    def test_world_destination_markers_follow_rom_tile_classes(self) -> None:
        self.assertEqual(_world_destination_marker("world", 0x10), "town")
        self.assertEqual(_world_destination_marker("world", 0x12), "castle")
        self.assertEqual(_world_destination_marker("world", 0x0B), "cave")
        self.assertEqual(_world_destination_marker("gottside", 0x11), "tower")
        self.assertEqual(_world_destination_marker("underworld", 0x07), "palace")
        self.assertEqual(_world_destination_marker("underworld", 0x1D), "lair")


class RomAtlasTests(unittest.TestCase):
    def test_arena_fresh_stake_payout_uses_native_fraction_rounding_not_decimal_float(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        fractions = (0, 25, 51, 76, 102, 128, 153, 179, 204, 230)
        assets._cpu_byte = Mock(side_effect=lambda bank, address: fractions[address - 0xA97B])
        self.assertEqual(assets.arena_payout(5, 2, 5), 13)
        self.assertEqual(assets.arena_payout(50, 2, 1), 105)
        self.assertIsNone(assets.arena_payout(51, 2, 1))
        self.assertIsNone(assets.arena_payout(1, 2, 10))
    def test_native_transition_directory_preserves_record_widths_and_floor_terminators(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        pointer = cpu_offset(8, 0xB974)
        assets._data[pointer:pointer + 2] = (0xBA00).to_bytes(2, "little")
        start = cpu_offset(8, 0xBA00)
        data = bytes((1, 0xE1, 2, 0xA2, 3, 4, 255, 255))
        assets._data[start:start + len(data)] = data
        records = assets.transition_records()
        self.assertEqual(records[area_key(1, 0)], ((0x61, 2, 1),))
        self.assertEqual(records[area_key(1, 1)], ((0x22, 3, 4),))

    def test_walking_transition_uses_scan_ordinal_and_ignores_default_only_floor(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        source = AreaMapDescriptor(1, 0, 0, 4, 4, 9, 0)
        target = AreaMapDescriptor(1, 1, 0, 4, 4, 9, 0)
        assets._descriptor_by_key = {source.key: source, target.key: target}
        assets.transition_records = Mock(return_value={source.key: ((0x61, 1, 1),)})
        assets._transition_tiles = Mock(side_effect=lambda descriptor, live=None: ((2, 3),) if descriptor.key == source.key else ((0, 0), (3, 2)))
        assets._cpu_byte = Mock(return_value=255)
        route = assets.tile_transition_routes(1, 0)[0]
        self.assertEqual((route.x, route.y, route.destination_key, route.destination_x, route.destination_y),
                         (2, 3, target.key, 3, 2))
        assets.transition_records.return_value = {source.key: ((0, None, 1),)}
        assets._transition_tiles.return_value = ()
        assets._transition_tiles.side_effect = None
        assets._record_diagnostic = Mock()
        self.assertEqual(assets.tile_transition_routes(1, 0), ())
        assets._record_diagnostic.assert_not_called()

    def test_native_rate_trace_rejects_schema_mismatch_and_wrong_threshold(self) -> None:
        from tools.verify_rom import verify_threshold_trace
        assets = Mock()
        assets.land_encounter_threshold.return_value = (32, "Native threshold")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rates.tsv"
            header = "zone\tterrain\ttime\tstep\trepel\tstrength\tscent\tthreshold\n"
            path.write_text(header + "0\t0\t0\t0\t0\t10\t0\t32\n", encoding="ascii")
            self.assertEqual(verify_threshold_trace(path, assets), 1)
            assets.land_encounter_threshold.assert_called_once_with(0, 0, 0, 0, 0, 10, 0)
            path.write_text(header + "0\t0\t0\t0\t0\t10\t0\t31\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "disagrees"):
                verify_threshold_trace(path, assets)
            path.write_text("unrelated\tcolumns\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "columns"):
                verify_threshold_trace(path, assets)

    def test_land_threshold_uses_native_product_high_byte_repel_and_expiry(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        assets._cpu_bytes = Mock(side_effect=lambda bank, address, size: bytes((0, 0xA8)) if address == 0xA239 else bytes((0xE0, 10)))
        values = {0xA347: 32, 0xA33D: 2, 0xA27B: 128, 0xA283: 64, 0xA348: 192}
        assets._cpu_byte = Mock(side_effect=lambda bank, address: values[address])
        self.assertEqual(assets.land_encounter_threshold(0, 0, 0, 0, 0, 10, 0)[0], 32)
        self.assertEqual(assets.land_encounter_threshold(0, 0, 0x78, 0, 0, 10, 0)[0], 16)
        self.assertEqual(assets.land_encounter_threshold(0, 0, 0, 0, 2, 11, 0)[0], 24)
        self.assertEqual(assets.land_encounter_threshold(0, 0, 0, 0, 2, 15, 0)[0], 0)
        self.assertIn("wears off next step", assets.land_encounter_threshold(0, 0, 0, 0, 1, 10, 0)[1])
        self.assertEqual(assets.land_encounter_threshold(0, 0, 0, 3, 0, 10, 1)[0], 0)
        values[0xA27B] = 64
        self.assertEqual(assets.land_encounter_threshold(0, 0, 0, 3, 0, 10, 1)[0], 256)
        self.assertEqual(assets.land_encounter_threshold(0, 8, 0, 0, 0, 10, 0)[0], 0)

    def test_event_searches_use_native_prerequisites_without_becoming_loot(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._hidden_rows = Mock(return_value=(bytes((1, 0, 2, 3, 0xED)), bytes((1, 0, 4, 5, 0xEC)),
                                                bytes((1, 0, 6, 7, 0xE4))))
        assets.descriptor = Mock(return_value=AreaMapDescriptor(1, 0, 0, 32, 24, 9, 0))
        unknown = assets.conditional_search_overlay(1, 0, b"", bytes(27), frozenset(), 0, 2)
        self.assertTrue(all(point.kind == "entrance" for point in unknown.waypoints))
        self.assertIn("Face north", unknown.waypoints[0].detail)
        self.assertIn("Face east", unknown.waypoints[1].detail)
        self.assertIn("not known yet", unknown.waypoints[2].detail)
        flags = bytearray(50)
        flags[2], flags[15] = 4, 2
        tiles = bytearray(32 * 24)
        ready = assets.conditional_search_overlay(1, 0, bytes(flags), bytes(27), frozenset(), 0, 0, bytes(tiles))
        self.assertEqual(ready.waypoints[0].detail, "Ready")
        tiles[11 * 32 + 20] = 3
        changed = assets.conditional_search_overlay(1, 0, bytes(flags), bytes(27), frozenset(), 0, 0, bytes(tiles))
        self.assertTrue(changed.waypoints[0].completed)

    def test_special_relative_world_exit_does_not_claim_preserved_arrival(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        assets._exit_routes = ()
        route = assets.exit_routes(0x41, 0)[0]
        self.assertEqual(route.layer_key, "world")
        self.assertIsNone(route.destination_y)
        self.assertIn("3 steps in Chapter 1, otherwise 2", route.arrival_note)
        self.assertIn("south", route.arrival_note)

    def test_padequia_chest_event_gate_does_not_fabricate_pickup_completion(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(4, 0, 0, 1, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        point = MapWaypoint(0, 0, "Padequia Seed", "Available", "collectibles", marker="chest")
        assets._feature_templates = {descriptor.key: (FeatureTemplate(point, 0, reward_handler=0xE2),)}
        ready = assets.feature_overlay(4, 0, bytes(27), event_flags=bytes(50))
        self.assertEqual(ready.waypoints[0].detail, "Available")
        events = bytearray(50)
        events[0x18] = 1
        blocked = assets.feature_overlay(4, 0, bytes(27), event_flags=bytes(events))
        self.assertIn("No longer available", blocked.waypoints[0].detail)
        self.assertFalse(blocked.waypoints[0].completed)
        unknown = assets.feature_overlay(4, 0, bytes(27))
        self.assertEqual(unknown.waypoints[0].detail, "Not known yet")

    def test_native_pattern_frame_excludes_current_queued_nmi_upload(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        assets._cpu_bytes = Mock(side_effect=lambda bank, pointer, size: bytes([pointer >> 8]) * size)
        ram = bytearray(0x800)
        ram[0x28] = 1
        ram[0x3C] = 15
        ram[0x573] = 0xA0
        ram[0x574] = ram[0x576] = 0x40
        ram[0x57C] = 0x89
        ram[0x57E] = 0x8A
        ram[0x1F] = 0x20
        ram[0x50B] = 4
        for ordinal in range(4):
            start = 0x300 + ordinal * 19
            ram[start:start + 3] = bytes((0x94, 16, ordinal * 16))
        indices = bytes((0x40, 0x41, 0x42, 0x43)) + bytes(132)
        self.assertEqual(assets.native_pattern_frame(bytes(ram), indices),
                         tuple((index, bytes([0x8A]) * 16) for index in range(4)))

    def test_native_pattern_overlap_uses_latest_trigger_not_highest_group(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        assets._cpu_bytes = Mock(side_effect=lambda bank, pointer, size: bytes([pointer >> 8]) * size)
        ram = bytearray(0x800)
        ram[0x28] = 1
        ram[0x3C] = 0x2A
        ram[0x573] = 0x0A
        ram[0x578] = ram[0x57A] = 0x40
        ram[0x580] = 0x8A
        ram[0x582] = 0x89
        indices = bytes((0x40, 0x41, 0x42, 0x43)) + bytes(132)
        updates = assets.native_pattern_frame(bytes(ram), indices)
        self.assertEqual(updates, tuple((index, bytes([0x8A]) * 16) for index in range(4)))

    def test_native_pattern_frame_does_not_invent_frozen_menu_phase(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        assets._cpu_bytes = Mock()
        ram = bytearray(0x800)
        ram[0x28] = 1
        ram[0x3E] = 1
        ram[0x58E] = 2
        ram[0x573] = 0x80
        ram[0x574] = 0x40
        self.assertEqual(assets.native_pattern_frame(bytes(ram), bytes(136)), ())
        assets._cpu_bytes.assert_not_called()
        self.assertEqual(assets.native_pattern_frame(bytes(0x58E), bytes(136)), ())

    def test_portable_replay_memory_enforces_chunks_regions_and_corruption_bounds(self) -> None:
        from struct import pack
        from tools.verify_rom import replay_memory

        ram_field = b"RAM\x00" + pack("<I", 0x800) + bytes(0x800)
        wram_field = b"WRAM" + pack("<I", 0x2000) + bytes(0x2000)
        body = pack("<BI", 1, len(ram_field)) + ram_field + pack("<BI", 16, len(wram_field)) + wram_field
        header = b"FCS\xff" + pack("<I", len(body)) + bytes(8)
        self.assertEqual(replay_memory(header + body), (bytes(0x800), bytes(0x2000)))
        with self.assertRaises(ValueError):
            replay_memory(header + body[:-1])
        corrupt = bytearray(header + body)
        corrupt[25:29] = pack("<I", 0xFFFFFFFF)
        with self.assertRaises(ValueError):
            replay_memory(bytes(corrupt))
        duplicated = body + pack("<BI", 1, len(ram_field)) + ram_field
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            replay_memory(b"FCS\xff" + pack("<I", len(duplicated)) + bytes(8) + duplicated)

    def test_conditional_facing_rewards_keep_gold_separate_from_item_identity(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._hidden_rows = Mock(return_value=(bytes((1, 0, 2, 3, 0xE5)), bytes((1, 0, 4, 5, 0xE7))))
        assets.descriptor = Mock(return_value=AreaMapDescriptor(1, 0, 0, 10, 10, 9, 0))
        blocked = assets.conditional_search_overlay(1, 0, bytes(50), bytes(27), frozenset(), 0, 1)
        self.assertEqual(blocked.waypoints[0].title, "50 Gold")
        self.assertIn("Face north", blocked.waypoints[0].detail)
        flags = bytearray(27)
        flags[26] = 5
        completed = assets.conditional_search_overlay(1, 0, bytes(50), bytes(flags), frozenset(), 0, 0)
        self.assertTrue(all(point.completed for point in completed.waypoints))

    def test_conditional_search_uses_event_item_facing_and_pickup_states(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._hidden_rows = Mock(return_value=(bytes((1, 0, 2, 3, 0xE8)), bytes((1, 0, 4, 5, 0xE9))))
        assets.descriptor = Mock(return_value=AreaMapDescriptor(1, 0, 0, 10, 10, 9, 0))
        events = bytearray(50)
        events[11] = 2
        ready = assets.conditional_search_overlay(1, 0, bytes(events), bytes(27), frozenset(), 1, 0)
        self.assertEqual(ready.waypoints[0].detail, "Search here")
        blocked = assets.conditional_search_overlay(1, 0, bytes(events), bytes(27), frozenset((0x75,)), 1, 1)
        self.assertIn("already carried", blocked.waypoints[0].detail)
        self.assertIn("Face north", blocked.waypoints[1].detail)
        flags = bytearray(27)
        flags[26] = 8
        collected = assets.conditional_search_overlay(1, 0, bytes(events), bytes(flags), frozenset(), 1, 0)
        self.assertTrue(collected.waypoints[1].completed)
        unknown = assets.conditional_search_overlay(1, 0, bytes(events), b"", frozenset(), 1, 0)
        self.assertIn("unknown", unknown.waypoints[1].detail)

    def test_native_world_exits_preserve_direction_and_real_world_layer(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        assets._exit_routes = ()
        start = cpu_offset(0x12, 0xB8C6)
        assets._data[start:start + 8] = bytes((17, 13, 22, 16, 18, 19, 13, 16))
        routes = assets.exit_routes(0x3E, 0)
        self.assertEqual(tuple(route.direction for route in routes), (0, 1, 2, 3))
        self.assertTrue(all(route.layer_key == "gottside" for route in routes))
        self.assertEqual((routes[2].destination_x, routes[2].destination_y), (18, 19))

    def test_special_conditional_exit_rectangles_match_native_arrival_priority(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        assets._exit_routes = ()
        assets._descriptor_by_key = {
            area_key(0x3F, floor): AreaMapDescriptor(0x3F, floor, 0, 20, 24, 9, 0)
            for floor in (1, 2)
        }
        routes = assets.exit_routes(0x3F, 1)
        for x, y, expected in ((12, 4, (10, 6)), (5, 4, (5, 6)), (12, 6, (5, 6)),
                               (1, 10, (6, 10)), (5, 10, (6, 10))):
            matching = tuple(route for route in routes if route.x <= x < route.x + route.width and route.y <= y < route.y + route.height)
            self.assertEqual(len(matching), 1)
            self.assertEqual((matching[0].destination_x, matching[0].destination_y), expected)

    def test_special_exit_routes_keep_generic_floors_and_exact_arrivals(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        assets._exit_routes = ()
        assets._descriptor_by_key = {
            area_key(0x33, 0): AreaMapDescriptor(0x33, 0, 0, 32, 32, 9, 0),
            area_key(0x36, 3): AreaMapDescriptor(0x36, 3, 0, 32, 32, 9, 0),
        }
        entrance = assets.exit_routes(0x1C, 0)[0]
        self.assertEqual((entrance.destination_key, entrance.destination_x, entrance.destination_y),
                         (area_key(0x33, 0), 23, 3))
        special = assets.exit_routes(0x36, 1)[0]
        self.assertEqual((special.destination_key, special.destination_x, special.destination_y),
                         (area_key(0x36, 3), 8, 15))
        self.assertEqual(assets.exit_routes(0x36, 0), ())

    def test_native_weapon_passives_distinguish_recoil_from_hp_recovery(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        self.assertIn("Hurts you", assets.equipment_passives(0x13)[0])
        self.assertIn("quarter of damage dealt, rounded down, plus 1 HP", assets.equipment_passives(0x1C)[0])
        self.assertIn("Heals you", assets.equipment_passives(0x1C)[0])
        self.assertEqual(assets.equipment_passives(0), ())

    def test_native_weapon_passives_preserve_target_lists_and_integer_rounding(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        assets._cpu_bytes = Mock(return_value=bytes((0x40, 0x6F, 0x8C, 0x93, 0x9E, 0xA3, 0xA1, 0xB8)))
        assets.monster_name = Mock(side_effect=lambda monster_id: f"Enemy {monster_id}")
        self.assertIn("1.5x damage", assets.equipment_passives(0x15)[0])
        assets._cpu_bytes.assert_called_once_with(0x11, 0xA73F, 8)
        self.assertIn("Enemy 168", assets.equipment_passives(0x0E)[0])
        self.assertIn("Deals 1 damage", assets.equipment_passives(0x0F)[0])
        self.assertIn("susceptible enemies", assets.equipment_passives(0x0F)[0])
        self.assertIn("2 attacks in 3", assets.equipment_passives(0x12)[0])

    def test_native_defensive_and_followup_effects_keep_eligibility_and_thresholds(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        self.assertIn("first hit", assets.equipment_passives(0x16)[0])
        self.assertIn("1 in 6 physical hits", assets.equipment_passives(0x33)[0])
        self.assertIn("1 in 8 spells", assets.equipment_passives(0x36)[0])
        self.assertIn("MP remaining", assets.equipment_passives(0x36)[0])
        self.assertIn("ordinary physical hit", assets.equipment_passives(0x38)[0])
        self.assertIn("Half the time", assets.equipment_passives(0x38)[0])
        self.assertIn("rounded down, plus 1 HP", assets.equipment_passives(0x41)[0])
        self.assertIn("attack-spell damage", assets.equipment_passives(0x41)[0])

    def test_formation_entry_chances_reproduce_inclusive_native_random_bound(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._formation_entries = Mock(return_value=(("First", 1), ("Second", 1)))
        self.assertEqual(assets.formation_entry_chances(0, 0x3FFF), (("First", 256),))
        assets._formation_entries.return_value = (("Zero edge", 0), ("Next", 2))
        self.assertEqual(assets.formation_entry_chances(0, 0x3FFF), (("Zero edge", 128), ("Next", 128)))
        assets._formation_entries.return_value = (("First", 128), ("Second", 127))
        self.assertEqual(assets.formation_entry_chances(0, 0x3FFF), (("First", 129), ("Second", 127)))

    def test_indoor_encounter_directory_uses_native_stride_and_no_pool_sentinel(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        assets.has_area = Mock(return_value=True)
        assets._formation_pool = Mock(return_value=(7, (("Slime", 3),)))
        start = cpu_offset(0x18, 0xA23B)
        assets._data[start:start + 2] = (0xA700).to_bytes(2, "little")
        start = cpu_offset(0x18, 0xA700)
        assets._data[start:start + 7] = bytes((2, 5, 0xFF, 4, 7, 0xFF, 0xFF))
        assets._data[cpu_offset(0x18, 0xA474 + 2)] = 2
        assets._data[cpu_offset(0x18, 0xA474 + 4)] = 2
        self.assertEqual(assets.indoor_encounter_pool(0, 4, 0), (7, (("Slime", 3),)))
        assets._formation_pool.assert_called_with(7, 0x3FFF)
        self.assertIsNone(assets.indoor_encounter_pool(0, 4, 1))
        self.assertIsNone(assets.indoor_encounter_pool(0, 3, 0))

    def test_native_frame_render_preserves_live_palette_and_pattern_updates(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(2, 0, 0, 1, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        patterns = (bytes(16),) * 136
        graphics = AreaGraphics(((0, 1, 2, 3),), (0,), patterns, (9,) * 12, (0,), ())
        assets._area_layout = Mock(return_value=(((0,),), graphics))
        assets._area_palette = Mock(return_value=(8,) * 12)
        assets._area_renderer = Mock()
        assets._write_manifest = Mock()
        with tempfile.TemporaryDirectory() as directory:
            assets.cache_directory = Path(directory)
            assets.render_area_map(descriptor.key, palette_context=(1, False, False),
                                   live_palette=(1,) * 12, pattern_updates=((5, bytes((2,)) * 16),))
        rendered = assets._area_renderer.call_args.args[1]
        self.assertEqual(rendered.palette, (1,) * 12)
        self.assertEqual(rendered.patterns[5], bytes((2,)) * 16)
        self.assertEqual(rendered.patterns[4], bytes(16))

    def test_native_pattern_frame_uses_phase_and_deduplicated_ppu_slots(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        ram = bytearray(0x800)
        ram[0x28] = 1
        ram[0x573] = 0x80
        ram[0x574] = 20
        ram[0x57C] = 0x81
        ram[0x584] = 0
        ram[0x3C] = 15
        ram[0x58D] = 3
        start = cpu_offset(0x1D, 0x810C)
        assets._data[start:start + 64] = bytes(range(64))
        mapping = bytearray((255,)) * 136
        mapping[0:4] = bytes((20, 21, 22, 23))
        mapping[8] = 21
        updates = dict(assets.native_pattern_frame(bytes(ram), bytes(mapping)))
        self.assertEqual(updates[0], bytes(range(16)))
        self.assertEqual(updates[3], bytes(range(48, 64)))
        self.assertEqual(updates[8], updates[1])
        self.assertEqual(len(updates), 5)

    def test_display_frame_changes_reuse_static_loader_and_update_native_variant(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._display_layers_cache = {}
        assets.render_world_map = Mock()
        layer = MapLayer("world", "World", "World", Path("world.png"), image_loader=lambda: Path("world.png"))
        first = assets.display_layers((layer,), 0, 0, 0, animated_layer=("world", tuple(range(1, 13))))
        second = assets.display_layers((layer,), 0, 0, 0, animated_layer=("world", tuple(range(2, 14))))
        self.assertIs(first[0].image_loader, second[0].image_loader)
        self.assertNotEqual(first[0].image_variants[0].image_path, second[0].image_variants[0].image_path)
        self.assertEqual(first[0].image_variants[0].title, "Live frame")

    def test_native_palette_frame_accepts_only_supported_initialized_shadow(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        ram = bytearray(0x800)
        self.assertIsNone(assets.native_palette_frame(bytes(ram)))
        ram[0x5FD:0x609] = bytes(range(1, 13))
        self.assertEqual(assets.native_palette_frame(bytes(ram)), tuple(range(1, 13)))
        ram[0x28] = 1
        self.assertIsNone(assets.native_palette_frame(bytes(ram)))
        ram[0x28] = 0x18
        ram[0x600] = 0xFF
        self.assertIsNone(assets.native_palette_frame(bytes(ram)))

    def test_native_world_scan_entries_match_forward_and_reverse_segments(self) -> None:
        data = bytes((0x1F, 0x1F, 0x3F, 0x3F, 0x5F, 0x5F, 0x7F, 0x7F))
        full = decode_world_row(data, 0, 256)
        for coordinate in (0, 63, 64, 127, 128, 191, 192, 255):
            self.assertEqual(decode_world_point(data, 0, coordinate, 4, 8), full[coordinate])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            decode_world_point(b"", 0, 0)

    def test_native_reveal_tile_remains_visible_outside_selected_room_class(self) -> None:
        graphics = AreaGraphics((), (), (), (), (), ())
        with tempfile.TemporaryDirectory() as directory:
            normal = Path(directory) / "normal.png"
            revealed = Path(directory) / "revealed.png"
            with patch("map_renderer._tile_image", side_effect=lambda tile, data: Image.new("RGB", (16, 16), "red" if tile == 0 else "blue")):
                render_area_map(((0, 0x20),), graphics, normal, room_class=0)
                render_area_map(((0, 0x20),), graphics, revealed, room_class=0, reveal_tile=0)
            with Image.open(normal) as first, Image.open(revealed) as second:
                self.assertEqual(first.getpixel((24, 8)), (0, 0, 255))
                self.assertEqual(second.getpixel((24, 8)), (255, 0, 0))

    def test_native_exit_graph_preserves_asymmetry_and_source_rectangle(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        assets._exit_routes = None
        assets._descriptor_by_key = {
            area_key(4, floor): AreaMapDescriptor(4, floor, 0, 32, 32, 9, 0)
            for floor in (0, 1)
        }
        start = cpu_offset(0x12, 0xB970)
        assets._data[start:start + 2] = (0xBA00).to_bytes(2, "little")
        start = cpu_offset(0x12, 0xBA00)
        assets._data[start:start + 9] = bytes((4, 0x80, 0x82, 3, 0x21, 1, 5, 6, 0xFF))
        routes = assets.exit_routes(4, 0)
        self.assertEqual(len(routes), 1)
        self.assertEqual((routes[0].x, routes[0].y, routes[0].width, routes[0].height), (2, 3, 2, 3))
        self.assertEqual((routes[0].destination_key, routes[0].destination_x, routes[0].destination_y), (area_key(4, 1), 5, 6))
        self.assertEqual(assets.exit_routes(4, 1), ())

    def test_stepguard_projection_only_protects_native_swamp_and_barrier(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(4, 0, 0, 3, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        assets._area_layout = Mock(return_value=(((0, 1, 2),), Mock(behaviors=(1, 2, 5))))
        assets._feature_templates = {descriptor.key: tuple(
            FeatureTemplate(MapWaypoint(index, 0, title, kind="hazards", marker="hazard"), behavior=behavior)
            for index, (title, behavior) in enumerate((("Swamp", 1), ("Barrier", 2), ("Pit", 5)))
        )}
        protected = assets.feature_overlay(4, 0, protected_hazards=frozenset((1, 2)))
        self.assertEqual(tuple(point.marker for point in protected.waypoints),
                         ("hazard-protected", "hazard-protected", "hazard"))
        expired = assets.feature_overlay(4, 0)
        self.assertEqual(tuple(point.marker for point in expired.waypoints), ("hazard",) * 3)

    def test_hazards_ignore_exterior_padding_and_out_of_bounds_markers(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(4, 0, 0, 5, 3, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        tiles = ((0, 1, 1, 1, 1), (2, 1, 0, 2, 1), (0, 1, 1, 1, 1))
        assets._area_layout = Mock(return_value=(tiles, Mock(behaviors=(0, 0x80, 5))))
        assets._arrival_points = Mock(return_value=((99, 99), (-1, -1)))
        assets._feature_templates = {descriptor.key: tuple(
            FeatureTemplate(MapWaypoint(x, y, "Pitfall", kind="hazards", marker="hazard"), behavior=5)
            for x, y in ((0, 1), (3, 1), (5, 1), (-1, 1))) }
        overlay = assets.feature_overlay(4, 0, position=(2, 1))
        self.assertEqual(tuple((point.x, point.y) for point in overlay.waypoints), ((3, 1),))

    def test_native_lock_projection_resolves_reserve_and_companion_inputs(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(4, 0, 0, 1, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        point = MapWaypoint(0, 0, "Magic Key door", kind="locks", marker="magic-door")
        assets._feature_templates = {descriptor.key: (FeatureTemplate(point),)}
        available = assets.feature_overlay(4, 0, active_keys=frozenset(), reserve_keys=frozenset((0x72,)),
                                            reserve_accessible=True, companion_magic_access=False)
        self.assertEqual(available.waypoints[0].marker, "door-ready")
        self.assertNotIn("active party", available.waypoints[0].detail)
        blocked = assets.feature_overlay(4, 0, active_keys=frozenset(), reserve_keys=frozenset((0x72,)),
                                          reserve_accessible=False, companion_magic_access=False)
        self.assertEqual(blocked.waypoints[0].marker, "magic-door")
        companion = assets.feature_overlay(4, 0, active_keys=frozenset(), chapter=3,
                                            reserve_accessible=False, companion_magic_access=True)
        self.assertEqual(companion.waypoints[0].marker, "door-ready")
        absent = assets.feature_overlay(4, 0, active_keys=frozenset(), chapter=3,
                                         reserve_accessible=False, companion_magic_access=False)
        self.assertEqual(absent.waypoints[0].marker, "magic-door")

    def test_hidden_reward_invalid_mask_retains_valid_neighbor_and_one_diagnostic(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets.region = "US"
        assets._hidden_treasures = None
        furniture = (bytes((2, 0, 1, 1, 0x53, 0, 3)), bytes((2, 0, 2, 1, 0x53, 0, 1)))
        assets._hidden_rows = Mock(side_effect=lambda address, width: furniture if address == 0xBCED else ())
        rewards = assets.hidden_treasures()
        self.assertEqual(len(rewards), 1)
        self.assertEqual(rewards[0].x, 2)
        self.assertEqual(len(assets.diagnostics), 1)
        self.assertEqual(assets.hidden_treasures(), rewards)
        self.assertEqual(len(assets.diagnostics), 1)

    def test_hidden_record_rejection_does_not_bypass_the_parser_bound(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets._cpu_byte = Mock(return_value=0)
        assets.has_area = Mock(return_value=False)
        with self.assertRaisesRegex(ValueError, "unterminated"):
            assets._hidden_rows(0xB000, 7)
        self.assertEqual(assets.has_area.call_count, 64)

    def test_shape_fourteen_uses_native_special_graphics_bank(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        start = cpu_offset(8, 0xAEB7 + 8 * 2)
        assets._data[start:start + 2] = (0x8100).to_bytes(2, "little")
        ordinary = cpu_offset(0x0C, 0x8100)
        special = cpu_offset(0x1D, 0x8100)
        assets._data[ordinary:ordinary + 64] = bytes((1,)) * 64
        assets._data[special:special + 64] = bytes((2,)) * 64
        self.assertEqual(assets._tile_patterns(0, 8, 0x0E), (bytes((2,)) * 16,) * 4)

    def test_equipment_protection_uses_native_packed_nibbles(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        start = cpu_offset(0x13, 0xB540)
        assets._data[start:start + 7] = bytes((0x32, 0x34, 0x35, 0x37, 0x3C, 0x41, 0x43))
        start = cpu_offset(0x13, 0xB547)
        assets._data[start:start + 4] = bytes((0x78, 0xF9, 0x79, 0x08))
        self.assertEqual(assets.equipment_protection(0x32), (("Breath damage", 170),))
        self.assertEqual(len(assets.equipment_protection(0x37)), 4)
        self.assertEqual(assets.equipment_protection(0x20), ())

    def test_encounter_pool_applies_time_masks_and_expands_group_entries(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        assets.monster_name = Mock(side_effect=lambda identifier: f"Monster {identifier}")
        for address, value in ((0xA245, 0xA500), (0xA239, 0x92AA), (0xA237, 0xB000)):
            start = cpu_offset(0x18, address)
            assets._data[start:start + 2] = value.to_bytes(2, "little")
        record = bytearray((0, 0) + (0xFF,) * 14)
        record[2] = 1
        record[6] = 2
        record[14] = 0
        start = cpu_offset(0x18, 0x92AA)
        assets._data[start:start + 16] = record
        start = cpu_offset(0x18, 0xB000)
        assets._data[start:start + 6] = bytes((0, 0, 3, 0xFF, 0xFF, 0xFF))
        for ordinal, weight in ((0, 2), (4, 3), (12, 4)):
            assets._data[cpu_offset(0x18, 0xA28D + ordinal)] = weight
        day = assets.encounter_pool(4, 0, 0, 0, 0)
        night = assets.encounter_pool(4, 0, 0, 0, 0x78)
        self.assertEqual(day, (0, (("Monster 1", 2), ("Monster 3", 4))))
        self.assertEqual(night, (0, (("Monster 2", 3), ("Monster 3", 4))))
        self.assertIsNone(assets.encounter_pool(4, 0, 0, 0, 0, 2))

    def test_native_spell_milestones_preserve_variable_descriptor_and_hero_alias(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        assets.indexed_name = Mock(side_effect=lambda category, identifier: ("Blaze", "Blazemore")[identifier])
        for address, value in ((0xA10B, 0xA400), (0xA117, 0xA408)):
            start = cpu_offset(0x12, address)
            assets._data[start:start + 2] = value.to_bytes(2, "little")
        assets._data[cpu_offset(0x12, 0xA400)] = 3
        start = cpu_offset(0x12, 0xA408)
        assets._data[start:start + 2] = bytes((3, 0x8F))
        self.assertEqual(assets.spell_milestones(0), (("Blaze", 3, False), ("Blazemore", 15, True)))
        self.assertEqual(assets.spell_milestones(8), assets.spell_milestones(0))
        self.assertEqual(assets.spell_milestones(5), ())

    def test_native_drop_rank_seven_and_resistance_success_polarity(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        assets.monster_name = Mock(return_value="Monster")
        assets.indexed_name = Mock(return_value="Blaze")
        start = cpu_offset(0x18, 0x8046)
        assets._data[start + 8] = 1
        assets._data[start + 20] = 7
        assets._data[cpu_offset(0x12, 0x9285 + 7)] = 1
        assets._data[cpu_offset(0x13, 0xB736)] = 3
        for resistance, expected in enumerate(("Susceptible", "Partial resistance", "Strong resistance", "Immune")):
            assets._data[start + 15] = resistance << 6
            monster = assets.monster_definition(0)
            self.assertIsNotNone(monster)
            self.assertEqual(monster.drop_denominator, 4096)
            self.assertEqual(monster.resistances[0], ("Blaze", expected))

    def test_typed_collection_catalog_excludes_empty_and_trap_chests(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        assets._collectible_catalog = None
        start = cpu_offset(0x1E, 0xBDC2)
        assets._data[start:start + 4] = bytes((4, 0, 3, 0xFF))
        start = cpu_offset(0x1E, 0xBEB9)
        assets._data[start:start + 3] = bytes((0x69, 0xFF, 0xFE))
        assets._data[cpu_offset(0x1E, 0xBCED)] = 0xFF
        assets._data[cpu_offset(0x1E, 0xBF59)] = 0xFF
        catalog = assets.collectible_catalog()
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].item_id, 0x69)
        self.assertFalse(catalog[0].collected(bytes(27)))
        self.assertTrue(catalog[0].collected(bytes((0x80,))))
        self.assertIsNone(catalog[0].collected(b""))
        self.assertIs(catalog, assets.collectible_catalog())

    def test_live_final_key_door_is_not_mistaken_for_an_opened_tile(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(4, 0, 0, 1, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        point = MapWaypoint(0, 0, "Final Key door", kind="locks", marker="final-door")
        assets._feature_templates = {descriptor.key: (FeatureTemplate(point),)}
        graphics = AreaGraphics((), (), (), (), (0x97,), ())
        assets._area_layout = Mock(return_value=(((0,),), graphics))
        overlay = assets.feature_overlay(4, 0, bytes(27), bytes(1), frozenset())
        self.assertIsNotNone(overlay)
        self.assertFalse(overlay.waypoints[0].completed)
        self.assertEqual(overlay.waypoints[0].marker, "final-door")

    def test_monster_catalog_uses_native_stats_reward_words_and_drop_mask(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        assets.monster_name = Mock(return_value="Native monster")
        assets.indexed_name = Mock(return_value="Blaze")
        start = cpu_offset(0x18, 0x8046)
        record = bytearray(22)
        record[:2] = (513).to_bytes(2, "little")
        record[2:9] = bytes((12, 7, 44, 45, 46, 7, 0xD3))
        record[15:19] = bytes((1, 1, 1, 2))
        assets._data[start:start + 22] = record
        monster = assets.monster_definition(0)
        self.assertIsNotNone(monster)
        self.assertEqual((monster.max_hp, monster.attack, monster.defense), (300, 301, 302))
        self.assertEqual((monster.experience, monster.gold, monster.drop_item_id), (513, 519, 0x53))

    def test_return_destinations_use_lsb_first_chapter_specific_lists(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        assets._submap_names = {}
        before = cpu_offset(0x10, 0x95B4)
        after = cpu_offset(0x10, 0x95C3)
        assets._data[before:before + 3] = bytes((2, 4, 0xFF))
        assets._data[after:after + 3] = bytes((6, 4, 0xFF))
        self.assertEqual(assets.return_destinations(0, bytes((2,))), ((4, "Endor"),))
        self.assertEqual(assets.return_destinations(4, bytes((1,))), ((6, "Branca"),))

    def test_all_special_chest_dispatches_have_classified_outcomes(self) -> None:
        self.assertEqual(_chest_reward(0xFF)[0], "Empty chest")
        self.assertEqual(_chest_reward(0xFE)[0], "Mimic chest")
        self.assertEqual(_chest_reward(0xFD)[0], "Man-eater chest")
        for value, name in ((0xEF, "Baron's Horn"), (0xEE, "Iron Safe"), (0xE3, "Lamp of Darkness"),
                            (0xE2, "Padequia Seed"), (0xE0, "Symbol of Faith")):
            title, detail = _chest_reward(value)
            self.assertEqual(title, name)
            self.assertEqual(detail, "Story reward")

    def test_damaged_and_wrong_sized_cached_images_are_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cached.png"
            path.write_bytes(b"not a PNG")
            self.assertFalse(_valid_cached_image(path, 16, 16))
            Image.new("RGB", (8, 8)).save(path)
            self.assertFalse(_valid_cached_image(path, 16, 16))
            Image.new("RGB", (16, 16)).save(path)
            self.assertTrue(_valid_cached_image(path, 16, 16))

    def test_routing_directory_allows_terminator_after_all_native_maps(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets._submap_names = {}
        pointer = cpu_offset(0x08, 0xB7F9)
        for map_id in range(0x49):
            start = pointer + map_id * 5
            assets._data[start:start + 5] = bytes((map_id, 0, 0, 0, 0))
        assets._data[pointer + 0x49 * 5] = 0xFF
        self.assertEqual(assets._world_destination_waypoints(), {"world": (), "gottside": (), "underworld": ()})

    def test_entity_roles_follow_native_interaction_selectors(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        record = cpu_offset(5, 0xB100)
        assets._data[record:record + 17] = bytes((0x10, 0, 0, 0, 1, 2, 3, 0,
                                                0x10, 0, 0, 0, 6, 4, 5, 0, 0))
        self.assertEqual(assets.map_actor_roles(5, 0xB100, 0), (("Weapon merchant", "shop"), ("Innkeeper", "healing")))
        self.assertEqual(assets.map_actor_roles(5, 0xB100, 0x80), ())
        assets._data[record + 4] = 5
        self.assertEqual(assets.map_actor_roles(5, 0xB100, 0)[0], ("House of Healing", "healing"))

    def test_shop_directories_do_not_bleed_into_adjacent_stock_tables(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        for index in range(3):
            pointer = cpu_offset(0x18, 0x802C + index * 2)
            assets._data[pointer:pointer + 2] = (0xB400 + index * 3).to_bytes(2, "little")
            record = cpu_offset(0x18, 0xB400 + index * 3)
            assets._data[record:record + 3] = bytes((2, 0, 0x80 | (index + 1)))
        assets._data[cpu_offset(0x18, 0xB409)] = 0xFF
        self.assertEqual(assets.town_shops(2), ((0, 1, (1,)), (0, 2, (2,)), (0, 3, (3,))))

    def test_native_shop_stock_price_and_equipment_eligibility(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        for shop_type in range(3):
            pointer = cpu_offset(0x18, 0x802C + shop_type * 2)
            assets._data[pointer:pointer + 2] = (0xB400 + shop_type * 16).to_bytes(2, "little")
            record = cpu_offset(0x18, 0xB400 + shop_type * 16)
            assets._data[record:record + 5] = bytes((2, 0, 2, 0x83, 0xFF))
        assets._data[cpu_offset(0x10, 0x8CE4 + 2)] = 2
        assets._data[cpu_offset(0x10, 0x8DE2 + 2)] = 10
        assets._data[cpu_offset(0x10, 0x8C65 + 2)] = 0b01000001
        assets._data[cpu_offset(0x10, 0x9DE0 + 2)] = 12
        assets._data[cpu_offset(0x10, 0x8D63 + 2)] = 0x9B
        self.assertEqual(assets.town_shops(2)[0], (0, 1, (2, 3)))
        self.assertEqual(assets.town_shops(3), ())
        self.assertEqual(assets.item_price(2, 2, 0), 1000)
        self.assertEqual(assets.equipment_bonus(2), 12)
        self.assertEqual(assets.equipment_traits(2), (0, 0x1B, 0x80))
        self.assertTrue(assets.equipment_eligible(2, 0))
        self.assertTrue(assets.equipment_eligible(2, 6))
        self.assertFalse(assets.equipment_eligible(2, 7))

    def test_native_name_decoder_preserves_initial_capitalization(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        pointer = cpu_offset(0x0B, 0xB057)
        assets._data[pointer:pointer + 2] = (0xB100).to_bytes(2, "little")
        record = cpu_offset(0x0B, 0xB100)
        assets._data[record:record + 4] = bytes((3, 0, 1, 0))
        assets._data[cpu_offset(0x0B, 0xBC40)] = 2
        assets._data[cpu_offset(0x0B, 0xBC41):cpu_offset(0x0B, 0xBC41) + 2] = bytes((0x0B, 0x0C))
        assets._data[cpu_offset(0x0B, 0xB034)] = 2
        assets._data[cpu_offset(0x0B, 0xB03C)] = 3
        self.assertEqual(assets.indexed_name(0, 0), "Aba")
        with self.assertRaises(ValueError):
            assets.indexed_name(11, 0)

    def test_monster_vitals_use_native_record_width_and_us_layout_gate(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets.region = "US"
        record = cpu_offset(0x18, 0x8046 + 3 * 22)
        assets._data[record + 4] = 44
        assets._data[record + 15] = 1
        assets._data[record + 3] = 24
        self.assertEqual(assets.monster_vitals(3), (300, 24))
        assets._data[record + 4] = 0xFF
        assets._data[record + 15] = 3
        self.assertEqual(assets.monster_vitals(3), (1200, 24))
        self.assertIsNone(assets.monster_vitals(214))
        assets.region = "Japan"
        self.assertIsNone(assets.monster_vitals(3))

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

    def test_world_destination_records_choose_exact_layers_and_coordinates(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        assets._submap_names = {}
        routes = cpu_offset(0x08, 0xB7F9)
        assets._data[routes:routes + 15] = bytes(
            (0x02, 0x00, 4, 5, 0, 0x1A, 0x20, 6, 7, 0, 0x26, 0x60, 8, 9, 0)
        )
        assets._data[routes + 15] = 0xFF
        positions = cpu_offset(0x0E, 0xBE0B)
        assets._data[positions:positions + 12] = bytes(
            (0x02, 10, 11, 0x1A, 12, 13, 0x26, 14, 15, 0x02, 16, 17)
        )
        assets._data[positions + 12] = 0xFF
        rows = {
            "world": [[0] * 20 for _ in range(20)],
            "gottside": [[0] * 20 for _ in range(20)],
            "underworld": [[0] * 20 for _ in range(20)],
        }
        rows["world"][11][10] = 0x10
        rows["world"][17][16] = 0x12
        rows["gottside"][13][12] = 0x11
        rows["underworld"][15][14] = 0x07
        assets.world_tile = Mock(side_effect=lambda key, x, y: rows[key][y][x])

        points = assets._world_destination_waypoints()

        self.assertEqual(
            tuple((point.x, point.y, point.marker) for point in points["world"]),
            ((10, 11, "town"), (16, 17, "castle")),
        )
        self.assertEqual(
            (points["gottside"][0].x, points["gottside"][0].y),
            (12, 13),
        )
        self.assertEqual(
            (points["underworld"][0].x, points["underworld"][0].y),
            (14, 15),
        )

    def test_area_stream_uses_documented_cross_bank_continuations(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        bank_09_end = cpu_offset(0x09, 0xBFD6)
        bank_0a_end = cpu_offset(0x0A, 0xBFD6)
        assets._data[bank_09_end:bank_09_end + 2] = bytes((1, 2))
        assets._data[cpu_offset(0x0A, 0x8000):cpu_offset(0x0A, 0x8000) + 2] = bytes((3, 4))
        assets._data[bank_0a_end:bank_0a_end + 2] = bytes((5, 6))
        assets._data[cpu_offset(0x0B, 0x8012):cpu_offset(0x0B, 0x8012) + 2] = bytes((7, 8))
        assets._data[cpu_offset(0x09, 0xBFD8):cpu_offset(0x09, 0xC000)] = bytes((0xEE,)) * 40
        assets._data[cpu_offset(0x0A, 0xBFD8):cpu_offset(0x0A, 0xC000)] = bytes((0xEF,)) * 40

        from_bank_09 = assets._area_stream(
            AreaMapDescriptor(0x2D, 7, 0, 1, 1, 0x09, bank_09_end)
        )
        from_bank_0a = assets._area_stream(
            AreaMapDescriptor(0x45, 4, 0, 1, 1, 0x0A, bank_0a_end)
        )

        self.assertEqual(from_bank_09[:4], bytes((1, 2, 3, 4)))
        self.assertEqual(from_bank_0a[:4], bytes((5, 6, 7, 8)))
        self.assertNotIn(0xEE, from_bank_09)
        self.assertNotIn(0xEF, from_bank_0a)

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

    def test_chest_marker_uses_rom_value_and_msb_collected_flag(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        descriptor = AreaMapDescriptor(2, 1, 0, 1, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        assets._hidden_treasures = ()
        graphics = AreaGraphics(
            ((0, 0, 0, 0),),
            (0,),
            (bytes(16),),
            (0,) * 12,
            (0x04,),
            (0,),
        )
        assets._area_layout = Mock(return_value=(((0,),), graphics))
        directory = cpu_offset(0x1E, 0xBDC2)
        assets._data[directory:directory + 4] = bytes((2, 1, 1, 0xFF))
        assets._data[cpu_offset(0x1E, 0xBEB9)] = ITEM_NAMES.index("Agility Seed")
        overlay = assets.feature_overlay(2, 1, bytes((0x80,)) + bytes(26))

        self.assertIsNotNone(overlay)
        self.assertEqual(overlay.waypoints[0].title, "Agility Seed")
        self.assertEqual(overlay.waypoints[0].detail, "Looted")
        self.assertTrue(overlay.waypoints[0].completed)
        changed = assets.feature_overlay(2, 1, bytes(27))
        self.assertFalse(changed.waypoints[0].completed)
        unknown = assets.feature_overlay(2, 1)
        self.assertIsNone(unknown.waypoints[0].completed)
        self.assertEqual(unknown.waypoints[0].marker, "chest-unknown")
        assets._area_layout.assert_called_once()

    def test_negative_chest_value_stays_neutral(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        directory = cpu_offset(0x1E, 0xBDC2)
        assets._data[directory:directory + 4] = bytes((3, 2, 1, 0xFF))
        assets._data[cpu_offset(0x1E, 0xBEB9)] = 0xFE

        self.assertEqual(assets._chest_records(3, 2), ((0, 0xFE),))

    def test_non_special_high_chest_value_decodes_gold_amount(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        descriptor = AreaMapDescriptor(3, 2, 0, 1, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        assets._hidden_treasures = ()
        graphics = AreaGraphics(
            ((0, 0, 0, 0),),
            (0,),
            (bytes(16),),
            (0,) * 12,
            (0x04,),
            (0,),
        )
        assets._area_layout = Mock(return_value=(((0,),), graphics))
        directory = cpu_offset(0x1E, 0xBDC2)
        assets._data[directory:directory + 4] = bytes((3, 2, 1, 0xFF))
        assets._data[cpu_offset(0x1E, 0xBEB9)] = 0x82

        overlay = assets.feature_overlay(3, 2)

        self.assertEqual(overlay.waypoints[0].title, "80 Gold")

    def test_chest_records_aliases_the_next_state_variant(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        directory = cpu_offset(0x1E, 0xBDC2)
        assets._data[directory:directory + 4] = bytes((3, 2, 1, 0xFF))
        assets._data[cpu_offset(0x1E, 0xBEB9)] = 0xFE

        self.assertEqual(assets._chest_records(3, 1), ((0, 0xFE),))

    def test_chest_records_returns_empty_after_fixed_directory(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        directory = cpu_offset(0x1E, 0xBDC2)
        assets._data[directory:directory + 82 * 3] = bytes(82 * 3)

        self.assertEqual(assets._chest_records(7, 7), ())

    def test_hidden_tables_keep_only_direct_furniture_and_search_items(self) -> None:
        data = synthetic_rom()
        furniture = cpu_offset(0x1E, 0xBCED)
        data[furniture:furniture + 8] = bytes(
            (0x02, 0x00, 29, 26, ITEM_NAMES.index("Medical Herb"), 0x01, 0x40, 0xFF)
        )
        search = cpu_offset(0x1E, 0xBF59)
        data[search:search + 11] = bytes(
            (0x0D, 0x00, 8, 20, 0xA3, 0x20, 0x00, 4, 6, 0xE7, 0xFF)
        )
        items = cpu_offset(0x1E, 0xBDB3)
        data[items + 3] = ITEM_NAMES.index("Small Medal")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dw4.nes"
            path.write_bytes(data)
            with patch("game.rom_assets._rom_region", return_value="US"):
                assets = DragonWarrior4RomAssets(
                    path,
                    Path(directory),
                    discard_area_renderer,
                    discard_world_renderer,
                )

            hidden = assets.hidden_treasures()

        self.assertEqual(
            tuple(
                (item.map_id, item.x, item.y, item.flag_index, item.reward, item.description)
                for item in hidden
            ),
            (
                (0x02, 29, 26, 190, "Medical Herb", "ROM furniture record at (29,26)"),
                (0x0D, 8, 20, 172, "Small Medal", "ROM search record at (8,20)"),
            ),
        )

    def test_search_table_decodes_high_bit_amount_as_gold(self) -> None:
        data = synthetic_rom()
        data[cpu_offset(0x1E, 0xBCED)] = 0xFF
        search = cpu_offset(0x1E, 0xBF59)
        data[search:search + 6] = bytes((0x0D, 0x00, 8, 20, 0xA7, 0xFF))
        data[cpu_offset(0x1E, 0xBDB3) + 7] = 0x82
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dw4.nes"
            path.write_bytes(data)
            with patch("game.rom_assets._rom_region", return_value="US"):
                assets = DragonWarrior4RomAssets(
                    path,
                    Path(directory),
                    discard_area_renderer,
                    discard_world_renderer,
                )

            hidden = assets.hidden_treasures()

        self.assertEqual(hidden[0].reward, "80 Gold")

    def test_hidden_tables_are_ignored_for_non_us_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dw4.nes"
            path.write_bytes(synthetic_rom())
            with patch("game.rom_assets._rom_region", return_value="Japan"):
                assets = DragonWarrior4RomAssets(
                    path,
                    Path(directory),
                    discard_area_renderer,
                    discard_world_renderer,
                )

            self.assertEqual(assets.hidden_treasures(), ())

    def test_hidden_item_marker_reports_container_and_looted_state(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        descriptor = AreaMapDescriptor(2, 1, 0, 1, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        assets._hidden_treasures = (
            HiddenTreasure(2, 1, 0, 0, 190, "Medical Herb", "Burland - drawer #4"),
        )
        graphics = AreaGraphics(
            ((0, 0, 0, 0),),
            (0,),
            (bytes(16),),
            (0,) * 12,
            (0xAB,),
            (0,),
        )
        assets._area_layout = Mock(return_value=(((0,),), graphics))
        flags = bytearray(27)

        available = assets.feature_overlay(2, 1, bytes(flags))
        flags[23] = 0x40
        looted = assets.feature_overlay(2, 1, bytes(flags))

        point = available.waypoints[0]
        self.assertEqual((point.title, point.kind, point.marker), ("Medical Herb", "collectibles", "drawer"))
        self.assertTrue(point.detail.startswith("In a drawer · Available"))
        self.assertFalse(point.completed)
        self.assertTrue(looted.waypoints[0].completed)

    def test_feature_overlay_distinguishes_entrances_and_locks(self) -> None:
        assets = DragonWarrior4RomAssets.__new__(DragonWarrior4RomAssets)
        assets._prg_offset = PRG_OFFSET
        assets._data = synthetic_rom()
        descriptor = AreaMapDescriptor(3, 1, 0, 10, 1, 9, 0)
        assets._descriptor_by_key = {descriptor.key: descriptor}
        assets._hidden_treasures = ()
        graphics = AreaGraphics(
            ((0, 0, 0, 0),),
            (0,),
            (bytes(16),),
            (0,) * 12,
            (0x04, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0C, 0x31, 0x95, 0x96),
            (0,),
        )
        assets._area_layout = Mock(
            return_value=(((0, 1, 2, 3, 4, 5, 6, 7, 8, 9),), graphics)
        )

        overlay = assets.feature_overlay(3, 1)

        self.assertIsNotNone(overlay)
        self.assertEqual(
            tuple((point.kind, point.marker) for point in overlay.waypoints),
            (
                ("collectibles", "chest-unknown"),
                ("entrance", "exit"),
                ("entrance", "exit"),
                ("entrance", "stairs-up"),
                ("entrance", "stairs-down"),
                ("entrance", "travel-door"),
                ("entrance", "exit"),
                ("locks", "thief-door"),
                ("locks", "magic-door"),
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
            underworld_table = cpu_offset(0x0B, 0xAE89)
            for row in range(54):
                data[
                    underworld_table + row * 4:underworld_table + row * 4 + 4
                ] = bytes((0x00, 0x80, 2, 2))
            rom = root / "dw4.nes"
            rom.write_bytes(data)
            renderer = Mock()
            assets = DragonWarrior4RomAssets(
                rom,
                root / "state",
                discard_area_renderer,
                renderer,
            )
            overworld_graphics = object()
            overworld_graphics = AreaGraphics(
                ((0, 0, 0, 0),),
                (0,),
                (bytes(16),),
                (0,) * 12,
                (0,),
                (0,),
            )
            assets._area_graphics = Mock(return_value=overworld_graphics)
            assets._data = bytearray(assets._data)
            palette = cpu_offset(0x1E, 0xA2E3)
            assets._data[palette:palette + 12] = bytes(range(12))
            assets._data[palette + 8 * 12:palette + 9 * 12] = bytes(range(12, 24))

            assets.render_world_map("gottside")

            rows, graphics, _ = renderer.call_args.args
            self.assertEqual(len(rows), 64)
            self.assertEqual(rows[0], (0,) * 64)
            self.assertEqual(graphics.palette, tuple(range(12)))
            descriptor = assets._area_graphics.call_args.args[0]
            self.assertEqual(descriptor.tileset, 0)
            self.assertEqual(WORLD_MAP_SPECS["gottside"][6], 16)

            assets.render_world_map("underworld")
            underworld_graphics = renderer.call_args.args[1]
            self.assertEqual(underworld_graphics.palette, tuple(range(12, 24)))


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

    def test_world_renderer_draws_overworld_tileset_graphics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "world.png"
            water = bytes((0xFF,) * 8 + (0,) * 8)
            grass = bytes((0,) * 8 + (0xFF,) * 8)
            graphics = AreaGraphics(
                ((0, 0, 0, 0), (1, 1, 1, 1)),
                (0, 0),
                (water, grass),
                (0x21, 0x2A, 0x10) * 4,
                (0x83, 0x00),
                (0, 0),
            )

            render_world_map(((0, 1), (1, 0)), graphics, output)

            with Image.open(output) as image:
                self.assertEqual(image.size, (32, 32))
                self.assertEqual(image.getpixel((0, 0)), NES_PALETTE[0x21])
                self.assertEqual(image.getpixel((16, 0)), NES_PALETTE[0x2A])
                self.assertEqual(image.getpixel((0, 16)), NES_PALETTE[0x2A])

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