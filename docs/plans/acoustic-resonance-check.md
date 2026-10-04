# Plan: the acoustic resonance check

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: done (2026-10-04). Phase 1 (D5) is #49, and phase 2 (the check
`acoustic.resonance-energy`) is #50. The user approved all the decisions of
section 5. Section 7 has the changes to this plan during the work.

## 1. Goal

A new check that compares the gradient spectrum of a sequence with the
acoustic resonances of the target. A gradient waveform with much energy at a
resonance frequency of the gradient coil makes the coil vibrate strongly.

The rule (D1, D2, D7): the check fails when more than 30 % of the energy of
the gradient spectrum is in the resonance bands of the target, all the bands
together. The 30 % is for the sum over all the bands, not for each band. The
fraction is of the total energy of the spectrum. It does not change when the spectrum is
normalized to its peak, because a scale of the spectrum does not change a
fraction.

Not in this plan: a limit in mT/m/sqrt(Hz), a limit from the target profile,
check options, and a change of the analysis `gradient.spectrum`.

## 2. Context (verified on 2026-10-04, `main` at `cc57362`)

### 2.1 The resonances of the target

1. `TargetProfile.acoustic_resonances` is a tuple of `(frequency, bandwidth)`
   pairs in Hz, or `None`. The value path is `acoustic.resonances`. The
   profile file gives it in `[acoustic]`, or the `.asc` reader gives it
   (`aflGCAcousticResonanceFrequency` or
   `asGPAParameters[0].sGCParameters.aflAcousticResonanceFrequency`, with the
   bandwidths).
2. The profile reader checks only that each pair has two numbers
   (`profile.py`, `_is_number`: an `int` or a `float` that is not a
   `bool`). It accepts an empty list, a frequency or a bandwidth that is 0
   or below 0, and `inf` or `nan` (TOML and JSON readers can give them).
3. `docs/usage.md` section 2.5 says that no check of version 1 uses
   `acoustic.resonances`.
4. The `.asc` file and pypulseq give no limit and no verdict. pypulseq
   `calculate_gradient_spectrum` only draws the resonances
   (`docs/plans/pulseq-checks.md`, section 3, table).

### 2.2 The spectrum (pulseq-analysis `v0.1.0rc4`)

1. The analysis `gradient.spectrum` has no parameters and no binding. Its
   `compute(seq)` is `grad_spectrum.gradient_spectrum_for(seq)`, which keeps
   one result for each sequence object and each set of arguments. Thus the
   check and a requested analysis result of one target share one
   calculation. `run_checks` reads a `.seq` file one time for each target,
   with the `Opts` of that target, so two targets have two sequence objects
   and two calculations (section 7.1).
2. It uses the defaults of pypulseq: `max_frequency_hz=2000.0`,
   `window_s=0.05`, `frequency_oversampling=3.0`. The frequency step is
   `1 / (window_s * frequency_oversampling)`, 6.67 Hz. There are 301
   frequencies, from 0 Hz to 2000 Hz.
3. `GradientSpectrum.rss` is the root-sum-of-squares of the three axes in
   each window, then the maximum over the windows, in Hz/m/sqrt(Hz). Each
   window has a constant detrend and a Hann window.
4. `reason == NO_GRADIENTS` when the sequence has no gradient event. A
   sequence with the rotation extension raises `NotImplementedError`.
5. The spectrum uses `GradientRasterTime` and `BlockDurationRaster`
   (`spec.rasters`).

### 2.3 Measurements (scratch script, not in the repository)

The bands of `tests/profiles/prisma.toml` are `[590, 100]` and
`[1140, 220]`. The energy fraction is `sum(rss^2)` over the frequencies in
the bands divided by `sum(rss^2)` over all frequencies.

| Sequence | Fraction in the bands |
|---|---|
| `spin_echo_sequence()` of `tests/synthetic.py` | 0.19 |
| `gre_sequence()` | 0.079 |
| 200 bipolar trapezoids at about 1140 Hz, axis x | 0.98 |
| The same train, rotated by 0.6 rad between x and y | 0.98 |
| 60 bipolar trapezoids at 300 Hz | 0.0006 |

