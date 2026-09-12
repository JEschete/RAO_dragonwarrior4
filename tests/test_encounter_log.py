from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from game.battle import BattleEnemyState, BattleState
from game.encounter_log import EncounterLog
from game.state import read_state


NOW = datetime(2026, 9, 9, 13, 0, tzinfo=timezone.utc)


def game_state(*, hp: int = 40, gold: int = 100, experience: int = 200):
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


def battle_state(
    *,
    hp: int = 45,
    reward_gold: int = 0,
    reward_experience: int = 0,
) -> BattleState:
    enemy = BattleEnemyState(0, 0x12, 1, hp, 6, 8, 14, 11, 0)
    return BattleState(
        True,
        hp > 0,
        reward_gold,
        reward_experience,
        (enemy,),
        "test detector",
    )


def test_writes_one_json_per_completed_victory(tmp_path) -> None:
    log = EncounterLog(tmp_path)
    start = game_state()

    log.observe(battle_state(), start, now=NOW)
    log.observe(battle_state(hp=30), start, now=NOW + timedelta(seconds=1))
    assert log.active_path.is_file()
    assert list(tmp_path.glob("*/*/*/*.json")) == []

    won = game_state(gold=125, experience=500)
    ended = battle_state(hp=0, reward_gold=25, reward_experience=300)
    log.observe(ended, won, now=NOW + timedelta(seconds=2))
    log.observe(ended, won, now=NOW + timedelta(seconds=3))

    files = list(tmp_path.glob("*/*/*/*.json"))
    assert len(files) == 1
    assert not log.active_path.exists()
    record = log.recent[0]
    assert record.outcome == "victory"
    assert record.reward_gold == 25
    assert record.reward_experience == 300
    assert record.observed_gold_gain == 25
    assert record.observed_experience_gain == 300
    assert record.enemies[0].starting_hp == 45
    assert record.enemies[0].lowest_hp == 0
    assert [frame.enemies[0].hp for frame in record.timeline] == [45, 30, 0]


def test_classifies_party_wipe_as_defeat(tmp_path) -> None:
    log = EncounterLog(tmp_path, start_samples=1, end_samples=1)
    log.observe(battle_state(), game_state(), now=NOW)

    log.observe(battle_state(hp=0), game_state(hp=0), now=NOW + timedelta(seconds=4))

    assert log.recent[0].outcome == "defeat"


def test_classifies_unrewarded_clear_as_escape_or_interruption(tmp_path) -> None:
    log = EncounterLog(tmp_path, start_samples=1, end_samples=1)
    log.observe(battle_state(), game_state(), now=NOW)

    log.observe(battle_state(hp=0), game_state(), now=NOW + timedelta(seconds=4))

    assert log.recent[0].outcome == "escaped_or_interrupted"


def test_restart_resumes_active_checkpoint_without_duplicate_combat(tmp_path) -> None:
    first = EncounterLog(tmp_path, start_samples=1, end_samples=2)
    first.observe(battle_state(), game_state(), now=NOW)
    encounter_id = first.active_document["encounter_id"]

    resumed = EncounterLog(tmp_path, start_samples=1, end_samples=2)
    assert resumed.active_document["encounter_id"] == encounter_id
    ended = battle_state(hp=0, reward_experience=10)
    resumed.observe(ended, game_state(experience=210), now=NOW + timedelta(seconds=2))
    resumed.observe(ended, game_state(experience=210), now=NOW + timedelta(seconds=3))

    assert len(list(tmp_path.glob("*/*/*/*.json"))) == 1
    assert resumed.recent[0].encounter_id == encounter_id


def test_single_active_sample_opens_immediately_for_fast_forward(tmp_path) -> None:
    log = EncounterLog(tmp_path)

    log.observe(battle_state(), game_state(), now=NOW)

    assert log.active_document is not None
    assert len(log.active_document["timeline"]) == 1


def test_reward_edge_reconstructs_combat_missed_between_polls(tmp_path) -> None:
    log = EncounterLog(tmp_path)
    idle = battle_state(hp=0)
    log.observe(idle, game_state(), now=NOW)

    rewarded = battle_state(hp=0, reward_gold=7, reward_experience=12)
    log.observe(
        rewarded,
        game_state(gold=107, experience=212),
        now=NOW + timedelta(milliseconds=50),
    )

    assert len(log.recent) == 1
    assert log.recent[0].outcome == "victory"
    assert "Reconstructed" in log.recent[0].detector_evidence
    assert len(list(tmp_path.glob("*/*/*/*.json"))) == 1


def test_identical_fast_samples_are_collapsed_from_timeline(tmp_path) -> None:
    log = EncounterLog(tmp_path)
    state = game_state()
    battle = battle_state()

    log.observe(battle, state, now=NOW)
    writer = Mock(wraps=log._write_json)
    log._write_json = writer
    log.observe(battle, state, now=NOW + timedelta(milliseconds=50))
    log.observe(battle, state, now=NOW + timedelta(milliseconds=100))

    assert len(log.active_document["timeline"]) == 1
    assert log.active_summary["frame_count"] == 1
    assert "timeline" not in log.active_summary
    writer.assert_not_called()


def test_single_idle_frame_separates_back_to_back_fast_combats(tmp_path) -> None:
    log = EncounterLog(tmp_path, end_samples=2)
    state = game_state()
    log.observe(battle_state(hp=45), state, now=NOW)
    log.observe(battle_state(hp=0), state, now=NOW + timedelta(milliseconds=50))

    log.observe(
        battle_state(hp=45),
        state,
        now=NOW + timedelta(milliseconds=100),
    )

    assert len(log.recent) == 1
    assert log.recent[0].outcome == "escaped_or_interrupted"
    assert log.active_document is not None
    assert log.active_document["encounter_id"] != log.recent[0].encounter_id
    assert len(list(tmp_path.glob("*/*/*/*.json"))) == 1