from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import (
    MapDocument, MapRegion, PanelAction, PanelChip, PanelColumn, PanelMeter,
    PanelNumberInput, PanelRow, PanelSection,
)

from .achievements import ACHIEVEMENTS, TOTAL_POINTS, local_prerequisite
from .arena import MAX_SIMULATION_COUNT, PredictionStatus
from .battle import BattleState
from .bestiary import monster_card, resistance_lines
from .guide import chapter_heading, guide_headings, location_heading
from .map_snapshot import MEMORY_ERRORS, _layer_key
from .objectives import chapter_objectives, chapter_transition_losses
from .reference_data import MAP_NAMES, item_category, load_submap_names, map_title
from .rom_assets import DragonWarrior4RomAssets
from .shops import EquipmentComparison, compare_equipment, shop_currency
from .state import CharacterState, DragonWarrior4State


RA_GAME_ID = 4612
CURRENCY_UNITS = {"gold": "G", "casino coins": "coins", "medals": "medals"}
UPGRADE_VERDICTS = frozenset(("Upgrade", "Upgrade with tradeoff"))
HP_COLOR = "#198754"
MP_COLOR = "#087ca7"
XP_COLOR = "#d4a017"
GOOD_COLOR = "#198754"
BAD_COLOR = "#b33939"
CAUTION_COLOR = "#b7791f"
POISON_COLOR = "#7a4fa3"


class PanelPresentation:
    def __init__(
        self, context: GameContext, assets: DragonWarrior4RomAssets | None,
        map_document: MapDocument | None, asset_error: str, *, log: Callable[[str], None],
    ) -> None:
        self.context = context
        self.assets = assets
        self.map_document = map_document
        self.asset_error = asset_error
        self.submap_names = load_submap_names(context.repository_root)
        self.progress = self._progress(context)
        self._guide, self._guide_error = self._load_guide(context.repository_root)
        self._guide_headings = guide_headings(self._guide)
        self._bestiary_rows: tuple[PanelRow, ...] | None = None
        self._economy_target: tuple[int, int, int] | None = None
        self._presentation_log = log

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

    def _resistances(self, monster_id: int) -> tuple[tuple[str, str], ...]:
        if self.assets is None or self.assets.region != "US":
            return ()
        monster = self.assets.monster_definition(monster_id)
        resistances = getattr(monster, "resistances", ())
        return resistances if isinstance(resistances, tuple) else ()


    def _sections(
        self, state: DragonWarrior4State, battle: BattleState, special_stock: bytes, *,
        encounters: Callable[[], tuple[PanelSection | None, tuple[int, ...], tuple[str, MapRegion] | None]],
        arena_section: Callable[[], PanelSection],
    ) -> tuple[tuple[PanelSection, ...], tuple[str, MapRegion] | None]:
        in_battle = battle.available and battle.active
        current_zone = None
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
            sections.append(arena_section())
        if self.assets is not None:
            try:
                collections = self._collection_section(state)
                if collections is not None:
                    sections.append(collections)
            except MEMORY_ERRORS as error:
                self._presentation_log(f"Collection catalog unavailable: {error}")
        local_monsters: tuple[int, ...] = ()
        if not in_battle:
            try:
                encounters, local_monsters, current_zone = encounters()
                if encounters is not None:
                    sections.append(encounters)
            except (*MEMORY_ERRORS, IndexError) as error:
                self._presentation_log(f"Encounter pool unavailable: {error}")
        bestiary = self._bestiary_section(battle, local_monsters)
        if bestiary is not None:
            sections.append(bestiary)
        if self.assets is not None and state.chapter == 4:
            knowledge = self._ai_knowledge_section(state, battle)
            if knowledge is not None:
                sections.append(knowledge)
        if self.assets is not None and not state.location.is_world and not in_battle:
            try:
                shops = self._shop_section(state, special_stock)
                if shops is not None:
                    sections.append(shops)
            except (ValueError, IndexError) as error:
                self._presentation_log(f"Town stock unavailable: {error}")
        return tuple(sections), current_zone

    def set_economy_target(self, target: tuple[int, int, int] | None) -> None:
        self._economy_target = target

    def _monster_name(self, monster_id: int) -> str | None:
        return self.assets.monster_name(monster_id) if self.assets is not None else None

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
            self._presentation_log(f"Savings target unavailable: {error}")
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
    def _progress(context: GameContext) -> RAProgress | None:
        if context.ra_progress_provider is None:
            return None
        try:
            return context.ra_progress_provider(RA_GAME_ID)
        except (RuntimeError, OSError, ValueError):
            return None

    def _present_arena(
        self, state: DragonWarrior4State, battle: BattleState, *, prediction: PredictionStatus,
        lineup: tuple[int, ...], requested: bool, simulations: int, ready: bool,
        predict: Callable[[], None], cancel: Callable[[], None], set_simulations: Callable[[int], None],
    ) -> PanelSection:
        rows = [PanelRow(f"Casino coins {state.casino_coins:,}")]
        if battle.arena_wager is not None:
            rows.append(PanelRow(f"Bet {battle.arena_wager:,} coins"))
        for index, (integer, fraction) in enumerate(battle.arena_odds):
            monster_id = lineup[index] if len(lineup) == 4 else 255
            if monster_id == 255 and len(lineup) == 4:
                continue
            name = self._monster_name(monster_id) if monster_id != 255 else None
            text = (f"Entry {index + 1}" + (f" · {name}" if name else "") + f" · {integer}.{fraction}x"
                    if lineup else f"Entry {index + 1} pays {integer}.{fraction}x")
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
        if requested:
            rows.append(PanelRow("Capturing matchup"))
        elif prediction.running:
            rows.append(PanelRow(f"Simulating {prediction.completed:,}/{prediction.simulations:,}",
                                 progress=prediction.completed / prediction.simulations))
        elif prediction.result is not None:
            rows.append(PanelRow(f"Draw {prediction.result.draws / prediction.result.simulations:.0%} · {prediction.result.simulations:,} simulations"))
        elif prediction.error:
            rows.append(PanelRow(f"Prediction failed: {prediction.error}", emphasis="warning"))
        actions = ()
        if requested or prediction.running:
            actions = (PanelAction("Cancel", "Cancel arena estimate", (),
                                   key="arena-cancel", command=cancel),)
        elif self.assets is not None and ready:
            actions = (PanelAction("Estimate win chances", "Arena win chances", (),
                                   key="arena-predict", command=predict),)
        inputs = (PanelNumberInput(
            "Simulations", simulations, minimum=1, maximum=MAX_SIMULATION_COUNT,
            key="arena-simulations", enabled=not requested and not prediction.running,
            command=set_simulations,
        ),)
        return PanelSection("Arena", tuple(rows), actions=actions, priority=3, role="urgent", key="arena", inputs=inputs)


    def _present_encounters(
        self, state: DragonWarrior4State, ram: bytes, wram: bytes, *,
        rate_row: Callable[[int, bool], PanelRow],
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
            header = (rate_row(zone, night),)
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

    def _present_encounter_rate_row(self, threshold: int | None, detail: str, night: bool) -> PanelRow:
        period = "Night" if night else "Day"
        if threshold is None:
            return PanelRow(period)
        if threshold == 0:
            return PanelRow(detail or "No encounter on the next step", emphasis="success")
        return PanelRow(f"{period} · about {min(threshold, 256) / 256:.0%} per step")


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