The rotated train has the same `rss` as the train on x to 2e-16 of the peak.
In each window, the RSS of the three axes is the norm of the complex vector
of the spectrum, and a rotation does not change that norm. Thus the value of
the check does not change when the scan rotates the logical axes.

### 2.4 The checks of this package

1. A check is a `CheckSpec` and a `run(ctx)` in `src/pulseq_checks/checks/`,
   with an entry point in the group `pulseq_checks.checks` of
   `pyproject.toml`. `checks/pns.py` is the nearest model: one analysis, a
   value in percent, and findings.
2. `CheckSpec.inputs` gives "not evaluated" when the target does not give a
   value path. `CheckSpec.rasters` and `CheckSpec.analyses` give "not
   evaluated" for a missing raster or an analysis that is not available.
3. `scripts/check_docs.py` makes `docs/checks.md` from the specifications.
   `scripts/check` fails when `docs/checks.md` is not up to date.

## 3. Design

### 3.1 The rule

For one sequence and one target:

1. `s = ctx.analysis("gradient.spectrum")`. If `s.reason == NO_GRADIENTS`,
   the result is "pass" with the value 0 % and no finding.
2. `f = s.frequency_hz` and `e = s.rss ** 2`.
3. For each pair `(fc, bw)` of `acoustic_resonances`, the band is the closed
   interval `[fc - bw / 2, fc + bw / 2]`. `in_bands` is True at each
   frequency of `f` that is in one band or more. A frequency in two bands
   counts one time.
4. `total = e.sum()`. If `total == 0`, the result is "pass" with the value
   0 %.
5. The value is `100 * e[in_bands].sum() / total`, in percent: the share of
   the energy in all the bands together.
6. The limit is the constant `ACOUSTIC_BAND_ENERGY_LIMIT = 30.0` (percent).
   The state is "fail" when the value is above 30 %, and "pass" when it is
   at or below 30 % (D7). There is no limit for one band. Thus two bands
   with 20 % each give 40 % and a fail.
7. The gamma of the target is not necessary: a fraction of energy has no
   unit.

The check uses the default arguments of the spectrum (D9). Thus the spectrum
of the check and the spectrum of the analysis result in the matrix are the
same calculation, and a report that draws the analysis result draws the
spectrum that the check used. Each finding also gives the three arguments.

### 3.2 The specification

In `src/pulseq_checks/checks/acoustic.py`, the rule `RESONANCE_ENERGY`, with
the entry point `"acoustic.resonance-energy" =
"pulseq_checks.checks.acoustic:RESONANCE_ENERGY"` (D3):

| Field | Value |
|---|---|
| `id` | `acoustic.resonance-energy` |
| `version` | 1 |
| `title` | Gradient energy in the acoustic resonance bands |
| `quantity` | The percent of the energy of the gradient spectrum (the RSS of x, y and z, from 0 Hz to 2000 Hz, by the method of `calculate_gradient_spectrum` of pypulseq) that is in the acoustic resonance bands of the target, all the bands together. A frequency in two bands counts one time. The energy at a frequency is the square of the RSS spectrum. |
| `inputs` | `("acoustic.resonances",)` |
| `models` | `()` |
| `limit` | 30 % of the energy of the spectrum, for all the bands together. |
| `tolerance` | None. |
| `pass_condition` | The percent is at or below 30 %, with the "not evaluated" conditions of D4 and of the rasters. |
| `cost` | `"slow"` |
| `pypulseq` | `calculate_gradient_spectrum` of pypulseq (the method), through `grad_spectrum.gradient_spectrum_for` of pulseq-analysis |
| `url` | None |
| `rasters` | `("GradientRasterTime", "BlockDurationRaster")` |
| `analyses` | `("gradient.spectrum",)` |
| `findings` | Section 3.3. |
| `promise` | Section 3.4. |

