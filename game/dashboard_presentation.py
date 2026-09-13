from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


WORKSPACE_SPECS = (
    ("atlas", "Atlas", "map", "ROM terrain, live position, and map features"),
    ("party", "Party", "cards", "Active party and reserve companions"),
    ("journey", "Journey", "overview", "Progress, travel, resources, and achievements"),
    ("journal", "Journal", "records", "Previously read dialogue"),
    ("encounters", "Combat Log", "records", "Active and completed encounters"),
    ("archive", "Archive", "overview", "Memory, ROM, and research evidence"),
)


def static_presentation(world_maps: dict[str, tuple[object, ...]]) -> dict[str, Any]:
    return {
        "title": "Dragon Warrior IV",
        "subtitle": "Cartographer's Companion",
        "workspaces": [
            {
                "key": key,
                "title": title,
                "kind": kind,
                "subtitle": subtitle,
            }
            for key, title, kind, subtitle in WORKSPACE_SPECS
        ],
        "controls": [
            {
                "key": "world_map",
                "workspace": "atlas",
                "label": "World map",
                "kind": "choice",
                "default": "world",
                "choices": [
                    {"value": key, "label": str(specification[0])}
                    for key, specification in world_maps.items()
                ],
            }
        ],
        "map_overlay_kinds": [
            "objective",
            "collectibles",
            "entrance",
            "services",
            "locks",
            "connections",
            "npcs",
            "encounters",
        ],
    }


def live_presentation(
    static: dict[str, Any],
    live: dict[str, Any],
) -> dict[str, Any]:
    location = live.get("location", {})
    reference = live.get("reference", {})
    return {
        "status": {
            "title": str(location.get("title", "Waiting for game")),
            "mode": str(live.get("mode", "waiting")).upper(),
            "detail": (
                f"Memory: {reference.get('memory_region', '--')} / "
                f"ROM: {reference.get('rom_region', '--')}"
            ),
        },
        "workspaces": {
            "atlas": _atlas_workspace(static, live),
            "party": _party_workspace(live),
            "journey": _journey_workspace(static, live),
            "journal": _journal_workspace(live),
            "encounters": _encounter_workspace(live),
            "archive": _archive_workspace(static, live),
        },
    }


