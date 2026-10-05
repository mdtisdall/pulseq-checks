# Plan: move to pulseq-analysis 0.1.0rc5

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: planned (2026-10-04). The user approved the decisions D1 to D7 of
section 5.

## 1. Goal

pulseq-checks uses pulseq-analysis `v0.1.0rc5` in place of `v0.1.0rc4`. The
results of the checks do not change: the same states, values, limits, units
and findings, to the float rounding. There are two exceptions:

1. A target with a negative gamma. Now the values and the limits of its
   gradient checks are negative, and the checks fail (fact 2.2.2). After
   this change, it gives the same results as the magnitude of its gamma
   (D2, D6, a fix).
2. `pns.safe` for a `Sequence` object whose `seq.system.gamma` is not the
   gamma of the target, with the limits from the profile. rc4 divided by
   `seq.system.gamma` (fact 2.2.3). After this change, `pns.safe` uses
   the gamma of the target, as the gradient checks do (D5).

In rc5, no value of pulseq-analysis uses a gamma. The gradient values are in
Hz/m and Hz/m/s, and the PNS values are in Hz/T. pulseq-checks converts them
with the magnitude of the gamma of the target, `gamma_magnitude(ctx)`, before
it compares or reports them. A gamma can be negative (for example 15N or
29Si). pulseq-checks accepts it and does not require a positive gamma
(section 3.1).

Not in this plan: a gamma in the JSON result (D3), a new check, a change of
the JSON result format, a change of a `spec.version`, and a check of a gamma
that is 0 or not finite. The profile reader does not check the gamma now.
After this change, a gamma of 0 gives the threshold 0, which rc5 refuses
(fact 2.1.6), so `pns.safe` gives "error". That is a separate fix.

## 2. Context (verified on 2026-10-04, `main` at `e38bf5c`)

### 2.1 What changed in pulseq-analysis

The source is the change report of pulseq-analysis for rc4 to rc5 (the
CHANGELOG at the tag, and `docs/usage.md` section 8 at the tag). In summary:

1. **No gamma.** `seq_utils.GAMMA` is removed. `gradient_limits` and
   `block_gradient_values` have no `gamma` argument, and a call with
   `gamma=` raises `TypeError`. The analyses `gradient.limits` and
   `gradient.blocks` have `spec.params == ()`. The PNS model does not read
   `seq.system.gamma`.
2. **Units.** To get the unit of rc4, divide by `|γ|` (γ in Hz/T):

   | Values | rc5 unit | To get the rc4 unit |
   |---|---|---|
   | `grad_limits` amplitudes, RMS | Hz/m | `v * 1e3 / abs(γ)` (mT/m) |
   | `grad_limits` slew rates, junction steps | Hz/m/s | `v / abs(γ)` (T/m/s) |
   | `pns_levels`, `pns` PNS values | Hz/T | `v / abs(γ)` (fraction, 1 = 100 %) |
   | `pns_levels` thresholds (an input) | Hz/T | give `f * abs(γ)` for a fraction `f` |
   | `grad_spectrum` | Hz/m/sqrt(Hz) | no change |

3. **Names.** Only the unit part of each name changes, and the field order
   does not change:
   - `AxisResult`: `peak_hz_per_m`, `max_slew_hz_per_m_per_s`,
     `rms_hz_per_m`.
   - `GradientLimits`: `vector_peak_hz_per_m`, `whole_rms_hz_per_m`.
   - `BlockGradientValues`: `peak_hz_per_m`, `slew_hz_per_m_per_s`,
     `junction_hz_per_m_per_s`, `vector_peak_hz_per_m`.
   - `PnsLevels`: `level_min_hz_per_t`, `level_max_hz_per_t`,
     `peak_hz_per_t`, `axis_peaks_hz_per_t`. `PnsInterval.peak_hz_per_t`.
     `PnsPrediction.peak_hz_per_t`, `.axis_peaks_hz_per_t`.
   - `pns_levels`, `pns_levels_for`: `thresholds_hz_per_t=()` in place of
     `thresholds=(PNS_LIMIT,)`. The default `()` gives `above == {}`.
     `PNS_LIMIT` stays `1.0` (a fraction), but it is not a default.
