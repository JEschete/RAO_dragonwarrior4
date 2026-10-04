import ast
from dataclasses import replace
from unittest.mock import Mock
from pathlib import Path

from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import RetroArchStatus, MapDocument, MapLayer, MapOverlay, MapWaypoint, PanelRow

from game.adapter import STALE_SNAPSHOT_LIMIT, Adapter
from game.battle import BATTLE_MEMORY_SIZE, BATTLE_TEXT_ADDRESS, read_battle_state
from game.state import read_state


ROOT = Path(__file__).parents[1]


def _monster(name: str = "Raw profile", **values) -> Mock:
    fields = dict(max_hp=8, max_mp=0, attack=9, defense=4, agility=3, experience=1, gold=2,
                  drop_item_id=None, drop_denominator=None, resistances=())
    fields.update(values)
    monster = Mock(**fields)
    monster.name = name
    return monster


def test_current_catalogs_keep_boss_display_identity_separate_from_phase_stats() -> None:
    assets = Mock()
    assets.region = "US"
    assets.monster_name.side_effect = lambda identity: "Necrosaro" if identity == 0xAE else "Raw profile"
    assets.monster_definition.return_value = _monster(max_hp=1200, max_mp=255, attack=180, defense=140, agility=80)
    adapter = Adapter(GameContext(repository_root=ROOT), assets)
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[6:10] = bytes((0xD2, 255, 255, 255))
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 0xC0, 0, 0, 0, 30, 0, 3, 0))
    state = read_battle_state(bytes(0x800), bytes(battle), assets.monster_name,
                              setup_monster_ids=bytes((0xAE, 255, 255, 255)))
    section = adapter._bestiary_section(state)
    assert section.rows[0].text == "Necrosaro"
    assert [chip.text for chip in section.rows[0].chips] == ["HP 1,200", "MP unlimited"]
    assert section.compact_rows == section.rows and section.priority < 5
    knowledge = adapter._ai_knowledge_section(read_state(bytes(0x800), bytes(0x300)), state)
    assert "Necrosaro" in knowledge.rows[1].text
    assert "$" not in knowledge.rows[1].text


def test_bestiary_cards_group_stats_rewards_and_spell_resistances() -> None:
    assets = Mock()
    assets.region = "US"
    assets.indexed_name.return_value = "Medical Herb"
    assets.monster_definition.side_effect = lambda identity: _monster(
        f"Monster {identity}", drop_item_id=0x53, drop_denominator=32,
        resistances=(("Blaze", "Susceptible"), ("Icebolt", "Susceptible"), ("Bang", "Susceptible"),
                     ("Sleep", "Strong resistance"), ("Beat", "Immune")))
    adapter = Adapter(GameContext(repository_root=ROOT), assets)
    from game.battle import BattleState
    section = adapter._bestiary_section(BattleState.unavailable(), (3, 7))
    assert [row.text for row in section.rows] == ["Monster 3", "Monster 7"]
    assert [chip.text for chip in section.rows[0].chips] == ["HP 8", "MP 0"]
    assert section.rows[0].detail.splitlines() == [
        "ATK 9 · DEF 4 · AGI 3",
        "1 XP · 2 G",
        "Drops Medical Herb (1 in 32)",
        "Vulnerable: Blaze, Icebolt, Bang",
        "Strongly resists: Sleep",
        "Immune: Beat",
    ]
    assert section.compact_rows[0].text == "2 monsters in this area"
    assert len(section.actions[0].rows) == 214
    assert section.actions[0].rows == tuple(sorted(section.actions[0].rows, key=lambda row: row.text.casefold()))
    assert len(adapter._bestiary_section(BattleState.unavailable(), (3, 3, 7)).rows) == 2
    assert adapter._bestiary_section(BattleState.unavailable()).compact_rows[0].text == "No monsters in this area"


def test_medal_pickups_do_not_depend_on_the_exchange_balance() -> None:
    from game.rom_assets import CollectibleDefinition
    assets = Mock()
    assets.collectible_catalog.return_value = (CollectibleDefinition(0, 0x80, 0x69, "Small Medal"),)
    adapter = Adapter(GameContext(repository_root=ROOT), assets)
    state = replace(read_state(bytes(0x800), bytes(0x300)), treasure_flags=bytes((0x80,)) + bytes(26), small_medals=0)
    first = adapter._collection_section(state)
    second = adapter._collection_section(replace(state, small_medals=20))
    assert first.rows[1].text == second.rows[1].text == "Small medals found 1/1"
    assert second.rows[2].text == "Small medals: 0 carried · 20 with the Medal King"
    assert len(first.rows) == 3


