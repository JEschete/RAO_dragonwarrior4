import pytest

from game.arena import ArenaPrediction, ArenaRandom, arena_action_allowed


def test_rng_matches_native_crc_recurrence_and_byte_counter_wrap() -> None:
    random = ArenaRandom(0)
    assert random.next_byte() == 0x10
    assert (random.state, random.counter) == (0x1D0F, 1)
    random = ArenaRandom(1, 255)
    assert random.next_byte() == 0x2E
    assert (random.state, random.counter) == (0x0D2E, 0)


def test_arena_filter_retains_spells_breaths_healing_and_normal_attack() -> None:
    assert all(arena_action_allowed(action) for action in (0x00, 0x10, 0x22, 0x29, 0x2D, 0x2E, 0x2F, 0x32))
    blocked = (0x15, 0x3B, 0x43, 0x61, *range(0x1F, 0x22), *range(0x47, 0x58))
    assert not any(arena_action_allowed(action) for action in blocked)


def test_prediction_keeps_duplicate_monsters_as_separate_entries() -> None:
    result = ArenaPrediction((0, 0, 1, 1), (20, 30, 25, 15), 10)
    assert result.wins == (20, 30, 25, 15)
    with pytest.raises(ValueError, match="every simulation"):
        ArenaPrediction((0, 0, 1, 1), (100, 0, 0, 0), 1)


def test_native_sandbox_banks_and_rng_match_the_python_recurrence() -> None:
    from game.arena_native import NativeArena

    prg = bytes(identity for identity in range(32) for _ in range(0x4000))
    machine = NativeArena(prg, bytes(0x800), bytes(0x2000), 1)
    assert machine.memory[0x8000] == 0x11
    assert machine.memory[0xC000] == 0x1F
    machine.memory[0x507] = 8
    assert machine.memory[0x8000] == 8
    assert machine.memory[0xC000] == 15
    machine.memory[0xFFFF] = 0
    assert machine.memory[0xFFFF] == 15
    machine.memory[0x12:0x14] = [0, 0]
    machine.memory[0x50D] = 0
    machine.cpu.pc = 0xC891
    machine._step()
    assert machine.cpu.a == 0x10
    assert machine.memory[0x12:0x14] == [15, 29]
    assert machine.cpu.pc == 0x6000


def test_bank_mapping_reuses_immutable_rom_and_keeps_each_ram_private() -> None:
    from game.arena_native import NativeArena

    prg = bytes(identity for identity in range(32) for _ in range(0x4000))
    first = NativeArena(prg, bytes(0x800), bytes(0x2000), 1)
    second = NativeArena(prg, bytes(0x800), bytes(0x2000), 2)
    assert first.memory.banks is second.memory.banks
    assert isinstance(first.memory.banks[0], bytes)
    first.memory[0x507] = 17
    first.memory[0x507] = 18
    assert first.memory[0x8000] == 18 and first.memory[0xC000] == 31
    first.memory[0x507] = 2
    assert first.memory[0x8000] == 2 and first.memory[0xC000] == 15
    first.memory[0x12] = 99
    assert second.memory[0x12] != 99
    assert second.memory[0x8000] == 17 and second.memory[0xC000] == 31


def test_invalid_native_inputs_fail_instead_of_fabricating_draws() -> None:
    from game.arena_native import ArenaSimulationError, NativeArena, simulate_arena

    with pytest.raises(ArenaSimulationError, match="Incomplete"):
        NativeArena(b"", b"", b"", 0)
    with pytest.raises(ArenaSimulationError, match="two to four valid"):
        simulate_arena(bytes(0x80000), bytes(0x800), bytes([255]) * 0x2000)


def test_one_hundred_runs_report_each_completion_and_separate_draws(monkeypatch) -> None:
    from game.arena_native import NativeArena, simulate_arena

    outcomes = iter([0, 1, 2, None] * 25)
    monkeypatch.setattr(NativeArena, "run", lambda self, **kwargs: next(outcomes))
    workspace = bytearray(0x2000)
    workspace[0xE45:0xE49] = bytes((0, 1, 2, 255))
    progress = []
    result = simulate_arena(bytes(0x80000), bytes(0x800), bytes(workspace), progress=progress.append)
    assert result.wins == (25, 25, 25, 0)
    assert result.draws == 25
    assert progress == list(range(1, 101))


