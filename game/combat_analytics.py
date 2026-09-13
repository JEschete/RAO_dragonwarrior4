from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .encounter_log import EncounterRecord


SCHEMA_VERSION = 1
PROCESSED_ID_LIMIT = 500


class CombatAnalytics:
    def __init__(
        self,
        path: Path | None,
        existing_records: Iterable[EncounterRecord] = (),
    ) -> None:
        self.path = path
        self._session_ids: set[str] = set()
        self._document = self._load() or self._empty_document()
        changed = False
        for record in reversed(tuple(existing_records)):
            changed = self._include(record, session=False) or changed
        if changed:
            self._write()

    @property
    def document(self) -> dict[str, Any]:
        total = int(self._document["total_encounters"])
        victories = int(self._document["outcomes"].get("victory", 0))
        duration = float(self._document["duration_seconds"])
        locations = sorted(
            self._document["locations"].values(),
            key=lambda value: (-int(value["encounters"]), str(value["name"])),
        )
        enemies = sorted(
            self._document["enemies"].values(),
            key=lambda value: (-int(value["encounters"]), int(value["monster_id"])),
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "total_encounters": total,
            "session_encounters": len(self._session_ids),
            "outcomes": dict(self._document["outcomes"]),
            "win_rate": round(victories / total, 4) if total else 0.0,
            "reward_gold": int(self._document["reward_gold"]),
            "reward_experience": int(self._document["reward_experience"]),
            "duration_seconds": round(duration, 3),
            "average_duration_seconds": round(duration / total, 3) if total else 0.0,
            "unidentified_groups": int(self._document["unidentified_groups"]),
            "locations": locations,
            "enemies": enemies,
        }

    def observe(self, records: Iterable[EncounterRecord]) -> bool:
        changed = False
        for record in reversed(tuple(records)):
            changed = self._include(record, session=True) or changed
        if changed:
            self._write()
        return changed

    @staticmethod
    def _empty_document() -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "processed_ids": [],
            "total_encounters": 0,
            "outcomes": {
                "victory": 0,
                "defeat": 0,
                "escaped_or_interrupted": 0,
            },
            "reward_gold": 0,
            "reward_experience": 0,
            "duration_seconds": 0.0,
            "unidentified_groups": 0,
            "locations": {},
            "enemies": {},
        }

    def _include(self, record: EncounterRecord, *, session: bool) -> bool:
        processed_ids = self._document["processed_ids"]
        if record.encounter_id in processed_ids:
            return False
        processed_ids.append(record.encounter_id)
        del processed_ids[:-PROCESSED_ID_LIMIT]
        if session:
            self._session_ids.add(record.encounter_id)

        self._document["total_encounters"] += 1
        outcomes = self._document["outcomes"]
        outcomes[record.outcome] = int(outcomes.get(record.outcome, 0)) + 1
        self._document["reward_gold"] += record.reward_gold
        self._document["reward_experience"] += record.reward_experience
        self._document["duration_seconds"] += record.duration_seconds

        location = self._document["locations"].setdefault(
            record.start_location,
            {
                "name": record.start_location,
                "encounters": 0,
                "victories": 0,
                "defeats": 0,
                "escapes": 0,
            },
        )
        location["encounters"] += 1
        if record.outcome == "victory":
            location["victories"] += 1
        elif record.outcome == "defeat":
            location["defeats"] += 1
        else:
            location["escapes"] += 1

        identified: dict[int, str] = {}
        for enemy in record.enemies:
            if enemy.monster_id is None:
                self._document["unidentified_groups"] += 1
            else:
                identified[enemy.monster_id] = enemy.label
        for monster_id, label in identified.items():
            key = f"{monster_id:02x}"
            enemy = self._document["enemies"].setdefault(
                key,
                {
                    "monster_id": monster_id,
                    "label": label,
                    "encounters": 0,
                    "victories": 0,
                    "defeats": 0,
                    "escapes": 0,
                },
            )
            enemy["label"] = label
            enemy["encounters"] += 1
            if record.outcome == "victory":
                enemy["victories"] += 1
            elif record.outcome == "defeat":
                enemy["defeats"] += 1
            else:
                enemy["escapes"] += 1
        return True

    def _load(self) -> dict[str, Any] | None:
        if self.path is None:
            return None
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
            return None
        empty = self._empty_document()
        for key in empty:
            if key not in document or not isinstance(document[key], type(empty[key])):
                return None
        return document

    def _write(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)