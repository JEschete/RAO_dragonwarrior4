from datetime import datetime, timedelta, timezone
import json

from game.dialogue_journal import DialogueJournal


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def test_commits_dialogue_after_text_settles(tmp_path) -> None:
    journal = DialogueJournal(tmp_path / "journal.json")

    assert journal.observe("The king", "Endor", 4, 6, now=NOW) == ()
    assert journal.observe(
        "The king awaits.",
        "Endor",
        4,
        6,
        now=NOW + timedelta(milliseconds=250),
    ) == ()
    entries = journal.observe(
        "The king awaits.",
        "Endor",
        4,
        6,
        now=NOW + timedelta(seconds=1),
    )

    assert len(entries) == 1
    assert entries[0].text == "The king awaits."
    assert entries[0].location == "Endor"


def test_replaces_recent_typewriter_prefix_instead_of_keeping_fragments(tmp_path) -> None:
    journal = DialogueJournal(tmp_path / "journal.json")
    journal.observe("The king", "Endor", 4, 6, now=NOW)
    journal.observe("The king", "Endor", 4, 6, now=NOW + timedelta(seconds=1))
    journal.observe("The king awaits.", "Endor", 4, 6, now=NOW + timedelta(seconds=2))
    entries = journal.observe(
        "The king awaits.",
        "Endor",
        4,
        6,
        now=NOW + timedelta(seconds=3),
    )

    assert [entry.text for entry in entries] == ["The king awaits."]


def test_commits_previous_line_when_dialogue_changes_and_deduplicates_repeats(
    tmp_path,
) -> None:
    journal = DialogueJournal(tmp_path / "journal.json")
    journal.observe("First line.", "Keeleon", 0, 1, now=NOW)
    entries = journal.observe(
        "Second line.",
        "Keeleon",
        0,
        1,
        now=NOW + timedelta(milliseconds=200),
    )
    assert [entry.text for entry in entries] == ["First line."]

    journal.observe("", "Keeleon", 0, 1, now=NOW + timedelta(seconds=1))
    journal.observe("First line.", "Keeleon", 0, 1, now=NOW + timedelta(seconds=10))
    journal.observe("", "Keeleon", 0, 1, now=NOW + timedelta(seconds=11))

    first = next(entry for entry in journal.entries if entry.text == "First line.")
    assert first.seen_count == 2


def test_reloads_persisted_journal(tmp_path) -> None:
    path = tmp_path / "journal.json"
    journal = DialogueJournal(path)
    journal.observe("Recorded line.", "Burland", 2, 1, now=NOW)
    journal.observe("", "Burland", 2, 1, now=NOW + timedelta(seconds=1))

    reloaded = DialogueJournal(path)

    assert reloaded.entries == journal.entries


def test_rapid_duplicate_after_clear_does_not_increment_seen_count(tmp_path) -> None:
    journal = DialogueJournal(tmp_path / "journal.json")
    journal.observe("Repeated line.", "Endor", 4, 0, now=NOW)
    journal.observe("", "Endor", 4, 0, now=NOW + timedelta(seconds=1))
    journal.observe("Repeated line.", "Endor", 4, 0, now=NOW + timedelta(seconds=2))
    journal.observe("", "Endor", 4, 0, now=NOW + timedelta(seconds=3))

    assert len(journal.entries) == 1
    assert journal.entries[0].seen_count == 1


def test_load_merges_duplicate_records_in_existing_file(tmp_path) -> None:
    path = tmp_path / "journal.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "entry_id": "old-one",
                        "text": "  Same   line. ",
                        "location": "Endor",
                        "map_id": 4,
                        "submap": 0,
                        "first_seen": "2026-09-09T12:00:00+00:00",
                        "last_seen": "2026-09-09T12:00:00+00:00",
                        "seen_count": 1,
                    },
                    {
                        "entry_id": "old-two",
                        "text": "Same line.",
                        "location": "Endor",
                        "map_id": 4,
                        "submap": 0,
                        "first_seen": "2026-09-09T12:01:00+00:00",
                        "last_seen": "2026-09-09T12:01:00+00:00",
                        "seen_count": 2,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    journal = DialogueJournal(path)

    assert len(journal.entries) == 1
    assert journal.entries[0].text == "Same line."
    assert journal.entries[0].seen_count == 2
    assert journal.entries[0].first_seen == "2026-09-09T12:00:00+00:00"
    assert journal.entries[0].last_seen == "2026-09-09T12:01:00+00:00"