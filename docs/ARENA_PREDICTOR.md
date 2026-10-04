# Arena Win Estimates

The Arena overlay offers **Estimate win chances** only while the arena monster
selection/wager window is open or an arena battle is active. Pressing it queues
capture on the controller's polling worker, without network reads on the UI
thread. The **Simulations** numeric input defaults to 100 and accepts 1-100,000.
The captured lineup starts the requested number of simulations in headless child
processes. The count is locked during capture/execution; **Cancel** stops a batch
without leaving the arena. Editing a count does not start simulations. The
capture uses reads no larger than RetroArch's 4 KiB limit and rejects incomplete
or changing matchups before starting. Each
entry retains its own probability, including duplicate monster IDs. Unused slots
are omitted. The result includes the draw percentage and clears when the matchup
changes or the arena closes. It estimates a complete match, not the remaining
turns of a match already underway.

## Native Battle Execution

The plugin uses py65's Python 6502 interpreter to execute the configured,
verified US ROM. The original bank dispatcher, monster stat loader, AI/action
filter, targeting, agility order, HP/MP, resistance, damage and status routines
run in a private memory copy. There are no live memory writes, controller inputs,
save-state loads or save-file changes. The plugin does not distribute ROM bytes.

Arena enemies can use spells, breaths, healing and status effects. The ROM's
arena action filter and targeting restrictions remain active. `$6E7F & 3` is the
player's selected entry, not a precomputed winner; native survivor comparisons
are used to count outcomes. Monster stats and action repertoires are loaded by
the original ROM routines, so no separately extracted stat tables are required.

Presentation calls for windows, battle messages and sound are bypassed. Input
waits are bypassed, with random low-byte seed increments sampled for frame waits.
The graphics-only PPU queue append at bank 1D `$BEC4` is also bypassed: captured
display queues must not be scanned indefinitely without an emulated NMI consumer.
It has no combat/RNG side effects in the headless model. The pictured Giant
Bantam/Flythrope/Pteranodon lineup and a stale-queue loop have regressions; actual
combat instruction-budget exhaustion remains an error, not a draw.
The RNG at `$C891` is replaced by its equivalent Python recurrence, including
the ADC flags. Initial RNG state and counter are sampled independently per run.
The real battle termination paths produce winners, stalemates and the ten-round
draw. Cancellation or an exhausted instruction budget is an error, never a draw.

These are Monte Carlo estimates, not exact next-fight predictions. Presentation
timing is modeled rather than cycle-emulated; timing distributions have not been
calibrated against live play. With 100 samples, a 50% estimate has approximately
10 percentage points of 95% sampling uncertainty, in addition to modeling error.
No claim of live emulator parity is made.

A 70% estimate means 70 sampled wins, not a guaranteed next result. Even a
perfectly calibrated 70% favorite does not win 30% of matches, including losses
and draws. With only 100 samples,
70 wins has a roughly 60%-78% 95% Wilson interval before accounting for model
error. Zero sampled wins does not establish an impossible win. Fresh-bet draws
return the wager; the carry-over branch has a separate reroll path.

## Modern Battle Flow

This is a structural summary of the inspected ROM paths, not an independently
implemented replacement engine. Helper calls below include the game's integer
rounding, state checks, action-specific exceptions and RNG consumption.

```text
fight(entries, rng):
	monsters = initialize_from_rom(entries, arena_mode=True)
	for round in 1..10:
		slots = prepare_action_slots(monsters, their_ai_state)
		for slot in active(slots):
			agility = effective_agility(slot.actor)
			base = floor(agility / 4)
			slot.speed = base + rng.below(agility - base)
		order = descending_speed(slots, rom_tie_breaking)

		for slot in order:
			actor = slot.actor
			if not rom_status_and_turn_checks_allow(actor):
				continue
			action = resolve_queued_action(slot, actor, monsters, rng)
			targets = resolve_action_targets(action, actor, monsters, rng)
			if not rom_requirements_allow(action, actor, targets):
				apply_rom_failure_behavior()
				continue
			execute_rom_action(action, actor, targets, rng)
			apply_followups_and_status_transitions()
			if rom_declares_winner_or_stalemate():
				return rom_terminal_outcome()
		finish_round_using_rom_rules()
	return DRAW

monster_decision(actor, battle, rng):
	candidates = actor.rom_action_slots_and_weights
	candidates = apply_arena_and_current_state_gates(candidates, battle)
	if actor.ai_uses_a_sequence:
		choice = next_enabled_slot(actor.ai_cursor, candidates)
	else:
		choice = weighted_random_slot(candidates, rng)
	return resolve_rom_fallbacks_and_target_mask(choice, battle, rng)
```

