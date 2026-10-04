# DW4 Implementation Coverage

Updated: 2026-10-04. The original [Ideas.md](Ideas.md) is unchanged.

**The complete 105-entry backlog is not finished.** This ledger records actual
delivery and unresolved work; it does not redefine or reduce the requirements.
Entries 064-084 and archive/outcome parts of 058-063 are superseded by the
explicit removal requirement 100, not retained as hidden features.

## Overlay Cleanup

- Removed persistent and observed-name learning caches, capability/diagnostic
  panels, the separate exit-route list, and user-facing decoder/disclaimer prose.
  Enemy names come directly from the configured ROM. Tactics stay in AI knowledge.
- Combatants use one full-width party column in the field and two columns only
  during combat. XP progress is gold; HP/MP retain their separate meters.
- Collapsed actions wrap in plugin order; expanded details occupy a full row.
  Guide shortcuts are direct heading jumps, not expandable detail buttons.
- Shop summaries retain every actual upgrade for recruited active/reserve
  characters regardless of affordability. Expanded rows separate stat changes
  from special-effect tradeoffs; affordability names its currency.
- Bestiary cards separate HP/MP, combat stats, rewards, drops, and all four
  resistance strengths. The full catalog is alphabetized and filterable, and
  current/local monster identities are deduplicated without losing boss names.
- Guide contents, search, previous/next matches, and chapter/location jumps
  preserve reading state across live snapshots. Light/dark document colors and
  search icons have rendered-pixel and formatting checks.
- Hazard reachability starts at actual entrances, valid arrivals, or observed
  player positions, not arbitrary exterior padding. Out-of-bounds markers are
  removed; collectible and locked-door rewards remain visible.
- Map/search tooltips use game language. Encounter-zone titles appear only on
  hover, with formation chances. An open compatible atlas stays open while a
  position is unavailable; a genuine disconnect still retires it.
- Disassembly sources were not edited. Desktop Qt regressions and screenshot
  checks cover 360px/760px and both themes. Shared fixed-DPI geometry tests run
  offscreen; no fresh emulator teleport capture is claimed by this cleanup.

## Primary Requirements

| Entry | Delivered Behavior | Remaining Verification/Limits |
| --- | --- | --- |
| 097 | Full-width party in the field, party/enemy columns only in combat, gold XP progress, separate numeric HP/MP meters, formation order, active guests, 214 ROM enemy names, ROM-backed maxima including special HP setup, and explicit infinite-MP bars/accessibility. | The party mirror carries derived attack/defense, not replacement HP/MP at `$7211/$7213`; live SRAM timing still needs emulator trace comparison. |
| 098 | Native field clearing, setup/group scene rejection, persistent party and captured FCEUX victory/escape return checks. | Player-party defeat and fresh Mesen/per-core transition parity remain unverified. |
| 099 | Legacy lower Party section and Party Details action removed. | No legacy controls remain in the adapter. |
| 100 | Recorder, capture hook, encounter log, analytics implementation and controls removed; no combat archive writes. | Existing user archives are deliberately preserved. |
| 101 | Embedded local Markdown guide with tables, stable heading anchors, contents selector, search/match navigation, chapter/location jumps, retained reading position, and missing-file diagnostic. | No external guide window or copied guide artifact. |
| 102 | Native merchant/House of Healing/inn/vault roles/icons replace slot numbers/raw fields; graphics/facing separated; native hide/room checks; acquired boat/balloon slots and distinct icons. | Personal names for unclassified story NPCs remain unresolved; neutral NPC role is retained, not a guessed name. |
| 103 | Native local-map context, proper coordinates, bounds checks, compatible in-place map refresh, live area palettes, and dimension/identity-checked live SRAM tiles for matching buffers up to 2 KiB. | Larger or mismatched live buffers use ROM layouts; paused-game coordinate comparisons across all maps still required. |
| 104 | Native town stock/currencies, special stock, complete roster, current-room observed merchant versus catalog/other-floor qualification, and town/world clearing. | Full scripted service availability remains unclassified; catalog affordability does not claim a hidden merchant is available. |
| 105 | Per-character equipped baseline, eligibility, curses, signed stat deltas, restoration, actual armor/shield/helmet protection priority, and inspected recoil/recovery, KO/miss, target-specific damage, followup, evasion and damage-return gains/losses. | Remaining unclassified effects and captured battle timing need further consumer tracing; verdicts remain qualified rather than ranking by ATK alone. |

## Audit Disposition

