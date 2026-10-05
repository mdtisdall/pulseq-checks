# Changelog

Each version of `pulseq-checks` has an entry here. The version numbers follow
[PEP 440](https://peps.python.org/pep-0440/).

## Unreleased

pulseq-analysis is `0.1.0rc5`. No value of pulseq-analysis uses a gamma
now: the gradient values are in Hz/m and Hz/m/s, and the PNS values are in
Hz/T. The checks convert them with the magnitude of the gamma of the target.
The results of the checks do not change, except in two cases: a target with
a negative gamma (see "Fixed"), and `pns.safe` of a `Sequence` object whose
`seq.system.gamma` is not the gamma of the profile (see "Changed"). The JSON
result format stays 1, and the version of each check and analysis stays 1.
The plan is `docs/plans/pulseq-analysis-rc5.md`.

### Added

- **`bindings.gamma_magnitude(ctx)`**, the magnitude of `gamma(ctx)`, in
  Hz/T. The checks convert the values of the analyses with it. Each limit
  and each value of a check is a magnitude, so a negative gamma is valid and
  the checks use its magnitude. `gamma(ctx)` stays signed.
- **`bindings.pns_threshold_hz_per_t(ctx)`**, the PNS stimulation limit of
  the target in Hz/T: `PNS_LIMIT * gamma_magnitude(ctx)`. The binding of
  `pns.safe.levels` gives it as the one threshold, and a check finds the
  intervals at or above the limit in `levels.above[pns_threshold_hz_per_t(ctx)]`.

### Changed

- **pulseq-analysis `0.1.0rc5`** in place of `0.1.0rc4`. The series of
  `pns.safe.levels` have the unit `"Hz/T"`: a PNS value is the fraction of
  the stimulation limit times the magnitude of the gamma of the target. To
  get a percent, use `100 * v / meta["threshold"]` of the threshold series,
  which is `100 * v / abs(gamma)`. The threshold series is `pns_above_0` in
  place of `pns_above_1`. A JSON result of `0.1.0rc4` with this series still
  reads, because the format is 1, but its PNS values are fractions and its
  threshold series is `pns_above_1`.
- **The bindings.** `gradient.limits` and `gradient.blocks` take no
  argument: they have no `gamma` parameter now. `pns.safe.levels` takes
  `thresholds_hz_per_t=(pns_threshold_hz_per_t(ctx),)` in place of
  `thresholds=(PNS_LIMIT,)`.
- **`pns.safe` of a `Sequence` object** with the limits from the profile uses
  the gamma of the profile, not `seq.system.gamma`, as the gradient checks
  do. The value changes only when the two gammas are different. With
  `limits_from_sequence=True`, it uses `seq.system.gamma`, as before.
- **`pns.safe`** decides its state in Hz/T: it fails when the peak is at or
  above `pns_threshold_hz_per_t(ctx)`, the rule of the intervals of its
  findings. Thus a fail always has a finding.

### Fixed

- **A negative gamma.** The gradient checks divided by the signed gamma, so
  a target with a negative gamma gave negative values and negative limits,
  and the gradient checks failed. Now the values and the limits use the
  magnitude of the gamma, and a negative gamma gives the results of its
  magnitude. `pns.safe` was already correct for a negative gamma.

## 0.1.0rc4 (2026-10-04)

The fourth release candidate. The new check `acoustic.resonance-energy`
compares the gradient spectrum of the sequence with the acoustic resonances
of the target: it fails when more than 30 % of the energy of the spectrum is
in the resonance bands, all the bands together. The new analysis
`gradient.spectrum` keeps that spectrum in the matrix and in the JSON result
(`--analysis gradient.spectrum`). pulseq-analysis is `0.1.0rc4`. A series of
an analysis has a coordinate with its own unit, so the JSON result of this
version and the JSON result of `0.1.0rc3` cannot read each other when they
have a series (see "Changed"). A resonance pair of a profile that is not
finite and above 0 is now an error. The tests of the six checks of
`0.1.0rc3` pass with no change. The plan is
`docs/plans/acoustic-resonance-check.md`.

The time budget before the tag (`scripts/budget.py`, 10^6 blocks, Apple M1
Max, with the read of the file, 3.57 s; the profile has the resonances of
`tests/profiles/prisma.toml`): the fast checks together take 4.27 s
(budget: 10 s), `acoustic.resonance-energy` takes 16.38 s, and all seven
checks take 36.88 s (the six checks of `0.1.0rc3` took 24.54 s). With
`analyses=["pns.safe.levels"]` they take 36.63 s, and the JSON result is
0.05 MB.

### Added

- **The analysis `gradient.spectrum`**, from pulseq-analysis `0.1.0rc4` in
  place of `0.1.0rc3`. `--analysis gradient.spectrum` (or
  `run_checks(..., analyses=["gradient.spectrum"])`) keeps the spectrum of
  the gradient waveform of the whole sequence in the matrix and in the JSON
  result: one `SAMPLES` series `gradient_spectrum`, with `coord_unit` `"Hz"`,
  the unit `"Hz/m/sqrt(Hz)"` (no gamma), the arrays `value` (the
  root-sum-of-squares of the axes), `x`, `y` and `z`, and the arguments of
  the calculation in `meta` (the defaults of pypulseq). It has no parameters,
  so it needs no binding and takes no value of the target. It uses the
  rasters `GradientRasterTime` and `BlockDurationRaster`, and it is "not
  evaluated" when neither the file nor the target gives one of them. scipy
  is now also a dependency of pulseq-analysis. The format stays 1, and no
  check changes.

- **The check `acoustic.resonance-energy`**
  (`docs/plans/acoustic-resonance-check.md`). It compares the gradient
  spectrum of the sequence (the analysis `gradient.spectrum`, with the
  defaults of pypulseq, 0 Hz to 2000 Hz) with the acoustic resonances of the
  target (`acoustic.resonances`). The value is the percent of the energy of
  the spectrum (the square of the RSS spectrum) in the bands
  `[f - bw/2, f + bw/2]`, all the bands together. It fails when the value is
  above 30 %, a constant of the check and not a limit of a vendor. A fail has
  one finding, `ACOUSTIC_BAND_ENERGY`, for all the bands. A band above
  2000 Hz gives "not evaluated", and an empty list of resonances gives a pass
  with 0 %. It is a slow check, and its specification is version 1.

### Changed

- **pulseq-analysis `0.1.0rc3`** in place of `0.1.0rc2`. A series object of
  the JSON result has the keys `name`, `kind`, `unit`, `coord_unit`,
  `coord_start`, `coord_step`, `coord_end`, `meta` and `arrays`: the new
  `coord_unit` (`"s"` for the series of `pns.safe.levels`), and
  `coord_start`, `coord_step` and `coord_end` in place of `t0_s`, `step_s`
  and `end_s`. The arrays of a `RUNS` series are `start` and `end` in place
  of `start_s` and `end_s`, and the array of a `POINTS` series is `coord` in
  place of `time_s`. Thus this version cannot read a JSON result of
  `0.1.0rc3` that has a series, and `0.1.0rc3` cannot read a JSON result of
  this version that has a series. The format stays 1, and the version of
  `pns.safe.levels` stays 1. The results of the checks do not change.

- **`acoustic.resonances`** must have a finite frequency and a finite
  bandwidth above 0 in each pair. A frequency or a bandwidth that is 0, below
  0, `inf` or `nan` is now a `ProfileError`, from the profile file and from
  the `.asc` file. Before, the reader accepted these values. An empty list
  stays valid. The profile format stays 1. This is phase 1 of
  `docs/plans/acoustic-resonance-check.md` (decision D5).

## 0.1.0rc3 (2026-10-04)

The third release candidate. The measurement modules are in their own
package, pulseq-analysis (`0.1.0rc2`), and a run can keep the result of an
analysis for each target, with its series, in the matrix and in the JSON
result: for example the SAFE PNS level over time and the intervals at or
above 100 % (`--analysis pns.safe.levels`). Each check also says what a pass
promises and what a fail means. The results of the checks do not change. The
JSON result of this version and the JSON result of `0.1.0rc2` cannot read
each other (see "Changed"), and the old import paths of the measurement
modules stop working. The plans are `docs/plans/pulseq-analysis.md` and
`docs/plans/pulseq-analysis-implementation.md`.

The time budget before the tag (`scripts/budget.py`, 10^6 blocks, Apple M1
Max, with the read of the file): the fast checks together take 4.28 s
(budget: 10 s), and all six checks take 24.54 s. With
`analyses=["pns.safe.levels"]` they take 24.41 s, and the JSON result is
0.05 MB (`docs/plans/pulseq-analysis.md`, section 9.2).

### Added

- **`CheckSpec.promise`**, a `CheckPromise` with three texts: what a pass of
  the check guarantees (`on_pass`), what a fail means (`on_fail`) and what the
  check does not promise (`not_promised`). Each check of this package gives
  one, and `docs/checks.md` shows it first for each check. It is the last
  field of `CheckSpec`, with the default `None`, so a plugin that gives the
  fields by position works as before. The rules of the checks do not change,
  and each specification stays version 1.
- **The analysis results**: a run can keep the result of an analysis of
  pulseq-analysis for each target, with its series. `run_checks(...,
  analyses=[...])` takes the analysis IDs (made unique and sorted; an ID that is
  not installed is a `RunError` before the file is read). The run calculates
  each analysis for each target, also with `select=[]`, and `fast_only` does not
  remove it. `ResultMatrix.analyses` is a tuple of the new `AnalysisResult`
  (`id`, `version`, `target`, `state`, `reason`, `series`), the new
  `AnalysisState` is `done`, `not evaluated` or `error`,
  `ResultMatrix.analysis(target, id)` gives one result, and
  `ResultMatrix.without_series()` gives a matrix with no series, for a small
  JSON. `AnalysisResult` and `AnalysisState` are exported
  from `pulseq_checks`. An analysis result is not a check result: it does not
  change the exit status. The matrix keeps the series only, not the full value
  (for example not `PnsLevels`): `docs/usage.md` shows the call that gives it.
- **`--analysis ID`** of `pulseq-check` (it can be repeated, also with
  `--config`). It changes the JSON result. The summary lists an
  analysis result that is not "done", with its reason, in "not evaluated and
  errors".
- **`CheckSpec.analyses`**: the IDs of the analyses that a check uses. It is the
  last field of `CheckSpec`, after `promise`, so that a plugin that gives the
  earlier fields by position keeps working. The run function gives "not
  evaluated" before `run` when one of them is not available for the target (the
  binding needs an input or a model that the target does not give, or the
  analysis uses a raster that neither the file nor the target gives), and
  "error" when it is not installed.
