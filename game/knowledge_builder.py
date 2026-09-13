from __future__ import annotations

import json
import re
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .achievements import ACHIEVEMENTS
from .knowledge import SCHEMA_VERSION
from .reference_data import (
    CHARACTER_SPELL_BITS,
    ITEM_NAMES,
    REFERENCE_SOURCE_SPECS,
    _SubmapTableParser,
    _TreasureTableParser,
)


class _SectionTableParser(HTMLParser):
    def __init__(self, section_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.section_id = section_id
        self.section_found = False
        self.in_table = False
        self.in_cell = False
        self.cell: list[str] = []
        self.row: list[str] = []
        self.rows: list[tuple[str, ...]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id") == self.section_id:
            self.section_found = True
        elif self.section_found and tag == "table" and not self.in_table:
            self.in_table = True
        elif self.in_table and tag in {"td", "th"}:
            self.in_cell = True
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag in {"td", "th"} and self.in_cell:
            self.row.append(" ".join("".join(self.cell).split()))
            self.in_cell = False
        elif self.in_table and tag == "tr":
            if self.row:
                self.rows.append(tuple(self.row))
            self.row = []
        elif self.in_table and tag == "table":
            self.in_table = False
            self.section_found = False


class _ApplicationPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_application_data = False
        self.fragments: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.in_application_data = (
            tag == "script"
            and values.get("data-page") == "app"
            and values.get("type") == "application/json"
        )

    def handle_data(self, data: str) -> None:
        if self.in_application_data:
            self.fragments.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_application_data = False


def build_knowledge(root: Path) -> dict[str, Any]:
    resources = root / "resources"
    values_path = resources / REFERENCE_SOURCE_SPECS[8][1]
    ram_path = resources / REFERENCE_SOURCE_SPECS[2][1]
    achievement_paths = tuple(
        path
        for path in resources.glob("*RetroAchievements.htm")
        if not path.name.startswith("Code Notes")
    )
    if not achievement_paths:
        raise FileNotFoundError("Saved RetroAchievements game page is unavailable")

    values_document = values_path.read_text(encoding="utf-8")
    ram_document = ram_path.read_text(encoding="utf-8")
    achievement_document = achievement_paths[0].read_text(encoding="utf-8")

    submaps = _SubmapTableParser()
    submaps.feed(values_document)
    treasures = _TreasureTableParser()
    treasures.feed(ram_document)
    items = _item_names(values_document)
    spells = _spell_bits(ram_document)
    achievements = _achievements(achievement_document)

    if tuple(items) != ITEM_NAMES:
        raise ValueError("Saved item table does not match the reviewed runtime catalog")
    expected_spells = [
        [asdict(value) if value is not None else None for value in definitions]
        for definitions in CHARACTER_SPELL_BITS
    ]
    if spells != expected_spells:
        raise ValueError("Saved spell table does not match the reviewed runtime catalog")
    expected_achievements = [asdict(value) for value in ACHIEVEMENTS]
    if achievements != expected_achievements:
        raise ValueError(
            "Saved achievement set does not match the reviewed runtime catalog"
        )

    revision = re.search(r'"wgCurRevisionId":(\d+)', values_document)
    captured = re.search(r"all-(\d{4}\.\d{2}\.\d{2})-", achievement_document)
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": {
            "data_crystal": {
                "url": REFERENCE_SOURCE_SPECS[8][2],
                "revision": int(revision.group(1)) if revision else None,
            },
            "retroachievements": {
                "url": "https://retroachievements.org/game/4612",
                "captured": captured.group(1) if captured else "unknown",
            },
        },
        "submap_names": {
            f"{map_id:02x}:{submap:02x}": name
            for (map_id, submap), name in sorted(submaps.names.items())
        },
        "treasures": [asdict(value) for value in treasures.records],
        "items": items,
        "spells": spells,
        "achievements": achievements,
    }


def _item_names(document: str) -> list[str]:
    parser = _SectionTableParser("Items")
    parser.feed(document)
    names: dict[int, str] = {}
    for row in parser.rows:
        if len(row) < 2:
            continue
        try:
            item_id = int(row[0].removeprefix("$"), 16)
        except ValueError:
            continue
        if item_id < 0x7F:
            name = row[1]
            names[item_id] = "Unknown item $51" if item_id == 0x51 else name
    if set(names) != set(range(0x7F)):
        raise ValueError("Saved item table is incomplete")
    return [names[item_id] for item_id in range(0x7F)]


def _spell_bits(document: str) -> list[list[dict[str, str] | None]]:
    character_ids = {
        "Hero": 0,
        "Cristo": 1,
        "Nara": 2,
        "Mara": 3,
        "Brey": 4,
    }
    result: list[list[dict[str, str] | None]] = [[None] * 24 for _ in range(8)]
    for character, character_id in character_ids.items():
        parser = _SectionTableParser(character)
        parser.feed(document)
        record_start = 0x6001 + character_id * 30
        for row in parser.rows:
            if len(row) < 4 or "Spell #" not in row[3]:
                continue
            address = re.search(r"\$([0-9a-fA-F]{4})\s*#\s*([01_]{8,})", row[1])
            description = re.match(r"(Battle|Overworld) Spell #\d+ - (.+)", row[3])
            if address is None or description is None:
                continue
            byte_offset = int(address.group(1), 16) - (record_start + 27)
            mask = int(address.group(2).replace("_", ""), 2)
            bit_index = byte_offset * 8 + mask.bit_length() - 1
            name = description.group(2)
            if 0 <= bit_index < 24 and name.casefold() != "n/a":
                result[character_id][bit_index] = {
                    "name": name,
                    "usage": (
                        "battle"
                        if description.group(1) == "Battle"
                        else "field"
                    ),
                }
    return result


def _achievements(document: str) -> list[dict[str, object]]:
    parser = _ApplicationPageParser()
    parser.feed(document)
    if not parser.fragments:
        raise ValueError("Saved RetroAchievements application data is unavailable")
    payload = json.loads("".join(parser.fragments))
    values = payload["props"]["game"]["gameAchievementSets"][0][
        "achievementSet"
    ]["achievements"]
    values_by_id = {int(value["id"]): value for value in values}
    return [
        {
            "achievement_id": int(value["id"]),
            "title": str(value["title"]),
            "description": str(value["description"]),
            "points": int(value["points"]),
        }
        for achievement in ACHIEVEMENTS
        for value in (values_by_id[achievement.achievement_id],)
    ]