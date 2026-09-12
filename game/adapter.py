from __future__ import annotations

from retroarch_overlay.core.contracts import GameContext, MemoryReader
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import (
    GameDisplaySpec,
    MapDocument,
    MapPosition,
    OverlaySnapshot,
    PanelAction,
    PanelRow,
    PanelSection,
    RetroArchStatus,
)
from retroarch_overlay.retroarch import RetroArchError

from .battle import (
    BATTLE_MEMORY_ADDRESS,
    BATTLE_MEMORY_SIZE,
    BattleState,
    read_battle_state,
)
from .dashboard_bridge import DashboardBridge
from .dashboard_model import DashboardModel
from .dialogue_journal import DialogueJournal
from .encounter_log import EncounterLog
from .reference_data import load_submap_names, load_treasure_records, reference_sources
from .rom_assets import DragonWarrior4RomAssets
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
        journal_path = (
            context.state_directory / "dashboard" / "dialogue-journal.json"
            if context.state_directory is not None
            else None
        )
        self.dialogue_journal = DialogueJournal(journal_path)
        encounter_root = (
            context.state_directory / "encounters"
            if context.state_directory is not None
            else None
        )
        self.encounter_log = EncounterLog(encounter_root)
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

        try:
            battle_memory = memory.read_memory(
                BATTLE_MEMORY_ADDRESS,
                BATTLE_MEMORY_SIZE,
            )
            battle = read_battle_state(ram, battle_memory)
        except (RetroArchError, RuntimeError, OSError, ValueError) as error:
            battle = BattleState.unavailable(str(error))

        overlay = None
        if self.assets is not None and not state.location.is_world:
            try:
                overlay = self.assets.feature_overlay(
                    state.location.map_id,
                    state.location.submap,
                    self.treasure_records,
                    state.treasure_flags,
                )
            except ValueError:
                overlay = None
        journal_entries = self.dialogue_journal.observe(
            state.dialogue,
            state.location.title,
            state.location.map_id,
            state.location.submap,
        )
        encounter_entries = self.encounter_log.observe(battle, state)
        self._dashboard.publish(
            self._dashboard_model.dynamic_document(
                state,
                overlay,
                journal_entries,
                battle,
                self.encounter_log.active_summary,
                encounter_entries,
            )
        )
        return OverlaySnapshot(
            self.name,
            f"{state.location.title} · ({state.location.x},{state.location.y})",
            self._sections(state),
            MapPosition(
                state.location.area,
                state.location.layer_id,
                state.location.x,
                state.location.y,
                state.location.is_world,
            ),
            map_document=self.map_document,
            map_overlays=(overlay,) if overlay is not None else (),
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
            ram = bytearray(self._last_ram)
            ram[0x440:0x442] = monster_ids
            state = read_state(bytes(ram), wram, self.assets, self.submap_names)
            battle = read_battle_state(bytes(ram), battle_memory)
        except (RetroArchError, RuntimeError, OSError, ValueError):
            return
        self.encounter_log.observe(battle, state)

    def _sections(self, state: DragonWarrior4State) -> tuple[PanelSection, ...]:
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
        return_actions = (
            PanelAction(
                "OPEN RETURN LIST",
                "Return Destinations",
                tuple(PanelRow(location, True) for location in state.return_locations)
                or (PanelRow("No Return destinations recorded"),),
            ),
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
        return (
            PanelSection("Journey", journey_rows, priority=5, role="objective"),
            PanelSection("Party", tuple(party_rows), priority=10, role="party"),
            PanelSection(
                "Resources",
                resource_rows,
                actions=return_actions,
                priority=20,
                role="progress",
            ),
            PanelSection(
                "Atlas confidence",
                reference_rows,
                alert=self.assets is None or state.location.memory_region == "Unknown",
                priority=30,
                role="context",
            ),
        )

    def _memory_unavailable(self, detail: str) -> OverlaySnapshot:
        self._dashboard.publish(
            {
                "mode": "waiting",
                "location": {"title": "Waiting for readable NES memory"},
                "detail": detail,
            }
        )
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
                ),
            ),
            map_document=self.map_document,
            display_spec=DISPLAY_SPEC,
        )

    @staticmethod
    def _progress(context: GameContext) -> RAProgress | None:
        if context.ra_progress_provider is None:
            return None
        return context.ra_progress_provider(RA_GAME_ID)
