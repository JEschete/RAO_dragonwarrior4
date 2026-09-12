from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .battle import BattleEnemyState, BattleState
from .state import CharacterState, DragonWarrior4State


@dataclass(frozen=True, slots=True)
class PartyCombatant:
    character_id: int
    name: str
    level: int
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    alive: bool
    poisoned: bool
    paralyzed: bool
    experience: int


@dataclass(frozen=True, slots=True)
class EnemyCombatant:
    slot: int
    monster_id: int | None
    label: str
    group_code: int
    starting_hp: int
    highest_hp: int
    lowest_hp: int
    final_hp: int
    mp: int
    agility: int
    attack: int
    defense: int
    status: int


@dataclass(frozen=True, slots=True)
class CombatFrameEnemy:
    slot: int
    monster_id: int | None
    label: str
    group_code: int
    hp: int
    mp: int
    status: int


@dataclass(frozen=True, slots=True)
class CombatFrame:
    observed_at: str
    elapsed_seconds: float
    battle_active: bool
    reward_gold: int
    reward_experience: int
    party: tuple[PartyCombatant, ...]
    enemies: tuple[CombatFrameEnemy, ...]


@dataclass(frozen=True, slots=True)
class EncounterRecord:
    schema_version: int
    encounter_id: str
    started_at: str
    ended_at: str
    duration_seconds: float
    outcome: str
    outcome_evidence: tuple[str, ...]
    start_location: str
    end_location: str
    map_id: int
    submap: int
    reward_gold: int
    reward_experience: int
    observed_gold_gain: int
    observed_experience_gain: int
    party_start: tuple[PartyCombatant, ...]
    party_end: tuple[PartyCombatant, ...]
    enemies: tuple[EnemyCombatant, ...]
    timeline: tuple[CombatFrame, ...]
    sample_count: int
    detector_evidence: str


@dataclass(slots=True)
class _ActiveEncounter:
    encounter_id: str
    started_at: str
    start_location: str
    end_location: str
    map_id: int
    submap: int
    start_gold: int
    start_experience: int
    party_start: tuple[PartyCombatant, ...]
    party_latest: tuple[PartyCombatant, ...]
    enemies: dict[int, EnemyCombatant]
    timeline: list[CombatFrame]
    reward_gold: int
    reward_experience: int
    sample_count: int
    inactive_samples: int
    detector_evidence: str


@dataclass(slots=True)
class _CandidateEncounter:
    battle: BattleState
    state: DragonWarrior4State
    start_state: DragonWarrior4State
    observed_at: datetime
    samples: int = 1