| Entries | Status |
| --- | --- |
| 001, 003, 006, 009-012 | Implemented: gold boundaries, formation/availability, explicit unknown locations, gender for eligibility, and vault units. |
| 004-005 | Implemented active/reserve short guest records and selected alternate hero record; complete ninth-record lifecycle not certified. |
| 002 | Typed, deduplicated catalog of 177 native chest/search/furniture/inspected conditional reward flags; empty/trap chests and unrelated/unclassified bits excluded; missing flag bytes remain unknown. Conditional scripted rewards are not a blanket lifetime total. |
| 007-008 | Initialization/known-layout gates plus final map/chapter/roster consistency reads implemented. Unsupported partial-read transports remain degraded; complete captured transition certification and Japanese-layout support unfinished. |
| 013 | Native chapter-specific Return unlocks and atlas navigation implemented through generic host actions. Manual destination/floor browsing persists across live updates and Center resumes the player view; unavailable layers receive no inert action. |
| 014 | Native 120-movement-update activation, expiry/transition clearing, character/NPC form classification, and masked sprite-definition identity presented in Journey. Opaque sprite IDs are not mislabeled as monster names. |
| 015-022 | Manifest matching, exact core aliases, empty-title rejection, supplied-CRC matching, lazy initial activation, capability errors, atlas failure isolation, progress refresh/provider containment implemented. CRC-unavailable identity remains unverified. |
| 023-029, 031-033 | Native map rollover, cartridge/PRG checks, factory layout gating, chest gating, destination bounds, routing terminator, damaged PNG recovery, preservation of other cache versions, bounded floor/name caches implemented. |
| 035, 037, 039 | Unknown collection state, distinct uncertain chest marker, bounded static feature templates projected against live flags, and live time/world/story area palette variants implemented. Same-atlas refresh preserves map windows, zoom, filters, and pan. |
| 038 | Native room-class roof/interior views, all-room cutaway, and `$07BA=4/$0520` reveal-tile exception implemented with distinct cache identities and pixel regression. Captured visual parity remains unverified. |
| 030 | Native forward/reverse world scan-entry decoding implemented and used for entrance classification; exhaustive equivalence covers all 73,088 world tiles and 63/64, 191/192 boundaries. |
| 040 | Native palette/pattern frames, shape-$0E graphics bank, group timing, overlapping-destination priority, pending-NMI committed frame handling and inhibit gates implemented. Static low-motion views and quiet loader reconciliation retained. Six captured field checkpoints match 384 pattern bytes; all-floor/cross-core timing parity remains open. |
| 034, 036 | Feature errors surface; fixed-width invalid hidden records/masks retain valid neighbors with deduplicated diagnostics; hard bounds count examined rows, including rejected records. Truncated/unterminated streams remain hard failures. |
| 041 | Matching indoor tile buffers up to 2 KiB render live with digest-keyed images; door/chest markers use the same snapshot. Dimensions and map identity are rechecked after reads. Other buffer contracts remain unverified. |
| 042, 050 | Verified merchant/inn/vault roles implemented from native entity record selectors; full named entity identities unfinished. |
| 043 | All eight special chest values classified from actual dispatcher/handler instructions: empty, two trap battles, and five item-grant outcomes. Scripted rewards retain condition notes. |
| 046-047 | Hazard/direction markers, native key hierarchy, exact reserve-roster gate, alive/nonparalyzed Chapter 4 ID-9 magic-door bypass, and live StepGuard protection only for swamp/barrier implemented. Unknown optional inputs remain qualified. |
| 044 | All 12 inspected conditional search dispatches now projected. Item/gold rewards retain native gates; Iron Safe, passage and travel events use separate markers/live tile qualification and never inflate loot totals. Special-chest event gates remain distinct; further scripted prerequisites stay qualified. |
| 045 | 70 boundary/special exits plus 531 local walking connections from 584 per-floor records, exact source/arrival ordinals, direct coordinate and story/time overrides. Marker details and atlas actions work; 2,124 variant cases and one fresh doorway capture pass. `$09:07/$0D:02` source mismatches and some world-entry semantics remain unknown. |
| 048-049 | Uninitialized actor suppression, context/layer clearing, bounds checks, actual `$7020,X & $90` hide flags, and `$7140,X & $E0` room-class checks implemented; every world actor contract not certified. |
| 051-052, 054, 057 | Field clearing, full-width stats, native setup/group consistency, inspected boss display/profile alias and diagnostics implemented. Captured scenes no longer become ghost enemies. Complete battle-mode semantics remain open. |
| 053 | Party-mirror timing remains unresolved; mirrored words are ATK/DEF, not HP/MP. |
| 055 | Superseded by the explicit cache-removal request: persisted and observed-name learning caches and their controls are removed. Names resolve directly from the configured ROM; existing user cache files are not deleted. |
| 056 | Native Sleeping, Confused, Silenced, and Paralyzed labels implemented from actual selector/message consumers. Ordinary `$C0` presence flags are not treated as paralysis; stacked/removed effects have regressions. Other bits remain unclassified. |
| 058-063 | Archive/outcome/timeline portions superseded. Current snapshot-based live decoding remains; transformation generations and rewind-aware live presentation need additional verification. |
| 064-084 | Superseded by 100: affected implementation and user controls removed rather than expanded. |
| 085 | Current-chapter rules cover all five chapters: Flying Shoes, voice/Nectar, tournament, tunnel funding, Chapter 4 item retrieval, lighthouse and Padequia. Exact verified floor links and distinct retrieval/affordability/completion gates. The full story quest graph remains unresolved. |
| 086 | Native carried-item transition-loss warnings implemented for Iron Safe/Flying Shoes/Sphere of Silence, with current possession/chapter clearing. Full uncollected-treasure/shop missable lifecycle unresolved; Iron Claw closure timing is not invented. |
| 087 | Eligibility/stat/curse, actual protection priority and inspected passives, including Bolero MP-drain eligibility, exact integer rounding and target lists. Remaining unclassified effects retain qualified verdicts. |
| 089 | Filterable 214-record native bestiary with current-enemy context, HP/MP, full-width stats, XP/gold, masked drop identities, nominal selected-enemy drop probabilities, and named innate susceptibility implemented. Optional sprites and live resistance modifiers remain unfinished. |
| 088 | Native XP threshold subtraction, alternate-hero index-zero mapping, level-99 exclusion, and five native named spell-learning tables implemented in the existing party panel. Variable intelligence/random learning checks are qualified, not promised at a fixed level. |
| 090 | Land/indoor pools, zones, masks, groups and normalized entry chances. Native next-land-step threshold includes terrain, movement, Repel strength/expiry and scent with exact word wrapping; all 23 captured pre-RNG checks match. Ship scratch-state selection and final mixed-group count odds remain unresolved. |
| 091 | Native two-bit training ranks, current-enemy/catalog views, rank/update consumers and verified Try Out/Use No MP/special-mode dispatch constraints implemented. No guide-derived accuracy percentage or exact action prediction. Captured learning-update certification remains unfinished. |
| 092 | Native prices/currencies, optional targets, arena amount/selected-entry/multiplier display, conditional fresh-stake payout rounding up to 50, and an arena-only button running 100 native-ROM simulations with per-slot win/draw estimates and cancellation. Carry-over arithmetic and live timing calibration remain qualified; no winning guarantee. |
| 093 | Native local formation, coin, boat/balloon and named carried-equipment evidence attached to public achievement targets. No private trigger logic or local unlock claim; server remains authoritative. Additional unverified prerequisites remain unclaimed. |
| 094 | Carried items, exchange balance and validated pickup flags stay separate. Historical redeemed total explicitly unavailable: the inspected save stores no redemption history. Balance changes cannot fabricate pickup/redemption evidence. Complete conditional pickup correspondence remains unresolved. |
| 095-096 | Curated ASM contracts, synthetic corruption fixtures and bounded native/replay gates implemented. Legacy set passes 31 snapshots (2 battle, 25 field, 4 scenes) and 384 pattern bytes. Isolated internally driven FCEUX victory/escape captures are verified; player-party defeat and fresh Mesen/per-core certification remain unfinished. |