- **`RunContext.analysis(id)`**: the value of `compute` of an analysis for the
  target, calculated one time for each target (the value, or the exception, is
  kept). It raises `LookupError` when the analysis is not installed or is not
  available for the target. The arguments of `compute` come from
  `pulseq_checks.bindings`.
- **`scripts/budget.py`** has the mode `@analysis` (all the checks, with
  `analyses=["pns.safe.levels"]`), and each run of the checks also gives the
  size of the JSON result and the time of `to_json`.

### Changed

- **The JSON key `"analyses"`** comes after `"results"`. `to_json` always writes
  it (an empty list when the caller asked for no analysis), and `from_json`
  needs it. Thus this version cannot read a JSON result of `0.1.0rc2`, and
  `0.1.0rc2` cannot read a JSON result of this version. The format stays 1.
- **The checks of this package use `ctx.analysis`** in place of `ctx.measure`
  (`seq.index`, `gradient.limits`, `gradient.blocks` and `pns.safe.levels`).
  Each check lists its analyses in `CheckSpec.analyses`, and `docs/checks.md`
  has an "Analyses" line for each check. The results of the checks, their
  specifications and their versions do not change.
- **`ctx.measure`** is for the measurements of a plugin. The names `"index"`,
  `"gradient_limits"`, `"gradient_blocks"` and `"pns_levels"` are no longer
  used by this package: a plugin that used them to share a value with a check
  uses `ctx.analysis` with the analysis ID.
