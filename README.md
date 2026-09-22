# Dragon Warrior IV Overlay Plugin

Standalone Dragon Warrior IV integration for RetroArch Overlay. The plugin reads NES RAM and WRAM to follow the current map and submap, player coordinates, party vitals, chapter, tactics, time of day, travel unlocks, currency, Return destinations, and treasure progress.

## Maps

Configure a Dragon Warrior IV ROM in Plugin Manager to enable the atlas. The plugin reads the retail MMC1 layout directly and does not require a decompilation project.

- Town and dungeon maps use the documented DW4 bitstream command format, Bank 17 map directory, native tilesets, NES patterns, attributes, palettes, tile behaviors, and wall smoothing.
- The main world, Gottside, and underworld use the documented row pointers and run-length terrain stream, drawn with the game's own overworld tileset 0 (the tileset US `$0028` reports while outdoors) at native 16-pixel tiles. The main world matches the game; Gottside and the underworld use the same tiles and day palette, which may differ from their in-game colors.
- Images are generated only when needed and cached below the framework's local plugin-state directory. PNGs use atomic replacement, so an interrupted render cannot be accepted as a valid cache entry. ROM bytes and generated images are never written into this repository.
- Map feature markers come from documented tile behavior values for treasure, stairs, exits, travel doors, healing tiles, and keyed doors.
- Hover a chest marker to see documented contents and game-detected looted state. Single-chest floors with a matching Data Crystal record show an exact reward. Multi-chest or mismatched floors show the complete documented floor inventory without guessing which reward belongs to which coordinate.
- Hidden items in drawers, pots, and search spots are placed at exact coordinates read from the US ROM's search tables in bank `$1E` (`$BCED` furniture records and `$BF59` search records), including their live looted flags. Scripted search spots whose handlers do not expose an item are paired with documented rewards on the same floor only when the floor's left/middle/right wording orders them unambiguously.

The US RAM map documents map and submap IDs at `$0063/$0064`. The saved Japanese RetroAchievements notes independently document a provisional map ID at `$0028` and player coordinates at `$0042-$0045`. The Atlas & memory section shows the selected evidence source and ROM region so a regional mismatch is never presented as exact.

## Overlay sections

Everything appears in the standard RetroArch Overlay rail and map window; there is no separate companion window. Sections are collapsible and remember whether they are open through battles and map changes.

- **Battle**: live enemy slots with observed HP, MP, attack, defense, agility, and status, plus reward counters.
- **Journey**: chapter, time of day, tactics, travel unlocks, gold, casino coins, Small Medals, treasure flags, the Return network, and Chapter 3 Lakanaba stock.
- **Party**: active party vitals; details list every recruited companion's stats, equipment, pack, battle/field spells, and experience, marking reserve members.
- **Nearby features**: this floor's documented map features and learned transitions sorted by distance and direction from the player, with looted chests marked.
- **Combat log**: per-playthrough lifetime/session battle counts, win rate, rewards, frequent locations and monsters, and a list of recent completed combats.
- **RetroAchievements**: unlock and point totals with the complete 43-achievement set.
- **Dialogue journal**: the dialogue currently on screen and a searchable history with location, first/last read times, and repeat counts. Typewriter fragments are debounced and replaced by the completed line; normalized duplicates are merged on load, and rapid clear/replay or restart echoes are suppressed.
- **Atlas & memory**: ROM atlas status, live memory layout, location evidence, playthrough identity, saved research sources, and the tile behavior legend.

## Accuracy boundaries

- On US memory, `$0028` holds the loaded tileset: indoor maps use tilesets 1-50 and the overworld reads `$00` (verified live in Burland, Burland Castle, and the overworld). `$0063/$0064` keep the last town ID outdoors, so they are only trusted when a tileset is loaded. Gottside and the underworld have not been verified yet, so outdoor locations use the Main World layer.
- Learned connections record observed map transitions. They can include scripted movement, Return, or other teleport-like transitions and are not presented as canonical exit destinations.
- Dialogue markers show where text was observed; they do not claim a stable NPC identity or position.
- The available monster-table research is incomplete. Battle and analytics views learn canonical names from the game's decoded battle-introduction text and retain stable IDs internally. Until a complete introduction is observed, they use a neutral enemy-group label rather than exposing a raw ID or attaching an unverified name, resistance, or drop.
- Save-specific persistence uses the configured save-file path when available. Without one, it falls back to ROM identity plus hero name; separate saves with the same hero name can therefore share a profile.
- Legacy unscoped journal and encounter files are left in place. New records are written only below the active playthrough directory.

## Encounter archive

The framework calls the plugin's lightweight battle capture hook every 50 ms while RetroArch is playing. Full UI snapshots remain on their normal cadence. One coherent enemy frame opens an encounter immediately, and every distinct battle state records party HP/MP, enemy HP/status, and reward counters. Identical high-frequency samples are collapsed.

Completed combats are stored as one atomic JSON file per encounter under:

```text
plugin-state/org.jeschete.retroarch-overlay.dragonwarrior4/
	playthroughs/<save-or-hero-identity>/
		dialogue-journal.json
		combat-analytics.json
		map-intelligence.json
		encounters/
			active.json
			YYYY/MM/DD/<timestamp>-<id>.json
```

`active.json` checkpoints an in-progress fight so restarting the overlay does not create a duplicate combat. Victories, defeats, and unrewarded escape/interruption results carry the evidence used for classification. If fast-forward skips every active frame, a zero-to-nonzero battle reward edge reconstructs the completed victory. A fully skipped escape with no coherent enemy frame and no rewards cannot be reconstructed from the documented memory fields and is not fabricated.

## Research inputs

All saved pages under `resources` are represented in `game/reference_data.py`: the Data Crystal overview, ROM map, RAM map, SRAM map, map data format, map list, text table, tile behaviors, values/submaps, and the RetroAchievements code-notes capture. The pages are local research material and are not runtime dependencies. Reviewed submap, treasure, item, spell, and achievement facts are stored in the versioned `game/data/dw4_knowledge.json` artifact, so clean installs retain those features without redistributing browser captures.

## Development

Run this plugin's tests from its repository with the framework source available:

```powershell
$env:PYTHONPATH = "..\..\src;."
..\..\.venv\Scripts\python.exe -m pytest -q tests
..\..\.venv\Scripts\python.exe tools\generate_knowledge.py --check
```

The Qt migration acceptance suite currently passes 98 tests. The base suite
passes 393 tests plus 32 subtests, with six waived native-only skips.

Regenerating knowledge requires the ignored reviewed source captures under `resources`. Runtime use and the normal test suite require only the tracked generated artifact.

Redistributable game-specific assets belong under `game/assets`. The tracked `resources` directory is local-only by default and remains ignored until material is deliberately reviewed. ROMs, generated maps, save data, and patches must not be committed.
