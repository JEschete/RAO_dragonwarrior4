from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .reference_data import item_category
from .state import CharacterState, InventoryItemState


class EquipmentCatalog(Protocol):
    def equipment_bonus(self, item_id: int) -> int: ...
    def equipment_traits(self, item_id: int) -> tuple[int, int, int]: ...
    def equipment_eligible(self, item_id: int, character_id: int, hero_female: bool = False) -> bool: ...


@dataclass(frozen=True, slots=True)
class EquipmentComparison:
    character_id: int
    character_name: str
    current_item: str
    stat: str
    current_value: int | None
    candidate_value: int | None
    delta: int | None
    verdict: str
    notes: tuple[str, ...] = ()


def shop_currency(map_id: int, submap: int) -> str:
    if map_id == 0x22:
        return "medals"
    return "casino coins" if (map_id, submap) == (4, 1) else "gold"


def compare_equipment(
    catalog: EquipmentCatalog,
    item_id: int,
    character: CharacterState,
    hero_female: bool = False,
) -> EquipmentComparison:
    category = item_category(item_id)
    equipped = {item.category: item for item in reversed(character.items) if item.equipped}
    current = equipped.get(category)
    current_name = current.name if current is not None else "None"
    if character.guest or not catalog.equipment_eligible(item_id, character.character_id & 7, hero_female):
        return EquipmentComparison(character.character_id, character.name, current_name, "", None, None, None, "Cannot equip")
    candidate_traits = catalog.equipment_traits(item_id)
    current_traits = catalog.equipment_traits(current.item_id) if current is not None else (0, 0, 0)
    if current is not None and current_traits[0] & 8 and current.item_id != item_id:
        return EquipmentComparison(character.character_id, character.name, current_name, "", None, None, None,
                                   "Cannot replace cursed gear")
    notes = []
    if candidate_traits[0] & 8:
        notes.append("Cursed")
    if current is not None and candidate_traits != current_traits:
        notes.append("Different special effect")
    passive_provider = getattr(catalog, "equipment_passives", None)
    if passive_provider is not None:
        before_passives = set(passive_provider(current.item_id)) if current is not None else set()
        after_passives = set(passive_provider(item_id))
        notes.extend("Loses: " + effect for effect in sorted(before_passives - after_passives))
        notes.extend("Gains: " + effect for effect in sorted(after_passives - before_passives))
    protection = getattr(catalog, "equipment_protection", None)
    if protection is not None:
        candidate_loadout = dict(equipped)
        candidate_loadout[category] = InventoryItemState(item_id, "Candidate", category, True)
        current_protection = _loadout_protection(protection, equipped)
        candidate_protection = _loadout_protection(protection, candidate_loadout)
        for effect in sorted(current_protection.keys() | candidate_protection.keys()):
            before = current_protection.get(effect, 256)
            after = candidate_protection.get(effect, 256)
            if before != after:
                notes.append(f"{effect} taken {(after - before) / 256:+.0%}")
    current_bonus = catalog.equipment_bonus(current.item_id) if current is not None else 0
    candidate_bonus = catalog.equipment_bonus(item_id)
    if category == "weapon":
        stat = "ATK"
        current_value = character.strength + current_bonus
    elif category in {"armor", "shield", "helmet"}:
        stat = "DEF"
        current_value = _defense(catalog, character, equipped)
    elif category == "accessory":
        current_value = _agility(character, equipped)
        candidate_value = min(255, character.agility * 2) if item_id == 0x50 else character.agility
        if "armor" in equipped and equipped["armor"].item_id == 0x3C:
            candidate_value = 0
        delta = candidate_value - current_value
        verdict = "Upgrade" if delta > 0 else "Downgrade" if delta < 0 else "Sidegrade"
        return EquipmentComparison(character.character_id, character.name, current_name, "AGI", current_value,
                                   candidate_value, delta, verdict, tuple(notes))
    else:
        return EquipmentComparison(character.character_id, character.name, current_name, "", None, None, None, "Not equipment")
    delta = candidate_bonus - current_bonus
    if stat == "DEF" and "weapon" in equipped and equipped["weapon"].item_id == 0x1F:
        delta = 0
    if category == "weapon" and item_id == 0x1F:
        notes.append(f"DEF {_defense(catalog, character, equipped)} to 0")
    if category == "armor" and item_id == 0x3C:
        notes.append(f"AGI {_agility(character, equipped)} to 0")
    if category == "armor" and current is not None and current.item_id == 0x3C and item_id != 0x3C:
        replacement = dict(equipped)
        replacement.pop("armor", None)
        notes.append(f"AGI 0 to {_agility(character, replacement)}")
    verdict = "Upgrade" if delta > 0 else "Downgrade" if delta < 0 else "Sidegrade"
    if notes and verdict == "Upgrade":
        verdict = "Upgrade with tradeoff"
    return EquipmentComparison(character.character_id, character.name, current_name, stat, current_value,
                               current_value + delta, delta, verdict, tuple(notes))


def _loadout_protection(provider, equipped: dict) -> dict[str, int]:
    for category in ("armor", "shield", "helmet"):
        item = equipped.get(category)
        if item is not None:
            return dict(provider(item.item_id))
    return {}


def _agility(character: CharacterState, equipped: dict) -> int:
    if "armor" in equipped and equipped["armor"].item_id == 0x3C:
        return 0
    return min(255, character.agility * 2) if "accessory" in equipped and equipped["accessory"].item_id == 0x50 else character.agility


def _defense(catalog: EquipmentCatalog, character: CharacterState, equipped: dict) -> int:
    if "weapon" in equipped and equipped["weapon"].item_id == 0x1F:
        return 0
    return character.agility // 2 + sum(
        catalog.equipment_bonus(item.item_id)
        for kind, item in equipped.items() if kind in {"armor", "shield", "helmet"}
    )