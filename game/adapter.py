from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
import re

from retroarch_overlay.core.contracts import GameContext, MemoryReader
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import (
    GameDisplaySpec,
    MapDocument,
    MapOverlay,
    MapPosition,
    OverlaySnapshot,
    PanelAction,
    PanelRow,
    PanelSection,
    RetroArchStatus,
)
from retroarch_overlay.retroarch import RetroArchError

from .achievements import ACHIEVEMENTS, TOTAL_POINTS
from .battle import (
    BATTLE_MEMORY_ADDRESS,
    BATTLE_MEMORY_SIZE,
    BATTLE_TEXT_ADDRESS,
    BATTLE_TEXT_SIZE,
    BattleState,
    observed_monster_names,
    read_battle_state,
)
from .combat_analytics import CombatAnalytics
from .dashboard_bridge import DashboardBridge
from .dashboard_model import DashboardModel
from .dialogue_journal import DialogueJournal
from .encounter_log import EncounterLog
from .map_intelligence import MapIntelligence
from .reference_data import load_submap_names, load_treasure_records, reference_sources
from .rom_assets import WORLD_MAP_SPECS, DragonWarrior4RomAssets
from .state import RAM_SIZE, WRAM_ADDRESS, WRAM_SIZE, DragonWarrior4State, read_state


RA_GAME_ID = 4612
DISPLAY_SPEC = GameDisplaySpec("nes-4-3", 4, 3)