- **The measurement modules moved to the package pulseq-analysis**
  (`0.1.0rc2`), a dependency of pulseq-checks. `pulseq_checks` does not
  re-export them, so the old import paths stop working. The new paths are:
  `pulseq_checks.asc`, `extensions`, `grad_limits`, `pns`, `pns_levels`,
  `sampling`, `seq_index` and `seq_utils` become the modules of the same name
  in `pulseq_analysis`. The results of the checks do not change.
- **`HardwareLimits`** is in `pulseq_checks.profile`. It stays a public name:
  `pulseq_checks.HardwareLimits` works as before.
- **The entry point of the SAFE model** is `pulseq_checks.safe_model:SAFE_MODEL`.
  `SAFE_MODEL` and `hw_from_dict` moved from `pns_levels` to the new module
  `pulseq_checks.safe_model`. The name of the model, `pns.safe`, does not
  change.
- **`PnsLevels.above_limit`** is now `PnsLevels.above[PNS_LIMIT]`
  (`above` is a dict from each threshold to its intervals), and
  `gradient_limits` has no `limits` argument and `GradientLimits` has no
  `limits` field. These are changes of pulseq-analysis, and the checks of this
  package use them.

## 0.1.0rc2 (2026-09-30)

The second release candidate. Each of the six checks gives findings (the
plans `docs/plans/check-findings.md` and
`docs/plans/gradient-pns-findings.md`). The gradient and PNS checks use the
rasters and the gamma of the file and of the target, not the defaults of
pypulseq. The JSON result of this version and the JSON result of `0.1.0rc1`
cannot read each other (see "Changed"). pulseq-reports pins this tag, or a
later one, for its step 3: `0.1.0rc1` does not have the fixes that
pulseq-reports has in its copies of the moved modules.

