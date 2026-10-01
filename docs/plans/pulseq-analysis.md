# Plan: pulseq-analysis, the analyses of a sequence in their own package

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: approved, not started. Written on 2026-10-01. The user approved the
answer of each decision of section 6 on the same day.

## 1. Goal

`pns.safe` calculates the SAFE PNS of the whole sequence for each target.
The run function discards that calculation after the check. A next reader
(for example pulseq-reports, which draws the PNS of each target) must run the
SAFE model again, and a reader of the JSON result cannot get the PNS at all.

This plan:

1. Moves the measurement modules of this package into a new package,
   **pulseq-analysis**. An *analysis* takes a sequence and explicit
   physical parameters, and gives a derived value: a time series (possibly
   with more than one variable), or a summary. An analysis does not change
   the sequence. It has no target profile, no limit, no pass or fail and no
   finding.
2. Adds `Series`, one general form of a derived time series that can go into
   JSON, and a `Analysis` protocol with a specification, in
   pulseq-analysis.
3. Makes the SAFE PNS analysis give two series: the SAFE total (an
   envelope) and the samples at or above a threshold (runs).
4. Makes pulseq-checks bind the target profile to the parameters of each
   analysis, keep the analysis results that a caller asks for in the
   `ResultMatrix`, and write them to the JSON result.
5. Makes `pns.safe` a judgment over the output of the PNS analysis.

pulseq-reports then gets the PNS of each target from the matrix (live, or
from the JSON result), and imports the measurement modules from
pulseq-analysis instead of its own copies.

Not in this plan: the work in pulseq-reports (its own plan, section 8),
series of the gradient analyses, plugin bindings (section 6, T9), and
the move of other measurement modules of pulseq-reports (section 8).

## 2. Context (verified on 2026-10-01, `main` at `e4e8257`)

1. **The run function discards the measurements.** `RunContext.measure(name,
   fn)` (`rules.py`) calculates a measurement one time for each target and
   keeps it in `RunContext._measurements` for the other rules of that
   target. The names are "index", "gradient_limits", "gradient_blocks" and
   "pns_levels". `run_checks` makes one `RunContext` for each target and
   discards it after the rules of that target.
2. **The kept PNS does not help a later caller.** With a `.seq` path,
   `run_checks` reads one `Sequence` object for each target and discards it.
   `pns.pns_levels_for` keeps its result in a `WeakKeyDictionary` keyed by
   the sequence object, so the kept result goes away with the object.
3. **The JSON result has no place for an array.** `Finding.data` holds only
   JSON scalars, and `Result` has no array field.
4. **The measurement modules do not import the check layer.** `seq_index`,
   `sampling`, `seq_utils`, `extensions`, `grad_limits`, `pns_levels`, `pns`
   and `asc` import only each other, numpy, pypulseq and the standard
   library. Two parts are of the check layer: `SAFE_MODEL` and
   `hw_from_dict` in `pns_levels.py` (the model `pns.safe` of the target
   profile, entry point `pulseq_checks.pns_levels:SAFE_MODEL`), and
   `HardwareLimits` in `grad_limits.py` (imported by `profile.py` and
   `checks/gradient.py`, and exported by `pulseq_checks`).
5. **The private fork function has one importer.** `pns_levels.py` is the
   only module that imports `_safe_gwf_to_pns_chunk` of the pinned pypulseq
   fork.
6. **pulseq-reports has copies.** `src/pulseq_reports/` of pulseq-reports has
   its own `asc`, `extensions`, `grad_limits`, `pns`, `pns_levels`,
   `sampling`, `seq_index` and `seq_utils`. Its plan
   (`docs/plans/pulseq-checks.md` of that repository, section 6 and step 1
   of section 7) replaces them with imports from `pulseq_checks` after a
   tag that documents the measurement API. It also has measurement modules
   that pulseq-checks does not have: `grad_spectrum`, `rf_exposure`,
   `rf_sim`, `profile_metrics` and `waveforms`.
