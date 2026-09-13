from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DialogueEntry:
    entry_id: str
    text: str
    location: str
    map_id: int
    submap: int
    first_seen: str
    last_seen: str
    seen_count: int = 1
    x: int = -1
    y: int = -1


@dataclass(slots=True)
class _PendingDialogue:
    text: str
    location: str
    map_id: int
    submap: int
    x: int
    y: int
    since: datetime
    committed: bool = False


class DialogueJournal:
    def __init__(
        self,
        path: Path | None,
        *,
        settle_seconds: float = 0.75,
        duplicate_window_seconds: float = 5.0,
    ) -> None:
        self.path = path
        self.settle_time = timedelta(seconds=settle_seconds)
        self.duplicate_window = timedelta(seconds=duplicate_window_seconds)
        self._entries = list(self._load())
        self._pending: _PendingDialogue | None = None

    @property
    def entries(self) -> tuple[DialogueEntry, ...]:
        return tuple(self._entries)

    def observe(
        self,
        text: str,
        location: str,
        map_id: int,
        submap: int,
        *,
        x: int = -1,
        y: int = -1,
        now: datetime | None = None,
    ) -> tuple[DialogueEntry, ...]:
        observed_at = now or datetime.now(timezone.utc)
        normalized = " ".join(text.split())
        pending = self._pending
        if not normalized:
            if pending is not None and not pending.committed:
                self._commit(pending, observed_at)
            self._pending = None
            return self.entries

        same_location = (
            pending is not None
            and (pending.map_id, pending.submap) == (map_id, submap)
        )
        if pending is None:
            self._pending = _PendingDialogue(
                normalized,
                location,
                map_id,
                submap,
                x,
                y,
                observed_at,
            )
        elif same_location and normalized == pending.text:
            if min(x, y) >= 0:
                pending.x = x
                pending.y = y
            if not pending.committed and observed_at - pending.since >= self.settle_time:
                self._commit(pending, observed_at)
                pending.committed = True
        elif same_location and normalized.startswith(pending.text):
            self._pending = _PendingDialogue(
                normalized,
                location,
                map_id,
                submap,
                x,
                y,
                observed_at,
            )
        else:
            if not pending.committed:
                self._commit(pending, observed_at)
            self._pending = _PendingDialogue(
                normalized,
                location,
                map_id,
                submap,
                x,
                y,
                observed_at,
            )
        return self.entries

    def _commit(self, pending: _PendingDialogue, observed_at: datetime) -> None:
        timestamp = observed_at.astimezone(timezone.utc).isoformat()
        key = (pending.map_id, pending.submap, pending.text)
        for index, entry in enumerate(self._entries):
            if (entry.map_id, entry.submap, entry.text) == key:
                previous_seen = self._timestamp(entry.last_seen)
                if previous_seen is not None and observed_at - previous_seen <= self.duplicate_window:
                    return
                self._entries[index] = replace(
                    entry,
                    last_seen=timestamp,
                    seen_count=entry.seen_count + 1,
                )
                self._write()
                return

        if self._entries:
            previous = self._entries[-1]
            previous_seen = self._timestamp(previous.last_seen)
            if (
                (previous.map_id, previous.submap)
                == (pending.map_id, pending.submap)
                and pending.text.startswith(previous.text)
                and previous_seen is not None
                and observed_at - previous_seen <= timedelta(seconds=15)
            ):
                self._entries[-1] = DialogueEntry(
                    self._entry_id(pending.map_id, pending.submap, pending.text),
                    pending.text,
                    pending.location,
                    pending.map_id,
                    pending.submap,
                    previous.first_seen,
                    timestamp,
                    previous.seen_count,
                    pending.x,
                    pending.y,
                )
                self._write()
                return

        self._entries.append(
            DialogueEntry(
                self._entry_id(pending.map_id, pending.submap, pending.text),
                pending.text,
                pending.location,
                pending.map_id,
                pending.submap,
                timestamp,
                timestamp,
                1,
                pending.x,
                pending.y,
            )
        )
        self._write()

    @staticmethod
    def _entry_id(map_id: int, submap: int, text: str) -> str:
        value = f"{map_id:02x}:{submap:02x}:{text}".encode("utf-8")
        return hashlib.sha256(value).hexdigest()[:16]

    @staticmethod
    def _timestamp(value: str) -> datetime | None:
        try:
            result = datetime.fromisoformat(value)
        except ValueError:
            return None
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)

    def _load(self) -> tuple[DialogueEntry, ...]:
        if self.path is None:
            return ()
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            values = document.get("entries", [])
            if not isinstance(values, list):
                return ()
            entries = tuple(
                DialogueEntry(**value)
                for value in values
                if isinstance(value, dict)
            )
            return self._deduplicate(entries)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return ()

    def _deduplicate(
        self,
        entries: tuple[DialogueEntry, ...],
    ) -> tuple[DialogueEntry, ...]:
        merged: dict[tuple[int, int, str], DialogueEntry] = {}
        order: list[tuple[int, int, str]] = []
        for entry in entries:
            text = " ".join(entry.text.split())
            if not text:
                continue
            key = (entry.map_id, entry.submap, text)
            normalized = replace(
                entry,
                entry_id=self._entry_id(entry.map_id, entry.submap, text),
                text=text,
            )
            existing = merged.get(key)
            if existing is None:
                merged[key] = normalized
                order.append(key)
                continue
            first_seen = min(existing.first_seen, normalized.first_seen)
            last_seen = max(existing.last_seen, normalized.last_seen)
            latest = normalized if normalized.last_seen >= existing.last_seen else existing
            merged[key] = replace(
                latest,
                first_seen=first_seen,
                last_seen=last_seen,
                seen_count=max(existing.seen_count, normalized.seen_count),
            )
        return tuple(merged[key] for key in order)

    def _write(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "entries": [asdict(entry) for entry in self._entries],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)