The time budget before the tag (`scripts/budget.py`, 10^6 blocks, Apple M1
Max, with the read of the file): the fast checks together take 4.28 s
(budget: 10 s), and all six checks take 24.65 s. On a file that fails the
three gradient checks in each TR, the fast checks take 7.63 s
(`docs/plans/gradient-pns-findings.md`, section 7.2).

### Added

- **Findings**: a check can report each problem that it found, not only the
  worst value. `Finding` (`code`, `message`, `location`, `data`) is exported
  from `pulseq_checks`. `Result.findings` is a tuple of `Finding`, and
  `Result.findings_omitted` is the number of findings that were removed. A
  finding does not change the state of its result.
- **`CheckSpec.findings`**: the text in which a check documents its findings
  (what one finding is, its codes, its location, the keys of `data` and the
  order). It is the last field of `CheckSpec`, so that a plugin that gives the
  earlier fields by position keeps working.
- **`CheckSpec.rasters`**: the raster names that the measurement of a check uses
  (`GradientRasterTime`, `RadiofrequencyRasterTime`, `AdcRasterTime`,
  `BlockDurationRaster`). The default is `()`. It is the last field of
  `CheckSpec`, after `findings`, so that a plugin that gives the earlier fields
  by position keeps working. The run function gives "not evaluated" before
  `run` when the file does not declare a listed raster and the target does not
  give it. `docs/checks.md` has a "Rasters" line for each check.
- **`RunContext.raster_sources`**: a dict from each raster name to where its
  value comes from: `"file"`, `"target"`, `"sequence object"` or `"pypulseq
  default"`. A `RunContext` that is made by hand has `"sequence object"` for all
  four rasters, so that no rule of a plugin is "not evaluated" for it.
- **`ResultMatrix.with_max_findings(n)`**: a new matrix in which each result
  keeps at most `n` findings, and `findings_omitted` has the number of the
  others.
- **`--max-findings N` and `--show-findings`** of `pulseq-check`. The command
  writes all findings to the JSON result, unless `--max-findings` limits them.
  `--show-findings` lists the kept findings in the summary.
- **The findings part of the summary**: when a result has findings, the summary
  has one count line for each of them. The part comes after "not evaluated and
  errors" and before the unused profile sections.
- **`timing.pypulseq` gives its findings**: one finding for each error of
  `check_timing`, in the play order of the blocks. The code is the error type.
  The location is the block and its start time. `data` has the fields of the
  error record. The message is the text of the error report of pypulseq. The
  specification version stays 1, because the verdict does not change. On 10^6
  blocks with 4 x 10^5 errors, the check takes 17.9 s instead of 15.3 s. The
  JSON result with all findings is about 200 MB (0.5 MB with `--max-findings
  1000`).
- **`timing.rasters` gives its findings**: one finding for each of the four
  rasters that has a problem, in the order GradientRasterTime,
  RadiofrequencyRasterTime, AdcRasterTime, BlockDurationRaster. The codes are
  `RASTER_NOT_DECLARED` (the file does not declare the raster),
  `RASTER_INVALID` (the file declares a value that is not one positive finite
  number) and `RASTER_MISMATCH` (the raster of the file differs from the
  raster of the target by more than the tolerance). `data` has the name of the
  raster and the values in seconds. A result with the state "error" lists every
  raster problem, also the mismatches of the other rasters. The location is
  none. The specification version stays 1, because the verdict does not
  change.