7. **The size of the PNS.** `pns_levels` does not keep the samples. At the
   10 µs raster, one hour is 3.6 × 10⁸ samples (about 1.4 GB as float32).
   It keeps an envelope: the float32 minimum and maximum of the total in
   bins of `bin_samples` samples (615 at 10 µs, about 6 ms), at most
   `MAX_BINS` (2 × 10⁶) bins, 16 MB. The float32 cast is outward: each bin
   holds every total of its samples. It also keeps `above_limit`: each run
   of samples with a float64 total at or above `PNS_LIMIT` (1.0), with its
   first and last sample, its peak and the first sample with the peak.
8. **pulseq-reports already encodes arrays.** `diagram_data.encode_tables`
   of pulseq-reports writes each array as `{"dtype", "length", "data"}`:
   the little-endian bytes, gzipped (level 6, `mtime=0`, OS byte 255) and
   base64-encoded.
9. **The tests of the measurement modules.** `tests/test_seq_index.py`,
   `test_sampling.py`, `test_seq_utils.py`, `test_extensions.py`,
   `test_grad_limits.py`, `test_pns.py` and `test_pns_levels.py` (3069
   lines), with `tests/oracles/` and `tests/synthetic.py`. `TESTS.md`
   sections 2.1 to 2.7 describe them.

## 3. The options that this plan does not use

### 3.1 Where the PNS time series goes

| Option | Why not |
|---|---|
| A. Return `RunContext._measurements` of each target | The objects are of any type, the names are internal and a plugin can use the same name, and they cannot go into JSON. |
| B. Give the caller the `Sequence` object of each target, so that `pns_levels_for` finds its kept result | It depends on the cache of the package, and it cannot go into JSON. |
| C. A `Series` field of `Result`, given by the check | The series is a fact of the sequence and the hardware, not of the check. No series when the check does not run (`fast_only` removes `pns.safe`, `select` does not name it) or gives "error". Two checks that use one measurement write it two times. |
| D. An analysis step that always runs before the checks | It runs SAFE for each target in a run that needs no PNS (for example a CI run of `timing.*` only). |

This plan uses an analysis that runs on demand: a check declares the
analyses that it uses, a caller can ask for more, and the run function
calculates each one time for each target, as `RunContext.measure` does now.

### 3.2 Where the analyses go

| Option | Why not |
|---|---|
| Keep them in pulseq-checks | A report tool depends on a check framework only to get waveforms. A user who wants the PNS of a file in a notebook gets profiles and exit statuses that are not necessary. |
| One repository with two distributions (a uv workspace) | Each repository of this user has one package, one `scripts/check`, one `CLAUDE.md` and the `ship` skill. Use it only if three repositories are too much work (decision T2). |

### 3.3 The form of the "above the limit" series

| Form | Why not, or why |
|---|---|
| One boolean for each sample | The same size problem as the samples: 360 MB for each hour as bytes, 45 MB as bits. |
| One boolean for each bin of the envelope | It is `level_max >= threshold`, so it adds nothing. Its edges are correct to one bin (about 6 ms), not to one sample. The float32 maximum rounds up, so a bin with a float64 total in [1 − 6 × 10⁻⁸, 1) shows as 1.0, but `pns.safe` passes it (`peak < 1`). |
| Runs at the sample resolution (chosen) | Exact and small: one pair for each run. It is `above_limit` with a general form. Each run can also give its peak, so `pns.safe` gives its findings with the float64 peak, as now. |

## 4. Design

### 4.1 The two packages

**pulseq-analysis** (import name `pulseq_analysis`):

