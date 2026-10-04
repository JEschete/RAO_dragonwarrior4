# Dragon Warrior IV Plugin Audit and Ideas

Reviewed: 2026-09-30.

Scope: this plugin, its existing tests, and the US disassembly at
`D:/Dev/Decomp/DragonWarrior4`. This is a research backlog, not an implementation
change. Existing runtime behavior is intentionally untouched.

Labels: **Confirmed** means directly supported by inspected code or a focused
check; **Verify** means a plausible risk or conflicting evidence that needs a
specific experiment; **Feature** means an additional capability, not a defect.
**Requirement** means an explicit user-requested change, not an optional idea.
Priorities: **P1** correctness/data integrity or mandatory redesign, **P2** resilience/accuracy,
**P3** optional usability and research work.

## Review Summary

105 actionable entries follow: the original 96 audit entries and nine explicit
user requirements added on 2026-09-30 (**097-105**). The new requirements take
precedence over conflicting earlier proposals, especially proposals to retain
or extend the legacy Party section, encounter archives, combat logs, or analytics.
Earlier findings are preserved as historical evidence, not permission to keep
functionality the user has requested removed.

Start with the requested two-panel redesign and removals, the embedded guide,
meaningful/correctly placed map markers, and town shopping comparisons. Relevant
supporting defects include **023** (map corruption), **015** (alias rejection),
and **026** (unguarded US chest tables). Entries marked Verify are not proven
gameplay bugs; optional Feature entries are distinct from mandatory Requirements.

Evidence collected:

- All **86 existing plugin tests passed**, including Qt presentation tests.
- `tools/generate_knowledge.py --check` passed against the local captures.
- Tiny runtime probes reproduced alias rejection, the broad core match,
  party reordering, all-zero entity decoding, and malformed JSON failures.
- The locally built US reference ROM matched SHA-256
  `373be958cb33651fe599a6b282d2a232eb3b99559c258b2c70b53df0fa31e34a`.
  It indexed as US with 279 area descriptors. Three boundary/control maps
  were compared, not the entire atlas; see 023 for the results.
- No emulator session was exercised. Cross-core transport, Japanese memory,
  save-state rewind, fast-forward, and gameplay recommendations still need
  targeted validation. Passing current tests does not settle those questions.

Decompilation references below are relative to the declared reference root:
`README.md` identifies the reference image; `docs/BANK_MAP.md` indexes
bank/data boundaries; `src/constants/ram.inc` names RAM fields;
`analysis/save-ram-report.md` summarizes persistence;
`analysis/routine-interfaces.tsv` identifies consumers; and
`src/banks/bank_XX.asm` contains the corresponding assembly. The reference
summary and the executable consumers can disagree, as entry 001 illustrates.

Verification standard: a decompilation-backed fact requires inspection of the
actual `src/banks/bank_XX.asm` instructions or data bytes and their consumer.
Reports, constants, routine names, and guide descriptions are navigation aids,
not semantic proof. An inspected candidate routine does not certify the entire
proposed feature; unresolved contracts remain explicit below.

### ASM Recheck Outcome

- **001 resolved:** inspected gold arithmetic confirms three-byte storage
  and the 99,999 cap. The two-byte summary is incorrect, not the plugin read.
- **002 downgraded:** the supposedly decisive "story flag" label is also
  used by the actual chest-indexing and chest-opening instructions. Unrelated
  story-bit contamination has not been proved.
- **023 retained:** the actual bitstream-pointer routine confirms `$BFD8`
  rollover and bank-$0B resume at `$8012`, supporting the existing ROM probe.
- **051 corrected:** the setup comparison sets `$72E4` bit 6 for differing
  non-empty IDs, despite a misleading duplicate-entry routine name.
- **094 sharpened:** the exchange code both adds to and subtracts from the
  medal byte; it is not a monotonic lifetime collection total.

Every decompilation-backed evidence paragraph now identifies inspected ASM
instructions/data or explicitly states that the proposed semantic contract is
unverified. This check does not certify every idea's implementation, Japanese
layout compatibility, or every BRK-dispatched service and gameplay condition.

## State Accuracy

### 001. Preserve the assembly-confirmed three-byte carried-gold contract [Confirmed, P2]

- Evidence: [game/state.py](game/state.py) reads `$6157-$6159` as three bytes,
  and [tests/test_state.py](tests/test_state.py) constructs a three-byte value.
  Actual assembly `src/banks/bank_10.asm`, `AddGoldCappedAt99999` at
  `$10:$868D-$86AA`, loads all three bytes into `$72-$74` and sets the cap
  bytes to `$9F/$86/$01` (99,999). Chapter setup in
  `src/banks/bank_12.asm` at `$12:$901B-$9029` clears `$6158/$6159` and
  initializes `$6157`. The save-RAM summary's two-byte description is wrong;
  this is not a plugin-width bug.
- Idea/check: retain the three-byte decoder and add fixtures at 65,535,
  65,536, and 99,999. Track correction of the reference summary separately;
  do not narrow this field based on that summary.

### 002. Verify collectible-bit membership before counting completion [Verify, P1]

- Evidence: [game/state.py](game/state.py) counts every bit in `$625D-$6277`,
  and [game/adapter.py](game/adapter.py) labels the count as treasure flags
  "opened". Actual `src/banks/bank_1E.asm` at `$1E:$B447-$B458` tests and
  sets a chest flag through `$B72E/$B791/$B79C`; `$B731-$B776` derives its
  index from a map/submap/count directory, and `$B779-$B7AE` applies an
  MSB-first mask to `$625D,X`. Despite the `SaveStoryFlags` name, these
  instructions explicitly serve chests. The prior claim that `$625D` proves
  unrelated story events were counted is withdrawn.
- Idea/check: enumerate the actual chest/search/furniture consumers and valid
  indices before accepting 216 bits as a completion denominator. Keep unused
  or unclassified bits separate. A non-collectible-bit fixture requires a
  proven non-collectible consumer, not a label-derived assumption.

### 003. Preserve actual party-slot order [Confirmed, P2]

- Evidence: [game/state.py](game/state.py) extracts ordered party IDs, then
  builds characters in numeric ID order; [game/adapter.py](game/adapter.py)
  filters that tuple. Runtime slots `[7, 6, 1]` display as `[1, 6, 7]`.
- Idea/check: retain party-slot identities and render in slot order. Test a
  deliberately nonnumeric formation and a mid-session formation change.

### 004. Include temporary companions in the party model [Feature, P2]

- Evidence: the state decoder recognizes only eight permanent IDs. The
  actual `src/banks/bank_10.asm` table at `$10:$9F83-$9FAC` includes twelve
  pointers from `$610F` through `$6151` in six-byte increments, following
  the nine longer-record pointers. `$8301-$8312` masks the party member ID
  with `$1F` and indexes this table; `$8387-$8391` distinguishes IDs at
  least nine. `src/banks/bank_12.asm` at `$12:$8EB2-$8EB8` clears exactly
  `$610F-$6156`. Guest names and full vitals semantics are not established
  by those operations; the local guide is only a candidate identity source.
- Idea/check: decode the guest-record contract and slot encodings, including
  guest vitals and participation. Validate one guest-containing chapter.

### 005. Classify the ninth full character record [Verify, P2]

- Evidence: actual `src/banks/bank_10.asm`, `$10:$9F83-$9F94`, contains
  nine little-endian pointers from `$6001` to `$60F1`, spaced 30 bytes apart;
  `$8306-$8312` selects them by character ID. [game/state.py](game/state.py)
  reads eight. The table does not establish the ninth actor's identity or
  that it is a ninth permanent playable character.
- Idea/check: trace the ninth record's consumers and lifecycle; document
  whether it is scratch, a special actor, or missing supported state.

### 006. Separate recruitment from retained character levels [Verify, P2]

