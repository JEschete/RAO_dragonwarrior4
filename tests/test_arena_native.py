from pathlib import Path
from threading import Event

import pytest

from game.arena_native import ArenaSimulationError, NativeArena


@pytest.fixture
def prg() -> bytes:
    path = Path(__file__).parents[1] / "resources/DW4_Disassembly/build/arena/Dragon Warrior IV (USA).nes"
    if not path.is_file():
        pytest.skip("Build the local reference ROM to run native arena checks")
    return path.read_bytes()[16:]


def workspace(entries=(0, 0, 0, 0)) -> bytes:
    result = bytearray(0x2000)
    result[0x16A] = 0x80
    result[0xE45:0xE49] = bytes(entries)
    return bytes(result)


def test_rng_hook_matches_actual_rom_execution_including_adc_flags(prg: bytes) -> None:
    for seed in range(32):
        actual = NativeArena(prg, bytes(0x800), workspace(), seed)
        hooked = NativeArena(prg, bytes(0x800), workspace(), seed)
        actual.cpu.pc = hooked.cpu.pc = 0xC891
        hooked._step()
        for _ in range(1000):
            if actual.cpu.pc == 0x6000:
                break
            actual.cpu.step()
        assert actual.cpu.pc == 0x6000
        assert (actual.cpu.a, actual.cpu.p & 0xC3) == (hooked.cpu.a, hooked.cpu.p & 0xC3)
        assert actual.memory[0x12:0x14] == hooked.memory[0x12:0x14]
        assert actual.memory[0x50D] == hooked.memory[0x50D]


def test_reference_slime_fight_loads_stats_and_produces_one_survivor(prg: bytes) -> None:
    machine = NativeArena(prg, bytes(0x800), workspace(), 1)
    result = machine.run()
    assert result in range(4)
    for slot in range(4):
        record = machine.memory[0x7274 + slot * 14:0x7282 + slot * 14]
        assert record[0:5] == [3, 9, 0, 5, 0]
        assert bool(record[10] | (record[11] << 8)) == (slot == result)


def test_special_actions_execute_and_native_overtime_is_a_draw(prg: bytes) -> None:
    machine = NativeArena(prg, bytes(0x800), workspace((41, 46, 46, 41)), 3)
    actions = set()
    step = machine._step

    def observe() -> None:
        if machine.memory[0x507] == 0x11 and machine.cpu.pc == 0x8CAA:
            pointer = machine.memory[0] | (machine.memory[1] << 8)
            actions.add((pointer - 0xA40A) // 2)
        step()

    machine._step = observe
    assert machine.run() is None
    assert machine.memory[0x6E81] == 10
    assert actions - {0x43}


def test_native_execution_can_be_cancelled_without_mutating_inputs(prg: bytes) -> None:
    ram, saved_workspace = bytes(0x800), workspace()
    machine = NativeArena(prg, ram, saved_workspace, 0)
    cancel = Event()
    cancel.set()
    with pytest.raises(ArenaSimulationError, match="cancelled"):
        machine.run(cancel=cancel)
    assert ram == bytes(0x800)
    assert saved_workspace == workspace()


@pytest.mark.parametrize("address, target", ((0xA32E, 0xA348), (0xA381, 0xA38C)))
@pytest.mark.parametrize("stack", (0, 1, 14, 127, 255))
def test_stat_workspace_blocks_match_actual_instructions_and_cycles(prg: bytes, address: int, target: int, stack: int) -> None:
    from random import Random

    raw = NativeArena(prg, bytes(0x800), workspace(), 1)
    fast = NativeArena(prg, bytes(0x800), workspace(), 1)
    random = Random(stack)
    ram = [random.randrange(256) for _ in range(0x200)]
    for machine in (raw, fast):
        machine.memory[:0x200] = ram
        machine.memory[0x507] = 0x10
        machine.cpu.pc = address
        machine.cpu.sp = stack
        machine.cpu.p = stack
        machine.cpu.x, machine.cpu.y = 19, 37
    for _ in range(256):
        if raw.cpu.pc == target:
            break
        raw.cpu.step()
    assert raw.cpu.pc == target
    fast._step()
    assert (fast.cpu.pc, fast.cpu.a, fast.cpu.x, fast.cpu.y, fast.cpu.sp, fast.cpu.p, fast.cpu.processorCycles) == (
        raw.cpu.pc, raw.cpu.a, raw.cpu.x, raw.cpu.y, raw.cpu.sp, raw.cpu.p, raw.cpu.processorCycles)
    assert fast.memory == raw.memory


@pytest.mark.parametrize("entries, seed", (((0, 0, 0, 0), 1), ((41, 46, 46, 41), 3)))
def test_accelerated_full_fight_preserves_outcome_rng_and_combat_state(prg: bytes, entries, seed: int) -> None:
    raw = NativeArena(prg, bytes(0x800), workspace(entries), seed)
    raw._fast_blocks = False
    fast = NativeArena(prg, bytes(0x800), workspace(entries), seed)
    assert fast.run() == raw.run()
    assert fast.memory[:0x8000] == raw.memory[:0x8000]
    assert (fast.cpu.pc, fast.cpu.a, fast.cpu.x, fast.cpu.y, fast.cpu.sp, fast.cpu.p) == (
        raw.cpu.pc, raw.cpu.a, raw.cpu.x, raw.cpu.y, raw.cpu.sp, raw.cpu.p)


def test_stale_ppu_queue_cannot_trap_headless_battle_in_graphics_loop(prg: bytes) -> None:
    raw = NativeArena(prg, bytes(0x800), workspace((33, 51, 62, 255)), 0)
    headless = NativeArena(prg, bytes(0x800), workspace((33, 51, 62, 255)), 0)
    for machine in (raw, headless):
        machine.memory[0x507] = 0x1D
        machine.memory[0x50A] = 3
        machine.memory[0x300:0x302] = [0x80, 253]
        machine.cpu.pc = 0xBEC4
    for _ in range(1000):
        raw.cpu.step()
    assert 0xBEC7 <= raw.cpu.pc <= 0xBEEA
    combat = headless.memory[0x6000:0x8000]
    random_state = headless.memory[0x12:0x14], headless.memory[0x50D]
    headless._step()
    assert headless.cpu.pc == 0x6000
    assert headless.memory[0x6000:0x8000] == combat
    assert (headless.memory[0x12:0x14], headless.memory[0x50D]) == random_state


@pytest.mark.parametrize("seed", (0, 3, 7))
def test_pictured_three_monster_matchup_completes_without_graphics_stall(prg: bytes, seed: int) -> None:
    machine = NativeArena(prg, bytes(0x800), workspace((33, 51, 62, 255)), seed)
    outcome = machine.run()
    assert outcome is None or outcome in (0, 1, 2)
    assert machine.memory[0x6E81] <= 10


def test_real_instruction_budget_exhaustion_is_not_counted_as_a_draw(prg: bytes) -> None:
    machine = NativeArena(prg, bytes(0x800), workspace(), 0)
    with pytest.raises(ArenaSimulationError, match="instruction budget"):
        machine.run(instruction_limit=1)