4. **Series.** `pns.safe.levels` has `spec.params == ("hardware",
   "thresholds_hz_per_t")`. Its series have the unit `"Hz/T"`. The threshold
   series is `pns_above_<k>`, where `<k>` is the position of the threshold
   from 0. Thus `pns_above_1` of rc4 is `pns_above_0` for one threshold.
   `meta["threshold"]` is the threshold in Hz/T. Every `spec.version` stays
   1, and the `Series` JSON format does not change.
5. **Behavior.** The `level_*` arrays of `PnsLevels` are read-only.
   `PnsLevels` and `GradientSpectrum` compare by value and are not hashable.
   `pns_levels_for` keeps one result for each tuple of thresholds, so two
   targets with the same SAFE hardware and different gammas run the model
   two times. pulseq-checks does not change these arrays in place and does
   not hash these values, so no code changes for item 5.
6. **Each value is a magnitude** (verified in the source at the tag
   `v0.1.0rc5`). `grad_limits` takes `np.abs` of each amplitude, slew rate
   and junction step, and an RMS is not negative. A PNS total is not
   negative. `_validated_thresholds` of `pns_levels` raises `ValueError` for
   a threshold that is not finite or not above 0. Thus a threshold made from
   a negative gamma must use its magnitude.

### 2.2 The gamma in pulseq-checks now

1. `bindings.gamma(ctx)` (`bindings.py:43–48`) gives `seq.system.gamma`
   when `ctx.limits_source == "sequence object"`, else
   `ctx.profile.make_opts().gamma`. It is the gamma that converts the
   gradient limits. It is signed. In rc4 the gradient bindings gave it to
   `gradient_limits` and `block_gradient_values`, which divided by it.
2. The gradient limits are converted with the signed gamma, in three places:
   `profile.py:341–342` (`TargetProfile.hardware_limits`),
   `run.py:242–243` (the limits of `seq.system`), and
   `checks/gradient.py:101–103` (`_hardware_limits`, a target with only one
   limit). A negative gamma gives negative limits and, through the binding
   (fact 1), negative values. The rule `value <= limit * (1 + 1e-9)` is then
   false for any gradient, so each gradient check of a sequence with
   gradients fails, and the reported numbers are negative.
3. `pns.safe` compares `levels.peak < 1` and reports `100 * levels.peak`.
   In rc4, the model divided by `seq.system.gamma`. For a `.seq` path,
   `run.py:193` reads the file with `target.make_opts()`, so that is the
   gamma of the target. For a `Sequence` object, `run.py:110` uses the
   object of the caller, so it is the gamma of that object. This is true
   also when the limits come from the profile, where `gamma(ctx)` is the
   gamma of the profile.
4. `pp.Opts` accepts a negative gamma, keeps it signed in `opts.gamma`, and
   converts the units with its magnitude. With `gamma=-40e6`, `max_grad=28`
   mT/m gives `max_grad == 1.12e6` Hz/m, a positive value (verified with the
   pinned pypulseq on 2026-10-04). Thus `opts.max_grad` and `opts.max_slew`
   are magnitudes in Hz/m and Hz/m/s for each sign of gamma.
5. The SAFE model does not change when the sign of the whole waveform
   changes: pypulseq `safe_pns_prediction.py:245–247` takes `abs` of each
   filtered term. In rc4 the PNS model divided the waveform by the signed
   `seq.system.gamma`, so `pns.safe` is correct now for a negative gamma.
   Only the gradient checks have the bug of fact 2.2.2.

## 3. Design

### 3.1 The sign of gamma

A negative gamma is valid. pulseq-checks does not refuse it and does not
make it positive where it keeps it. Each limit of a check of this package
is a magnitude (`max_grad`, `max_slew`, the PNS stimulation limit), and each
value that a check compares with it is a magnitude (fact 2.1.6). The
magnitude of a physical value is the magnitude of the Hz value divided by
`|γ|`. Thus each conversion uses `|γ|`, and no check uses the sign of gamma.
A check that needs the physical direction of a gradient (not in this
package now) would divide the signed Hz/m value by the signed gamma.

The rules (D2, D7):

1. `gamma(ctx)` stays signed and keeps its rule (fact 2.2.1): it is the
   gamma of the target.
2. `gamma_magnitude(ctx)` is `abs(gamma(ctx))`. The checks and
   `pns_threshold_hz_per_t` use only this function to convert. No check
   writes `abs(gamma(ctx))` itself.
3. Where there is no `RunContext` (the limits of `profile.py` and
   `run.py`, and `scripts/compare_with_cards.py`), the code writes
   `abs(built.gamma)`, `abs(seq.system.gamma)` or
   `abs(profile.make_opts().gamma)`. These are the gamma that `gamma(ctx)`
   gives for the same target and limits source (fact 2.2.1).
4. `opts.max_grad` and `opts.max_slew` are already magnitudes (fact 2.2.4).
   Do not take `abs` of them: a negative limit in a profile is a separate
   matter.

All the checks of a target use this one gamma, `pns.safe` too (D5). The
table gives each place where a gamma converts a value:

| Place | Value | Conversion |
|---|---|---|
| `checks/gradient.py`, `_GradientCheck.run` | Hz/m, Hz/m/s of `gradient.limits` and `gradient.blocks` | `* self._scale(gamma_magnitude(ctx))` |
| `checks/gradient.py:101–103`, `_hardware_limits` | `opts.max_grad`, `opts.max_slew` | `* 1e3 / gamma_magnitude(ctx)`, `/ gamma_magnitude(ctx)` |
| `profile.py:341–342` | `built.max_grad`, `built.max_slew` | `* 1e3 / abs(built.gamma)`, `/ abs(built.gamma)` |
| `run.py:242–243` | `seq.system.max_grad`, `seq.system.max_slew` | `* 1e3 / abs(seq.system.gamma)`, `/ abs(seq.system.gamma)` |
| `bindings.py`, `pns_threshold_hz_per_t` | `PNS_LIMIT` | `* gamma_magnitude(ctx)` |
| `checks/pns.py` | PNS values in Hz/T | `/ gamma_magnitude(ctx)` |
| `scripts/compare_with_cards.py`, `_checks_pair` | Hz/m, Hz/m/s of `gradient_limits` | `* 1e3 / g` for mT/m, `/ g` for T/m/s, `g = abs(profile.make_opts().gamma)` |

A negative gamma then gives the same results as its magnitude.

### 3.2 The bindings (`src/pulseq_checks/bindings.py`)

1. Remove `_gradient_arguments`. Bind `gradient.limits` and
   `gradient.blocks` with `Binding()`. Keep both entries:
   `test_each_analysis_of_pulseq_analysis_but_gradient_spectrum_has_a_binding`
   expects a binding for each analysis except the spectrum.
2. Keep `gamma(ctx)` and its rule. Change its docstring: it is the signed
   gamma of the target, a negative gamma is valid, and no analysis uses it.
   To convert, use `gamma_magnitude(ctx)`.
3. Add `gamma_magnitude(ctx) -> float`, which gives `abs(gamma(ctx))`. Its
   docstring says that each limit and each value of the checks is a
   magnitude, so a conversion uses the magnitude of gamma (section 3.1).
4. Add `pns_threshold_hz_per_t(ctx) -> float`, which gives
   `PNS_LIMIT * gamma_magnitude(ctx)`. It is above 0 for each gamma that is
   not 0 (fact 2.1.6). `_pns_safe_arguments` passes
   `"thresholds_hz_per_t": (pns_threshold_hz_per_t(ctx),)`. The check
   `pns.safe` calls the same function, so it indexes `levels.above` with
   the same float.
5. The module docstring stays correct. Read it again after the change.

### 3.3 The check `pns.safe` (`src/pulseq_checks/checks/pns.py`)

1. `threshold = pns_threshold_hz_per_t(ctx)` and `g = gamma_magnitude(ctx)`.
2. The state: `FAIL` when `levels.peak_hz_per_t >= threshold`, else `PASS`.
   This is the condition of pulseq-analysis for a sample in `above`. Thus
   a fail always has at least one finding, and a pass has none. A
   comparison of `peak / g` with 1 could differ from it by one rounding at
   the boundary.
3. The value: `100 * levels.peak_hz_per_t / g`. The findings:
   `levels.above[threshold]`, and `peak_percent` is
   `100 * interval.peak_hz_per_t / g`.
