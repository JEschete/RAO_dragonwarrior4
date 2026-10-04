from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, RLock, Thread
from typing import Callable


SIMULATION_COUNT = 100
MAX_SIMULATION_COUNT = 100_000
ROUND_LIMIT = 10


def validate_simulations(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_SIMULATION_COUNT:
        raise ValueError(f"Simulation count must be an integer from 1 to {MAX_SIMULATION_COUNT:,}")
    return value


@dataclass(slots=True)
class ArenaRandom:
    state: int
    counter: int = 0

    def next_byte(self) -> int:
        for _ in range(16):
            feedback = (self.state >> 15) ^ 1
            self.state = (self.state << 1) & 0xFFFF
            if feedback:
                self.state ^= 0x1021
        self.counter = (self.counter + 1) & 0xFF
        return ((self.state & 0xFF) + self.counter) & 0xFF

    def below(self, limit: int) -> int:
        return (limit * self.next_byte()) >> 8


def arena_action_allowed(action_id: int) -> bool:
    return (
        0 <= action_id < 0xFF
        and action_id not in (0x15, 0x3B, 0x43, 0x61)
        and not 0x1F <= action_id < 0x22
        and not 0x47 <= action_id < 0x58
    )


@dataclass(frozen=True, slots=True)
class ArenaPrediction:
    monster_ids: tuple[int, ...]
    wins: tuple[int, ...]
    draws: int
    simulations: int = SIMULATION_COUNT

    def __post_init__(self) -> None:
        validate_simulations(self.simulations)
        if len(self.monster_ids) != len(self.wins) or len(self.wins) != 4:
            raise ValueError("An arena prediction requires four entry slots")
        if min((*self.wins, self.draws)) < 0 or sum(self.wins) + self.draws != self.simulations:
            raise ValueError("Arena outcomes must account for every simulation")

def arena_key(workspace: bytes) -> bytes:
    if len(workspace) != 0x2000:
        raise ValueError("Incomplete arena memory snapshot")
    return workspace[0xE31:0xE41] + workspace[0xE45:0xE49]


def arena_betting_open(ram: bytes) -> bool:
    return (len(ram) == 0x800 and ram[0x63:0x65] == bytes((4, 1))
            and ram[0xF6] in (0x6B, 0x6C)
            and ram[0x7B5:0x7B7] == bytes((0x39, 0x6E)))


@dataclass(frozen=True, slots=True)
class PredictionStatus:
    running: bool = False
    completed: int = 0
    result: ArenaPrediction | None = None
    error: str = ""
    simulations: int = SIMULATION_COUNT


class ArenaPredictor:
    def __init__(self) -> None:
        self._lock = RLock()
        self._cancel = Event()
        self._status = PredictionStatus()
        self._processes: dict[subprocess.Popen[str], Event] = {}

    @property
    def _process(self) -> subprocess.Popen[str] | None:
        with self._lock:
            return next(iter(self._processes), None)

    @property
    def status(self) -> PredictionStatus:
        with self._lock:
            return self._status

    def cancel(self) -> None:
        with self._lock:
            self._cancel.set()
            self._status = PredictionStatus()
            processes = tuple(self._processes)
        for process in processes:
            _terminate(process)

    def fail(self, detail: str) -> None:
        with self._lock:
            self._cancel.set()
            self._status = PredictionStatus(error=detail)
            processes = tuple(self._processes)
        for process in processes:
            _terminate(process)

    def start(self, prg: bytes, ram: bytes, workspace: bytes, *, simulations: int = SIMULATION_COUNT) -> None:
        validate_simulations(simulations)
        with self._lock:
            if self._status.running:
                return
            self._cancel = Event()
            cancellation = self._cancel
            self._status = PredictionStatus(running=True, simulations=simulations)
        Thread(target=self._run, args=(prg, ram, workspace, cancellation, simulations), daemon=True,
               name="dw4-arena-predictor").start()

    def _run(self, prg: bytes, ram: bytes, workspace: bytes, cancellation: Event,
             simulations: int = SIMULATION_COUNT) -> None:
        try:
            payload = {name: base64.b64encode(value).decode("ascii")
                       for name, value in (("prg", prg), ("ram", ram), ("workspace", workspace))}
            workers = min(4, simulations, max(1, (os.cpu_count() or 1) - 1))
            size, remainder = divmod(simulations, workers)
            counts = [size + int(index < remainder) for index in range(workers)]
            completed = [0] * workers

            def report(index: int, count: int) -> None:
                with self._lock:
                    if not completed[index] <= count <= counts[index]:
                        raise ValueError("Invalid arena worker progress")
                    completed[index] = count
                    if cancellation is self._cancel and not cancellation.is_set():
                        self._status = PredictionStatus(running=True, completed=sum(completed), simulations=simulations)

            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dw4-arena-io") as executor:
                futures = []
                offset = 0
                for index, count in enumerate(counts):
                    futures.append(executor.submit(
                        self._run_batch, payload, offset, count, cancellation,
                        lambda count, index=index: report(index, count)))
                    offset += count
                try:
                    results = [future.result() for future in as_completed(futures)]
                except Exception as error:
                    self._abort(cancellation, str(error))
                    return
            result = ArenaPrediction(tuple(workspace[0xE45:0xE49]),
                                     tuple(sum(result.wins[index] for result in results) for index in range(4)),
                                     sum(result.draws for result in results), simulations)
            with self._lock:
                if cancellation is self._cancel and not cancellation.is_set():
                    self._status = PredictionStatus(completed=simulations, result=result, simulations=simulations)
        except Exception as error:
            self._abort(cancellation, str(error))

    def _abort(self, cancellation: Event, detail: str) -> None:
        with self._lock:
            if cancellation is self._cancel and not cancellation.is_set():
                self._status = PredictionStatus(error=detail)
            cancellation.set()
            processes = tuple(process for process, event in self._processes.items() if event is cancellation)
        for process in processes:
            _terminate(process)

    def _run_batch(self, payload: dict[str, str], seed: int, count: int,
                   cancellation: Event, progress: Callable[[int], None]) -> ArenaPrediction:
        process = None
        try:
            if cancellation.is_set():
                raise ValueError("Arena simulation cancelled")
            executable = Path(sys.executable)
            if executable.name.casefold() == "pythonw.exe":
                executable = executable.with_name("python.exe")
            process = subprocess.Popen(
                [str(executable), "-u", str(Path(__file__).with_name("arena_worker.py"))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            with self._lock:
                if cancellation is not self._cancel or cancellation.is_set():
                    raise ValueError("Arena simulation cancelled")
                self._processes[process] = cancellation
            process.stdin.write(json.dumps({**payload, "seed": seed, "simulations": count}))
            process.stdin.close()
            result = None
            for line in process.stdout:
                message = json.loads(line)
                if message["kind"] == "error":
                    raise ValueError(message["detail"])
                if message["kind"] == "result":
                    result = ArenaPrediction(tuple(message["monster_ids"]), tuple(message["wins"]),
                                             message["draws"], message["simulations"])
                    expected_ids = tuple(base64.b64decode(payload["workspace"])[0xE45:0xE49])
                    if result.simulations != count or result.monster_ids != expected_ids:
                        raise ValueError("The arena worker returned a different matchup or trial count")
                    continue
                if message["kind"] != "progress":
                    raise ValueError("Invalid arena worker response")
                progress(message["completed"])
            if process.wait() != 0 or result is None:
                raise ValueError("The arena worker exited without a prediction")
            return result
        finally:
            _terminate(process)
            if process is not None:
                process.wait()
                process.stdout.close()
                if not process.stdin.closed:
                    process.stdin.close()
            with self._lock:
                self._processes.pop(process, None)


def _terminate(process: subprocess.Popen[str] | None) -> None:
    if process is not None and process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass