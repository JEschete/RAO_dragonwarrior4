import ast
from pathlib import Path

from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import MapOverlay, MapWaypoint, RetroArchStatus

from game.adapter import Adapter
from game.battle import BATTLE_MEMORY_SIZE, BATTLE_TEXT_ADDRESS
from game.state import read_state


ROOT = Path(__file__).parents[1]


class FakeMemory:
    def __init__(self, ram: bytes, wram: bytes, battle: bytes | None = None) -> None:
        self.ram = ram
        self.wram = wram
        self.battle = battle

    def read_memory(self, address: int, size: int) -> bytes:
        if 0 <= address < len(self.ram):
            return self.ram[address:address + size]
        if address == 0x6000:
            return self.wram[:size]
        if address == 0x7200 and self.battle is not None:
            return self.battle[:size]
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
    ram[0x63:0x65] = bytes((0x04, 0x06))
    ram[0x44:0x46] = bytes((12, 9))
    wram = bytearray(0x300)
    wram[0x15A:0x15C] = bytes((4, 2))
    wram[0x16A:0x16E] = bytes((0, 7, 1, 7))
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
        "journey": "goals",
        "party": "party",
        "nearby-features": "area",
        "combat-log": "goals",
        "retroachievements": "goals",
        "dialogue-journal": "area",
        "atlas-confidence": "area",
    }
    assert all(section.compact_rows or section.rows for section in snapshot.sections)


