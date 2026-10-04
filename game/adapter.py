from __future__ import annotations

from dataclasses import replace
import logging
from pathlib import Path
import re
import tomllib

from retroarch_overlay.core.contracts import GameContext, MemoryReader
from retroarch_overlay.adapters.base import ContentHashResolver
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import (
    GameDisplaySpec,
    MapDocument,
    MapOverlay,
    MapPosition,
    MapRegion,
    MapWaypoint,
    OverlaySnapshot,
    PanelAction,
    PanelChip,
    PanelColumn,
    PanelMeter,
    PanelNumberInput,
    PanelRow,
    PanelSection,
    RetroArchStatus,
)
from retroarch_overlay.retroarch import RetroArchError

from .achievements import ACHIEVEMENTS, TOTAL_POINTS, local_prerequisite
from .battle import (
    BATTLE_CONTEXT_ADDRESS,
    BATTLE_MEMORY_ADDRESS,
    BATTLE_MEMORY_SIZE,
    BattleState,
    read_battle_state,
)
from .bestiary import monster_card, resistance_lines
from .arena import ArenaPredictor, MAX_SIMULATION_COUNT, SIMULATION_COUNT, arena_betting_open, arena_key, validate_simulations
from .guide import chapter_heading, guide_headings, location_heading
from .map_entities import (
    ENTITY_MEMORY_ADDRESS,
    ENTITY_MEMORY_SIZE,
    read_map_entities,
    read_world_vehicles,
)
from .reference_data import load_submap_names
from .reference_data import MAP_NAMES, item_category, map_title
from .rom_assets import DragonWarrior4RomAssets
from .shops import EquipmentComparison, compare_equipment, shop_currency
from .objectives import chapter_objectives, chapter_transition_losses
from .state import RAM_SIZE, WRAM_ADDRESS, WRAM_SIZE, CharacterState, DragonWarrior4State, read_state


RA_GAME_ID = 4612
DISPLAY_SPEC = GameDisplaySpec("nes-4-3", 4, 3)
MEMORY_ERRORS = (RetroArchError, RuntimeError, OSError, ValueError)
LOGGER = logging.getLogger(__name__)