The action repertoire has six slots. Duplicate actions/weights affect selection;
some profiles advance a saved sequence cursor instead of making independent
weighted draws. Arena filters exclude forbidden actions. Target masks depend on
the action: a single-target attack samples an eligible target, whereas healing,
self-targeted and group actions follow their own eligibility rules. Targets are
validated again during execution as deaths/status changes can invalidate earlier
choices. Additional actions, interruptions and exceptional monster behavior stay
inside the ROM helpers, rather than being assumed identical for every entity.

The underlying generator is deterministic state plus an eight-bit counter, not
a new independent seed for each decision. Action choices, targets, turn order,
damage and status rolls consume its stream. Frame/input waits also affect state,
so knowing the current seed before a bet does not fix the future stream. Exact
prediction would require matching the complete state and subsequent timing.

Evidence: bank 10 `$AE43-$AE6D`, `$B095-$B145`; bank 11
`$88CA-$89D3`, `$9518-$95DC`, `$BEB2-$BF2D`; bank 12 `$88B0-$88C0`.

## Completion Time

The overlay partitions seeds 0 through the requested count minus one into
disjoint batches using at most four child processes, limited to logical CPU count
minus one (minimum one worker). It runs exactly the requested number of full
encounters, with no zero-sized batches for small counts. The parent handles pipe I/O, aggregates
progress and validates matching lineups/trial counts. Cancellation and worker
failure terminate and reap every process; stale generations cannot publish.
There are no nested process pools or orphanable grandchildren.

Immutable ROM banks are reused within each child. Remapping copies only a changed
switchable bank and updates the fixed bank only when its identity changes. Two
hot scratch-workspace loops use direct Python operations instead of stepping
each instruction. Differential tests compare RAM, stack, registers, flags and
cycles against the original instructions, plus complete-fight RNG/outcome parity.
The rest of combat still runs through py65: this is not a finished action-level
engine. A full direct engine is feasible but must preserve byte/word wrapping,
rounding, AI cursors, exceptional actions and RNG call order, with the ROM retained
as its differential oracle. More simulations would reduce sampling error, not
repair an uncalibrated timing model.

Runtime grows approximately linearly with the chosen trial count. Increasing
trials by 100x reduces Monte Carlo standard error by roughly 10x under the model;
it does not change the next fight's randomness or guarantee a winning bet.

## Setup And Verification

Install the plugin dependency in the overlay's Python environment:

```powershell
python -m pip install -r requirements-arena.txt
```

The existing configured ROM provides both code and monster data directly. The
reference disassembly can also be built for local verification. In this
implementation the rebuilt ROM matched SHA-256
`373be958cb33651fe599a6b282d2a232eb3b99559c258b2c70b53df0fa31e34a`.
No disassembly source was edited. The standard build requires MSBuild; the
reference assembler can assemble the same source into the build directory.

From the plugin directory, run the independent 100-match verifier:

```powershell
python tools/predict_arena.py --rom "resources/DW4_Disassembly/build/arena/Dragon Warrior IV (USA).nes" --entries 0 0 0 0
python -m pytest tests/test_arena.py tests/test_arena_overlay.py tests/test_arena_native.py
```

Native ROM tests skip when the local build is absent. The standalone verifier
prints entry stats, win counts and draw counts. Entry ID 255 is an unused slot;
two to four valid entries are required. Native tests compare RNG output/flags
against the actual ROM, check loaded stats and survivor state, execute special
actions, and exercise the game's overtime draw. These tests do not replace a
future captured live-arena comparison.

## Measured Verification

A complete reference-ROM run with four Slimes and seed zero originally completed
100 fights in 109.2 seconds. The optimized overlay worker completed the same
100 seeds in **27.2 seconds**, with identical entry win counts 19, 37, 18 and 26,
and no draws: approximately **4.0x faster** on the measured machine. A ten-round
Giant Eyeball/Spectet/Spectet/Giant Eyeball fight at seed 3 took 4.91 seconds with
the native workspace loops versus 4.42 seconds with the direct blocks, with
identical full combat state and RNG. This is a synthetic reference snapshot,
not a captured live arena accuracy measurement. Longer fights still take longer;
the standalone verifier remains sequential. Progress is aggregated while the
overlay workers run.
Qt tests exercise the button and results at 360px and 760px in both host themes,
including high-DPI captures. Leaving the arena cancels the worker and prevents
an old result from being published.