def test_content_lifecycle_resets_session_services(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    adapter = Adapter(context)
    adapter.snapshot(memory())
    first_playthrough = adapter.playthrough_id

    adapter.deactivate()
    assert adapter.playthrough_id == ""
    assert adapter._last_ram is None
    assert adapter.dialogue_journal.path is None

    adapter.activate(("nes", "Dragon Warrior IV", "rom-hash"))
    adapter.snapshot(memory())
    assert adapter.playthrough_id == first_playthrough
    assert not (tmp_path / "dashboard").exists()


def test_snapshot_composes_live_floor_party_and_reference_sections(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )

    snapshot = Adapter(context).snapshot(memory())

    assert snapshot.location == "Endor - Castle, F2 (throne room) · (12,9)"
    assert snapshot.map_position is not None
    assert snapshot.map_position.map_id == 0x0406
    assert snapshot.map_position.area == "Dungeon / town"
    assert not snapshot.map_position.is_world
    assert tuple(section.title for section in snapshot.sections) == (
        "Journey",
        "Party",
        "Nearby features",
        "Combat log",
        "RetroAchievements",
        "Dialogue journal",
        "Atlas & memory",
    )
    journey = snapshot.sections[0]
    assert any(row.text.startswith("Gold 0 · Casino coins 0") for row in journey.rows)
    assert [action.key for action in journey.actions] == ["return-list"]
    assert "Lv" in snapshot.sections[1].rows[0].text
    party_action = snapshot.sections[1].actions[0]
    assert party_action.title == "Party Equipment, Stats, and Spells"
    assert "STR 18" in party_action.rows[0].text
    assert party_action.rows[1].text == "Equipped: Weapon: Cypress Stick"
    assert party_action.rows[2].text == "Carried: Medical Herb"
    assert party_action.rows[3].text == "Battle spells: Blaze"
    assert party_action.rows[5].text == "Experience: 0"
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
    assert section.rows[0].text == "1/43 unlocked · 5/360 points"
    assert section.rows[1].text == "Account: Jude"
    assert section.actions[0].rows[0].caught is True


def test_dialogue_journal_records_and_appears_in_overlay(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    game_memory = memory()
    ram = bytearray(game_memory.ram)
    ram[0x6AA:0x6AF] = bytes((0x2C, 0x0F, 0x16, 0x16, 0x19))
    game_memory.ram = bytes(ram)
    adapter = Adapter(context)

    on_screen = adapter.snapshot(game_memory)
    ram[0x6AA:0x6AF] = bytes(5)
    game_memory.ram = bytes(ram)
    after = adapter.snapshot(game_memory)

    assert adapter.dialogue_journal.entries[0].text == "Hello"
    assert adapter.dialogue_journal.path is not None
    assert adapter.dialogue_journal.path.is_file()
    assert adapter.dialogue_journal.path.parent.parent == tmp_path / "playthroughs"
    journal = {section.key: section for section in on_screen.sections}["dialogue-journal"]
    assert journal.rows[0].text == "Hello"
    journal = {section.key: section for section in after.sections}["dialogue-journal"]
    assert journal.rows[0].text == "No dialogue on screen"
    assert journal.actions[0].rows[0].text.endswith(": Hello")


def test_adapter_checkpoints_combat_after_one_coherent_sample(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory = memory()
    game_memory.battle = bytes(battle)
    adapter = Adapter(context)

    snapshot = adapter.snapshot(game_memory)

    assert adapter.encounter_log.active_document is not None
    assert adapter.encounter_log.active_path is not None
    assert adapter.encounter_log.active_path.is_file()
    assert snapshot.sections[0].title == "Battle"
    assert "ATK 14" in snapshot.sections[0].rows[0].text
    assert "Highest observed ATK" in snapshot.sections[0].actions[0].rows[0].text


def test_snapshot_resolves_monster_name_from_battle_introduction(tmp_path: Path) -> None:
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
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory.battle = bytes(battle)

    snapshot = Adapter(context).snapshot(game_memory)

    assert snapshot.sections[0].rows[0].text.startswith("Giant Worm · HP 45")


def test_persistence_is_scoped_by_configured_save_path(tmp_path: Path) -> None:
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

    assert first.playthrough_id.startswith("slot-one-")
    assert second.playthrough_id.startswith("slot-two-")
    assert first.playthrough_id != second.playthrough_id
    assert first.encounter_log.root != second.encounter_log.root


def test_high_frequency_capture_records_flow_between_snapshots(tmp_path: Path) -> None:
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
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory.battle = bytes(battle)
    ram = bytearray(game_memory.ram)
    ram[0x440:0x442] = bytes((0x03, 0xFF))
    introduction = encoded_text("Giant Worm appears.")
    ram[BATTLE_TEXT_ADDRESS:BATTLE_TEXT_ADDRESS + len(introduction)] = introduction
    game_memory.ram = bytes(ram)

    adapter.capture(game_memory)
    battle[0x7E:0x80] = (30).to_bytes(2, "little")
    game_memory.battle = bytes(battle)
    adapter.capture(game_memory)

    timeline = adapter.encounter_log.active_document["timeline"]
    assert [frame["enemies"][0]["hp"] for frame in timeline] == [45, 30]
    assert adapter.encounter_log.active_document["enemies"][0]["label"] == "Giant Worm"


def test_memory_failure_returns_actionable_snapshot(tmp_path: Path) -> None:
    context = GameContext(
        settings={},
        repository_root=ROOT,
        state_directory=tmp_path,
    )

    snapshot = Adapter(context).snapshot(FakeMemory(bytes(4), bytes(4)))

    assert snapshot.location == "Memory unavailable"
    assert snapshot.sections[0].alert
    assert "system RAM" in snapshot.sections[0].rows[0].text


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
    ram[0x63:0x65] = bytes((0x04, 0x06))
    ram[0x42:0x44] = bytes((20, 15))
    game_memory.ram = bytes(ram)

    snapshot = Adapter(context).snapshot(game_memory)

    assert snapshot.location == "Main World · (20,15)"
    assert snapshot.map_position is not None
    assert snapshot.map_position.area == "World"
    assert snapshot.map_position.is_world
    nearby = {section.key: section for section in snapshot.sections}["nearby-features"]
    assert nearby.rows[0].text == "Outdoor features are not mapped"


def test_nearby_features_are_sorted_by_distance_with_direction() -> None:
    adapter = Adapter(GameContext(settings={}, repository_root=ROOT))
    state = read_state(memory().ram, memory().wram)
    overlay = MapOverlay(
        "area-04-06",
        (
            MapWaypoint(20, 9, "Far chest", "Available", "collectibles"),
            MapWaypoint(12, 7, "Stairs", "ROM tile behavior $08", "entrance"),
            MapWaypoint(13, 9, "Villager", "Observed dialogue", "npcs"),
            MapWaypoint(11, 10, "Looted chest", "Looted", "collectibles", True),
        ),
    )

    section = adapter._nearby_section(state, (overlay,))

    assert [row.text for row in section.rows] == [
        "Looted chest · (11,10) · 2 south-west",
        "Stairs · (12,7) · 2 north",
        "Far chest · (20,9) · 8 east",
    ]
    assert section.rows[0].caught is True
    assert section.compact_rows[0].text.startswith("3 features · nearest: Looted chest")


def test_combat_log_section_summarizes_recorded_battles(tmp_path: Path) -> None:
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

    combat = {section.key: section for section in snapshot.sections}["combat-log"]
    assert combat.rows[0].text.startswith("1 lifetime · 1 this session")
    assert combat.actions[0].key == "recent-combats"
    assert "Endor - Castle, F2 (throne room)" in combat.actions[0].rows[0].text