def test_rail_has_no_name_cache_or_diagnostic_sections(tmp_path: Path) -> None:
    assets = Mock()
    assets.region = "US"
    assets.diagnostics = ("Skipped a hidden reward record",)
    assets.spell_milestones.return_value = ()
    assets.collectible_catalog.return_value = ()
    assets.encounter_pool.return_value = None
    assets.indoor_encounter_pool.return_value = None
    assets.has_area.return_value = True
    assets.feature_overlay.return_value = None
    assets.tile_transition_routes.return_value = ()
    assets.conditional_search_overlay.return_value = None
    assets.town_shops.return_value = ()
    assets.monster_definition.return_value = None
    assets.return_destinations.return_value = ()
    adapter = Adapter(GameContext(repository_root=ROOT, state_directory=tmp_path), assets,
                      asset_error="Configure a Dragon Warrior IV ROM in Plugin Manager")
    snapshot = adapter.snapshot(memory())
    keys = {section.key for section in snapshot.sections}
    assert not {"name-cache", "capabilities", "exit-routes"} & keys
    assert not hasattr(adapter, "reset_name_cache")
    assert not hasattr(adapter, "_monster_names")
    setup = next(section for section in snapshot.sections if section.key == "rom-setup")
    assert setup.alert and "Configure" in setup.rows[0].text
    assert list(tmp_path.iterdir()) == []


def test_rail_text_carries_no_decoder_language(tmp_path: Path) -> None:
    snapshot = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path)).snapshot(memory())
    texts = [snapshot.location]
    for section in snapshot.sections:
        rows = (*section.rows, *section.compact_rows, *(row for column in section.columns for row in column.rows),
                *(row for action in section.actions for row in action.rows))
        texts.extend((section.title, *(action.label for action in section.actions)))
        texts.extend(part for row in rows for part in (row.text, row.detail, row.tooltip))
    joined = "\n".join(texts).casefold()
    for word in ("native", "not certified", "not verified", "unavailable:", "rng", "$"):
        assert word not in joined


def test_random_encounter_suppression_replaces_the_pool_with_one_plain_row() -> None:
    adapter = Adapter(GameContext(repository_root=ROOT))
    initial = memory()
    ram, wram = bytearray(initial.ram), bytearray(initial.wram)
    ram[0x515] = 2
    snapshot = adapter.snapshot(FakeMemory(bytes(ram), bytes(wram)))
    section = next(section for section in snapshot.sections if section.key == "encounter-pool")
    assert [row.text for row in section.rows] == ["No random encounters while flying"]
    ram[0x515] = 0
    wram[0x288] = 0x80
    snapshot = adapter.snapshot(FakeMemory(bytes(ram), bytes(wram)))
    section = next(section for section in snapshot.sections if section.key == "encounter-pool")
    assert [row.text for row in section.rows] == ["No random encounters right now"]
    wram[0x288] = 0
    ram[0x58E] = 2
    snapshot = adapter.snapshot(FakeMemory(bytes(ram), bytes(wram)))
    section = next(section for section in snapshot.sections if section.key == "encounter-pool")
    assert [row.text for row in section.rows] == ["No random encounters right now"]


class FakeMemory:
    def __init__(
        self,
        ram: bytes,
        wram: bytes,
        battle: bytes | None = None,
        entities: bytes | None = None,
    ) -> None:
        self.ram = ram
        self.wram = wram
        self.battle = battle if battle is not None else bytes(BATTLE_MEMORY_SIZE)
        self.entities = entities
        self.context_flags = 0
        self.thresholds: bytes | None = None
        self.room_classes = bytes(32)
        self.arena_flags = 0
        self.arena_wager = bytes(3)
        self.arena_odds: bytes | None = None
        self.arena_selection = 0
        self.encounter_timing: bytes | None = None
        self.scent_count = 0

    def read_memory(self, address: int, size: int) -> bytes:
        if 0 <= address < len(self.ram):
            return self.ram[address:address + size]
        if 0x6000 <= address < 0x6000 + len(self.wram):
            return self.wram[address - 0x6000:address - 0x6000 + size]
        if address == 0x6BDE:
            return bytes((self.context_flags,))[:size]
        if address == 0x7200 and self.battle is not None:
            return self.battle[:size]
        if address == 0x6F60 and self.entities is not None:
            return self.entities[:size]
        if address == 0x7140:
            return self.room_classes[:size]
        if address == 0x6E19 and self.thresholds is not None:
            return self.thresholds[:size]
        if address == 0x72E9:
            return bytes((self.arena_flags,))[:size]
        if address == 0x6E83:
            return self.arena_wager[:size]
        if address == 0x6E39 and self.arena_odds is not None:
            return self.arena_odds[:size]
        if address == 0x6E7F:
            return bytes((self.arena_selection,))[:size]
        if address == 0x6E41 and self.encounter_timing is not None:
            return self.encounter_timing[:size]
        if address == 0x6BEB:
            return bytes((self.scent_count,))[:size]
        raise RuntimeError(f"Unexpected read at {address:#x}")


def encoded_text(value: str) -> bytes:
    return bytes(
        0
        if character == " "
        else ord(character) - ord("a") + 0x0B
        if character.islower()
        else ord(character) - ord("A") + 0x25
        if character.isupper()
        else 0x78
        if character == "."
        else 0x6E
        for character in value
    )