## Verification

- Latest configurable arena acceptance: **370 combined plugin/affected framework
  tests passed**, including numeric entry at 360px/760px in both themes, live
  refresh preservation, exact custom seed counts, Cancel, the stale-PPU graphics
  loop and the pictured Giant Bantam/Flythrope/Pteranodon matchup. Modified modules
  have no editor diagnostics; no disassembly source was changed.
- Latest arena acceleration acceptance: **261 plugin tests passed**, including
  actual-ROM CPU/RAM/RNG parity, all-child cancellation and error cleanup,
  aggregated progress, complete seed coverage and network-free UI clicks.
- Latest overlay cleanup acceptance: **240 plugin tests passed** and **89 affected
  shared Qt tests passed**. Shared geometry fixtures use the offscreen platform
  to avoid desktop-DPI assumptions. Screenshot, pixel, and link-format checks
  cover the shipped guide and bestiary at 360px/760px in both themes. Modified
  runtime modules have no editor diagnostics.
- Arena predictor: focused regressions cover native RNG output/flags, stat loading,
  permitted special actions, ten-round draws, 100-outcome accounting, duplicate and
  unused slots, coherent captures, stale-worker cancellation and arena-only
  visibility. UI clicks queue capture on the polling worker without network I/O;
  up to four headless child processes partition the requested seed range, with aggregated
  progress and whole-group cancellation/error cleanup. The optimized reference-ROM
  four-Slime batch completed in 27.2 seconds versus the original 109.2 seconds,
  preserving wins 19/37/18/26 and zero draws. Immutable bank reuse and direct
  workspace blocks have CPU/RAM/RNG differential checks. Remaining native code
  runs through py65 in private memory; display/input timing is sampled.
  The arena-only Simulations input accepts 1-100,000 (default 100), preserves
  edits across live refreshes, locks while running, and offers Cancel without
  leaving the arena. Progress and outcomes use the requested count. The pure
  graphics append at bank 1D `$BEC4` is bypassed to avoid stale PPU queues without
  an NMI consumer; the exact loop and pictured three-entry lineup have regressions.
  No live probability calibration is
  claimed. See [docs/ARENA_PREDICTOR.md](docs/ARENA_PREDICTOR.md).
