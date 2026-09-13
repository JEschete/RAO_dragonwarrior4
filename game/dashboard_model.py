from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import MapOverlay

from .achievements import ACHIEVEMENTS, TOTAL_POINTS
from .battle import BattleState
from .dashboard_presentation import live_presentation, static_presentation
from .dialogue_journal import DialogueEntry
from .encounter_log import EncounterRecord
from .reference_data import CHAPTERS, TACTICS, TILE_BEHAVIORS, ReferenceSource
from .rom_assets import WORLD_MAP_SPECS, DragonWarrior4RomAssets
from .state import DragonWarrior4State


class DashboardModel:
    def __init__(
        self,
        assets: DragonWarrior4RomAssets | None,
        sources: tuple[ReferenceSource, ...],
        progress: RAProgress | None,
        asset_error: str = "",
    ) -> None:
        self.assets = assets
        self.sources = sources
        self.progress = progress
        self.asset_error = asset_error
        self._static_document: dict[str, Any] | None = None

    def static_document(self) -> dict[str, Any]:
        map_layers = getattr(self.assets, "map_layers", None)
        maps = map_layers() if callable(map_layers) else ()
        unlocked_ids = self.progress.unlocked_ids if self.progress else frozenset()
        unlocked_points = sum(
            achievement.points
            for achievement in ACHIEVEMENTS
            if achievement.achievement_id in unlocked_ids
        )
        document = {
            "schema_version": 1,
            "game": "Dragon Warrior IV",
            "workspaces": [
                "atlas",
                "party",
                "journey",
                "journal",
                "encounters",
                "archive",
            ],
            "maps": [
                {
                    "key": layer.key,
                    "title": layer.title,
                    "area": layer.area,
                    "path": str(layer.image_path),
                    "map_id": layer.map_id,
                    "width": layer.wrap_width,
                    "height": layer.wrap_height,
                    "tile_width": layer.tile_width,
                    "tile_height": layer.tile_height,
                    "credit": layer.credit,
                    "source_url": layer.source_url,
                    "offset_x": layer.offset_x,
                    "offset_y": layer.offset_y,
                    "anchor_x": layer.anchor_x,
                    "anchor_y": layer.anchor_y,
                    "wraps": layer.wraps,
                }
                for layer in maps
            ],
            "chapters": list(CHAPTERS),
            "tactics": list(TACTICS),
            "tile_behaviors": [
                {"value": value, "name": name}
                for value, name in sorted(TILE_BEHAVIORS.items())
            ],
            "sources": [asdict(source) for source in self.sources],
            "retroachievements": {
                "username": self.progress.username if self.progress else "",
                "unlocked": sum(
                    achievement.achievement_id in unlocked_ids
                    for achievement in ACHIEVEMENTS
                ),
                "total": len(ACHIEVEMENTS),
                "points": unlocked_points,
                "total_points": TOTAL_POINTS,
                "message": self.progress.message if self.progress else "",
                "achievements": [
                    {
                        **asdict(achievement),
                        "unlocked": achievement.achievement_id in unlocked_ids,
                    }
                    for achievement in ACHIEVEMENTS
                ],
            },
            "atlas": {
                "available": self.assets is not None,
                "region": self.assets.region if self.assets is not None else "",
                "content_hash": (
                    str(getattr(self.assets, "content_hash", ""))
                    if self.assets is not None
                    else ""
                ),
                "error": self.asset_error,
            },
        }
        document["presentation"] = static_presentation(WORLD_MAP_SPECS)
        self._static_document = document
        return document

    def dynamic_document(
        self,
        state: DragonWarrior4State,
        overlay: MapOverlay | None,
        journal_entries: tuple[DialogueEntry, ...] = (),
        battle: BattleState | None = None,
        active_encounter: dict[str, Any] | None = None,
        encounter_entries: tuple[EncounterRecord, ...] = (),
        encounter_root: Path | None = None,
        playthrough_id: str = "",
        combat_analytics: dict[str, Any] | None = None,
        world_map_key: str = "world",
    ) -> dict[str, Any]:
        if world_map_key not in WORLD_MAP_SPECS:
            world_map_key = "world"
        image_path = ""
        map_key = (
            world_map_key
            if state.location.is_world
            else f"area-{state.location.map_id:02x}-{state.location.submap:02x}"
        )
        if self.assets is not None:
            try:
                if state.location.is_world:
                    image_path = str(self.assets.render_world_map(world_map_key))
                else:
                    image_path = str(
                        self.assets.render_area_map(state.location.layer_id)
                    )
            except (OSError, ValueError):
                image_path = ""
        features = []
        if overlay is not None:
            for point in overlay.waypoints:
                delta_x = point.x - state.location.x
                delta_y = point.y - state.location.y
                features.append(
                    {
                        **asdict(point),
                        "id": f"{map_key}:{point.kind}:{point.x}:{point.y}",
                        "distance": abs(delta_x) + abs(delta_y),
                        "direction": self._direction(delta_x, delta_y),
                    }
                )
            features.sort(
                key=lambda point: (
                    int(point["distance"]),
                    str(point["kind"]),
                    str(point["title"]),
                )
            )
        location = asdict(state.location)
        if state.location.is_world:
            title, area = WORLD_MAP_SPECS[world_map_key][:2]
            evidence = state.location.evidence
            if "outdoor layer selected in companion" not in evidence:
                evidence += "; outdoor layer selected in companion"
            location.update(
                title=title,
                area=area,
                evidence=evidence,
            )
        document = {
            "schema_version": 1,
            "mode": "world" if state.location.is_world else "area",
            "location": {
                **location,
                "map_key": map_key,
                "image_path": image_path,
            },
            "atlas": {
                "features": features,
            },
            "party": [asdict(character) for character in state.characters],
            "journey": {
                "chapter": state.chapter,
                "chapter_name": state.chapter_name,
                "tactics": state.tactics_name,
                "gold": state.gold,
                "casino_coins": state.casino_coins,
                "time_value": state.time_value,
                "time_name": state.time_name,
                "return_locations": list(state.return_locations),
                "treasure_opened": state.treasure_opened,
                "treasure_total": state.treasure_total,
                "has_boat": state.has_boat,
                "has_balloon": state.has_balloon,
                "small_medals": state.small_medals,
                "taloon_shop_stock": [
                    {"name": name, "count": count}
                    for name, count in state.taloon_shop_stock
                ],
            },
            "reference": {
                "memory_region": state.location.memory_region,
                "evidence": state.location.evidence,
                "rom_region": (
                    self.assets.region if self.assets is not None else "Unavailable"
                ),
                "saved_pages": sum(source.available for source in self.sources),
                "total_pages": len(self.sources),
            },
            "dialogue": state.dialogue,
            "journal": [asdict(entry) for entry in journal_entries],
            "combat": {
                "memory_available": battle.available if battle is not None else False,
                "battle_active": battle.active if battle is not None else False,
                "detector_evidence": (
                    battle.detector_evidence if battle is not None else ""
                ),
                "active": active_encounter,
                "recent": [
                    self._encounter_summary(entry)
                    for entry in encounter_entries
                ],
                "archive_root": str(encounter_root) if encounter_root else "",
                "archive_format": "One JSON file per completed combat",
                "analytics": combat_analytics or {},
            },
            "playthrough": playthrough_id,
        }
        static = self._static_document or self.static_document()
        document["presentation"] = live_presentation(static, document)
        return document

    @staticmethod
    def waiting_document(detail: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "mode": "waiting",
            "location": {"title": "Waiting for readable NES memory"},
            "detail": detail,
            "presentation": {
                "status": {
                    "title": "Waiting for readable NES memory",
                    "mode": "WAITING",
                    "detail": detail,
                },
                "workspaces": {},
            },
        }

    @staticmethod
    def _direction(delta_x: int, delta_y: int) -> str:
        if delta_x == delta_y == 0:
            return "here"
        horizontal = "east" if delta_x > 0 else "west"
        vertical = "south" if delta_y > 0 else "north"
        if delta_x == 0:
            return vertical
        if delta_y == 0:
            return horizontal
        return f"{vertical}-{horizontal}"

    @staticmethod
    def _encounter_summary(entry: EncounterRecord) -> dict[str, Any]:
        return {
            "encounter_id": entry.encounter_id,
            "started_at": entry.started_at,
            "ended_at": entry.ended_at,
            "duration_seconds": entry.duration_seconds,
            "outcome": entry.outcome,
            "start_location": entry.start_location,
            "end_location": entry.end_location,
            "reward_gold": entry.reward_gold,
            "reward_experience": entry.reward_experience,
            "enemy_count": len(entry.enemies),
            "enemy_labels": [enemy.label for enemy in entry.enemies],
            "sample_count": entry.sample_count,
        }