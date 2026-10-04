# Verified US Native Contracts

The runtime decoder targets the verified US PRG identity only. These contracts
come from inspected assembly consumers, not names in RAM reports or guide prose.
The complete implementation backlog remains in the separate coverage ledger.

## Persistent Character State

| Field | Native Location / Packing | Runtime Rule |
| --- | --- | --- |
| Full records | `$6001 + character_id * 30`, IDs 0-8 | Record 8 is an alternate selected hero record, not a ninth permanent party member. |
| Guest records | `$610F + (character_id - 9) * 6`, IDs 9-20 | Short records contain status, HP/MP pairs, and a native profile identifier. |
| Formation | `$616A` roster banks selected by `$618E` | Keep actual slot order; membership uses bit 7 and the low five-bit ID. |
| Available characters | Active and reserve roster entries | Retained levels alone do not prove availability. |
| Carried gold | `$6157-$6159`, little-endian three-byte value | Preserve all three bytes; native arithmetic caps at 99,999. |
| Vault gold | `$625B-$625C`, little-endian thousands | Multiply by 1,000; do not combine with spendable carried gold. |
| Current XP | Full record offsets 16-18 | Little-endian three-byte value. |
| Next-level XP | `$6E19 + growth_id * 3` | Native threshold, not an invented XP formula; alternate hero uses growth ID 0. |
| Level cap | Full record offset 5 equals 99 | The native builder skips the update, so never display the stale threshold. |
| AI training | `$619B + (monster_id >> 2)` | Two-bit little-endian pair at `(monster_id & 3) * 2`; valid native monster IDs 0-213. |

Evidence: bank 10 `$8301-$8312`, `$868D-$86AA`, `$9F83-$9FAC`;
bank 12 `$9D29-$9D6C`; bank 13 `$89B6-$89CA`, `$B066-$B0DB`.
The table builder retains `$09 = 0` while the pointer may substitute record 8.
The separate pointer resolver does not change `$09`.

## Battle Records

Eight enemy records begin at `$7274`, with a 14-byte stride. The low two bits of
record offset 13 index the group IDs at `$7206-$7209`. Current HP is the word at
offsets 10-11, current MP is byte 12, attack is the word at 1-2, and defense is
the word at 3-4. A field-context snapshot clears the displayed enemy party.
Positive/coherent records are additionally required because the context bit
alone does not certify a fight. Full battle mode/status certification is open.

`$6BDE & $80` is also used by chapter/shop scenes (bank 1B `$ABC9-$ABF8`, bank 1C `$B0FF-$B114`), so it is not a sole active-battle bit. When `$6E45-$6E48` is available, its setup IDs must agree with the live group header. The bank 11 `$9223-$926B` Necrosaro phase exception permits group-0 profiles `$CD-$D2` with setup `$AE`; the visible name stays `$AE`, and vitals still use the phase profile. Unsupported setup reads retain qualified coherent-record fallback.

MP `$FF` is an infinite sentinel: bank 10 `$AA34-$AA41` skips consumption for
selector `$0A`. It is shown as Unlimited, not an ordinary maximum of 255.
Party mirror words `$7211/$7213` are derived attack/defense, not alternate
HP/MP storage. Captured timing comparison with persistent vitals remains open.

Native monster records are 22 bytes at bank 18 `$8046`; 214 records end at the
following encounter directory. Names come from the configured ROM's indexed
name codec. Base HP uses the packed ten-bit value and native special 1,200-HP
case. Base rewards, innate susceptibility, and current live modifications are
not interchangeable.

## Progression And Resistance

Bank 12 `$9E76-$9F7B` reads eight-byte global spell masks through `$A10B` and
minimum-level descriptors through `$A117`. Descriptor bit 7 selects the variable
intelligence/random learning path. Only five character tables are learnable;
alternate hero uses table zero. A minimum is not a promised learning level.

Innate resistance selectors use bank 10 `$A773-$A798` and bank 13 `$B736`.
The actual bank 11 `$AD7C-$AD88` carry consumer establishes success polarity:
packed ranks 0/1/2/3 correspond to susceptible/partial/strong/immune. The base
catalog does not claim to include live action, equipment, or buff modifiers.

Drop rank is the low three bits of monster record byte 20. Bank 12
`$91DD-$929C` yields nominal denominators 1, 8, 16, 32, 64, 128, 256, and 4096;
rank 7 includes a second random check. This is the selected reward enemy's
chance, not an independent roll for each defeated monster. Chapter 3 has a
separate pool and eligibility gates still apply.