- **The gradient checks give their findings**: `gradient.amplitude.axis`,
  `gradient.slew.axis` and `gradient.amplitude.any-orientation` give one
  finding for each block (and axis) that is above the limit, in the play order
  of the blocks, then in the order of the axes x, y, z. The codes are
  `AMPLITUDE_ABOVE_LIMIT`, `SLEW_ABOVE_LIMIT`, `JUNCTION_SLEW_ABOVE_LIMIT` (the
  step at the start of the block, before the segment of the same block and
  axis) and `VECTOR_AMPLITUDE_ABOVE_LIMIT`. The location is the block and the
  time of the value, and `data` has the axis, the value and the limit. The
  checks calculate the findings only for a fail, with
  `grad_limits.block_gradient_values(seq, gamma=...)`, a new public function
  that gives the gradient values of each block. The value, the limit, the
  location and the state of each result do not change. The specification
  version of each check stays 1, because the verdict does not change.
- **`pns.safe` gives its findings**: one finding for each interval of
  consecutive samples where the SAFE total is at or above 100 %, in time order.
  The code is `PNS_ABOVE_LIMIT`. The location is the block of the first sample
  of the interval and its time, and `data` has `start_s`, `end_s`,
  `peak_percent`, `peak_time_s` (all in seconds, or in percent of the
  stimulation limit) and `num_samples`. `pns_levels.PnsLevels.above_limit` (a
  tuple of the new `pns_levels.PnsInterval`) is new and public. `pns_levels`
  finds the intervals in its chunk loop, with no second pass over the samples.
  The value, the limit, the location and the state of each result do not
  change. The specification version stays 1, because the verdict does not
  change.

### Changed

- **The JSON result** has in each result the keys `findings` and
  `findings_omitted`. The format stays 1 in the release candidates. A reader
  of `0.1.0rc1` refuses a result of this version (the unknown key
  `findings`), and `from_json` of this version refuses a result of
  `0.1.0rc1` (the missing key `findings`).
- **The run function gives "error"** for a result whose `findings` is not a
  tuple of `Finding`, or whose `findings_omitted` is not an `int` of 0 or more.
- **The version of a specification** changes from the first final release
  (0.1.0) on. In the release candidates, each specification is version 1: a
  change of a rule, as for `gradient.slew.axis` below, is in this changelog
  only.
- A profile that gives both `opts.max_slew` and `opts.rise_time` (from the
  profile file or from the `.asc` file) is an error. `pp.Opts` replaced
  `max_slew` with `max_grad / rise_time` without a message.

### Fixed

- **A raster that the file does not declare**: `gradient.amplitude.axis`,
  `gradient.slew.axis`, `gradient.amplitude.any-orientation` and `pns.safe` use
  `GradientRasterTime` and `BlockDurationRaster` (the sample times of an
  arbitrary gradient, the block start times and, for `pns.safe`, the time step
  of the model). When the file does not declare one of them (a file older than
  1.4.0, or a damaged file) and the target gives it in `[rasters]`, the checks
  use the raster of the target. When the target does not give it either, the
  checks are "not evaluated", and the reason names the raster. Before, they used
  the default of pypulseq (10 µs) without a message: a file built with 4 µs and
  without the `GradientRasterTime` line passed `gradient.slew.axis` with 18.79
  T/m/s, 2.5 times less than its real 46.97 T/m/s. The four specifications stay
  version 1. The checks of a file that declares its rasters do not change.
- **Gradient checks**: `gradient.amplitude.axis`, `gradient.slew.axis` and
  `gradient.amplitude.any-orientation` convert the measured values with the
  gamma of the target, the same gamma as the limits, not with a fixed
  42.576 MHz/T. Before, a profile with another gamma compared the values and
  the limits in different units (a 21 mT/m gradient passed a 20 mT/m limit
  with `gamma = 40e6`). `gradient_limits` has a new keyword argument `gamma`
  (default 42.576 MHz/T). `limits_from_sequence` converts the limits of
  `seq.system` with its own gamma.
- **`gradient.slew.axis`**: a profile that gives `opts.max_grad` and
  `opts.rise_time` and no `opts.max_slew` gives the slew limit `max_grad /
  rise_time`, the value that `pp.Opts` calculates. Before, the check was "not
  evaluated" and `hardware_limits` was None, although `docs/usage.md` said that
  `rise_time` gives the slew limit. `TargetProfile.has_value("opts.max_slew")`
  is true for such a profile.
  The step at a block junction is divided by the gradient raster of the file
  (`seq.grad_raster_time`), not by the raster of the target or the pypulseq
  default. Before, a file with a 4 µs raster read with a 10 µs target had
  junction steps 2.5 times too small. A difference between the rasters of the
  file and of the target is the subject of `timing.rasters`.

