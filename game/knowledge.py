from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class DragonWarrior4Knowledge:
    document: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> DragonWarrior4Knowledge:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"DW4 knowledge is unavailable: {error}") from error
        if not isinstance(document, dict):
            raise ValueError("DW4 knowledge must contain a JSON object")
        if document.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("DW4 knowledge schema does not match this plugin")
        for key in ("sources", "submap_names"):
            if not isinstance(document.get(key), dict):
                raise ValueError(f"DW4 knowledge field {key!r} must be an object")
        for key in ("treasures", "items", "spells", "achievements"):
            if not isinstance(document.get(key), list):
                raise ValueError(f"DW4 knowledge field {key!r} must be an array")
        for key, name in document["submap_names"].items():
            try:
                parts = tuple(int(part, 16) for part in key.split(":"))
            except (AttributeError, TypeError, ValueError) as error:
                raise ValueError("Invalid DW4 submap identity") from error
            if len(parts) != 2 or not 0 <= parts[0] < 0x49 or not 0 <= parts[1] < 64 or not isinstance(name, str):
                raise ValueError("Invalid DW4 submap record")
        for record in document["treasures"]:
            if not isinstance(record, dict) or not all(isinstance(record.get(key), int) for key in ("flag_index", "map_id", "submap")):
                raise ValueError("Invalid DW4 treasure identity")
            if not all(isinstance(record.get(key), str) for key in ("description", "reward")):
                raise ValueError("Invalid DW4 treasure description")
        if not all(isinstance(name, str) for name in document["items"]):
            raise ValueError("Invalid DW4 item name")
        for spells in document["spells"]:
            if not isinstance(spells, list):
                raise ValueError("Invalid DW4 spell-bit list")
            for spell in spells:
                if spell is not None and (
                    not isinstance(spell, dict) or not isinstance(spell.get("name"), str)
                    or spell.get("usage") not in {"battle", "field"}
                ):
                    raise ValueError("Invalid DW4 spell-bit record")
        for record in document["achievements"]:
            if not isinstance(record, dict) or not all(isinstance(record.get(key), int) for key in ("achievement_id", "points")):
                raise ValueError("Invalid DW4 achievement identity")
            if not all(isinstance(record.get(key), str) for key in ("title", "description")):
                raise ValueError("Invalid DW4 achievement text")
        return cls(document)

    def __getitem__(self, key: str) -> Any:
        return self.document[key]