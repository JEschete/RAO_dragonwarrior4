# Rights and Provenance

Locally authored plugin code is offered under MIT. That license does not cover ROMs, game assets, generated map images, patches, trademarks, saved web pages, or content inside `decomp_reference`.

## Runtime-generated material

Map images are derived locally from a user-configured Dragon Warrior IV ROM and are written only to the framework's plugin-state directory. They are not part of this repository or covered by the plugin's MIT license. The plugin does not distribute ROM bytes or extracted game graphics.

## Research references

The ignored `resources` directory may contain local saved copies of these pages:

- Data Crystal, Dragon Warrior IV (NES) and its ROM map, RAM map, SRAM map, Map Data Format, Map List, TBL, Tile Behaviors, and Values subpages: `https://datacrystal.tcrf.net/wiki/Dragon_Warrior_IV_(NES)`. The captures identify the GNU Free Documentation License through their page metadata and footer.
- RetroAchievements code notes for game 4612: `https://retroachievements.org/game/4612` and `https://retroachievements.org/codenotes.php?g=4612`.

These captures are reference material, not plugin assets, and remain ignored by Git. `game/reference_data.py` records factual identifiers, addresses, value labels, source URLs, and local availability; it does not redistribute the captured pages. Contributors must review third-party terms before deliberately adding any captured content.

Saved guide webpages and their browser support directories are also ignored.
The original local captures are preserved, not deleted by repository cleanup.
The authored `Guide/DW4_UnifiedGuide.md` is kept unchanged as the embedded guide.

`game/data/dw4_knowledge.json` is a locally generated factual index containing numeric identifiers, short value labels, source revisions, submap names, treasure records, spell flags, and public achievement metadata. It intentionally excludes page markup, images, private achievement trigger logic, ROM bytes, and extracted game graphics. `tools/generate_knowledge.py --check` verifies the artifact against reviewed local captures when those ignored source files are available.

Normal runtime loaders use that validated knowledge artifact only. Saved HTML
parsers live in the development-only knowledge builder and cannot supply an
unreviewed fallback when the runtime artifact is missing or malformed.

## Development toolchain

The unrelated cc65 source tree was relocated outside the plugin to
`F:/tools/cc65-dw4-reference` on 2026-10-04. All 4,151 preserved compiler files
were checked against their pre-migration SHA-256 hashes, including the original
compiler README, license, and third-party notices. A migration manifest remains
with that local archive. cc65 is not a runtime or build requirement for this
Python plugin; its original terms are not replaced by the plugin's MIT license.

Dragon Warrior IV, Dragon Quest IV, character names, graphics, music, and related marks remain the property of their respective rights holders. No ownership or endorsement is claimed.
