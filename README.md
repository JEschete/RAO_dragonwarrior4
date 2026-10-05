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

## Structure

| Component | Responsibility |
| --- | --- |
| `plugin.py` | Host entry point and ROM setup |
| `game/adapter.py` | Activation, coherent memory reads, and snapshot orchestration |
| `game/map_snapshot.py` | Live map capture, entities, animation, and display state |
| `game/presentation.py` | Party, catalogs, objectives, guide, and other panel sections |
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
The unrelated cc65 source tree and its original notices were preserved outside
the plugin at `F:/tools/cc65-dw4-reference` during the local cleanup.

## Coverage And Rights

[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) records delivered behavior
and unresolved verification. The full backlog in [Ideas.md](Ideas.md) remains
unchanged and is not claimed complete by this structural cleanup.
See [docs/ARENA_PREDICTOR.md](docs/ARENA_PREDICTOR.md) for simulation limits and
[RIGHTS_AND_PROVENANCE.md](RIGHTS_AND_PROVENANCE.md) for research and asset terms.