| Module | From | Change |
|---|---|---|
| `seq_index`, `sampling`, `seq_utils`, `extensions`, `asc` | pulseq-checks | None (phase 1) |
| `grad_limits` | pulseq-checks | Phase 3: no `limits` argument and no `GradientLimits.limits` field. `HardwareLimits` stays in pulseq-checks (decision T4). |
| `pns_levels` | pulseq-checks | Phase 1: without `SAFE_MODEL` and `hw_from_dict`. Phase 3: `thresholds` (section 4.4). |
| `pns` | pulseq-checks | None (phase 1) |
| `series` | new | `Series`, `SeriesKind`, `encode_array`, `decode_array` (section 4.2) |
| `analyses` | new | `AnalysisSpec`, `Analysis`, the entry-point group and the registry (section 4.3) |

**pulseq-checks** keeps the target profile, the configuration, the registry
of checks, models and profile readers, `run_checks`, `ResultMatrix`, the
command and the check rules. It gets:

- `safe_model.py`: `SAFE_MODEL`, `SAFE_FIELDS` (as needed by the model) and
  `hw_from_dict`, from `pns_levels.py`. The entry point of the model
  `pns.safe` changes to `pulseq_checks.safe_model:SAFE_MODEL`.
- `HardwareLimits` in `profile.py` (phase 4), or where `profile.py` and
  `checks/gradient.py` can import it.
- `bindings.py`: the binding of the target profile to the parameters of each
  analysis (section 4.5).

### 4.2 `Series` (pulseq-analysis, `series.py`)

```python
class SeriesKind(Enum):
    SAMPLES = "samples"  # value[k] at t0_s + k * step_s
    ENVELOPE = "envelope"  # min[i] and max[i] of the bin [t0_s + i*step_s, t0_s + (i+1)*step_s);
    # the last bin stops at end_s
    POINTS = "points"  # value[k] at time_s[k] (not regular, for example one for each block)
    RUNS = "runs"  # a boolean that is true from start_s[k] to end_s[k], else false


@dataclass(frozen=True, eq=False)
class Series:
    name: str  # stable, as Finding.code: for example "pns_total"
    kind: SeriesKind
    unit: str  # for example "1" (a fraction), "mT/m", "s"
    arrays: Mapping[str, np.ndarray]
    t0_s: float = 0.0  # SAMPLES and ENVELOPE
    step_s: float | None = None  # SAMPLES and ENVELOPE
    end_s: float | None = None  # ENVELOPE
    meta: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)
```

- The arrays of each kind:

  | Kind | Necessary arrays | Other arrays |
  |---|---|---|
  | `SAMPLES` | `value` | More variables, each with the length of `value` |
  | `ENVELOPE` | `min`, `max` | None |
  | `POINTS` | `time_s`, `value` | More variables, each with the length of `time_s` |
  | `RUNS` | `start_s`, `end_s` | Values for each run, each with the length of `start_s` |

  A series with more than one variable (for example the x, y and z of a
  gradient) is one series with more arrays, or one series for each
  variable. The specification of the analysis says which.
- `__post_init__` raises `TypeError` or `ValueError` when: `name` is not a
  string that is not empty; an array that the kind needs is missing; an
  array is not one-dimensional, or not of a numeric or bool dtype; two
  arrays of one series do not have the same length; `step_s` is missing or
  not above 0 for `SAMPLES` and `ENVELOPE`; `end_s` is missing for
  `ENVELOPE`; or `meta` is not of JSON scalars (the rules of
  `Finding.data`). It makes each array read-only.
- `__eq__`: the same fields, and each array equal by
  `np.array_equal(a, b, equal_nan=True)` with the same dtype. Without it,
  `Series == Series` raises, because `==` of two numpy arrays gives an
  array. A `Series` is not hashable.
- `encode_array(a) -> dict` and `decode_array(d) -> np.ndarray`: the form of
  `encode_tables` of pulseq-reports (section 2, fact 8), with `"dtype"` the
  numpy dtype name. `to_obj` and `from_obj` of `Series` use them. The
  encoding is deterministic: one array always gives the same text.
