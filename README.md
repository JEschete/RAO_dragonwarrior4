# Dragon Warrior IV Overlay Plugin

Standalone Dragon Warrior IV integration for RetroArch Overlay. The plugin reads NES RAM and WRAM to follow the current map and submap, player coordinates, party vitals, chapter, tactics, time of day, travel unlocks, currency, Return destinations, and treasure progress.

## Maps

Configure a Dragon Warrior IV ROM in Plugin Manager to enable the atlas. The plugin reads the retail MMC1 layout directly and does not require a decompilation project.

- Town and dungeon maps use the documented DW4 bitstream command format, Bank 17 map directory, native tilesets, NES patterns, attributes, palettes, tile behaviors, and wall smoothing.
- The main world, Gottside, and underworld use the documented row pointers and run-length terrain stream. Because the saved references do not document their metatile graphics, these layers use a clearly labeled cartographic terrain rendering rather than invented native art.
- Images are generated only when needed and cached below the framework's local plugin-state directory. ROM bytes and generated images are never written into this repository.
- Map feature markers come from documented tile behavior values for treasure, stairs, exits, travel doors, healing tiles, and keyed doors.
- Hover a chest marker or its feature row to see documented contents and live/manual completion state. Single-chest floors with a matching Data Crystal record show an exact reward. Multi-chest or mismatched floors show the complete documented floor inventory without guessing which reward belongs to which coordinate.
- Chest and objective markers can be marked complete from the feature row or detail panel. Manual state is stored in the companion controls file; game-detected looted flags take precedence and are labeled separately.

The US RAM map documents map and submap IDs at `$0063/$0064`. The saved Japanese RetroAchievements notes independently document a provisional map ID at `$0028` and player coordinates at `$0042-$0045`. The companion shows the selected evidence source and ROM region so a regional mismatch is never presented as exact.

## Companion

The plugin launches a separate Cartographer's Companion by default. It follows the Vagrant Story plugin's isolated JSON bridge pattern and provides six workspaces:

- **Atlas**: current generated map, centered live player marker, zoom, interactive ROM-derived feature markers, documented chest contents, manual completion controls, and a synchronized popout map with independent zoom.
- **Party**: active and reserve companions with HP, MP, level, conditions, experience, and inventory counts.
- **Journey**: chapter timeline, travel state, tactics, time, gold, casino coins, medals, treasure flags, and Return network.
- **Journal**: searchable, newest-first dialogue history with location, first/last read times, and repeat counts. Typewriter fragments are debounced and replaced by the completed line; normalized duplicates are merged on load, and rapid clear/replay or restart echoes are suppressed. Entries persist under the plugin state directory even when the companion window is closed.
- **Combat Log**: active fast-capture status and newest-first completed encounters. Selecting a combat lazily loads its full party, enemy, reward, result-evidence, and distinct-state timeline from disk.
- **Archive**: live memory/ROM confidence, all saved research sources, and the tile behavior legend.

Closing the companion suppresses relaunching it for the rest of that plugin session. The standard RetroArch Overlay map window and information rail continue to work independently.

Live coordinates, dialogue, party vitals, currency, time, treasure status, and journal entries update retained widgets in place. Full workspace reconstruction is reserved for structural changes such as moving to another map, changing the active party roster, or advancing chapters.

## Encounter archive

The framework calls the plugin's lightweight battle capture hook every 50 ms while RetroArch is playing. Full UI snapshots remain on their normal cadence. One coherent enemy frame opens an encounter immediately, and every distinct battle state records party HP/MP, enemy HP/status, and reward counters. Identical high-frequency samples are collapsed.

Completed combats are stored as one atomic JSON file per encounter under:

```text
plugin-state/org.jeschete.retroarch-overlay.dragonwarrior4/
	encounters/
		active.json
		YYYY/MM/DD/<timestamp>-<id>.json
```

`active.json` checkpoints an in-progress fight so restarting the overlay does not create a duplicate combat. Victories, defeats, and unrewarded escape/interruption results carry the evidence used for classification. If fast-forward skips every active frame, a zero-to-nonzero battle reward edge reconstructs the completed victory. A fully skipped escape with no coherent enemy frame and no rewards cannot be reconstructed from the documented memory fields and is not fabricated.

## Research inputs

All saved pages under `resources` are represented in `game/reference_data.py`: the Data Crystal overview, ROM map, RAM map, SRAM map, map data format, map list, text table, tile behaviors, values/submaps, and the RetroAchievements code-notes capture. The pages are local research material and are not runtime dependencies; stable facts needed by the plugin are represented in locally authored code, while the Values capture optionally enriches floor names when present.

## Development

Run this plugin's tests from its repository with the framework source available:

```powershell
$env:PYTHONPATH = "..\..\src;."
..\..\.venv\Scripts\python.exe -m pytest -q tests
```

Redistributable game-specific assets belong under `game/assets`. The tracked `resources` directory is local-only by default and remains ignored until material is deliberately reviewed. ROMs, generated maps, save data, and patches must not be committed.