4. The spec text: `quantity` (lines 26–30) says that pulseq-analysis gives
   the total in Hz/T, with no gamma, and that the check divides it by the
   magnitude of the gamma of the target (`|opts.gamma|`, or 42.576 MHz/T, the value of
   pypulseq, when the profile does not give it; `|seq.system.gamma|` when
   the limits come from the sequence object). For a `Sequence` object with
   the limits from the profile, the text says that the gamma is that of the
   profile, not that of `seq.system` (D5). A negative gamma is valid, and
   the check uses its magnitude. `tolerance` says that the
   rule is `peak >= limit` in Hz/T, the rule of `pns_norm < 1` of pypulseq
   without the division. `spec.version` stays 1 (rule of the release
   candidates).
5. The module docstring: `PnsLevels.above` is keyed by the Hz/T threshold.

### 3.4 The gradient checks (`src/pulseq_checks/checks/gradient.py`)

Convert, then compare (D1). `HardwareLimits`, the tolerance, the result
values, the limits and the finding data stay in mT/m and T/m/s.

1. Each subclass of `_GradientCheck` gets a static method
   `_scale(g: float) -> float`, where `g` is a magnitude: `1e3 / g` (Hz/m to
   mT/m) for `_AmplitudeAxis` and `_AmplitudeAnyOrientation`, and `1 / g`
   (Hz/m/s to T/m/s) for `_SlewAxis`. `run` calculates
   `scale = self._scale(gamma_magnitude(ctx))` one time, and gives it to
   `_candidates(measured, scale)` and `_findings(blocks, limit, scale)`.
   Each of them multiplies its values by `scale` before the comparison. The
   arrays of `BlockGradientValues` are multiplied as whole arrays, one time
   for each column. `_entries_above_limit` gets the scaled arrays, so it
   does not change. `scale` is above 0, so the order of the candidates and
   the tie rule do not change.
2. The renames, at `e38bf5c`: lines 286, 307, 416, 423–424, 454, 543 and
   560 (section 2.1.3).
3. `_hardware_limits` (lines 101–103): divide by `gamma_magnitude(ctx)`
   in place of `opts.gamma`. The function is reached only when
   `ctx.hardware_limits` is None, thus with the limits from the profile, so
   `gamma(ctx)` is `opts.gamma` there (fact 2.2.1).
4. `_GAMMA` (lines 54–59, used at lines 217, 334 and 470): pulseq-analysis
   gives the values in Hz/m and Hz/m/s with no gamma, and the check
   converts them with the magnitude of the gamma of the target (or of
   `seq.system`). The limit uses the same magnitude. A negative gamma is
   valid. Change the module docstring (lines 1–12) where it says what the
   analyses give.
5. The `limit` texts (lines 231–232, 349–351 and 485–486) say "converted
   from the unit of the profile with the gamma of its Opts". Change them to
   "with the magnitude of the gamma of its Opts". The `quantity` texts that
   say "is converted from Hz/m" get the same change; read each one again.

### 3.5 The limits (`src/pulseq_checks/profile.py`, `src/pulseq_checks/run.py`)

`profile.py:341–342` and `run.py:242–243`: divide by `abs(built.gamma)` and
`abs(seq.system.gamma)` (D2, section 3.1 rule 3). The `HardwareLimits`
docstring says that the limits are magnitudes, converted with the magnitude
of gamma.

### 3.6 The comparison script (`scripts/compare_with_cards.py`)

`_checks_pair` (lines 422 and 452–457) reads the fields of
`gradient_limits`. Rename them, and convert with
`g = abs(profile.make_opts().gamma)`: the output keys
`peak_mt_per_m`, `slew_t_per_m_per_s` and `vector_peak_mt_per_m` keep
their names and units. Lines 321–371 use the modules of pulseq-reports and
do not change.

### 3.7 The dependency

`pyproject.toml:13`: `@v0.1.0rc4` to `@v0.1.0rc5`. Then
`nix develop --command uv lock`. The version of pulseq-checks stays
`0.1.0rc4` until the release PR (section 6, PR 3).

## 4. Tests

### 4.1 Changes to tests that exist

1. `tests/synthetic.py:7`, `tests/test_check_gradient.py:10`: remove the
   import of `GAMMA`. Define `GAMMA = 42.576e6  # Hz/T, the 1H gamma of
   pypulseq` in `tests/synthetic.py`, and import it from there in
   `test_check_gradient.py` and `test_check_pns.py`.
