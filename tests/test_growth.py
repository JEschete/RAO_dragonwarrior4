from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable

import pytest

from game.growth import experience_curve, experience_threshold


ROM_ENVIRONMENT = "RAO_DW4_ROM"
DEFAULT_ROM = Path("//TARDIS-IVORY/Roms/NES/Dragon Warrior IV (USA).nes")
US_PRG_MD5 = "d8a1d610c93b96ad98e55e09dfcc7533"
GROWTH_NAMES = ("Hero", "Cristo", "Nara", "Mara", "Brey", "Taloon", "Ragnar", "Alena")
# Published Dragon Warrior IV (NES) totals, levels 2-20, in growth ID order
# (Dragon's Den "Experience Levels", linked from the saved fansite walkthrough).
PUBLISHED_EARLY = (
    (19, 57, 133, 285, 513, 855, 1368, 2137, 3290, 5019, 7180, 9881, 13257, 17477, 22224, 27564, 33571, 40328, 47929),
    (18, 51, 112, 203, 339, 543, 849, 1308, 1996, 3028, 4576, 6511, 8929, 11951, 15728, 20449, 25760, 31734, 38454),
    (20, 60, 140, 260, 440, 710, 1115, 1722, 2632, 3997, 6044, 8602, 11799, 15795, 20790, 27033, 34836, 43614, 53489),
    (15, 45, 105, 195, 330, 532, 835, 1289, 1970, 2991, 4522, 6435, 8826, 11814, 15549, 20217, 25468, 31375, 38020),
    (19, 54, 119, 216, 361, 578, 903, 1390, 2120, 3215, 4857, 6909, 9474, 12680, 16687, 21695, 27329, 33667, 40797),
    (10, 30, 70, 130, 220, 355, 557, 860, 1314, 1995, 3016, 4292, 5887, 7880, 10371, 13484, 17375, 22238, 27708),
    (12, 36, 84, 156, 264, 426, 669, 1033, 1579, 2398, 3626, 5161, 7079, 9476, 12472, 16217, 20898, 26749, 34062),
    (16, 46, 102, 186, 312, 501, 784, 1208, 1844, 2798, 4229, 6017, 8252, 11045, 14536, 18899, 23807, 29328, 35539),
)
PUBLISHED_LATE_LEVELS = (30, 40, 50, 60, 99)
PUBLISHED_LATE = (
    (201625, 700644, 1804730, 2945430, 7394160),
    (174355, 615599, 1680129, 2814859, 7240306),
    (253192, 901625, 2336318, 3818588, 9599441),
    (172385, 608621, 1745165, 3007195, 7929112),
    (184967, 653064, 1872655, 3226905, 8508480),
    (138307, 497354, 1363553, 2286873, 5887821),
    (181943, 662075, 1626835, 2602435, 6407275),
    (161129, 568889, 1552609, 2601199, 6690700),
)
# (growth ID, current level, value the running game held at $6E19 + growth ID * 3).
NATIVE_RAM_OBSERVATIONS = (
    (0, 1, 19), (1, 15, 15728), (2, 1, 20), (3, 1, 15),
    (4, 14, 12680), (5, 12, 4292), (6, 13, 7079), (7, 15, 14536),
)


def unreadable(bank: int, address: int, size: int) -> bytes:
    raise AssertionError("experience_threshold must not read the ROM for this input")


def synthetic_reader(
    growth_id: int,
    descriptor: tuple[int, ...],
    row: int,
    scalars: tuple[int, ...],
    pointer: int = 0xB000,
) -> Callable[[int, int, int], bytes]:
    bank = bytearray(b"\xFF" * 0x4000)
    bank[0x20FB:0x20FD] = pointer.to_bytes(2, "little")
    start = pointer - 0x8000 + growth_id * 5
    bank[start:start + 5] = bytes(descriptor)
    bank[0x2259 + row * 6:0x2259 + row * 6 + 6] = bytes(scalars)

    def read_bytes(bank_id: int, address: int, size: int) -> bytes:
        assert bank_id == 0x12
        if not 0x8000 <= address or size < 0 or address + size > 0xC000:
            raise ValueError("DW4 ROM table leaves its declared PRG bank")
        return bytes(bank[address - 0x8000:address - 0x8000 + size])

    return read_bytes


def test_first_level_needs_no_experience_and_reads_nothing() -> None:
    for growth_id in range(8):
        for level in (-3, 0, 1):
            assert experience_threshold(unreadable, growth_id, level) == 0


def test_unsupported_growth_ids_and_levels_return_none() -> None:
    for growth_id in (-1, 8, 9, 20):
        for level in (1, 2, 50):
            assert experience_threshold(unreadable, growth_id, level) is None
        assert experience_curve(unreadable, growth_id) is None
    for level in (100, 255):
        assert experience_threshold(unreadable, 0, level) is None


def test_synthetic_descriptor_selects_row_and_walks_all_six_segments() -> None:
    # Bit 7 of bytes 0 and 2 packs base 5; byte 0 bit 5 selects scalar row 1;
    # limits are 4, 6, 8, 9, 10, then the unlimited sixth segment.
    read_bytes = synthetic_reader(3, (0xA4, 0x06, 0x88, 0x09, 0x0A), 1, (0x20, 0x18, 0x10, 0x08, 0x30, 0x14))
    expected = {2: 5, 3: 15, 4: 35, 5: 65, 6: 110, 7: 155, 8: 200, 9: 222, 10: 288, 11: 370, 12: 472}
    assert {level: experience_threshold(read_bytes, 3, level) for level in expected} == expected