def memory() -> FakeMemory:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x28] = 0x0E
    ram[0x41] = 0x80
    ram[0x63:0x65] = bytes((0x04, 0x06))
    ram[0x44:0x46] = bytes((12, 9))
    wram = bytearray(0x300)
    wram[0x15A:0x15C] = bytes((4, 2))
    wram[0x16A:0x16E] = bytes((0x80, 0x87, 0x81, 0))
    wram[1] = 0x80
    wram[2:4] = (40).to_bytes(2, "little")
    wram[13:15] = (50).to_bytes(2, "little")
    wram[7:12] = bytes((18, 21, 24, 27, 30))
    wram[20:28] = bytes((0x80, 0x53) + (0xFF,) * 6)
    wram[28] = 0b00000100
    wram[0x2ED] = 0x84
    return FakeMemory(bytes(ram), bytes(wram))


def test_every_panel_section_and_action_declares_a_stable_key() -> None:
    path = ROOT / "game" / "adapter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    missing = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in {"PanelSection", "PanelAction"}:
            continue
        if not any(keyword.arg == "key" for keyword in node.keywords):
            missing.append((node.func.id, node.lineno))

    assert missing == []


def test_snapshot_has_unique_shared_qt_roles_and_identities(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )

    snapshot = Adapter(context).snapshot(memory())

    section_keys = [section.key for section in snapshot.sections]
    assert len(section_keys) == len(set(section_keys))
    assert all(section_keys)
    assert all(
        action.key
        for section in snapshot.sections
        for action in section.actions
    )
    assert {section.key: section.role for section in snapshot.sections} == {
        "combatants": "urgent",
        "journey": "goals",
        "retroachievements": "goals",
        "guide": "context",
    }
    assert all(section.compact_rows or section.rows or section.columns or section.markdown
               for section in snapshot.sections)