- Combined plugin/shared-framework acceptance: **541 passed, 7 skipped**.
  The final annotation-only Qt model repair additionally passes all seven
  plugin Qt presentation checks and Pylance signature compatibility; its
  editor diagnostics are clear. New permanent regressions cover
  native XP aliasing/level cap, mixed snapshots, spell descriptors, resistance
  polarity, rare drop rank, typed pickup flags, Final Key doors, infinite MP,
  actor visibility, formation time/group expansion, and alternate-view pixels.
  Broad tests were deferred until the end of this implementation pass.
  Editor diagnostics are clear for the modified modules.
- The tracked knowledge artifact still passes `tools/generate_knowledge.py --check`.
- Qt screenshot/pixel checks cover 360px and 760px overlay widths, meter colors,
  non-overlapping columns, keyed updates, and functional guide navigation.
- `tools/verify_rom.py` runs in a bounded child process against a locally owned
  ROM. The exact reference SHA-256 is
  `373be958cb33651fe599a6b282d2a232eb3b99559c258b2c70b53df0fa31e34a`.
- The ROM gate successfully decodes 279 floors, three worlds at 256x256,
  64x64, and 64x54, 74 destinations, 214 names/vitals, 63 native shop records,
  214 complete bestiary records, six representative day/night palette renders,
  and 38 direct hidden rewards. This is not byte/pixel equivalence certification
  against emulator output for every floor.
- Extended native gate also validates five spell-learning tables, 177 reward
  flag identities, 32 direct medal pickup flags, all 214 resistance/drop records,
  2,560 chapter/grid/time land pools with special-world boundaries and native
  predefined groups, and pixel-distinct equal-size roof/cutaway renders.
- Latest gate additionally verifies all **73,088** world point lookups against
  full rows and **70** valid directed local/special/world exit records, 1,395 indoor chapter/floor cases (235 eligible), and 192 normalized zone/mask cases. New regressions
  cover native protection masks, hidden-record recovery/bounds, casino currency,
  world vehicles, condition stacks, arena clearing, reserve/key/StepGuard rules,
  reveal pixels, transformation class/expiry, native palette inputs and quiet
  static-view frame updates. The reviewed knowledge check remains clean.
- Opt-in replay gate passes 31 snapshots from 28 local archives: 2 battle, 25 field and 4 scripted scenes. Six field animation frames match 384 CHR pattern bytes, including temporal overlap and pending NMI cases. Archives are read in-place and never distributed; legacy notes are not proof of fresh or unmodified Mesen play.
- Fresh isolated FCEUX 2.6.6 controller runs passed final-boss victory/return (43 samples, 5 party-vital states, 33 cleared field samples), ordinary Slime victory/return (63 samples), and escape/return (59 samples, HP/rewards/gold/XP proving no defeated enemy). No HP/memory edits or global keys. A defeat-targeting experiment instead won; player-party defeat remains open. These checks found/fixed the Necrosaro phase-name and reused-scripted-scene detector defects.
- Latest walking gate validates 584 records/279 floors, 531 resolved local routes and 2,124 time/story cases. Fresh doorway input matched `(28,27)` on Lakanaba floor 0 to `(33,7)` on floor 1 at frame 677. Native pre-RNG hooks supplied 23 exact threshold matches. A post-scripted-loss checkpoint cleared scene context but did not expose all-party death; defeat certification remains open. FCEUX game-screen captures stayed blank, so no new visual parity claim was made.

