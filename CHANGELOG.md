# Changelog

Each version of `pulseq-checks` has an entry here. The version numbers follow
[PEP 440](https://peps.python.org/pep-0440/).

## Unreleased

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
- **`ResultMatrix.with_max_findings(n)`**: a new matrix in which each result
  keeps at most `n` findings, and `findings_omitted` has the number of the
  others.
- **`--max-findings N` and `--show-findings`** of `pulseq-check`. The command
  writes all findings to the JSON result, unless `--max-findings` limits them.
  `--show-findings` lists the kept findings in the summary.
- **The findings part of the summary**: when a result has findings, the summary
  has one count line for each of them. The part comes after "not evaluated and
  errors" and before the unused profile sections.

### Changed

- **The JSON result is format 2.** Each result has the keys `findings` and
  `findings_omitted`. A reader of `0.1.0rc1` refuses format 2. `from_json` of
  this version still reads format 1: a result of format 1 has no findings.
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

- **`gradient.slew.axis`**: a profile that gives `opts.max_grad` and
  `opts.rise_time` and no `opts.max_slew` gives the slew limit `max_grad /
  rise_time`, the value that `pp.Opts` calculates. Before, the check was "not
  evaluated" and `hardware_limits` was None, although `docs/usage.md` said that
  `rise_time` gives the slew limit. `TargetProfile.has_value("opts.max_slew")`
  is true for such a profile.

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