AI rank selects randomized estimate windows through bank 13 `$92AE-$92D8`
and `$94DB/$94DC`. Update thresholds `$FF/$80/$40/$00` are not percentages of
correct decisions or achievement progress. Chapter 5 update gates apply.

## Maps And Objects

US `$0041` bit 7 selects local context. World selector `$0065` is 0 Main World,
1 Gottside, or 3 Underworld. World coordinates use `$0042/$0043`; local
coordinates use `$0044/$0045`, with map/submap IDs at `$0063/$0064`.
Unknown identities and out-of-bounds nonwrapping coordinates do not get a pin.

Verified live local tile buffers begin at `$7800`, match `$003F/$0040` and
the descriptor dimensions, and are at most 2 KiB. Identity is rechecked after
the read. Larger/mismatched buffer contracts remain unverified and use ROM data.

Native visible-tile selection at bank 0F `$D4F3-$D518` compares packed room
class with `$46`, using supplemental metatile `$20` outside or `$21` inside.
Bank 08 `$80B7-$80C3`, `$851A-$852D` loads those common descriptors from
`$8ABB`. Cutaway preserves all decoded lower-five-bit tiles. Exceptional reveal
mode `$07BA = 4` preserves matching `$0520` tiles across room masking and is
represented with a separately keyed, current-floor reveal input.

Actor positions begin at `$6F60/$6F80`. Native facing uses `$7000 & 3`, not
the graphics slot. The render consumer hides actors with `$7020,X & $90` and
filters `$7140,X & $E0` against `$46`. These fields must not be inferred from
unrelated `$70E0` flags. Personal story identities remain open. Boat slot 6 and
balloon anchor slot 7 use graphics identities 6/7, acquisition `$628E & 1/2`,
and native world restrictions; balloon slot 8 is not a second vehicle. The
`$EB` router at bank 1F `$C4B6-$C4C9` tests `$627B + index`, proving the
acquisition byte. Party presentation slots 4/5 are not vehicles.

## Additional Native Consumers