def test_content_lifecycle_resets_session_services(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    adapter = Adapter(context)
    adapter.snapshot(memory())
    assert adapter._monster_name(3) is None

    adapter.deactivate()
    assert adapter._content_key is None
    assert not hasattr(adapter, "_monster_names")

    adapter.activate(("nes", "Dragon Warrior IV", "rom-hash"))
    adapter.snapshot(memory())
    assert adapter._content_key == ("nes", "Dragon Warrior IV", "rom-hash")
    assert not (tmp_path / "dashboard").exists()


def test_snapshot_composes_live_floor_party_and_reference_sections(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )

    snapshot = Adapter(context).snapshot(memory())

    assert snapshot.location == "Endor - Castle, F2 (throne room)"
    assert snapshot.map_position is not None
    assert snapshot.map_position.map_id == 0x0406
    assert snapshot.map_position.area == "Dungeon / town"
    assert not snapshot.map_position.is_world
    assert tuple(section.title for section in snapshot.sections) == (
        "Combatants",
        "Journey",
        "RetroAchievements",
        "Guide",
    )
    journey = snapshot.sections[1]
    assert [row.text for row in journey.rows] == ["Chapter 5 · Hero", "Night", "Gold 0"]
    assert journey.actions == ()
    combatants = snapshot.sections[0]
    assert not combatants.collapsible
    assert combatants.actions == ()
    assert [column.key for column in combatants.columns] == ["party"]
    assert "Lv" in combatants.columns[0].rows[0].text
    assert tuple(meter.label for meter in combatants.columns[0].rows[0].meters) == ("HP", "MP")
    assert [row.text.split(" · ")[0] for row in combatants.columns[0].rows] == ["Hero", "Alena", "Cristo"]
    assert snapshot.sections[3].markdown.startswith("# Dragon Warrior IV Unified Walkthrough")
    assert snapshot.display_spec is not None
    assert snapshot.display_spec.layout_key == "nes-4-3"


def test_snapshot_presents_retroachievements_progress(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
        ra_progress_provider=lambda _: RAProgress("Jude", frozenset({52318})),
    )

    snapshot = Adapter(context).snapshot(memory())

    section = next(
        value for value in snapshot.sections if value.title == "RetroAchievements"
    )
    assert [row.text for row in section.rows] == ["1/43 unlocked · 5/360 points"]
    assert section.actions[0].rows[0].caught is True
    assert section.actions[0].rows[0].detail == "Help Flora find her missing husband"


def test_live_enemy_panel_never_records_encounters(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[7] = 0x03
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory = memory()
    game_memory.battle = bytes(battle)
    game_memory.context_flags = 0x80
    adapter = Adapter(context)

    snapshot = adapter.snapshot(game_memory)

    assert snapshot.sections[0].key == "combatants"
    assert len(snapshot.sections[0].columns[1].rows) == 1
    assert not hasattr(adapter, "encounter_log")
    assert not hasattr(adapter, "combat_analytics")
    assert not hasattr(adapter, "capture")
    assert list(tmp_path.rglob("*.json")) == []


def test_snapshot_does_not_learn_names_from_battle_introduction(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    game_memory = memory()
    ram = bytearray(game_memory.ram)
    ram[0x440:0x442] = bytes((0x03, 0xFF))
    introduction = encoded_text("Giant Worm appears.")
    ram[BATTLE_TEXT_ADDRESS:BATTLE_TEXT_ADDRESS + len(introduction)] = introduction
    game_memory.ram = bytes(ram)
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[7] = 0x03
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory.battle = bytes(battle)
    game_memory.context_flags = 0x80

    snapshot = Adapter(context).snapshot(game_memory)

    assert snapshot.sections[0].columns[1].rows[0].text.startswith("Unknown enemy · HP 45")
    assets = Mock()
    assets.monster_name.return_value = "Giant Worm"
    assert Adapter(context, assets)._monster_name(3) == "Giant Worm"


def test_configured_save_paths_do_not_create_combat_archives(tmp_path: Path) -> None:
    first = Adapter(
        GameContext(
            settings={"save_path": tmp_path / "slot-one.sav"},
            repository_root=ROOT,
            state_directory=tmp_path,
        )
    )
    second = Adapter(
        GameContext(
            settings={"save_path": tmp_path / "slot-two.sav"},
            repository_root=ROOT,
            state_directory=tmp_path,
        )
    )

    first.snapshot(memory())
    second.snapshot(memory())

    assert list(tmp_path.iterdir()) == []


def test_field_context_clears_enemy_panel_without_losing_player_party(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    game_memory = memory()
    game_memory.battle = bytes(BATTLE_MEMORY_SIZE)
    adapter = Adapter(context)
    adapter.snapshot(game_memory)
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[7] = 0x03
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory.battle = bytes(battle)
    ram = bytearray(game_memory.ram)
    ram[0x440:0x442] = bytes((0x03, 0xFF))
    introduction = encoded_text("Giant Worm appears.")
    ram[BATTLE_TEXT_ADDRESS:BATTLE_TEXT_ADDRESS + len(introduction)] = introduction
    game_memory.ram = bytes(ram)

    game_memory.context_flags = 0x80
    first = adapter.snapshot(game_memory)
    battle[0x7E:0x80] = (30).to_bytes(2, "little")
    game_memory.battle = bytes(battle)
    game_memory.context_flags = 0
    field = adapter.snapshot(game_memory)
    assert len(first.sections[0].columns[1].rows) == 1
    assert [column.key for column in field.sections[0].columns] == ["party"]
    assert field.sections[0].columns[0].rows == first.sections[0].columns[0].rows
    assert list(tmp_path.rglob("*.json")) == []


def test_memory_failure_returns_actionable_snapshot(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )

    snapshot = Adapter(context).snapshot(FakeMemory(bytes(4), bytes(4)))

    assert snapshot.location == "Waiting for game"
    assert snapshot.sections[0].alert
    assert "system RAM" in snapshot.sections[0].rows[0].text


def test_uninitialized_memory_does_not_invent_journey_or_party(tmp_path: Path) -> None:
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path))
    snapshot = adapter.snapshot(FakeMemory(bytes(0x800), bytes(0x300)))
    assert {section.key for section in snapshot.sections} == {"memory-access", "guide"}
    assert "saved game" in snapshot.sections[0].rows[0].text


def test_running_rom_mismatch_disables_exact_overlay_data(tmp_path: Path) -> None:
    assets = Mock(content_hash="configured-rom-hash")
    context = GameContext(settings={"rom_path": tmp_path / "configured.nes"}, repository_root=ROOT)
    adapter = Adapter(context, assets)
    resolver = Mock()
    resolver.resolve.return_value = "different-running-rom-hash"
    adapter._content_resolver = resolver
    adapter.activate(("Mesen", "Dragon Warrior IV", "12345678"))
    snapshot = adapter.snapshot(memory())
    assert snapshot.map_position is None
    assert "does not match" in snapshot.sections[0].rows[0].text
    assert {section.key for section in snapshot.sections} == {"memory-access", "guide"}


def test_supports_common_nes_cores_and_dw4_content() -> None:
    adapter = Adapter(
        GameContext(settings={}, repository_root=ROOT)
    )

    assert adapter.supports(
        RetroArchStatus("PLAYING", "Nintendo - NES / Famicom (Mesen)", "Dragon Warrior 4.nes")
    )
    assert not adapter.supports(
        RetroArchStatus("PLAYING", "SwanStation", "Dragon Warrior 4.bin")
    )


def test_outdoor_location_uses_main_world_layer(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    game_memory = memory()
    ram = bytearray(game_memory.ram)
    ram[0x28] = 0x00
    ram[0x41] = 0
    ram[0x63:0x65] = bytes((0x04, 0x06))
    ram[0x42:0x44] = bytes((20, 15))
    game_memory.ram = bytes(ram)

    snapshot = Adapter(context).snapshot(game_memory)

    assert snapshot.location == "Main World"
    assert snapshot.map_position is not None
    assert snapshot.map_position.area == "World"
    assert snapshot.map_position.is_world


def test_snapshot_maps_only_visible_live_entities(tmp_path: Path) -> None:
    context = GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path)
    game_memory = memory()
    entities = bytearray(0x1A0)
    entities[0xC6:0xE0] = bytes((0xFF,)) * 26
    entities[0xC6] = 0x02
    entities[0xC8] = 0x83
    entities[6] = 11
    entities[8] = 22
    entities[0x26] = 7
    entities[0x28] = 9
    entities[0x86] = 0x2A
    entities[0xE6] = 0x11
    entities[0x186] = 0x40
    game_memory.entities = bytes(entities)
    assets = Mock()
    assets.spell_milestones.return_value = ()
    assets.diagnostics = ()
    assets.collectible_catalog.return_value = ()
    assets.encounter_pool.return_value = None
    assets.indoor_encounter_pool.return_value = None
    assets.has_area.return_value = True
    assets.feature_overlay.return_value = None
    assets.tile_transition_routes.return_value = ()
    assets.conditional_search_overlay.return_value = None
    assets.town_shops.return_value = ()
    assets.descriptor.return_value = Mock(width=20, height=15)
    assets.map_actor_roles.return_value = (("Weapon merchant", "shop"), ("NPC", "npc"), ("NPC", "npc"))

    adapter = Adapter(context, assets)
    snapshot = adapter.snapshot(game_memory)

    entity_overlay = next(
        overlay for overlay in snapshot.map_overlays if overlay.layer_key == "area-04-06"
    )
    entity = next(point for point in entity_overlay.waypoints if point.kind == "services")
    assert (entity.x, entity.y, entity.marker) == (11, 7, "shop")
    assert entity.title == "Weapon merchant"
    assert "facing" not in entity.detail
    assert {(point.x, point.y) for point in entity_overlay.waypoints} == {
        (11, 7),
    }
    from game.rom_assets import ExitRoute
    assets.feature_overlay.return_value = MapOverlay("area-04-06", (MapWaypoint(3, 4, "Stairs", "", "entrance", marker="stairs-up"),))
    assets.tile_transition_routes.return_value = (ExitRoute(0x406, 0x407, 3, 4, 1, 1, 8, 9),)
    routed = adapter.snapshot(game_memory)
    marker = next(point for overlay in routed.map_overlays for point in overlay.waypoints if point.title == "Stairs")
    assert marker.detail.startswith("Leads to ") and "(8,9)" not in marker.detail
    assert assets.feature_overlay.call_args.kwargs["position"] == (12, 9)
    ram = bytearray(game_memory.ram)
    ram[0x41] = 0
    game_memory.ram = bytes(ram)
    assert adapter.snapshot(game_memory).map_overlays == ()


def test_completed_battle_has_no_legacy_party_or_combat_log_controls(tmp_path: Path) -> None:
    context = GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path)
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory = memory()
    game_memory.battle = bytes(battle)
    adapter = Adapter(context)
    adapter.snapshot(game_memory)
    battle[1:3] = (12).to_bytes(2, "little")
    battle[0x7E:0x80] = bytes(2)
    game_memory.battle = bytes(battle)
    adapter.snapshot(game_memory)
    game_memory.battle = bytes(BATTLE_MEMORY_SIZE)

    snapshot = adapter.snapshot(game_memory)

    assert not {"party", "battle", "combat-log"}.intersection(section.key for section in snapshot.sections)
    assert not {"party-details", "recent-combats"}.intersection(
        action.key for section in snapshot.sections for action in section.actions
    )
    assert list(tmp_path.rglob("*.json")) == []


def test_town_stock_compares_recruited_reserves_and_clears_on_world_return(tmp_path: Path) -> None:
    assets = Mock()
    assets.diagnostics = ()
    assets.spell_milestones.return_value = ()
    assets.collectible_catalog.return_value = ()
    assets.encounter_pool.return_value = None
    assets.indoor_encounter_pool.return_value = None
    assets.has_area.return_value = True
    assets.feature_overlay.return_value = None
    assets.tile_transition_routes.return_value = ()
    assets.conditional_search_overlay.return_value = None
    assets.town_shops.return_value = ((0, 1, (2,)),)
    assets.indexed_name.return_value = "Copper Sword"
    assets.item_price.return_value = 100
    assets.equipment_traits.return_value = (0, 0, 0)
    assets.equipment_protection.return_value = ()
    assets.equipment_passives.return_value = ()
    assets.equipment_eligible.return_value = True
    assets.equipment_bonus.side_effect = lambda item_id: 12 if item_id == 2 else 2
    game_memory = memory()
    wram = bytearray(game_memory.wram)
    wram[0x172] = 0x86
    reserve = 1 + 6 * 30
    wram[reserve + 6] = 30
    wram[reserve + 19:reserve + 27] = bytes((0x80,)) + bytes((0xFF,)) * 7
    game_memory.wram = bytes(wram)
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path), assets)
    snapshot = adapter.snapshot(game_memory)
    shop = next(section for section in snapshot.sections if section.key == "town-shops")
    assert shop.collapsible
    ragnar = next(row for row in shop.rows if "Ragnar" in row.text)
    assert "ATK 32 to 42" in ragnar.text and ragnar.emphasis == "success"
    assert ragnar.chips[0].text == "+10 ATK"
    hero = next(row for row in shop.rows if row.text.startswith("▲ Hero"))
    assert "ATK 20 to 30" in hero.text and hero.chips[0].text == "+10 ATK"
    # Closed, the section still names every upgrade the shop offers.
    assert len(shop.compact_rows) == 1
    assert shop.compact_rows[0].text.startswith("Copper Sword · 100 G · ")
    assert "Ragnar +10 ATK" in shop.compact_rows[0].text and "Hero +10 ATK" in shop.compact_rows[0].text
    assert not any("availability" in row.text or "Not equippable" in row.text for row in shop.rows)
    assert shop.rows[0].emphasis == "heading" and shop.rows[1].emphasis == ""
    local_state = read_state(game_memory.ram, game_memory.wram, assets)
    local_state = replace(local_state, location=replace(local_state.location, submap=0))
    assert adapter._shop_section(local_state, bytes(3)).rows[0].text == "Weapon shop"
    assert [action.label for action in shop.actions] == ["Track Copper Sword"]
    shop.actions[0].command()
    wram[0x157:0x15A] = (40).to_bytes(3, "little")
    game_memory.wram = bytes(wram)
    target = next(section for section in adapter.snapshot(game_memory).sections if section.key == "economy-target")
    assert target.rows[1].text == "60 G to go"
    assert target.rows[1].progress == 0.4
    assert target.compact_rows[0].text == "Copper Sword · 60 G to go" and target.compact_rows[0].progress == 0.4
    wram[0x157:0x15A] = (500).to_bytes(3, "little")
    game_memory.wram = bytes(wram)
    affordable = next(section for section in adapter.snapshot(game_memory).sections if section.key == "town-shops")
    assert affordable.actions == () and affordable.rows[1].chips[0].text == "Can afford"
    wram[0x157:0x15A] = (40).to_bytes(3, "little")
    game_memory.wram = bytes(wram)
    ram = bytearray(game_memory.ram)
    ram[0x28] = 0
    ram[0x41] = 0
    game_memory.ram = bytes(ram)
    world_snapshot = adapter.snapshot(game_memory)
    assert "town-shops" not in {section.key for section in world_snapshot.sections}
    target = next(section for section in world_snapshot.sections if section.key == "economy-target")
    target.actions[0].command()
    assert "economy-target" not in {section.key for section in adapter.snapshot(game_memory).sections}