The result has `value` (percent), `limit=30.0`, `unit="%"` and
`location=None`, because a spectrum has no block and no time. On a pass or a
fail, `reason` gives the number of bands, for example `2 resonance bands`.

### 3.3 The findings

A fail has one finding. A pass has none (D8). The finding is for all the
bands together, not for one band, because the limit is for all the bands
together. The result gives no share for one band. The code is
`ACOUSTIC_BAND_ENERGY`. The location is None. The data:

| Key | Value |
|---|---|
| `energy_percent` | The percent of the total energy in all the bands together (the value of the result). |
| `limit_percent` | 30.0. |
| `num_bands` | The number of resonance bands of the target. |
| `max_frequency_hz`, `window_s`, `frequency_oversampling` | The arguments of the spectrum. |

The message is the share and the limit, for example
`"42.1 % of the gradient energy is in the 2 resonance bands (limit 30 %)"`.

### 3.4 The promise

- `on_pass`: At most 30 % of the energy of the gradient spectrum of the
  file, from 0 Hz to 2000 Hz, is in the acoustic resonance bands of the
  target. The value does not change when the scan rotates the logical axes.
- `on_fail`: More than 30 % of that energy is in the resonance bands, all
  the bands together. A fail does not need one band above 30 %.
- `not_promised`: That the scanner accepts the sequence, that the scan is
  quiet, or that the coil is safe. 30 % is a rule of this package, not a
  limit of a vendor, and the scanner can have its own rules (for example the
  forbidden echo spacings of an EPI readout). The energy above 2000 Hz. A
  short, strong burst at a resonance: the spectrum is the maximum over
  windows of 50 ms, so the sum of its squares is not the energy of the
  whole sequence, and a short burst can have a small share. The waveform
  that the scanner plays, when its interpreter makes it in another way than
  the file (as for `pns.safe`).

### 3.5 The documentation

1. `docs/checks.md`: from `scripts/check_docs.py`.
2. `docs/usage.md` section 1: a row for `acoustic.resonance-energy`
   (`acoustic.resonances`, and the two rasters when the file does not
   declare them). Section 2.5: the check uses `acoustic.resonances`. The
   paragraph on findings: the findings of the new check.
3. `CHANGELOG.md`: an "Added" entry under "Unreleased".
4. `TESTS.md`: an entry for each new test.

## 4. Tests

`tests/test_check_acoustic.py`. The oracle of most tests is a hand-made
`GradientSpectrum` with known `rss`, given by a fake analysis
`gradient.spectrum` in the `RunContext`. Thus the expected percent is a
count of frequencies, not a second copy of the code.

1. A flat spectrum (each `rss` value 1, 301 frequencies) and one band that
   holds exactly `k` frequencies: the value is `100 * k / 301`.
2. The limit: a spectrum with exactly 30 % of its energy in the band gives
   "pass", and one with a bit more gives "fail" (D7).
3. The band edges are closed: a band whose edges are on two frequencies of
   the spectrum holds both of them.
4. All the bands together: two bands that do not overlap, each with 20 % of
   the energy, give 40 % and "fail". Two bands with 10 % each give 20 % and
   "pass".
5. Two overlapping bands: a frequency in both counts one time in the value.
6. The finding of a fail: one finding, with the data of section 3.3 and the
   message. A pass has no finding.
7. `NO_GRADIENTS`, and a spectrum with zero energy: "pass", 0 %.
8. A target without `acoustic.resonances`: "not evaluated" (the run
   function, from `inputs`).
9. A band above the spectrum (D4) and an empty list of resonances (D6).
10. The real spectrum: a train of bipolar trapezoids at about 1140 Hz with
   the bands of `prisma.toml` gives "fail" with a value above 90 %. A train
   at 300 Hz gives "pass" with a value below 1 %. The bounds come from
   section 2.3.
11. Rotation: the train on x and the same train rotated between x and y
    give the same value (relative tolerance 1e-9).
12. One target: the check and the requested analysis `gradient.spectrum`
    use one spectrum. Count the calls of `gradient_spectrum_for`
    (section 7.1).