- Equipment: bank 13 `$B4E8-$B572`, `$B540/$B547/$B54B` defines seven packed protection entries and scale `$AA/256`; actual armor/shield/helmet lookup priority applies, even when the first equipped type has no protection. Bank 10 `$850C-$852A` doubles agility only for item `$50`.
- Weapon/passive consumers: bank 11 `$9848-$9850` fetches equipped weapon selector zero, not a spell ID. `$96DB-$970C` supplies eligible item-$16 second hit. `$A63E-$A69E` supplies item-$33 evasion threshold 43 rather than 4. `$A69F-$A789` supplies item-$0F eligible KO/1-damage fallback, item-$12 RNG-below-170 misses, item-$15 native target-list damage `3*floor(damage/2)`, and item-$0E fixed damage against IDs `$75/$5C/$A8`. `$A7C4-$A816/$A855` supplies recoil/recovery; `$A8A7-$A8D2` supplies qualified item-$38/$41 damage return. Effects are not unconditional action predictions.
- Reserve/key access: bank 10 `$8498-$84E7`, `$9849-$98BD`, `$996C-$99B4` supplies the roster gate. Bank 1E `$B381-$B3C7` gives Chapter 4 ID-9 bypass for magic-door behaviors, using alive/nonparalyzed membership mask 3.
- StepGuard: bank 12 `$A714-$A71F` sets `$627F & $60`; bank 1E `$9A05-$9A2F` suppresses swamp/barrier damage with live bit `$40`.
- Enemy conditions: bank 11 `$8B1F-$8B59`, `$8C50-$8C78` and bank 10 `$A920-$A95D` establish sleep/confusion/silence in record byte 5 bits 0/2/3, and paralysis in record byte 6 bit 5. Presence bits are separate.
- Arena: bank 18 `$ABA6-$ABA8` sets `$72E9 & $80`; `$AAE0-$AAFD` reads the three-byte wager `$6E83-$6E85`. The arena-only button runs 100 private-memory ROM-driven simulations for win/draw estimates. `$6E7F & 3` is the player's choice, not a predicted winner; bank 11 `$936E-$937F` compares the survivor against it. Timing is sampled, not cycle-emulated; no exact next-fight outcome or live parity is claimed. See [ARENA_PREDICTOR.md](ARENA_PREDICTOR.md).
- Exits: bank 12 `$B71E-$B726`, `$B7BC-$B887` parses a table referenced by `$B970`, with conditional points/rectangles and directed floor arrivals. Inspected special local and Gottside branches are represented separately, with actual direction/world metadata. Complete tile-to-route associations remain open.
- Map-41 exit: bank 12 `$B95C-$B96D` followed by `$B7A1` retains world X and moves world Y south by three tiles in Chapter 1, otherwise two, with native byte arithmetic. It must not be labeled preserved arrival.
- Walking routes: bank 08 `$B22E-$B2E4` selects variable-width per-floor records through `$B974`; `$B4C1-$B4E4` defines widths 1/2/3, and `$B4ED-$B59E` maps source/arrival scan ordinals using `$B675` behaviors. `$B323-$B373` applies direct coordinate transitions first; `$B397-$B48D` applies story/time overrides. The owned ROM has 584 records across 279 floors, 531 resolved local connections and 2,124 passing time/story arrival cases. Default-only floors are not errors; source-count mismatches at `$09:07/$0D:02` remain unknown. A fresh internally driven doorway capture matched Lakanaba `(28,27)` to floor 1 `(33,7)` at frame 677.
- Actor services: bank 15 `$9962-$9971`, `$9CBF-$9CE2` resolves direct selectors 1-6; selectors 1/2/3 feed `$07C5` and the three native stock directories (`$B1FA-$B215`), despite misleading routine names. Selector 5 reaches House of Healing through `$B528-$B530`; 4/6 use vault/inn consumers. Story-specific identities are not inferred from dialogue prose.
- World rows: bank 0F `$D2E9-$D385` defines forward/reverse scan-entry offsets, not row lengths; native point/full-row equality covers all 73,088 tiles.
- Frames: bank 1D `$8B1E-$8C51` rotates color shadows; bank 0E `$802D-$8090` builds `$05FD-$0608`. Bank 1D `$8C52-$8CE5` uses `$0573` group mask, `$0574` PPU destination, `$057C/$0584` source, and phase `$3C & $058D`. Writes are ordered by latest trigger, not group index. The `$3E/$058E` inhibit gate prevents invented frozen phases. Bank 1F `$C222-$C274` consumes pending `$0300` commands; queued current uploads must not replace committed CHR. Six captured field frames match 384 pattern bytes. Static views remain available; every-floor timing parity is not certified.
- Objectives: bank 12 `$B201-$B261` gives Santeem active/completion flags and day/night floors. Bank 1E `$B8DD-$B8F6` gives Nectar event/held-item checks and `$BF59` its exact floor-0 coordinates. Bank 1E `$B11D-$B125` sets Padequia reunion completion `$6291 & 8`; bank 1D `$B0F6-$B168` separates request/root/formation prerequisites. Lighthouse request/completion remains separate. Guide routes do not substitute for flags.
- Additional objectives: tournament bank 1C `$AEFC-$AF18` activates `$6285 & $20` and uses `$6287 & 7`; bank 1D `$A9D8-$AA08` separately sets victory `$6284 & $40`. Tunnel funding bank 15 `$A62C-$A646` checks `$EA60` carried gold and sets `$6287 & $40`, also consumed by tunnel entity visibility. Native chest records place Flying Shoes `$33:03`, Sphere of Silence `$31:03`, and Gunpowder Jar `$2D:02`; eligible possession is retrieval, not inferred confrontation completion.
- Arena: bank 18 `$A961-$A97A` stores integer/fraction odds at `$6E39/$6E3D`; `$AAE0-$AB41` uses `$A97B` fractional coefficients and rounds the high-byte product. Fresh stakes up to 50 have bounded conditional payout calculation; amount bytes `$6E83-$6E85` are reused after settlement. Multipliers are not win probabilities; carry-over arithmetic remains qualified.
- Bolero: bank 11 `$A873-$A8A6` checks armor `$B6`, native action cost, RNG below 32 and remaining target MP. The comparison shows a qualified reaction, not an unsupported recovery amount.
- Transition losses: bank 12 `$908C-$90C5` removes inventory IDs `$6B/$6C/$5D` during chapter initialization. Current carried possession before Chapter 5 produces disclosure-only warnings; this does not prove every uncollected treasure or shop is missable.
- Economy targets use the inspected source shop's native price/currency and current balance. Target selection and clearing are local UI commands, not game writes, achievement unlocks, or predictions of winnings.
- Tactics: bank 13 `$805B-$809E` selects native dispatch, including Normal/Offensive special-mode override; `$A54D-$A619` rejects callbacks for Use No MP and treats Try Out separately. No exact action choice or accuracy percentage is promised.
- Name provenance: bounded 64-KiB/214-entry local names-only JSON is scoped by verified US ROM MD5 and decoder identity, uses atomic writes, prioritizes native names, rejects conflicting observations, and has a scoped reset. This is not a combat archive.
- Transformation: bank 1E `$B02F-$B074`, `$966C-$9694`, `$9E6B-$9E79`, `$9817-$9824` establishes 120 movement updates, bit-7 form class, low-seven sprite identity, expiry refresh, and transition clearing.