def test_native_xp_thresholds_use_hero_slot_for_alternate_record_and_skip_level_cap(tmp_path: Path) -> None:
    game_memory = memory()
    wram = bytearray(game_memory.wram)
    wram[0x18E] = 0x40
    wram[0x186] = 0x88
    alternate = 1 + 8 * 30
    wram[alternate] = 0x80
    wram[alternate + 5] = 10
    wram[alternate + 16:alternate + 19] = (600).to_bytes(3, "little")
    game_memory.wram = bytes(wram)
    game_memory.thresholds = (900).to_bytes(3, "little") + bytes(24)
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path))
    snapshot = adapter.snapshot(game_memory)
    row = next(section for section in snapshot.sections if section.key == "combatants").columns[0].rows[0]
    assert "300 XP to next" in row.text
    wram[alternate + 5] = 99
    game_memory.wram = bytes(wram)
    snapshot = adapter.snapshot(game_memory)
    row = next(section for section in snapshot.sections if section.key == "combatants").columns[0].rows[0]
    assert "XP 600" in row.tooltip and "XP to next" not in row.text
    assert row.progress is None


def test_experience_bar_is_gold_and_only_drawn_when_the_rom_curve_matches_the_game(tmp_path: Path) -> None:
    game_memory = memory()
    wram = bytearray(game_memory.wram)
    wram[1 + 5] = 10
    wram[1 + 16:1 + 19] = (600).to_bytes(3, "little")
    game_memory.wram = bytes(wram)
    game_memory.thresholds = (900).to_bytes(3, "little") + bytes(24)
    assets = Mock()
    assets.region = "US"
    assets.diagnostics = ()
    assets.spell_milestones.return_value = ()
    assets.collectible_catalog.return_value = ()
    assets.indoor_encounter_pool.return_value = None
    assets.has_area.return_value = True
    assets.feature_overlay.return_value = None
    assets.tile_transition_routes.return_value = ()
    assets.conditional_search_overlay.return_value = None
    assets.town_shops.return_value = ()
    assets.monster_definition.return_value = None
    assets.return_destinations.return_value = ()
    assets.experience_threshold.side_effect = lambda growth, level: {10: 500, 11: 900}.get(level)
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path), assets)
    row = adapter.snapshot(game_memory).sections[0].columns[0].rows[0]
    assert row.progress == 0.25 and row.progress_color == "#d4a017"
    assert "300 XP to next" in row.text
    # A curve that disagrees with the game's own next-level value draws no bar.
    game_memory.thresholds = (950).to_bytes(3, "little") + bytes(24)
    assert adapter.snapshot(game_memory).sections[0].columns[0].rows[0].progress is None


