from pathlib import Path

from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.models import RetroArchStatus

from game.adapter import Adapter
from game.battle import BATTLE_MEMORY_SIZE


ROOT = Path(__file__).parents[1]


class FakeMemory:
    def __init__(self, ram: bytes, wram: bytes, battle: bytes | None = None) -> None:
        self.ram = ram
        self.wram = wram
        self.battle = battle

    def read_memory(self, address: int, size: int) -> bytes:
        if address == 0:
            return self.ram[:size]
        if address == 0x6000:
            return self.wram[:size]
        if address == 0x7200 and self.battle is not None:
            return self.battle[:size]
        if address == 0x0440:
            return self.ram[address:address + size]
        raise RuntimeError(f"Unexpected read at {address:#x}")


def memory() -> FakeMemory:
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x63:0x65] = bytes((0x04, 0x06))
    ram[0x44:0x46] = bytes((12, 9))
    wram = bytearray(0x300)
    wram[0x15A:0x15C] = bytes((4, 2))
    wram[0x16A:0x16E] = bytes((0, 7, 1, 7))
    wram[1] = 0x80
    wram[2:4] = (40).to_bytes(2, "little")
    wram[13:15] = (50).to_bytes(2, "little")
    wram[0x2ED] = 0x84
    return FakeMemory(bytes(ram), bytes(wram))


def test_snapshot_composes_live_floor_party_and_reference_sections(tmp_path: Path) -> None:
    context = GameContext(
        settings={"dashboard": False},
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
        "Resources",
        "Atlas confidence",
    )
    assert "Lv" in snapshot.sections[1].rows[0].text
    assert snapshot.display_spec is not None
    assert snapshot.display_spec.layout_key == "nes-4-3"
    assert not (tmp_path / "dashboard").exists()


def test_dialogue_journal_records_even_when_dashboard_is_disabled(tmp_path: Path) -> None:
    context = GameContext(
        settings={"dashboard": False},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    game_memory = memory()
    ram = bytearray(game_memory.ram)
    ram[0x6AA:0x6AF] = bytes((0x2C, 0x0F, 0x16, 0x16, 0x19))
    game_memory.ram = bytes(ram)
    adapter = Adapter(context)

    adapter.snapshot(game_memory)
    ram[0x6AA:0x6AF] = bytes(5)
    game_memory.ram = bytes(ram)
    adapter.snapshot(game_memory)

    assert adapter.dialogue_journal.entries[0].text == "Hello"
    assert (tmp_path / "dashboard" / "dialogue-journal.json").is_file()


def test_adapter_checkpoints_combat_after_one_coherent_sample(tmp_path: Path) -> None:
    context = GameContext(
        settings={"dashboard": False},
        repository_root=ROOT,
        state_directory=tmp_path,
    )
    battle = bytearray(BATTLE_MEMORY_SIZE)
    battle[0x74:0x82] = bytes((8, 14, 0, 11, 0, 0, 2, 0, 0, 0, 45, 0, 6, 1))
    game_memory = memory()
    game_memory.battle = bytes(battle)
    adapter = Adapter(context)

    adapter.snapshot(game_memory)

    assert adapter.encounter_log.active_document is not None
    assert (tmp_path / "encounters" / "active.json").is_file()


def test_high_frequency_capture_records_flow_between_snapshots(tmp_path: Path) -> None:
    context = GameContext(
        settings={"dashboard": False},
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

    adapter.capture(game_memory)
    battle[0x7E:0x80] = (30).to_bytes(2, "little")
    game_memory.battle = bytes(battle)
    adapter.capture(game_memory)

    timeline = adapter.encounter_log.active_document["timeline"]
    assert [frame["enemies"][0]["hp"] for frame in timeline] == [45, 30]


def test_memory_failure_returns_actionable_snapshot(tmp_path: Path) -> None:
    context = GameContext(
        settings={"dashboard": False},
        repository_root=ROOT,
        state_directory=tmp_path,
    )

    snapshot = Adapter(context).snapshot(FakeMemory(bytes(4), bytes(4)))

    assert snapshot.location == "Memory unavailable"
    assert snapshot.sections[0].alert
    assert "system RAM" in snapshot.sections[0].rows[0].text


def test_supports_common_nes_cores_and_dw4_content() -> None:
    adapter = Adapter(
        GameContext(settings={"dashboard": False}, repository_root=ROOT)
    )

    assert adapter.supports(
        RetroArchStatus("PLAYING", "Nintendo - NES / Famicom (Mesen)", "Dragon Warrior 4.nes")
    )
    assert not adapter.supports(
        RetroArchStatus("PLAYING", "SwanStation", "Dragon Warrior 4.bin")
    )