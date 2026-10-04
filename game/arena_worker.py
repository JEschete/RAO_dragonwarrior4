from __future__ import annotations

import base64
from dataclasses import asdict
import json
from pathlib import Path
import sys


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from game.arena_native import simulate_arena

        payload = json.load(sys.stdin)
        values = tuple(base64.b64decode(payload[name], validate=True) for name in ("prg", "ram", "workspace"))

        def progress(completed: int) -> None:
            print(json.dumps({"kind": "progress", "completed": completed}), flush=True)

        result = simulate_arena(*values, seed=payload.get("seed", 0),
                    simulations=payload.get("simulations", 100), progress=progress)
        print(json.dumps({"kind": "result", **asdict(result)}), flush=True)
        return 0
    except Exception as error:
        print(json.dumps({"kind": "error", "detail": str(error)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())