- Evidence: party details use `level != 0` to decide which inactive records
  deserve display. Actual `src/banks/bank_19.asm` at `$19:$8058-$8066`
  checks Chapter 5 and compares `$6292` with `$FF` before choosing music;
  `src/banks/bank_1C.asm` at `$1C:$A3FE-$A40C` tests its high bit to alter
  entity visibility. Those consumers establish a progression-related byte,
  not the complete per-character recruitment mapping.
- Idea/check: model recruitment, active party, and stored chapter records
  separately after classifying the flag semantics. Test Chapter 5 reunions.

### 007. Reject boot and transition garbage as game state [Verify, P1]

- Evidence: [game/state.py](game/state.py) checks snapshot lengths but not
  initialization or chapter-transition validity; zero-filled records decode
  into plausible-looking chapters, inventories, and locations.
- Idea/check: derive a conservative readiness contract from initialization
  routines. Fixtures for boot, title screen, and chapter setup should not
  generate fictional progress or encounters.

### 008. Use an explicit region-specific memory contract [Verify, P1]

- Evidence: `_location()` has a Japanese candidate, but party, currency,
  battle, and progression reads still use the same fixed offsets. A region
  label does not prove that every field shares the US contract.
- Idea/check: support verified layouts per region and disable unsupported
  fields. Compare US and Japanese snapshots field by field before advertising
  equal coverage.

### 009. Do not silently map unknown world selectors to Main World [Confirmed, P2]

- Evidence: `WORLD_LOCATIONS.get()` in [game/state.py](game/state.py) defaults
  to Main World for every selector other than 0, 1, and 3.
- Idea/check: show an unknown/transitional location with the raw selector
  rather than an authoritative world pin. Test selectors 2 and `$FF`.

### 010. Distinguish an unmatched indoor descriptor from outdoor travel [Confirmed, P2]

- Evidence: with assets present, `_location()` falls back to Main World when
  no descriptor matches, even when the US tileset is nonzero.
- Idea/check: represent unresolved indoor identity explicitly and suppress
  the world pin. Test a nonzero tileset with invalid map/submap values.

### 011. Decode hero gender as independent state [Feature, P3]

- Evidence: actual `src/banks/bank_08.asm` at `$08:$85C3-$85CB` reads
  `$615C`, masks bit 0, and shifts it into the character sprite-set selector.
  The current state model omits that byte; text/pronoun semantics are not
  established by this sprite consumer.
- Idea/check: expose the verified value where relevant to names, portraits,
  or factual character details, without guessing from the player's name.

### 012. Display vault gold separately from carried gold [Feature, P3]

- Evidence: actual `src/banks/bank_15.asm` at `$15:$B4B9-$B4ED` adds,
  subtracts, and loads the little-endian pair `$625B/$625C`, using carry and
  borrow across both bytes. The withdrawal path at `$BD4E-$BD78` uses the
  same requested quantity first in the vault-word subtraction and then in
  `$B4EE-$B512`, which calls the multiply-by-ten helper three times before
  converting it to carried gold. This establishes a 1,000-gold vault unit.
  Journey displays carried gold only.
- Idea/check: decode the thousand-gold unit and show vault and carried totals
  separately. Validate deposits, withdrawals, and a zero balance.

### 013. Show verified Return destinations [Feature, P3]

- Evidence: [game/reference_data.py](game/reference_data.py) contains a
  `RETURN_LOCATIONS` catalog, but the adapter does not expose unlocked
  destinations. Actual `src/banks/bank_1D.asm` at `$1D:$AA52-$AA71`, named
  `LoadEventReturnDestination`, sets submap 0 and local coordinates `(23,10)`
  for a scripted transition. It is not evidence of Return-spell unlock bits;
  that contract remains unverified.
- Idea/check: recover the unlock-bit contract, then show available travel
  destinations and corresponding atlas links, not every catalog entry.

### 014. Surface transformation state and remaining steps [Feature, P3]

- Evidence: actual `src/banks/bank_1E.asm` at `$1E:$B02F-$B031` writes
  120 to `$6296`, and `$B069-$B071` selects/encodes a shape into `$6297`.
  `$9817-$9821` clears the active counter and refreshes party entities.
  The state model does not read these fields; exact decrement timing and
  shape identities still require their consumers to be traced.
- Idea/check: classify shape and step semantics through their consumers and
  add a contextual status row. Test activation, expiration, and map changes.

## Plugin Selection and Integration

### 015. Reconcile advertised content aliases with supports() [Confirmed, P1]

- Evidence: [plugin.toml](plugin.toml) advertises "dragon warrior iv" and
  "dragonquest4"; runtime probes show `Adapter.supports()` rejects both
  "Dragon Warrior IV" and "Dragon Quest 4" on Mesen.
- Idea/check: share one normalized matcher with the framework contract and
  parameterize tests over every manifest alias, including filename suffixes.

### 016. Replace substring-based core recognition [Confirmed, P2]

- Evidence: `"nes" in core` in [game/adapter.py](game/adapter.py) makes the
  method accept `snes9x` for a matching content title in a runtime probe.
  Manifest filtering may reduce exposure; the method itself is inconsistent.
- Idea/check: compare normalized core identifiers or explicit aliases. Add
  negative tests for SNES cores and similarly named non-NES systems.

### 017. Do not treat an empty content title as positive identification [Verify, P2]

- Evidence: `supports()` returns true for any accepted core when content is
  empty, which can occur while content metadata is unavailable.
- Idea/check: require another verified identity signal or a pending state.
  Test empty metadata, unloaded content, and subsequent metadata arrival.

### 018. Bind the configured ROM to the actual running content [Verify, P1]

- Evidence: `content_hash` is unused by `supports()`, and `activate()` discards
  its content key. Atlas assets come from a separately configured ROM.
- Idea/check: compare compatible content identities and warn or disable exact
  overlays on a mismatch. Test a patch or another ROM launched under a DW4 name.

### 019. Display ROM configuration and extraction errors [Confirmed, P2]

- Evidence: [plugin.py](plugin.py) supplies `asset_error`, but
  [game/adapter.py](game/adapter.py) stores it without presenting it. A missing
  ROM can therefore remove maps without explaining why in a normal snapshot.
- Idea/check: provide a keyed diagnostic section while preserving live RAM
  features. Test missing paths, invalid images, and unavailable state storage.

### 020. Contain failures while constructing map layers [Confirmed, P1]

- Evidence: `_rom_assets()` catches some construction errors, but
  `Plugin.create()` calls `assets.map_layers()` outside that protected path;
  world waypoint parsing can raise `ValueError` or `IndexError` there.
- Idea/check: fail the atlas independently of the whole adapter. Corrupt a
  routing record and verify that party/state functionality still initializes.

### 021. Verify achievement progress refresh after activation [Verify, P2]

- Evidence: the adapter requests progress only in `__init__()` and retains
  the returned object; `_reset_session()` does not refresh it.
- Idea/check: establish whether the provider mutates that object or returns
  snapshots, then refresh according to the framework contract. Test an unlock
  and account change after adapter creation.

### 022. Isolate achievement-provider failures from core state [Verify, P2]

- Evidence: `_progress()` directly invokes the provider without local error
  handling. A provider exception can abort adapter construction.
- Idea/check: confirm which exceptions the host owns, and ensure unavailable
  account services cannot remove live party/maps. Test a failing provider.

## ROM Decoding and Atlas Reliability

### 023. Fix map-stream footer rollover and the bank-$0B resume offset [Confirmed, P1]

- Evidence: `_area_stream()` in [game/rom_assets.py](game/rom_assets.py) reads
  through `$BFFF` and repeats bank `$0A` after a stream starting there.
  Actual `src/banks/bank_0F.asm`, `LowerFixed_AdvanceBitstreamPointerAndBank`
  at `$0F:$E642-$E673`, compares the stream address to `$BFD8`, increments
  the bank, and resumes at `$8012` for bank `$0B` rather than consuming
  footer bytes.
