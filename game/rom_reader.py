from __future__ import annotations

import hashlib
from pathlib import Path


def _rom_region(full_hash: str, content_hash: str) -> str:
    full_regions = {
        "e45105e8f82d8aa29b39260fd531498d": "US",
        "65be0515383394a096084d4921c353f4": "Japan",
    }
    content_regions = {
        "d8a1d610c93b96ad98e55e09dfcc7533": "US",
    }
    return full_regions.get(
        full_hash,
        content_regions.get(content_hash, "Unknown or patched"),
    )


class RomReader:
    """Validated cartridge bytes, bank-addressed reads, and extraction diagnostics."""

    _data: bytes
    _prg_offset: int
    _diagnostics: dict[str, str]
    content_hash: str
    region: str

    def _load_cartridge(self, rom_path: Path) -> str:
        if rom_path.stat().st_size > 0x100000:
            raise ValueError("Configured DW4 ROM exceeds the supported cartridge size")
        data = rom_path.read_bytes()
        if len(data) < 16 or data[:4] != b"NES\x1a":
            raise ValueError("Configured file is not an iNES ROM")
        nes2 = data[7] & 0x0C == 8
        mapper = (data[6] >> 4) | (data[7] & 0xF0) | ((data[8] & 0x0F) << 8 if nes2 else 0)
        if mapper != 1 or data[5] or (nes2 and (data[9] & 0x0F or data[8] >> 4)):
            raise ValueError("DW4 requires the supported MMC1 cartridge with CHR RAM")
        trainer_size = 512 if data[6] & 0x04 else 0
        self._prg_offset = 16 + trainer_size
        prg_size = data[4] * 0x4000
        if prg_size != 0x80000 or self._prg_offset + prg_size > len(data):
            raise ValueError("Dragon Warrior IV requires 32 16-KiB PRG pages")
        self._data = data
        self.content_hash = hashlib.md5(
            data[self._prg_offset:self._prg_offset + prg_size],
            usedforsecurity=False,
        ).hexdigest()
        return hashlib.md5(data, usedforsecurity=False).hexdigest()

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(getattr(self, "_diagnostics", {}).values())

    def _record_diagnostic(self, identity: str, detail: str) -> None:
        if not hasattr(self, "_diagnostics"):
            self._diagnostics = {}
        self._diagnostics[identity] = detail

    def _cpu_byte(self, bank: int, address: int) -> int:
        return self._cpu_bytes(bank, address, 1)[0]

    def _cpu_bytes(self, bank: int, address: int, size: int) -> bytes:
        start = self._cpu_address(bank, address)
        if size < 0 or address + size > 0xC000 or start + size > self._prg_offset + 0x80000:
            raise ValueError("DW4 ROM table leaves its declared PRG bank")
        result = bytes(self._data[start:start + size])
        if len(result) != size:
            raise ValueError("DW4 ROM table is truncated")
        return result

    def _cpu_address(
        self,
        bank: int,
        address: int,
        *,
        allow_previous_bank: bool = False,
    ) -> int:
        minimum = 0x7F00 if allow_previous_bank else 0x8000
        if not minimum <= address < 0xC000:
            raise ValueError(f"Invalid CPU address ${address:04X} for PRG bank {bank:02X}")
        offset = self._prg_offset + bank * 0x4000 + address - 0x8000
        if offset < self._prg_offset or offset >= self._prg_offset + 0x80000:
            raise ValueError("DW4 ROM bank address is outside PRG data")
        return offset

    def _graphics_address(self, bank: int, address: int) -> int:
        if 0xC000 <= address <= 0xFFFF:
            offset = self._prg_offset + 0x1F * 0x4000 + address - 0xC000
            if offset >= self._prg_offset + 0x80000:
                raise ValueError("DW4 fixed-bank graphics address is outside PRG data")
            return offset
        return self._cpu_address(bank, address, allow_previous_bank=True)