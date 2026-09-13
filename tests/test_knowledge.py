import json
from pathlib import Path
import pytest

from game.knowledge import DragonWarrior4Knowledge
from game.knowledge_builder import build_knowledge
from game.reference_data import load_submap_names, load_treasure_records


ROOT = Path(__file__).parents[1]
KNOWLEDGE_PATH = ROOT / "game" / "data" / "dw4_knowledge.json"


def test_generated_knowledge_matches_reviewed_sources() -> None:
    resources = ROOT / "resources"
    required = (
        resources / "Dragon Warrior IV (NES)_Values - Data Crystal.htm",
        resources / "Dragon Warrior IV (NES)_RAM map - Data Crystal.htm",
    )
    if not all(path.is_file() for path in required) or not any(
        path
        for path in resources.glob("*RetroAchievements.htm")
        if not path.name.startswith("Code Notes")
    ):
        pytest.skip("local reviewed source captures are unavailable")
    expected = build_knowledge(ROOT)
    actual = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))

    assert actual == expected


def test_generated_knowledge_loads_without_reference_pages(tmp_path: Path) -> None:
    destination = tmp_path / "game" / "data"
    destination.mkdir(parents=True)
    destination.joinpath("dw4_knowledge.json").write_bytes(
        KNOWLEDGE_PATH.read_bytes()
    )

    knowledge = DragonWarrior4Knowledge.load(
        destination / "dw4_knowledge.json"
    )

    assert len(knowledge["items"]) == 0x7F
    assert len(knowledge["achievements"]) == 43
    assert load_submap_names(tmp_path)
    assert load_treasure_records(tmp_path)