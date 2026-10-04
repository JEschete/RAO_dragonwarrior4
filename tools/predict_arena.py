from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from game.arena_native import simulate_arena
from game.rom_assets import DragonWarrior4RomAssets
from map_renderer import render_area_map, render_world_map


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 100 native DW4 arena simulations")
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--entries", nargs=4, type=lambda value: int(value, 0), default=(0, 0, 0, 0))
    parser.add_argument("--seed", type=int, default=0)
    options = parser.parse_args()
    assets = DragonWarrior4RomAssets(options.rom, options.rom.parent, render_area_map, render_world_map)
    workspace = bytearray(0x2000)
    workspace[0x16A] = 0x80
    workspace[0xE45:0xE49] = bytes(options.entries)

    def progress(completed: int) -> None:
        if completed % 25 == 0:
            print(f"Completed {completed}/100", file=sys.stderr, flush=True)

    result = simulate_arena(assets.arena_program(), bytes(0x800), bytes(workspace),
                            seed=options.seed, progress=progress)
    profiles = [asdict(profile) if (profile := assets.monster_definition(identity)) is not None else None
                for identity in result.monster_ids]
    print(json.dumps({**asdict(result), "profiles": profiles}, indent=2))


if __name__ == "__main__":
    main()