def test_betting_gate_requires_arena_window_location_and_odds_pointer() -> None:
    from game.arena import arena_betting_open

    ram = bytearray(0x800)
    ram[0x63:0x65] = bytes((4, 1))
    ram[0xF6] = 0x6B
    ram[0x7B5:0x7B7] = bytes((0x39, 0x6E))
    assert arena_betting_open(bytes(ram))
    ram[0xF6] = 0x6C
    assert arena_betting_open(bytes(ram))
    ram[0xF6] = 0
    assert not arena_betting_open(bytes(ram))
    ram[0xF6] = 0x6B
    ram[0x64] = 0
    assert not arena_betting_open(bytes(ram))


def test_cancelled_worker_cannot_publish_a_result_for_an_old_match(monkeypatch) -> None:
    from game import arena
    from game.arena import ArenaPredictor
    from threading import Event
    from unittest.mock import Mock
    import json

    predictor = ArenaPredictor()
    old_cancel = Event()
    predictor._cancel = old_cancel

    def finish_old_match():
        predictor.cancel()
        yield json.dumps({"kind": "result", "monster_ids": [0, 0, 0, 0],
                          "wins": [25, 25, 25, 25], "draws": 0, "simulations": 100})

    process = Mock(stdout=finish_old_match())
    process.poll.return_value = 0
    process.wait.return_value = 0
    monkeypatch.setattr(arena.os, "cpu_count", lambda: 2)
    monkeypatch.setattr(arena.subprocess, "Popen", Mock(return_value=process))
    predictor._run(bytes(0x80000), bytes(0x800), bytes(0x2000), old_cancel)
    assert predictor.status.result is None
    assert not predictor.status.running


def _worker_program(target: int) -> bytes:
    prg = bytearray(0x80000)
    start = 0x11 * 0x4000 + 0x36
    prg[start:start + 3] = bytes((0x4C, target & 255, target >> 8))
    return bytes(prg)


def test_real_child_process_reports_results_while_qt_remains_responsive(qtbot) -> None:
    import os
    from PySide6.QtCore import QTimer
    from game.arena import ArenaPredictor

    predictor = ArenaPredictor()
    workspace = bytearray(0x2000)
    workspace[0xE45:0xE49] = bytes((0, 0, 255, 255))
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    predictor.start(_worker_program(0x936E), bytes(0x800), bytes(workspace), simulations=137)
    try:
        qtbot.waitUntil(lambda: predictor._process is not None, timeout=10000)
        assert predictor._process.pid != os.getpid()
        qtbot.waitUntil(lambda: not predictor.status.running, timeout=20000)
        assert predictor.status.error == ""
        assert predictor.status.result.wins == (137, 0, 0, 0)
        assert predictor.status.completed == predictor.status.simulations == predictor.status.result.simulations == 137
        assert ticks
    finally:
        timer.stop()
        predictor.cancel()


def test_cancelling_busy_children_reaps_all_and_rejects_old_results(qtbot, monkeypatch) -> None:
    from game import arena
    from game.arena import ArenaPredictor

    monkeypatch.setattr(arena.os, "cpu_count", lambda: 5)
    predictor = ArenaPredictor()
    workspace = bytearray(0x2000)
    workspace[0xE45:0xE49] = bytes((0, 0, 255, 255))
    predictor.start(_worker_program(0x8036), bytes(0x800), bytes(workspace))
    try:
        qtbot.waitUntil(lambda: len(predictor._processes) == 4, timeout=10000)
        processes = tuple(predictor._processes)
        predictor.cancel()
        qtbot.waitUntil(lambda: all(process.poll() is not None for process in processes), timeout=10000)
        qtbot.waitUntil(lambda: not predictor._processes, timeout=10000)
        assert predictor.status.result is None and not predictor.status.running
    finally:
        predictor.cancel()