- Runtime result: on the exact reference image, current versus corrected
  stream slicing differed by **332/950 tiles on `2D:07`** and
  **1,323/1,323 tiles on `45:04`**. Control map `45:05` matched.
- Idea/check: implement the verified bank reader and replace the misleading
  full-bank continuation fixture in [tests/test_rom_assets.py](tests/test_rom_assets.py).
  Test both rollover points, exclude footer bytes, and compare all 279 floors
  against a trusted decoder before calling the atlas exact.

### 024. Validate cartridge identity beyond PRG page count [Confirmed, P2]

- Evidence: ROM construction checks the magic and 32 PRG pages, but not the
  MMC1 mapper, NES 2.0 extensions, or other expected cartridge properties.
  Actual `src/dragon-warrior-iv.asm` emits the 16-byte header: byte 4 is
  `$20`, byte 5 is zero, and flags 6/7 are `$12/$08`, establishing 32 PRG
  pages, no CHR ROM, mapper 1, and the NES 2.0 marker directly from source.
- Idea/check: parse the header structurally and establish supported variants.
  Reject incompatible mappers and malformed extended sizes with clear errors.

### 025. Gate fixed-address decoding for unknown or patched ROMs [Verify, P1]

- Evidence: `region == "Unknown or patched"` does not prevent indexing fixed
  US-layout maps, routes, graphics, and palettes.
- Idea/check: define verified layout fingerprints or explicit patch profiles.
  Unknown images should not inherit exact-layout claims just because some
  pointers happen to pass range checks.

### 026. Apply region/layout gating to chest tables too [Confirmed, P1]

- Evidence: `_read_hidden_treasures()` refuses non-US images, but
  `_chest_records()` reads `$1E:$BDC2/$BEB9` without the same gate.
  The README identifies US retail layout as the exact object-layout boundary.
  Actual `src/banks/bank_1E.asm` at `$1E:$BDBE-$BDC1` stores the directory
  and value pointers `$BDC2/$BEB9`; `$B731-$B776` consumes directory counts
  and `$B7B2-$B7C9` fetches the indexed reward. This establishes the US
  consumer, not compatibility of those offsets with another region.
- Idea/check: apply a common layout capability check to every exact object
  decoder. Test that an unsupported image does not emit guessed chest contents.

### 027. Validate world-destination coordinates before indexing rows [Confirmed, P2]

- Evidence: `_world_destination_waypoints()` directly reads `rows[key][y][x]`;
  Gottside and Underworld are smaller than the byte coordinate range.
- Idea/check: validate coordinates against the selected world's dimensions.
  Test out-of-range x/y records and preserve the other valid destinations.

### 028. Report an unterminated map-routing table [Confirmed, P2]

- Evidence: the route loop stops after `MAP_COUNT` without checking that a
  terminator was found; the neighboring world-position loop does check it.
- Idea/check: make bounded table exhaustion explicit and distinguish it from
  successful parsing. Test a route table with no `$FF` terminator.

### 029. Bound table reads to the intended PRG range [Verify, P2]

- Evidence: `_cpu_bytes()` validates the starting address and total image
  length, not the end of the selected bank or declared PRG payload.
- Idea/check: give table and stream readers distinct bounds contracts. Fuzz
  near-bank-end lengths and images with appended data without forbidding
  explicitly verified cross-bank formats.

### 030. Validate world-row consumption against native row metadata [Verify, P2]

- Evidence: `decode_world_row()` clips the final run to width and reads until
  that width is satisfied; `_world_rows()` consumes only the pointer portion
  of each four-byte row record.
  Actual `src/banks/bank_0F.asm` at `$0F:$D2E9-$D332` multiplies the row
  index by four, selects byte 2 for x at least `$40` and byte 3 for x at
  least `$C0`, then uses that byte as a scan-entry offset into the row stream.
  `$D333-$D385` consumes terrain runs and extended literals. These metadata
  bytes are not established row lengths.
- Idea/check: reproduce scan-entry behavior and verify native malformed-run
  rules before adding bounds based on metadata. Test truncated rows and
  compare full-row decoding with point lookups at x 63/64 and 191/192.

### 031. Detect damaged cached PNGs [Confirmed, P2]

- Evidence: both render methods return any existing file without checking
  PNG integrity or dimensions.
- Idea/check: regenerate unreadable or wrong-sized images once, with a
  diagnostic if regeneration fails. Test an empty file and a valid wrong-size PNG.

### 032. Avoid deleting caches still owned by another instance [Verify, P2]

- Evidence: `_discard_stale_caches()` recursively deletes every other version
  under the content hash as soon as an asset object is constructed.
- Idea/check: use ownership/age-aware cleanup or explicit cache maintenance.
  Test two instances with different extractor versions sharing one state root.

### 033. Bound the decoded-area memory cache [Verify, P2]

- Evidence: `_area_cache` retains every visited floor's tile tuples and
  graphics for the lifetime of the asset object; there is no size limit.
- Idea/check: measure a full-atlas browsing session and apply an LRU/byte
  budget if needed. Ensure eviction never changes marker or rendering results.

### 034. Make map-feature decoding failures observable [Confirmed, P2]

- Evidence: `snapshot()` catches a feature-overlay `ValueError` and silently
  sets the overlay to `None`; the user cannot distinguish failure from no objects.
- Idea/check: provide a deduplicated per-layer diagnostic without interrupting
  party state. Test a bad feature table and recovery after a valid map change.

### 035. Represent uncertain chest completion separately from uncollected [Verify, P2]

- Evidence: a chest-count mismatch sets `completed=False` for every decoded
  chest and cannot express unknown completion independently.
- Idea/check: introduce an explicit uncertainty state or neutral presentation.
  Test that a mismatched floor cannot be mistaken for a verified fresh chest list.

### 036. Do not hide all hidden rewards because one record is invalid [Confirmed, P2]

- Evidence: `hidden_treasures()` catches a single parse failure, replaces the
  complete result with `()`, and caches that empty result permanently.
- Idea/check: expose the failed capability and classify whether partial recovery
  is safe. Test one invalid furniture mask beside otherwise valid records.

### 037. Cache static feature positions independently of live flags [Verify, P2]

- Evidence: every indoor `snapshot()` rescans all floor tiles and re-reads
  chest associations, although tile layout and record ordering are static.
- Idea/check: cache immutable feature templates and update only verified live
  completion bits. Benchmark repeated snapshots on a large floor.

### 038. Offer a deliberate roof/cutaway view [Feature, P3]

- Evidence: the decoder preserves roof bits, but [map_renderer.py](map_renderer.py)
  masks every tile to `$1F`, producing a base-tile view without roof semantics.
- Idea/check: classify roof composition and offer explicit cutaway/native modes.
  Compare a roofed floor with the game; do not call an intentional cutaway a bug.

### 039. Add day/night palette variants [Feature, P3]

- Evidence: `_area_palette()` handles forced palette overrides but does not
  receive the live time value already decoded by the state reader.
  Actual `src/banks/bank_0E.asm`, `SelectMapPaletteNumber` at
  `$0E:$BAF7-$BB51`, reads `$62ED`, compares it with `$78`, applies map/
  submap overrides, and tests `$6293 & $10` for override index `$0E`.
- Idea/check: render cache-keyed day/night variants after verifying palette
  selection rules, including the story-bit branch. Validate a normal town,
  a forced-palette location, and the story-sensitive override.

### 040. Support verified animated-tile frames [Feature, P3]

