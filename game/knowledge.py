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
        except (OSError, json.JSONDecodeError) as error:
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
        return cls(document)

    def __getitem__(self, key: str) -> Any:
        return self.document[key]