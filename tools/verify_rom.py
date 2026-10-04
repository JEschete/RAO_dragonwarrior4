from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
from zipfile import ZipFile
from PIL import Image


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from game.rom_assets import DragonWarrior4RomAssets
from game.battle import BATTLE_MEMORY_SIZE, read_battle_state
from game.state import read_state
from map_renderer import render_area_map, render_world_map


def replay_regions(data: bytes) -> dict[bytes, bytes]:
    if len(data) < 16 or len(data) > 262144 or data[:4] != b"FCS\xff":
        raise ValueError("Unsupported or oversized legacy FCEUX replay")
    if struct.unpack_from("<I", data, 4)[0] != len(data) - 16 or data[12:16] != bytes(4):
        raise ValueError("Compressed or inconsistent legacy replay header")
    offset = 16
    regions = {}
    while offset < len(data):
        if offset + 5 > len(data):
            raise ValueError("Truncated replay chunk")
        kind, length = struct.unpack_from("<BI", data, offset)
        offset += 5
        end = offset + length
        if end > len(data):
            raise ValueError("Replay chunk crosses file boundary")
        while offset < end:
            if offset + 8 > end:
                raise ValueError("Truncated replay field")
            label, size = struct.unpack_from("<4sI", data, offset)
            offset += 8
            if offset + size > end:
                raise ValueError("Replay field crosses chunk boundary")
            if (kind, label) in {(1, b"RAM\x00"), (16, b"WRAM"), (16, b"CHRR")}:
                if label in regions:
                    raise ValueError("Duplicate replay memory region")
                regions[label] = data[offset:offset + size]
            offset += size
    if len(regions.get(b"RAM\x00", b"")) != 0x800 or len(regions.get(b"WRAM", b"")) != 0x2000:
        raise ValueError("Replay does not contain the native RAM/WRAM widths")
    if b"CHRR" in regions and len(regions[b"CHRR"]) != 0x2000:
        raise ValueError("Replay CHR RAM width disagrees")
    return regions


def replay_memory(data: bytes) -> tuple[bytes, bytes]:
    regions = replay_regions(data)
    return regions[b"RAM\x00"], regions[b"WRAM"]


def verify_replays(paths: tuple[Path, ...], assets: DragonWarrior4RomAssets) -> dict[str, int]:
    counts = {"snapshots": 0, "battle_snapshots": 0, "field_snapshots": 0,
              "scripted_scene_snapshots": 0, "native_pattern_bytes_matched": 0}
    for path in paths:
        with ZipFile(path) as archive:
            entries = tuple(entry for entry in archive.infolist()
                            if entry.filename.lower().endswith(tuple(f".fc{slot}" for slot in range(10))))
            if not entries or len(entries) > 64 or any(entry.file_size > 262144 for entry in entries):
                raise ValueError("Replay archive has missing or oversized checkpoints")
            for entry in entries:
                regions = replay_regions(archive.read(entry))
                ram, wram = regions[b"RAM\x00"], regions[b"WRAM"]
                state = read_state(ram, wram[:0x300], assets, guest_profile=assets.guest_profile)
                battle = read_battle_state(ram, wram[0x1200:0x1200 + BATTLE_MEMORY_SIZE],
                                          context_flags=wram[0xBDE], monster_name=assets.monster_name,
                                          monster_vitals=assets.monster_vitals, setup_monster_ids=wram[0xE45:0xE49])
                if not state.party_ids or not all(character in state.available_ids for character in state.party_ids):
                    raise ValueError("Captured formation/available roster disagree")
                if not wram[0xBDE] & 0x80 and battle.enemies:
                    raise ValueError("Captured field context retained enemy rows")
                if battle.active and any(enemy.coherent and not enemy.label for enemy in battle.enemies):
                    raise ValueError("Captured native enemy could not be named")
                if not wram[0xBDE] & 0x80 and ram[0x41] & 0x80 and b"CHRR" in regions:
                    indices = wram[0x1600:0x1688]
                    patterns = assets.native_pattern_frame(ram, indices)
                    for index, pattern in patterns:
                        offset = 0x1000 + indices[index] * 16
                        if pattern != regions[b"CHRR"][offset:offset + 16]:
                            raise ValueError("Captured native pattern phase disagrees with CHR RAM")
                        counts["native_pattern_bytes_matched"] += 16
                counts["snapshots"] += 1
                kind = "battle_snapshots" if battle.active else "scripted_scene_snapshots" if wram[0xBDE] & 0x80 else "field_snapshots"
                counts[kind] += 1
    return counts