- Evidence: animated pattern pointers are handled as one static pattern set;
  the atlas has no animation-state input. Inspected data in
  `src/banks/bank_08.asm`, `Bank08_AnimatedTilePointers` at `$08:$AEB7`,
  includes the pointer `$ED07`, but its name alone does not verify sequencing
  or timing; this feature's animation contract is unverified.
- Idea/check: recover frame sequencing and timing for water or other animated
  tiles, keeping a low-motion static option and bounded redraw work.

### 041. Reflect dynamic opened doors and changed map tiles [Feature, P2]

- Evidence: feature overlays use ROM layouts and collected bits, not the
  mutable tile state. Actual `src/banks/bank_1E.asm` at `$1E:$9E92-$9EA1`
  writes a new low-five-bit tile while preserving the upper bits; its pointer
  consumer `$9EA2-$9EC3` resolves the RAM map at `$7800`. The inspected
  `ReplaceCompletedEventTile` path at `$B87C-$B8A9` conditionally changes
  tile `(20,11)`. Other door and event conditions remain to be classified.
- Idea/check: recover verified live map modifications and overlay them on the
  immutable ROM floor. Test opening a door and a story-driven tile change.

### 042. Populate the currently unused services marker category [Feature, P3]

- Evidence: [plugin.py](plugin.py) declares `services`, but feature decoding
  emits collectibles, entrances, locks, and entities rather than named services.
- Idea/check: identify inns, churches, shops, and vaults through entity/event
  consumers, with exact coordinates and no guessed identity from guide prose.

### 043. Classify the eight special chest dispatch values [Feature, P2]

- Evidence: `SPECIAL_CHEST_VALUES` deliberately stays neutral. Actual
  `src/banks/bank_1E.asm` at `$1E:$BC34-$BC4C` contains eight special
  values and their little-endian handler pointers. `$B462-$B476` performs
  the lookup and indirect jump. `$FE/$FD` select `$B868/$B86F`, whose
  instructions emit distinct messages, select `$00/$1B`, invoke a battle
  service, and reinitialize the map; `$FF` selects `$B4CE`. Other values and
  all dispatched BRK-service meanings still require tracing, not name inference.
- Idea/check: trace each value to its handler and conditions; expose rewards,
  trap warnings, or conditional outcomes only after fixture validation.

### 044. Extend hidden rewards to verified scripted searches [Feature, P2]

- Evidence: only direct `$A0-$AA` search items are indexed. Bank `$1E` has
  actual item-grant instructions: `src/banks/bank_1E.asm` at
  `$1E:$B807/$B81B/$B8FD` loads item IDs `$52/$6B/$7E` and calls the
  grant paths. `$B8F7-$B908` gates the last grant with a flag-service result
  and conditionally sets that flag. Handler dispatch, names, prerequisites,
  and coordinates must be traced individually before publishing markers.
- Idea/check: recover each handler's chapter, item, and story prerequisites
  and coordinates. Keep conditional searches distinct from unconditional loot.

### 045. Link stairs, exits, and travel doors to destination floors [Feature, P3]

- Evidence: atlas entrance waypoints identify tile behavior but not a verified
  destination. Actual `src/banks/bank_08.asm` at `$08:$B037-$B05B` scans
  five-byte routing records to `$FF`; `$B06A-$B099` scans a separate
  three-byte world-position table and writes `$0042/$0043`. These prove
  canonical routing consumers, not a complete stair-to-floor transition graph.
- Idea/check: build a directed transition graph and allow destination navigation.
  Validate asymmetric exits and multiple entrances to the same location.

### 046. Show hazards and forced-movement tiles [Feature, P3]

- Evidence: `TILE_BEHAVIORS` names swamps, barriers, pitfalls, and arrows,
  but `feature_overlay()` skips those cases.
- Idea/check: add a separate hazard layer based on verified effects and
  movement rules, including clear uncertainty for unclassified behaviors.

### 047. Show whether a locked route is currently usable [Feature, P3]

- Evidence: keyed-door markers and party inventory are available independently;
  the overlay does not combine them into a verified access state.
- Idea/check: trace key and door rules, including holder and chapter conditions,
  then show usable/blocked/unknown without writing to game memory.

## Live Entities

### 048. Gate entity overlays during uninitialized or unrelated modes [Verify, P2]

- Evidence: a runtime probe of all-zero entity memory returns 26 actors at
  `(0,0)`; visibility depends only on descriptor/coordinate `$FF` sentinels.
  That probe alone does not prove normal gameplay produces this snapshot.
- Idea/check: validate map readiness/mode and actual active-slot flags before
  rendering. Test title screen, map load, battle, and return to the field.

### 049. Validate live coordinates against the selected map [Verify, P2]

- Evidence: `_entity_overlay()` forwards raw coordinates onto the selected
  layer without local bounds or coordinate-space checks.
- Idea/check: classify wrapping, offscreen actors, and local/world coordinate
  conventions. Test actors outside a small floor and on all three world layers.

### 050. Resolve semantic entity identities through source records [Feature, P3]

- Evidence: icons are intentionally numbered slots with raw descriptor fields.
  Actual `src/banks/bank_1C.asm` at `$1C:$9B12-$9B33` doubles the map ID,
  reads a bank-$05 pointer, and `$9B3F-$9B66` skips submap record blocks.
  `$977A-$9795` reads descriptor-dependent fields; `$9798-$97B2` selects
  day/night variants. These establish source-record selection, not NPC names
  or a one-to-one mapping from a live descriptor to an identity.
- Idea/check: follow source-record provenance to verified NPC/vehicle roles,
  retaining raw fields whenever identity or script conditions are unresolved.

## Battle Capture and Outcomes

### 051. Use verified battle mode and phase signals [Verify, P1]

- Evidence: [game/battle.py](game/battle.py) detects combat from positive HP
  and nonzero enemy stats. Its read ends at `$72E3`, immediately before named
  mode/status/phase fields `$72E4-$72E9` in the decompilation.
  Actual `src/banks/bank_12.asm` at `$12:$8075-$809A` clears `$72E4-$72E7`
  and sets `$72E8` to `$FF`. `$811A-$8147` sets `$72E4` bit 6 when two
  non-`$FF` setup IDs differ: the equality branch at `$8133` skips the
  `LDA #$40` at `$8135`. The routine's duplicate-entry name is misleading.
  No single active-battle bit or complete field-mode lifecycle has been
  established here.
  Actual `src/banks/bank_18.asm` at `$18:$ABA6-$ABA8` writes `$80` to
  `$72E9` on the arena path: mode must be considered before interpreting
  all coherent enemy records as ordinary party encounters.
- Idea/check: trace those fields' lifecycles and combine independent evidence.
  Test leftover enemy records, setup, victory messages, casino arena, and field mode.

### 052. Verify and decode full-width enemy attack and defense [Verify, P1]

- Evidence: the reader consumes offsets `+1` and `+3` as single bytes and
  ignores their neighbors. Existing tests set those neighbors to zero.
  Actual `src/banks/bank_18.asm`, `LoadMonsterAttackPower` at
  `$18:$9AC1-$9AD5`, reads ROM field 5 into `$0C` and field `$10 & $03`
  into `$0D`. `$9BCC-$9BE5` establishes live record base `$7274` and
  14-byte stride. This proves a ten-bit ROM attack value and the live
  record layout, but not the live attack/defense high-byte semantics.
- Idea/check: trace the live combatant-field contract and test stats above 255.
  If the live fields are words, combine both bytes and fix coherent detection;
  do not equate the ROM record encoding with the live encoding without tracing it.

### 053. Verify live battle-party vitals versus persistent records [Verify, P1]

