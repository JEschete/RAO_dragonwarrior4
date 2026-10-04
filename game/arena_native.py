from __future__ import annotations

from collections import deque
from functools import lru_cache
from random import Random
from threading import Event
from typing import Callable

from py65.devices.mpu6502 import MPU

from .arena import ArenaPrediction, ArenaRandom, SIMULATION_COUNT, validate_simulations


class ArenaSimulationError(ValueError):
    pass


@lru_cache(maxsize=1)
def _rom_banks(prg: bytes) -> tuple[bytes, ...]:
    return tuple(prg[offset:offset + 0x4000] for offset in range(0, len(prg), 0x4000))


class _Memory(list):
    def __init__(self, prg: bytes, ram: bytes, workspace: bytes) -> None:
        super().__init__([0] * 65536)
        self.banks = _rom_banks(prg)
        self._mapped_bank: int | None = None
        self[:0x800] = ram
        self[0x6000:0x8000] = workspace
        self[0x507] = 0x11

    def __setitem__(self, address, value) -> None:
        if isinstance(address, int) and address >= 0x8000:
            return
        super().__setitem__(address, value)
        if address == 0x507:
            bank = value & 31
            if bank != self._mapped_bank:
                super().__setitem__(slice(0x8000, 0xC000), self.banks[bank])
                if self._mapped_bank is None or (bank & 16) != (self._mapped_bank & 16):
                    super().__setitem__(slice(0xC000, 0x10000), self.banks[(bank & 16) | 15])
                self._mapped_bank = bank


class NativeArena:
    def __init__(self, prg: bytes, ram: bytes, workspace: bytes, seed: int) -> None:
        if len(prg) != 0x80000 or len(ram) != 0x800 or len(workspace) != 0x2000:
            raise ArenaSimulationError("Incomplete arena ROM or memory snapshot")
        self.memory = _Memory(prg, ram, workspace)
        self.cpu = MPU(memory=self.memory, pc=0x8036)
        self.cpu.sp = 0xFF
        self.cpu.stPushWord(0x5FFF)
        self.random = Random(seed)
        self.rng = ArenaRandom(self.random.randrange(65536), self.random.randrange(256))
        self.memory[0x12] = self.rng.state & 255
        self.memory[0x13] = self.rng.state >> 8
        self.memory[0x50D] = self.rng.counter
        self.memory[0x6E7F] = 0
        self.memory[0x6E81] = 0
        self.memory[0x72E9] = 0x80
        self.memory[0x6E49:0x6E4D] = [int(identity != 255) for identity in self.memory[0x6E45:0x6E49]]
        self.trace = deque(maxlen=16)
        self._fast_blocks = True

    def _return(self) -> None:
        self.cpu.pc = (self.cpu.stPopWord() + 1) & 0xFFFF

    def _stat_workspace_block(self, address: int) -> None:
        cpu, memory = self.cpu, self.memory
        if address == 0xA32E:
            for value in reversed(memory[:16]):
                cpu.stPush(value)
            memory[:16] = [0] * 16
            memory[0x81:0x84] = memory[0x7B:0x7E]
            cpu.a = memory[0x7B]
            cpu.x = 255
            cpu.p = (cpu.p & ~0x82) | 0x80
            cpu.pc = 0xA348
            cpu.processorCycles += 380
        else:
            for offset in range(16):
                memory[offset] = cpu.stPop()
            cpu.a = memory[15]
            cpu.x, cpu.y = 16, 0
            cpu.p = (cpu.p & ~0x82) | 0x02
            cpu.pc = 0xA38C
            cpu.processorCycles += 243

    def _step(self) -> None:
        cpu = self.cpu
        memory = self.memory
        bank = memory[0x507]
        address = cpu.pc
        self.trace.append((bank, address))
        if self._fast_blocks and bank == 0x10 and address in (0xA32E, 0xA381):
            self._stat_workspace_block(address)
            return
        if bank == 0x1D and address == 0xBEC4:
            self._return()
            return
        if address == 0xC891:
            self.rng.state = memory[0x12] | (memory[0x13] << 8)
            self.rng.counter = memory[0x50D]
            cpu.a = self.rng.next_byte()
            memory[0x12] = self.rng.state & 255
            memory[0x13] = self.rng.state >> 8
            memory[0x50D] = self.rng.counter
            total = (self.rng.state & 255) + self.rng.counter
            overflow = (~((self.rng.state & 255) ^ self.rng.counter) & ((self.rng.state & 255) ^ cpu.a)) & 0x80
            cpu.p = ((cpu.p & ~0xC3) | (0x02 if cpu.a == 0 else 0) | (cpu.a & 0x80)
                     | int(total > 255) | (overflow >> 1))
            self._return()
            return
        if address in (0xFF74, 0xC62D, 0xC633, 0xC90C, 0xC8CC, 0xC8E1, 0xD214, 0xD218):
            memory[0x12] = (memory[0x12] + self.random.randrange(256)) & 255
            memory[0x50C] = (memory[0x50C] + 1) & 255
            self._return()
            return
        if address == 0xC8EC:
            memory[0x14:0x16] = [0, 0]
            self._return()
            return
        if memory[address] == 0:
            service, operand = memory[address + 1:address + 3]
            if operand & 15 == 11 and operand < 0xCB:
                cpu.pc += 3
                return
            target_bank = (operand >> 4) | ((operand & 8) << 1)
            if operand == 0xFB or (target_bank == 0x19 and operand & 15 != 3):
                cpu.pc += 3
                return
            if target_bank == 0x16 and operand & 15 != 3:
                cpu.pc += 4 if service == 7 else 3
                return
        cpu.step()

    def run(self, instruction_limit: int = 8_000_000, cancel: Event | None = None) -> int | None:
        for count in range(instruction_limit):
            if count % 4096 == 0 and cancel is not None and cancel.is_set():
                raise ArenaSimulationError("Arena simulation cancelled")
            bank, address = self.memory[0x507], self.cpu.pc
            if bank == 0x11 and address == 0x936E:
                if self.cpu.x >= 4:
                    raise ArenaSimulationError("Arena survivor is outside the four entry slots")
                return self.cpu.x
            if bank == 0x11 and address == 0x9358:
                return None
            if bank == 0x12 and address == 0x88C0 and self.cpu.a >= 10:
                return None
            if address == 0x6000:
                raise ArenaSimulationError("Arena battle returned without a terminal outcome")
            self._step()
        path = ", ".join(f"{bank:02X}:{address:04X}" for bank, address in self.trace)
        raise ArenaSimulationError(f"Arena simulation exceeded its instruction budget ({path})")


def simulate_arena(
    prg: bytes, ram: bytes, workspace: bytes, *, seed: int = 0,
    progress: Callable[[int], None] | None = None, cancel: Event | None = None,
    simulations: int = SIMULATION_COUNT,
) -> ArenaPrediction:
    validate_simulations(simulations)
    monster_ids = tuple(workspace[0xE45:0xE49])
    if (len(monster_ids) != 4 or sum(identity != 255 for identity in monster_ids) < 2
            or any(identity >= 214 and identity != 255 for identity in monster_ids)):
        raise ArenaSimulationError("The arena lineup requires two to four valid monsters")
    wins = [0, 0, 0, 0]
    draws = 0
    for index in range(simulations):
        outcome = NativeArena(prg, ram, workspace, seed + index).run(cancel=cancel)
        if outcome is None:
            draws += 1
        else:
            wins[outcome] += 1
        if progress is not None:
            progress(index + 1)
    return ArenaPrediction(monster_ids, tuple(wins), draws, simulations)