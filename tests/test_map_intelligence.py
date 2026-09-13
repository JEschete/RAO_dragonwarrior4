from datetime import datetime, timezone

from game.dialogue_journal import DialogueEntry
from game.map_intelligence import MapIntelligence
from game.state import LocationState


def _location(
    title: str,
    map_id: int,
    submap: int,
    x: int,
    y: int,
) -> LocationState:
    return LocationState(
        title,
        "Dungeon / town",
        map_id,
        submap,
        x,
        y,
        False,
        (map_id << 8) | submap,
        "US",
        "test",
    )


def test_records_both_ends_of_observed_transition_and_reloads(tmp_path) -> None:
    path = tmp_path / "map-intelligence.json"
    knowledge = MapIntelligence(path)
    endor = _location("Endor", 4, 0, 8, 12)
    castle = _location("Endor Castle", 4, 1, 3, 7)

    assert not knowledge.observe(endor, "area-04-00")
    assert knowledge.observe(castle, "area-04-01")

    assert len(knowledge.transitions) == 2
    reloaded = MapIntelligence(path)
    overlay = reloaded.overlay(endor, "area-04-00", ())
    assert overlay is not None
    assert overlay.waypoints[0].title == "Transition to Endor Castle"
    assert (overlay.waypoints[0].x, overlay.waypoints[0].y) == (8, 12)


def test_adds_observed_dialogue_positions_to_current_map(tmp_path) -> None:
    knowledge = MapIntelligence(tmp_path / "map-intelligence.json")
    location = _location("Endor", 4, 0, 8, 12)
    entry = DialogueEntry(
        "entry",
        "The king awaits beyond the throne room.",
        "Endor",
        4,
        0,
        datetime(2026, 9, 9, tzinfo=timezone.utc).isoformat(),
        datetime(2026, 9, 9, tzinfo=timezone.utc).isoformat(),
        1,
        9,
        13,
    )

    overlay = knowledge.overlay(location, "area-04-00", (entry,))

    assert overlay is not None
    assert overlay.waypoints[0].kind == "npcs"
    assert overlay.waypoints[0].marker == "person"
    assert (overlay.waypoints[0].x, overlay.waypoints[0].y) == (9, 13)


def test_tracks_each_encounter_once_at_its_observed_coordinate(tmp_path) -> None:
    path = tmp_path / "map-intelligence.json"
    knowledge = MapIntelligence(path)
    encounter = {
        "encounter_id": "battle-one",
        "enemies": [{"label": "Monster $12"}],
    }

    assert knowledge.observe_encounter(encounter, "area-04-00", 9, 13)
    assert not knowledge.observe_encounter(encounter, "area-04-00", 9, 13)
    assert len(knowledge.hotspots) == 1
    assert knowledge.hotspots[0].encounters == 1

    reloaded = MapIntelligence(path)
    overlay = reloaded.overlay(_location("Endor", 4, 0, 9, 13), "area-04-00", ())
    assert overlay is not None
    marker = overlay.waypoints[0]
    assert marker.kind == "encounters"
    assert marker.title == "1 observed encounter"
    assert marker.detail == "Monster $12"