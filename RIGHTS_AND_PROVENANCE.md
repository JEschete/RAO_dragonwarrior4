# Rights and Provenance

Locally authored plugin code is offered under MIT. That license does not cover ROMs, game assets, generated map images, patches, trademarks, saved web pages, or content inside `decomp_reference`.

## Runtime-generated material

Map images are derived locally from a user-configured Dragon Warrior IV ROM and are written only to the framework's plugin-state directory. They are not part of this repository or covered by the plugin's MIT license. The plugin does not distribute ROM bytes or extracted game graphics.

## Research references

The ignored `resources` directory may contain local saved copies of these pages:

- Data Crystal, Dragon Warrior IV (NES) and its ROM map, RAM map, SRAM map, Map Data Format, Map List, TBL, Tile Behaviors, and Values subpages: `https://datacrystal.tcrf.net/wiki/Dragon_Warrior_IV_(NES)`. The captures identify the GNU Free Documentation License through their page metadata and footer.
- RetroAchievements code notes for game 4612: `https://retroachievements.org/game/4612` and `https://retroachievements.org/codenotes.php?g=4612`.

These captures are reference material, not plugin assets, and remain ignored by Git. `game/reference_data.py` records factual identifiers, addresses, value labels, source URLs, and local availability; it does not redistribute the captured pages. Contributors must review third-party terms before deliberately adding any captured content.

`game/data/dw4_knowledge.json` is a locally generated factual index containing numeric identifiers, short value labels, source revisions, submap names, treasure records, spell flags, and public achievement metadata. It intentionally excludes page markup, images, private achievement trigger logic, ROM bytes, and extracted game graphics. `tools/generate_knowledge.py --check` verifies the artifact against reviewed local captures when those ignored source files are available.

Dragon Warrior IV, Dragon Quest IV, character names, graphics, music, and related marks remain the property of their respective rights holders. No ownership or endorsement is claimed.
