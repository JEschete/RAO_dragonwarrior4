from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from retroarch_overlay.models import MapOverlay, MapWaypoint

from .dialogue_journal import DialogueEntry
from .state import LocationState


SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ObservedTransition:
    map_key: str
    x: int
    y: int
    destination_key: str
    destination: str
    seen_count: int
    last_seen: str


@dataclass(frozen=True, slots=True)
class EncounterHotspot:
    map_key: str
    x: int
    y: int
    encounters: int
    enemies: tuple[str, ...]
    last_seen: str


class MapIntelligence:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        transitions, hotspots, encounter_ids = self._load()
        self._transitions = list(transitions)
        self._hotspots = list(hotspots)
        self._encounter_ids = list(encounter_ids)
        self._previous: tuple[LocationState, str] | None = None

    @property
    def transitions(self) -> tuple[ObservedTransition, ...]:
        return tuple(self._transitions)

    @property
    def hotspots(self) -> tuple[EncounterHotspot, ...]:
        return tuple(self._hotspots)

    def observe(self, location: LocationState, map_key: str) -> bool:
        previous = self._previous
        self._previous = (location, map_key)
        if previous is None:
            return False
        previous_location, previous_key = previous
        previous_identity = (
            previous_location.is_world,
            previous_location.map_id,
            previous_location.submap,
        )
        current_identity = (location.is_world, location.map_id, location.submap)
        if previous_identity == current_identity:
            return False
        now = datetime.now(timezone.utc).isoformat()
        changed = self._record(
            previous_key,
            previous_location.x,
            previous_location.y,
            map_key,
            location.title,
            now,
        )
        changed = self._record(
            map_key,
            location.x,
            location.y,
            previous_key,
            previous_location.title,
            now,
        ) or changed
        if changed:
            self._write()
        return changed

    def observe_encounter(
        self,
        encounter: dict[str, object] | None,
        map_key: str,
        x: int,
        y: int,
    ) -> bool:
        if encounter is None:
            return False
        encounter_id = str(encounter.get("encounter_id", ""))
        if not encounter_id or encounter_id in self._encounter_ids:
            return False
        self._encounter_ids.append(encounter_id)
        del self._encounter_ids[:-500]
        enemy_values = encounter.get("enemies", [])
        if not isinstance(enemy_values, list):
            enemy_values = []
        labels = tuple(
            sorted(
                {
                    str(enemy.get("label", "Unknown enemy"))
                    for enemy in enemy_values
                    if isinstance(enemy, dict)
                }
            )
        )
        now = datetime.now(timezone.utc).isoformat()
        for index, hotspot in enumerate(self._hotspots):
            if (hotspot.map_key, hotspot.x, hotspot.y) != (map_key, x, y):
                continue
            self._hotspots[index] = EncounterHotspot(
                map_key,
                x,
                y,
                hotspot.encounters + 1,
                tuple(sorted(set(hotspot.enemies) | set(labels))),
                now,
            )
            self._write()
            return True
        self._hotspots.append(EncounterHotspot(map_key, x, y, 1, labels, now))
        self._write()
        return True

    def overlay(
        self,
        location: LocationState,
        map_key: str,
        journal_entries: tuple[DialogueEntry, ...],
    ) -> MapOverlay | None:
        points = [
            MapWaypoint(
                transition.x,
                transition.y,
                f"Transition to {transition.destination}",
                (
                    f"Observed {transition.seen_count} "
                    f"{'time' if transition.seen_count == 1 else 'times'}; "
                    f"last seen {transition.last_seen}"
                ),
                "connections",
                marker="building",
            )
            for transition in self._transitions
            if transition.map_key == map_key
        ]
        points.extend(
            MapWaypoint(
                hotspot.x,
                hotspot.y,
                f"{hotspot.encounters} observed encounter"
                f"{'s' if hotspot.encounters != 1 else ''}",
                (
                    ", ".join(hotspot.enemies)
                    if hotspot.enemies
                    else "Enemy identity was unavailable"
                ),
                "encounters",
            )
            for hotspot in self._hotspots
            if hotspot.map_key == map_key
        )
        seen_dialogue_positions: set[tuple[int, int, str]] = set()
        for entry in reversed(journal_entries):
            if (
                entry.map_id != location.map_id
                or entry.submap != location.submap
                or min(entry.x, entry.y) < 0
            ):
                continue
            key = (entry.x, entry.y, entry.text)
            if key in seen_dialogue_positions:
                continue
            seen_dialogue_positions.add(key)
            preview = entry.text if len(entry.text) <= 42 else entry.text[:39] + "..."
            points.append(
                MapWaypoint(
                    entry.x,
                    entry.y,
                    preview,
                    (
                        f"Observed dialogue at {entry.location}\n"
                        f"Seen {entry.seen_count} "
                        f"{'time' if entry.seen_count == 1 else 'times'}"
                    ),
                    "npcs",
                    marker="person",
                )
            )
        return MapOverlay(map_key, tuple(points)) if points else None

    def _record(
        self,
        map_key: str,
        x: int,
        y: int,
        destination_key: str,
        destination: str,
        now: str,
    ) -> bool:
        for index, transition in enumerate(self._transitions):
            if (
                transition.map_key,
                transition.x,
                transition.y,
                transition.destination_key,
            ) == (map_key, x, y, destination_key):
                self._transitions[index] = ObservedTransition(
                    map_key,
                    x,
                    y,
                    destination_key,
                    destination,
                    transition.seen_count + 1,
                    now,
                )
                return True
        self._transitions.append(
            ObservedTransition(
                map_key,
                x,
                y,
                destination_key,
                destination,
                1,
                now,
            )
        )
        return True

    def _load(
        self,
    ) -> tuple[
        tuple[ObservedTransition, ...],
        tuple[EncounterHotspot, ...],
        tuple[str, ...],
    ]:
        if self.path is None:
            return (), (), ()
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if document.get("schema_version") != SCHEMA_VERSION:
                return (), (), ()
            values = document.get("transitions", [])
            if not isinstance(values, list):
                return (), (), ()
            transitions = tuple(
                ObservedTransition(**value)
                for value in values
                if isinstance(value, dict)
            )
            hotspot_values = document.get("hotspots", [])
            hotspots = tuple(
                EncounterHotspot(
                    str(value["map_key"]),
                    int(value["x"]),
                    int(value["y"]),
                    int(value.get("encounters", 0)),
                    tuple(str(enemy) for enemy in value.get("enemies", [])),
                    str(value.get("last_seen", "")),
                )
                for value in hotspot_values
                if isinstance(value, dict)
            ) if isinstance(hotspot_values, list) else ()
            encounter_ids = document.get("encounter_ids", [])
            return (
                transitions,
                hotspots,
                tuple(str(value) for value in encounter_ids)
                if isinstance(encounter_ids, list)
                else (),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return (), (), ()

    def _write(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "transitions": [
                        asdict(transition) for transition in self._transitions
                    ],
                    "hotspots": [asdict(hotspot) for hotspot in self._hotspots],
                    "encounter_ids": self._encounter_ids,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)