2. `tests/test_check_gradient.py`:
   - Line 348: `vector_peak_mt_per_m=` to `vector_peak_hz_per_m=`. The
     `AxisResult` and `GradientLimits` of lines 343–351 are hand-made, so
     their values are now in Hz/m and Hz/m/s. Write them as the mT/m and
     T/m/s values times the gamma of the profile of the test (`5.0 * 1e-3 *
     GAMMA`, `50.0 * GAMMA`), so that the expected values of the test do not
     change and it still checks a value with no block.
   - Search for other hand-made `AxisResult`, `GradientLimits` and
     `BlockGradientValues` values, and make their units Hz/m.
   - Lines 456–457: the calls of `gradient_limits` have no keyword
     arguments. Assert `call == {}` for each call.
   - Line 818: `calls[0] == {}`.
3. `tests/test_bindings.py`:
   - Lines 49–54 and 69: the bindings of the gradient analyses give `{}`.
     Rename the test of lines 49–54: `gamma(ctx)` is the gamma of the
     profile, and the gradient bindings give no argument.
   - Lines 71–72: remove the two assertions with `gradient_limits(seq,
     gamma=...)`. Replace them with `ctx.analysis("gradient.limits") ==
     gradient_limits(seq)`. The gamma now matters only in the checks, and
     `test_limits_from_sequence_converts_values_and_limits_with_the_gamma_of_seq_system`
     of `test_check_gradient.py` covers it.
   - Lines 80 and 84: the arguments are `hardware` and
     `thresholds_hz_per_t`, and `thresholds_hz_per_t ==
     (PNS_LIMIT * gamma_magnitude(ctx),)`.
4. `tests/test_check_pns.py`:
   - The gamma of a test is `g = abs(profile.make_opts().gamma)` of its
     profile. The profiles of this file give no gamma, so `g == GAMMA`, but
     the tests use `g`, so that they stay correct for a profile with a
     gamma.
   - Lines 87, 93 and 142: the helpers call `pns_levels_for` with
     `thresholds_hz_per_t=(PNS_LIMIT * g,)`, as the binding does, so that
     they get the kept result of the run, and read `.peak_hz_per_t`. The
     expected percent is `100 * peak_hz_per_t / g`.
   - Lines 238–301: `levels.above[PNS_LIMIT]` to the Hz/T key, and
     `interval.peak` to `interval.peak_hz_per_t` (lines 247, 253, 276,
     287). The percents of lines 247, 253 and 276 divide by `g`. Line 287
     scales the profile by the peak as a fraction, so it uses
     `peak_hz_per_t / g`.
5. `tests/test_run.py:803–805`: `thresholds_hz_per_t=(PNS_LIMIT * γ,)` and
   the series names `["pns_total", "pns_above_0"]`.
6. `tests/test_cli.py:710`: `pns_above_0`.
7. `tests/test_safe_model.py:117–118`: no change. `pns_levels(seq)` has no
   thresholds, and `_assert_levels_equal` compares `above == {}` on both
   sides. The helper stays, for `ignore=("hardware",)`.

### 4.2 New tests

1. `test_check_pns.py`: the state and the findings agree at the boundary.
   A hand-made `PnsLevels` (a fake `pns.safe.levels`) with
   `peak_hz_per_t == threshold` and one interval in `above[threshold]`
   gives "fail" with one finding.
2. `test_check_pns.py`: a profile with another gamma (for example 40 MHz/T)
   gives the same percent as the peak of `pns_levels_for` with that
   profile divided by that gamma. This shows that the check and the
   binding use one gamma.
3. `test_check_gradient.py` and `test_check_pns.py`, a negative gamma
   (D2). `pp.Opts` accepts it (fact 2.2.4).
   - One `.seq` file (fixed Hz/m values), read with a profile with
     `GAMMA_40` and with a profile with `-GAMMA_40`: the same states,
     values, limits and findings, for the three gradient checks and
     `pns.safe`. The values are not negative. This test isolates the
     conversion.
   - A `Sequence` object built with `pp.Opts(..., gamma=-GAMMA_40)`, whose
     amplitudes come from mT/m through that gamma (thus negative Hz/m), with
     `limits_from_sequence=True` (the limits of `run.py:242–243`): the same
     results as the same build with `GAMMA_40`.
   - A profile with a negative gamma and only `opts.max_grad` (the path of
     `_hardware_limits`): a positive limit.
