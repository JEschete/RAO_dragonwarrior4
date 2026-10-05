from __future__ import annotations

from dataclasses import dataclass, replace

from .reference_data import decode_text, map_title
from .rom_map_data import (
    MAP_COUNT,
    MAX_MAP_DIMENSION,
    RomMapData,
    WORLD_KEY_BY_SELECTOR,
)


@dataclass(frozen=True, slots=True)
class MonsterDefinition:
    monster_id: int
    name: str
    max_hp: int
    max_mp: int
    agility: int
    attack: int
    defense: int
    experience: int
    gold: int
    drop_item_id: int | None
    drop_denominator: int | None = None
    resistances: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FormationChance:
    label: str
    monster_ids: tuple[int, ...]
    chance: int
    fixed_group: bool


def _selection_counts(weights: tuple[int, ...]) -> tuple[int, ...]:
    total = sum(weights)
    if not weights or not 0 < total <= 255:
        return ()
    counts = [0] * len(weights)
    for random_byte in range(256):
        roll = random_byte if total == 255 else random_byte * total >> 8
        cumulative = 0
        for index, weight in enumerate(weights):
            cumulative += weight
            if cumulative >= roll:
                counts[index] += 1
                break
    return tuple(counts)


class RomCatalog(RomMapData):
    """Native combat, character growth, equipment, merchant, and name catalogs."""

    def _initialize_catalog(self) -> None:
        self._name_cache: dict[tuple[int, int], str] = {}

    def encounter_pool(self, chapter: int, world: int, x: int, y: int,
                       time_value: int, travel_mode: int = 0) -> tuple[int, tuple[tuple[str, int], ...]] | None:
        if self.region != "US" or travel_mode != 0 or world not in WORLD_KEY_BY_SELECTOR:
            return None
        if chapter == 4 and world:
            zone = (0x35 if y < 12 else 0x34) if world == 1 else 0x36
        else:
            pointer_address = 0xA245 if chapter == 4 else 0xA243 if chapter == 2 else 0xA241
            grid = int.from_bytes(self._cpu_bytes(0x18, pointer_address, 2), "little")
            zone = self._cpu_byte(0x18, grid + (y & 0xF0) + (x >> 4)) & 0x3F
        return self._formation_pool(zone, 0x3FBE if time_value >= 0x78 else 0x1BEF)

    def land_encounter_threshold(self, zone: int, terrain: int, time_value: int, step_count: int,
                                 repel_count: int, party_strength: int, scent_count: int) -> tuple[int | None, str]:
        if self.region != "US" or not 0 <= zone < 64:
            return None, "Encounter rate unavailable"
        if any(not 0 <= value <= 255 for value in (terrain, time_value, step_count, repel_count, party_strength, scent_count)):
            raise ValueError("Invalid native encounter threshold input")
        if terrain >= 8:
            return 0, "No random encounters on this terrain"
        pointer = int.from_bytes(self._cpu_bytes(0x18, 0xA239, 2), "little")
        control, repel_strength = self._cpu_bytes(0x18, pointer + zone * 16, 2)
        base = self._cpu_byte(0x18, 0xA340 + (control >> 5))
        factor = self._cpu_byte(0x18, 0xA33D + step_count) if step_count < 3 else 16
        rate = base * factor
        coefficient = self._cpu_byte(0x18, 0xA27B + terrain) if time_value < 0x78 else 0
        if not coefficient:
            coefficient = self._cpu_byte(0x18, 0xA283 + terrain)
        rate = ((rate * coefficient) & 0xFFFF) >> 8
        remaining = repel_count & 0x7F
        if remaining == 1:
            return 0, "Repel is active and wears off next step"
        if remaining > 1:
            difference = party_strength - repel_strength
            if difference >= 5:
                return 0, "Repel is keeping monsters away"
            if difference > 0:
                rate = (rate * self._cpu_byte(0x18, 0xA348 + difference - 1)) >> 8
        if scent_count:
            rate = min(256, rate * 4)
        return rate, ""

    def indoor_encounter_pool(self, chapter: int, map_id: int, submap: int) -> tuple[int, tuple[tuple[str, int], ...]] | None:
        if self.region != "US" or not self.has_area(map_id, submap):
            return None
        directory = 0xA23D if chapter == 4 else 0xA23B
        pointer = int.from_bytes(self._cpu_bytes(0x18, directory, 2), "little")
        for _ in range(MAP_COUNT):
            current = self._cpu_byte(0x18, pointer)
            if current == 0xFF:
                return None
            if current >= MAP_COUNT:
                raise ValueError("Invalid DW4 indoor encounter map identity")
            count = self._cpu_byte(0x18, 0xA474 + current)
            if not 0 < count <= MAX_MAP_DIMENSION:
                raise ValueError("Invalid DW4 indoor encounter stride")
            if current == map_id:
                if not 0 <= submap < count:
                    return None
                zone = self._cpu_byte(0x18, pointer + submap + 1)
                return None if zone == 0xFF else self._formation_pool(zone, 0x3FFF)
            pointer += count + 1
        raise ValueError("DW4 indoor encounter directory is unterminated")

    def _formation_slots(self, zone: int, mask: int) -> tuple[FormationChance, ...]:
        """One entry per selectable formation slot; chance holds the slot's raw weight."""
        pointer = int.from_bytes(self._cpu_bytes(0x18, 0xA239, 2), "little")
        record = self._cpu_bytes(0x18, pointer + zone * 16, 16)
        weights = self._cpu_bytes(0x18, 0xA28D + ((record[0] >> 2) & 7) * 18, 14)
        slots = []
        for ordinal, monster_id in enumerate(record[2:]):
            if monster_id == 0xFF or not mask & (1 << ordinal):
                continue
            if ordinal >= 12:
                group_pointer = int.from_bytes(self._cpu_bytes(0x18, 0xA237, 2), "little")
                group = self._cpu_bytes(0x18, group_pointer + monster_id * 6, 6)
                members = tuple(identifier for identifier in group[2:] if identifier != 0xFF)
                names = tuple(self.monster_name(identifier) for identifier in members)
                if not names or any(name is None for name in names):
                    raise ValueError("DW4 predefined formation contains an unknown monster")
                label = " + ".join(f"{name} x{names.count(name)}" if names.count(name) > 1 else name
                                   for name in dict.fromkeys(names))
                slots.append(FormationChance(label, members, weights[ordinal], True))
                continue
            name = self.monster_name(monster_id)
            if name:
                slots.append(FormationChance(name, (monster_id,), weights[ordinal], False))
        return tuple(slots)

    def _formation_entries(self, zone: int, mask: int) -> tuple[tuple[str, int], ...]:
        return tuple((slot.label, slot.chance) for slot in self._formation_slots(zone, mask))

    def _formation_pool(self, zone: int, mask: int) -> tuple[int, tuple[tuple[str, int], ...]]:
        pool = {}
        for name, weight in self._formation_entries(zone, mask):
            if weight:
                pool[name] = pool.get(name, 0) + weight
        return zone, tuple(pool.items())

    def formation_entry_chances(self, zone: int, mask: int) -> tuple[tuple[str, int], ...]:
        entries = self._formation_entries(zone, mask)
        chances = {}
        for (name, _), count in zip(entries, _selection_counts(tuple(weight for _, weight in entries))):
            if count:
                chances[name] = chances.get(name, 0) + count
        return tuple(chances.items())

    def formation_chances(self, zone: int, mask: int) -> tuple[FormationChance, ...]:
        slots = self._formation_slots(zone, mask)
        merged: dict[tuple[bool, tuple[int, ...]], FormationChance] = {}
        for slot, count in zip(slots, _selection_counts(tuple(slot.chance for slot in slots))):
            if not count:
                continue
            identity = slot.fixed_group, slot.monster_ids
            previous = merged.get(identity)
            merged[identity] = replace(slot, chance=count + (previous.chance if previous is not None else 0))
        return tuple(sorted(merged.values(), key=lambda entry: -entry.chance))

    def experience_threshold(self, growth_id: int, level: int) -> int | None:
        if self.region != "US":
            return None
        from .growth import experience_threshold
        return experience_threshold(self._cpu_bytes, growth_id, level)

    def spell_milestones(self, character_id: int) -> tuple[tuple[str, int, bool], ...]:
        if self.region != "US" or character_id & 7 >= 5 or not 0 <= character_id <= 8:
            return ()
        character_id &= 7
        mask_pointer = int.from_bytes(self._cpu_bytes(0x12, 0xA10B + character_id * 2, 2), "little")
        level_pointer = int.from_bytes(self._cpu_bytes(0x12, 0xA117 + character_id * 2, 2), "little")
        mask = int.from_bytes(self._cpu_bytes(0x12, mask_pointer, 8), "little")
        levels = self._cpu_bytes(0x12, level_pointer, mask.bit_count())
        result = []
        ordinal = 0
        for spell_id in range(64):
            if not mask & (1 << spell_id):
                continue
            descriptor = levels[ordinal]
            ordinal += 1
            name = self.indexed_name(0, spell_id)
            if name:
                result.append((name, descriptor & 0x7F, bool(descriptor & 0x80)))
        return tuple(sorted(result, key=lambda value: (value[1], value[0])))

    def monster_vitals(self, monster_id: int) -> tuple[int, int] | None:
        if self.region != "US" or not 0 <= monster_id < 214:
            return None
        record = self._cpu_bytes(0x18, 0x8046 + monster_id * 22, 22)
        maximum_hp = record[4] | ((record[15] & 0x03) << 8)
        return 1200 if maximum_hp == 0x03FF else maximum_hp, record[3]

    def arena_program(self) -> bytes:
        if self.region != "US":
            raise ValueError("Arena prediction requires the verified US ROM")
        return self._data[self._prg_offset:self._prg_offset + 0x80000]

    def monster_name(self, monster_id: int) -> str | None:
        return self.indexed_name(9, monster_id) if self.region == "US" and 0 <= monster_id < 214 else None

    def monster_definition(self, monster_id: int) -> MonsterDefinition | None:
        vitals = self.monster_vitals(monster_id)
        if vitals is None:
            return None
        record = self._cpu_bytes(0x18, 0x8046 + monster_id * 22, 22)
        drop = record[8] & 0x7F
        rank = record[20] & 7
        threshold = self._cpu_byte(0x12, 0x9285 + rank)
        denominator = 1 if rank == 0 else (256 // threshold) * (16 if rank == 7 else 1)
        resistance_names = ("Susceptible", "Partial resistance", "Strong resistance", "Immune")
        resistances = []
        for spell_id in range(64):
            category = self._cpu_byte(0x13, 0xB80B + spell_id) & 0x1F
            if category >= 15:
                continue
            selector = self._cpu_byte(0x13, 0xB736 + category)
            resistance = (record[15 + selector // 4] >> ((selector & 3) * 2)) & 3
            name = self.indexed_name(0, spell_id)
            if name:
                resistances.append((name, resistance_names[resistance]))
        return MonsterDefinition(
            monster_id, self.monster_name(monster_id) or "Unknown monster", *vitals,
            record[2], record[5] | ((record[16] & 3) << 8),
            record[6] | ((record[17] & 3) << 8), int.from_bytes(record[:2], "little"),
            record[7] | ((record[18] & 3) << 8), None if drop == 0x7F else drop,
            None if drop == 0x7F else denominator, tuple(resistances),
        )

    def guest_profile(self, monster_id: int) -> tuple[str, int, int] | None:
        vitals = self.monster_vitals(monster_id)
        if vitals is None:
            return None
        name = self.indexed_name(7, monster_id - 0xC5 + 7) if 0xC5 <= monster_id <= 0xCD else self.monster_name(monster_id)
        return (name or "Guest", *vitals)

    def town_shops(self, map_id: int, time_value: int = 0, special_stock: bytes = b"\0\0\0") -> tuple[tuple[int, int, tuple[int, ...]], ...]:
        if self.region != "US":
            return ()
        shops = []
        pointers = tuple(int.from_bytes(self._cpu_bytes(0x18, 0x802C + index * 2, 2), "little")
                         for index in range(3))
        for shop_type in range(1, 4):
            pointer = pointers[shop_type - 1]
            end = min((address for address in (*pointers, 0xB5C2) if address > pointer), default=0xB5C2)
            for _ in range(128):
                if pointer >= end:
                    break
                entry_map = self._cpu_byte(0x18, pointer)
                if entry_map == 0xFF:
                    break
                submap = self._cpu_byte(0x18, pointer + 1)
                pointer += 2
                items = []
                for _ in range(8):
                    if pointer >= end:
                        raise ValueError("DW4 shop stock crosses its directory boundary")
                    value = self._cpu_byte(0x18, pointer)
                    pointer += 1
                    if value & 0x7F != 0x7F:
                        items.append(value & 0x7F)
                    if value & 0x80:
                        break
                else:
                    raise ValueError("DW4 shop stock is unterminated")
                if entry_map != map_id:
                    continue
                if (map_id, submap, shop_type) == (0x16, 0, 1):
                    additions = self._cpu_bytes(0x15, 0xA479, 3)
                    items.extend(item for item, count in zip(additions, special_stock[:3]) if count)
                if (map_id, submap, shop_type) == (9, 0, 1) and time_value < 0x78:
                    items = [6, 0x23, 7, 0x10]
                if items:
                    shops.append((submap, shop_type, tuple(dict.fromkeys(items))))
            else:
                raise ValueError("DW4 shop directory exceeds its native bounds")
        return tuple(shops)

    def equipment_bonus(self, item_id: int) -> int:
        if self.region != "US" or not 0 <= item_id <= 0x50:
            raise ValueError("Unsupported DW4 equipment identity")
        return self._cpu_byte(0x10, 0x9DE0 + item_id)

    def equipment_traits(self, item_id: int) -> tuple[int, int, int]:
        if self.region != "US" or not 0 <= item_id <= 0x50:
            raise ValueError("Unsupported DW4 equipment identity")
        action = self._cpu_byte(0x10, 0x8D63 + item_id)
        return (self._cpu_byte(0x10, 0x8CE4 + item_id) & 0xFC, action & 0x3F, action & 0xC0)

    def equipment_passives(self, item_id: int) -> tuple[str, ...]:
        if self.region != "US":
            return ()
        if item_id in {0x0E, 0x15}:
            targets = (0x75, 0x5C, 0xA8) if item_id == 0x0E else tuple(self._cpu_bytes(0x11, 0xA73F, 8))
            names = ", ".join(name for name in map(self.monster_name, targets) if name) or "certain monsters"
            return (f"Always deals 2 damage to {names}" if item_id == 0x0E else f"Deals 1.5x damage to {names}",)
        return {
            0x0F: ("Deals 1 damage, with about a 1 in 8 instant-kill chance against susceptible enemies",),
            0x12: ("Misses about 2 attacks in 3",),
            0x13: ("Hurts you for a quarter of damage dealt, rounded down, plus 1 HP",),
            0x16: ("Attacks again if the target survives the first hit",),
            0x1C: ("Heals you for a quarter of damage dealt, rounded down, plus 1 HP",),
            0x33: ("Dodges about 1 in 6 physical hits",),
            0x36: ("Absorbs the MP of about 1 in 8 spells cast at you, while you have MP remaining",),
            0x38: ("Half the time, returns about a quarter of an ordinary physical hit to the attacker",),
            0x3C: ("Agility drops to 0",),
            0x1F: ("Defense drops to 0",),
            0x41: ("Returns a quarter of attack-spell damage, rounded down, plus 1 HP to the caster",),
            0x50: ("Doubles agility",),
        }.get(item_id, ())

    def equipment_protection(self, item_id: int) -> tuple[tuple[str, int], ...]:
        if self.region != "US" or not 0 <= item_id <= 0x50:
            return ()
        identities = self._cpu_bytes(0x13, 0xB540, 7)
        if item_id not in identities:
            return ()
        ordinal = identities.index(item_id)
        packed = self._cpu_byte(0x13, 0xB547 + ordinal // 2)
        mask = (packed >> (4 if ordinal & 1 else 0)) & 0x0F
        categories = ("Fire/explosion damage", "Ice damage", "Wind damage", "Breath damage")
        return tuple((category, 0xAA) for bit, category in enumerate(categories) if mask & (1 << bit))

    def equipment_eligible(self, item_id: int, character_id: int, hero_female: bool = False) -> bool:
        if self.region != "US" or not 0 <= character_id < 8 or not 0 <= item_id < 0x53:
            return False
        if item_id in {0x30, 0x31, 0x3B, 0x4D} and character_id not in {2, 3, 7}:
            if character_id != 0 or not hero_female:
                return False
        return bool(self._cpu_byte(0x10, 0x8C65 + item_id) & (1 << character_id))

    def arena_payout(self, amount: int, integer: int, fraction: int) -> int | None:
        if self.region != "US" or not 0 <= amount <= 50 or not 0 <= integer <= 255 or not 0 <= fraction < 10:
            return None
        coefficient = self._cpu_byte(0x18, 0xA97B + fraction)
        return amount * integer + ((amount * coefficient + 128) >> 8)

    def item_price(self, item_id: int, map_id: int, submap: int) -> int:
        if self.region != "US" or not 0 <= item_id < 0x7F:
            raise ValueError("Unsupported DW4 price identity")
        if map_id == 0x18 and item_id in {6, 0x79}:
            return 10 if item_id == 6 else 2
        if map_id == 0x22:
            return {0x17: 1, 0x4E: 4, 0x1C: 6}.get(item_id, 20)
        if (map_id, submap) == (4, 1):
            for offset in range(0, 18, 3):
                record = self._cpu_bytes(0x15, 0xB34D + offset, 3)
                if record[0] == item_id:
                    return int.from_bytes(record[1:3], "little")
        flags = self._cpu_byte(0x10, 0x8CE4 + item_id)
        return (self._cpu_byte(0x10, 0x8DE2 + item_id) & 0x7F) * (10 ** (flags & 3))

    def return_destinations(self, chapter: int, flags: bytes) -> tuple[tuple[int, str], ...]:
        if self.region != "US":
            return ()
        address = 0x95C3 if chapter >= 4 else 0x95B4
        result = []
        for index in range(40):
            map_id = self._cpu_byte(0x10, address + index)
            if map_id == 0xFF:
                return tuple(result)
            byte_index, bit = divmod(index, 8)
            if byte_index < len(flags) and flags[byte_index] & (1 << bit):
                result.append((map_id, map_title(map_id, 0, self._submap_names)))
        raise ValueError("DW4 Return destination directory is unterminated")

    def map_actor_roles(self, bank: int, pointer: int, time_value: int) -> tuple[tuple[str, str], ...]:
        if self.region != "US" or bank not in {5, 0x1C} or not 0x8000 <= pointer < 0xBFD8:
            return ()
        roles = []
        for _ in range(128):
            if not 0x8000 <= pointer < 0xBFD8:
                raise ValueError("DW4 entity record leaves its data bank")
            flags = self._cpu_byte(bank, pointer)
            if flags == 0:
                return tuple(roles)
            size = 7
            if flags & 0x18 == 0x18:
                size += int(not flags & 1) + int(not flags & 2) + (2 if not flags & 4 else 0)
            record = self._cpu_bytes(bank, pointer, size)
            night = time_value >= 0x78
            visible = bool(flags & (8 if night else 0x10))
            if visible:
                if night and not flags & 2:
                    high = record[1] & 3
                    low = record[7 if flags & 1 else 8]
                else:
                    high = (record[1] & 0x1C) >> 2
                    low = record[4]
                selector = low | (high << 8)
                roles.append({
                    1: ("Weapon merchant", "shop"),
                    2: ("Item merchant", "shop"),
                    3: ("Armor merchant", "shop"),
                    4: ("Vault keeper", "service"),
                    5: ("House of Healing", "healing"),
                    6: ("Innkeeper", "healing"),
                }.get(selector, ("NPC", "npc")))
            pointer += size
            for mask in (0x10, 8):
                if flags & mask:
                    pointer += self._cpu_byte(bank, pointer) + 1
            if len(roles) > 26:
                raise ValueError("DW4 entity record exceeds native runtime slots")
        raise ValueError("DW4 entity record is unterminated")

    def indexed_name(self, category: int, index: int) -> str:
        if self.region != "US" or not 0 <= category <= 10 or not 0 <= index < 255:
            raise ValueError("Unsupported DW4 native name identity")
        cache = getattr(self, "_name_cache", None)
        if cache is None:
            cache = self._name_cache = {}
        identity = category, index
        if identity in cache:
            return cache[identity]
        pointer = int.from_bytes(self._cpu_bytes(0x0B, 0xB057 + category * 2, 2), "little")
        for _ in range(index):
            pointer += self._cpu_byte(0x0B, pointer) + 1
        length = self._cpu_byte(0x0B, pointer)
        if not 0 < length <= 24:
            raise ValueError("Invalid DW4 native name record length")
        threshold = self._cpu_byte(0x0B, 0xBC40)
        if not 0 < threshold <= 0x80:
            raise ValueError("Invalid DW4 native name dictionary")
        symbols = []
        for encoded in self._cpu_bytes(0x0B, pointer + 1, length):
            symbols.extend(
                (encoded,) if encoded < threshold
                else self._cpu_bytes(0x0B, 0xBC63 + (encoded - threshold) * 2, 2)
            )
        decoded = []
        state = 8
        for symbol in symbols:
            if symbol >= threshold:
                raise ValueError("Invalid DW4 native name symbol")
            raw = self._cpu_byte(0x0B, 0xBC41 + symbol)
            delta = (raw - 0x7E) & 0xFF if raw & 0x80 else int(raw == 0)
            decision = self._cpu_byte(0x0B, 0xB034 + ((state + delta) & 0xFF))
            action = decision & 7
            if action:
                decoded.append(0 if action == 1 else (raw + (0x1A if action >= 3 else 0)) & 0xFF)
            state = decision & 0x18
        if len(decoded) > 24:
            raise ValueError("DW4 native name exceeds its text scratch capacity")
        name = decode_text(bytes(decoded))
        cache[identity] = name
        return name
