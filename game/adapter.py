from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import re

from retroarch_overlay.core.contracts import GameContext, MemoryReader
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import (
    GameDisplaySpec,
    MapDocument,
    MapOverlay,
    MapPosition,
    MapWaypoint,
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
from .encounter_log import EncounterLog
from .map_entities import (
    ENTITY_MEMORY_ADDRESS,
    ENTITY_MEMORY_SIZE,
    MapEntityState,
    read_map_entities,
)
from .reference_data import (
    load_submap_names,
)
from .rom_assets import DragonWarrior4RomAssets
from .state import (
    RAM_SIZE,
    WRAM_ADDRESS,
    WRAM_SIZE,
    CharacterState,
    DragonWarrior4State,
    read_state,
)


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
        self.progress = self._progress(context)
        self.playthrough_id = ""
        self.encounter_log = EncounterLog(None)
        self.combat_analytics = CombatAnalytics(None)
        self._monster_names: dict[int, str] = {}
        self._last_ram: bytes | None = None

    def activate(self, _content_key: tuple[str, str, str]) -> None:
        self._reset_session()

    def deactivate(self) -> None:
        self._reset_session()

    def _reset_session(self) -> None:
        self.playthrough_id = ""
        self.encounter_log = EncounterLog(None)
        self.combat_analytics = CombatAnalytics(None)
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

        feature_overlay = None
        if self.assets is not None and not state.location.is_world:
            try:
                feature_overlay = self.assets.feature_overlay(
                    state.location.map_id,
                    state.location.submap,
                    state.treasure_flags,
                )
            except ValueError:
                feature_overlay = None
        overlays = tuple(
            value
            for value in (feature_overlay, self._entity_overlay(memory, state))
            if value is not None
        )
        encounter_entries = self.encounter_log.observe(battle, state)
        self.combat_analytics.observe(encounter_entries)
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
            battle = read_battle_state(
                bytes(ram),
                battle_memory,
                self._monster_names.get,
            )
        except (RetroArchError, RuntimeError, OSError, ValueError):
            return
        encounter_entries = self.encounter_log.observe(battle, state)
        self.combat_analytics.observe(encounter_entries)

    def _sections(
        self,
        state: DragonWarrior4State,
        battle: BattleState | None = None,
    ) -> tuple[PanelSection, ...]:
        sections = [
            self._journey_section(state),
            self._party_section(state),
            self._combat_section(),
            self._achievement_section(),
        ]
        battle_section = self._battle_section(battle)
        if battle_section is not None:
            sections.insert(0, battle_section)
        return tuple(sections)

    @staticmethod
    def _entity_overlay(
        memory: MemoryReader,
        state: DragonWarrior4State,
    ) -> MapOverlay | None:
        try:
            entity_memory = memory.read_memory(
                ENTITY_MEMORY_ADDRESS,
                ENTITY_MEMORY_SIZE,
            )
            entities = read_map_entities(entity_memory)
        except (RetroArchError, RuntimeError, OSError, ValueError):
            return None
        points = tuple(Adapter._entity_point(entity) for entity in entities)
        if not points:
            return None
        return MapOverlay(_layer_key(state), points)

    @staticmethod
    def _entity_point(entity: MapEntityState) -> MapWaypoint:
        return MapWaypoint(
            entity.x,
            entity.y,
            f"Map entity {entity.slot - 5}",
            (
                f"Live slot ${entity.slot:02X} · facing ${entity.facing:02X} · "
                f"descriptor ${entity.descriptor:02X} · "
                f"behavior ${entity.behavior_state:02X} · "
                f"runtime flags ${entity.runtime_flags:02X}"
            ),
            "entities",
            marker=f"map-entity:{entity.slot - 5}",
        )

    @staticmethod
    def _journey_section(state: DragonWarrior4State) -> PanelSection:
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
        rows = (
            PanelRow(state.chapter_name),
            PanelRow(f"{state.time_name} · Tactics: {state.tactics_name}"),
            PanelRow(f"Travel: {travel}"),
            PanelRow(
                f"Gold {state.gold:,} · Casino coins {state.casino_coins:,} · "
                f"Small Medals {state.small_medals}"
            ),
            PanelRow(
                f"Treasure flags: {state.treasure_opened}/{state.treasure_total} opened"
            ),
        )
        return PanelSection(
            "Journey",
            rows,
            priority=5,
            role="goals",
            compact_rows=(PanelRow(f"{state.chapter_name} · Gold {state.gold:,}"),),
            key="journey",
        )

    def _party_section(self, state: DragonWarrior4State) -> PanelSection:
        active = tuple(character for character in state.characters if character.active)
        rows = []
        for character in active:
            conditions = _conditions(character)
            suffix = f" · {', '.join(conditions)}" if conditions else ""
            rows.append(
                PanelRow(
                    f"{character.name} · Lv {character.level} · "
                    f"HP {character.hp}/{character.max_hp} · "
                    f"MP {character.mp}/{character.max_mp}{suffix}",
                    not conditions,
                    progress=(
                        character.hp / character.max_hp if character.max_hp else None
                    ),
                )
            )
        if not rows:
            rows.append(PanelRow("No active party slots detected"))
        summary = (
            " · ".join(
                f"{character.name} {character.hp}/{character.max_hp}"
                for character in active
            )
            or rows[0].text
        )
        return PanelSection(
            "Party",
            tuple(rows),
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
            compact_rows=(PanelRow(summary),),
            key="party",
        )

    def _combat_section(self) -> PanelSection:
        analytics = self.combat_analytics.document
        total = int(analytics.get("total_encounters", 0))
        win_rate = float(analytics.get("win_rate", 0.0))
        rows = (
            PanelRow(
                f"{total} lifetime · {int(analytics.get('session_encounters', 0))} "
                f"this session · {win_rate:.0%} victories"
            ),
            PanelRow(
                f"Rewards: {int(analytics.get('reward_experience', 0)):,} XP · "
                f"{int(analytics.get('reward_gold', 0)):,} gold"
            ),
            PanelRow(
                "Locations: "
                + (
                    " · ".join(
                        f"{value.get('name', 'Unknown')} ({int(value.get('encounters', 0))})"
                        for value in analytics.get("locations", [])[:4]
                    )
                    or "none recorded"
                )
            ),
            PanelRow(
                "Monsters: "
                + (
                    " · ".join(
                        f"{value.get('label', 'Unknown')} ({int(value.get('encounters', 0))})"
                        for value in analytics.get("enemies", [])[:6]
                    )
                    or "none recorded"
                )
            ),
        )
        records = tuple(
            PanelRow(
                f"{record.outcome.replace('_', ' ').upper()} · {record.end_location} · "
                f"{', '.join(enemy.label for enemy in record.enemies) or 'Unknown enemies'} · "
                f"{record.reward_experience:,} XP / {record.reward_gold:,} gold",
                tooltip=(
                    f"{_local_time(record.ended_at)} · "
                    f"{record.duration_seconds:.2f}s · "
                    f"{record.sample_count} distinct frames"
                ),
            )
            for record in self.encounter_log.recent
        ) or (PanelRow("Completed combat records will appear here"),)
        return PanelSection(
            "Combat log",
            rows,
            actions=(
                PanelAction(
                    "OPEN RECENT COMBATS",
                    "Recent Combats",
                    records,
                    key="recent-combats",
                ),
            ),
            priority=30,
            role="goals",
            compact_rows=(
                PanelRow(f"{total} battles · {win_rate:.0%} victories"),
            ),
            key="combat-log",
        )

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
                        f"LUCK {character.luck}"
                        f"{'' if character.active else ' · reserve'}",
                        emphasis="heading",
                    ),
                    PanelRow(f"Equipped: {equipped}"),
                    PanelRow(f"Carried: {carried}"),
                    PanelRow(f"Battle spells: {battle_spells}"),
                    PanelRow(f"Field spells: {field_spells}"),
                    PanelRow(f"Experience: {character.experience:,}"),
                )
            )
        return tuple(rows) or (PanelRow("No recruited party members detected"),)

    def _memory_unavailable(self, detail: str) -> OverlaySnapshot:
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
            self.encounter_log = EncounterLog(None)
            self.combat_analytics = CombatAnalytics(None)
            return
        root = self.context.state_directory / "playthroughs" / identity
        self.encounter_log = EncounterLog(root / "encounters")
        self.combat_analytics = CombatAnalytics(
            root / "combat-analytics.json",
            self.encounter_log.recent,
        )

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

    @staticmethod
    def _progress(context: GameContext) -> RAProgress | None:
        if context.ra_progress_provider is None:
            return None
        return context.ra_progress_provider(RA_GAME_ID)


def _conditions(character: CharacterState) -> list[str]:
    conditions = []
    if not character.alive:
        conditions.append("down")
    if character.poisoned:
        conditions.append("poisoned")
    if character.paralyzed:
        conditions.append("paralyzed")
    return conditions


def _layer_key(state: DragonWarrior4State) -> str:
    if state.location.is_world:
        return {
            "World": "world",
            "Gottside": "gottside",
            "Underworld": "underworld",
        }.get(state.location.area, "world")
    return f"area-{state.location.map_id:02x}-{state.location.submap:02x}"


def _local_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value or "unknown"