class Adapter:
    name = "Dragon Warrior IV"

    def __init__(
        self,
        context: GameContext,
        assets: DragonWarrior4RomAssets | None = None,
        map_document: MapDocument | None = None,
        asset_error: str = "",
    ) -> None:
        self.context = context
        self.assets = assets
        self.map_document = map_document
        self.asset_error = asset_error
        self.submap_names = load_submap_names(context.repository_root)
        self.treasure_records = load_treasure_records(context.repository_root)
        self.progress = self._progress(context)
        self.sources = reference_sources(context.repository_root)
        self.playthrough_id = ""
        self.dialogue_journal = DialogueJournal(None)
        self.encounter_log = EncounterLog(None)
        self.combat_analytics = CombatAnalytics(None)
        self.map_intelligence = MapIntelligence(None)
        self._monster_names: dict[int, str] = {}
        self._last_ram: bytes | None = None
        self._dashboard_model = DashboardModel(
            assets,
            self.sources,
            self.progress,
            asset_error,
        )
        dashboard_enabled = context.settings.get("dashboard", True) is not False
        dashboard_launch = context.settings.get("dashboard_launch", True) is not False
        self._dashboard = DashboardBridge(
            context.state_directory,
            context.repository_root,
            self._dashboard_model.static_document(),
            enabled=dashboard_enabled,
            launch=dashboard_launch,
        )

    def activate(self, _content_key: tuple[str, str, str]) -> None:
        self._reset_session()
        self._dashboard.activate()

    def deactivate(self) -> None:
        self._dashboard.close()
        self._reset_session()

    def _reset_session(self) -> None:
        self.playthrough_id = ""
        self.dialogue_journal = DialogueJournal(None)
        self.encounter_log = EncounterLog(None)
        self.combat_analytics = CombatAnalytics(None)
        self.map_intelligence = MapIntelligence(None)
        self._monster_names.clear()
        self._last_ram = None

    def supports(self, status: RetroArchStatus, content_hash: str | None = None) -> bool:
        core = status.core.casefold().replace(" ", "_")
        if not any(
            name in core
            for name in ("mesen", "nestopia", "fceumm", "quicknes", "nes")
        ):
            return False
        content = status.content.casefold().replace(" ", "")
        return not content or "dragonwarrior4" in content or "dragonquestiv" in content

    def snapshot(self, memory: MemoryReader) -> OverlaySnapshot:
        try:
            ram = memory.read_memory(0, RAM_SIZE)
            wram = memory.read_memory(WRAM_ADDRESS, WRAM_SIZE)
            state = read_state(ram, wram, self.assets, self.submap_names)
        except (RetroArchError, RuntimeError, OSError, ValueError) as error:
            return self._memory_unavailable(str(error))
        world_map_key = self._selected_world_map()
        state = self._select_world_location(state, world_map_key)
        self._last_ram = bytes(ram)
        self._select_playthrough(state)
        self._monster_names.update(observed_monster_names(ram))

        try:
            battle_memory = memory.read_memory(
                BATTLE_MEMORY_ADDRESS,
                BATTLE_MEMORY_SIZE,
            )
            battle = read_battle_state(ram, battle_memory, self._monster_names.get)
        except (RetroArchError, RuntimeError, OSError, ValueError) as error:
            battle = BattleState.unavailable(str(error))

        map_key = (
            world_map_key
            if state.location.is_world
            else f"area-{state.location.map_id:02x}-{state.location.submap:02x}"
        )
        feature_overlay = None
        if self.assets is not None and not state.location.is_world:
            try:
                feature_overlay = self.assets.feature_overlay(
                    state.location.map_id,
                    state.location.submap,
                    self.treasure_records,
                    state.treasure_flags,
                )
            except ValueError:
                feature_overlay = None
        journal_entries = self.dialogue_journal.observe(
            state.dialogue,
            state.location.title,
            state.location.map_id,
            state.location.submap,
            x=state.location.x,
            y=state.location.y,
        )
        self.map_intelligence.observe(state.location, map_key)
        learned_overlay = self.map_intelligence.overlay(
            state.location,
            map_key,
            journal_entries,
        )
        overlays = tuple(
            value
            for value in (feature_overlay, learned_overlay)
            if value is not None
        )
        dashboard_overlay = (
            MapOverlay(
                map_key,
                tuple(
                    waypoint
                    for value in overlays
                    for waypoint in value.waypoints
                ),
            )
            if overlays
            else None
        )
        encounter_entries = self.encounter_log.observe(battle, state)
        self.combat_analytics.observe(encounter_entries)
        self.map_intelligence.observe_encounter(
            self.encounter_log.active_summary,
            map_key,
            state.location.x,
            state.location.y,
        )
        self._dashboard.publish(
            self._dashboard_model.dynamic_document(
                state,
                dashboard_overlay,
                journal_entries,
                battle,
                self.encounter_log.active_summary,
                encounter_entries,
                self.encounter_log.root,
                self.playthrough_id,
                self.combat_analytics.document,
                world_map_key,
            )
        )
        return OverlaySnapshot(
            self.name,
            f"{state.location.title} · ({state.location.x},{state.location.y})",
            self._sections(state, battle),
            MapPosition(
                state.location.area,
                state.location.layer_id,
                state.location.x,
                state.location.y,
                state.location.is_world,
            ),
            map_document=self.map_document,
            map_overlays=overlays,
            display_spec=DISPLAY_SPEC,
        )

    def capture(self, memory: MemoryReader) -> None:
        if self._last_ram is None:
            return
        try:
            battle_memory = memory.read_memory(
                BATTLE_MEMORY_ADDRESS,
                BATTLE_MEMORY_SIZE,
            )
            wram = memory.read_memory(WRAM_ADDRESS, WRAM_SIZE)
            monster_ids = memory.read_memory(0x0440, 2)
            battle_text = memory.read_memory(BATTLE_TEXT_ADDRESS, BATTLE_TEXT_SIZE)
            ram = bytearray(self._last_ram)
            ram[0x440:0x442] = monster_ids
            ram[BATTLE_TEXT_ADDRESS:BATTLE_TEXT_ADDRESS + BATTLE_TEXT_SIZE] = battle_text
            self._monster_names.update(observed_monster_names(ram))
            state = read_state(bytes(ram), wram, self.assets, self.submap_names)
            world_map_key = self._selected_world_map()
            state = self._select_world_location(state, world_map_key)
            battle = read_battle_state(
                bytes(ram),
                battle_memory,
                self._monster_names.get,
            )
        except (RetroArchError, RuntimeError, OSError, ValueError):
            return
        encounter_entries = self.encounter_log.observe(battle, state)
        self.combat_analytics.observe(encounter_entries)
        map_key = (
            world_map_key
            if state.location.is_world
            else f"area-{state.location.map_id:02x}-{state.location.submap:02x}"
        )
        self.map_intelligence.observe_encounter(
            self.encounter_log.active_summary,
            map_key,
            state.location.x,
            state.location.y,
        )

    def _sections(
        self,
        state: DragonWarrior4State,
        battle: BattleState | None = None,
    ) -> tuple[PanelSection, ...]:
        active = tuple(character for character in state.characters if character.active)
        party_rows = []
        for character in active:
            conditions = []
            if not character.alive:
                conditions.append("down")
            if character.poisoned:
                conditions.append("poisoned")
            if character.paralyzed:
                conditions.append("paralyzed")
            suffix = f" · {', '.join(conditions)}" if conditions else ""
            party_rows.append(
                PanelRow(
                    f"{character.name} · Lv {character.level} · "
                    f"HP {character.hp}/{character.max_hp} · "
                    f"MP {character.mp}/{character.max_mp}{suffix}",
                    not conditions,
                )
            )
        if not party_rows:
            party_rows.append(PanelRow("No active party slots detected"))

        if state.has_boat or state.has_balloon:
            travel = " · ".join(
                value
                for value, available in (
                    ("Boat", state.has_boat),
                    ("Balloon", state.has_balloon),
                )
                if available
            )
        else:
            travel = "On foot"
        journey_rows = (
            PanelRow(state.chapter_name),
            PanelRow(f"{state.time_name} · Tactics: {state.tactics_name}"),
            PanelRow(f"Travel: {travel}"),
        )
        resource_rows = (
            PanelRow(f"Gold {state.gold:,} · Casino coins {state.casino_coins:,}"),
            PanelRow(f"Small Medals turned in: {state.small_medals}"),
            PanelRow(
                f"Treasure flags: {state.treasure_opened}/{state.treasure_total} opened"
            ),
        )
        resource_actions = [
            PanelAction(
                "OPEN RETURN LIST",
                "Return Destinations",
                tuple(PanelRow(location, True) for location in state.return_locations)
                or (PanelRow("No Return destinations recorded"),),
                key="return-list",
            ),
        ]
        if state.chapter == 2 or any(count for _, count in state.taloon_shop_stock):
            resource_actions.append(
                PanelAction(
                    "OPEN TALOON STOCK",
                    "Lakanaba Shop Stock",
                    tuple(
                        PanelRow(f"{name}: {count}")
                        for name, count in state.taloon_shop_stock
                    ),
                    key="taloon-stock",
                )
            )
        atlas_status = (
            f"ROM atlas: {self.assets.region} · {len(self.assets.area_maps)} floors"
            if self.assets is not None
            else f"ROM atlas unavailable: {self.asset_error or 'configure a ROM path'}"
        )
        reference_rows = (
            PanelRow(atlas_status, self.assets is not None),
            PanelRow(f"Live layout: {state.location.memory_region}"),
            PanelRow(state.location.evidence),
            PanelRow(
                f"Saved references available: "
                f"{sum(source.available for source in self.sources)}/{len(self.sources)}"
            ),
        )
        sections = [
            PanelSection(
                "Journey",
                journey_rows,
                priority=5,
                role="goals",
                key="journey",
            ),
            PanelSection(
                "Party",
                tuple(party_rows),
                actions=(
                    PanelAction(
                        "OPEN PARTY DETAILS",
                        "Party Equipment, Stats, and Spells",
                        self._party_detail_rows(state),
                        key="party-details",
                    ),
                ),
                priority=10,
                role="party",
                key="party",
            ),
            PanelSection(
                "Resources",
                resource_rows,
                actions=tuple(resource_actions),
                priority=20,
                role="party",
                key="resources",
            ),
            self._achievement_section(),
            PanelSection(
                "Atlas confidence",
                reference_rows,
                alert=self.assets is None or state.location.memory_region == "Unknown",
                priority=30,
                role="area",
                key="atlas-confidence",
            ),
        ]
        battle_section = self._battle_section(battle)
        if battle_section is not None:
            sections.insert(0, battle_section)
        return tuple(sections)

    def _achievement_section(self) -> PanelSection:
        unlocked_ids = self.progress.unlocked_ids if self.progress else frozenset()
        unlocked = tuple(
            achievement
            for achievement in ACHIEVEMENTS
            if achievement.achievement_id in unlocked_ids
        )
        unlocked_points = sum(achievement.points for achievement in unlocked)
        rows = (
            PanelRow(
                f"{len(unlocked)}/{len(ACHIEVEMENTS)} unlocked · "
                f"{unlocked_points}/{TOTAL_POINTS} points",
                len(unlocked) == len(ACHIEVEMENTS),
            ),
            PanelRow(
                f"Account: {self.progress.username}"
                if self.progress and self.progress.username
                else "RetroAchievements account unavailable"
            ),
        )
        details = tuple(
            PanelRow(
                f"{achievement.title} · {achievement.points} points",
                achievement.achievement_id in unlocked_ids,
                achievement.description,
            )
            for achievement in ACHIEVEMENTS
        )
        return PanelSection(
            "RetroAchievements",
            rows,
            actions=(
                PanelAction(
                    "OPEN ACHIEVEMENTS",
                    "Dragon Quest IV Achievements",
                    details,
                    key="achievements",
                ),
            ),
            priority=25,
            role="goals",
            key="retroachievements",
        )

    @staticmethod
    def _battle_section(battle: BattleState | None) -> PanelSection | None:
        if battle is None or not battle.available or not battle.active:
            return None
        enemies = tuple(enemy for enemy in battle.enemies if enemy.coherent)
        if not enemies:
            return None
        rows = tuple(
            PanelRow(
                f"{enemy.label} · HP {enemy.hp} · MP {enemy.mp} · "
                f"ATK {enemy.attack} · DEF {enemy.defense} · AGI {enemy.agility} · "
                f"status ${enemy.status:02X}",
                tooltip=(
                    f"Observed enemy slot {enemy.slot + 1}; group code "
                    f"${enemy.group_code:02X}. Status bits are not yet documented."
                ),
            )
            for enemy in enemies
        )
        highest_attack = max(enemies, key=lambda enemy: enemy.attack)
        fastest = max(enemies, key=lambda enemy: enemy.agility)
        observations = (
            PanelRow(
                f"Highest observed ATK: {highest_attack.label} "
                f"({highest_attack.attack})"
            ),
            PanelRow(f"Fastest observed group: {fastest.label} ({fastest.agility} AGI)"),
            PanelRow(
                f"Current reward counters: {battle.reward_experience:,} XP · "
                f"{battle.reward_gold:,} gold"
            ),
        )
        return PanelSection(
            "Battle",
            rows,
            alert=True,
            actions=(
                PanelAction(
                    "OPEN BATTLE OBSERVATIONS",
                    "Battle Observations",
                    observations,
                    key="battle-observations",
                ),
            ),
            priority=1,
            role="urgent",
            key="battle",
        )

    @staticmethod
    def _party_detail_rows(state: DragonWarrior4State) -> tuple[PanelRow, ...]:
        rows = []
        for character in state.characters:
            if not character.active and character.level == 0:
                continue
            equipped = ", ".join(
                f"{item.category.title()}: {item.name}"
                for item in character.items
                if item.equipped
            ) or "none"
            carried = ", ".join(
                item.name for item in character.items if not item.equipped
            ) or "none"
            battle_spells = ", ".join(
                spell.name for spell in character.spells if spell.usage == "battle"
            ) or "none"
            field_spells = ", ".join(
                spell.name for spell in character.spells if spell.usage == "field"
            ) or "none"
            rows.extend(
                (
                    PanelRow(
                        f"{character.name} · Lv {character.level} · "
                        f"STR {character.strength} · AGI {character.agility} · "
                        f"VIT {character.vitality} · INT {character.intelligence} · "
                        f"LUCK {character.luck}",
                        emphasis="heading",
                    ),
                    PanelRow(f"Equipped: {equipped}"),
                    PanelRow(f"Carried: {carried}"),
                    PanelRow(f"Battle spells: {battle_spells}"),
                    PanelRow(f"Field spells: {field_spells}"),
                )
            )
        return tuple(rows) or (PanelRow("No recruited party members detected"),)

    def _memory_unavailable(self, detail: str) -> OverlaySnapshot:
        self._dashboard.publish(self._dashboard_model.waiting_document(detail))
        return OverlaySnapshot(
            self.name,
            "Memory unavailable",
            (
                PanelSection(
                    "NES memory access",
                    (
                        PanelRow(detail or "The active core did not return DW4 memory"),
                        PanelRow(
                            "Use Mesen or FCEUmm with a loaded Dragon Warrior IV save"
                        ),
                    ),
                    alert=True,
                    priority=1,
                    role="urgent",
                    key="memory-access",
                ),
            ),
            map_document=self.map_document,
            display_spec=DISPLAY_SPEC,
        )

    def _select_playthrough(self, state: DragonWarrior4State) -> None:
        identity = self._playthrough_identity(state)
        if identity == self.playthrough_id:
            return
        self.playthrough_id = identity
        if self.context.state_directory is None:
            self.dialogue_journal = DialogueJournal(None)
            self.encounter_log = EncounterLog(None)
            self.combat_analytics = CombatAnalytics(None)
            self.map_intelligence = MapIntelligence(None)
            return
        root = self.context.state_directory / "playthroughs" / identity
        self.dialogue_journal = DialogueJournal(root / "dialogue-journal.json")
        self.encounter_log = EncounterLog(root / "encounters")
        self.combat_analytics = CombatAnalytics(
            root / "combat-analytics.json",
            self.encounter_log.recent,
        )
        self.map_intelligence = MapIntelligence(root / "map-intelligence.json")

    def _playthrough_identity(self, state: DragonWarrior4State) -> str:
        rom_identity = (
            self.assets.content_hash
            if self.assets is not None
            else "unverified-rom"
        )
        configured_save = self.context.settings.get("save_path")
        if isinstance(configured_save, str) and configured_save.strip():
            configured_save = Path(configured_save)
        if isinstance(configured_save, Path):
            source = str(configured_save.expanduser().resolve()).casefold()
            label = configured_save.stem
        else:
            hero = state.characters[0].name.strip() or "unnamed-hero"
            source = hero.casefold()
            label = hero
        safe_label = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")
        digest = hashlib.sha256(f"{rom_identity}|{source}".encode("utf-8")).hexdigest()
        return f"{safe_label or 'playthrough'}-{digest[:10]}"

    def _selected_world_map(self) -> str:
        value = str(self._dashboard.controls().get("world_map", "world"))
        return value if value in WORLD_MAP_SPECS else "world"

    @staticmethod
    def _select_world_location(
        state: DragonWarrior4State,
        world_map_key: str,
    ) -> DragonWarrior4State:
        if not state.location.is_world:
            return state
        title, area = WORLD_MAP_SPECS[world_map_key][:2]
        return replace(
            state,
            location=replace(
                state.location,
                title=title,
                area=area,
                evidence=(
                    f"{state.location.evidence}; outdoor layer selected in companion"
                ),
            ),
        )

    @staticmethod
    def _progress(context: GameContext) -> RAProgress | None:
        if context.ra_progress_provider is None:
            return None
        return context.ra_progress_provider(RA_GAME_ID)
