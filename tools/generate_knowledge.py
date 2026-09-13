import argparse
import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from game.knowledge_builder import build_knowledge


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate reviewed Dragon Warrior IV knowledge"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PLUGIN_ROOT / "game" / "data" / "dw4_knowledge.json",
    )
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    rendered = json.dumps(
        build_knowledge(PLUGIN_ROOT),
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
    ) + "\n"
    if arguments.check:
        if (
            not arguments.output.is_file()
            or arguments.output.read_text(encoding="utf-8") != rendered
        ):
            print(f"Generated knowledge is stale: {arguments.output}", file=sys.stderr)
            return 1
        return 0
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(arguments.output)
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())