# Plan: the values of the file, not the defaults of `seq.system`

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: draft (2026-09-30). The user approved D1 and D4 of section 5.
Phase 1 needs only these two decisions, so it can start. Do not start
phase 2 before the approval of D5, or phase 3 before the approval of D2
and D3.

## 1. Goal

Fix the problem that the pulseq-reports session found in `gradient.slew.axis`,
and fix the other places where a check uses a value of `seq.system` that
does not come from the file or from the target profile.

The source of the problem report:
`/Users/dylan/dev/pulseq-reports/.claude/worktrees/optimistic-pasteur-528cdc/pulseq-checks-raster-findings.md`
(not in this repository). This plan uses its reproduction and its "Decision
needed" section.

The rule that this plan applies (from `docs/usage.md`, section 1, "No default
limits", and the notes of section 2.2): a check uses a value only when the
file or the target profile gives it. A value that neither gives is not
replaced by a pypulseq default.

Not in this plan: the release tag after the fixes, and the port to
pulseq-reports. Section 8 gives what the port needs.

## 2. Context (verified on 2026-09-30)

### 2.1 Two sources for each raster after `Sequence.read`

pypulseq `1.5.0.post1` (the pinned fork):

1. `read_seq.py:57-60`: `read` first sets `seq.grad_raster_time`,
   `seq.rf_raster_time`, `seq.adc_raster_time` and
   `seq.block_duration_raster` from `seq.system`.
2. `read_seq.py:76-92`: the `[DEFINITIONS]` section of the file replaces
   each raster that the file declares.
3. `read_seq.py:247-259`: for a file of format older than 1.4.0, `read`
   adds each raster that the file does not declare to `seq.definitions`,
   with the value of step 1 (`set_definition`). For a file of format 1.4.0
   or newer, `read` does not add a missing raster to `seq.definitions`.
4. `read` does not change `seq.system`.

`run._read_sequence` (`run.py:142`) reads the file with
`pp.Sequence(system=target.make_opts())`. Thus `seq.system` has the rasters
of the target profile, or the pypulseq defaults (10 µs, 1 µs, 100 ns, 10 µs)
when the profile has no `[rasters]`.

The result: `seq.grad_raster_time` is the raster that the file declares.
When the file does not declare it, `seq.grad_raster_time` is the raster of
the target, or the pypulseq default. `seq.system.grad_raster_time` is always
the raster of the target or the pypulseq default.

### 2.2 Where pypulseq uses these rasters when it reads blocks

- `block.py:416-434`: the sample times of an arbitrary gradient without a
  time shape use `seq.grad_raster_time`.
- `read_seq.py:546`: the block durations of a file of format 1.4.0 or newer
  are the block duration column times `seq.block_duration_raster`.
- `block.py:483`: `get_block` gives each ADC `seq.system.adc_dead_time`.
  Only `timing.pypulseq` uses it, and that check lists
  `opts.adc_dead_time` as an input.
- `read_seq.py:419-431` (`detect_rf_use`, for a file older than 1.5.0):
  the RF use comes from `seq.system.B0` and `seq.system.gamma`. No check of
  version 1 reads the RF use.

### 2.3 The reproductions

Run with the `.venv` of the main checkout, on `main` at `024289a` (the code
of `origin/main` at `965c1b6` is the same).

**R1, the report's script.** The file has a 4 µs gradient raster, a ramp of
46.97 T/m/s and a junction step of 58.72 T/m/s. `max_slew` is 50 T/m/s.

| Profile `[rasters]` | `gradient.slew.axis` | Value (T/m/s) | Block |
|---|---|---|---|
| none | pass | 46.97 | 1 (the ramp) |
| `GradientRasterTime = 4e-6` | fail | 58.72 | 2 (the junction) |
| `GradientRasterTime = 10e-6` | pass | 46.97 | 1 (the ramp) |

**R2, a raster that the file does not declare.** The same kind of file, with
an arbitrary gradient of 4 µs samples (a peak slew of 46.97 T/m/s). In a
copy, the `GradientRasterTime` line is renamed. A profile without
`[rasters]` reads the copy with `seq.grad_raster_time = 1e-05` (the pypulseq
default), and `gradient.slew.axis` passes with 18.79 T/m/s. `timing.rasters`
is "not evaluated", because the profile has no rasters. No result tells the
user that a default was used.

**R3, the gamma of the target.** A profile with `gamma = 40e6`,
`max_grad = 20` mT/m. The file is built with `gamma = 40e6` and a trapezoid
of 21 mT/m (840 kHz/m). `gradient.amplitude.axis` passes with the value
19.73 mT/m (840 kHz/m divided by 42.576 MHz/T). The limit is 20 mT/m. The
gradient is 5 % above the limit.

## 3. The findings

### F1. `gradient.slew.axis` divides the junction step by the raster of the target

`grad_limits.py:573`: `grad_raster = seq.system.grad_raster_time`.
`grad_limits.py:474` divides each junction step by it. This is the raster of
the target, or the pypulseq default (R1). Two problems:

1. A profile without `[rasters]` gets a value that uses the pypulseq default
   (10 µs), and `gradient.slew.axis` does not list a raster as an input.
2. When the target raster is not the file raster, the step is divided by a
   raster that the waveform of the file does not use. The specification says
   "divided by the gradient raster time of the sequence".

The segment slopes use the times of the file (`seq.grad_raster_time` through
`get_block`). Thus the two parts of the quantity use different rasters now.

### F2. A raster that the file does not declare comes from `seq.system`

When the file does not declare a raster (a file of format older than 1.4.0,
or a damaged file), pypulseq uses the raster of `seq.system` (section 2.1).
When the profile has no `[rasters]`, that is a pypulseq default (R2). These
measurements use such a raster:

| Raster | Measurement | Checks |
|---|---|---|
| `GradientRasterTime` | the sample times of an arbitrary gradient without a time shape | `gradient.slew.axis`; the location times of `gradient.amplitude.axis` and `gradient.amplitude.any-orientation`; `pns.safe` |
| `GradientRasterTime` | `dt` of `pns_levels` (`pns_levels.py:141`) | `pns.safe` |
| `GradientRasterTime` | the junction step, after the fix of F1 | `gradient.slew.axis` |
| `BlockDurationRaster` | the block durations, so the block start times | the locations of all gradient checks; `pns.safe` (the samples and `on_raster`) |

`RadiofrequencyRasterTime` and `AdcRasterTime`: no check of version 1 except
`timing.pypulseq` uses them, and it lists all four rasters as inputs.

`timing.rasters` gives "error" for a file of format 1.4.0 or newer that does
not declare a raster. It is "not evaluated" for a profile without
`[rasters]`. For a file older than 1.4.0 it compares the target with itself
and passes (as its specification says). So no result tells the user about R2.

### F3. The gradient checks convert the file values with a constant gamma

- `grad_limits.py` converts each measured value from Hz/m (Hz/m/s) to mT/m
  (T/m/s) with the constant `seq_utils.GAMMA` (42.576 MHz/T): lines 256,
  511, 516, 521 and 532.
- `checks/gradient.py:63-68` and `profile.py:319-323` convert the limits with
  the gamma of the `Opts` of the target (`opts.gamma` of the profile, or the
  pypulseq default).
- `pns_levels.py:176` divides by `seq.system.gamma` (the gamma of the target).
- `run.py:163-164` and `grad_limits.py:118-119` convert the limits of
  `seq.system` with `GAMMA`, not with `seq.system.gamma`.

When a profile gives a `gamma` that is not 42.576 MHz/T, the value and the
limit of each gradient check use different gamma values, and the result can
be wrong (R3). `tests/test_check_gradient.py:356-370` tests the limit side
of this on purpose ("not the 42.576 MHz/T of the measurement"), so the
current behavior is a design choice. But the value and the limit are not
comparable when the two gamma values differ.

### F4. `docs/usage.md` says that `gamma` is used only for the limits

`docs/usage.md`, section 2.2, notes: "The one use of a default is `gamma`,
for the conversion of the units of `max_grad` and `max_slew`". `pns.safe`
also uses the gamma of the target, or the pypulseq default (F3).

### 3.1 What the audit found correct

| Place | What it uses | Result |
|---|---|---|
| `pns_levels.py:141` | `dt = seq.grad_raster_time` | The file raster. Correct, except F2. |
| `pns_levels.py:176` | `seq.system.gamma` | The file does not declare gamma, so the target is its only source. See F3 and F4. |
| `sampling.py`, `seq_utils.hold_samples` | the raster comes from the caller | No raster of their own. |
| `seq_index.py:114` | `seq.block_durations` | The file values. Correct, except F2. |
| `checks/timing.py`, `timing.rasters` | `seq.definitions` against `profile.rasters` | As designed (design section 5.10). |
| `checks/timing.py`, `timing.pypulseq` | `check_timing` with `seq.system` | As designed (decision 5). All the values of the target that it reads are inputs. |
| `profile.py:319-323`, `checks/gradient.py:63-68` | the `Opts` of the target | Correct for the limits. See F3 for the values. |
| `pns.py` (`pns_levels_for` cache) | keyed by the sequence object | `run_checks` reads one sequence object for each target, so a target never gets the levels of a different target. |
| `asc.py`, `asc_profile.py`, `extensions.py`, `results.py`, `registry.py`, `config.py`, `cli.py` | no raster, no `seq.system` | No problem. |
| `scripts/compare_with_cards.py`, `scripts/budget.py` | the pypulseq default rasters, the same as the rasters of their files | The fixes do not change their results. |

## 4. The changes

### 4.1 F1: the junction step uses the file raster

- `grad_limits.py:573`: `grad_raster = seq.grad_raster_time`.
- `grad_limits.py`, the module docstring (line 21): say that the raster is
  the gradient raster of the sequence, `seq.grad_raster_time` (the
  `GradientRasterTime` that the file declares), not the raster of
  `seq.system`. Say why: the segment slopes use the times of the file, and
  `add_block` checked the step against the raster that built the file.
- `checks/gradient.py`, `_SlewAxis.spec`: the version stays 1 (D4). In
  part (b) of the quantity, say "divided by the gradient raster time of the
  sequence (the `GradientRasterTime` that the file declares)". Add one
  sentence: a difference between the raster of the file and the raster of
  the target is the subject of `timing.rasters`.
- `docs/checks.md`: make it again (`scripts/check_docs.py`).
- `CHANGELOG.md`: under "Unreleased", "Fixed", add the junction raster to
  the entry of `gradient.slew.axis` (PR #21).

The inputs of `gradient.slew.axis` do not change (decision D1).

### 4.2 F3 and F4: one gamma for the value and the limit

- `grad_limits.gradient_limits`: a new keyword argument
  `gamma: float = GAMMA` (Hz/T). Each conversion of `grad_limits.py` uses it
  in place of `GAMMA`: lines 256, 511, 516, 521, 532, and `_default_limits`
  (lines 118-119). The default keeps the behavior of pulseq-reports.
- `checks/gradient.py`, `_measurement`: give `gradient_limits` the gamma of
  the target, `ctx.profile.make_opts().gamma`, the same gamma as
  `_hardware_limits`. With the opt-in of decision 4
  (`ctx.limits_source == "sequence object"`), give `seq.system.gamma`, and
  `run._hardware_limits` converts the limits of `seq.system` with
  `seq.system.gamma` (not `GAMMA`).
- `checks/gradient.py`: the three specifications stay version 1 (D4). The
  quantity text says that the value is converted with the gamma of the
  target (`opts.gamma`, or 42.576 MHz/T, the value of pypulseq, when the
  profile does not give it).
- `checks/pns.py`: the quantity text says that the gradient is divided by the
  gamma of the target, with the same words. The version does not change: the
  value does not change.
- `docs/usage.md`, section 2.2, notes: the one use of a default is `gamma`
  (42.576 MHz/T) when the profile does not give it: for the units of the
  limits, for the units of the gradient values, and for the SAFE model.
- `tests/test_check_gradient.py:356-370`: change the docstring. The test
  stays.

### 4.3 F2: the source of each raster

1. **Find the rasters that the file does not declare.** In
   `run._read_sequence`, record each raster name that pypulseq adds to
   `seq.definitions` during `seq.read`. Wrap `set_definition` of the
   sequence object for the duration of the read; `read_seq.py:250-259` is
   the only place where `read` calls it. After the read, a raster that is
   not in `seq.definitions` is also not declared (format 1.4.0 or newer).
   A test pins this behavior of pypulseq (section 6).
2. **The source of each raster.** `RunContext.raster_sources`: a mapping
   from each of the four raster names to one of:
   - `"file"`: the file declares it;
   - `"target"`: the file does not declare it, and the profile gives
     `rasters.<name>`;
   - `"sequence object"`: the sequence is a `pp.Sequence` object (its
     rasters come from the system of its author);
   - `"pypulseq default"`: neither the file nor the profile gives it.
3. **`CheckSpec.rasters`**: a new field, `tuple[str, ...] = ()`. It is the
   raster names that the measurement of the check uses. `run._run_rule`
   gives "not evaluated" before `run` when a listed raster has the source
   `"pypulseq default"`. The reason names the raster: "the file does not
   declare GradientRasterTime and the target 'x' does not give
   rasters.GradientRasterTime".
4. **The rasters of each check** (D3): `gradient.amplitude.axis`,
   `gradient.slew.axis`, `gradient.amplitude.any-orientation` and `pns.safe`
   list `("GradientRasterTime", "BlockDurationRaster")`. The two timing
   checks list none (they read the rasters through their inputs).
5. `scripts/check_docs.py` writes the new field in `docs/checks.md`.
   `docs/usage.md`: section 1 ("No default limits") and the section on
   `CheckSpec` for plugin authors.
6. The four checks of item 4 change their "not evaluated" rule. Their
   specifications stay version 1 (D4), and the CHANGELOG says what changed.

This changes `rules.py`, `run.py` and `scripts/check_docs.py`. The branch
`feature/check-findings` (phase 1 of `docs/plans/check-findings.md`) changes
the same files now. Start this phase after that branch merges.

## 5. Decisions (the user must approve them)

| # | Decision | Recommendation | Alternatives |
|---|---|---|---|
| D1 | The raster of the junction step | Decided (2026-09-30): (a), the file raster, `seq.grad_raster_time` (option (a) of the report). It is the raster that built the waveform and that `add_block` used. It needs no new input. `pns_levels` uses the same raster. R6 (design section 5.10) says that the rasters of the file must equal the rasters of the target, and `timing.rasters` fails a file with different rasters. Thus (a) and (b) give the same value when `timing.rasters` passes. They give different values only when the profile has no `[rasters]` or when the rasters are different (R1). Then (a) gives the slew of the waveform of the file, and only `timing.rasters` reports the different rasters. | (b) The target raster: add `rasters.GradientRasterTime` to the inputs, and say "of the target" in the quantity. Then a profile without `[rasters]` gives "not evaluated", and the value describes a play of the file that design section 5.10 does not define. |
| D2 | A raster that the file does not declare | Section 4.3: a raster of the target replaces it (as the interpreter of the target does for an old file), and a pypulseq default makes the check "not evaluated". | (b) Make every gradient check and `pns.safe` list `rasters.GradientRasterTime` and `rasters.BlockDurationRaster` as inputs. Simple, but then a profile without `[rasters]` never gets these checks, also for a file that declares its rasters. (c) Do nothing, and document R2 as a known limit. |
| D3 | The rasters of each check (section 4.3, item 4) | Both rasters for all four checks. The amplitude value of an arbitrary gradient does not depend on the raster, but its location time does. | Only `GradientRasterTime` for `gradient.slew.axis` and `pns.safe`. |
| D4 | The version of a specification in the release candidates | Each specification stays version 1 until the first final release (0.1.0). A change of a rule is in the CHANGELOG only (decided 2026-09-30, PR #22). The JSON result format also stays 1 (PR #23). | One version step for each release. One version step for each PR. |
| D5 | F3, the gamma of the value | The gamma of the target (section 4.2). The value and the limit then use one gamma, and the limit in mT/m is the number that the profile gives. | (b) Convert the limit with `GAMMA` too: the pass or fail is correct (the ratio in Hz/m), but the limit in the result is not the number of the profile. (c) Refuse a profile `gamma` that is not 42.576 MHz/T. |

## 6. Tests

### Phase 1 (F1)

- `tests/test_grad_limits.py`: a sequence built with a 4 µs gradient raster
  (R1), written, and read with `pp.Sequence()` (10 µs in `seq.system`).
  `gradient_limits` gives the junction value step / 4 µs on `y`, at block 2,
  at the time of the junction. A second case: the same sequence object
  before the write (no change of behavior).
- `tests/test_check_gradient.py`: R1 through `run_checks`, with the three
  profiles of the report. Each gives a fail, 58.72 T/m/s, block 2. The spec
  version stays 1.
- `TESTS.md`: the new tests.

### Phase 2 (F3, F4)

- `tests/test_grad_limits.py`: `gradient_limits(seq, gamma=40e6)` gives the
  values in mT/m and T/m/s with 40 MHz/T.
- `tests/test_check_gradient.py`: R3 gives a fail with the value 21 mT/m
  and the limit 20 mT/m. A profile without `gamma` gives the same results
  as before. The opt-in of decision 4 with a `seq.system` gamma of 40 MHz/T
  gives the values and limits with that gamma.

### Phase 3 (F2)

- `tests/test_run.py`: the raster sources for a file of format 1.5.0 (all
  `"file"`), for the same file with a `GradientRasterTime` line removed and
  a profile with and without `[rasters]` (`"target"`, `"pypulseq
  default"`), for a hand-written file of format 1.3.1 (pypulseq adds the
  four definitions; this test pins `read_seq.py:247-259`), and for a
  `Sequence` object (`"sequence object"`).
- `tests/test_check_gradient.py`, `tests/test_check_pns.py`: R2 gives "not
  evaluated" with the reason of section 4.3, item 3. With
  `rasters.GradientRasterTime = 4e-6` in the profile, the checks are
  evaluated, with the 4 µs raster.
- `tests/test_results.py` or `tests/test_run.py`: a plugin `CheckSpec`
  without `rasters` works as before.

## 7. How to execute this plan

One branch and one PR for each phase, each from `origin/main`, in
`.worktrees/<short-name>` (the `start-task` skill). Before each PR:
`nix develop --command scripts/check`.

| Phase | Branch | Files | Start |
|---|---|---|---|
| 1 | `fix/junction-raster` | `grad_limits.py`, `checks/gradient.py`, `tests/test_grad_limits.py`, `tests/test_check_gradient.py`, `docs/checks.md` (made again), `CHANGELOG.md`, `TESTS.md` | Now. Only `docs/checks.md`, `CHANGELOG.md` and `TESTS.md` overlap with `feature/check-findings`; make `docs/checks.md` again after a rebase. |
| 2 | `fix/target-gamma` | `grad_limits.py`, `checks/gradient.py`, `checks/pns.py`, `run.py` (`_hardware_limits` only), `docs/usage.md` (section 2.2), the tests of section 6, `docs/checks.md`, `CHANGELOG.md`, `TESTS.md` | After phase 1 (the same files). |
| 3 | `feature/raster-sources` | `rules.py`, `run.py`, `scripts/check_docs.py`, the four check modules, `docs/usage.md`, the tests of section 6, `docs/checks.md`, `CHANGELOG.md`, `TESTS.md` | After phase 2 and after `feature/check-findings` merges. |

Each phase is small. One worker (`worker-medium`) for each phase is enough;
the main agent reviews the diff. Phase 3 has a design part (the wrapper of
`set_definition`); give it to `worker-high`, or do it in the main agent.

When all phases merge: move the lasting content of this plan to
`docs/usage.md` and the design, and delete this file (the `start-task` rule
for planning documents), in the PR of phase 3.

## 8. The port to pulseq-reports

`grad_limits.py` is shared. After phase 1 merges and a new tag of
pulseq-checks exists:

- `src/pulseq_reports/grad_limits.py:568`: the change of section 4.1.
  pulseq-reports reads each file with `pp.Sequence()`, so today its
  Gradient limits card divides each junction step by 10 µs. For a file with
  a 4 µs raster it gives a junction slew 2.5 times too small.
- After phase 2: the `gamma` argument, with the default `GAMMA`. The card
  does not change.
- Phase 3 is in the run function of pulseq-checks only. Nothing to port.

## 9. Outside this plan

- A profile with `rise_time` and no `max_slew`: done in PR #21
  (`fix/slew-rise-time`). `opts.max_grad` with `opts.rise_time` gives the
  slew limit `max_grad / rise_time`, and `max_slew` with `rise_time` is a
  profile error.

## 10. Results

None yet.