- A float that is not finite in an array needs no special text: it is in
  the bytes. A float that is not finite in `meta` or in a field is written
  as in `results.py` (`"inf"`, `"-inf"`, `"nan"`).

### 4.3 `Analysis` (pulseq-analysis, `analyses.py`)

```python
@dataclass(frozen=True)
class AnalysisSpec:
    id: str  # for example "pns.safe.levels"
    version: int
    title: str
    description: str  # what the value is: the contract
    params: tuple[str, ...]  # the names of the keyword arguments of compute
    rasters: tuple[str, ...]  # the rasters of the sequence that it uses
    cost: str = "slow"  # "fast" or "slow"
    series: str | None = None  # what to_series gives: names, kinds, units, times


class Analysis(Protocol):
    spec: AnalysisSpec

    def compute(self, seq: pp.Sequence, **params: Any) -> Any: ...
    def to_series(self, value: Any) -> tuple[Series, ...]: ...
```

- `compute` gives the full Python value (for example `PnsLevels`).
  `to_series` gives the part that can go into JSON. An analysis with
  nothing for JSON gives `()`.
- The entry-point group `pulseq_analysis.analyses`, and
  `analyses.registry() -> dict[str, Analysis]`, with the rules of
  `registry.check_rules` of pulseq-checks: two analyses with one ID are
  an error that names both packages.
- The analyses of the package:

  | ID | `compute` | `params` | `to_series` |
  |---|---|---|---|
  | `seq.index` | `sequence_index` | none | `()` |
  | `gradient.limits` | `gradient_limits` | `gamma` | `()` |
  | `gradient.blocks` | `block_gradient_values` | `gamma` | `()` (later: `POINTS`, section 8) |
  | `pns.safe.levels` | `pns_levels_for` | `hardware`, `thresholds` | section 4.4 |

### 4.4 The SAFE PNS analysis

`pns_levels(seq, *, gradient_asc=None, hardware=None, thresholds=(1.0,))`
and `pns_levels_for` with the same argument:

- `PnsLevels.above` replaces `PnsLevels.above_limit`: a dict from each
  threshold to a tuple of `PnsInterval`, the runs of consecutive samples
  whose float64 total is at or above that threshold. They are found in the
  same pass as now: one pass for all the thresholds. The kept result of
  `pns_levels_for` is keyed by the hardware and the thresholds.
- `thresholds` must be a tuple of finite floats above 0, with no two equal,
  else `ValueError`. The default `(1.0,)` is the stimulation threshold of
  the SAFE model: a total of 1 is 100 %.
- The tests of `above_limit` stay, for `above[1.0]`. A new test: two
  thresholds in one call give the same runs as two calls with one threshold
  each.

`to_series` of `pns.safe.levels` gives, for a sequence with a gradient
event:

| Name | Kind | Unit | Arrays | `meta` |
|---|---|---|---|---|
| `pns_total` | `ENVELOPE` | `"1"` (1 is the stimulation threshold) | `min`, `max` (float32, `level_min` and `level_max`) | `hardware`, `asc_file`, `dt_s`, `bin_samples`, `num_samples`, `peak`, `peak_time_s`, `axis_peaks_x`, `axis_peaks_y`, `axis_peaks_z` |
| `pns_above_<t>` (one for each threshold, `<t>` is the threshold with `:g`, for example `pns_above_1`) | `RUNS` | `"1"` | `start_s`, `end_s`, `num_samples`, `peak`, `peak_time_s` (float64, int64) | `threshold` |

`t0_s` is 0, `step_s` is `bin_samples * dt_s` and `end_s` is
`num_samples * dt_s`. Sample `k` is at `(k + 0.5) * dt_s`; `start_s` and
`end_s` of a run are the times of its first and last sample. For a sequence
without a gradient event (`NO_GRADIENTS`), `to_series` gives `()`.

