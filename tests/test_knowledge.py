import json
from pathlib import Path
import pytest

from game.knowledge import DragonWarrior4Knowledge
from game.knowledge_builder import build_knowledge
from game.reference_data import REFERENCE_SOURCE_SPECS, load_submap_names, load_treasure_records


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


@pytest.mark.parametrize("artifact", (None, "{broken"))
def test_runtime_does_not_fall_back_to_saved_html(tmp_path: Path, artifact: str | None) -> None:
    resources = tmp_path / "resources"
    resources.mkdir()
    resources.joinpath(REFERENCE_SOURCE_SPECS[8][1]).write_text(
        '<h2 id="Maps">Maps</h2><table><tr><td>$01</td><td>$02</td>'
        '<td>Unreviewed Place</td></tr></table>', encoding="utf-8")
    resources.joinpath(REFERENCE_SOURCE_SPECS[2][1]).write_text(
        '<h2 id="Full_List">Treasures</h2><table><tr><td>Treasure</td>'
        '<td>$625D #00000001</td><td></td><td>$01</td><td>$02</td>'
        '<td>Chest</td><td>Unreviewed Reward</td></tr></table>', encoding="utf-8")
    if artifact is not None:
        destination = tmp_path / "game" / "data"
        destination.mkdir(parents=True)
        destination.joinpath("dw4_knowledge.json").write_text(artifact, encoding="utf-8")

    assert load_submap_names(tmp_path) == {}
    assert load_treasure_records(tmp_path) == ()


@pytest.mark.parametrize("field,value", (("submap_names", {"invalid": "Town"}),
                                         ("treasures", [{}]), ("spells", [[{}]]),
                                         ("achievements", [{}])))
def test_malformed_nested_knowledge_fails_before_runtime_use(tmp_path: Path, field: str, value) -> None:
    document = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    document[field] = value
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError):
        DragonWarrior4Knowledge.load(path)