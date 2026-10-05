from __future__ import annotations

from dataclasses import replace
import logging
from pathlib import Path
import re
import tomllib

from retroarch_overlay.core.contracts import GameContext, MemoryReader
from retroarch_overlay.adapters.base import ContentHashResolver
from retroarch_overlay.models import (
    GameDisplaySpec, MapDocument, MapOverlay, MapPosition, MapRegion,
    OverlaySnapshot, PanelRow, PanelSection, RetroArchStatus,
)

from .battle import BATTLE_CONTEXT_ADDRESS, BATTLE_MEMORY_ADDRESS, BATTLE_MEMORY_SIZE, BattleState, read_battle_state
from .arena import ArenaPredictor, SIMULATION_COUNT, arena_betting_open, arena_key, validate_simulations
from .map_snapshot import MEMORY_ERRORS, MapSnapshot, _layer_key
from .poker import PokerTable, read_poker_table
from .rom_assets import DragonWarrior4RomAssets
from .presentation import (
    BAD_COLOR, CAUTION_COLOR, CURRENCY_UNITS, GOOD_COLOR, HP_COLOR, MP_COLOR,
    POISON_COLOR, RA_GAME_ID, UPGRADE_VERDICTS, XP_COLOR, PanelPresentation,
    _character_row, _other_verdicts, _upgrade_row,
)
from .state import RAM_SIZE, WRAM_ADDRESS, WRAM_SIZE, DragonWarrior4State, read_state


DISPLAY_SPEC = GameDisplaySpec("nes-4-3", 4, 3)
LOGGER = logging.getLogger(__name__)
STALE_SNAPSHOT_LIMIT = 8