- Evidence: capture reads persistent character records for party HP/MP;
  actual `src/banks/bank_12.asm` at `$12:$80D2-$80F3` writes separate
  party fields at `$7210-$7214` with a ten-byte slot stride computed by
  `$8148-$8156`. `src/banks/bank_10.asm` at `$10:$835C-$8386` resolves
  these records via `$72EA` identities and pointers at `$9FAD`. The
  assembly proves separate battle records, not yet which source is freshest
  for each HP/MP change; that timing remains Verify.
- Idea/check: compare both sources during damage, healing, transformation, and
  victory settlement. Prefer the verified live source for combat timelines.

### 054. Resolve names for encounters with more than two groups [Feature, P2]

- Evidence: name learning takes two IDs from `$0440-$0441`, while battle
  groups come from four slots at `$7206-$7209`; complete text matching can
  reject introductions that do not fit the two-name contract.
  Actual `src/banks/bank_12.asm` at `$12:$810E-$8119` copies four setup
  IDs to `$7206-$7209`; `$84C7-$84E2` iterates four introduction groups.
  The complete text-to-monster-name linkage is still unverified.
- Idea/check: recover the US monster-name/text linkage from ROM consumers,
  retaining conservative fallback labels. Validate one-, two-, and four-group fights.

### 055. Persist verified learned monster names with provenance [Feature, P3]

- Evidence: `_monster_names` is in-memory only and cleared on deactivation,
  so later sessions can replace learned labels with neutral slot names.
- Idea/check: persist names scoped to ROM identity, region, and decoder version,
  with conflict detection and a reset path. Never carry US text guesses into JP.

### 056. Decode enemy conditions rather than exposing only raw status [Feature, P2]

- Evidence: battle tooltips explicitly state that status bits are undocumented;
  actual `src/banks/bank_13.asm` at `$13:$85EE-$8601` tests masked flags
  at combatant offsets 5, 6, and 7 after resolving the live record at
  `$899C-$89B5`. Status is therefore not established as only the single byte
  currently displayed. Individual named conditions remain unclassified.
- Idea/check: recover status masks and lifetimes for named conditions, retaining
  raw values for unknown bits. Validate stacked effects and effect removal.

### 057. Distinguish unavailable battle memory from no battle [Confirmed, P2]

- Evidence: read errors become `BattleState.unavailable(reason)`, but
  `_battle_section()` hides unavailable states and does not present the reason.
- Idea/check: add a nonintrusive capability diagnostic while retaining working
  party state. Test a core that exposes system RAM but not the battle region.

### 058. Track enemy generations when a slot is reused [Verify, P1]

- Evidence: active encounters key enemy history only by slot. `_update_active()`
  can replace an ID while keeping the old starting/highest/lowest HP values.
- Idea/check: model transformations, summons, and replacement as generations or
  explicit events. Test Necrosaro phases and another reused-slot sequence.

### 059. Require reward-counter lifecycle evidence [Verify, P1]

- Evidence: active rewards start at current counters and retain their maximum;
  nonzero rewards are enough to classify a later idle frame as victory.
  Actual `src/banks/bank_12.asm` at `$12:$8083-$808F` clears `$7201-$7205`
  during setup. This confirms one reset path, but not all settlement, escape,
  restart, or mid-fight observation behavior.
- Idea/check: trace initialization/reset behavior and compare edges to the
  encounter baseline. Test starting observation mid-fight and stale rewards
  left from a previous encounter before an escape.

### 060. Treat chapter and scripted transitions as explicit encounter boundaries [Verify, P1]

- Evidence: encounter finalization derives outcomes from party/reward changes
  without a chapter or transition identity in the active-encounter model.
- Idea/check: classify scripted endings and chapter initialization separately
  from defeat/victory. Replay a transition that replaces party and currency state.

### 061. Handle save-state loads and rewind without inventing outcomes [Verify, P1]

- Evidence: capture has no discontinuity marker; HP, rewards, party membership,
  and story state can jump backwards while the same log remains active.
- Idea/check: use host lifecycle signals where available and conservative
  rollback detection otherwise. Test rewind inside a battle and loading an
  earlier save after victory, preserving separate timeline branches.

### 062. Separate observation time from game time [Verify, P2]

- Evidence: durations use UTC timestamps; they can include pauses, app downtime,
  and save-checkpoint resumption, while fast-forward compresses game turns.
- Idea/check: store wall time and verified emulated/active time separately,
  using monotonic time for in-session intervals. Test pause and system-clock changes.

### 063. Refresh the state that controls high-frequency capture [Verify, P1]

- Evidence: `capture()` clones `_last_ram` and refreshes only monster IDs and
  battle text, while WRAM and battle records are fresh. Location/tileset bytes
  can therefore come from an older full snapshot.
- Idea/check: define a coherent minimum capture read set and session generation.
  Test a fight beginning immediately after a map/chapter transition between snapshots.

## Archive Integrity and Persistence

### 064. Recover from structurally malformed encounter JSON [Confirmed, P1]

- Evidence: `_load_active()` and `_load_recent()` do not catch missing-key or
  wrong-root errors such as `KeyError`/`AttributeError`. With mocked file contents
  `{}`, constructing `EncounterLog` raises `KeyError` in a runtime probe.
- Idea/check: validate root shape and required fields before construction,
  quarantine/report bad records, and continue with healthy history. Test `{}`,
  arrays, missing nested fields, and a healthy neighboring record.

### 065. Validate nested analytics objects before accepting the archive [Confirmed, P1]

- Evidence: [game/combat_analytics.py](game/combat_analytics.py) checks only
  top-level container types. A runtime probe accepts `locations={"broken": {}}`
  and then raises `KeyError` when computing `document`.
- Idea/check: validate nested counts, labels, IDs, and numeric ranges; recover
  safely rather than failing during panel composition. Add corrupted nested fixtures.

### 066. Handle invalid UTF-8 analytics files [Confirmed, P2]

- Evidence: `CombatAnalytics._load()` catches `OSError` and `JSONDecodeError`,
  but not `UnicodeDecodeError` raised by `read_text()` on invalid UTF-8.
- Idea/check: treat decoding failures as recoverable archive corruption and
  preserve the original for diagnosis. Test invalid byte sequences explicitly.

### 067. Enforce encounter/checkpoint schema compatibility [Confirmed, P2]

- Evidence: `_active_from_document()` ignores schema version;
  `_record_from_document()` accepts arbitrary versions without migration.
- Idea/check: reject unsupported future versions and migrate explicitly known
  old versions. Test absent, current, old, and future schema identifiers.

### 068. Validate persisted encounter IDs before using them in paths [Verify, P1]

- Evidence: IDs loaded from `active.json` are arbitrary strings, and `_write_record()`
  joins that ID into an output filename. Generated IDs are safe; loaded IDs
  are not constrained to that format.
- Idea/check: enforce a safe identifier grammar and state-root containment.
  Test separators, parent traversal, absolute paths, and invalid Windows filenames.

### 069. Keep persistence errors from breaking the live snapshot [Confirmed, P1]

- Evidence: encounter/analytics writes and directory creation occur after
  `snapshot()`'s protected memory-read block; write/replace/unlink `OSError`s
  can propagate into the caller instead of returning live information.
- Idea/check: isolate the storage boundary, report degraded persistence, and
  preserve in-memory state. Test permission denial, disk-full, and locked files.

### 070. Prevent writers from sharing the same temporary filename [Verify, P2]

- Evidence: JSON writers use a fixed `.tmp` sibling, unlike a uniquely owned
  temporary file. Concurrent instances can contend on the same path.
- Idea/check: establish the framework's single-writer guarantee or use explicit
  ownership/locking and unique atomic temp files. Test two writers to one archive.

### 071. Make encounter finalization recoverably idempotent [Verify, P1]

- Evidence: finalization writes the completed record, inserts it in memory,
  clears the active object, then deletes `active.json` as separate operations.
- Idea/check: fault-inject each boundary and reconcile a checkpoint whose ID
  already has a completed record. Recovery must not duplicate recent entries
  or silently lose an encounter.

