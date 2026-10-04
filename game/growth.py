from __future__ import annotations

from typing import Callable


GROWTH_BANK = 0x12
GROWTH_POINTER_ADDRESS = 0xA0FB
GROWTH_SCALAR_ADDRESS = 0xA259
GROWTH_ID_COUNT = 8
GROWTH_DESCRIPTOR_SIZE = 5
GROWTH_SCALAR_ROW_SIZE = 6
LEVEL_CAP = 99


def experience_threshold(read_bytes: Callable[[int, int, int], bytes], growth_id: int, level: int) -> int | None:
    """Total experience the game requires to reach `level` for one growth ID.

    Port of the experience path (`$0B == 0`) of bank 12 `$9F7C`, as called by
    `$9D41` with `$0A = level`. The result is the three-byte value the game
    stores at `$6E19 + growth_id * 3` while the character is at `level - 1`.
    `read_bytes(bank, cpu_address, size)` reads the configured ROM; the values
    are specific to that ROM, so callers cache per ROM identity.
    """
    if not 0 <= growth_id < GROWTH_ID_COUNT or level > LEVEL_CAP:
        return None
    return _thresholds(read_bytes, growth_id, level)[-1] if level > 1 else 0


def experience_curve(read_bytes: Callable[[int, int, int], bytes], growth_id: int) -> tuple[int, ...] | None:
    """Every threshold for one growth ID, indexed by level 0-99 (levels 0 and 1 are 0)."""
    if not 0 <= growth_id < GROWTH_ID_COUNT:
        return None
    return (0, 0, *_thresholds(read_bytes, growth_id, LEVEL_CAP))


def _thresholds(read_bytes: Callable[[int, int, int], bytes], growth_id: int, level: int) -> list[int]:
    # $9F9C/$A06E: experience descriptors are five bytes per growth ID behind
    # the first word of the family pointer table.
    pointer = int.from_bytes(_read(read_bytes, GROWTH_POINTER_ADDRESS, 2), "little")
    descriptor = _read(read_bytes, (pointer + growth_id * GROWTH_DESCRIPTOR_SIZE) & 0xFFFF, GROWTH_DESCRIPTOR_SIZE)
    # $A038: bit 7 of the five bytes packs the level-2 value, byte 0 first;
    # bits 5-6 of byte 0 select the six-byte scalar row.
    base = sum((value >> 7) << index for index, value in enumerate(descriptor))
    row = (descriptor[0] >> 5) & 3
    scalars = _read(read_bytes, GROWTH_SCALAR_ADDRESS + row * GROWTH_SCALAR_ROW_SIZE, GROWTH_SCALAR_ROW_SIZE)
    # $9FB9-$A037: level 2 returns the base value; every later level scales the
    # previous increment by the current segment's scalar and adds it.
    total = step = base
    result = [total]
    segment = 0
    for current in range(3, level + 1):
        # $9FFA-$A019: a segment covers levels up to its limit; index 5 has no limit.
        while segment < 5 and (descriptor[segment] & (0x7F if segment else 0x1F)) < current:
            segment += 1
        step = _scale(step, scalars[segment])
        total = (total + step) & 0xFFFFFF
        result.append(total)
    return result


def _scale(value: int, scalar: int) -> int:
    # $A07D with $0B == 0: shift-and-add multiply of a 24-bit value into a
    # 32-bit accumulator, then a plain divide by sixteen (no stat rounding).
    accumulator = 0
    while True:
        if scalar & 1:
            accumulator = (accumulator + value) & 0xFFFFFFFF
        scalar >>= 1
        value = (value << 1) & 0xFFFFFF
        if not scalar:
            return (accumulator >> 4) & 0xFFFFFF


def _read(read_bytes: Callable[[int, int, int], bytes], address: int, size: int) -> bytes:
    data = read_bytes(GROWTH_BANK, address, size)
    if len(data) != size:
        raise ValueError("DW4 growth table is truncated")
    return data
