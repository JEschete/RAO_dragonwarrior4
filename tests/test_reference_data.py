from pathlib import Path

from game.reference_data import (
    _SubmapTableParser,
    load_treasure_records,
    decode_text,
    load_submap_names,
    map_title,
    reference_sources,
    time_of_day,
)


ROOT = Path(__file__).parents[1]


def test_saved_reference_catalog_accounts_for_every_page() -> None:
    sources = reference_sources(ROOT)

    assert len(sources) == 10
    assert all(source.available for source in sources)
    assert {source.title for source in sources} >= {
        "ROM map",
        "RAM map",
        "SRAM map",
        "Map data format",
        "Map list",
        "Text table",
        "Tile behaviors",
        "Values and submaps",
        "RetroAchievements code notes",
    }


def test_values_page_supplies_detailed_submap_names() -> None:
    names = load_submap_names(ROOT)

    assert names[(0x00, 0x00)] == "Keeleon - Outside"
    assert names[(0x04, 0x06)] == "Endor - Castle, F2 (throne room)"
    assert len(names) > 150


def test_ram_page_supplies_documented_treasure_rewards_and_flags() -> None:
    records = load_treasure_records(ROOT)

    assert len(records) == 182
    assert records[0].map_id == 0x02
    assert records[0].submap == 0x01
    assert records[0].reward == "Agility Seed"
    assert not records[0].is_open(bytes(27))
    assert records[0].is_open(bytes((1,)) + bytes(26))
    assert any(record.reward.endswith("Mimic!") for record in records)


def test_submap_parser_ignores_unrelated_tables() -> None:
    parser = _SubmapTableParser()
    parser.feed(
        "<table><tr><td>$09</td><td>$09</td><td>Wrong</td></tr></table>"
        '<h2><span id="Maps">Maps</span></h2>'
        "<table><tr><th>Map</th><th>Submap</th><th>Description</th></tr>"
        "<tr><td>$01</td><td>$02</td><td>Right Place</td></tr></table>"
    )

    assert parser.names == {(1, 2): "Right Place"}


def test_fallback_titles_and_reference_values_are_stable() -> None:
    assert map_title(0x01, 0) == "Santeem"
    assert map_title(0x01, 2) == "Santeem · Submap 3"
    assert time_of_day(0x84) == "Night"
    assert time_of_day(0xC8) == "Morning"
    assert decode_text(bytes((0x25, 0x16, 0x0F, 0x18, 0x0B, 0x00, 0x01, 0x02, 0xFF))) == "Alena 01"