4. `test_bindings.py`: `gamma(ctx)` is signed and `gamma_magnitude(ctx)` is
   its magnitude, for a profile and for a sequence object with the limits
   from `seq.system`, each with a negative gamma.
   `pns_threshold_hz_per_t(ctx) == PNS_LIMIT * gamma_magnitude(ctx)`, and it
   is above 0.
5. `test_check_pns.py` (D5): a `Sequence` object with `seq.system.gamma ==
   GAMMA_40` and a profile with no gamma (42.576 MHz/T). With the limits
   from the profile, the percent is the peak in Hz/T divided by 42.576e6.
   With `limits_from_sequence=True`, it is divided by 40e6.

The tests of the six other checks and of `acoustic.resonance-energy` must
pass with no change of their expected values. A value that changes only by
the float rounding of the new conversion is permitted: record it in
section 7.

### 4.3 `TESTS.md`

Change the entry of each test of section 4.1 that changes what it checks
(lines 2006–2007, 2172, 4255, 4374–4376 at `e38bf5c`, and the entries of
the gradient tests with the `gamma` keyword). Add an entry for each test of
section 4.2.

## 5. Decisions

Approved by the user (2026-10-04):

- **D1. Gradient checks: convert, then compare.** One helper converts the
  values of `gradient.limits` and `gradient.blocks` to mT/m and T/m/s with
  `gamma_magnitude(ctx)`. `HardwareLimits`, the tolerance, the results and the
  finding data stay in mT/m and T/m/s. The other choice was to compare in
  Hz/m and convert only the reported numbers. That touches `profile.py`,
  `run.py` and `rules.py` more, for no change of a result.
- **D2. `|γ|` everywhere.** A negative gamma is valid. The values and the
  limits all use `|γ|`, because each limit and each value of the checks is
  a magnitude (section 3.1). This includes the limits of `profile.py`,
  `run.py` and `checks/gradient.py`, which now use the signed gamma.
- **D3. The JSON result: documentation only.** The series of
  `pns.safe.levels` are in Hz/T, and the JSON result does not give the
  gamma of the target. `docs/usage.md` and the CHANGELOG say that a reader
  divides by `|γ|` of the target. The documentation also says that
  `meta["threshold"]` of `pns_above_0` is `PNS_LIMIT * |γ|`, and
  `PNS_LIMIT` is 1, so the percent is `100 * v / meta["threshold"]`. A
  gamma in the JSON result is a separate change.
- **D4. Three PRs** (section 6).
- **D5. One gamma for each target, `pns.safe` too.** `pns.safe` uses
  `gamma_magnitude(ctx)`, the gamma of the gradient checks. For a `Sequence` object
  with the limits from the profile, that is the gamma of the profile. rc4
  used `seq.system.gamma` there (fact 2.2.3), so this case changes when the
  two gammas are different. The CHANGELOG gives it under "Changed".
- **D6. The negative-gamma fix is in PR 2.** It is a fix of a bug of the
  gradient checks on `main` (fact 2.2.2). `pns.safe` does not have the bug
  (fact 2.2.5). A fix on rc4 alone would have to change the gradient
  binding and the three limit conversions, and PR 2 changes the same lines
  again. PR 2 gives it as its own "Fixed" entry of the CHANGELOG and says
  so in the PR description.
- **D7. `gamma_magnitude(ctx)`.** `gamma(ctx)` stays signed (the real value
  of the target). The new `gamma_magnitude(ctx)` in `bindings.py` is the
  one function that the checks and `pns_threshold_hz_per_t` use to convert.
  Thus `abs` is in one place, and the name says that it is a magnitude.

The PNS state rule in Hz/T (section 3.3, item 2) is from the change report
of pulseq-analysis, section 6, item 4.

## 6. How to execute this plan

1. **PR 1** (`docs/pulseq-analysis-rc5-plan`): this plan only.
2. **PR 2** (`chore/pulseq-analysis-rc5`, its own worktree): sections 3
   and 4, and the documentation of section 6.1, in one PR. The bump of the
   dependency breaks the tests until all the code changes are done, so the
   work cannot be split into more PRs. `spec.version` of each check stays
   1, and the JSON result format stays 1 (the rule of the release
   candidates). Run `nix develop --command uv sync --frozen` one time after
   `uv lock`, then `nix develop --command scripts/check`. Before the merge,
   set the status of this plan and fill in section 7.
