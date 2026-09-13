from dataclasses import replace
from datetime import datetime, timedelta, timezone

from game.battle import BattleEnemyState, BattleState
from game.combat_analytics import CombatAnalytics
from game.encounter_log import EncounterLog
from game.state import read_state


NOW = datetime(2026, 9, 9, 13, 0, tzinfo=timezone.utc)


def _state(*, hp: int = 40, gold: int = 100, experience: int = 200):
    ram = bytearray(0x800)
    ram[0x58F] = 0x10
    ram[0x63] = 4
    wram = bytearray(0x300)
    wram[0x16A] = 0
    wram[1] = 0x80 if hp else 0
    wram[2:4] = hp.to_bytes(2, "little")
    wram[6] = 8
    wram[13:15] = (50).to_bytes(2, "little")
    wram[17:20] = experience.to_bytes(3, "little")
    wram[0x157:0x15A] = gold.to_bytes(3, "little")
    return read_state(bytes(ram), bytes(wram))


def _battle(*, hp: int = 45, reward_gold: int = 0, reward_experience: int = 0):
    enemy = BattleEnemyState(0, 0x12, 1, hp, 6, 8, 14, 11, 0)
    return BattleState(
        True,
        hp > 0,
        reward_gold,
        reward_experience,
        (enemy,),
        "test detector",
    )


def test_persists_lifetime_and_resets_session_counts(tmp_path) -> None:
    log = EncounterLog(tmp_path / "encounters", end_samples=1)
    log.observe(_battle(), _state(), now=NOW)
    records = log.observe(
        _battle(hp=0, reward_gold=25, reward_experience=300),
        _state(gold=125, experience=500),
        now=NOW + timedelta(seconds=2),
    )
    path = tmp_path / "combat-analytics.json"
    analytics = CombatAnalytics(path)

    assert analytics.observe(records)
    document = analytics.document
    assert document["total_encounters"] == 1
    assert document["session_encounters"] == 1
    assert document["outcomes"]["victory"] == 1
    assert document["reward_experience"] == 300
    assert document["reward_gold"] == 25
    assert document["locations"][0]["encounters"] == 1
    assert document["enemies"][0]["monster_id"] == 0x12

    reloaded = CombatAnalytics(path, records)
    assert reloaded.document["total_encounters"] == 1
    assert reloaded.document["session_encounters"] == 0
    assert not reloaded.observe(records)


def test_tracks_outcomes_and_unidentified_groups(tmp_path) -> None:
    log = EncounterLog(tmp_path / "encounters", end_samples=1)
    log.observe(_battle(), _state(), now=NOW)
    defeated = log.observe(
        _battle(hp=0),
        _state(hp=0),
        now=NOW + timedelta(seconds=1),
    )[0]
    unknown_enemy = replace(defeated.enemies[0], monster_id=None, label="Enemy group 1")
    escaped = replace(
        defeated,
        encounter_id="second",
        outcome="escaped_or_interrupted",
        enemies=(unknown_enemy,),
    )
    analytics = CombatAnalytics(tmp_path / "combat-analytics.json")

    analytics.observe((defeated, escaped))

    document = analytics.document
    assert document["total_encounters"] == 2
    assert document["outcomes"]["defeat"] == 1
    assert document["outcomes"]["escaped_or_interrupted"] == 1
    assert document["unidentified_groups"] == 1