HP_COLOR = "#198754"
MP_COLOR = "#087ca7"
XP_COLOR = "#d4a017"
GOOD_COLOR = "#198754"
BAD_COLOR = "#b33939"
CAUTION_COLOR = "#b7791f"
POISON_COLOR = "#7a4fa3"
CURRENCY_UNITS = {"gold": "G", "casino coins": "coins", "medals": "medals"}
UPGRADE_VERDICTS = frozenset(("Upgrade", "Upgrade with tradeoff"))
# A transition or a single failed read keeps the last good snapshot this many polls.
STALE_SNAPSHOT_LIMIT = 8


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
        self._content_key: tuple[str, str, str] | None = None
        self._guide, self._guide_error = self._load_guide(context.repository_root)
        self._guide_headings = guide_headings(self._guide)
        self._match = self._load_match(context.repository_root)
        rom_path = context.settings.get("rom_path")
        if isinstance(rom_path, str) and rom_path.strip():
            rom_path = Path(rom_path)
        self._content_resolver = ContentHashResolver(files=(rom_path.expanduser(),)) if isinstance(rom_path, Path) else None
        self._identity_error = ""
        self._bestiary_rows: tuple[PanelRow, ...] | None = None
        self._display_context: tuple | None = None
        self._display_document = map_document
        self._economy_target: tuple[int, int, int] | None = None
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

    def set_economy_target(self, target: tuple[int, int, int] | None) -> None:
        self._economy_target = target

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
        in_battle = battle.available and battle.active

        current_zone = None
        live_area = None
        feature_overlay = None
        conditional_overlay = None
        if self.assets is not None and not state.location.is_world:
            try:
                descriptor = self.assets.descriptor(state.location.map_id, state.location.submap)
                if (
                    not battle.active and descriptor is not None
                    and (ram[0x3F], ram[0x40]) == (descriptor.width, descriptor.height)
                    and descriptor.width * descriptor.height <= 0x800
                ):
                    live_tiles = memory.read_memory(0x7800, descriptor.width * descriptor.height)
                    if len(live_tiles) != descriptor.width * descriptor.height:
                        raise ValueError("Live map snapshot is incomplete")
                    if (
                        memory.read_memory(0x3F, 3) != ram[0x3F:0x42]
                        or memory.read_memory(0x63, 3) != ram[0x63:0x66]
                    ):
                        raise ValueError("Discarded live map tiles during a floor transition")
                    live_area = descriptor.key, live_tiles
                feature_overlay = self.assets.feature_overlay(
                    state.location.map_id, state.location.submap, state.treasure_flags,
                    live_area[1] if live_area is not None else None,
                    frozenset(item.item_id for character in state.active_party for item in character.items),
                    frozenset(item.item_id for character in state.available_party if not character.active for item in character.items),
                    state.chapter,
                    state.reserve_accessible,
                    state.chapter == 3 and any(character.character_id == 9 and character.alive and not character.paralyzed
                                               for character in (state.available_party if state.reserve_accessible else state.active_party)),
                    frozenset((1, 2)) if wram[0x27F] & 0x40 else frozenset(),
                    event_flags=state.event_flags,
                    position=(state.location.x, state.location.y),
                )
                roster = state.available_party if state.reserve_accessible else state.active_party
                conditional_overlay = self.assets.conditional_search_overlay(
                    state.location.map_id, state.location.submap, state.event_flags, state.treasure_flags,
                    frozenset(item.item_id for character in roster for item in character.items), state.chapter, ram[0x3D] & 3,
                    live_area[1] if live_area is not None else None)
                walking_routes = self.assets.tile_transition_routes(
                    state.location.map_id, state.location.submap, state.time_value, wram[0x2AA],
                    state.event_flags, live_area[1] if live_area is not None else None)
                if feature_overlay is not None and walking_routes:
                    destinations = {(route.x, route.y): route for route in walking_routes}
                    points = []
                    for point in feature_overlay.waypoints:
                        route = destinations.get((point.x, point.y))
                        if route is not None:
                            destination = map_title(route.destination_key >> 8, route.destination_key & 255, self.submap_names)
                            point = replace(point, detail=" · ".join(
                                part for part in (point.detail, f"Leads to {destination}") if part))
                        points.append(point)
                    feature_overlay = replace(feature_overlay, waypoints=tuple(points))
            except (*MEMORY_ERRORS, IndexError) as error:
                self._log(f"Map objects unavailable: {error}")
        entity_overlay = self._entity_overlay(memory, state, ram, battle)
        overlays = tuple(
            value for value in (feature_overlay, conditional_overlay, entity_overlay,
                                self._vehicle_overlay(memory, state, ram, battle))
            if value is not None
        )
        if self.assets is not None:
            for detail in self.assets.diagnostics:
                self._log(detail)
        if not battle.available:
            self._log(f"Enemy memory unavailable: {battle.detector_evidence}")

        sections = [
            self._combatants_section(state, battle),
            self._journey_section(state),
            self._achievement_section(state),
            self._guide_section(state),
        ]
        if self.asset_error:
            sections.append(PanelSection("ROM setup", (PanelRow(self.asset_error),), alert=True,
                                         priority=1, role="urgent", key="rom-setup"))
        objectives = self._objective_section(state)
        if objectives is not None:
            sections.append(objectives)
        losses = chapter_transition_losses(state)
        if losses:
            sections.append(PanelSection(
                "Chapter end",
                tuple(PanelRow(f"{name} is lost when this chapter ends", emphasis="warning") for name in losses),
                priority=7, role="goals", key="chapter-transition"))
        target = self._economy_section(state)
        if target is not None:
            sections.append(target)
        if battle.arena:
            sections.append(self._arena_section(state, battle))
        if self.assets is not None:
            try:
                collections = self._collection_section(state)
                if collections is not None:
                    sections.append(collections)
            except MEMORY_ERRORS as error:
                self._log(f"Collection catalog unavailable: {error}")
        local_monsters: tuple[int, ...] = ()
        if not in_battle:
            try:
                encounters, local_monsters, current_zone = self._encounter_section(memory, state, ram, wram)
                if encounters is not None:
                    sections.append(encounters)
            except (*MEMORY_ERRORS, IndexError) as error:
                self._log(f"Encounter pool unavailable: {error}")
        bestiary = self._bestiary_section(battle, local_monsters)
        if bestiary is not None:
            sections.append(bestiary)
        if self.assets is not None and state.chapter == 4:
            knowledge = self._ai_knowledge_section(state, battle)
            if knowledge is not None:
                sections.append(knowledge)
        if self.assets is not None and not state.location.is_world and not in_battle:
            try:
                shops = self._shop_section(state, wram[0x2E7:0x2EA])
                if shops is not None:
                    sections.append(shops)
            except (ValueError, IndexError) as error:
                self._log(f"Town stock unavailable: {error}")
        if self.assets is not None and self.map_document is not None:
            reveal_area = (state.location.layer_id, ram[0x520]) if not state.location.is_world and ram[0x7BA] == 4 and ram[0x520] < 32 else None
            palette_frame = self.assets.native_palette_frame(ram) if not battle.active else None
            animated_layer = (_layer_key(state), palette_frame) if palette_frame is not None else None
            pattern_layer = None
            if not battle.active and ram[0x573]:
                try:
                    updates = self.assets.native_pattern_frame(ram, memory.read_memory(0x7600, 136))
                    if updates:
                        pattern_layer = (_layer_key(state), updates)
                except MEMORY_ERRORS:
                    pass
            context = (int(state.time_value >= 0x78), ram[0x65] == 3, bool(wram[0x293] & 0x10), live_area, reveal_area, animated_layer, pattern_layer, current_zone)
            if context != self._display_context:
                layers = self.assets.display_layers(self.map_document.layers, state.time_value, ram[0x65], wram[0x293], live_area, reveal_area, animated_layer, pattern_layer)
                if current_zone is not None:
                    layers = tuple(replace(layer, regions=layer.regions + (current_zone[1],))
                                   if layer.key == current_zone[0] else layer for layer in layers)
                self._display_document = MapDocument(
                    self.map_document.title,
                    layers,
                    self.map_document.overlay_kinds,
                )
                self._display_context = context
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
            map_document=self._display_document,
            map_overlays=overlays,
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

    def _combatants_section(self, state: DragonWarrior4State, battle: BattleState) -> PanelSection:
        in_battle = battle.available and battle.active
        columns = [PanelColumn("party", "Party", tuple(_character_row(character, in_battle) for character in state.active_party))]
        if in_battle:
            enemies = []
            described: set[int] = set()
            for enemy in battle.enemies:
                if not enemy.coherent:
                    continue
                meters = ()
                if enemy.max_hp is not None and enemy.max_mp is not None:
                    meters = (PanelMeter("HP", enemy.hp, enemy.max_hp, HP_COLOR),
                              PanelMeter("MP", enemy.mp, enemy.max_mp, MP_COLOR, enemy.infinite_mp))
                title = enemy.name or "Unknown enemy"
                if not meters:
                    title += f" · HP {enemy.hp} · MP {'unlimited' if enemy.infinite_mp else enemy.mp}"
                detail = ""
                if enemy.monster_id is not None and enemy.monster_id not in described:
                    described.add(enemy.monster_id)
                    detail = "\n".join(resistance_lines(self._resistances(enemy.monster_id), compact=True))
                enemies.append(PanelRow(title, meters=meters, detail=detail,
                                        chips=tuple(PanelChip(condition, CAUTION_COLOR) for condition in enemy.conditions)))
            columns.append(PanelColumn("enemies", "Arena monsters" if battle.arena else "Enemies", tuple(enemies)))
        return PanelSection(
            "Combatants", (), priority=0, role="urgent", key="combatants", collapsible=False,
            columns=tuple(columns),
        )

    def _monster_name(self, monster_id: int) -> str | None:
        return self.assets.monster_name(monster_id) if self.assets is not None else None

    def _resistances(self, monster_id: int) -> tuple[tuple[str, str], ...]:
        if self.assets is None or self.assets.region != "US":
            return ()
        monster = self.assets.monster_definition(monster_id)
        resistances = getattr(monster, "resistances", ())
        return resistances if isinstance(resistances, tuple) else ()

    def _monster_card(self, monster_id: int, title: str | None = None) -> PanelRow | None:
        assets = self.assets
        monster = assets.monster_definition(monster_id) if assets is not None else None
        if assets is None or monster is None:
            return None
        drop = assets.indexed_name(3, monster.drop_item_id) if monster.drop_item_id is not None else None
        return monster_card(monster, drop, title)

    def _bestiary_section(self, battle: BattleState, local_monsters: tuple[int, ...] = ()) -> PanelSection | None:
        assets = self.assets
        if assets is None or assets.region != "US":
            return None
        if self._bestiary_rows is None:
            self._bestiary_rows = tuple(sorted(
                (card for card in (self._monster_card(identifier) for identifier in range(214)) if card is not None),
                key=lambda card: card.text.casefold()))
        if not self._bestiary_rows:
            return None
        catalog = PanelAction("View bestiary", "Bestiary", self._bestiary_rows, key="bestiary-catalog")
        in_battle = battle.available and battle.active
        if in_battle:
            cards = []
            for identifier in dict.fromkeys(enemy.monster_id for enemy in battle.enemies
                                            if enemy.coherent and enemy.monster_id is not None):
                enemy = next(enemy for enemy in battle.enemies if enemy.monster_id == identifier and enemy.coherent)
                # A boss phase keeps its displayed name over the stat record it borrows.
                card = self._monster_card(identifier, enemy.name)
                if card is not None:
                    cards.append(card)
            if cards:
                return PanelSection("Bestiary", tuple(cards), priority=1, role="area", key="bestiary",
                                    actions=(catalog,), compact_rows=tuple(cards))
        cards = tuple(card for card in (self._monster_card(identifier) for identifier in dict.fromkeys(local_monsters))
                  if card is not None)
        summary = (PanelRow(f"{len(cards)} monsters in this area" if len(cards) != 1 else "1 monster in this area")
                   if cards else PanelRow("No monsters in this area", emphasis="muted"))
        return PanelSection("Bestiary", cards, priority=20, role="area", key="bestiary",
                            actions=(catalog,), compact_rows=(summary,))

    def _ai_knowledge_section(self, state: DragonWarrior4State, battle: BattleState) -> PanelSection | None:
        if self.assets is None or self.assets.region != "US":
            return None
        catalog = tuple(PanelRow(f"{self.assets.monster_name(identifier)} · learned {state.knowledge_rank(identifier)}/3",
                                 progress=state.knowledge_rank(identifier) / 3, progress_color="accent")
                        for identifier in range(214) if state.knowledge_rank(identifier) is not None)
        if not catalog:
            return None
        identities = tuple(dict.fromkeys(enemy.monster_id for enemy in battle.enemies
                                        if battle.active and enemy.coherent and enemy.monster_id is not None))
        current = tuple(PanelRow(
            f"{next(enemy.label for enemy in battle.enemies if enemy.monster_id == identifier and enemy.coherent)} · "
            f"learned {state.knowledge_rank(identifier)}/3",
            progress=state.knowledge_rank(identifier) / 3, progress_color="accent")
            for identifier in identities if state.knowledge_rank(identifier) is not None)
        rows = (PanelRow(f"Tactics: {state.tactics_name}"),) + current
        return PanelSection("AI knowledge", rows, priority=21, role="area", key="ai-knowledge",
                            actions=(PanelAction("View AI knowledge", "What the party AI has learned", catalog, key="ai-knowledge-catalog"),))

    def _objective_section(self, state: DragonWarrior4State) -> PanelSection | None:
        objectives = chapter_objectives(state)
        if not objectives:
            return None
        rows = tuple(PanelRow(f"{objective.title} · {objective.destination}", objective.completed,
                              detail="" if objective.completed else objective.hint, progress=objective.progress)
                     for objective in objectives)
        pending = next((objective for objective in objectives if not objective.completed), None)
        compact = (PanelRow(f"{pending.title} · {pending.destination}", False, progress=pending.progress)
                   if pending is not None else PanelRow("All objectives complete", True))
        keys = {layer.key for layer in self.map_document.layers} if self.map_document is not None else set()
        actions = tuple(PanelAction(f"Map: {objective.destination}", objective.destination, (),
                                    key=f"objective-map-{objective.key}", map_layer_key=objective.layer_key)
                        for objective in objectives if not objective.completed and objective.layer_key in keys)
        return PanelSection("Chapter objectives", rows, priority=8, role="goals", key="chapter-objectives",
                            actions=actions, compact_rows=(compact,))

    def _economy_section(self, state: DragonWarrior4State) -> PanelSection | None:
        if self.assets is None or self._economy_target is None:
            return None
        try:
            item_id, map_id, submap = self._economy_target
            currency = shop_currency(map_id, submap)
            unit = CURRENCY_UNITS[currency]
            price = self.assets.item_price(item_id, map_id, submap)
            balance = {"gold": state.gold, "casino coins": state.casino_coins, "medals": state.small_medals}[currency]
            title = self.assets.indexed_name(3, item_id)
        except MEMORY_ERRORS as error:
            self._log(f"Savings target unavailable: {error}")
            return None
        progress = min(1.0, balance / price) if price else 1.0
        status = "You can afford it" if balance >= price else f"{price - balance:,} {unit} to go"
        return PanelSection(
            "Saving for",
            (PanelRow(f"{title} · {price:,} {unit}", emphasis="heading"), PanelRow(status, progress=progress)),
            actions=(PanelAction("Stop tracking", "Stop tracking", (), key="clear-economy-target",
                                 command=lambda: self.set_economy_target(None)),),
            priority=9, role="goals", key="economy-target",
            compact_rows=(PanelRow(f"{title} · {status[0].lower()}{status[1:]}", progress=progress),))

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
        rows = [PanelRow(f"Casino coins {state.casino_coins:,}")]
        if battle.arena_wager is not None:
            rows.append(PanelRow(f"Bet {battle.arena_wager:,} coins"))
        prediction = self._arena_predictor.status
        for index, (integer, fraction) in enumerate(battle.arena_odds):
            monster_id = self._arena_lineup[index] if len(self._arena_lineup) == 4 else 255
            if monster_id == 255 and len(self._arena_lineup) == 4:
                continue
            name = self._monster_name(monster_id) if monster_id != 255 else None
            text = (f"Entry {index + 1}" + (f" · {name}" if name else "") + f" · {integer}.{fraction}x"
                    if self._arena_lineup else f"Entry {index + 1} pays {integer}.{fraction}x")
            chance = None
            if prediction.result is not None:
                chance = prediction.result.wins[index] / prediction.result.simulations
                text += f" · {chance:.0%} win chance"
            rows.append(PanelRow(text, progress=chance,
                                 chips=(PanelChip("Your bet", GOOD_COLOR),) if index == battle.arena_selection else ()))
        if self.assets is not None and battle.arena_wager is not None and battle.arena_selection is not None and battle.arena_odds:
            payout = self.assets.arena_payout(battle.arena_wager, *battle.arena_odds[battle.arena_selection])
            if payout is not None:
                rows.append(PanelRow(f"A win pays {payout:,} coins", emphasis="success"))
        if self._arena_requested is not None:
            rows.append(PanelRow("Capturing matchup"))
        elif prediction.running:
            rows.append(PanelRow(f"Simulating {prediction.completed:,}/{prediction.simulations:,}",
                                 progress=prediction.completed / prediction.simulations))
        elif prediction.result is not None:
            rows.append(PanelRow(f"Draw {prediction.result.draws / prediction.result.simulations:.0%} · {prediction.result.simulations:,} simulations"))
        elif prediction.error:
            rows.append(PanelRow(f"Prediction failed: {prediction.error}", emphasis="warning"))
        actions = ()
        if self._arena_requested is not None or prediction.running:
            actions = (PanelAction("Cancel", "Cancel arena estimate", (),
                                   key="arena-cancel", command=self.cancel_arena_prediction),)
        elif self.assets is not None and self._arena_key is not None:
            actions = (PanelAction("Estimate win chances", "Arena win chances", (),
                                   key="arena-predict", command=self.predict_arena),)
        inputs = (PanelNumberInput(
            "Simulations", self._arena_simulations, minimum=1, maximum=MAX_SIMULATION_COUNT,
            key="arena-simulations", enabled=self._arena_requested is None and not prediction.running,
            command=self.set_arena_simulations,
        ),)
        return PanelSection("Arena", tuple(rows), actions=actions, priority=3, role="urgent", key="arena", inputs=inputs)

    def _collection_section(self, state: DragonWarrior4State) -> PanelSection | None:
        if self.assets is None:
            return None
        catalog = self.assets.collectible_catalog()
        if not catalog:
            return None
        statuses = tuple(definition.collected(state.treasure_flags) for definition in catalog)
        found = statuses.count(True)
        unknown = statuses.count(None)
        medals = tuple(definition.collected(state.treasure_flags) for definition in catalog if definition.item_id == 0x69)
        carried = sum(item.item_id == 0x69 for character in state.available_party for item in character.items)
        rows = (
            PanelRow(f"Treasures found {found}/{len(catalog)}" + (f" · {unknown} unknown" if unknown else ""),
                     progress=found / len(catalog)),
            PanelRow(f"Small medals found {medals.count(True)}/{len(medals)}"),
            PanelRow(f"Small medals: {carried} carried · {state.small_medals} with the Medal King"),
        )
        return PanelSection("Collections", rows, priority=12, role="area", key="collections")

    def _encounter_section(
        self, memory: MemoryReader, state: DragonWarrior4State, ram: bytes, wram: bytes,
    ) -> tuple[PanelSection | None, tuple[int, ...], tuple[str, MapRegion] | None]:
        if ram[0x515] == 2:
            suppressed = "No random encounters while flying"
        elif ram[0x58E] == 2 or wram[0x288] & 0x80:
            suppressed = "No random encounters right now"
        else:
            suppressed = ""
        if suppressed:
            return PanelSection("Local encounters", (PanelRow(suppressed, emphasis="success"),),
                                priority=15, role="area", key="encounter-pool"), (), None
        assets = self.assets
        if assets is None:
            return None, (), None
        current_zone = None
        header: tuple[PanelRow, ...] = ()
        if state.location.is_world:
            pool = assets.encounter_pool(state.chapter, ram[0x65], state.location.x,
                                         state.location.y, state.time_value, ram[0x515])
            if pool is None:
                return None, (), None
            zone = pool[0]
            night = state.time_value >= 0x78
            if ram[0x65] == 0:
                area = MapRegion((state.location.x // 16) * 16, (state.location.y // 16) * 16, 16, 16,
                                 "Encounter zone", kind="encounter-zone", color="#bf8b2e")
            elif ram[0x65] == 1:
                area = MapRegion(0, 0 if state.location.y < 12 else 12, 64, 12 if state.location.y < 12 else 52,
                                 "Encounter zone", kind="encounter-zone", color="#bf8b2e")
            elif ram[0x65] == 3:
                area = MapRegion(0, 0, 64, 54, "Encounter zone", kind="encounter-zone", color="#bf8b2e")
            else:
                area = None
            if area is not None:
                current_zone = _layer_key(state), area
            header = (self._encounter_rate_row(memory, state, wram, zone, night),)
            formations = assets.formation_chances(zone, 0x3FBE if night else 0x1BEF)
        else:
            pool = assets.indoor_encounter_pool(state.chapter, state.location.map_id, state.location.submap)
            if pool is None:
                return None, (), None
            formations = assets.formation_chances(pool[0], 0x3FFF)
        rows = []
        monsters: list[int] = []
        for formation in formations:
            definitions = tuple(assets.monster_definition(identifier) for identifier in formation.monster_ids)
            monsters.extend(identifier for identifier in formation.monster_ids if identifier not in monsters)
            reward = ""
            if definitions and all(definition is not None for definition in definitions):
                reward = (f" · {sum(definition.experience for definition in definitions):,} XP"
                          f" · {sum(definition.gold for definition in definitions):,} G"
                          + ("" if formation.fixed_group else " each"))
            rows.append(PanelRow(formation.label + reward, progress=formation.chance / 256, progress_color="accent",
                                 chips=(PanelChip(f"{formation.chance / 256:.0%}"),)))
        if not rows:
            return None, (), current_zone
        if current_zone is not None:
            layer_key, region = current_zone
            current_zone = layer_key, replace(region, detail="\n".join(
                f"{formation.label} · {formation.chance / 256:.0%}" for formation in formations))
        leading = " · ".join(f"{formation.label} {formation.chance / 256:.0%}" for formation in formations[:2])
        if len(formations) > 2:
            leading += f" · +{len(formations) - 2} more"
        return (PanelSection("Local encounters", header + tuple(rows), priority=15, role="area", key="encounter-pool",
                             compact_rows=(PanelRow(leading),)),
                tuple(monsters), current_zone)

    def _encounter_rate_row(self, memory: MemoryReader, state: DragonWarrior4State,
                            wram: bytes, zone: int, night: bool) -> PanelRow:
        period = "Night" if night else "Day"
        try:
            timing = memory.read_memory(0x6E41, 2)
            terrain = memory.read_memory(0x7140, 1)
            scent = memory.read_memory(0x6BEB, 1)
            if len(timing) != 2 or len(terrain) != 1 or len(scent) != 1:
                raise ValueError("Incomplete encounter rate inputs")
            threshold, detail = self.assets.land_encounter_threshold(
                zone, terrain[0], state.time_value, timing[1], timing[0], wram[0x2D5], scent[0])
        except MEMORY_ERRORS:
            return PanelRow(period)
        if threshold is None:
            return PanelRow(period)
        if threshold == 0:
            return PanelRow(detail or "No encounter on the next step", emphasis="success")
        return PanelRow(f"{period} · about {min(threshold, 256) / 256:.0%} per step")

    def _shop_section(self, state: DragonWarrior4State, special_stock: bytes) -> PanelSection | None:
        assets = self.assets
        if assets is None:
            return None
        stock = assets.town_shops(state.location.map_id, state.time_value, special_stock)
        if not stock:
            return None
        roster = tuple(character for character in state.available_party if not character.guest)
        rows: list[PanelRow] = []
        upgrades: list[PanelRow] = []
        actions: list[PanelAction] = []
        for submap, shop_type, items in stock:
            currency = shop_currency(state.location.map_id, submap)
            unit = CURRENCY_UNITS[currency]
            balance = {"gold": state.gold, "casino coins": state.casino_coins, "medals": state.small_medals}[currency]
            shop_name = ("Casino prizes" if currency == "casino coins" else "Medal exchange" if currency == "medals"
                         else {1: "Weapon shop", 2: "Item shop", 3: "Armor shop"}[shop_type])
            if submap != state.location.submap:
                shop_name += " · " + map_title(state.location.map_id, submap, self.submap_names)
            rows.append(PanelRow(shop_name, emphasis="heading"))
            for item_id in items:
                title = assets.indexed_name(3, item_id)
                price = assets.item_price(item_id, state.location.map_id, submap)
                affordable = balance >= price
                afford = (PanelChip("Can afford", GOOD_COLOR) if affordable
                          else PanelChip(f"Need {price - balance:,} {unit}", BAD_COLOR))
                label = f"{title} · {price:,} {unit}"
                rows.append(PanelRow(label, chips=(afford,),
                                     progress=None if affordable or not price else balance / price))
                if not affordable:
                    target = (item_id, state.location.map_id, submap)
                    actions.append(PanelAction(f"Track {title}", "Track a savings target", (),
                                               key=f"economy-target-{submap}-{shop_type}-{item_id}",
                                               command=lambda selected=target: self.set_economy_target(selected)))
                if item_category(item_id) == "item":
                    continue
                comparisons = tuple(compare_equipment(assets, item_id, character, state.hero_female) for character in roster)
                gains = tuple(comparison for comparison in comparisons if comparison.verdict in UPGRADE_VERDICTS)
                rows.extend(_upgrade_row(comparison) for comparison in gains)
                others = _other_verdicts(comparisons)
                if others:
                    rows.append(PanelRow(others, emphasis="muted"))
                if gains:
                    upgrades.append(PanelRow(
                        f"{label} · " + ", ".join(f"{comparison.character_name} {comparison.delta:+d} {comparison.stat}"
                                                  for comparison in gains),
                        tooltip="\n".join(f"{comparison.character_name}: {', '.join(comparison.notes)}"
                                          for comparison in gains if comparison.notes),
                        chips=(afford,)))
        compact = tuple(upgrades) or (PanelRow("No upgrades for your party here", emphasis="muted"),)
        return PanelSection("Town shops", tuple(rows), actions=tuple(actions), priority=14, role="area",
                            key="town-shops", compact_rows=compact)

    def _journey_section(self, state: DragonWarrior4State) -> PanelSection:
        vehicles = tuple(title for title, available in (("Boat", state.has_boat), ("Balloon", state.has_balloon))
                         if available)
        funds = f"Gold {state.gold:,}"
        if state.casino_coins:
            funds += f" · Casino coins {state.casino_coins:,}"
        rows = [
            PanelRow(state.chapter_name),
            PanelRow(" · ".join((state.time_name, *vehicles))),
            PanelRow(funds),
        ]
        if state.vault_gold:
            rows.append(PanelRow(f"Vault {state.vault_gold:,} gold"))
        actions = ()
        if self.assets is not None and self.assets.region == "US":
            destinations = self.assets.return_destinations(state.chapter, state.return_flags)
            keys = {layer.key for layer in self.map_document.layers} if self.map_document is not None else set()
            actions = tuple(PanelAction(f"Map: {title}", title, (), key=f"return-map-{map_id:02x}",
                                        map_layer_key=f"area-{map_id:02x}-00")
                            for map_id, title in destinations if f"area-{map_id:02x}-00" in keys)
            if actions:
                rows.append(PanelRow("Return destinations:"))
            elif destinations:
                rows.append(PanelRow("Return: " + ", ".join(title for _, title in destinations)))
        if state.transform_steps:
            rows.append(PanelRow(f"Transformed · {state.transform_steps} steps left"))
        return PanelSection(
            "Journey",
            tuple(rows),
            priority=5, role="goals", key="journey",
            actions=actions,
            compact_rows=(PanelRow(f"{state.chapter_name} · Gold {state.gold:,}"),),
        )

    def _achievement_section(self, state: DragonWarrior4State | None = None) -> PanelSection:
        self.progress = self._progress(self.context)
        unlocked_ids = self.progress.unlocked_ids if self.progress else frozenset()
        unlocked = tuple(value for value in ACHIEVEMENTS if value.achievement_id in unlocked_ids)
        rows = [PanelRow(f"{len(unlocked)}/{len(ACHIEVEMENTS)} unlocked · {sum(value.points for value in unlocked)}/{TOTAL_POINTS} points",
                         len(unlocked) == len(ACHIEVEMENTS))]
        if not (self.progress and self.progress.username):
            rows.append(PanelRow("RetroAchievements account unavailable", emphasis="muted"))
        return PanelSection(
            "RetroAchievements", tuple(rows), priority=25, role="goals", key="retroachievements",
            actions=(PanelAction("View achievements", "Dragon Quest IV Achievements", tuple(
                PanelRow(f"{value.title} · {value.points} points", value.achievement_id in unlocked_ids,
                         detail="\n".join(part for part in (
                             value.description,
                             local_prerequisite(value.achievement_id, state) if state is not None else "",
                         ) if part))
                for value in ACHIEVEMENTS
            ), key="achievements"),),
        )

    def _guide_section(self, state: DragonWarrior4State | None = None) -> PanelSection:
        actions = []
        if state is not None:
            chapter = chapter_heading(self._guide_headings, state.chapter)
            if chapter is not None:
                actions.append(PanelAction(f"Go to Chapter {state.chapter + 1}", chapter.title, (),
                                           key="guide-chapter", document_anchor=chapter.anchor))
            if not state.location.is_world and 0 <= state.location.map_id < len(MAP_NAMES):
                step = location_heading(self._guide_headings, state.chapter, MAP_NAMES[state.location.map_id])
                if step is not None:
                    actions.append(PanelAction(f"Go to {step.title}", step.title, (),
                                               key="guide-location", document_anchor=step.anchor))
        return PanelSection(
            "Guide", (PanelRow(self._guide_error),) if self._guide_error else (),
            priority=40, role="context", key="guide", markdown=self._guide, actions=tuple(actions),
        )

    @staticmethod
    def _load_guide(root: Path | None) -> tuple[str, str]:
        if root is None:
            return "", "Guide unavailable: plugin repository root is missing"
        try:
            return (root / "Guide" / "DW4_UnifiedGuide.md").read_text(encoding="utf-8"), ""
        except (OSError, UnicodeError) as error:
            return "", f"Guide unavailable: {error}"

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

    @staticmethod
    def _progress(context: GameContext) -> RAProgress | None:
        if context.ra_progress_provider is None:
            return None
        try:
            return context.ra_progress_provider(RA_GAME_ID)
        except (RuntimeError, OSError, ValueError):
            return None

    def _entity_overlay(self, memory: MemoryReader, state: DragonWarrior4State,
                        ram: bytes, battle: BattleState) -> MapOverlay | None:
        if self.assets is None or state.location.is_world or state.location.area == "Unknown" or battle.active:
            return None
        descriptor = self.assets.descriptor(state.location.map_id, state.location.submap)
        if descriptor is None:
            return None
        try:
            entities = read_map_entities(memory.read_memory(ENTITY_MEMORY_ADDRESS, ENTITY_MEMORY_SIZE),
                                         memory.read_memory(0x7140, 32))
            roles = self.assets.map_actor_roles(ram[0x67], int.from_bytes(ram[0x3A:0x3C], "little"), state.time_value)
        except (*MEMORY_ERRORS, IndexError):
            return None
        points = tuple(
            MapWaypoint(entity.x, entity.y, roles[entity.slot - 6][0], kind="services" if roles[entity.slot - 6][1] in {"shop", "service", "healing"} else "entities",
                        marker=roles[entity.slot - 6][1])
            for entity in entities
            if entity.slot - 6 < len(roles) and 0 <= entity.x < descriptor.width and 0 <= entity.y < descriptor.height
            and entity.visible and entity.room_class == ram[0x46] & 0xE0
        )
        return MapOverlay(_layer_key(state), points) if points else None

    def _vehicle_overlay(self, memory: MemoryReader, state: DragonWarrior4State,
                         ram: bytes, battle: BattleState) -> MapOverlay | None:
        if not state.location.is_world or state.location.memory_region != "US" or battle.active:
            return None
        try:
            vehicles = read_world_vehicles(memory.read_memory(ENTITY_MEMORY_ADDRESS, ENTITY_MEMORY_SIZE),
                                           ram[0x65], state.has_boat, state.has_balloon)
        except MEMORY_ERRORS:
            return None
        points = tuple(MapWaypoint(x, y, title, "Where you left it", "entities",
                                   marker=title.casefold()) for title, x, y in vehicles)
        return MapOverlay(_layer_key(state), points) if points else None

    def _interrupted(self, detail: str) -> OverlaySnapshot:
        # Area changes and single failed reads would otherwise flash an alert
        # and drop the map position, so the last good snapshot stands in briefly.
        self._stale_polls += 1
        if self._last_snapshot is not None and self._stale_polls <= STALE_SNAPSHOT_LIMIT:
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


def _character_row(character: CharacterState, in_battle: bool = False) -> PanelRow:
    chips = tuple(PanelChip(label, color) for label, enabled, color in (
        ("Down", not character.alive, BAD_COLOR),
        ("Poisoned", character.poisoned, POISON_COLOR),
        ("Paralyzed", character.paralyzed, CAUTION_COLOR),
    ) if enabled)
    title = character.name if character.guest else f"{character.name} · Lv {character.level}"
    remaining = character.experience_remaining
    if not character.guest and not in_battle and remaining is not None:
        title += f" · {remaining:,} XP to next"
    tooltip = [] if character.guest else [f"XP {character.experience:,}"]
    if character.spell_milestones:
        tooltip.append("Next spells: " + ", ".join(character.spell_milestones))
    return PanelRow(title, tooltip="\n".join(tooltip), chips=chips,
                    progress=character.experience_fraction, progress_color=XP_COLOR,
                    meters=(PanelMeter("HP", character.hp, character.max_hp, HP_COLOR),
                            PanelMeter("MP", character.mp, character.max_mp, MP_COLOR)))


def _upgrade_row(comparison: EquipmentComparison) -> PanelRow:
    text = f"▲ {comparison.character_name} · {comparison.stat} {comparison.current_value} to {comparison.candidate_value}"
    if comparison.current_item != "None":
        text += f" · replaces {comparison.current_item}"
    return PanelRow(text, emphasis="success" if comparison.verdict == "Upgrade" else "warning",
                    detail="\n".join(comparison.notes), chips=(PanelChip(
        f"{comparison.delta:+d} {comparison.stat}",
        GOOD_COLOR if comparison.verdict == "Upgrade" else CAUTION_COLOR),))


def _other_verdicts(comparisons: tuple[EquipmentComparison, ...]) -> str:
    groups = (
        ("Same", tuple(comparison.character_name + (f" ({', '.join(comparison.notes)})" if comparison.notes else "")
                       for comparison in comparisons if comparison.verdict == "Sidegrade")),
        ("Worse", tuple(f"{comparison.character_name} {comparison.delta:+d}"
                        for comparison in comparisons if comparison.verdict == "Downgrade")),
        ("Can't equip", tuple(comparison.character_name for comparison in comparisons
                              if comparison.verdict == "Cannot equip")),
        ("Wearing cursed gear", tuple(comparison.character_name for comparison in comparisons
                                      if comparison.verdict == "Cannot replace cursed gear")),
    )
    return " · ".join(f"{label}: {', '.join(names)}" for label, names in groups if names)


def _identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _layer_key(state: DragonWarrior4State) -> str:
    if state.location.is_world:
        return {"World": "world", "Gottside": "gottside", "Underworld": "underworld"}.get(state.location.area, "world")
    return f"area-{state.location.map_id:02x}-{state.location.submap:02x}"