3. **PR 3** (`chore/release-0.1.0rc5`): the version `0.1.0rc5` in
   `pyproject.toml` and `README.md:21`, the CHANGELOG heading, and the time
   budget (`scripts/budget.py`), as #53 did for `0.1.0rc4`. Section 2.1.5
   says that the SAFE model can now run one time for each gamma, so compare
   the time of `pns.safe` with `0.1.0rc4`.

### 6.1 Documentation (in PR 2)

1. `docs/usage.md`:
   - Section 1, the `opts` table (line 140), the row `gamma`: add to the
     notes that a gamma can be negative, and that the checks use its
     magnitude, because each limit is a magnitude.
   - The links to the usage document of pulseq-analysis (lines 815, 819,
     1002, 1301, 1303, 1305): `v0.1.0rc4` to `v0.1.0rc5`. Add a link to
     its section 8 (units and gamma) where the units are described.
   - Lines 844–851 (the full value): `thresholds_hz_per_t=(PNS_LIMIT *
     abs(target.make_opts().gamma),)`. Say that the PNS values are in Hz/T.
     Lines 855–859 say that a `Sequence` object of the run gets the kept
     result. Add: only with the same float threshold. With
     `limits_from_sequence=True`, the binding uses `seq.system.gamma`, so
     the example calls with `abs(seq.system.gamma)` to get the kept result.
   - Lines 1007–1060 (the JSON example): the unit `"Hz/T"`, the series
     `pns_above_0`, `meta["threshold"]` and the PNS values of `meta` in
     Hz/T (run the command again to get the item), and the sentence "1 is
     the stimulation limit" (line 1011): the stimulation limit is `|γ|` in
     Hz/T. Say how to get a percent: `100 * v / meta["threshold"]` of
     `pns_above_0`, which is `100 * v / abs(γ)` with the gamma of the
     target (D3).
   - Lines 1314–1324 (the bindings table): `gradient.limits` and
     `gradient.blocks` have no arguments. `pns.safe.levels` has
     `thresholds_hz_per_t=(pns_threshold_hz_per_t(ctx),)`. The first item
     of the list: `gamma(ctx)` is the signed gamma of the target, and the
     checks convert with `gamma_magnitude(ctx)`. Name both functions, so
     that a plugin uses the same gamma.
   - Lines 1330–1333 (`gradient.spectrum`): the conversion is
     `1e3 / abs(gamma)`.
   - Lines 1511–1512 (**Gamma**): the analyses use no gamma. The checks
     convert with `gamma_magnitude(ctx)`, and a negative gamma is valid.
   - Lines 1528–1561 (section 8.1, the plugin example):
     `levels.above[pns_threshold_hz_per_t(ctx)]`, with the import from
     `pulseq_checks.bindings`, and the binding call with
     `thresholds_hz_per_t`. A plugin that reports a percent divides by
     `gamma_magnitude(ctx)`.
2. `docs/checks.md`: from `scripts/check_docs.py` (the spec texts of
   sections 3.3 and 3.4).
3. `CHANGELOG.md`: an "Unreleased" entry. The summary says that the results
   of the checks do not change, except the two cases of section 1.
   - "Changed": pulseq-analysis `0.1.0rc5`. The series of `pns.safe.levels`
     are in Hz/T, and the threshold series is `pns_above_0` in place of
     `pns_above_1`. A JSON result of `0.1.0rc4` with this series still
     reads (the format is 1), but its PNS values are fractions and its
     threshold series is `pns_above_1`. The gradient analyses take no
     argument. `pns.safe` of a `Sequence` object with the limits from the
     profile uses the gamma of the profile, not `seq.system.gamma` (D5).
   - "Added": `bindings.gamma_magnitude(ctx)` and
     `bindings.pns_threshold_hz_per_t(ctx)`.
   - "Fixed": with a negative gamma, the gradient checks gave negative
     values and limits and failed. Now a negative gamma gives the same
     results as its magnitude (D6). `pns.safe` was already correct.
4. `TESTS.md`: section 4.3.

## 7. Results

To fill in during PR 2.