13. The rotation extension: "error".
14. `test_cli.py` or `test_run.py`: the check runs with `prisma.toml` and
    gives a result with the unit `%`.

## 5. Decisions

Decided by the user (2026-10-04):

- **D1. The fail rule.** The fraction of the total energy of the spectrum
  that is in the bands (reading A). The energy at a frequency is the square
  of the RSS spectrum. The user did not choose a value normalized to the
  peak of the spectrum.
- **D2. The limit.** 30 %, a constant of the check
  (`ACOUSTIC_BAND_ENERGY_LIMIT`). It is not a value of the target profile
  and not a check option. Its source is the decision of the user.

Approved by the user (2026-10-04). D3 to D6 and D9 are as recommended. D7
and D8 have the correction of the user:

- **D3. The ID.** `acoustic.resonance-energy`. The name says what the check
  measures, and it is different from the value path `acoustic.resonances`.
- **D4. A band above the spectrum.** If a band has `high_hz` above
  `max_frequency_hz` (2000 Hz), the result is "not evaluated", with a reason
  that names the band and the range of the spectrum. The check cannot
  measure the energy in that band, so it must not give a pass. The other
  choice is to calculate the spectrum up to the highest band. Then the total
  energy, and thus the value, depends on the target, and the spectrum of the
  check is not the spectrum of the analysis result.
- **D5. A pair that is not valid.** A frequency or a bandwidth that is 0,
  below 0, or not finite is an error of the profile reader (`ProfileError`),
  not a result of the check. This is a change of `profile.py` and its tests
  (phase 1).
- **D6. An empty list of resonances.** `resonances = []` says that the
  target has no resonance band. The result is "pass" with the value 0 %.
- **D7. The limit is for all the bands together** (decided by the user,
  2026-10-04). The value is the share of the energy in all the bands
  together, and the state uses only that value. There is no limit for one
  band. The user said "more than 30 %", so 30 % exactly is a pass. There is
  no tolerance.
- **D8. One finding, only on a fail** (from D7, decided by the user,
  2026-10-04). The finding is for all the bands together. The result gives
  no share for one band, so that no reader takes the limit as a limit for
  each band. A pass has no finding, as for the other checks of this
  package.
- **D9. The default spectrum.** The check uses
  `ctx.analysis("gradient.spectrum")`, with the defaults of pypulseq. It
  does not choose other arguments. If a later version needs other
  arguments, each finding already gives them, and the analysis can get
  parameters (as the `thresholds` of `pns.safe.levels`).

## 6. How to execute this plan

1. Get the approval of the user for D3 to D6 and D9. Done (2026-10-04).
2. Phase 1, its own branch and PR (`fix/acoustic-resonance-values` or
   similar): D5 in `profile.py`, with tests and `TESTS.md` entries. Done
   (#49).
3. Phase 2, its own branch and PR (`feature/acoustic-resonance-check`):
   `checks/acoustic.py`, the entry point, the tests of section 4, the
   documentation of section 3.5. The specification is version 1 (the rule of
   the release candidates). Run `nix develop --command scripts/check`. Done
   (#50).
4. Before the merge of phase 2, move the lasting content of this plan into
   `docs/checks.md` and `docs/usage.md`, and record the results in section 7.
   Done (#50).

## 7. Results

### 7.1 Changes to this plan during the work

1. Section 2.2, fact 1, and test 12. The plan said that the check and the
   targets of a sequence share one spectrum. That is true for one sequence
   object only. `run_checks` reads a `.seq` file one time for each target,
   so each target has its own sequence object and its own calculation. The
   check and a requested analysis result of one target share one
   calculation. This is correct: when the file does not declare its
   rasters, each target gives them, and the spectrum can differ between
   targets. No change to `run.py`.
2. Section 3.2. On a pass with no gradient event, `reason` is
   `no gradient event`. With an empty list of resonances, it is
   `no resonance band`.
3. Section 4, test 9 (the real spectrum of `spin_echo_sequence()`) is not
   a test: it would repeat the formula of the check. The tests with a
   train at a known frequency cover the real analysis.
