from __future__ import annotations

from dataclasses import asdict
from typing import Any

from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import MapOverlay

from .battle import BattleState
from .dialogue_journal import DialogueEntry
from .encounter_log import EncounterRecord
from .reference_data import CHAPTERS, TACTICS, TILE_BEHAVIORS, ReferenceSource
from .rom_assets import DragonWarrior4RomAssets
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

    def static_document(self) -> dict[str, Any]:
        maps = self.assets.map_layers() if self.assets is not None else ()
        return {
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
                "unlocked": len(self.progress.unlocked_ids) if self.progress else 0,
                "message": self.progress.message if self.progress else "",
            },
            "atlas": {
                "available": self.assets is not None,
                "region": self.assets.region if self.assets is not None else "",
                "content_hash": self.assets.content_hash if self.assets is not None else "",
                "error": self.asset_error,
            },
        }

    def dynamic_document(
        self,
        state: DragonWarrior4State,
        overlay: MapOverlay | None,
        journal_entries: tuple[DialogueEntry, ...] = (),
        battle: BattleState | None = None,
        active_encounter: dict[str, Any] | None = None,
        encounter_entries: tuple[EncounterRecord, ...] = (),
    ) -> dict[str, Any]:
        image_path = ""
        map_key = (
            "world"
            if state.location.is_world
            else f"area-{state.location.map_id:02x}-{state.location.submap:02x}"
        )
        if self.assets is not None:
            try:
                if state.location.is_world:
                    image_path = str(self.assets.render_world_map("world"))
                else:
                    image_path = str(
                        self.assets.render_area_map(state.location.layer_id)
                    )
            except (OSError, ValueError):
                image_path = ""
        features = []
        if overlay is not None:
            features = [
                {
                    **asdict(point),
                    "id": (
                        f"{map_key}:{point.kind}:{point.x}:{point.y}"
                    ),
                }
                for point in overlay.waypoints
            ]
        return {
            "mode": "world" if state.location.is_world else "area",
            "location": {
                **asdict(state.location),
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
                "archive_format": "One JSON file per completed combat",
            },
        }

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