def test_area_transition_keeps_the_last_snapshot_instead_of_dropping_the_map(tmp_path: Path) -> None:
    game_memory = memory()
    reader = Mock(wraps=game_memory)
    transition = lambda address, size: bytes((5, 6, 0)) if address == 0x63 else game_memory.read_memory(address, size)
    reader.read_memory.side_effect = transition
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path))
    discarded = adapter.snapshot(reader)
    assert discarded.map_position is None
    assert "finish loading" in discarded.sections[0].rows[0].text
    reader.read_memory.side_effect = game_memory.read_memory
    good = adapter.snapshot(reader)
    assert good.map_position is not None
    reader.read_memory.side_effect = transition
    for _ in range(STALE_SNAPSHOT_LIMIT):
        assert adapter.snapshot(reader) is good
    assert adapter.snapshot(reader).map_position is None
    reader.read_memory.side_effect = game_memory.read_memory
    assert adapter.snapshot(reader).map_position is not None


def test_native_ai_training_catalog_is_distinct_from_unlocks_and_decision_accuracy(tmp_path: Path) -> None:
    game_memory = memory()
    wram = bytearray(game_memory.wram)
    wram[0x19B] = 0xE4
    game_memory.wram = bytes(wram)
    assets = Mock()
    assets.region = "US"
    assets.monster_name.side_effect = lambda identifier: f"Monster {identifier}"
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path), assets)
    state = read_state(game_memory.ram, game_memory.wram)
    from game.battle import BattleState
    section = adapter._ai_knowledge_section(state, BattleState.unavailable())
    assert section is not None
    catalog = section.actions[0].rows
    assert catalog[0].text == "Monster 0 · learned 0/3"
    assert catalog[3].text == "Monster 3 · learned 3/3" and catalog[3].progress == 1.0
    assert catalog[0].tooltip == ""
    assert [row.text for row in section.rows] == ["Tactics: Offensive"]
    assert len(catalog) == 214
    assert state.knowledge_rank(214) is None


