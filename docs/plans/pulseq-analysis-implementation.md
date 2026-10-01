# Implementation plan: pulseq-analysis, phases 2 and 4 (pulseq-checks)

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: approved by the user on 2026-10-01, not started. Written on 2026-10-01.

## 1. Scope

The design is `docs/plans/pulseq-analysis.md` at commit `e46f0bf` (PR #39).
In this plan, "the design" is that file, and "design 4.5" is its section 4.5.
pulseq-analysis did phases 1 and 3 with its own plan
(`docs/plans/implementation.md` of that repository, "the analysis plan"),
and tagged `v0.1.0rc1` and `v0.1.0rc2`.

This plan gives the work in this repository:

| Phase | Branch | Result |
|---|---|---|
| 0 | `docs/plan-pulseq-analysis-impl` | This plan. |
| 2 | `refactor/use-pulseq-analysis` | Design phase 2, with the pin `v0.1.0rc2` (decision P2): pulseq-checks depends on pulseq-analysis and has no copies. The results do not change (section 5). |
| 4 | `feature/analysis-results` | Design phase 4: tasks 4.1 to 4.4, and the documents of task 4.5 (section 6). |
| R | `chore/release-0.1.0rc3` | The release of design task 4.5: the version, the `CHANGELOG.md` entry, the tag `v0.1.0rc3` (section 7, L14). |

Section 3 lists the decisions. Two of them change the design: P2 (the pin
of phase 2) and P3 (the gamma of the gradient binding). This plan does not
change any other decision of design section 6.

### 1.1 Order

```
Phase 0 (this plan, merged)  ->  Phase 2  ->  Phase 4  ->  Phase R  ->  tag v0.1.0rc3
```

Phase 4 needs the files of phase 2 (`safe_model.py`, the imports), so it
starts from `origin/main` after phase 2 merges.

## 2. Context (verified on 2026-10-01)

pulseq-checks `main` is at `e46f0bf`. pulseq-analysis `main` is at `9f65863`,
which is the tag `v0.1.0rc2`.

1. **The moved modules and tests.** `src/pulseq_checks/` has `asc.py`,
   `extensions.py`, `grad_limits.py`, `pns.py`, `pns_levels.py`,
   `sampling.py`, `seq_index.py` and `seq_utils.py`. `tests/` has
   `test_seq_utils.py`, `test_pns_levels.py`, `test_extensions.py`,
   `test_seq_index.py`, `test_sampling.py`, `test_grad_limits.py`,
   `test_pns.py` and `tests/oracles/`. pulseq-analysis `v0.1.0rc2` has the
   same modules and tests.
2. **The importers that stay.** These files import a moved module:

   | File | Imports |
   |---|---|
   | `src/pulseq_checks/__init__.py` | `HardwareLimits` (and exports it) |
   | `src/pulseq_checks/profile.py`, `rules.py`, `run.py` | `HardwareLimits` |
   | `src/pulseq_checks/asc_profile.py` | `pulseq_checks.asc` (`hardware_name`, `read_gradient_asc`) |
   | `src/pulseq_checks/checks/pns.py` | `pns_levels_for`; `NO_GRADIENTS`, `SAFE_MODEL`, `PnsInterval`, `hw_from_dict`; `sequence_index` |
   | `src/pulseq_checks/checks/gradient.py` | `grad_limits` (`HardwareLimits`, `GradientLimits`, `gradient_limits`, `block_gradient_values` and others) |
   | `src/pulseq_checks/checks/timing.py` | `block_cache_off`, `sequence_index` |
   | `tests/synthetic.py` | `GAMMA` |
   | `tests/test_check_pns.py` | `pns_levels_for`, `SAFE_MODEL`, `hw_from_dict`, `sequence_index`; it reads `levels.above_limit` |
   | `tests/test_check_gradient.py` | `AxisResult`, `GradientLimits`, `HardwareLimits`, `GAMMA`; line 328 makes a `GradientLimits` with `limits=` |
   | `tests/test_run.py` | `HardwareLimits` |
   | `scripts/compare_with_cards.py` | `pulseq_checks.grad_limits.gradient_limits`, line 452 with `limits=` (the "checks" side). Line 345 is the "cards" side: it runs in pulseq-reports and does not change. |

3. **The changes of `v0.1.0rc2` that touch the importers.** `HardwareLimits`,
   the `limits` argument of `gradient_limits` and `GradientLimits.limits` are
   removed. `PnsLevels.above_limit` is replaced by `PnsLevels.above`, a dict
   from each threshold to its intervals. The default `thresholds` is
   `(PNS_LIMIT,)`. `SAFE_MODEL` and `hw_from_dict` are removed from
   `pns_levels`. `SAFE_FIELDS` stays there (analysis plan D1).
4. **What `SAFE_MODEL` was.** In `pns_levels.py` at `e46f0bf`, lines 483 to
   552: a section comment, `_real`, `_SafeModel`, `SAFE_MODEL` and
   `hw_from_dict`. They use `SAFE_FIELDS` and `Mapping`. Five tests in
   `tests/test_pns_levels.py` test them: `test_safe_model_reads_a_valid_dict`,
   `test_safe_model_refuses_an_unknown_key`,
   `test_safe_model_refuses_a_missing_field_or_axis`,
   `test_safe_model_refuses_a_value_that_is_not_a_real_number` and
   `test_hw_from_dict_gives_the_example_hardware`. `TESTS.md` section 2.2
   describes them.
5. **What stays in `tests/`** (analysis plan section 10): `synthetic.py`,
   `scale_sequences.py` and `conftest.py`, whole. `tests/oracles/` has no
   other user and is deleted.
6. **The registry of pulseq-analysis.** `pulseq_analysis.analyses.registry()`
   gives the four analyses by ID. Its `RegistryError` is a subclass of
   `Exception`, not of `CheckRunError`. The specification values are those
   of analysis plan section 8.3: `pns.safe.levels` has `params`
   `("hardware", "thresholds")`, `rasters` `("GradientRasterTime",
   "BlockDurationRaster")` and `cost` `"slow"`.
7. **The JSON form is strict.** `ResultMatrix.from_json` raises `ValueError`
   for a missing key and for an unknown key, in each object.
8. **The gamma of the gradient checks.** `checks/gradient.py` `_gamma(ctx)`
   gives `ctx.sequence.system.gamma` when the limits come from the sequence
   object, else `ctx.profile.make_opts().gamma`. For a `.seq` path, the
   sequence is read with the `Opts` of the target, so the two are equal. For
   a `Sequence` object with the limits of the profile, they can be different.
9. **The documents that name the moved modules.** `docs/usage.md` section 5
   (`HardwareLimits`, a public name), section 7 (the table of the names of
   `ctx.measure`, with the module paths, and the rule "never call
   `gradient_limits` with `limits=None`"), section 8 (all of it), and the
   `TESTS.md` sections 2.1 to 2.7 and the "Contents" paragraph.
10. **Dependencies.** `pyproject.toml` has `pypulseq>=1.5.0.post1`, `numpy`
    and `scipy`, and the fork pin `a74ab06` in `[tool.uv.sources]`.
    pulseq-analysis pins the same commit. No file of this repository imports
    `scipy`.
11. **The release practice.** Each feature PR adds to an "Unreleased" entry
    of `CHANGELOG.md`. A separate release PR (for example #37,
    `chore: release 0.1.0rc2`) sets the version and the date, and then the
    tag is made on `main`.

## 3. Decisions

### 3.1 Decisions of the user (2026-10-01)

| # | Decision | Answer | Alternative (not chosen) |
|---|---|---|---|
| P1 | A plan before the work | This plan, approved before phase 2 starts. | Execute from the design. |
| P2 | The pin of phase 2 | `v0.1.0rc2`. This changes the design, which pins `v0.1.0rc1` in phase 2. Thus phase 2 also moves `HardwareLimits` to `profile.py`, removes `limits=` from the calls of `gradient_limits`, and uses `above[PNS_LIMIT]`. The results do not change. | `v0.1.0rc1` in phase 2, and `v0.1.0rc2` in phase 4. |
| P3 | The gamma of the bindings `gradient.limits` and `gradient.blocks` | `_gamma(ctx)` as now (fact 8): the gamma that converted the limits. This corrects design 4.5, which says `seq.system.gamma`. | `seq.system.gamma`. |
| P4 | `fast_only` and the requested analyses | `fast_only` removes only checks. An analysis in `analyses=` always runs, as a required check does. | `fast_only` gives "not evaluated" for a slow analysis. |
| P5 | The key `"analyses"` of the JSON result | `to_json` always writes it (an empty list when there is no analysis). `from_json` requires it, as each other key. Thus `0.1.0rc3` cannot read a JSON result of `0.1.0rc2`, and `0.1.0rc2` cannot read one of `0.1.0rc3`. `CHANGELOG.md` says so. The format stays 1 (T10). | Optional on read; written only when not empty. |
| P6 | The measurement of design task 4.4 | A tracked mode of `scripts/budget.py` (section 6.4). | A script in the scratchpad. |

### 3.2 Decisions of this plan

These decisions follow from the code. The approval of this plan approves
them.

| # | Decision | Reason |
|---|---|---|
| L1 | The dependency is the PEP 508 direct reference `pulseq-analysis @ git+https://github.com/mdtisdall/pulseq-analysis@v0.1.0rc2`, with `[tool.hatch.metadata] allow-direct-references = true`. | The design gives this form. pip and uv can both install it. A name in `[tool.uv.sources]` only works with uv. Hatchling refuses a direct reference without the option. |
| L2 | `HardwareLimits` goes to `profile.py` in phase 2, with no change to its fields or its docstring, except the sentence on `GradientLimits.limits`. `pulseq_checks.HardwareLimits` stays a public name. | P2 and design 4.1. `profile.py` already makes it, and `rules.py`, `run.py` and `checks/gradient.py` import `profile.py`. |
| L3 | `safe_model.py` is lines 483 to 552 of `pns_levels.py` at `e46f0bf` (fact 4), with the imports that they need. `SAFE_FIELDS` comes from `pulseq_analysis.pns_levels`. The five tests go to `tests/test_safe_model.py` with no change other than their imports. | Analysis plan section 10, facts 1 and 5. |
| L4 | `TESTS.md`: sections 2.1 to 2.7 are removed. The new section "2.1 The SAFE model (`test_safe_model.py`)" has the five entries of fact 4. Sections 2.8 to 2.17 become 2.2 to 2.11. The "Contents" paragraph changes to agree. | The numbers stay in sequence. No document links to a `TESTS.md` section number. |
| L5 | `scipy` stays in the dependencies. | It has no importer (fact 10), but its removal is a different concern. A separate task can remove it. |
| L6 | An analysis that has no binding in `bindings.py` is available only when its `spec.params` is empty. Then `compute(seq)` gets no argument. With parameters, it is "not evaluated", with the reason that pulseq-checks has no binding for it. | T9 defers the plugin bindings. A call with the defaults of the plugin could use values that are not of the target. |
| L7 | `RunContext.analysis(id)` keeps the value, or the exception, of `compute`. A second call for the same ID gives the kept value or raises the kept exception again. | `compute` runs only one time for each target, also when it fails. The check and the requested analysis then give the same error. |
| L8 | `RunContext.analysis(id)` raises `LookupError` when the ID is not installed or the analysis is not available for the target, with the reason. | A check that did not declare the analysis then gets "error" from `_run_rule`, with a reason that names the analysis. |
| L9 | In `_run_rule`, an ID of `spec.analyses` that is not installed gives "error", not "not evaluated". | It is a fault of the installed packages, not a value that the target does not give. |
| L10 | The requested IDs are made unique and sorted, as the check IDs are. An ID that is not installed is a `RunError` before the run reads the sequence. | Design 4.6: "in the order of the targets, then of the IDs". |
| L11 | `run_checks` loads the registry of pulseq-analysis one time. Its `RegistryError` becomes a `pulseq_checks.registry.RegistryError` (exit status 1). `RunContext` gets the loaded registry. A `RunContext` that is made by hand loads it on its first `analysis` call. | Fact 6: an error of the registry is an error of the run. |
| L12 | The command gets no `analyses` key in the check configuration file. `--analysis` works with `--config` and adds to it. | The design gives only `--analysis`. |
| L13 | Each check declares each analysis that it calls: `timing.pypulseq` `("seq.index",)`; the three gradient checks `("gradient.limits", "gradient.blocks")`; `pns.safe` `("pns.safe.levels", "seq.index")`. The `CheckSpec.inputs`, `models` and `rasters` of each check do not change. | Design 4.5. `docs/checks.md` gets an "Analyses" row for each check, and no other change. |
| L14 | Phase R is a separate release PR, not part of phase 4. | Fact 11. |

## 4. How to execute this plan

The workflow is that of design section 7, with the worker tiers of
`docs/plans/pulseq-checks-v1.md` section 3.2:

1. Start each branch with the `dev-workflow:start-task` skill, from the
   latest `origin/main`. Then run `nix develop --command uv sync --frozen`
   one time in the worktree, before a worker starts. (Phase 2 changes the
   dependencies: run `uv lock` and then `uv sync` in that branch.)
2. Each test that a task adds, moves, removes or changes gets its `TESTS.md`
   change in the same PR.
3. Run `nix develop --command scripts/check` before each PR.
4. Show the commit message to the user, and wait for approval before
   `git commit`. Merge only when the user tells you to.
5. The executing agent reviews each worker's diff line by line.
6. When a task finds that this plan or the design is wrong, stop and ask the
   user.

Tiers:

| Tier | Agent | Use it for |
|---|---|---|
| M | `worker-medium` | A move, a removal or an import change with an exact file list, or code that this plan gives exactly. |
| H | `worker-high` | A public interface with local decisions, its tests, or a long document. |
| X | The executing agent | The comparisons, the measurements, the tags, the questions to the user, and the review. |

Give each worker: the task, the worktree, this plan and the sections of the
task, the design sections, the files that it owns, the files that it may
read, and the checks to run. Workers put scratch files in the session
scratchpad.

## 5. Phase 2: pulseq-checks uses pulseq-analysis

Branch: `refactor/use-pulseq-analysis`.

### 5.1 Task 2.0: the baseline (tier X)

In the worktree of phase 2, before task 2.1 changes a file (the worktree is
then at `origin/main`), the executing agent writes the baseline JSON results
with a script in the scratchpad:

- each builder of `tests/synthetic.py` (the list of
  `scripts/compare_with_cards.py` `_synthetic_builders`), written to a `.seq`
  file;
- against each profile of `tests/profiles/`, one at a time, with
  `run_checks(path, [profile])`;
- with `ResultMatrix.to_json()`, and `package_version` set to `""`.

A pair that raises `RunError` records the message. Task 2.3 runs the same
script on the branch.

### 5.2 Task 2.1: the dependency and the move (tier M)

Files:

| File | Change |
|---|---|
| `pyproject.toml` | Add the dependency of L1 and `[tool.hatch.metadata] allow-direct-references = true`. The model entry point `"pns.safe"` becomes `pulseq_checks.safe_model:SAFE_MODEL`. Keep the fork pin and its comment (T12). Then `uv lock`. |
| `uv.lock` | From `uv lock`. |
| `src/pulseq_checks/safe_model.py` (new) | L3. Module docstring: the SAFE model of the target profile (`[models.pns.safe]`), and `hw_from_dict`, which makes the hardware argument of `pulseq_analysis.pns.pns_levels_for`. |
| `src/pulseq_checks/asc.py`, `extensions.py`, `grad_limits.py`, `pns.py`, `pns_levels.py`, `sampling.py`, `seq_index.py`, `seq_utils.py` | Delete. |
| `src/pulseq_checks/profile.py` | Add `HardwareLimits` (L2). Remove its import. |
| `src/pulseq_checks/__init__.py`, `rules.py`, `run.py` | Import `HardwareLimits` from `.profile`. |
| `src/pulseq_checks/asc_profile.py` | Import from `pulseq_analysis.asc`. |
| `src/pulseq_checks/checks/timing.py` | Import from `pulseq_analysis.seq_index`. |
| `src/pulseq_checks/checks/gradient.py` | Import the measurement names from `pulseq_analysis.grad_limits`, and `HardwareLimits` from `..profile`. The call is `gradient_limits(seq, gamma=gamma)`. Change the module docstring: `gradient_limits` has no `limits` argument (lines 5 to 7). |
| `src/pulseq_checks/checks/pns.py` | Import from `pulseq_analysis.pns`, `pulseq_analysis.pns_levels` (`NO_GRADIENTS`, `PNS_LIMIT`, `PnsInterval`), `pulseq_analysis.seq_index` and `..safe_model`. The findings come from `levels.above[PNS_LIMIT]`. The module docstring names `PnsLevels.above`. The text of `CheckSpec` does not change. |
| `tests/test_seq_utils.py`, `test_pns_levels.py`, `test_extensions.py`, `test_seq_index.py`, `test_sampling.py`, `test_grad_limits.py`, `test_pns.py`, `tests/oracles/` | Delete. |
| `tests/test_safe_model.py` (new) | L3. |
| `tests/synthetic.py` | Import `GAMMA` from `pulseq_analysis.seq_utils`. |
| `tests/test_check_pns.py` | Import from `pulseq_analysis` and `pulseq_checks.safe_model`. `levels.above_limit` becomes `levels.above[PNS_LIMIT]`. No other change. |
| `tests/test_check_gradient.py` | Import from `pulseq_analysis.grad_limits`, `pulseq_analysis.seq_utils` and `pulseq_checks.profile`. Line 335: remove `limits=...` from the `GradientLimits` call. No other change. |
| `tests/test_run.py` | Import `HardwareLimits` from `pulseq_checks.profile`. |
| `scripts/compare_with_cards.py` | The "checks" side only: import from `pulseq_analysis.grad_limits`, and line 452 is `gradient_limits(read())`. |

The executing agent checks that no file imports a deleted module:

```bash
git grep -nE "pulseq_checks(\.|\s+import\s+)(asc|extensions|grad_limits|pns|pns_levels|sampling|seq_index|seq_utils)\b|from \.\.?(asc|extensions|grad_limits|pns|pns_levels|sampling|seq_index|seq_utils) import" -- src tests scripts
```

The output must be empty.

### 5.3 Task 2.2: the documents (tier M)

Files:

- `TESTS.md`: L4.
- `docs/usage.md`:
  - section 7, the table of `ctx.measure`: the module paths become those of
    pulseq-analysis, and `gradient_limits(seq, gamma=...)` has no `limits`.
    Remove the sentence "Never call `gradient_limits` with `limits=None`
    ...". The example check imports `sequence_index` from
    `pulseq_analysis.seq_index`.
  - section 8: a short section. The measurement modules are in the package
    pulseq-analysis, a dependency of pulseq-checks. Its `docs/usage.md`
    (a link to `https://github.com/mdtisdall/pulseq-analysis/blob/v0.1.0rc2/docs/usage.md`)
    gives their interface. Keep the text of section 8 on the checks (the
    rasters of `CheckSpec`, the gamma and the hardware of the target, and
    the run function that turns an exception into "error"). Keep the plugin
    example of section 8.3, with `pns_levels_for` from `pulseq_analysis.pns`,
    `hw_from_dict` from `pulseq_checks.safe_model`, and `above[PNS_LIMIT]`.
    Correct each link to a removed subsection.
- `README.md`: one sentence: the measurement modules are in pulseq-analysis.
- `CHANGELOG.md`: an "Unreleased" entry. "Changed": the measurement modules
  moved to pulseq-analysis `0.1.0rc2`, with no re-export (T11); the old
  import paths and their new paths; `HardwareLimits` is in
  `pulseq_checks.profile` and stays `pulseq_checks.HardwareLimits`; the
  model entry point; `above_limit` is now `above[PNS_LIMIT]`, and
  `gradient_limits` has no `limits` (from pulseq-analysis).
- `TODO.md`: the fork item names the three repositories (T12).

### 5.4 Task 2.3: the comparison (tier X)

The executing agent runs the script of task 2.0 on the branch. Each JSON
result is equal to the baseline, byte for byte. Record the number of pairs
and the result in the PR description.

Checks of phase 2:

- [ ] `scripts/check` passes.
- [ ] The `git grep` of task 2.1 gives no output.
- [ ] The comparison of task 2.3 gives no difference.

## 6. Phase 4: the analysis results

Branch: `feature/analysis-results`. Task 4.1 comes first. Tasks 4.2 and 4.3
share no file, except their `TESTS.md` sections, and can run at the same
time. Task 4.4 comes after 4.2 and 4.3.

### 6.1 Task 4.1: the binding, the context, the run and the matrix (tier H)

Files: `src/pulseq_checks/bindings.py` (new), `rules.py`, `run.py`,
`results.py`, `__init__.py`, `tests/test_bindings.py` (new),
`tests/test_run.py`, `tests/test_results.py`, `TESTS.md`.

`bindings.py` (design 4.5):

- `Binding`, a frozen dataclass: `inputs: tuple[str, ...] = ()`,
  `models: tuple[str, ...] = ()`, and `arguments: Callable[[RunContext],
  dict[str, Any]]` (the keyword arguments of `compute`).
- `BINDINGS: Mapping[str, Binding]`, the four bindings of design 4.5:
  - `seq.index`: no inputs, no models, no arguments.
  - `gradient.limits`, `gradient.blocks`: `{"gamma": gamma(ctx)}`.
  - `pns.safe.levels`: models `("pns.safe",)`, and
    `{"hardware": (hw_from_dict(params), label), "thresholds": (PNS_LIMIT,)}`,
    with `params = ctx.profile.models["pns.safe"]` and
    `label = params.get("name") or ctx.profile.sources["models.pns.safe"]`.
- `gamma(ctx)`: `_gamma` of `checks/gradient.py`, moved here (P3).
  `checks/gradient.py` imports it.
- `unavailable(ctx, analysis) -> list[str]`: the reasons that `analysis` is
  not available for the target of `ctx`. Each input and model of its
  binding that the target does not give (with the text of `_run_rule`), each
  raster of `analysis.spec.rasters` with the source "pypulseq default", and
  L6. An empty list means available.

`rules.py`:

- `CheckSpec.analyses: tuple[str, ...] = ()`, the last field.
- `RunContext.__init__` gets `analyses: Mapping[str, Analysis] | None = None`
  (L11).
- `RunContext.analysis(id) -> Any`: L7 and L8. The value is
  `analysis.compute(self.sequence, **binding.arguments(self))`. The kept
  values and exceptions are in `RunContext._analyses`, by ID.
- `measure` stays, with a docstring for plugins only. The four names of this
  package are no longer used.

`run.py`:

- `run_checks(..., analyses: Sequence[str] = ())`: L10, L11 and P4. After the
  checks of each target, one `AnalysisResult` for each requested ID: "not
  evaluated" with the reasons of `unavailable`; else `to_series(value)`,
  which must be a tuple of `Series`, for "done"; else "error" with
  `f"{type(e).__name__}: {e}"` for an exception of `compute` or
  `to_series`, or for a value of `to_series` that is not a tuple of
  `Series`.
- `_run_rule`: before `run`, for each ID of `spec.analyses`: L9 for an ID
  that is not installed; else the reasons of `unavailable` are added to the
  reasons of "not evaluated", each one with the analysis ID. The rules of
  `inputs`, `models` and `rasters` stay.

`results.py` (design 4.6):

- `AnalysisState` and `AnalysisResult`, as design 4.6.
- `ResultMatrix.analyses: tuple[AnalysisResult, ...] = ()`, the last field.
- `ResultMatrix.analysis(target, id) -> AnalysisResult | None`.
- `ResultMatrix.without_series()`.
- `exit_status` and `with_max_findings` do not use `analyses`.
  `with_max_findings` keeps them.
- `to_json`: `"analyses"` after `"results"`, a list of `{"id", "version",
  "target", "state", "reason", "series"}`, each series as `Series.to_obj()`.
  `from_json`: P5. A `ValueError` of `Series.from_obj` stays a `ValueError`.

`__init__.py`: export `AnalysisResult` and `AnalysisState`.

Tests (design task 4.1), with their `TESTS.md` entries:

- `run_checks(path, [target], select=[], analyses=["pns.safe.levels"])`
  gives no result and one `AnalysisResult` "done", whose series are equal to
  `to_series` of `pns_levels_for` with the same hardware.
- a target without `[models.pns.safe]` gives "not evaluated", with a reason
  that names `pns.safe.levels` and the model.
- a `.seq` file without `GradientRasterTime`, and a target without
  `rasters.GradientRasterTime`, gives "not evaluated" for `pns.safe.levels`.
- an exception of `compute` (a monkeypatched registry) gives "error", and
  the exit status of the matrix does not change.
- a check that declares an analysis whose `compute` raises gives "error",
  and `compute` runs one time for the target (L7).
- `analyses=["no.such"]` raises `RunError`.
- `fast_only=True` keeps a requested slow analysis (P4).
- an analysis without a binding: "done" with no parameters, "not evaluated"
  with parameters (L6).
- the JSON round trip of a matrix with series, with a value that is not
  finite in `meta`; `from_json` refuses a matrix without `"analyses"` (P5).
- `ResultMatrix.analysis` and `without_series`.
- a `RegistryError` of pulseq-analysis (a monkeypatched registry) becomes a
  `pulseq_checks.registry.RegistryError` (L11).
- each binding gives the arguments of design 4.5, and the gamma of P3 for a
  `Sequence` object whose gamma is not that of the profile.

### 6.2 Task 4.2: the checks use the analyses (tier M)

After task 4.1. Files: `src/pulseq_checks/checks/pns.py`, `gradient.py`,
`timing.py`, `scripts/check_docs.py`, `docs/checks.md`,
`tests/test_check_pns.py`, `tests/test_check_gradient.py`, `TESTS.md`.

- Each check gets `CheckSpec.analyses` of L13.
- `ctx.measure("index", sequence_index)` becomes `ctx.analysis("seq.index")`,
  `"gradient_limits"` becomes `ctx.analysis("gradient.limits")`,
  `"gradient_blocks"` becomes `ctx.analysis("gradient.blocks")`, and
  `"pns_levels"` becomes `ctx.analysis("pns.safe.levels")`. `pns.safe`
  takes its findings from `levels.above[PNS_LIMIT]` (design 4.7). The
  `hw_from_dict` call and the label move to the binding.
- `scripts/check_docs.py`: the row "Analyses", after "Rasters", with
  `as_code(spec.analyses)`. Then `scripts/check_docs.py` writes
  `docs/checks.md` again.
- Tests: no change in an expected value. Change only what names the
  measurement: `tests/test_check_gradient.py` lines 749 and 750 look for
  `"gradient.limits"` and `"gradient.blocks"` in `ctx._analyses`, not in
  `ctx._measurements`. Add one test: the `CheckSpec.analyses` of each check
  of this package are installed analyses.

### 6.3 Task 4.3: the command (tier M)

After task 4.1. Files: `src/pulseq_checks/cli.py`, `tests/test_cli.py`,
`TESTS.md`.

- `--analysis ID`: `action="append"`, `default=[]`, help "keep the result of
  this analysis for each target in the JSON result; repeat it for more
  analyses". It goes to `run_checks(..., analyses=...)`, also with
  `--config` (L12).
- `summary`: in "not evaluated and errors", after the lines of the checks,
  one line for each analysis result that is not "done":
  `f"  {state}: analysis {id}, target {target}"`, and its reason on the next
  lines, as for a check. "results: no check ran" stays for `select=[]`.
- Tests: `--analysis pns.safe.levels --json -` writes the series; an unknown
  ID gives exit status 1 and its message; a "not evaluated" analysis gives
  its summary lines and does not change the exit status.

### 6.4 Task 4.4: the measurement (tier M for the script, tier X for the run)

After tasks 4.2 and 4.3. Files: `scripts/budget.py`, `TESTS.md` (only if
`tests/test_budget.py` changes), and section 9 of the design.

- `scripts/budget.py`: a child mode `ANALYSIS = "@analysis"`: all the checks
  with `analyses=["pns.safe.levels"]`. Each child record also gets
  `json_bytes`, the length of `matrix.to_json()` in UTF-8 bytes. The table
  shows it.
- The executing agent runs `scripts/budget.py` (10⁶ blocks) and records in
  design section 9: the time and the peak RSS of `@all` and of
  `@analysis`, and the JSON size of each. When `@analysis` is more than 10 %
  slower than `@all`, stop and ask the user (the SAFE pass runs one time in
  both, so the extra time is `to_series` and the JSON).

Checks of phase 4:

- [ ] `scripts/check` passes.
- [ ] The comparison script of task 2.0, run on the branch, gives the same
      `"results"` of each pair as the baseline. (`"analyses"` is the only new
      key, P5.)
- [ ] `docs/checks.md` has the row "Analyses" for each check, and no other
      change.

### 6.5 Task 4.5: the documents (tier M)

In phase 4, after task 4.4. Files: `docs/usage.md`, `README.md`,
`CHANGELOG.md`.

- `docs/usage.md`:
  - section 4: `--analysis`, and the summary line.
  - section 5: `run_checks(..., analyses=...)`, `ResultMatrix.analyses`,
    `analysis`, `without_series`, `AnalysisResult` and `AnalysisState`.
    The live API gives the series only (T8): to get `PnsLevels`, call
    `pns_levels_for` with the arguments of the binding.
  - section 6: the key `"analyses"`, with an example, and the encoding of an
    array (a link to the `docs/usage.md` of pulseq-analysis).
  - section 7: `CheckSpec.analyses`, `ctx.analysis(id)`, and the bindings of
    this package. `ctx.measure` is for the measurements of a plugin.
  - section 8: the bindings of section 7.
- `README.md`: one example of `--analysis pns.safe.levels --json OUT`.
- `CHANGELOG.md`: add to "Unreleased". "Added": the analysis results and
  `--analysis`. "Changed": the JSON key `"analyses"` (P5); `CheckSpec.analyses`;
  the checks use `ctx.analysis`.

## 7. Phase R: the release

Branch: `chore/release-0.1.0rc3`. Tier X. As PR #37:

- `pyproject.toml`: version `0.1.0rc3`. Then `uv lock`.
- `CHANGELOG.md`: "Unreleased" becomes `0.1.0rc3` with the date, an
  introduction, and the time budget of task 4.4.
- `README.md`: the install line with `@v0.1.0rc3`.

After the merge, the executing agent shows the tag command, and runs it and
pushes the tag only after the user approves:

```bash
git -C /Users/dylan/dev/pulseq-checks tag -a v0.1.0rc3 -m "pulseq-checks 0.1.0rc3: the analysis results, with the measurement modules in pulseq-analysis (see CHANGELOG.md)" origin/main
```

## 8. Later

- Remove `scipy` from the dependencies (L5).
- The plugin bindings (T9), and an `analyses` key in the check
  configuration file (L12).
- The work of pulseq-reports (design section 8).

## 9. Measurements

Task 4.4 records its measurements in design section 9.