### 072. Check resumed checkpoints against the current session [Verify, P1]

- Evidence: a stored active encounter is resumed by archive path, without
  validating age, chapter, running-content key, or compatible current battle.
- Idea/check: retain session/content metadata and classify unmatched checkpoints
  as interrupted rather than merging unrelated fights. Test restarting on another save.

### 073. Rebuild lifetime analytics from the full archive, not just 200 records [Confirmed, P1]

- Evidence: the adapter seeds analytics with `encounter_log.recent`, limited to
  200 records. A missing/corrupt analytics file therefore cannot recover older totals.
- Idea/check: add a bounded streaming rebuild over completed records with progress
  and cancellation. Test deletion of analytics after more than 200 encounters.

### 074. Make duplicate detection compatible with full-history rebuilds [Verify, P1]

- Evidence: processed IDs retain only 500 entries. Replaying an older record
  outside that window can increment totals again; normal adapter batches are
  smaller, so ordinary polling is not itself shown to trigger this.
- Idea/check: use an archive watermark/index or another durable deduplication
  contract. Replaying 501+ records twice must leave lifetime totals unchanged.

### 075. Add archive retention and storage visibility [Feature, P3]

- Evidence: recent display is bounded, but dated encounter files and timelines
  accumulate without a user-visible storage budget or retention control.
- Idea/check: show archive size, allow explicit retention/export, and preserve
  lifetime totals when detail is pruned. Never delete history automatically
  without a documented, user-controlled policy.

### 076. Bound checkpoint serialization work during long fights [Verify, P2]

- Evidence: every distinct active frame appends to an unbounded timeline and
  rewrites that entire timeline to `active.json`; capture is intended at 50 ms.
- Idea/check: benchmark long changing fights, then use throttled checkpoints,
  bounded chunks, or an append journal with a defined crash-loss budget.
  Preserve frame fidelity and avoid adding a worker unless host ownership requires it.

### 077. Avoid documented same-name playthrough collisions [Confirmed, P2]

- Evidence: without a save path, identity is ROM plus hero name. The README
  explicitly acknowledges separate saves with the same name share an archive.
- Idea/check: provide explicit local playthrough profiles or another stable
  user-selected discriminator. Test two same-name saves of the same ROM.

### 078. Detect a different save replacing the same configured path [Verify, P1]

- Evidence: configured identity uses the normalized path, not a save-generation
  identity. Replacing that file leaves the archive key unchanged.
- Idea/check: offer a new-playthrough action and conservative replacement
  detection without using a changing save-file hash as the permanent key.
  Test a copied new game and normal incremental saves at the same path.

## Analytics Accuracy

### 079. Count observed rewards when reward counters were missed [Confirmed, P2]

- Evidence: encounter outcomes can be victories based only on persistent
  gold/experience gains, but analytics adds only `reward_gold` and
  `reward_experience`, ignoring the recorded observed gains.
- Idea/check: define counter-versus-observation precedence and confidence;
  test a victory with zero sampled counters and positive verified gains,
  accounting for experience distribution without double-counting party totals.

### 080. Do not count every interrupted fight as an escape [Confirmed, P2]

- Evidence: analytics increments location/enemy `escapes` for every outcome
  other than victory or defeat, including `escaped_or_interrupted`.
- Idea/check: preserve an unknown/interrupted bucket until an actual escape
  signal is verified. Test app shutdown, unavailable memory, and confirmed escape.

### 081. Make unidentified_groups count groups, not slots [Confirmed, P2]

- Evidence: `_include()` increments `unidentified_groups` once for every enemy
  with a missing ID, even when several slots share one group code.
- Idea/check: count distinct unresolved groups or rename the metric to its
  actual unit. Test three unidentified enemies in one group versus three groups.

### 082. Key location analytics by stable spatial identity [Verify, P2]

- Evidence: locations are keyed only by `start_location` text; map/submap
  fields do not participate, and world identity is not stored independently.
- Idea/check: use region/world/map/submap identifiers and treat names as labels.
  Test duplicate titles, renamed reference labels, and all three world maps.

### 083. Prevent neutral enemy labels from overwriting known names [Verify, P2]

- Evidence: analytics assigns `enemy["label"] = label` for each new record,
  even when a later session has only "Enemy slot N" for a previously named ID.
- Idea/check: keep label provenance/quality and prefer verified names over
  fallback labels. Test a named encounter followed by an unidentified-label session.

### 084. Make the victory-rate denominator explicit [Feature, P3]

- Evidence: `win_rate` divides victories by every recorded encounter, including
  unknown/interrupted outcomes and reconstructed entries.
- Idea/check: show resolved-outcome rates and capture coverage separately,
  with meaningful denominators. Test mixed known, interrupted, and reconstructed history.

## Decompilation-Grounded Gameplay Features

### 085. Add spoiler-controlled, live chapter objectives [Feature, P3]

- Evidence: the map document declares `objective`, but the plugin does not
  produce objective markers. Actual `src/banks/bank_12.asm` at
  `$12:$8EAD-$8F12` clears save/guest state, branches on `$615A`, and
  selects chapter-dependent party initialization. This establishes chapter
  setup, not objective completion flags or a verified quest graph; guide
  routes remain candidates until their event consumers are checked.
- Idea/check: author concise original objectives keyed to verified flags and
  exact destinations. Offer spoiler levels and avoid showing future-chapter tasks.

### 086. Warn about verified missable treasures before the transition [Feature, P2]

- Evidence: the local guide identifies progression-sensitive treasures;
  the current ROM feature layer has no availability/prerequisite lifecycle.
- Idea/check: corroborate each missable condition with the event consumer and
  flag state, then warn only while actionable. Test before/after the triggering event.

### 087. Compare equipment eligibility and actual stat effects [Feature, P3]

- Evidence: inventory already identifies equipment classes. Actual
  `src/banks/bank_10.asm` at `$10:$8B04-$8B58` masks an item ID,
  checks special cases including hero gender, and tests a roster bit against
  `$8C65,X`. `src/banks/bank_15.asm` at `$15:$B2CF-$B34C` resolves buy
  prices with location-specific branches, and `$B35F-$B373` applies the
  sell-price scaler. In contrast, the inspected `$12:$9619-$963C` routine
  checks selected-item special cases, not a complete wearability table;
  do not infer that table from its eligibility label. Stat deltas and curses
  still require their actual effect consumers.
- Idea/check: show verified eligibility, curses, and effective stat deltas for
  owned equipment. Include special effects rather than ranking by attack alone.

### 088. Show experience to the next level and learned-spell milestones [Feature, P3]

- Evidence: the party model displays current experience and spell bits only;
  actual `src/banks/bank_12.asm` at `$12:$9C22-$9C4F` subtracts three-byte
  current XP from a three-byte next-level threshold and handles level 99.
  `$9C8C-$9CBF` compares those threshold bytes for level-up eligibility.
  `$9EC5-$9F02` tests spell-learning level descriptors and includes a
  random branch at `$9EF3-$9EF7`. Exact tables remain to be decoded;
  spell learning cannot be assumed deterministic from a listed level alone.
- Idea/check: recover XP thresholds and spell-learning rules, separating
  deterministic thresholds from randomized growth. Validate a level-up boundary.

### 089. Add a ROM-backed bestiary with confidence-aware weaknesses [Feature, P3]

- Evidence: actual `src/banks/bank_18.asm` places monster bytes at `$18:$8046`
  and the following encounter table at `$92AA`; `$9B94-$9BB2` computes
  monster pointers with a 22-byte stride and base `$8046`, giving 214 records
  in that bounded region. Actual `src/banks/bank_13.asm` at
  `$13:$B66B-$B6DC` selects/clamps resistance values, and `$B6E0-$B717`
  computes a target-dependent chance. Full weakness labels, name linkage,
  and probability interpretation are not established by those names alone.
