# Dragon Warrior IV Qt Migration Status

Status: Complete under the revised correctness-only migration gate

Started: 2026-09-13

## Architecture

Update 2026-09-14: the sidecar companion was removed. Its Atlas, Party, Journey,
Journal, Combat Log, and Archive features are now keyed overlay sections and
the shared map window; the dashboard bridge, its JSON documents, and the
`dashboard.py` launcher no longer exist. The history below describes the
migration as it stood before that change.

Dragon Warrior IV remains toolkit-neutral. The base application owns all
PySide6 widgets and contains no Dragon Warrior IV identifiers, map rules,
feature IDs, progression rules, or labels.

## Completed

- Every overlay section and action has a stable key and uses the shared `area`,
  `party`, `goals`, or `urgent` roles.
- Real overworld, battle, and memory-failure snapshots render through the keyed
  Qt panel host; expanded Party Details and native section identity survive live
  value updates.
- The generic Qt sidecar renders all six declared workspaces: Atlas, Party,
  Journey, Journal, Combat Log, and Archive.
- Atlas uses the shared `QGraphicsScene` map view with generated local and world
  images, live player movement, zoom and pan, synchronized feature selection,
  source/evidence details, plugin-declared layer controls, completion state, and
  a retained popout map.
- Main World, Gottside, and Underworld remain explicit persisted selections
  because the reviewed sources do not justify guessing the live outdoor layer.
- Game-detected feature completion takes precedence over manual state. Manual
  state is isolated by playthrough, and legacy unscoped completion migrates to
  the first identified playthrough.
- Party cards update HP, MP, conditions, stats, equipment, inventory, and spells
  in place. Journey renders chapter progress, travel, resources, Return state,
  Lakanaba stock, and the complete achievement catalog.
- Journal and Combat Log provide persistent search, sorting, retained selection,
  and master/detail navigation. Full encounter JSON remains lazy-loaded only for
  the selected record.
- Workspace, search, sort, map zoom, splitter, layer visibility, and window-size
  state is persisted separately from game progress.
- Missing, malformed, stale, or partially written documents retain the last
  valid state or show an explicit waiting diagnostic. Missing map images replace
  stale scenes with an unavailable state.
- The bridge preserves atomic static/live/control publication and digest-based
  suppression, launches one generic Qt process, throttles crash restarts, honors
  user-close suppression, and uses bounded terminate/kill escalation during
  plugin switches and shutdown.
- Adapter activation and deactivation reset playthrough-bound runtime services,
  close the sidecar, and re-enable it only for a new content session.
- Generated area and world PNGs use same-directory atomic
  replacement so interrupted renders cannot become valid cache entries.
- Dialogue debounce, duplicate normalization, replay suppression, journal
  persistence, 50 ms encounter capture, coherent-frame opening, duplicate-frame
  collapse, checkpoint/resume, reward-edge reconstruction, combat analytics,
  US/JP evidence labels, and generated-knowledge verification remain covered.
- The complete plugin suite passes with 98 tests and no warnings or skips.
- `tools/generate_knowledge.py --check` passes.

## Host Evidence

The complete base suite passes with 393 tests, six waived native-only skips, and
32 subtests. The generic dashboard store and Qt views cover schema validation,
partial-file recovery, all workspace kinds, search/sort, map controls, UI-state
restoration, lazy details, waiting/error views, and close persistence.

Installer, accessibility, native-platform, and performance acceptance are not
phase gates under decisions D-010 through D-014. An offscreen 1260x790 Journey
capture showed no clipping or overlap; its square glyphs are the documented
offscreen backend's missing-font limitation, not missing content.