def test_return_navigation_only_targets_present_unlocked_atlas_layers(tmp_path: Path) -> None:
    assets = Mock()
    assets.region = "US"
    assets.return_destinations.return_value = ((4, "Endor"), (5, "Unavailable floor"))
    document = MapDocument("Atlas", (MapLayer("area-04-00", "Endor", "Town", tmp_path / "map.png"),))
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path), assets, document)
    game_memory = memory()
    section = adapter._journey_section(read_state(game_memory.ram, game_memory.wram))
    assert len(section.actions) == 1
    assert section.actions[0].map_layer_key == "area-04-00"
    assert section.actions[0].key == "return-map-04"


def test_casino_stock_affordability_uses_native_coin_balance(tmp_path: Path) -> None:
    from dataclasses import replace
    assets = Mock()
    assets.town_shops.return_value = ((1, 3, (0x53,)),)
    assets.indexed_name.return_value = "Medical Herb"
    assets.item_price.return_value = 200
    game_memory = memory()
    state = read_state(game_memory.ram, game_memory.wram)
    state = replace(state, casino_coins=120, gold=10000,
                    location=replace(state.location, map_id=4, submap=1))
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path), assets)
    section = adapter._shop_section(state, bytes(3))
    assert section is not None
    item = next(row for row in section.rows if "Medical Herb" in row.text)
    assert item.text == "Medical Herb · 200 coins"
    assert item.chips[0].text == "Need 80 coins"
    assert item.progress == 0.6
    assert [row.text for row in section.rows] == ["Casino prizes", "Medical Herb · 200 coins"]


def test_native_arena_view_reads_three_byte_wager_and_clears_with_field_context(tmp_path: Path) -> None:
    game_memory = memory()
    ram = bytearray(game_memory.ram)
    ram[0x63:0x65] = bytes((4, 1))
    game_memory.ram = bytes(ram)
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 0xC0, 0, 0, 0, 30, 0, 3, 0))
    game_memory.battle = bytes(battle)
    game_memory.context_flags = 0x80
    game_memory.arena_flags = 0x80
    game_memory.arena_wager = (65536).to_bytes(3, "little")
    game_memory.arena_odds = bytes((2, 3, 4, 5, 1, 2, 3, 4))
    game_memory.arena_selection = 1
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path))
    snapshot = adapter.snapshot(game_memory)
    arena = next(section for section in snapshot.sections if section.key == "arena")
    assert [row.text for row in arena.rows] == [
        "Casino coins 0", "Bet 65,536 coins",
        "Entry 1 pays 2.1x", "Entry 2 pays 3.2x", "Entry 3 pays 4.3x", "Entry 4 pays 5.4x",
    ]
    assert [chip.text for chip in arena.rows[3].chips] == ["Your bet"]
    assert all(not row.tooltip for row in arena.rows)
    combatants = next(section for section in snapshot.sections if section.key == "combatants")
    assert combatants.columns[1].title == "Arena monsters"
    game_memory.context_flags = 0
    snapshot = adapter.snapshot(game_memory)
    assert not any(section.key == "arena" for section in snapshot.sections)
    assert [column.key for column in
            next(section for section in snapshot.sections if section.key == "combatants").columns] == ["party"]


