from __future__ import annotations

from dataclasses import dataclass

from .state import DragonWarrior4State
from .reference_data import item_name


TUNNEL_COST = 60000


@dataclass(frozen=True, slots=True)
class ChapterObjective:
    key: str
    title: str
    destination: str
    hint: str
    completed: bool = False
    layer_key: str = ""
    progress: float | None = None


def chapter_objectives(state: DragonWarrior4State) -> tuple[ChapterObjective, ...]:
    if len(state.event_flags) <= 8:
        return ()
    objectives = []
    if state.chapter == 0:
        roster = state.available_party if state.reserve_accessible else state.active_party
        shoes_carried = any(item.item_id == 0x6C for character in roster for item in character.items)
        objectives.append(ChapterObjective(
            "flying-shoes", "Retrieve Flying Shoes", "Secret Playground Dungeon",
            "In a chest inside the dungeon.",
            shoes_carried, "area-33-03",
        ))
    if state.chapter == 1:
        flags = state.event_flags[8]
        active = flags & 0x0C == 0x0C
        completed = bool(flags & 2) and not flags & 8
        if active or completed:
            if active and len(state.event_flags) > 11 and state.event_flags[11] & 2:
                roster = state.available_party if state.reserve_accessible else state.active_party
                nectar_carried = any(item.item_id == 0x75 for character in roster for item in character.items)
                objectives.append(ChapterObjective(
                    "birdsong-nectar", "Obtain Birdsong Nectar", "Birdsong Tower",
                    "Search the marked spot in the tower.",
                    nectar_carried, "area-3f-00",
                ))
            night = state.time_value >= 0x78
            objectives.append(ChapterObjective(
                "santeem-voice", "Restore the King's voice", "Santeem Castle",
                "Use the Birdsong Nectar on the King in the throne room during the day.",
                completed, f"area-01-{2 if night else 1:02x}",
            ))
        if len(state.event_flags) > 12:
            tournament_complete = bool(state.event_flags[9] & 0x40)
            if state.event_flags[10] & 0x20 or tournament_complete:
                rounds = state.event_flags[12] & 7
                layer = f"area-04-{state.location.submap:02x}" if not state.location.is_world and state.location.map_id == 4 else ""
                objectives.append(ChapterObjective(
                    "endor-tournament", "Win the Endor tournament", "Endor Coliseum",
                    f"Rounds won: {min(rounds, 4)} of 4.",
                    tournament_complete, layer,
                    progress=None if tournament_complete else min(rounds, 4) / 4,
                ))
    if state.chapter == 2 and len(state.event_flags) > 12:
        tunnel_complete = bool(state.event_flags[12] & 0x40)
        shortfall = max(0, TUNNEL_COST - state.gold)
        objectives.append(ChapterObjective(
            "branca-tunnel", "Fund the Branca-Endor tunnel", "Branca-Endor tunnel",
            f"Costs {TUNNEL_COST:,} gold. " + (f"{shortfall:,} more to go." if shortfall else "You have enough gold."),
            tunnel_complete,
            progress=None if tunnel_complete else min(1.0, state.gold / TUNNEL_COST),
        ))
    if state.chapter == 3:
        roster = state.available_party if state.reserve_accessible else state.active_party
        carried = {item.item_id for character in roster for item in character.items}
        for item_id, key, destination, layer in (
            (0x5D, "sphere-silence", "Sphere of Silence Cave", "area-31-03"),
            (0x70, "gunpowder-jar", "Aktemto Mine", "area-2d-02"),
        ):
            objectives.append(ChapterObjective(
                key, f"Retrieve {item_name(item_id)}", destination,
                "In a chest here.",
                item_id in carried, layer,
            ))
    if state.chapter == 4 and len(state.event_flags) > 0x18:
        reunion_complete = bool(state.event_flags[0x16] & 8)
        if state.event_flags[0x17] & 0x10 or reunion_complete:
            objectives.append(ChapterObjective(
                "padequia-reunion", "Cure Cristo with the Padequia Root", "Mintos",
                "Bring the Padequia Root back to Cristo.",
                reunion_complete,
            ))
        flags = state.event_flags[0x18]
        if flags & 0x30:
            objectives.append(ChapterObjective(
                "lighthouse-fire", "Put out the evil lighthouse fire", "Great Lighthouse",
                "Use the Fire of Serenity on the flame.",
                bool(flags & 0x10), "area-42-00",
            ))
    return tuple(objectives)


def chapter_transition_losses(state: DragonWarrior4State) -> tuple[str, ...]:
    """Names of carried items that do not survive the end of this chapter."""
    if not 0 <= state.chapter < 4:
        return ()
    carried = {item.item_id for character in state.available_party for item in character.items}
    return tuple(item_name(item_id) for item_id in (0x6B, 0x6C, 0x5D) if item_id in carried)