### 4.5 The binding in pulseq-checks (`bindings.py`, `rules.py`, `run.py`)

- `CheckSpec.analyses: tuple[str, ...] = ()`, the last field: the IDs
  of the analyses that the check uses. `scripts/check_docs.py` adds the
  row "Analyses" to the table of each check.
- A *binding* for each analysis that needs values of the target profile:
  its `inputs` and `models` (the paths of `CheckSpec`), and a function from
  the `RunContext` to the keyword arguments of `compute`. The bindings of
  this plan:

  | Analysis | `inputs` | `models` | Arguments |
  |---|---|---|---|
  | `seq.index` | none | none | none |
  | `gradient.limits`, `gradient.blocks` | none | none | `gamma` from `seq.system.gamma` (the gamma of the target, as now) |
  | `pns.safe.levels` | none | `pns.safe` | `hardware=(hw_from_dict(params), label)`, the label as in `checks/pns.py` now; `thresholds=(PNS_LIMIT,)` |

- `RunContext.analysis(id) -> Any`: the value of `compute`, calculated one
  time for each ID in the context. It replaces `RunContext.measure` for the
  four names of this package. `measure` stays for a plugin with its own
  measurement.
- `_run_rule`: a check is "not evaluated" when an analysis in
  `CheckSpec.analyses` is not available for the target: its binding
  needs an input or a model that the target does not give, or it uses a
  raster that neither the file nor the target gives. The reason names the
  analysis and the missing value. The rules of `CheckSpec.inputs`,
  `models` and `rasters` stay; `pns.safe` and the gradient checks keep
  their values so that the specifications in `docs/checks.md` do not
  change.

### 4.6 The analysis results in the matrix

```python
class AnalysisState(Enum):
    DONE = "done"
    NOT_EVALUATED = "not evaluated"
    ERROR = "error"


@dataclass(frozen=True)
class AnalysisResult:
    id: str
    version: int
    target: str
    state: AnalysisState
    reason: str | None = None
    series: tuple[Series, ...] = ()
```

- `run_checks(..., analyses: Sequence[str] = ())`: the IDs of the
  analyses whose results the matrix keeps, for each target. The run
  function calculates each of them for each target, also when no check
  uses it, and with `select=[]` (a run with no checks). An ID that is not
  installed is a `RunError`.
- `ResultMatrix.analyses: tuple[AnalysisResult, ...] = ()`, in the order
  of the targets, then of the IDs. An analysis that is not available for
  a target gives "not evaluated" with a reason. An exception of `compute`
  or `to_series` gives "error" with a reason; it does not stop the run and
  does not change the exit status (an analysis is not a check).
- `ResultMatrix.analysis(target, id) -> AnalysisResult | None`.
- `ResultMatrix.without_series()`: a new matrix with each `series` empty.
- The JSON result: the key `"analyses"` after `"results"`, a list of
  `{"id", "version", "target", "state", "reason", "series"}`, each series as
  `Series.to_obj`. The format stays 1 (decision T10).
- The command: `--analysis ID`, which can be repeated. It changes only the
  JSON result. The summary gets one line for each analysis result that
  is not "done", in the part "not evaluated and errors".
- The live API gives only the series, not the full Python value (for
  example not `PnsLevels`). A live caller that needs the full value calls
  the analysis with the same arguments: decision T8.

### 4.7 `pns.safe`

- `CheckSpec.analyses = ("pns.safe.levels",)`.
- `run` gets `PnsLevels` with `ctx.analysis("pns.safe.levels")`. The state
  is `peak < PNS_LIMIT`. The findings are one for each run of
  `levels.above[PNS_LIMIT]`, as now. The value, the limit, the location,
  the findings and their order do not change, so the tests of
  `test_check_pns.py` stay as they are, except the calls of the private
  measurement.
- The specification version stays 1 (the memory rule for the release
  candidates).

## 5. The work in each repository