### Documentation

- **The measurement modules**: `docs/usage.md` has a new section 8 with the
  interface of `seq_index`, `grad_limits`, `pns`, `pns_levels`, `sampling`,
  `seq_utils`, `asc` and `extensions`: the fields and units of
  `SequenceIndex`, `GradientLimits`, `AxisResult`, `BlockGradientValues`,
  `PnsLevels` and `PnsInterval`, and the rules that all the measurements
  follow. A name that the section does not give can change in any release.
  "Limits of version 1" is now section 9. The docstrings of these modules no
  longer point to design documents and code of pulseq-reports, which are not
  in this repository.

## 0.1.0rc1 (2026-09-30)

The first release candidate: version 1 of `docs/plans/pulseq-checks.md`,
made by the plan `docs/plans/pulseq-checks-v1.md`.

### Added

- **Target profiles** (`read_profile`, `TargetProfile`): a TOML or JSON file
  with the `pp.Opts` values of a scanner (`[opts]`), its rasters (`[rasters]`),
  the parameters of a model (`[models.pns.safe]`) and the acoustic resonances
  (`[acoustic]`). There are no default limits: a value that no source gives
  is missing, and a check that needs it is "not evaluated". An unknown key is
  an error; an unknown section is listed as unused. See `docs/usage.md`.
- **The Siemens `.asc` profile reader** (`siemens-asc`): a profile can name an
  `.asc` file for the SAFE PNS parameters, the acoustic resonances and, with
  `asc_gradient_mode`, the GPA limits of an operation mode. A value that the
  profile and the `.asc` file both give is an error.
- **Six checks**, each with a specification in `docs/checks.md`:
  - `timing.rasters` (fast): the rasters that the file declares equal the
    rasters of the target.
  - `timing.pypulseq` (slow): `Sequence.check_timing` with the `Opts` of the
    target.
  - `gradient.amplitude.axis`, `gradient.slew.axis` (fast): the peak amplitude
    and slew of each logical axis against the limits of the target.
  - `gradient.amplitude.any-orientation` (fast): the peak of |G|, the worst
    case under any rotation of the logical axes.
  - `pns.safe` (slow): the peak of the SAFE PNS model with the parameters of
    the target.
- **The results**: four states (pass, fail, not evaluated, error), the value,
  the limit, the location (block and time), a short detail, the model and the
  link to the specification; a result matrix for one sequence and several
  targets, with its exit status and its JSON form.
- **`run_checks`**: one function for the command and for other tools. It reads
  the `.seq` file one time for each target, with the `Opts` of that target.
- **The command `pulseq-check`**: exit status 0 (no fail), 2 (a check failed)
  or 1 (an error, or a required check not evaluated); `--check` makes a check
  required; `--fast` runs the fast checks; `--json` writes the results.
- **The check configuration** (`read_check_config`): the targets, the selected
  and required checks and `fast_only` in one TOML or JSON file.
- **Plugins**: the entry-point groups `pulseq_checks.checks`,
  `pulseq_checks.models` and `pulseq_checks.profile_readers`.
- **The measurement modules** of pulseq-reports (`grad_limits`, `pns`,
  `pns_levels`, `asc`, `extensions`, `sampling`, `seq_index`, `seq_utils`),
  moved here; pulseq-reports will use them from this package. `pns_levels`
  takes a SAFE hardware struct (`hardware=`), and `gradient_limits` refuses a
  sequence with the rotation extension.
- **The time budget**: the fast checks together take 4.2 s for 10^6 blocks on
  an Apple M1 Max, with the read of the file (budget: 10 s).
  `scripts/budget.py` measures it; `tests/test_budget.py` finds a large
  slowdown in CI.
- **The comparison** with the checks of the pulseq-reports cards
  (`docs/comparison.md`): 180 pairs, all equal.

### Limits of this version

- The rasters of the file must equal the rasters of the target (see
  `TODO.md`).
- A sequence with the Pulseq rotation extension gives "error" for the
  gradient and PNS checks.
- The package needs pypulseq 1.5.0.post1 with four commits from a fork, which
  uv installs from `[tool.uv.sources]` and pip does not (see `TODO.md`).