def verify_threshold_trace(path: Path | None, assets: DragonWarrior4RomAssets) -> int:
    if path is None:
        return 0
    if path.stat().st_size > 65536:
        raise ValueError("Native rate trace exceeds its size bound")
    columns = ["zone", "terrain", "time", "step", "repel", "strength", "scent", "threshold"]
    count = 0
    with path.open(encoding="ascii", newline="") as stream:
        rows = csv.DictReader(stream, delimiter="\t")
        if rows.fieldnames != columns:
            raise ValueError("Native rate trace columns disagree")
        for row in rows:
            if count >= 4096 or None in row:
                raise ValueError("Native rate trace exceeds its row/column bounds")
            values = [int(row[column]) for column in columns]
            threshold, _ = assets.land_encounter_threshold(*values[:-1])
            if threshold != values[-1]:
                raise ValueError("Captured native pre-RNG threshold disagrees")
            count += 1
    if not count:
        raise ValueError("Native rate trace contains no observations")
    return count


def verify_rom(path: Path, state_archives: tuple[Path, ...] = (), rate_trace: Path | None = None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rao-dw4-verify-") as directory:
        assets = DragonWarrior4RomAssets(path, Path(directory), render_area_map, render_world_map)
        if assets.region != "US":
            raise ValueError("Exact native contract verification requires a supported US ROM")
        for descriptor in assets.area_maps:
            tiles, graphics = assets._area_layout(descriptor)
            if len(tiles) != descriptor.height or any(len(row) != descriptor.width for row in tiles):
                raise ValueError(f"Floor {descriptor.map_id:02X}:{descriptor.submap:02X} dimensions disagree")
            if any((tile & 0x1F) >= len(graphics.behaviors) for row in tiles for tile in row):
                raise ValueError("A decoded floor references an unavailable tile")
        worlds = {key: assets._world_rows(key) for key in ("world", "gottside", "underworld")}
        world_points = 0
        for key, rows in worlds.items():
            for y, row in enumerate(rows):
                for x, tile in enumerate(row):
                    if assets.world_tile(key, x, y) != tile:
                        raise ValueError("Native world scan entry disagrees with full-row decoding")
                    world_points += 1
        exit_routes = tuple(route for descriptor in assets.area_maps
                            for route in assets.exit_routes(descriptor.map_id, descriptor.submap))
        if not exit_routes or any(not route.destination_world and route.destination_key not in assets._descriptor_by_key for route in exit_routes):
            raise ValueError("Native directed exit graph contains an unresolved floor")
        walking_routes = tuple(route for descriptor in assets.area_maps
                               for route in assets.tile_transition_routes(descriptor.map_id, descriptor.submap,
                                                                          event_flags=bytes(50)))
        if not walking_routes:
            raise ValueError("Native walking transition directory produced no routes")
        walking_cases = 0
        for time_value, story_flags, event_flags in ((0, 0, bytes(50)), (0x78, 0, bytes(50)),
                                                   (0, 255, bytes([255]) * 50), (0x78, 255, bytes([255]) * 50)):
            for descriptor in assets.area_maps:
                for route in assets.tile_transition_routes(descriptor.map_id, descriptor.submap, time_value, story_flags, event_flags):
                    target = assets._descriptor_by_key[route.destination_key]
                    if not 0 <= route.x < descriptor.width or not 0 <= route.y < descriptor.height:
                        raise ValueError("Native walking source is outside its floor")
                    if not 0 <= route.destination_x < target.width or not 0 <= route.destination_y < target.height:
                        raise ValueError("Native walking arrival is outside its floor")
                    walking_cases += 1
        destinations = assets._world_destination_waypoints()
        names = [assets.monster_name(identifier) for identifier in range(214)]
        if any(not name for name in names):
            raise ValueError("A native monster name was empty")
        for identifier in range(214):
            monster = assets.monster_definition(identifier)
            if monster is None or monster.name != names[identifier]:
                raise ValueError("A native bestiary record could not be resolved")
            if not monster.resistances or monster.drop_denominator not in {None, 1, 8, 16, 32, 64, 128, 256, 4096}:
                raise ValueError("A native resistance/drop contract could not be resolved")
            if monster.drop_item_id is not None:
                assets.indexed_name(3, monster.drop_item_id)
        for identity in ((2, 0), (0x2D, 7), (0x45, 4)):
            descriptor = assets.descriptor(*identity)
            if descriptor is not None:
                assets.render_area_map(descriptor.key, (0, False, False))
                assets.render_area_map(descriptor.key, (1, False, False))
        milestones = tuple(assets.spell_milestones(identifier) for identifier in range(8))
        if not all(milestones[:5]) or any(milestones[5:]) or assets.spell_milestones(8) != milestones[0]:
            raise ValueError("Native spell-learning character coverage disagrees")
        catalog = assets.collectible_catalog()
        if len({(entry.flag_byte, entry.flag_mask) for entry in catalog}) != len(catalog):
            raise ValueError("Duplicate native collectible flag identities")
        if any(entry.flag_byte >= 27 or entry.collected(bytes(27)) is not False or entry.collected(bytes([255]) * 27) is not True for entry in catalog):
            raise ValueError("Native collectible flag bounds/polarity disagree")
        pools = 0
        for chapter in range(5):
            for x in range(0, 256, 16):
                for y in range(0, 256, 16):
                    for time_value in (0, 0x78):
                        pool = assets.encounter_pool(chapter, 0, x, y, time_value)
                        if pool is None or not 0 <= pool[0] < 64 or any(weight <= 0 for _, weight in pool[1]):
                            raise ValueError("Native land encounter pool could not be resolved")
                        pools += 1
        for world, y, expected in ((1, 0, 0x35), (1, 12, 0x34), (3, 0, 0x36)):
            pool = assets.encounter_pool(4, world, 0, y, 0)
            if pool is None or pool[0] != expected:
                raise ValueError("Native special-world encounter boundary disagrees")
        indoor_cases = 0
        indoor_pools = 0
        for chapter in range(5):
            for descriptor in assets.area_maps:
                pool = assets.indoor_encounter_pool(chapter, descriptor.map_id, descriptor.submap)
                if pool is not None:
                    indoor_pools += 1
                    if any(weight <= 0 for _, weight in pool[1]):
                        raise ValueError("Native indoor pool contains an invalid display weight")
                indoor_cases += 1
        for zone in range(64):
            for mask in (0x1BEF, 0x3FBE, 0x3FFF):
                chances = assets.formation_entry_chances(zone, mask)
                if chances and sum(count for _, count in chances) != 256:
                    raise ValueError("Native formation entry chances do not normalize")
        cutaway = assets.render_area_map(0x0200)
        roof = assets.render_area_map(0x0200, room_class=0)
        with Image.open(cutaway) as first, Image.open(roof) as second:
            if first.size != second.size or first.tobytes() == second.tobytes():
                raise ValueError("Native roof/cutaway render contract disagrees")
        shops = sum(len(assets.town_shops(map_id)) for map_id in range(0x49))
        return {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "region": assets.region,
            "floors_decoded": len(assets.area_maps),
            "world_dimensions": {key: [len(rows[0]), len(rows)] for key, rows in worlds.items()},
            "world_destinations": sum(len(points) for points in destinations.values()),
            "world_scan_entry_points": world_points,
            "generic_directed_exit_routes": len(exit_routes),
            "walking_transition_records": sum(map(len, assets.transition_records().values())),
            "resolved_walking_routes": len(walking_routes),
            "walking_time_story_cases": walking_cases,
            "monster_names_and_vitals": len(names),
            "native_bestiary_records": len(names),
            "native_resistance_records": len(names),
            "spell_learning_tables": sum(bool(value) for value in milestones),
            "typed_reward_flags": len(catalog),
            "direct_medal_pickup_flags": sum(entry.item_id == 0x69 for entry in catalog),
            "chapter_grid_time_pools": pools,
            "indoor_chapter_floor_cases": indoor_cases,
            "eligible_indoor_pools": indoor_pools,
            "normalized_zone_mask_cases": 192,
            "roof_cutaway_pixel_check": True,
            "palette_variants_rendered": 6,
            "town_shop_records": shops,
            "hidden_rewards": len(assets.hidden_treasures()),
            "boundary_floors": ["2d:07", "45:04", "45:05"],
            "captured_replay_cases": verify_replays(state_archives, assets),
            "captured_land_rate_checks": verify_threshold_trace(rate_trace, assets),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify DW4 native contracts against a locally owned ROM")
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--state-archive", type=Path, action="append", default=[], help="Opt-in local legacy FCEUX checkpoint archive; never extracted")
    parser.add_argument("--rate-trace", type=Path, help="Optional bounded native pre-RNG threshold TSV")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if not arguments.rom.is_file() or not 1 <= arguments.timeout <= 300:
        parser.error("A ROM file and a timeout between 1 and 300 seconds are required")
    if arguments.worker:
        print(json.dumps(verify_rom(arguments.rom, tuple(arguments.state_archive), arguments.rate_trace), indent=2))
        return 0
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--rom", str(arguments.rom.resolve()), "--worker",
             *(argument for path in arguments.state_archive for argument in ("--state-archive", str(path.resolve()))),
             *(("--rate-trace", str(arguments.rate_trace.resolve())) if arguments.rate_trace is not None else ())],
            timeout=arguments.timeout, capture_output=True, text=True, check=False,
        )
    except subprocess.TimeoutExpired:
        print("ROM verification exceeded its bounded timeout", file=sys.stderr)
        return 1
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())