def _atlas_workspace(static: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    location = live.get("location", {})
    map_key = str(location.get("map_key", ""))
    descriptor = next(
        (
            value
            for value in static.get("maps", [])
            if isinstance(value, dict) and value.get("key") == map_key
        ),
        {},
    )
    features = []
    for feature in live.get("atlas", {}).get("features", []):
        if not isinstance(feature, dict):
            continue
        kind = str(feature.get("kind", "point"))
        features.append(
            {
                "key": str(feature.get("id", "")),
                "title": str(feature.get("title", "Feature")),
                "subtitle": (
                    f"({feature.get('x', 0)},{feature.get('y', 0)}) · "
                    f"{feature.get('distance', 0)} {feature.get('direction', 'here')}"
                ),
                "detail": str(feature.get("detail", "No additional details")),
                "kind": kind,
                "marker": str(feature.get("marker", "")),
                "x": int(feature.get("x", 0)),
                "y": int(feature.get("y", 0)),
                "game_completed": bool(feature.get("completed")),
                "can_complete": kind in {"collectibles", "objective"},
            }
        )
    sections = [
        {
            "key": "position",
            "title": "Position",
            "rows": [
                {"label": "Coordinates", "value": f"X {location.get('x', 0)} / Y {location.get('y', 0)}"},
                {"label": "Evidence", "value": str(location.get("evidence", "Unknown"))},
            ],
        },
        {
            "key": "dialogue",
            "title": "Current dialogue",
            "rows": [
                {
                    "label": "Dialogue",
                    "value": str(live.get("dialogue", "")).strip() or "No active dialogue",
                }
            ],
        },
    ]
    atlas = _mapping(static.get("atlas"))
    if not atlas.get("available"):
        sections.append(
            {
                "key": "availability",
                "title": "Atlas unavailable",
                "rows": [
                    {
                        "label": "Reason",
                        "value": str(atlas.get("error", "Configure a supported ROM")),
                        "tone": "danger",
                    }
                ],
            }
        )
    credit = str(descriptor.get("credit", "")).strip()
    source_url = str(descriptor.get("source_url", "")).strip()
    if credit or source_url:
        sections.append(
            {
                "key": "source",
                "title": "Map source",
                "rows": [
                    {
                        "label": "Source",
                        "value": credit or "Source documentation",
                        "url": source_url,
                    }
                ],
            }
        )
    return {
        "heading": "Living Atlas",
        "subtitle": "ROM terrain, live position, and map features",
        "map": {
            **descriptor,
            "key": map_key,
            "title": str(location.get("title", descriptor.get("title", "Unknown map"))),
            "image_path": str(location.get("image_path", descriptor.get("path", ""))),
            "x": int(location.get("x", 0)),
            "y": int(location.get("y", 0)),
            "is_world": live.get("mode") == "world",
        },
        "items": features,
        "sections": sections,
    }


def _party_workspace(live: dict[str, Any]) -> dict[str, Any]:
    cards = []
    for member in live.get("party", []):
        if not isinstance(member, dict) or (
            not member.get("active") and int(member.get("level", 0)) == 0
        ):
            continue
        conditions = []
        if not member.get("alive", False):
            conditions.append("DOWN")
        if member.get("poisoned"):
            conditions.append("POISONED")
        if member.get("paralyzed"):
            conditions.append("PARALYZED")
        status = " / ".join(conditions) if conditions else "READY"
        stats, inventory, battle_spells, field_spells = party_detail_lines(member)
        maximum_hp = int(member.get("max_hp", 0))
        maximum_mp = int(member.get("max_mp", 0))
        cards.append(
            {
                "key": str(member.get("character_id", len(cards))),
                "title": str(member.get("name", "Companion")),
                "subtitle": (
                    f"{'Active' if member.get('active') else 'Reserve'} · "
                    f"Level {int(member.get('level', 0))}"
                ),
                "status": status,
                "tone": "danger" if conditions else "success",
                "metrics": [
                    {
                        "label": "HP",
                        "value": f"{int(member.get('hp', 0)):,} / {maximum_hp:,}",
                        "progress": (
                            int(member.get("hp", 0)) / maximum_hp
                            if maximum_hp
                            else 0.0
                        ),
                    },
                    {
                        "label": "MP",
                        "value": f"{int(member.get('mp', 0)):,} / {maximum_mp:,}",
                        "progress": (
                            int(member.get("mp", 0)) / maximum_mp
                            if maximum_mp
                            else 0.0
                        ),
                    },
                ],
                "rows": [
                    {"label": "Experience", "value": f"{int(member.get('experience', 0)):,}"},
                    {"label": "Stats", "value": stats},
                    {"label": "Inventory", "value": inventory},
                    {"label": "Battle spells", "value": battle_spells.removeprefix("Battle: ")},
                    {"label": "Field spells", "value": field_spells.removeprefix("Field: ")},
                ],
            }
        )
    return {
        "heading": "The Chosen",
        "subtitle": (
            f"{sum(bool(card['subtitle'].startswith('Active')) for card in cards)} active / "
            f"{len(cards)} recorded companions"
        ),
        "cards": cards,
    }


def _journey_workspace(static: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    journey = live.get("journey", {})
    chapter = int(journey.get("chapter", 0))
    chapters = static.get("chapters", [])
    travel_rows = [
        {"label": "Boat", "value": "Ready" if journey.get("has_boat") else "Locked"},
        {"label": "Balloon", "value": "Ready" if journey.get("has_balloon") else "Locked"},
        {"label": "Time", "value": str(journey.get("time_name", "Unknown"))},
        {"label": "Tactics", "value": str(journey.get("tactics", "Unknown"))},
    ]
    sections = [
        {"key": "travel", "title": "Travel state", "rows": travel_rows},
        {
            "key": "returns",
            "title": "Return network",
            "rows": [
                {
                    "label": "Destinations",
                    "value": " / ".join(
                        str(value) for value in journey.get("return_locations", [])
                    )
                    or "No destinations recorded",
                }
            ],
        },
    ]
    stock = [
        value
        for value in journey.get("taloon_shop_stock", [])
        if isinstance(value, dict)
    ]
    if chapter == 2 or any(int(value.get("count", 0)) for value in stock):
        sections.append(
            {
                "key": "stock",
                "title": "Lakanaba shop stock",
                "rows": [
                    {
                        "label": str(value.get("name", "Item")),
                        "value": str(int(value.get("count", 0))),
                    }
                    for value in stock
                ],
            }
        )
    achievement_value, achievement_detail = retroachievements_summary(static)
    locked = [
        achievement
        for achievement in static.get("retroachievements", {}).get("achievements", [])
        if isinstance(achievement, dict) and not achievement.get("unlocked")
    ]
    sections.append(
        {
            "key": "achievements",
            "title": "RetroAchievements",
            "subtitle": achievement_value,
            "rows": [
                {"label": "Account", "value": achievement_detail},
                *(
                    {
                        "label": str(achievement.get("title", "Achievement")),
                        "value": f"{achievement.get('points', 0)} points",
                        "detail": str(achievement.get("description", "")),
                    }
                    for achievement in locked[:8]
                ),
            ],
        }
    )
    return {
        "heading": "The Journey",
        "subtitle": str(journey.get("chapter_name", "Unknown chapter")),
        "progress": {
            "value": chapter + 1,
            "maximum": len(chapters),
            "labels": [str(value) for value in chapters],
        },
        "metrics": [
            {"label": "Gold", "value": f"{int(journey.get('gold', 0)):,}"},
            {"label": "Casino", "value": f"{int(journey.get('casino_coins', 0)):,}"},
            {"label": "Medals", "value": str(int(journey.get("small_medals", 0)))},
            {
                "label": "Treasure",
                "value": f"{journey.get('treasure_opened', 0)}/{journey.get('treasure_total', 0)}",
            },
        ],
        "sections": sections,
    }


def _journal_workspace(live: dict[str, Any]) -> dict[str, Any]:
    records = []
    for entry in reversed(live.get("journal", [])):
        if not isinstance(entry, dict):
            continue
        text = " ".join(str(entry.get("text", "")).split())
        seen = int(entry.get("seen_count", 1))
        records.append(
            {
                "key": str(entry.get("entry_id", "")),
                "title": str(entry.get("location", "Unknown location")),
                "subtitle": text if len(text) <= 90 else text[:87] + "...",
                "meta": (
                    f"First read {_journal_time(str(entry.get('first_seen', '')))} · "
                    f"Last read {_journal_time(str(entry.get('last_seen', '')))} · "
                    f"Seen {seen} {'time' if seen == 1 else 'times'}"
                ),
                "detail": str(entry.get("text", "")),
                "search": f"{entry.get('location', '')} {entry.get('text', '')}",
            }
        )
    return {
        "heading": "Dialogue Journal",
        "subtitle": "Previously read dialogue, deduplicated across sessions",
        "search_placeholder": "Search dialogue",
        "records": records,
        "empty": "Dialogue will appear after it has finished drawing in game.",
    }


def _encounter_workspace(live: dict[str, Any]) -> dict[str, Any]:
    combat = live.get("combat", {})
    active = combat.get("active")
    if isinstance(active, dict):
        active_status = "Capturing"
        active_detail = active_encounter_text(active)
        active_tone = "danger"
    elif not combat.get("memory_available", False):
        active_status = "Unavailable"
        active_detail = str(combat.get("detector_evidence", "Battle memory unavailable"))
        active_tone = "danger"
    else:
        active_status = "Idle"
        active_detail = "Waiting for coherent enemy slots"
        active_tone = "muted"
    summary, locations, enemies = combat_analytics_lines(combat.get("analytics", {}))
    records = []
    for encounter in combat.get("recent", []):
        if not isinstance(encounter, dict):
            continue
        outcome = str(encounter.get("outcome", "unknown")).replace("_", " ").upper()
        labels = ", ".join(str(value) for value in encounter.get("enemy_labels", []))
        records.append(
            {
                "key": str(encounter.get("encounter_id", "")),
                "title": f"{outcome} · {encounter.get('end_location', 'Unknown')}",
                "subtitle": labels or "Unknown enemies",
                "meta": (
                    f"{_journal_time(str(encounter.get('ended_at', '')))} · "
                    f"{float(encounter.get('duration_seconds', 0)):.2f}s · "
                    f"{int(encounter.get('sample_count', 0))} distinct frames"
                ),
                "detail": (
                    f"Rewards: {int(encounter.get('reward_experience', 0)):,} XP / "
                    f"{int(encounter.get('reward_gold', 0)):,} gold"
                ),
                "detail_path": _encounter_path(combat, encounter),
                "search": f"{outcome} {encounter.get('end_location', '')} {labels}",
            }
        )
    return {
        "heading": "Combat Log",
        "subtitle": "Fast-captured battle flow and completed combat records",
        "sections": [
            {
                "key": "active",
                "title": "Live encounter",
                "rows": [
                    {
                        "label": active_status,
                        "value": active_detail,
                        "tone": active_tone,
                    }
                ],
            },
            {
                "key": "analytics",
                "title": "Combat record",
                "rows": [
                    {"label": "Summary", "value": summary},
                    {"label": "Locations", "value": locations},
                    {"label": "Monsters", "value": enemies},
                ],
            },
        ],
        "search_placeholder": "Search encounters",
        "records": records,
        "empty": "Completed combat records will appear here.",
    }


def _archive_workspace(static: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    reference = live.get("reference", {})
    return {
        "heading": "Research Archive",
        "subtitle": (
            f"{reference.get('saved_pages', 0)}/{reference.get('total_pages', 0)} "
            "saved references available"
        ),
        "sections": [
            {
                "key": "evidence",
                "title": "Active evidence",
                "rows": [
                    {"label": "Live memory", "value": str(reference.get("memory_region", "Unknown"))},
                    {"label": "ROM layout", "value": str(reference.get("rom_region", "Unavailable"))},
                    {"label": "Location source", "value": str(reference.get("evidence", "Unknown"))},
                    {"label": "Playthrough", "value": str(live.get("playthrough", "Unidentified"))},
                ],
            },
            {
                "key": "sources",
                "title": "Saved pages",
                "rows": [
                    {
                        "label": str(source.get("title", "Reference")),
                        "value": "Available" if source.get("available") else "Missing",
                        "detail": str(source.get("purpose", "")),
                        "url": str(source.get("url", "")),
                        "tone": "success" if source.get("available") else "danger",
                    }
                    for source in static.get("sources", [])
                    if isinstance(source, dict)
                ],
            },
            {
                "key": "tile-behaviors",
                "title": "Tile behavior legend",
                "rows": [
                    {
                        "label": f"${int(entry.get('value', 0)):02X}",
                        "value": str(entry.get("name", "")),
                    }
                    for entry in static.get("tile_behaviors", [])
                    if isinstance(entry, dict)
                ],
            },
        ],
    }


def party_detail_lines(member: dict[str, Any]) -> tuple[str, str, str, str]:
    items = [item for item in member.get("items", []) if isinstance(item, dict)]
    equipped = ", ".join(
        f"{str(item.get('category', 'item')).title()}: {item.get('name', 'Unknown item')}"
        for item in items
        if item.get("equipped")
    ) or "none"
    carried = ", ".join(
        str(item.get("name", "Unknown item"))
        for item in items
        if not item.get("equipped")
    ) or "none"
    spells = [spell for spell in member.get("spells", []) if isinstance(spell, dict)]
    battle_spells = ", ".join(
        str(spell.get("name", "Unknown"))
        for spell in spells
        if spell.get("usage") == "battle"
    ) or "none"
    field_spells = ", ".join(
        str(spell.get("name", "Unknown"))
        for spell in spells
        if spell.get("usage") == "field"
    ) or "none"
    return (
        (
            f"STR {int(member.get('strength', 0))}  ·  "
            f"AGI {int(member.get('agility', 0))}  ·  "
            f"VIT {int(member.get('vitality', 0))}  ·  "
            f"INT {int(member.get('intelligence', 0))}  ·  "
            f"LUCK {int(member.get('luck', 0))}"
        ),
        f"Equipped: {equipped}\nPack: {carried}",
        f"Battle: {battle_spells}",
        f"Field: {field_spells}",
    )


def retroachievements_summary(document: dict[str, Any]) -> tuple[str, str]:
    progress = document.get("retroachievements", {})
    if not isinstance(progress, dict):
        return "Unavailable", "RetroAchievements progress is unavailable"
    username = str(progress.get("username", "")).strip()
    unlocked = int(progress.get("unlocked", 0))
    total = int(progress.get("total", 0))
    points = int(progress.get("points", 0))
    total_points = int(progress.get("total_points", 0))
    message = str(progress.get("message", "")).strip()
    if username:
        return (
            f"{unlocked}/{total} unlocked · {points}/{total_points} points",
            f"Account: {username}",
        )
    return "Unavailable", message or "Connect a RetroAchievements account to track progress"


def combat_analytics_lines(analytics: dict[str, Any]) -> tuple[str, str, str]:
    total = int(analytics.get("total_encounters", 0))
    session = int(analytics.get("session_encounters", 0))
    win_rate = float(analytics.get("win_rate", 0.0))
    rewards = (
        f"{int(analytics.get('reward_experience', 0)):,} XP / "
        f"{int(analytics.get('reward_gold', 0)):,} gold"
    )
    locations = analytics.get("locations", [])
    location_text = " · ".join(
        f"{value.get('name', 'Unknown')} ({int(value.get('encounters', 0))})"
        for value in locations[:4]
        if isinstance(value, dict)
    ) or "No encounter locations recorded"
    enemies = analytics.get("enemies", [])
    enemy_text = " · ".join(
        f"{value.get('label', 'Unknown')} ({int(value.get('encounters', 0))})"
        for value in enemies[:6]
        if isinstance(value, dict)
    ) or "No identified monster groups recorded"
    return (
        f"{total} lifetime / {session} this session / {win_rate:.0%} victories / {rewards}",
        location_text,
        enemy_text,
    )


def active_encounter_text(active: dict[str, Any]) -> str:
    enemies = [
        enemy for enemy in active.get("enemies", []) if isinstance(enemy, dict)
    ]
    if not enemies:
        return "Enemy identity pending"
    enemy_text = ", ".join(
        f"{enemy.get('label', 'Enemy')} HP {enemy.get('final_hp', 0)}"
        for enemy in enemies
    )
    highest_attack = max(enemies, key=lambda enemy: int(enemy.get("attack", 0)))
    fastest = max(enemies, key=lambda enemy: int(enemy.get("agility", 0)))
    return (
        f"{active.get('location', 'Unknown')}  |  "
        f"{active.get('frame_count', 0)} distinct frames  |  {enemy_text}\n"
        f"Highest ATK {highest_attack.get('label', 'Enemy')} "
        f"{int(highest_attack.get('attack', 0))}  |  Fastest "
        f"{fastest.get('label', 'Enemy')} {int(fastest.get('agility', 0))} AGI"
    )


def feature_is_complete(feature: dict[str, Any], manual: set[str]) -> bool:
    return bool(feature.get("completed")) or str(feature.get("id", "")) in manual


def feature_status(feature: dict[str, Any], manual: set[str]) -> str:
    if feature.get("completed"):
        return "LOOTED IN GAME"
    if str(feature.get("id", "")) in manual:
        return "MARKED COMPLETE"
    return "AVAILABLE"


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _journal_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value or "unknown"


def _encounter_path(combat: dict[str, Any], encounter: dict[str, Any]) -> str:
    root = str(combat.get("archive_root", "")).strip()
    encounter_id = str(encounter.get("encounter_id", ""))
    if not root or not encounter_id:
        return ""
    try:
        ended = datetime.fromisoformat(str(encounter.get("ended_at", "")))
    except ValueError:
        return ""
    return str(
        Path(root)
        / f"{ended.year:04d}"
        / f"{ended.month:02d}"
        / f"{ended.day:02d}"
        / f"{encounter_id}.json"
    )