class EncounterLog:
    def __init__(
        self,
        root: Path | None,
        *,
        start_samples: int = 1,
        end_samples: int = 2,
        recent_limit: int = 200,
    ) -> None:
        if start_samples < 1 or end_samples < 1 or recent_limit < 1:
            raise ValueError("Encounter log limits must be positive")
        self.root = root
        self.active_path = root / "active.json" if root is not None else None
        self.start_samples = start_samples
        self.end_samples = end_samples
        self.recent_limit = recent_limit
        self._active = self._load_active()
        self._candidate: _CandidateEncounter | None = None
        self._recent = list(self._load_recent())
        self._last_active_signature = ""
        self._last_idle_state: DragonWarrior4State | None = None
        self._last_reward_counters: tuple[int, int] | None = None

    @property
    def recent(self) -> tuple[EncounterRecord, ...]:
        return tuple(self._recent)

    @property
    def active_document(self) -> dict[str, Any] | None:
        if self._active is None:
            return None
        return {
            "encounter_id": self._active.encounter_id,
            "started_at": self._active.started_at,
            "location": self._active.start_location,
            "sample_count": self._active.sample_count,
            "reward_gold": self._active.reward_gold,
            "reward_experience": self._active.reward_experience,
            "party": [asdict(value) for value in self._active.party_latest],
            "enemies": [
                asdict(value)
                for value in sorted(
                    self._active.enemies.values(),
                    key=lambda enemy: enemy.slot,
                )
            ],
            "timeline": [asdict(value) for value in self._active.timeline],
            "detector_evidence": self._active.detector_evidence,
        }

    @property
    def active_summary(self) -> dict[str, Any] | None:
        document = self.active_document
        if document is None:
            return None
        document["frame_count"] = len(document.pop("timeline", []))
        return document

    def observe(
        self,
        battle: BattleState,
        state: DragonWarrior4State,
        *,
        now: datetime | None = None,
    ) -> tuple[EncounterRecord, ...]:
        observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if not battle.available:
            return self.recent
        reward_counters = (battle.reward_gold, battle.reward_experience)

        if self._active is not None:
            if (
                battle.active
                and self._active.inactive_samples > 0
                and self._starts_new_encounter(battle)
            ):
                self._finalize(state, observed_at)
                self._last_idle_state = state
                self._candidate = _CandidateEncounter(
                    battle,
                    state,
                    state,
                    observed_at,
                )
                self._start(self._candidate)
                self._candidate = None
                self._last_reward_counters = reward_counters
                return self.recent
            self._update_active(battle, state, observed_at)
            self._last_reward_counters = reward_counters
            if battle.active:
                if self._active.inactive_samples:
                    self._active.inactive_samples = 0
                    self._write_active()
            else:
                self._active.inactive_samples += 1
                self._write_active()
                if self._has_completion_evidence(battle, state):
                    self._finalize(state, observed_at)
                    self._last_idle_state = state
                elif self._active.inactive_samples >= self.end_samples:
                    self._finalize(state, observed_at)
                    self._last_idle_state = state
            return self.recent

        if not battle.active:
            self._candidate = None
            if (
                self._last_reward_counters == (0, 0)
                and reward_counters != (0, 0)
            ):
                self._reconstruct_from_rewards(battle, state, observed_at)
            self._last_reward_counters = reward_counters
            self._last_idle_state = state
            return self.recent
        if self._candidate is None:
            self._candidate = _CandidateEncounter(
                battle,
                state,
                self._last_idle_state or state,
                observed_at,
            )
        else:
            self._candidate.samples += 1
        if self._candidate.samples >= self.start_samples:
            candidate = self._candidate
            self._candidate = None
            self._start(candidate)
            if candidate.samples > 1:
                self._update_active(battle, state, observed_at)
        self._last_reward_counters = reward_counters
        return self.recent

    def _starts_new_encounter(self, battle: BattleState) -> bool:
        active = self._active
        if active is None:
            return False
        coherent = tuple(enemy for enemy in battle.enemies if enemy.coherent)
        if not coherent:
            return False
        for enemy in coherent:
            previous = active.enemies.get(enemy.slot)
            if previous is None:
                return True
            if (
                enemy.monster_id is not None
                and previous.monster_id is not None
                and enemy.monster_id != previous.monster_id
            ):
                return True
            if enemy.hp > previous.final_hp:
                return True
        return False

    def _start(self, candidate: _CandidateEncounter) -> None:
        party_start = self._party(candidate.start_state)
        party_latest = self._party(candidate.state)
        enemies = {
            enemy.slot: self._new_enemy(enemy)
            for enemy in candidate.battle.enemies
            if enemy.coherent
        }
        started_at = candidate.observed_at.isoformat()
        encounter_id = (
            candidate.observed_at.strftime("%Y%m%dT%H%M%S.%fZ")
            + "-"
            + uuid.uuid4().hex[:8]
        )
        self._active = _ActiveEncounter(
            encounter_id,
            started_at,
            candidate.state.location.title,
            candidate.state.location.title,
            candidate.state.location.map_id,
            candidate.state.location.submap,
            candidate.start_state.gold,
            sum(value.experience for value in party_start),
            party_start,
            party_latest,
            enemies,
            [
                self._frame(
                    candidate.battle,
                    candidate.state,
                    candidate.observed_at,
                    candidate.observed_at,
                )
            ],
            candidate.battle.reward_gold,
            candidate.battle.reward_experience,
            1,
            0,
            candidate.battle.detector_evidence,
        )
        self._last_active_signature = self._frame_signature(
            candidate.battle,
            candidate.state,
        )
        self._write_active()

    def _update_active(
        self,
        battle: BattleState,
        state: DragonWarrior4State,
        observed_at: datetime,
    ) -> None:
        active = self._active
        if active is None:
            return
        party = self._party(state)
        signature = self._frame_signature(battle, state)
        if signature == self._last_active_signature:
            return
        self._last_active_signature = signature
        active.sample_count += 1
        active.end_location = state.location.title
        active.party_latest = party
        active.reward_gold = max(active.reward_gold, battle.reward_gold)
        active.reward_experience = max(
            active.reward_experience,
            battle.reward_experience,
        )
        started_at = self._timestamp(active.started_at) or observed_at
        active.timeline.append(
            self._frame(battle, state, observed_at, started_at)
        )
        for enemy in battle.enemies:
            existing = active.enemies.get(enemy.slot)
            if existing is None:
                if enemy.coherent:
                    active.enemies[enemy.slot] = self._new_enemy(enemy)
                continue
            active.enemies[enemy.slot] = EnemyCombatant(
                existing.slot,
                enemy.monster_id
                if enemy.monster_id is not None
                else existing.monster_id,
                enemy.label if enemy.monster_id is not None else existing.label,
                enemy.group_code,
                existing.starting_hp,
                max(existing.highest_hp, enemy.hp),
                min(existing.lowest_hp, enemy.hp),
                enemy.hp,
                enemy.mp,
                enemy.agility,
                enemy.attack,
                enemy.defense,
                enemy.status,
            )
        self._write_active()

    def _has_completion_evidence(
        self,
        battle: BattleState,
        state: DragonWarrior4State,
    ) -> bool:
        active = self._active
        if active is None:
            return False
        return any(
            (
                battle.reward_gold,
                battle.reward_experience,
                active.reward_gold,
                active.reward_experience,
                max(0, state.gold - active.start_gold),
                max(
                    0,
                    sum(value.experience for value in self._party(state))
                    - active.start_experience,
                ),
            )
        )

    def _reconstruct_from_rewards(
        self,
        battle: BattleState,
        state: DragonWarrior4State,
        observed_at: datetime,
    ) -> None:
        reconstructed = BattleState(
            True,
            True,
            battle.reward_gold,
            battle.reward_experience,
            tuple(enemy for enemy in battle.enemies if enemy.coherent),
            (
                "Reconstructed from a zero-to-nonzero documented reward-counter "
                "edge; active battle frames were skipped during fast-forward"
            ),
        )
        candidate = _CandidateEncounter(
            reconstructed,
            state,
            self._last_idle_state or state,
            observed_at,
        )
        self._start(candidate)
        self._update_active(battle, state, observed_at)
        self._finalize(state, observed_at)

    @staticmethod
    def _frame_signature(
        battle: BattleState,
        state: DragonWarrior4State,
    ) -> str:
        return json.dumps(
            {
                "battle": asdict(battle),
                "party": [
                    asdict(value)
                    for value in EncounterLog._party(state)
                ],
                "location": state.location.title,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _frame(
        battle: BattleState,
        state: DragonWarrior4State,
        observed_at: datetime,
        started_at: datetime,
    ) -> CombatFrame:
        return CombatFrame(
            observed_at.isoformat(),
            round(max(0.0, (observed_at - started_at).total_seconds()), 3),
            battle.active,
            battle.reward_gold,
            battle.reward_experience,
            EncounterLog._party(state),
            tuple(
                CombatFrameEnemy(
                    enemy.slot,
                    enemy.monster_id,
                    enemy.label,
                    enemy.group_code,
                    enemy.hp,
                    enemy.mp,
                    enemy.status,
                )
                for enemy in battle.enemies
                if enemy.coherent or enemy.hp == 0
            ),
        )

    def _finalize(
        self,
        state: DragonWarrior4State,
        observed_at: datetime,
    ) -> None:
        active = self._active
        if active is None:
            return
        party_end = self._party(state)
        experience_gain = max(
            0,
            sum(value.experience for value in party_end) - active.start_experience,
        )
        gold_gain = max(0, state.gold - active.start_gold)
        starting_ids = {value.character_id for value in active.party_start}
        ending_by_id = {value.character_id: value for value in party_end}
        party_wiped = bool(starting_ids) and all(
            not ending_by_id.get(identifier, value).alive
            or ending_by_id.get(identifier, value).hp <= 0
            for identifier, value in (
                (member.character_id, member) for member in active.party_start
            )
        )
        evidence = []
        if party_wiped:
            outcome = "defeat"
            evidence.append("All combat-start party members were down at encounter end")
        elif any(
            (
                active.reward_gold,
                active.reward_experience,
                gold_gain,
                experience_gain,
            )
        ):
            outcome = "victory"
            if active.reward_gold or active.reward_experience:
                evidence.append("Documented battle reward counters increased")
            if gold_gain or experience_gain:
                evidence.append("Persistent party rewards increased")
        else:
            outcome = "escaped_or_interrupted"
            evidence.append("Battle slots cleared without rewards or a party wipe")
        started_at = self._timestamp(active.started_at) or observed_at
        record = EncounterRecord(
            1,
            active.encounter_id,
            active.started_at,
            observed_at.isoformat(),
            round(max(0.0, (observed_at - started_at).total_seconds()), 3),
            outcome,
            tuple(evidence),
            active.start_location,
            state.location.title,
            active.map_id,
            active.submap,
            active.reward_gold,
            active.reward_experience,
            gold_gain,
            experience_gain,
            active.party_start,
            party_end,
            tuple(sorted(active.enemies.values(), key=lambda enemy: enemy.slot)),
            tuple(active.timeline),
            active.sample_count,
            active.detector_evidence,
        )
        self._write_record(record, observed_at)
        self._recent.insert(0, record)
        del self._recent[self.recent_limit:]
        self._active = None
        self._last_active_signature = ""
        if self.active_path is not None:
            try:
                self.active_path.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _party(state: DragonWarrior4State) -> tuple[PartyCombatant, ...]:
        return tuple(
            EncounterLog._party_member(value)
            for value in state.characters
            if value.active
        )

    @staticmethod
    def _party_member(value: CharacterState) -> PartyCombatant:
        return PartyCombatant(
            value.character_id,
            value.name,
            value.level,
            value.hp,
            value.max_hp,
            value.mp,
            value.max_mp,
            value.alive,
            value.poisoned,
            value.paralyzed,
            value.experience,
        )

    @staticmethod
    def _new_enemy(value: BattleEnemyState) -> EnemyCombatant:
        return EnemyCombatant(
            value.slot,
            value.monster_id,
            value.label,
            value.group_code,
            value.hp,
            value.hp,
            value.hp,
            value.hp,
            value.mp,
            value.agility,
            value.attack,
            value.defense,
            value.status,
        )

    def _write_active(self) -> None:
        if self.active_path is None or self._active is None:
            return
        self._write_json(self.active_path, self._active_document(self._active))

    def _write_record(
        self,
        record: EncounterRecord,
        observed_at: datetime,
    ) -> None:
        if self.root is None:
            return
        directory = (
            self.root
            / f"{observed_at.year:04d}"
            / f"{observed_at.month:02d}"
            / f"{observed_at.day:02d}"
        )
        self._write_json(directory / f"{record.encounter_id}.json", asdict(record))

    def _load_active(self) -> _ActiveEncounter | None:
        if self.active_path is None:
            return None
        try:
            value = json.loads(self.active_path.read_text(encoding="utf-8"))
            return self._active_from_document(value)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _load_recent(self) -> tuple[EncounterRecord, ...]:
        if self.root is None or not self.root.is_dir():
            return ()
        records = []
        for year in self._dated_directories(self.root):
            for month in self._dated_directories(year):
                for day in self._dated_directories(month):
                    for path in sorted(day.glob("*.json"), reverse=True):
                        try:
                            value = json.loads(path.read_text(encoding="utf-8"))
                            records.append(self._record_from_document(value))
                        except (OSError, TypeError, ValueError, json.JSONDecodeError):
                            continue
                        if len(records) >= self.recent_limit:
                            return tuple(records)
        return tuple(records)

    @staticmethod
    def _dated_directories(root: Path) -> tuple[Path, ...]:
        try:
            return tuple(
                sorted(
                    (
                        path
                        for path in root.iterdir()
                        if path.is_dir() and path.name.isdigit()
                    ),
                    reverse=True,
                )
            )
        except OSError:
            return ()

    @staticmethod
    def _active_document(active: _ActiveEncounter) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "encounter_id": active.encounter_id,
            "started_at": active.started_at,
            "start_location": active.start_location,
            "end_location": active.end_location,
            "map_id": active.map_id,
            "submap": active.submap,
            "start_gold": active.start_gold,
            "start_experience": active.start_experience,
            "party_start": [asdict(value) for value in active.party_start],
            "party_latest": [asdict(value) for value in active.party_latest],
            "enemies": [asdict(value) for value in active.enemies.values()],
            "timeline": [asdict(value) for value in active.timeline],
            "reward_gold": active.reward_gold,
            "reward_experience": active.reward_experience,
            "sample_count": active.sample_count,
            "inactive_samples": active.inactive_samples,
            "detector_evidence": active.detector_evidence,
        }

    @staticmethod
    def _active_from_document(value: dict[str, Any]) -> _ActiveEncounter:
        enemies = {
            int(enemy["slot"]): EnemyCombatant(**enemy)
            for enemy in value.get("enemies", [])
        }
        timeline = [
            EncounterLog._frame_from_document(frame)
            for frame in value.get("timeline", [])
        ]
        return _ActiveEncounter(
            str(value["encounter_id"]),
            str(value["started_at"]),
            str(value["start_location"]),
            str(value.get("end_location", value["start_location"])),
            int(value["map_id"]),
            int(value["submap"]),
            int(value["start_gold"]),
            int(value["start_experience"]),
            tuple(PartyCombatant(**item) for item in value.get("party_start", [])),
            tuple(PartyCombatant(**item) for item in value.get("party_latest", [])),
            enemies,
            timeline,
            int(value.get("reward_gold", 0)),
            int(value.get("reward_experience", 0)),
            int(value.get("sample_count", 0)),
            int(value.get("inactive_samples", 0)),
            str(value.get("detector_evidence", "")),
        )

    @staticmethod
    def _record_from_document(value: dict[str, Any]) -> EncounterRecord:
        return EncounterRecord(
            int(value.get("schema_version", 1)),
            str(value["encounter_id"]),
            str(value["started_at"]),
            str(value["ended_at"]),
            float(value["duration_seconds"]),
            str(value["outcome"]),
            tuple(str(item) for item in value.get("outcome_evidence", [])),
            str(value["start_location"]),
            str(value["end_location"]),
            int(value["map_id"]),
            int(value["submap"]),
            int(value.get("reward_gold", 0)),
            int(value.get("reward_experience", 0)),
            int(value.get("observed_gold_gain", 0)),
            int(value.get("observed_experience_gain", 0)),
            tuple(PartyCombatant(**item) for item in value.get("party_start", [])),
            tuple(PartyCombatant(**item) for item in value.get("party_end", [])),
            tuple(EnemyCombatant(**item) for item in value.get("enemies", [])),
            tuple(
                EncounterLog._frame_from_document(item)
                for item in value.get("timeline", [])
            ),
            int(value.get("sample_count", 0)),
            str(value.get("detector_evidence", "")),
        )

    @staticmethod
    def _frame_from_document(value: dict[str, Any]) -> CombatFrame:
        return CombatFrame(
            str(value["observed_at"]),
            float(value.get("elapsed_seconds", 0)),
            bool(value.get("battle_active", False)),
            int(value.get("reward_gold", 0)),
            int(value.get("reward_experience", 0)),
            tuple(PartyCombatant(**item) for item in value.get("party", [])),
            tuple(CombatFrameEnemy(**item) for item in value.get("enemies", [])),
        )

    @staticmethod
    def _timestamp(value: str) -> datetime | None:
        try:
            result = datetime.fromisoformat(value)
        except ValueError:
            return None
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)