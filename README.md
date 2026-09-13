# Dragon Warrior IV Overlay Plugin

Standalone Dragon Warrior IV integration for RetroArch Overlay. The plugin reads NES RAM and WRAM to follow the current map and submap, player coordinates, party vitals, chapter, tactics, time of day, travel unlocks, currency, Return destinations, and treasure progress.

## Maps

Configure a Dragon Warrior IV ROM in Plugin Manager to enable the atlas. The plugin reads the retail MMC1 layout directly and does not require a decompilation project.

- Town and dungeon maps use the documented DW4 bitstream command format, Bank 17 map directory, native tilesets, NES patterns, attributes, palettes, tile behaviors, and wall smoothing.
- The main world, Gottside, and underworld use the documented row pointers and run-length terrain stream. Because the saved references do not document either their metatile graphics or a reliable live outdoor-layer discriminator, these layers use a clearly labeled cartographic terrain rendering and an explicit persisted world selector rather than invented art or guessed state.
- Images are generated only when needed and cached below the framework's local plugin-state directory. PNGs use atomic replacement, so an interrupted render cannot be accepted as a valid cache entry. ROM bytes and generated images are never written into this repository.
- Map feature markers come from documented tile behavior values for treasure, stairs, exits, travel doors, healing tiles, and keyed doors.
- Hover a chest marker or its feature row to see documented contents and live/manual completion state. Single-chest floors with a matching Data Crystal record show an exact reward. Multi-chest or mismatched floors show the complete documented floor inventory without guessing which reward belongs to which coordinate.
- Chest and objective markers can be marked complete from the feature row or detail panel. Manual state is stored in the companion controls file; game-detected looted flags take precedence and are labeled separately.

The US RAM map documents map and submap IDs at `$0063/$0064`. The saved Japanese RetroAchievements notes independently document a provisional map ID at `$0028` and player coordinates at `$0042-$0045`. The companion shows the selected evidence source and ROM region so a regional mismatch is never presented as exact.

## Companion

The plugin launches a separate PySide6 Cartographer's Companion by default. The plugin remains toolkit-neutral: it publishes versioned static, live, control, and presentation documents through an isolated JSON bridge, while the framework's generic Qt dashboard owns all widgets. The small `dashboard.py` entrypoint remains only as a compatibility launcher. The companion provides six workspaces:

- **Atlas**: current generated map, centered live player marker, zoom and pan, player-relative feature ordering, persistent plugin-declared layer controls, learned floor transitions, observed dialogue locations, documented chest contents, manual completion controls, source/evidence details, and a synchronized popout map.
- **Party**: active and reserve companions with HP, MP, level, conditions, experience, five base stats, named carried/equipped items, and learned battle/field spells.
- **Journey**: chapter timeline, travel state, tactics, time, gold, casino coins, medals, treasure flags, Return network, Chapter 3 Lakanaba stock, and the complete 43-achievement RetroAchievements set with points.
- **Journal**: searchable and sortable dialogue history with location, first/last read times, and repeat counts. Typewriter fragments are debounced and replaced by the completed line; normalized duplicates are merged on load, and rapid clear/replay or restart echoes are suppressed. Entries persist under the plugin state directory even when the companion window is closed.
- **Combat Log**: active fast-capture status, factual enemy-stat observations, per-playthrough lifetime/session analytics, and searchable/sortable completed encounters. Selecting a combat lazily loads its full party, enemy, reward, result-evidence, and distinct-state timeline from disk.
- **Archive**: live memory/ROM confidence, all saved research sources, and the tile behavior legend.

Closing the companion suppresses relaunching it for the rest of that plugin session. The standard RetroArch Overlay map window and information rail continue to work independently.

Switching to another game closes the companion and resets its session-bound observers. Switching back creates a fresh content session and permits the companion to open again. Workspace, search, sort, layer visibility, zoom, splitter, and window-size preferences are stored under a separate `ui` control namespace and do not alter per-playthrough game progress.

Live coordinates, dialogue, party vitals, currency, time, treasure status, and journal entries update retained widgets in place. Full workspace reconstruction is reserved for structural changes such as moving to another map, changing the active party roster, or advancing chapters.

## Accuracy boundaries

- The saved references do not identify a reliable RAM discriminator for the main world, Gottside, and underworld. The companion therefore persists an explicit world selection and labels that evidence instead of guessing.
- Learned connections record observed map transitions. They can include scripted movement, Return, or other teleport-like transitions and are not presented as canonical exit destinations.
- Dialogue markers show where text was observed; they do not claim a stable NPC identity or position.
- The available monster-table research is incomplete. Battle and analytics views retain stable hexadecimal monster IDs and observed live stats rather than attaching unverified names, resistances, or drops.
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

The Qt migration acceptance suite currently passes 97 tests. The base suite
passes 393 tests plus 32 subtests, with six waived native-only skips.

Regenerating knowledge requires the ignored reviewed source captures under `resources`. Runtime use and the normal test suite require only the tracked generated artifact.

Redistributable game-specific assets belong under `game/assets`. The tracked `resources` directory is local-only by default and remains ignored until material is deliberately reviewed. ROMs, generated maps, save data, and patches must not be committed.