| Phase | Repository | Branch | Result |
|---|---|---|---|
| 1 | pulseq-analysis (new) | `feature/initial-move` | The modules of section 4.1, moved, with their tests. Tag `v0.1.0rc1`. |
| 2 | pulseq-checks | `refactor/use-pulseq-analysis` | pulseq-checks depends on pulseq-analysis and has no copies. The behavior does not change. |
| 3 | pulseq-analysis | `feature/series-and-analyses` | `Series`, `Analysis`, the registry, `thresholds`, no `limits` in `grad_limits`. Tag `v0.1.0rc2`. |
| 4 | pulseq-checks | `feature/analysis-results` | Sections 4.5 to 4.7. Tag `v0.1.0rc3`. |
| 5 | pulseq-reports | its own plan | Section 8. |

## 6. Decisions (approved by the user on 2026-10-01)

The user approved the answer of each decision. Do not open these decisions
again. The alternatives stay here as a record.

| # | Decision | Answer | Alternative (not chosen) |
|---|---|---|---|
| T1 | The name of the new package and of its unit | `pulseq-analysis`, import name `pulseq_analysis`; the unit is an *analysis* (`Analysis`, `AnalysisSpec`). The term is that of the analysis passes of a compiler (for example LLVM): a pass that calculates information about the program and does not change it, calculated when a pass asks for it, and kept by a manager until the program changes. A *transformation* pass changes the program. These objects do not change the sequence, so they are analyses. | `pulseq-transformers` (it tells the reader that the sequence changes; a search finds Hugging Face `transformers`), `pulseq-measurements`, `pulseq-derivatives` (in MR, the slew is the derivative of the gradient) |
| T2 | One repository or two | A new repository, with the `project-setup` skill. | A uv workspace in this repository with two distributions; pulseq-reports installs with `#subdirectory=`. |
| T3 | The scope of the new package | Each derived value of a sequence: series and summaries (`GradientLimits`, the block table). They come from the same passes over the sequence. | Only time series. |
| T4 | Limits in pulseq-analysis | None. `HardwareLimits`, the `limits` argument of `gradient_limits`, `SAFE_MODEL` and `hw_from_dict` stay in pulseq-checks. The threshold of a PNS run is a parameter, not a limit. | Keep `HardwareLimits` and `limits` in `grad_limits`, as now. |
| T5 | The thresholds of the PNS runs | A parameter `thresholds`, default `(1.0,)`, so that a later check can use another fraction (for example 0.8) with exact runs. | The fixed threshold 1.0. |
| T6 | The unit of the PNS series | `"1"`, a fraction: 1 is the stimulation threshold, as `PnsLevels`. A float32 envelope in percent is `100 *` a float32, which can round inward, so a bin would not hold each total of its samples. | Percent, as `pns.safe` gives its value. |
| T7 | The encoding of an array in JSON | gzip and base64, the form of pulseq-reports (section 2, fact 8), so that a report puts it into its page with no new encoding. | base64 only, or a list of numbers. |
| T8 | The full Python value in the matrix | No. The matrix keeps only `AnalysisResult` (the series). A live caller calls the analysis again; `pns_levels_for` keeps its result only for one sequence object, so with a path this runs SAFE again. Phase 4 measures the cost. | Keep the full value in a field that does not go into JSON (`compare=False`), so that a live caller gets `PnsLevels`. |
| T9 | Plugin analyses that need values of the target profile | Later. In this plan, a plugin analysis can be registered and used by a plugin check through `compute`, but only the bindings of section 4.5 exist. | A binding entry-point group in this plan. |
| T10 | The JSON format and the specification versions | The format stays 1, and each check specification stays version 1 (the rule for the release candidates). | Format 2. |
| T11 | Names in pulseq-checks for the moved modules | None: no re-export. The release candidates can break the import paths, and no other package imports them yet. | Re-exports with a deprecation warning. |
| T12 | The pypulseq fork pin | Each of the three repositories pins the same commit of the fork. The `TODO.md` item of the fork names the three repositories. | Only pulseq-analysis pins it (not possible: pulseq-checks reads files and calls `check_timing`, which need the read fix of the fork). |

