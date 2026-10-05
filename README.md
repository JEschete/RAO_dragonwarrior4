# Dragon Warrior IV Overlay

Read-only Dragon Warrior IV plugin for RetroArchOverlay. The US NES ROM is
required for ROM-backed maps, names, catalogs, and arena simulation; ROMs,
save data, and extracted graphics are not distributed.

## Setup

Install the RetroArchOverlay host and its dependencies, then select this plugin
in Plugin Manager and configure `rom_path` with a locally owned US ROM.
The manifest lists recognized NES cores and content identities. Unsupported
ROM layouts remain unavailable rather than being decoded with US addresses.
Generated map images belong in the host-provided plugin state directory.

The optional arena predictor additionally requires the packages in
[requirements-arena.txt](requirements-arena.txt). The cc65 compiler is not a
plugin runtime or build dependency.

## Poker Helper

The Poker panel appears automatically at the US Endor poker table. It reads
the complete 53-card deck without writing memory or sending controller input.
For draw poker it evaluates all 32 hold combinations against the committed
replacement cards, recommends holds, and shows the held/draw counts and exact
result of the current selection. Equally valuable draws prefer fewer hold changes.

Double-or-nothing displays the dealer and all four face-down cards, marking each
as win, tie, or loss and recommending a winning card when one exists. A chosen
joker beats every ordinary dealer card; a dealer joker is an automatic loss.
Ties preserve the stake but start another shuffled round. At the collection
prompt the helper also reads the initialized eight-round arrangement schedule.
It recommends continuing only when the next round guarantees at least one
winning choice, and collecting before special rounds that do not guarantee a
win. The winning-card recommendation includes the same after-win stop advice.
The first offer has no initialized schedule, so it recommends collecting;
invalid or changing schedules also fail closed. The next exact cards are not
predicted, and the winning card still needs to be selected after dealing.

Deck order opens a read-only view of every committed card. Advice updates while
moving the cursor or toggling holds. Rendering flags and the ROM's temporary
payout-blink values do not suppress card advice; a stake caught during blinking
may briefly read "updating" rather than displaying an incorrect amount. Changed,
incomplete, or invalid decks clear advice, as do leaving the table and failed
game-memory snapshots. No future shuffle or guaranteed winning streak is claimed.

## Structure

| Component | Responsibility |
| --- | --- |
| `plugin.py` | Host entry point and ROM setup |
| `game/adapter.py` | Activation, coherent memory reads, and snapshot orchestration |
| `game/map_snapshot.py` | Live map capture, entities, animation, and display state |
| `game/presentation.py` | Party, catalogs, objectives, guide, and other panel sections |
| `game/poker.py` | Stable poker table reads, native hand rules, exact holds, and double-or-nothing advice |
| `game/rom_assets.py` | Stable ROM facade and compatibility exports |
| `game/rom_reader.py` | Cartridge validation and bounded byte access |
| `game/rom_map_data.py` | Map decoding, layout, and graphics data |
| `game/rom_maps.py` | Rendered layers and generated-image caches |
| `game/rom_catalog.py` | Monster, equipment, shop, growth, and encounter catalogs |
| `game/rom_features.py` | Rewards, hazards, reachability, and map routes |
| `game/knowledge_builder.py` | Development-only parsing of research captures |

Battle, growth, equipment comparison, objectives, and entity decoding retain
their focused modules. Existing facade imports and adapter behavior are kept.
Runtime reference loaders consume the validated `game/data/dw4_knowledge.json`
artifact only; missing or malformed knowledge does not fall back to saved HTML.

## Verification

From the RetroArchOverlay host root, using its Python environment:

```powershell
python -B -m pytest plugins/RAO_dragonwarrior4/tests -p no:cacheprovider -o "pythonpath=src plugins/RAO_dragonwarrior4 plugins/RAO_dragonwarrior4/tests"
python -B plugins/RAO_dragonwarrior4/tools/generate_knowledge.py --check
python -B plugins/RAO_dragonwarrior4/tools/verify_rom.py --rom "path/to/owned/Dragon Warrior IV (USA).nes" --timeout 120
```

Knowledge regeneration requires the ignored local `resources` captures; normal
operation and packaged tests do not. Raw guide webpages and their support files
also stay local and ignored. The authored unified guide remains in `Guide`.
Set `RAO_DW4_TEST_ROM` to a locally owned US ROM to include the opt-in native
arena instruction/parity tests without building a local disassembly checkout.
It also enables poker classifier/payout, redraw-mask, and double-or-nothing
comparison checks against the original ROM instructions. Safe-stop tests run
the original arrangement routine across cycle positions and include
unwinnable special-round examples.
The unrelated cc65 source tree and its original notices were preserved outside
the plugin at `F:/tools/cc65-dw4-reference` during the local cleanup.

## Coverage And Rights

[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) records delivered behavior
and unresolved verification. The full backlog in [Ideas.md](Ideas.md) remains
unchanged and is not claimed complete by this structural cleanup.
See [docs/ARENA_PREDICTOR.md](docs/ARENA_PREDICTOR.md) for simulation limits and
[RIGHTS_AND_PROVENANCE.md](RIGHTS_AND_PROVENANCE.md) for research and asset terms.