def test_scaling_shifts_a_24_bit_multiplicand() -> None:
    # Scalar $80 multiplies by eight; 2**19 shifted seven times leaves 24 bits,
    # so the increment becomes zero rather than 2**22.
    read_bytes = synthetic_reader(0, (0x1F, 0x63, 0x63, 0x63, 0xE3), 0, (0x80,) * 6)
    expected = {2: 16, 3: 144, 4: 1168, 5: 9360, 6: 74896, 7: 599184, 8: 599184, 9: 599184, 99: 599184}
    assert {level: experience_threshold(read_bytes, 0, level) for level in expected} == expected


def test_running_total_wraps_at_three_bytes() -> None:
    read_bytes = synthetic_reader(7, (0x90, 0xE3, 0xE3, 0xE3, 0xE3), 0, (0x20, 0x10, 0x10, 0x10, 0x10, 0x10))
    expected = {2: 31, 3: 93, 16: 1015777, 17: 1523681, 47: 16760801, 48: 491489, 99: 9617377}
    assert {level: experience_threshold(read_bytes, 7, level) for level in expected} == expected


def test_zero_scalar_row_never_adds_to_the_level_two_value() -> None:
    read_bytes = synthetic_reader(0, (0xC5, 0x8A, 0x0F, 0x14, 0xE3), 2, (0,) * 6)
    assert [experience_threshold(read_bytes, 0, level) for level in (2, 3, 50, 99)] == [19, 19, 19, 19]


def test_curve_is_indexed_by_level_and_matches_single_thresholds() -> None:
    read_bytes = synthetic_reader(3, (0xA4, 0x06, 0x88, 0x09, 0x0A), 1, (0x20, 0x18, 0x10, 0x08, 0x30, 0x14))
    curve = experience_curve(read_bytes, 3)
    assert curve is not None and len(curve) == 100
    assert curve[:5] == (0, 0, 5, 15, 35)
    assert all(curve[level] == experience_threshold(read_bytes, 3, level) for level in range(100))


def test_reader_failures_and_short_reads_raise_value_error() -> None:
    outside = synthetic_reader(0, (0x85, 0x0B, 0x0F, 0x2B, 0xE3), 0, (0x10,) * 6, pointer=0xBFF0)
    assert experience_threshold(outside, 0, 2) == 17
    with pytest.raises(ValueError):
        experience_threshold(outside, 4, 5)
    with pytest.raises(ValueError):
        experience_threshold(lambda bank, address, size: b"", 0, 5)


@pytest.fixture(scope="module")
def rom_reader() -> Callable[[int, int, int], bytes]:
    try:
        data = Path(os.environ.get(ROM_ENVIRONMENT) or DEFAULT_ROM).read_bytes()
    except OSError:
        pytest.skip("Dragon Warrior IV (USA) ROM is not readable")
    offset = 16 + (512 if len(data) > 6 and data[6] & 0x04 else 0)
    prg = data[offset:offset + 0x80000]
    if data[:4] != b"NES\x1a" or len(prg) != 0x80000 or hashlib.md5(prg, usedforsecurity=False).hexdigest() != US_PRG_MD5:
        pytest.skip("Configured ROM is not the verified US Dragon Warrior IV PRG")

    def read_bytes(bank: int, address: int, size: int) -> bytes:
        if not 0x8000 <= address or size < 0 or address + size > 0xC000:
            raise ValueError("DW4 ROM table leaves its declared PRG bank")
        start = bank * 0x4000 + address - 0x8000
        return prg[start:start + size]

    return read_bytes


def test_rom_thresholds_match_published_experience_tables(rom_reader: Callable[[int, int, int], bytes]) -> None:
    for growth_id, name in enumerate(GROWTH_NAMES):
        early = tuple(experience_threshold(rom_reader, growth_id, level) for level in range(2, 21))
        late = tuple(experience_threshold(rom_reader, growth_id, level) for level in PUBLISHED_LATE_LEVELS)
        assert early == PUBLISHED_EARLY[growth_id], name
        assert late == PUBLISHED_LATE[growth_id], name


def test_rom_thresholds_match_values_the_game_stored_in_ram(rom_reader: Callable[[int, int, int], bytes]) -> None:
    for growth_id, current_level, stored in NATIVE_RAM_OBSERVATIONS:
        assert experience_threshold(rom_reader, growth_id, current_level + 1) == stored, GROWTH_NAMES[growth_id]


def test_rom_thresholds_strictly_increase_and_fit_three_bytes(rom_reader: Callable[[int, int, int], bytes]) -> None:
    for growth_id, name in enumerate(GROWTH_NAMES):
        curve = experience_curve(rom_reader, growth_id)
        assert curve is not None and len(curve) == 100, name
        assert curve[0] == curve[1] == 0, name
        assert all(before < after for before, after in zip(curve[1:], curve[2:])), name
        assert curve[99] < 1 << 24, name
        assert all(curve[level] == experience_threshold(rom_reader, growth_id, level) for level in range(100)), name