## Collection And Encounter Catalogs

Chest directory bank 1E `$BDC2` contains 82 complete three-byte records plus a
one-byte terminator. Values at `$BEB9` select normal rewards, empty/trap chests,
or classified scripted rewards. Chest flags use MSB-first masks at `$625D`.
Furniture at `$BCED` and direct search handlers at `$BF59` have distinct mask
encodings. The typed catalog deduplicates byte/mask identities and excludes
empty/trap chests; missing bytes mean unknown, not uncollected.

The reference catalog contains 177 reward flags, including 32 direct medal
pickup flags. Carried item `$69`, mutable exchange balance `$62A2`, and pickup
evidence are separate quantities. The inspected exchange stores no redemption history; historical redeemed totals are explicitly unavailable rather than reconstructed from a current balance. Complete conditional pickup correspondence remains open.

Conditional search dispatch `$BC56/$BC62` and bank 1E `$B8DD-$B9EB` provide Nectar (`$E8`), Agility (`$E9`), Drought (`$E1`), Mystic Acorns (`$F1`), Leather Armor (`$E7`), Medical Herb (`$E6`), and 50 gold (`$E5`). Exact masks at `$6277`, north-facing checks where required, Chapter 5 Acorns branch, event bytes and eligible held Nectar are projected. Missing pickup/event bytes stay unknown. Other event handlers are not counted as unconditional rewards.

Event-only searches `$EE/$ED/$EC/$EA/$E4` use bank 1E `$B830-$B8DC/$B9B1-$B9D0`. North/east facing, `$627D & 4`, `$628A & 2`, confirmed tile replacements and held Iron Safe are qualified independently; passage/travel interactions do not enter loot totals.

Land encounter consumers at bank 18 `$9C19-$9E66` select chapter/world grids,
16-byte records, day/night masks, and nonuniform weights. The last two entry
positions expand six-byte predefined groups; they are not monster IDs. Relative
weights are not complete normalized formation odds. Indoor directories use `$A23B/$A23D`, native `$A474` strides, and `$FF` no-pool sentinel. Entry chances enumerate all 256 RNG bytes with native inclusive cumulative comparisons and bounded multiplication, including zero-weight edge behavior. Balloon and global inhibit gates clear pools. Next-land-step thresholds use bank 18 `$9C88-$9D0D/$A0BA-$A0F8`, terrain `$7140`, movement/Repel `$6E42/$6E41`, strength `$62D5` and scent `$6BEB`. Bank 1F `$C827-$C850` is a wrapping word multiplier; `$0E` is a pointer offset, not multiplication by fourteen. All 23 captured pre-RNG thresholds match. Ship selection depends on volatile `$07`; final mixed-group count odds remain open.

## Verification Boundaries

Final read-only map/chapter/roster identity checks discard mixed snapshots when
the transport supports these reads. Unsupported partial-read transports retain
degraded capability rather than losing the guide or complete party snapshot.
Constructed regressions and the bounded owned-ROM gate do not replace captured
victory/escape/defeat, rewind, coordinate, or cross-core certification.

The opt-in `--state-archive` verifier bounds legacy FCEUX chunks and field widths, rejects duplicate regions/truncation, and never extracts saves. The 28 locally held progression archives yield 31 passing snapshots: 2 battle, 25 field and 4 scripted scenes, with field clearing and native animation CHR parity. Their legacy provenance remains distinct from a newly captured Mesen transition sequence.

Isolated official FCEUX 2.6.6 controller runs, seeded from copied local checkpoints, verified final-boss victory-return at frame 2358 (43 samples, 5 party-vital states, 33 cleared field samples), ordinary Slime victory-return at frame 2081 (63 samples), and escape-return at frame 1622 (59 samples, enemy HP 8 unchanged, zero rewards and unchanged gold/XP). Player-party defeat is not certified. These runs use internal controller input, not HP/memory edits or global keys, and preserve original saves.