@pytest.mark.parametrize("cores, simulations, counts", (
    (1, 100, (100,)), (4, 100, (34, 33, 33)), (16, 100, (25, 25, 25, 25)),
    (16, 1, (1,)), (4, 1000, (334, 333, 333)), (16, 1001, (251, 250, 250, 250)),
))
def test_parallel_batches_preserve_all_seeds_and_aggregate_results(monkeypatch, cores, simulations, counts) -> None:
    from game import arena
    from threading import Event

    predictor = arena.ArenaPredictor()
    cancellation = Event()
    predictor._cancel = cancellation
    batches = []
    monkeypatch.setattr(arena.os, "cpu_count", lambda: cores)

    def batch(payload, seed, count, event, progress):
        batches.append((seed, count))
        progress(count)
        return ArenaPrediction((0, 0, 0, 0), (count, 0, 0, 0), 0, count)

    monkeypatch.setattr(predictor, "_run_batch", batch)
    predictor._run(bytes(0x80000), bytes(0x800), bytes(0x2000), cancellation, simulations)
    expected = []
    offset = 0
    for count in counts:
        expected.append((offset, count))
        offset += count
    assert sorted(batches) == expected
    assert predictor.status.result == ArenaPrediction((0, 0, 0, 0), (simulations, 0, 0, 0), 0, simulations)
    assert predictor.status.completed == predictor.status.simulations == simulations


def test_partial_batch_runs_only_its_assigned_seed_range(monkeypatch) -> None:
    from game import arena_native

    seeds = []

    class Trial:
        def __init__(self, prg, ram, workspace, seed):
            seeds.append(seed)

        def run(self, **kwargs):
            return 1

    monkeypatch.setattr(arena_native, "NativeArena", Trial)
    result = arena_native.simulate_arena(bytes(0x80000), bytes(0x800), bytes(0x2000), seed=25, simulations=250)
    assert seeds == list(range(25, 275))
    assert result == ArenaPrediction((0, 0, 0, 0), (0, 250, 0, 0), 0, 250)


@pytest.mark.parametrize("count", (0, -1, 100_001, True, 1.5, "100"))
def test_invalid_simulation_counts_fail_before_starting_workers(count) -> None:
    from game.arena import ArenaPredictor

    predictor = ArenaPredictor()
    with pytest.raises(ValueError, match="Simulation count"):
        predictor.start(bytes(0x80000), bytes(0x800), bytes(0x2000), simulations=count)
    assert not predictor.status.running and not predictor._processes


def test_child_failure_reports_error_and_reaps_the_entire_group(qtbot, monkeypatch) -> None:
    from game import arena

    monkeypatch.setattr(arena.os, "cpu_count", lambda: 5)
    predictor = arena.ArenaPredictor()
    predictor.start(b"", bytes(0x800), bytes(0x2000))
    try:
        qtbot.waitUntil(lambda: bool(predictor.status.error), timeout=20000)
        qtbot.waitUntil(lambda: not predictor._processes, timeout=10000)
        assert "Incomplete" in predictor.status.error
        assert predictor.status.result is None and not predictor.status.running
    finally:
        predictor.cancel()


def test_backwards_worker_progress_is_an_error_not_a_partial_prediction(monkeypatch) -> None:
    from game import arena
    from threading import Event

    monkeypatch.setattr(arena.os, "cpu_count", lambda: 2)
    predictor = arena.ArenaPredictor()
    cancellation = Event()
    predictor._cancel = cancellation

    def batch(payload, seed, count, event, progress):
        progress(2)
        progress(1)

    monkeypatch.setattr(predictor, "_run_batch", batch)
    predictor._run(bytes(0x80000), bytes(0x800), bytes(0x2000), cancellation)
    assert predictor.status.error == "Invalid arena worker progress"
    assert predictor.status.result is None and not predictor.status.running