## 7. How to execute this plan

The workflow, the worker tiers and the review are those of
`docs/plans/pulseq-checks-v1.md`, sections 3.1 and 3.2:

1. Start each phase with the `dev-workflow:start-task` skill, from the latest
   default branch of its repository. Then run `nix develop --command uv sync
   --frozen` one time in the worktree, before a worker starts.
2. Each test that a phase adds, moves or changes gets its `TESTS.md` entry
   in the same PR, in the repository of the test.
3. Run `nix develop --command scripts/check` before each PR.
4. Show the commit message to the user, and wait for approval before
   `git commit`. Merge only when the user tells you to.
5. The executing agent reviews each worker's diff line by line.
6. When a phase finds that this plan is wrong, stop and ask the user.

### Phase 1: pulseq-analysis, the move

Repository: new, `mdtisdall/pulseq-analysis`.

**Task 1.1.** The executing agent. The `dev-workflow:project-setup` skill:
the repository, its token, `flake.nix`, `.envrc`, `.gitignore`, the hook,
`scripts/check` (ruff, pytest, the `TESTS.md` check, shellcheck), CI,
`CLAUDE.md`, `pyproject.toml` with the pin of the fork (the
`[tool.uv.sources]` of pulseq-checks), `LICENSE` (MIT), `README.md`,
`CHANGELOG.md`.

**Task 1.2.** Tier M, a refactor (the `parallel-agents` skill). Move the
eight modules of section 4.1 and their tests (section 2, fact 9), with
`tests/oracles/` and the parts of `tests/synthetic.py` and `tests/conftest.py`
that the moved tests use. Change only:

- the import paths (`pulseq_checks` to `pulseq_analysis`);
- `pns_levels.py` without `SAFE_MODEL`, `hw_from_dict` and the tests of
  them;
- the docstrings that name pulseq-checks, its checks or its plans;
- `TESTS.md` sections 2.1 to 2.7, as sections of the new `TESTS.md`.

Compare each moved file with the original: the only differences are the
items above.

**Task 1.3.** Tier M. `docs/usage.md`: section 8 of the `docs/usage.md` of
pulseq-checks, with the changes of task 1.2. Tag `v0.1.0rc1`.

Checks:

- [ ] `scripts/check` passes.
- [ ] Each moved test passes with no change other than its imports.

### Phase 2: pulseq-checks uses pulseq-analysis

Branch: `refactor/use-pulseq-analysis`.

**Task 2.1.** Tier M. `pyproject.toml`: the dependency
`pulseq-analysis @ git+https://github.com/mdtisdall/pulseq-analysis@v0.1.0rc1`.
`safe_model.py` (section 4.1), and the entry point of the model. Delete the
eight modules and their tests. Change the imports in `checks/`, `profile.py`,
`asc_profile.py`, `__init__.py` and the remaining tests. `HardwareLimits`
moves to `profile.py` only if pulseq-analysis loses it (phase 3); in
this phase it is imported from `pulseq_analysis.grad_limits`.

**Task 2.2.** Tier M. `TESTS.md`: remove sections 2.1 to 2.7, and add the
tests of `safe_model.py`. `docs/usage.md` section 8: a link to the
`docs/usage.md` of pulseq-analysis and the example of section 8.3 with
the new imports. `README.md`, `CHANGELOG.md`, `TODO.md` (T12).

Checks:

- [ ] `scripts/check` passes.
- [ ] The JSON result of each sequence of `tests/synthetic.py` against each
  profile of `tests/profiles/` is the same as on `main`, except
  `package_version`.

### Phase 3: pulseq-analysis, series and analyses