## Additional ASM Evidence

- XP/spells: bank 12 `$9D29-$9D6C` and bank 13 `$89B6-$89CA` establish
  hero threshold index zero even when the pointer uses record 8; bank 12
  `$9E76-$9F7B` reads masks/level descriptors through `$A10B/$A117` and
  includes intelligence and random learning checks.
- Infinite enemy MP: bank 10 `$AA34-$AA41` skips consumption for selector
  `$0A` when the live byte is `$FF`.
- Resistance/drop: bank 10 `$A773-$A798`, `$A7AF-$A7B6`, bank 13
  `$B66B-$B72D`, and the bank 11 `$AD7C-$AD88` success-carry consumer
  establish packed innate susceptibility polarity. Bank 12 `$91DD-$929C`
  establishes native drop rank and its extra rank-seven random check.
- Encounter pools: bank 18 `$9C19-$9E66` selects grids, 16-byte records,
  day/night masks, relative weights, and six-byte predefined group records.
- Roofs/actors: bank 0F `$D4F3-$D518` selects default roof/interior-mask
  metatiles; bank 08 `$80B7-$80C3`, `$851A-$852D` loads supplemental
  tiles from `$8ABB`. Bank 0F `$E0CF-$E0DC`, `$E16F-$E176` supplies
  native hide flags and room-class filtering.
- AI training: bank 13 `$B066-$B0DB` gates Chapter 5 updates and reads/writes
  packed two-bit ranks at `$619B + (monster_id >> 2)`. `$92AE-$92D8` uses
  rank-specific `$94DB/$94DC` randomized estimate windows; rank and update
  thresholds are not decision-accuracy percentages.
- No ROM bytes, generated game images, save data, or existing guide content are
  distributed by this implementation. No existing user archives are deleted.
- Live verification is now connected on `127.0.0.1:55355`: RetroArch/Mesen
  0.9.9 was launched on 2026-10-02 with the matching US ROM (CRC `af12cb81`)
  and an isolated copy of the existing SRAM. System RAM, `$6000-$62FF`,
  battle, and entity regions are readable through the network interface.
- Actual adapter field acceptance passed in Lakanaba at `(14,6)`: Taloon
  level 1, HP `20/20`, MP `0/0`, native area object overlay, and no enemy rows.
  The original SRAM hash is preserved; config/save writes use temporary paths.
  This is not victory/escape/defeat, all-floor, or multi-core certification.
- Conditional searches: bank 1E `$BC56/$BC62`, `$B8DD-$B9EB` supplies the implemented dispatch/prerequisite/mask rules. Equipment passives use actual bank 11 `$96DB-$970C`, `$9848-$9850`, `$A63E-$A8D2` consumers. Animation uses bank 1D `$8B1E-$8CE5` and bank 1F `$C222-$C274`; captured CHR comparison found and fixed overlapping-write ordering and queued-upload defects.
- Direct actor services: bank 15 `$9962-$9971`, `$9CBF-$9CE2`, `$B528-$B530`, `$BF06-$BF0E`. Misleading buy/sell routine names do not change stock categories: `$07C5` indexes native directories at `$18:$802C`. Padequia Seed gate is `$1E:$B8F7-$B909`; map-41 relative world exit is `$12:$B95C-$B96D` followed by `$B7A1`.
- Walking records/arrival scans: bank 08 `$B22E-$B2E4`, `$B323-$B373`, `$B397-$B48D`, `$B4C1-$B59E`, pointer `$B974`. Land thresholds: bank 18 `$9C88-$9D0D/$A0BA-$A0F8`, wrapping math bank 1F `$C827-$C850`. Tournament completion and tunnel funding use separate inspected native event writes; native chest locations establish retrieval floors. Arena fractions use bank 18 `$A961-$A97A/$AAE0-$AB41`; Bolero gate uses bank 11 `$A873-$A8A6`.
- Original SRAM SHA-256 remains `B75E400F8838E42B897493004D04A034FCAAA49918C1FF1F9065666E2D7FA1E9`. Read-only Mesen access remains available. Background-targeted messages do not move the SDL2 core; global input is paused after another application took focus, so fresh live transition capture is not claimed.

## Next Required Work

Complete the unresolved portions of 097/098/102-105 with captured emulator
state and additional actual ASM consumer/effect tracing. Then complete the
unfinished original feature entries above as individual verified vertical
slices. Do not replace missing semantics with fabricated names, maxima,
probabilities, quest flags, availability rules, or inert controls.