def test_local_achievement_evidence_does_not_mark_server_unlocks(tmp_path: Path) -> None:
    from dataclasses import replace
    game_memory = memory()
    state = replace(read_state(game_memory.ram, game_memory.wram), casino_coins=10000, has_boat=True)
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path))
    section = adapter._achievement_section(state)
    roller = next(row for row in section.actions[0].rows if row.text.startswith("High Roller"))
    assert roller.detail == "Have at least 10,000 Casino coins\nNow: 10,000 of 10,000 coins"
    assert roller.tooltip == ""
    assert roller.caught is False


def test_world_encounter_zone_region_uses_native_grid_and_clears_indoors(tmp_path: Path) -> None:
    from dataclasses import replace
    assets = Mock()
    assets.region = "US"
    assets.has_area.return_value = True
    assets.feature_overlay.return_value = None
    assets.tile_transition_routes.return_value = ()
    assets.conditional_search_overlay.return_value = None
    assets.spell_milestones.return_value = ()
    assets.collectible_catalog.return_value = ()
    assets.monster_definition.return_value = None
    assets.return_destinations.return_value = ()
    assets.town_shops.return_value = ()
    assets.diagnostics = ()
    assets.encounter_pool.return_value = (7, (("Slime", 3),))
    assets.indoor_encounter_pool.return_value = None
    slime = _monster("Slime")
    assets.monster_definition.side_effect = lambda identity: slime if identity == 0 else None
    assets.indexed_name.return_value = "Medical Herb"
    assets.formation_chances.return_value = (
        Mock(label="Slime", monster_ids=(0,), chance=192, fixed_group=False),
        Mock(label="Slime x2 + Drakee", monster_ids=(0, 0, 1), chance=64, fixed_group=True),
    )
    assets.land_encounter_threshold.return_value = (16, "")
    assets.native_palette_frame.return_value = None
    layer = MapLayer("world", "World", "World", tmp_path / "map.png")
    assets.display_layers.side_effect = lambda layers, *args: layers
    game_memory = memory()
    ram = bytearray(game_memory.ram)
    ram[0x41] = 0
    ram[0x42:0x44] = bytes((20, 35))
    game_memory.ram = bytes(ram)
    game_memory.encounter_timing = bytes((0x82, 2))
    document = MapDocument("Atlas", (layer,))
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT, state_directory=tmp_path), assets, document)
    snapshot = adapter.snapshot(game_memory)
    region = snapshot.map_document.layers[0].regions[0]
    assert (region.x, region.y, region.width, region.height) == (16, 32, 16, 16)
    assert region.kind == "encounter-zone"
    assert region.title == "Encounter zone" and "zone 7" not in region.detail.casefold()
    assert region.label == region.compact_label == ""
    assert region.detail == "Slime · 75%\nSlime x2 + Drakee · 25%"
    encounter = next(section for section in snapshot.sections if section.key == "encounter-pool")
    assert [row.text for row in encounter.rows] == [
        "Night · about 6% per step", "Slime · 1 XP · 2 G each", "Slime x2 + Drakee"]
    assert [row.chips[0].text for row in encounter.rows[1:]] == ["75%", "25%"]
    assert encounter.rows[1].progress == 0.75
    assert encounter.compact_rows[0].text == "Slime 75% · Slime x2 + Drakee 25%"
    assets.land_encounter_threshold.assert_called_once_with(7, 0, game_memory.wram[0x2ED], 2, 0x82,
                                                           game_memory.wram[0x2D5], 0)
    assets.formation_chances.assert_called_once_with(7, 0x3FBE)
    bestiary = next(section for section in snapshot.sections if section.key == "bestiary")
    assert [row.text for row in bestiary.rows] == ["Slime"]
    assert bestiary.compact_rows[0].text == "1 monster in this area"
    assets.land_encounter_threshold.return_value = (0, "Repel is keeping monsters away")
    repelled = next(section for section in adapter.snapshot(game_memory).sections if section.key == "encounter-pool")
    assert repelled.rows[0].text == "Repel is keeping monsters away" and repelled.rows[0].emphasis == "success"
    assets.land_encounter_threshold.reset_mock()
    assets.land_encounter_threshold.return_value = (16, "")
    ram[0x41] = 0x80
    game_memory.ram = bytes(ram)
    snapshot = adapter.snapshot(game_memory)
    assert snapshot.map_document.layers[0].regions == ()
