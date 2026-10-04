from __future__ import annotations

from typing import Protocol, Sequence

from retroarch_overlay.models import PanelChip, PanelRow


VULNERABLE = "Susceptible"
IMMUNE = "Immune"


class MonsterRecord(Protocol):
    name: str
    max_hp: int
    max_mp: int
    attack: int
    defense: int
    agility: int
    experience: int
    gold: int
    drop_denominator: int | None
    resistances: tuple[tuple[str, str], ...]


def resistance_lines(resistances: Sequence[tuple[str, str]], *, compact: bool = False) -> tuple[str, ...]:
    groups = (
        ("Vulnerable", tuple(name for name, level in resistances if level == VULNERABLE)),
        ("Resists", tuple(name for name, level in resistances if level == "Partial resistance")),
        ("Strongly resists", tuple(name for name, level in resistances if level == "Strong resistance")),
        ("Immune", tuple(name for name, level in resistances if level == IMMUNE)),
    )
    return tuple(f"{label}: {', '.join(names)}" for label, names in groups
                 if names and not (compact and label == "Vulnerable"))


def monster_card(monster: MonsterRecord, drop_name: str | None, title: str | None = None) -> PanelRow:
    mp = "unlimited" if monster.max_mp == 0xFF else str(monster.max_mp)
    reward = f"{monster.experience:,} XP · {monster.gold:,} G"
    drop = "No item drop"
    if drop_name:
        drop = f"Drops {drop_name}"
        if monster.drop_denominator:
            drop += " (always)" if monster.drop_denominator == 1 else f" (1 in {monster.drop_denominator})"
    return PanelRow(
        title or monster.name,
        emphasis="heading",
        chips=(PanelChip(f"HP {monster.max_hp:,}", "#a83b45"), PanelChip(f"MP {mp}", "#356d99")),
        detail="\n".join((
            f"ATK {monster.attack} · DEF {monster.defense} · AGI {monster.agility}",
            reward,
            drop,
            *resistance_lines(monster.resistances),
        )),
    )