class Adapter(PanelPresentation):
    name = "Dragon Warrior IV"

    def __init__(
        self,
        context: GameContext,
        assets: DragonWarrior4RomAssets | None = None,
        map_document: MapDocument | None = None,
        asset_error: str = "",
    ) -> None:
        super().__init__(context, assets, map_document, asset_error, log=self._log)
        self._content_key: tuple[str, str, str] | None = None
        self._match = self._load_match(context.repository_root)
        rom_path = context.settings.get("rom_path")
        if isinstance(rom_path, str) and rom_path.strip():
            rom_path = Path(rom_path)
        self._content_resolver = ContentHashResolver(files=(rom_path.expanduser(),)) if isinstance(rom_path, Path) else None
        self._identity_error = ""
        self._map_snapshot = MapSnapshot(map_document)
        self._experience_curve: dict[tuple[int, int], int | None] = {}
        self._last_snapshot: OverlaySnapshot | None = None
        self._stale_polls = 0
        self._logged: set[str] = set()
        self._arena_predictor = ArenaPredictor()
        self._arena_key: bytes | None = None
        self._arena_memory: MemoryReader | None = None
        self._arena_lineup: tuple[int, ...] = ()
        self._arena_requested: bytes | None = None
        self._arena_simulations = SIMULATION_COUNT

    @property
    def _display_context(self) -> tuple | None:
        return self._map_snapshot._display_context

    @_display_context.setter
    def _display_context(self, value: tuple | None) -> None:
        self._map_snapshot._display_context = value

    @property
    def _display_document(self) -> MapDocument | None:
        return self._map_snapshot._display_document

    @_display_document.setter
    def _display_document(self, value: MapDocument | None) -> None:
        self._map_snapshot._display_document = value

    def activate(self, content_key: tuple[str, str, str]) -> None:
        self._clear_arena()
        if self._content_key != content_key:
            self._economy_target = None
        self._content_key = content_key
        self.progress = self._progress(self.context)
        self._identity_error = ""
        self._last_snapshot = None
        self._stale_polls = 0
        if content_key[2] and self.assets is not None and self._content_resolver is not None:
            try:
                identity = self._content_resolver.resolve(RetroArchStatus("PLAYING", *content_key))
                if identity != self.assets.content_hash:
                    self._identity_error = "The running game does not match the configured Dragon Warrior IV ROM"
            except (OSError, ValueError) as error:
                self._identity_error = f"The running game could not be checked against the configured ROM: {error}"

    def deactivate(self) -> None:
        self._clear_arena()
        self._content_key = None
        self._identity_error = ""
        self._last_snapshot = None
        self._stale_polls = 0

    def supports(self, status: RetroArchStatus, content_hash: str | None = None) -> bool:
        core = _identifier(status.core)
        if core not in {_identifier(value) for value in self._match.get("cores", ())}:
            return False
        if content_hash:
            return content_hash.casefold() in self._match.get("hashes", ())
        content = _identifier(status.content)
        return bool(content) and any(
            _identifier(hint) in content for hint in self._match.get("content_hints", ())
        )

    def snapshot(self, memory: MemoryReader) -> OverlaySnapshot:
        if self._identity_error:
            return self._memory_unavailable(self._identity_error)
        try:
            ram = memory.read_memory(0, RAM_SIZE)
            wram = memory.read_memory(WRAM_ADDRESS, WRAM_SIZE)
            state = read_state(ram, wram, self.assets, self.submap_names,
                               self.assets.guest_profile if self.assets is not None else None)
        except MEMORY_ERRORS as error:
            return self._interrupted(str(error))
        if not state.party_ids:
            return self._interrupted("Waiting for a saved game to load")
        if state.location.memory_region != "US":
            return self._memory_unavailable("Only the US version of Dragon Warrior IV is supported")
        state = self._with_experience(memory, state)
        state = self._with_spell_milestones(state)
        battle = self._battle(memory, ram)
        battle = self._with_arena(memory, ram, battle)
        map_capture = self._map_snapshot.capture(
            memory, state, ram, wram, battle, assets=self.assets, submap_names=self.submap_names, log=self._log,
        )
        if self.assets is not None:
            for detail in self.assets.diagnostics:
                self._log(detail)
        if not battle.available:
            self._log(f"Enemy memory unavailable: {battle.detector_evidence}")

        sections, current_zone = self._sections(
            state, battle, wram[0x2E7:0x2EA],
            encounters=lambda: self._encounter_section(memory, state, ram, wram),
            arena_section=lambda: self._arena_section(state, battle),
        )
        try:
            poker = read_poker_table(memory, ram)
        except MEMORY_ERRORS as error:
            poker = PokerTable("waiting", wager=None, detail="Waiting for current poker cards")
            self._log(f"Poker table read interrupted: {error}")
        if poker is not None:
            sections = (*sections, self._poker_section(poker, state.casino_coins))
        display_document = self._map_snapshot.display(
            memory, state, ram, wram, battle, map_capture, current_zone,
            assets=self.assets, map_document=self.map_document,
        )
        try:
            if (
                memory.read_memory(0x63, 3) != ram[0x63:0x66]
                or memory.read_memory(0x615A, 1) != wram[0x15A:0x15B]
                or memory.read_memory(0x616A, 0x25) != wram[0x16A:0x18F]
            ):
                return self._interrupted("Waiting for the game to finish loading this area")
        except MEMORY_ERRORS:
            pass
        self._stale_polls = 0
        self._last_snapshot = OverlaySnapshot(
            self.name,
            state.location.title,
            tuple(sections),
            MapPosition(state.location.area, state.location.layer_id, state.location.x,
                        state.location.y, state.location.is_world) if state.location.area != "Unknown" else None,
            map_document=display_document,
            map_overlays=map_capture.overlays,
            display_spec=DISPLAY_SPEC,
        )
        return self._last_snapshot

    def _with_experience(self, memory: MemoryReader, state: DragonWarrior4State) -> DragonWarrior4State:
        try:
            thresholds = memory.read_memory(0x6E19, 27)
            if len(thresholds) != 27:
                raise ValueError("Incomplete level threshold table")
        except MEMORY_ERRORS:
            return state
        characters = []
        for character in state.characters:
            growth = character.character_id & 7
            threshold = int.from_bytes(thresholds[growth * 3:growth * 3 + 3], "little") if not character.guest else 0
            upcoming = threshold if threshold and character.level < 99 else None
            characters.append(replace(character, next_level_experience=upcoming,
                                      level_start_experience=self._level_start(growth, character.level, upcoming)))
        return replace(state, characters=tuple(characters))

    def _level_start(self, growth: int, level: int, upcoming: int | None) -> int | None:
        # The ROM level curve is trusted only while it reproduces the game's
        # own next-level value for this character.
        if self.assets is None or upcoming is None:
            return None
        if self._experience_threshold(growth, level + 1) != upcoming:
            return None
        return self._experience_threshold(growth, level)

    def _experience_threshold(self, growth: int, level: int) -> int | None:
        key = growth, level
        if key not in self._experience_curve:
            try:
                value = self.assets.experience_threshold(growth, level) if self.assets is not None else None
            except (*MEMORY_ERRORS, IndexError, ImportError):
                value = None
            self._experience_curve[key] = value if isinstance(value, int) else None
        return self._experience_curve[key]

    def _with_spell_milestones(self, state: DragonWarrior4State) -> DragonWarrior4State:
        if self.assets is None:
            return state
        try:
            characters = []
            for character in state.characters:
                known = {spell.name.casefold() for spell in character.spells}
                milestones = () if character.guest or character.level >= 99 else tuple(
                    f"{name} (Lv {level}{'+' if variable else ''})"
                    for name, level, variable in self.assets.spell_milestones(character.character_id)
                    if name.casefold() not in known
                )
                characters.append(replace(character, spell_milestones=milestones))
            return replace(state, characters=tuple(characters))
        except MEMORY_ERRORS:
            return state

    def _battle(self, memory: MemoryReader, ram: bytes) -> BattleState:
        try:
            flags = memory.read_memory(BATTLE_CONTEXT_ADDRESS, 1)
            if len(flags) != 1:
                raise ValueError("Battle context snapshot is incomplete")
            battle_memory = memory.read_memory(BATTLE_MEMORY_ADDRESS, BATTLE_MEMORY_SIZE)
            setup_monster_ids = b""
            if flags[0] & 0x80:
                try:
                    setup_monster_ids = memory.read_memory(0x6E45, 4)
                except MEMORY_ERRORS:
                    pass
            battle = read_battle_state(
                ram,
                battle_memory,
                self._monster_name,
                context_flags=flags[0],
                monster_vitals=self.assets.monster_vitals if self.assets is not None else None,
                setup_monster_ids=setup_monster_ids,
            )
        except MEMORY_ERRORS as error:
            return BattleState.unavailable(str(error))
        if battle.available and battle.active:
            try:
                arena_flags = memory.read_memory(0x72E9, 1)
                if len(arena_flags) == 1 and arena_flags[0] & 0x80:
                    wager = memory.read_memory(0x6E83, 3)
                    battle = replace(battle, arena=True,
                                     arena_wager=int.from_bytes(wager, "little") if len(wager) == 3 else None)
                    odds = memory.read_memory(0x6E39, 8)
                    selection = memory.read_memory(0x6E7F, 1)
                    if len(odds) == 8 and len(selection) == 1 and all(value < 10 for value in odds[4:]):
                        battle = replace(battle, arena_odds=tuple(zip(odds[:4], odds[4:], strict=True)),
                                         arena_selection=selection[0] & 3)
            except MEMORY_ERRORS:
                pass
        return battle

    def _clear_arena(self) -> None:
        self._arena_predictor.cancel()
        self._arena_requested = None
        self._arena_key = None
        self._arena_memory = None
        self._arena_lineup = ()

    def _with_arena(self, memory: MemoryReader, ram: bytes, battle: BattleState) -> BattleState:
        if ram[0x63:0x65] != bytes((4, 1)):
            self._clear_arena()
            return replace(battle, arena=False, arena_odds=(), arena_selection=None, arena_wager=None)
        if not battle.arena and not arena_betting_open(ram):
            self._clear_arena()
            return battle
        try:
            lineup = memory.read_memory(0x6E45, 4)
            marker = memory.read_memory(0x6E31, 16)
            if (len(lineup) != 4 or len(marker) != 16 or sum(value != 255 for value in lineup) < 2
                    or any(value >= 214 and value != 255 for value in lineup)):
                raise ValueError("The arena lineup is still loading")
            identity = marker + lineup
            if identity != self._arena_key:
                self._arena_predictor.cancel()
                self._arena_requested = None
            self._arena_key = identity
            self._arena_lineup = tuple(lineup)
            self._arena_memory = memory
            odds = marker[8:]
            selection = memory.read_memory(0x6E7F, 1)
            amount = memory.read_memory(0x6E83, 3)
            if self._arena_requested == identity:
                self._arena_requested = None
                self._capture_arena(memory, identity)
            return replace(
                battle, arena=True,
                arena_odds=tuple(zip(odds[:4], odds[4:], strict=True)) if all(value < 10 for value in odds[4:]) else (),
                arena_selection=selection[0] & 3 if len(selection) == 1 else None,
                arena_wager=int.from_bytes(amount, "little") if len(amount) == 3 else None,
            )
        except MEMORY_ERRORS as error:
            self._clear_arena()
            self._log(str(error))
            return battle

    def set_arena_simulations(self, value: int) -> None:
        validate_simulations(value)
        if not self._arena_predictor.status.running and self._arena_requested is None:
            self._arena_simulations = value

    def predict_arena(self) -> None:
        if self._arena_predictor.status.running or self._arena_requested is not None:
            return
        if self._arena_key is not None and self.assets is not None:
            self._arena_requested = self._arena_key

    def cancel_arena_prediction(self) -> None:
        self._arena_requested = None
        self._arena_predictor.cancel()

    def _capture_arena(self, memory: MemoryReader, identity: bytes) -> None:
        if self.assets is None:
            return
        try:
            ram = memory.read_memory(0, RAM_SIZE)
            lower = memory.read_memory(0x6000, 0x1000)
            upper = memory.read_memory(0x7000, 0x1000)
            if len(ram) != RAM_SIZE or len(lower) != 0x1000 or len(upper) != 0x1000:
                raise ValueError("The arena memory capture is incomplete")
            workspace = lower + upper
            active = (len(workspace) == 0x2000 and workspace[0x12E9] & 0x80
                      and workspace[0xBDE] & 0x80 and ram[0x63:0x65] == bytes((4, 1)))
            if not arena_betting_open(ram) and not active:
                self._clear_arena()
                return
            if (arena_key(workspace) != identity
                    or memory.read_memory(0x6E31, 16) + memory.read_memory(0x6E45, 4) != identity
                    or memory.read_memory(0x63, 2) != ram[0x63:0x65]):
                raise ValueError("The arena matchup changed; try again")
            self._arena_predictor.start(self.assets.arena_program(), ram, workspace, simulations=self._arena_simulations)
        except MEMORY_ERRORS as error:
            self._arena_predictor.fail(str(error))

    def _arena_section(self, state: DragonWarrior4State, battle: BattleState) -> PanelSection:
        return self._present_arena(
            state, battle, prediction=self._arena_predictor.status, lineup=self._arena_lineup,
            requested=self._arena_requested is not None, simulations=self._arena_simulations,
            ready=self._arena_key is not None, predict=self.predict_arena,
            cancel=self.cancel_arena_prediction, set_simulations=self.set_arena_simulations,
        )

    def _encounter_section(
        self, memory: MemoryReader, state: DragonWarrior4State, ram: bytes, wram: bytes,
    ) -> tuple[PanelSection | None, tuple[int, ...], tuple[str, MapRegion] | None]:
        return self._present_encounters(
            state, ram, wram, rate_row=lambda zone, night: self._encounter_rate_row(memory, state, wram, zone, night),
        )

    def _encounter_rate_row(self, memory: MemoryReader, state: DragonWarrior4State,
                            wram: bytes, zone: int, night: bool) -> PanelRow:
        threshold, detail = self._map_snapshot.encounter_rate(memory, state, wram, zone, assets=self.assets)
        return self._present_encounter_rate_row(threshold, detail, night)

    @staticmethod
    def _load_match(root: Path | None) -> dict[str, tuple[str, ...]]:
        if root is not None:
            try:
                with (root / "plugin.toml").open("rb") as stream:
                    match = tomllib.load(stream).get("match", {})
                return {key: tuple(str(value) for value in match.get(key, ()))
                        for key in ("cores", "content_hints", "hashes")}
            except (OSError, ValueError):
                pass
        return {"cores": ("mesen", "fceumm", "nestopia", "quicknes", "nes"),
                "content_hints": ("dragonwarrior4", "dragonwarrioriv", "dragonquest4", "dragonquestiv"),
                "hashes": ()}

    def _entity_overlay(self, memory: MemoryReader, state: DragonWarrior4State,
                        ram: bytes, battle: BattleState) -> MapOverlay | None:
        return self._map_snapshot.entity_overlay(memory, state, ram, battle, assets=self.assets)

    def _vehicle_overlay(self, memory: MemoryReader, state: DragonWarrior4State,
                         ram: bytes, battle: BattleState) -> MapOverlay | None:
        return self._map_snapshot.vehicle_overlay(memory, state, ram, battle)

    def _interrupted(self, detail: str) -> OverlaySnapshot:
        # Area changes and single failed reads would otherwise flash an alert
        # and drop the map position, so the last good snapshot stands in briefly.
        self._stale_polls += 1
        if self._last_snapshot is not None and self._stale_polls <= STALE_SNAPSHOT_LIMIT:
            if any(section.key == "poker" for section in self._last_snapshot.sections):
                self._last_snapshot = replace(self._last_snapshot, sections=tuple(
                    section for section in self._last_snapshot.sections if section.key != "poker"
                ))
            return self._last_snapshot
        return self._memory_unavailable(detail)

    def _memory_unavailable(self, detail: str) -> OverlaySnapshot:
        self._last_snapshot = None
        return OverlaySnapshot(
            self.name, "Waiting for game",
            (PanelSection("Waiting for game", (PanelRow(detail),), alert=True, priority=1,
                          role="urgent", key="memory-access"), self._guide_section()),
            map_document=self.map_document, display_spec=DISPLAY_SPEC,
        )

    def _log(self, message: str) -> None:
        if message not in self._logged and len(self._logged) < 256:
            self._logged.add(message)
            LOGGER.warning("%s", message)


def _identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())