- Idea/check: decode names, stats, rewards, and resistance semantics from the
  configured ROM, with optional locally generated sprites. Keep innate resistance
  distinct from live modified stats and party AI knowledge.

### 090. Add encounter zones and verified local encounter pools [Feature, P3]

- Evidence: actual `src/banks/bank_18.asm` at `$18:$9C19-$9C87` selects
  a chapter/world-dependent grid, indexes it with x divided by 16 and y's
  high nibble, and handles special world cases. `$9C88-$9CB1` selects a
  16-byte formation record; `$9CB2-$9CCB` uses terrain and day/night
  branches for rate selection; `$9D06-$9D09` compares the random value.
  These establish actual inputs and consumers, not normalized formation odds.
- Idea/check: overlay the current zone and eligible formations with chapter,
  terrain, time, and suppression conditions. Show probabilities only after
  tracing weights and normalization rather than assuming uniform selection.

### 091. Explain verified Chapter 5 AI knowledge and tactics [Feature, P3]

- Evidence: actual `src/banks/bank_13.asm` at `$13:$8088-$809E` reads
  `$615B` into the AI state and branches on its values; `$824B-$825C`
  adds a scaled value to a two-byte action score; `$B66B-$B717` resolves
  resistance and target-dependent chance. This confirms tactics/scoring
  consumers, not the guide's persistent learning ranks, training percentages,
  or learning-update formula. Those remain unverified. The overlay currently
  displays a tactic name.
- Idea/check: trace the actual knowledge table and learning updates, then
  expose per-monster learned confidence and factual tactic constraints.
  Do not present guide percentages as verified without checking the code.

### 092. Show casino and economy goals using native rules [Feature, P3]

- Evidence: coins are decoded; actual `src/banks/bank_15.asm` at
  `$15:$A797-$A800` reads the coin balance, obtains a chapter stake, asks
  for a purchase, and starts multi-byte coin arithmetic. Shop-price branches
  are at `$B2CF-$B34C`. Actual `src/banks/bank_18.asm` at
  `$18:$AB8D-$ABB7` enters the arena path and sets `$72E9` bit 7.
  Journey offers no contextual affordability/progress view; prize catalogs
  and odds have not been certified by this inspection.
- Idea/check: show factual prize costs, verified balances, and optional targets.
  Keep arena encounters separate from ordinary combat analytics and make no
  unsupported guarantee about winnings or randomized outcomes.

### 093. Track local achievement prerequisites without claiming unlocks [Feature, P3]

- Evidence: [game/achievements.py](game/achievements.py) is a static checklist;
  the guide routes chapter, treasure, and restricted-party achievements.
- Idea/check: show locally verified prerequisites and active-party eligibility,
  while treating RetroAchievements as the authority for unlocks. Never reproduce
  private trigger logic or imply that a recommendation guarantees credit.

### 094. Distinguish medals held, redeemed, and ever collected [Feature, P2]

- Evidence: Journey displays `$62A2` as "Small Medals", while the guide and
  achievement checklist have a cumulative collection objective.
  Actual `src/banks/bank_15.asm`, `RunSmallMedalKingRewardExchange` at
  `$15:$A99A-$AA6D`, adds a counted quantity to `$62A2` at `$A9BA-$A9C0`
  and subtracts a reward cost at `$AA3B-$AA41`. Thus this byte is a mutable
  exchange balance, not a monotonic ever-collected counter. Complete inventory
  and collection-flag correspondence remains to be traced.
- Idea/check: label the exchange balance accurately, count carried medal items
  separately, and derive lifetime collection only from validated pickup evidence.
  Test depositing and redeeming medals without claiming achievement progress
  from the exchange balance alone.

## Research and Verification Guardrails

### 095. Give each decoded field a traceable contract and fixture [Feature, P2]

- Evidence: reference labels mix web captures, Japanese code notes, and US
  assembly. Entry 001 demonstrates a reference-summary conflict that could
  otherwise lead to a harmful "fix".
- Idea/check: maintain a small curated contract catalog with region, address,
  width, encoding, consumer, confidence, and regression fixture. Share contracts
  between state readers rather than duplicating offsets across adapter features.

### 096. Add portable replay and per-core memory-contract verification [Feature, P2]

- Evidence: tests are mostly constructed snapshots; current boundary tests
  can pass while real floors are wrong. Numerous cores are advertised, and
  source-regeneration checks depend on ignored local captures.
- Idea/check: add compact, reviewed replay cases for transitions, guest parties,
  large stats, corrupt archives, and rollover maps; retain a separate opt-in
  legally owned ROM gate. Check each supported core's address/region behavior.
  Clean-checkout tests must validate the tracked knowledge schema without
  requiring private captures or distributing ROM-derived graphics/guide prose.

## User-Requested Overlay Redesign

Added: 2026-09-30. These are mandatory requirements from the user's screenshots
and explicit direction, not optional feature suggestions. The user considers
the current Battle section, the separate lower Party section, the Combat log,
and generic map-entity labels unhelpful. This section supersedes earlier ideas
that would retain or extend those presentations or combat-recording features.
No runtime changes have been implemented by adding these requirements.

### 097. Replace the Battle section with two side-by-side party panels [Requirement, P1]

- Evidence: the supplied overlay screenshot shows a text-only Battle list with
  generic enemy-slot labels, followed by a redundant Party summary. The user
  explicitly requests a two-panel replacement in the main overlay.
- Required behavior: the left panel shows the player's current party, in actual
  formation order, with names, separate HP and MP bars, and readable numeric
  current/maximum HP and MP text for each member. It remains present both in
  and out of battle, including town and world-map travel. Include temporary
  companions when they are actually part of the party. The right panel shows
  the enemy party during battle with the same HP/MP bar-and-text presentation,
  using verified enemy identities rather than a final UI of raw slot numbers.
  Preserve the left/right arrangement at supported overlay widths; do not
  implement this as another collapsible text list or a separate window.
- Idea/check: test field, town, and battle snapshots, formation changes,
  guests, fallen members, and zero-MP combatants. Both bar fill and text must
  update from the same live state without layout shifts. Establish true enemy
  HP/MP maxima through actual ASM consumers; an observed peak must not be
  mislabeled as maximum, and fabricated bar percentages are not acceptable.

### 098. Clear the enemy panel at battle end and on return to the world map [Requirement, P1]

- Evidence: the user explicitly requires the right panel to clear when a fight
  ends and the game returns to exploration, rather than retain enemy records.
- Required behavior: clear all enemy rows, bars, names, and tooltips after
  victory, escape, defeat, or another verified battle-end transition, and keep
  the right panel empty outside battle. The player's left panel stays visible
  and continues updating. Do not display the previous encounter on the field
  or use stale positive enemy HP as sufficient proof that battle continues.
  A world-map fight can retain world-map coordinates while active: do not
  clear a genuine fight merely because `location.is_world` is still true.
- Idea/check: replay battle start, victory settlement, escape, defeat,
  world-map return, and a subsequent fight using the same enemy slots. Inspect
  the actual ASM mode/lifecycle consumers before declaring a detector correct;
  no previous enemy may remain after a confirmed return to exploration.

### 099. Remove the legacy lower Party section and its functionality [Requirement, P1]

- Evidence: the user calls the Party section below Battle useless and explicitly
  requests its removal, rather than a second presentation of the same party.
- Required behavior: remove the DW4 plugin's separate lower Party section,
  its compact summary, and its existing `OPEN PARTY DETAILS` presentation and
  actions. Do not retain them behind a toggle or recreate a duplicate section.
  Retain shared character/equipment decoding only where needed by the new
  left party panel and the town-shopping comparisons; removing this legacy
  functionality does not mean deleting the party data needed by those features.
