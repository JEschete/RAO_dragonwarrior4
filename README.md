# Dragon Warrior IV Overlay Plugin

Standalone Dragon Warrior IV integration for RetroArch Overlay. The plugin reads NES RAM and WRAM for live location, party, battle, progression, currency, travel, and treasure state. Configure a Dragon Warrior IV ROM in Plugin Manager to enable ROM-native maps and object overlays; no decompilation project is required at runtime.

## Maps and markers

- The 279 town and dungeon floors come from the Bank `$17` map directory and the game's compressed map streams, native tilesets, patterns, attributes, palettes, behaviors, and wall smoothing.
- The Main World is 256x256 tiles, Gottside is 64x64, and the Underworld is 64x54. All three use their native Bank `$0B` row tables and 16-pixel overworld tiles. The Underworld uses its dedicated world-palette row.
- The 74 static world destinations come directly from the routing table at `$08:$B7F9` and the world-position table at `$0E:$BE0B`. Repeated entrances remain separate, and marker classes come from the destination's decoded world tile.
- Indoor exits, stairs, travel doors, and keyed doors come from each decoded tile's native behavior. Behavior `$31` is not shown as a healing object because the game uses it only to alter movement timing.
- Chest positions use row-major behavior-`$04` order. Contents and collected bits come from the native directory at `$1E:$BDC2`, value table at `$1E:$BEB9`, and MSB-first flags at `$625D`. Alternate cave-state submaps follow the game's sorted-table aliasing. Ordinary items and encoded gold amounts are named exactly; eight special dispatch values remain neutral.
- The US ROM exposes 38 direct hidden rewards: furniture records at `$1E:$BCED` and item-search handlers `$A0-$AA` at `$1E:$BF59`. Their coordinates and live flags are used directly. Other scripted search handlers are omitted rather than paired with guide prose.
- Live map entities use the game's expanded slots `$06-$1F`. Every active slot receives a distinct numbered icon. Coordinates are exact, while facing, descriptor, behavior state, and runtime flags remain neutral raw fields rather than guessed NPC names.
- Images are generated lazily and cached below the framework's local plugin-state directory. ROM bytes and generated maps are never written into this repository.

## Overlay sections

Everything appears in the standard overlay rail and map window; there is no separate companion window.

- **Battle**: up to eight live enemy records with HP, MP, attack, defense, agility, status, group identity, and reward counters.
- **Journey**: chapter, time, tactics, travel unlocks, gold, casino coins, Small Medals, and packed treasure/story flag progress.
- **Party**: active and reserve membership, vitals, conditions, attributes, equipment, inventory, spells, and experience.
- **Combat log**: per-playthrough encounters, outcomes, rewards, frequent locations and enemies, and recent combat details.
- **RetroAchievements**: account progress, unlock totals, points, and the complete achievement set.

## Accuracy boundaries

- The exact map/object layout is the US retail ROM layout. Direct hidden-item tables are disabled for other detected regions.
- On US memory, `$0028` is the loaded tileset. A zero tileset selects the outdoor layer through `$0065`: `0` Main World, `1` Gottside, and `3` Underworld. Indoor map/submap IDs use `$0063/$0064`; coordinates use `$0042/$0043`.
- Static world markers represent canonical entrances, not inferred world items or NPC positions. Current NPCs, vehicles, and scripted actors appear only through live entity slots, without semantic identity guesses.
- Special chest dispatch values `$FF/$FE/$FD/$EF/$EE/$E3/$E2/$E0` are shown with their raw ROM value until each handler's gameplay result is classified.
- The available monster-name table is incomplete. Battle and analytics views learn names from decoded battle-introduction text and otherwise retain neutral enemy labels.
- Save-specific persistence uses the configured save path when available. Without one, ROM identity plus hero name forms the playthrough identity, so separate saves with the same hero name can share an archive.

## Encounter archive

The lightweight capture hook samples battles every 50 ms while RetroArch is playing. Distinct battle states record party HP/MP, enemy HP/status, and reward counters; identical high-frequency samples are collapsed.

```text
plugin-state/org.jeschete.retroarch-overlay.dragonwarrior4/
	playthroughs/<save-or-hero-identity>/
		combat-analytics.json
		encounters/
			active.json
			YYYY/MM/DD/<timestamp>-<id>.json
```

`active.json` checkpoints an in-progress fight. Reward edges can reconstruct a victory skipped by fast-forward; a fully skipped escape with no coherent enemy frame or reward evidence is not fabricated.

## Research inputs

Saved reference pages under `resources` are local research material, not runtime dependencies. Reviewed submap, item, spell, and achievement facts live in `game/data/dw4_knowledge.json`. Runtime object placement and chest ordering come from the configured ROM rather than prose sources.

## Development

Run the plugin tests from this repository with the framework source available:

```powershell
$env:PYTHONPATH = "..\..\src;."
..\..\.venv\Scripts\python.exe -m pytest -q tests
..\..\.venv\Scripts\python.exe tools\generate_knowledge.py --check
```

Regenerating knowledge requires the ignored reviewed captures under `resources`. ROMs, generated maps, save data, and patches must not be committed.