Branch: `feature/series-and-analyses` of pulseq-analysis.

**Task 3.1.** Tier H. `series.py` (section 4.2) and its tests: each refusal
of `__post_init__`; `__eq__` with NaN, with another dtype, with another
length; the round trip of `to_obj` and `from_obj` for each kind, with an
array of 2 × 10⁶ float32 values and with values that are not finite; the
same text for one array two times.

**Task 3.2.** Tier H. `pns_levels.py` and `pns.py`: `thresholds` and
`PnsLevels.above` (section 4.4). The tests of `above_limit` move to
`above[1.0]`; the new tests of section 4.4. Measure the time of `pns_levels`
on the 10⁶-block sequence of the time budget with one and with three
thresholds. If one threshold is more than 5 % slower than now, stop and ask
the user.

**Task 3.3.** Tier H, after tasks 3.1 and 3.2. `analyses.py`
(section 4.3), the four analyses, their entry points, `to_series` of
`pns.safe.levels`. `grad_limits.py` without `limits` (T4). Tests: the
registry (two analyses with one ID), the series of `pns.safe.levels`
equal to `level_min`, `level_max` and `above[1.0]` of the same call, and
`()` for a sequence without gradients.

**Task 3.4.** Tier M. `docs/usage.md`, `CHANGELOG.md`. Tag `v0.1.0rc2`.

### Phase 4: pulseq-checks, the analysis results

Branch: `feature/analysis-results`.

**Task 4.1.** Tier H. `rules.py` (`CheckSpec.analyses`,
`RunContext.analysis`), `bindings.py`, `run.py` (`_run_rule`, `analyses`),
`results.py` (`AnalysisState`, `AnalysisResult`, `ResultMatrix.analyses`,
`analysis`, `without_series`, the JSON form), `profile.py`
(`HardwareLimits`). Tests: a run with `analyses=["pns.safe.levels"]` and
`select=[]`; a target without `[models.pns.safe]` gives "not evaluated"; an
exception of `compute` gives "error" and the exit status does not change;
the JSON round trip with series; an ID that is not installed.

**Task 4.2.** Tier M, after task 4.1. `checks/pns.py` and
`checks/gradient.py` use `ctx.analysis`. `scripts/check_docs.py`: the row
"Analyses". `docs/checks.md` (made again). `test_check_pns.py` and
`test_check_gradient.py` pass with no change in their expected values.

**Task 4.3.** Tier M, after task 4.1. `cli.py`: `--analysis` and the
summary line. `tests/test_cli.py`.

**Task 4.4.** Tier X. Measure, on the 10⁶-block sequence of the time
budget: the time of a run with `--analysis pns.safe.levels` and without it,
and the size of the JSON result. Record them in section 9 of this plan.

**Task 4.5.** Tier M. `docs/usage.md` sections 4 to 8, `README.md`,
`CHANGELOG.md`. Tag `v0.1.0rc3`.

Checks:

- [ ] `scripts/check` passes.
- [ ] The results of the checks are the same as on `main`, except
  `package_version`.

## 8. Later

- **pulseq-reports** (its own plan, after phase 4): import the measurement
  modules from pulseq-analysis and delete its eight copies (section 2,
  fact 6); get the PNS lane and the PNS card of each target from
  `ResultMatrix.analysis(target, "pns.safe.levels")`, live or from the JSON
  result; mark the runs of `pns_above_1`.
- **Series of the gradient analyses**: `gradient.blocks` gives `POINTS`
  series for each axis (the peak, the slew and the junction step of each
  block), and the gradient checks get their findings from them.
- **The other measurement modules of pulseq-reports** (`grad_spectrum`,
  `rf_exposure`, `rf_sim`, `profile_metrics`, `waveforms`): move each one to
  pulseq-analysis when a second package needs it.
- **Plugin bindings** (T9).

## 9. Measurements and changes during the work

None yet.