- Idea/check: verify the main overlay has only the requested party presentation,
  with no legacy Party details action or duplicate lower summary. Remove obsolete
  plugin-only presentation wiring/tests without changing other plugins' UI.

### 100. Remove Combat log, encounter recording, and analytics completely [Requirement, P1]

- Evidence: the user explicitly rejects the Combat log and requests complete
  removal of its functionality, not merely hiding the visible section.
- Required behavior: remove the Combat log section, `OPEN RECENT COMBATS`,
  lifetime/session battle counts, win rates, reward/location/enemy analytics,
  recent-combat views, encounter timelines, outcome reconstruction, checkpoints,
  and ongoing encounter/archive/analytics persistence. Remove DW4's recorder
  capture hook, service initialization, and obsolete plugin-only recording code.
  Do not leave a hidden recorder running after removing the UI. Keep the live
  memory polling needed for the new party/enemy panels and preserve other
  plugins' shared framework capabilities. Do not automatically delete existing
  user archive files; removal of functionality is not permission to destroy data.
- Idea/check: a complete battle-and-exploration session must create no encounter
  checkpoints, completed encounter files, or combat-analytics updates and expose
  no log/count/history controls. Entries **064-084** and archive/outcome-focused
  parts of **058-063** are historical investigations, not implementation targets
  under this direction; none may justify retaining the removed functionality.

### 101. View the complete unified guide inside the scrollable main overlay [Requirement, P1]

- Evidence: the requested local guide is
  [Guide/DW4_UnifiedGuide.md](Guide/DW4_UnifiedGuide.md), at
  `F:/tools/RetroArchOverlay/plugins/RAO_dragonwarrior4/Guide/DW4_UnifiedGuide.md`.
  The user wants to read it in the main overlay window, with scrolling.
- Required behavior: provide an accessible in-overlay Guide view that renders
  the existing local Markdown file, including headings, lists, tables, the table
  of contents, and internal section links. The guide content must be scrollable
  inside the main overlay; opening an external editor/browser or another window
  is not a substitute. Keep the guide read-only and unchanged, load it relative
  to the plugin root, and preserve reading position during live state updates.
- Idea/check: open the guide, navigate a table-of-contents link, scroll through
  long chapter sections and reference tables, then continue receiving gameplay
  updates without losing the reading position. Test constrained overlay sizes
  and a missing/unreadable file with a useful in-overlay diagnostic.

### 102. Replace generic map labels with representative identities and icons [Requirement, P1]

- Evidence: the supplied map screenshot labels an object "Map entity 4" and
  shows slot, facing, descriptor, behavior, and runtime flags instead of a
  meaningful identity. The user explicitly rejects this presentation.
- Required behavior: map labels and marker icons must represent the actual
  object: a named actor, vehicle, entrance/destination, shop/service, treasure,
  or another verified role as appropriate. A slot number or raw descriptor is
  not an acceptable primary identity. Keep low-level diagnostics out of ordinary
  labels/tooltips, with optional separate developer diagnostics if still useful.
  Resolve identities from actual ASM entity/event consumers and source records;
  do not invent NPC names or roles from appearance or guide proximity. Explicitly
  unresolved identities must not masquerade as verified named objects.
- Idea/check: compare representative town/world objects with the same live game
  state and confirm that icons, visible labels, and tooltips agree with their
  verified identities, including entities whose slots change or are reused.

### 103. Verify and correct map-marker placement [Requirement, P1]

- Evidence: the user believes the placement in the supplied map screenshot is
  wrong. This is a reported accuracy concern, not a coordinate defect proven
  by the screenshot alone; the relevant source/state must be checked.
- Required behavior: markers must be anchored to the actual object's tile on
  the correct world or indoor floor. Verify world versus local coordinates,
  map/submap association, tile/pixel units, map origin, wrapping, tile-center
  anchors, and sprite-versus-tile offsets. Correct any wrong placement at the
  decoder/coordinate-contract boundary rather than shifting icons by eye.
  Do not place stale actors on a newly selected layer during transitions.
- Idea/check: use synchronized paused-game snapshots and actual ASM coordinate
  consumers to compare the player and several identifiable objects against the
  rendered map, then repeat after walking into town, changing floors, and
  returning to each world layer. Record exact expected coordinates and add
  regression cases; existing concerns in **023/049/050** support this work.

### 104. Show town stock and equipment eligibility for all available members [Requirement, P1]

- Evidence: the user requests an overlay section on town entry showing what is
  for sale and which available party members can equip each item.
- Required behavior: automatically show the current town's actual shop stock,
  grouped by shop, with item names and prices, and an eligibility comparison for
  each available party member. In Chapters 1-4 use the available chapter roster;
  in Chapter 5 include all currently available/recruited members, including
  reserves and wagon members, not just the active party. Do not include an
  unrecruited character merely because a retained record has a nonzero level.
  Refresh the section when town, chapter, roster, or verified stock conditions
  change, and remove stale town stock when leaving for the world map. Derive
  stock/prices and equipment rules from actual ROM tables and ASM consumers,
  not a generic item list or an assumption that the guide is always current.
- Idea/check: enter two towns with different shops, inspect equipment and item
  stock, and verify each character's eligibility against native rules. Test a
  Chapter 5 member outside the active four, a newly recruited member, and an
  unrecruited member. Non-equippable stock must still appear as stock without
  fabricated equip eligibility. This requirement expands **006/042/087**.

### 105. Show exact per-character upgrades over currently equipped gear [Requirement, P1]

- Evidence: the user requires both an upgrade verdict and the size of the
  upgrade for each eligible available character, not just an item recommendation.
- Required behavior: for each shop equipment item and each available character,
  show whether it is equippable, the relevant currently equipped item, current
  versus candidate effective stats, and signed numeric deltas such as attack,
  defense, or agility as applicable. Clearly distinguish upgrades, sidegrades,
  downgrades, and items the character cannot equip. Calculate the comparison
  per character and equipment slot, including active and reserve Chapter 5
  members. Account for verified curses, resistances, and special effects rather
  than calling every higher nominal stat an unconditional upgrade. Do not
  substitute character level, a universal item score, or a guide ranking for
  actual equipped-gear comparisons. All shopping assistance remains read-only.
- Idea/check: validate an upgrade, equal-stat item, downgrade, incompatible
  item, and special-effect tradeoff against the actual ASM equipment/effect
  consumers. Changing one character's equipped gear must update only that
  character's comparison. Verify that a reserve member gets a separate correct
  numeric result and that unknown mechanics are not reported as exact deltas.

## Suggested Implementation Order

1. Complete 097-100 together: persistent party/enemy panels, correct battle-end
   clearing, and complete removal of the legacy Party/combat-log functionality.
2. Complete 101: a usable, read-only guide viewer inside the scrollable main overlay.
3. Complete 102-103: representative map identities and verified placement,
   addressing map decoding defect 023 where it affects the result.
4. Complete 104-105 together: actual town stock, eligibility for every available
   member, and exact per-character comparisons against currently equipped gear.
5. Resolve supporting state/identity/capability risks before presenting results
   as exact: 001-008, 015/018/019/026, 048-054, and equipment consumers in 087.
   Do not implement the superseded archive/analytics backlog instead of removals.

Keep [Guide/DW4_UnifiedGuide.md](Guide/DW4_UnifiedGuide.md), existing design
documents, and the decompilation unchanged when implementing this backlog.
Reuse the framework's map/panel models and local tests. Do not introduce a
second UI window, a runtime dependency on the decompilation project, copied
walkthrough prose, bundled ROM bytes, or generated copyrighted game assets.

This review added documentation only. It did not fix the listed runtime issues,
rebuild the decompilation, or certify the untested gameplay paths.
