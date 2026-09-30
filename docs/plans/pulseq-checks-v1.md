# Plan: pulseq-checks version 1

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: approved (2026-09-30). The user approved the decisions of section
2.4, with the version `0.1.0rc1` (decision 11), and answered the questions
of section 7.

This is the implementation plan for step 2 of `docs/plans/pulseq-checks.md`
(the design). The design gives the concepts and the decisions. This plan
gives the phases, the tasks, the files, the workers and the order.

## 1. Goal

Make version 1 of `pulseq-checks`, as the design gives it in section 8, and
make the tag that pulseq-reports pins (design section 9, step 2.5):

1. The measurement modules of the design, section 7.2, move from
   pulseq-reports to this repository, with their tests.
2. The target profile (TOML or JSON), the Siemens `.asc` profile reader (SAFE
   parameters, acoustic resonances and GPA limits), the results, the check
   rules with their specifications, the run function, the check
   configuration reader and the `pulseq-check` command.
3. The version 1 checks: the raster check, the timing check, the gradient
   amplitude and slew checks of each logical axis, the worst-case amplitude
   under rotation, and the PNS check with the SAFE model.
4. The comparison of the new checks with the checks of the pulseq-reports
   cards (design step 2.4). It is done before pulseq-reports removes those
   checks (decision R7).
5. The cost classes and the tested time budget of the fast checks.
6. The tag `v0.1.0rc1`.

Not in this plan: the work in pulseq-reports (design steps 1 and 3), the
checks that the design gives as "later" (section 8 of the design), and JUnit
output.

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repositories

- **pulseq-checks** (`main` at `32ca0bc`): the dev-workflow setup (#1), the
  MIT license (#2), the worker agents `.claude/agents/worker-medium.md` and
  `.claude/agents/worker-high.md` (#3), the design (#4 to #7) and `TODO.md`.
  There is no Python code, no `pyproject.toml` and no `TESTS.md`.
  `scripts/check` runs only shellcheck.
- **pulseq-reports** (`main` at `475a1eb`): the source of the moved modules.
  Its design copy points to the design here (#104). Its step 1 waits for
  phase 7 of this plan (decision R7).
- **pypulseq**: pulseq-reports pins the fork `mdtisdall/pypulseq` at commit
  `a74ab06` (`[tool.uv.sources]` in its `pyproject.toml`): 1.5.0.post1 with
  four commits. Its `TODO.md` item "Move from the pypulseq fork to a pypulseq
  release" lists them.
- **Data.** The real ex-vivo file is
  `/Users/dylan/dev/pulseq-reports/data/exvivo_gre_seg_0.seq` (git-ignored
  there). Never commit it or copy it into this repository. The real `.asc`
  files are confidential. The tests write synthetic `.asc` files
  (`write_gradient_asc` in `tests/conftest.py`).

### 2.2 Decisions that are already made

Do not open these decisions again. They are in the design, section 11:
decisions 3 to 12 and R1 to R7. The ones that this plan uses most:

- Four result states: pass, fail, not evaluated, error (R1). Exit statuses
  0, 2 and 1; status 1 wins over 2 (decision 3, R3). A check is required
  when the caller names it by ID (decision 3, R4).
- No default limits. A missing profile field gives "not evaluated". A
  missing or invalid profile is an error of the run (R2).
- The `seq.system` opt-in is only a keyword argument of the Python function,
  for a `Sequence` object (decision 4).
- The profile format: TOML or JSON, a section for each model, the unknown
  section and unknown key rules, the format version, a value from two
  sources is an error (decision 6, design section 5.11).
- Cost classes `fast` and `slow`, default `slow` (decision 7).
- `HardwareLimits` moves here, and a target profile contains it (decision
  8).
- The public function that reads a check configuration (decision 9).
- The worst-case amplitude under rotation is in version 1 (decision 11).
- The `.asc` reader reads the GPA limits (R5).
- The specification of the raster check gives the direction of its rule
  (R6).
- Moved modules change here first until design step 3 (R7).

### 2.3 Facts that this plan uses (verified on 2026-09-30)

1. **The moved modules.** At pulseq-reports `475a1eb`, in
   `src/pulseq_reports/`:

   | Module | Lines | Imports in the package |
   |---|---|---|
   | `grad_limits.py` | 607 | `seq_index`, `seq_utils` |
   | `pns.py` | 110 | `pns_levels`, `seq_index` |
   | `pns_levels.py` | 334 | `asc`, `extensions`, `sampling`, `seq_index` |
   | `asc.py` | 50 | none |
   | `extensions.py` | 36 | none |
   | `sampling.py` | 278 | `seq_index`, `seq_utils` |
   | `seq_index.py` | 190 | none |
   | `seq_utils.py` | 46 | none |

   No module imports a card, the page or `waveforms`. `grad_spectrum.py` and
   `rf_exposure.py` do not move in version 1 (design section 7.2).
2. **The tests of the moved modules.** In `tests/`:

   | Test file | Tests | Uses | Stays in pulseq-reports |
   |---|---|---|---|
   | `test_grad_limits.py` | 21 | `synthetic`, `oracles.grad_limits` | none |
   | `test_pns.py` | 20 | `synthetic`, `write_gradient_asc` | `test_pns_levels_for_shares_one_computation_with_the_pns_card_and_the_diagram` (it calls `pns_card`, `diagram_card` and `waveforms.full_window`) |
   | `test_pns_levels.py` | 10 | `synthetic`, `write_gradient_asc` | none |
   | `test_extensions.py` | 6 | `synthetic` | `test_a_rotation_file_never_reaches_a_card_unrotated` and `test_gradient_cards_refuse_rotations` (they call cards and `full_window`) |
   | `test_sampling.py` | 21 | `synthetic` | none |
   | `test_seq_index.py` | 14 | `synthetic`, `load_diagram_scale` | none |
   | `test_seq_utils.py` | 9 | `synthetic` | none |

   `synthetic.load_diagram_scale()` imports `scripts/diagram_scale.py` of
   pulseq-reports. That script imports the diagram card and the page, so it
   does not move. `test_seq_index.py` uses only its `build_repeating` and
   `build_worst`. Lines 88 to 237 of `scripts/diagram_scale.py` (from the
   comment `Copied from tests/synthetic.py` to the end of `build_worst`)
   import only `math`, `sys`, `numpy` and `pypulseq`.
3. **The test helpers.** `tests/conftest.py` (71 lines): the
   `--collected-tests-file` option and the `write_gradient_asc` fixture.
   `tests/synthetic.py` (144 lines). `tests/oracles/grad_limits.py` (277
   lines) imports `tests/oracles/blocks.py` (31 lines) and
   `pulseq_reports.seq_utils`. `scripts/check_tests_md.py` (175 lines)
   checks that `TESTS.md` has one entry for each test.
4. **The `TESTS.md` sections of the moved tests** in pulseq-reports: 2.1
   (`test_seq_utils.py`), 2.11 (`test_pns.py`), 2.13 (`test_grad_limits.py`),
   2.21 (`test_extensions.py`), 2.22 (`test_seq_index.py`), 2.23
   (`test_sampling.py`), 2.24 (`test_pns_levels.py`). Section 1 describes the
   static checks.
5. **`seq.read` uses the system.** In the pinned fork, `Sequence.read`
   stores `system.adc_dead_time` in each ADC event (`append=`), and with
   `detect_rf_use` it uses `system.B0` and `system.gamma`. Thus a sequence
   that is read with the `Opts` of one target is not correct for a different
   target.
6. **`check_timing`** compares with `seq.system`: the rasters, the dead
   times and the ringdown of the target.
7. **PNS.** `pns_levels(seq, *, gradient_asc=None)` takes only an `.asc`
   path. With `None`, it uses `safe_example_hw()` and the label
   `asc.EXAMPLE_HARDWARE`. It converts the hardware to a dict with
   `_hw_to_dict` and runs `_safe_gwf_to_pns_chunk` of the fork. It calls
   `extensions.refuse_rotations`, which raises `NotImplementedError`.
8. **The rules of the cards** (the reference of phase 7):
   - Timing: `seq.check_timing()`; the card passes when the error list is
     empty (`cards/timing.py`).
   - PNS: fails when the peak is at or above 100 % (`cards/pns.py`,
     `_check`). A prediction with a `reason` passes. pypulseq gives
     `ok = all(pns_norm < 1)`, the same rule.
   - Gradient limits: fails when a value is above
     `limit * (1 + 1e-9)` (`_LIMIT_TOLERANCE`, `cards/gradient_limits.py`),
     for the peak amplitude and the peak slew of each axis, and with
     `check_norms` for the |G| peak against the amplitude limit. It checks
     the whole file and each window.
9. **The GPA limits in a Siemens `.asc` file.** Neither pypulseq nor MATLAB
   Pulseq reads them. A real file (`MP_GradSys_K2309_2250V_951A_XR_AS82.asc`,
   in `/Users/dylan/dev/vb_pulseq/data/`, confidential) has them, with a
   description of each field in its comments. Only the names, the
   descriptions and the ranges of the values were read; no value is in this
   plan.
   - `asGPAParameters[0].flGradMaxAmpl<Mode>`: "maximum of gradient amplitude
     for the <mode> operation mode".
   - `asGPAParameters[0].flGradMinRiseTime<Mode>`: "minimum gradient rise
     time for the <mode> operation mode".
   - `<Mode>` is `Absolute`, `Nominal`, `Normal`, `Fast`, `UltraFast`,
     `Whisper` or `Boost` (`Nominal` has only the amplitude). The values
     give five different pairs, so the mode changes the limits.
   - Each field has a twin `flDefGrad...`, with the same value in this file.
     The reader uses `flGrad...`.
   - `flSysMaxAmplAbsolute[0..2]` (mT/m) is the maximum of the amplifier for
     each axis. Each value is at or above `flGradMaxAmplAbsolute`. The
     reader does not use it.
   - The file gives the units as "n.a.". The user confirmed the Siemens
     units: the amplitude in mT/m, and the rise time in µs per mT/m. Thus
     the maximum slew in T/m/s is `1000 / rise time`. The values of the file
     are in the ranges that these units give (amplitudes 10 to 200 mT/m,
     slews 30 to 300 T/m/s).
10. **The `ci` devShell** of this repository has Python 3.12, uv and
    shellcheck (`flake.nix`). That is enough for `uv sync`, ruff and pytest.

### 2.4 Decisions of this plan (approved by the user on 2026-09-30)

1. **Package and module names.** The distribution is `pulseq-checks`, the
   import package is `pulseq_checks`, under `src/`. The moved modules keep
   their names (`pulseq_checks.grad_limits`, and so on). Thus design step 3
   in pulseq-reports is an import change only.
2. **The pypulseq pin.** The same fork commit as pulseq-reports (`a74ab06`),
   with the same `[tool.uv.sources]` entry and comment. The two packages
   must pin the same commit. Add the `TODO.md` item "Move from the pypulseq
   fork to a pypulseq release" here too.
3. **One read for each target.** The run function reads the `.seq` file one
   time for each target, with the `Opts` of that target (fact 5). A caller
   that gives a `Sequence` object gets one target only, unless it gives an
   object for each target.
4. **The check IDs of version 1.** The specification version of each one
   starts at 1.

   | ID | What it checks |
   |---|---|
   | `timing.rasters` | The rasters that the file declares, against the rasters of the target (design section 5.10) |
   | `timing.pypulseq` | `check_timing` with the `Opts` of the target |
   | `gradient.amplitude.axis` | The peak amplitude of each logical axis, at or below the amplitude limit |
   | `gradient.slew.axis` | The peak slew of each logical axis, at or below the slew limit |
   | `gradient.amplitude.any-orientation` | The peak of \|G\|, at or below the amplitude limit (decision 11) |
   | `pns.safe` | The peak of the SAFE PNS total, below 100 % |

5. **Tolerances.** The gradient checks use the rule of the card: pass when
   `value <= limit * (1 + 1e-9)` (fact 8). The PNS check uses the rule of
   pypulseq: pass when the peak is below 100 %. Each specification gives its
   tolerance.
6. **The specification as data.** A `CheckSpec` (section 4.5) goes with
   each check rule. `scripts/check_docs.py` makes `docs/checks.md` from the
   specifications of the checks of this package. `scripts/check` fails when
   `docs/checks.md` is not up to date. The link in a result of a check of
   this package goes to its heading in `docs/checks.md` on GitHub. A plugin
   check gives its own URL in its `CheckSpec`.
7. **Entry-point groups.** `pulseq_checks.profile_readers`,
   `pulseq_checks.models` and `pulseq_checks.checks`. The checks of this
   package use the same group, as the cards of pulseq-reports do.
8. **The time budget.** Two parts (question 2 of section 7):
   - `scripts/budget.py` measures the fast checks on a sequence of 10⁶
     blocks (`build_repeating` of `tests/scale_sequences.py`). The executing
     agent runs it in phase 8 and before each tag. This is the budget of
     decision 7. The user approves the number in phase 8.
   - `tests/test_budget.py` runs the fast checks on 10⁵ blocks in
     `scripts/check`, on each PR, with a large margin (phase 8 sets it from
     the measurements). It finds a large slowdown. The margin keeps it
     stable on shared CI machines. It is not the budget of decision 7.
9. **The JSON result.** One object with `"format": 1`, the version of the
   package, the sequence, the targets (with the source of each value), the
   results, and the unused profile sections.
10. **`TESTS.md`.** This repository uses the `TESTS.md` rules of
    pulseq-reports: one entry for each test, with **Checks**, **How** and
    **Assumptions**, and `scripts/check_tests_md.py` in `scripts/check`. The
    worker agents already ask for it.
11. **The version.** `0.1.0rc1`, and the tag `v0.1.0rc1`. `CHANGELOG.md`
    starts with this version.
12. **The PR limit.** At most four PRs of this plan are open at one time.

### 2.5 Terms

The terms of the design, section 12, and:

- **The move rule.** Section 3.5.
- **The comparison.** Phase 7: the new checks against the checks of the
  pulseq-reports cards.
- **Run context.** The object that a check rule gets. It gives the sequence
  of one target, the target profile, and the measurements, each one
  calculated one time for each run (section 4.5).

## 3. How to execute this plan

### 3.1 Workflow

1. Start each phase with the `dev-workflow:start-task` skill, from the
   latest `origin/main`. The worktree is `.worktrees/<short-name>`.
2. From phase 1, run `nix develop --command uv sync --frozen` one time in
   each new worktree, before a worker starts.
3. Each phase that adds or changes a test updates its `TESTS.md` section
   (section 3.4).
4. Run `nix develop --command scripts/check` before each PR.
5. Show the commit message to the user. Wait for approval before
   `git commit`. Merge only when the user tells you to.
6. Each phase ends with a line-by-line review of each worker's diff by the
   executing agent.
7. When a phase finds that this plan or the design is wrong, stop and ask
   the user. Do not change a decision of section 2.2.

### 3.2 Worker model tiers

The workers are the agents of this repository, in `.claude/agents/`.

| Tier | Agent | Use it when |
|---|---|---|
| M | `worker-medium` (Sonnet, medium effort) | The task is a copy, a move, a rename or a removal with an exact file list, or code whose design section 4 gives exactly. |
| H | `worker-high` (Sonnet, high effort) | The task writes a check rule and its specification, a reader with its error cases, a public interface from section 4 with local decisions, or a long document. |
| X | the executing agent, not a worker | The interfaces (section 4), the move rule, the comparison, the measurements, the questions to the user, and the review of each diff. |

Rules for workers, in addition to the rules in their agent files:

1. Give each worker the task, the worktree, this plan with the sections of
   the task, the files that it owns (section 3.4), the files that it may
   read, and the checks to run.
2. Give each worker the move rule (section 3.5) when the task copies a file.
3. A worker that finds that the task and this plan do not agree stops and
   reports. It does not look for a different change.
4. Workers put scratch files in the session scratchpad, not in the
   worktree.

### 3.3 Order and parallel work

```
Wave 1:  Phase 0 (scaffolding)
Wave 2:  Phase 1 (the move)
Wave 3:  Phase 2 (PNS hardware)   Phase 3 (the core)   Phase 4 (the .asc reader)
Wave 4:  Phase 5 (the check rules), after phases 2, 3 and 4
Wave 5:  Phase 6 (command and docs)   Phase 7 (comparison)   Phase 8 (budget)
Wave 6:  Phase 9 (release), after phases 1 to 8
```

- Phase 0 makes `pyproject.toml`, `uv.lock`, `scripts/check`, `TESTS.md`
  and the package. Each later phase needs them.
- Phase 1 copies the modules. Phases 2 to 5 edit or use them.
- Phases 2, 3 and 4 share no file, except their own `TESTS.md` sections.
  In phase 4, task 4.2 (the GPA limits) comes after task 4.1.
- Phase 5 uses the interfaces of phase 3, the PNS hardware of phase 2 and
  the profile reader of phase 4.
- Phases 6, 7 and 8 share no file. Phase 7 must be merged before
  pulseq-reports starts its step 1 (decision R7). Tell the user when phase 7
  is merged.
- Phase 9 comes last.

### 3.4 File ownership

Package root: `src/pulseq_checks/`. "New" marks a file that the phase
makes.

| Phase | Branch | Files that the phase edits |
|---|---|---|
| 0 | `chore/python-scaffolding` | `pyproject.toml` (new), `uv.lock` (new), `src/pulseq_checks/__init__.py` (new), `scripts/check`, `scripts/check_tests_md.py` (new), `tests/conftest.py` (new), `tests/test_package.py` (new), `TESTS.md` (new: the introduction, section 1 and section 2.0), `CLAUDE.md` (the dependency sync line), `TODO.md` (the fork item), `.github/workflows/check.yml` only if a change is necessary |
| 1 | `refactor/move-measurements` | `grad_limits.py`, `pns.py`, `pns_levels.py`, `asc.py`, `extensions.py`, `sampling.py`, `seq_index.py`, `seq_utils.py` (all new), `tests/synthetic.py`, `tests/scale_sequences.py`, `tests/oracles/grad_limits.py`, `tests/oracles/blocks.py`, the seven test files of fact 2 (all new), `TESTS.md` sections 2.1 to 2.7 (new) |
| 2 | `feature/pns-hardware` | `pns_levels.py`, `pns.py`, `tests/test_pns_levels.py`, `tests/test_pns.py`, `TESTS.md` sections 2.2 and 2.7 |
| 3 | `feature/check-core` | `profile.py`, `results.py`, `rules.py`, `run.py`, `config.py`, `registry.py` (all new), `__init__.py`, `tests/test_profile.py`, `tests/test_results.py`, `tests/test_run.py`, `tests/test_config.py` (all new), `tests/profiles/` (new), `TESTS.md` sections 2.8 to 2.11 (new) |
| 4 | `feature/asc-profile-reader` | `asc_profile.py` (new), `asc.py`, `pyproject.toml` (the `siemens-asc` entry point only), `tests/test_asc_profile.py` (new), `tests/conftest.py` (the GPA fields of `write_gradient_asc`, task 4.2 only), `TESTS.md` section 2.12 (new) |
| 5 | `feature/v1-checks` | `checks/__init__.py`, `checks/timing.py`, `checks/gradient.py`, `checks/pns.py` (all new), `pyproject.toml` (the entry points only), `tests/test_check_timing.py`, `tests/test_check_gradient.py`, `tests/test_check_pns.py` (all new), `TESTS.md` sections 2.13 to 2.15 (new) |
| 6 | `feature/pulseq-check-command` | `cli.py` (new), `pyproject.toml` (`[project.scripts]` only), `scripts/check_docs.py` (new), `docs/checks.md` (new), `docs/usage.md` (new), `README.md`, `scripts/check` (the `docs/checks.md` check), `tests/test_cli.py` (new), `TESTS.md` sections 1 (the docs check) and 2.16 (new) |
| 7 | `chore/compare-with-cards` | `scripts/compare_with_cards.py` (new), `docs/comparison.md` (new) |
| 8 | `chore/time-budget` | `scripts/budget.py` (new), `tests/test_budget.py` (new), `checks/*.py` (the `cost` field only, after phase 5), `docs/checks.md` (made again by `scripts/check_docs.py`), `TESTS.md` section 2.17 (new) |
| 9 | `chore/release-0.1.0rc1` | `pyproject.toml` (the version), `CHANGELOG.md` (new), `docs/plans/pulseq-checks-v1.md` (status and results), `docs/plans/pulseq-checks.md` (status) |

Rules:

1. A phase edits only its files. If a phase must edit a different file, it
   stops and asks the executing agent.
2. `TESTS.md`: each phase edits only its own sections. An unchanged heading
   separates each pair of sections, so git merges the edits of parallel
   phases. If a conflict occurs, keep both sides.
3. `pyproject.toml`: phase 0 makes it. Phase 4 adds only the entry point of
   the profile reader, phase 5 only the entry points of the checks, phase 6
   only `[project.scripts]`, phase 9 only the version. Rebase the later one
   and keep both edits.
4. `uv.lock`: only phase 0 changes the dependencies. No other phase adds a
   dependency (design section 10).

### 3.5 The move rule

A copied file of phase 1 is equal to its source at pulseq-reports `475a1eb`,
with only these changes:

1. `pulseq_reports` becomes `pulseq_checks` in import lines.
2. The changes that section 4.2 lists for that file, and no other change.

The executing agent verifies it for each copied file:

```
diff <(git -C /Users/dylan/dev/pulseq-reports show 475a1eb:<source path> \
       | sed 's/pulseq_reports/pulseq_checks/g') <destination path>
```

The output must show only the changes of section 4.2. Put the output in the
PR description.

### 3.6 The comparison rule (phase 7)

The reference is pulseq-reports at `475a1eb`, in a detached worktree:
`git -C /Users/dylan/dev/pulseq-reports worktree add --detach .worktrees/cards-reference 475a1eb`,
then `nix develop --command uv sync --frozen` in it. Remove it at the end of
phase 7. Do not use pulseq-reports `main`: its step 1 removes the checks of
the cards.

## 4. Design

### 4.1 The package

```
src/pulseq_checks/
  __init__.py          public API (phase 3): run_checks, read_check_config,
                       read_profile, TargetProfile, HardwareLimits, Result,
                       ResultMatrix, State, CheckSpec, CheckRule, RunContext
  grad_limits.py  pns.py  pns_levels.py  asc.py  extensions.py
  sampling.py  seq_index.py  seq_utils.py          (moved, phase 1)
  profile.py           TargetProfile and the profile file reader (phase 3)
  asc_profile.py       the Siemens .asc profile reader (phase 4)
  results.py           State, Result, ResultMatrix, JSON (phase 3)
  rules.py             CheckSpec, CheckRule, RunContext (phase 3)
  registry.py          the entry-point groups (phase 3)
  run.py               run_checks (phase 3)
  config.py            read_check_config (phase 3)
  checks/              the version 1 check rules (phase 5)
  cli.py               pulseq-check (phase 6)
```

### 4.2 The copy list (phase 1)

Copy these files from pulseq-reports at `475a1eb`. Apply the move rule
(section 3.5).

**Source code** (`src/pulseq_reports/` to `src/pulseq_checks/`):

| Source | Changes |
|---|---|
| `grad_limits.py` | Imports only |
| `pns.py` | Imports only |
| `pns_levels.py` | Imports only |
| `asc.py` | Imports only |
| `extensions.py` | Imports only |
| `sampling.py` | Imports only |
| `seq_index.py` | Imports only |
| `seq_utils.py` | Imports only |

Also: a docstring or comment that names a pulseq-reports card or document
stays as it is. Phase 1 does not edit text (the move rule). A later phase
that edits the module corrects its text.

**Tests** (`tests/` to `tests/`):

| Source | Changes |
|---|---|
| `test_grad_limits.py` | Imports only |
| `test_pns.py` | Remove `test_pns_levels_for_shares_one_computation_with_the_pns_card_and_the_diagram`, and the imports that only it uses (`pns_card`, `diagram_card`, `full_window`) |
| `test_pns_levels.py` | Imports only |
| `test_extensions.py` | Remove `test_a_rotation_file_never_reaches_a_card_unrotated` and `test_gradient_cards_refuse_rotations`, and the imports that only they use (the four cards, `full_window`) |
| `test_sampling.py` | Imports only |
| `test_seq_index.py` | Import `build_repeating` and `build_worst` from `scale_sequences`, not from `load_diagram_scale()` |
| `test_seq_utils.py` | Imports only |

**Test helpers:**

| Source | Destination | Changes |
|---|---|---|
| `tests/conftest.py` | `tests/conftest.py` | None (phase 0 copies it) |
| `tests/synthetic.py` | `tests/synthetic.py` | Remove `load_diagram_scale` and the imports that only it uses (`importlib.util`, `Path`) |
| `scripts/diagram_scale.py`, lines 88 to 237 | `tests/scale_sequences.py` | New file: a module docstring that names the source, the imports that the lines use, then the lines with no change |
| `tests/oracles/grad_limits.py` | `tests/oracles/grad_limits.py` | Imports only |
| `tests/oracles/blocks.py` | `tests/oracles/blocks.py` | Imports only |
| `scripts/check_tests_md.py` | `scripts/check_tests_md.py` | None (phase 0 copies it) |

**`TESTS.md`** (from the `TESTS.md` of pulseq-reports):

| Source section | Destination section | Changes |
|---|---|---|
| Introduction (lines 1 to 43) | Introduction | Remove the terms and the contents items for the files that do not move. Keep "Synthetic sequences". |
| 1 Static checks: Dependency install, Lint, Format, Shell scripts, TESTS.md coverage | 1 (phase 0) | Remove the Node.js parts. Name the files of this repository. |
| 2.1 `test_seq_utils.py` | 2.1 | None |
| 2.24 `test_pns_levels.py` | 2.2 | None |
| 2.21 `test_extensions.py` | 2.3 | Remove the two entries of the tests that stay |
| 2.22 `test_seq_index.py` | 2.4 | Name `tests/scale_sequences.py` for the builders |
| 2.23 `test_sampling.py` | 2.5 | None |
| 2.13 `test_grad_limits.py` | 2.6 | None |
| 2.11 `test_pns.py` | 2.7 | Remove the entry of the test that stays |

**Configuration** (phase 0): from the `pyproject.toml` of pulseq-reports,
the dependencies, the `[tool.uv.sources]` entry with its comment, the
`[dependency-groups]` and `[tool.ruff]`. From its `scripts/check`, the
`uv sync`, ruff, pytest and `TESTS.md` steps, without the Node.js step.

**Not copied:** the cards, the page, the assets, `waveforms.py`,
`grad_spectrum.py`, `rf_exposure.py`, the other scripts, the JavaScript
tests, `tests/rf_sequences.py`, `tests/plugin_card.py`, the other oracles,
`tests/fixtures/`, `docs/notes/` (the design links to
`docs/notes/slew-definitions.md` in pulseq-reports).

### 4.3 The target profile (phase 3)

`TargetProfile` (frozen dataclass, `profile.py`):

- `name`, `vendor`, `format_version`, `source_path`.
- `opts`: the keyword arguments for `pp.Opts(...)`, or `None` when the
  profile does not give them. `make_opts()` returns `pp.Opts(**opts)`.
- `hardware_limits`: a `HardwareLimits` from the `Opts` values (decision 8),
  or `None`.
- `raster_rule`: `"equal"` or `"multiple"`, for each raster.
- `models`: a mapping from a model section name (for example `"pns.safe"`)
  to its parameters.
- `acoustic_resonances`: a tuple of (frequency, bandwidth) pairs, or `None`.
- `sources`: a mapping from each value path (for example
  `"opts.max_grad"`) to `"profile"` or to the `.asc` file name.
- `unused_sections`: the section names that the reader did not know.

The file (TOML shown; JSON has the same structure):

```toml
format = 1
name = "Prisma AS82"
vendor = "siemens"
asc = "MP_GPA_K2309_2250V_951A_AS82.asc"   # optional; relative to the profile
asc_gradient_mode = "fast"   # optional; the GPA limits of this mode

[opts]              # the keywords of pp.Opts(...)
max_grad = 80
grad_unit = "mT/m"
max_slew = 200
slew_unit = "T/m/s"
rf_dead_time = 100e-6
rf_ringdown_time = 30e-6
adc_dead_time = 10e-6
B0 = 2.89

[rasters]           # the reserved [DEFINITIONS] names (design section 5.11)
GradientRasterTime = 10e-6
RadiofrequencyRasterTime = 1e-6
AdcRasterTime = 100e-9
BlockDurationRaster = 10e-6
rule = "equal"      # or "multiple" (R6)

[models.pns.safe]   # the fields of the SAFE hardware struct; not with an asc
# x = { tau1 = ..., ... }, y = ..., z = ...

[acoustic]          # not with an asc
resonances = [[590, 100], [1140, 220]]
```

Reader rules (`read_profile(path) -> TargetProfile`):

1. The file suffix selects the reader: `.toml` (`tomllib`) or `.json`
   (`json`). Another suffix is an error.
2. `format` is necessary. A value above the version of the reader is an
   error that names both versions.
3. The known sections of format 1: the top level, `opts`, `rasters`,
   `models`, `acoustic`. In `models`, the known model names are the models
   that are installed (the entry-point group). An unknown section is kept in
   `unused_sections`. An unknown key in a known section is an error that
   names the key and the section.
4. `asc` names an `.asc` file. The `.asc` profile reader (phase 4) gives
   the values of that file. A value that the profile file and the `.asc`
   file both give is an error that names the value and both sources.
   `asc_gradient_mode` selects the operation mode of the GPA limits (section
   4.4). Without it, the `.asc` file gives no gradient limits. It is an error
   without `asc`, or with a mode that the file does not have.
5. The reader raises `ProfileError` for each error. The run function turns
   it into an error of the run (status 1, R2).
6. The reader does not supply a default for a value that the file does not
   give.

### 4.4 The Siemens `.asc` profile reader (phase 4)

`asc_profile.py`, registered in `pulseq_checks.profile_readers` as
`siemens-asc`:

- It uses `asc.read_gradient_asc` (the `$INCLUDE` support) and
  `asc.hardware_name`.
- The SAFE parameters: `asc_to_hw` of pypulseq, stored as the section
  `models.pns.safe` in the form of the hardware struct.
- The acoustic resonances: the two layouts that pypulseq reads
  (`aflGCAcousticResonanceFrequency` and
  `asGPAParameters[0].sGCParameters.aflAcousticResonanceFrequency`, with the
  bandwidths).
- The GPA limits (task 4.2, R5), only when the profile gives
  `asc_gradient_mode` (question 1 of section 7). There is no default mode,
  because there are no default limits (R2). The mode names in the profile
  are `absolute`, `normal`, `fast`, `ultrafast`, `whisper` and `boost`
  (`nominal` has no rise time, so it is not a mode for the limits). For the
  mode `<Mode>` (section 2.3, fact 9):
  - `opts.max_grad` = `asGPAParameters[0].flGradMaxAmpl<Mode>`, with
    `grad_unit = "mT/m"`.
  - `opts.max_slew` = `1000 / asGPAParameters[0].flGradMinRiseTime<Mode>`,
    with `slew_unit = "T/m/s"` (the rise time is in µs per mT/m).
  - The result records the mode in `sources` (for example
    `"MP_GradSys_...asc (fast)"`).
- A value that the `.asc` file does not have is not given. It is not an
  error. The profile file can give it.

### 4.5 Check rules, specifications and the run context (phase 3)

```python
class State(Enum): PASS, FAIL, NOT_EVALUATED, ERROR

@dataclass(frozen=True)
class CheckSpec:
    id: str                 # stable, for example "gradient.slew.axis"
    version: int            # changes when the rule changes
    title: str
    quantity: str           # the quantity and its exact definition
    inputs: tuple[str, ...] # the profile value paths that it needs
    models: tuple[str, ...] # the model names that it needs
    limit: str
    tolerance: str
    pass_condition: str
    cost: str = "slow"      # "fast" or "slow" (decision 7)
    pypulseq: str | None = None
    url: str | None = None  # a plugin gives its own; None for this package

class CheckRule(Protocol):
    spec: CheckSpec
    def run(self, ctx: RunContext) -> Result: ...
```

`RunContext` (one for each target):

- `sequence`: the `pp.Sequence`, read with the `Opts` of the target (fact
  5).
- `profile`: the `TargetProfile`.
- `measure(name, fn)`: returns the value of `fn(sequence)` and keeps it for
  the other rules of the same target. The version 1 names are
  `"index"`, `"gradient_limits"` and `"pns_levels"`. A plugin check uses the
  same function, so that it does not calculate a measurement two times. This
  is the part of decision 7 for other developers.
- `limits_source`: `"profile"`, or `"sequence object"` with the opt-in of
  decision 4.

The run function makes a result with the state "not evaluated" before it
calls `run`, when a value of `spec.inputs` or a model of `spec.models` is
missing. It makes a result with the state "error" when `run` raises an
exception (R1). The reason has the exception type and message.

`Result` (frozen dataclass, `results.py`): `check_id`, `spec_version`,
`target`, `state`, `value`, `limit`, `unit`, `location` (block ID and time
in seconds, or `None`), `model` and `model_version` (or `None`),
`reason` (or `None`), `required` (bool), `spec_url`.

`ResultMatrix`: the results, the targets with their `sources`, the unused
sections of each profile, `exit_status()` (design section 5.6, R3),
`to_json()` and `from_json()` (decision 9 of section 2.4).
`from_json(to_json())` gives an equal matrix.

### 4.6 The run function and the check configuration (phase 3)

```python
def run_checks(
    sequence: str | Path | pp.Sequence,
    targets: Sequence[TargetProfile],
    *,
    select: Sequence[str] | None = None,        # check IDs; None: all
    required: Mapping[str, Sequence[str] | None] = {},  # ID -> targets or None (all)
    fast_only: bool = False,
    limits_from_sequence: bool = False,          # decision 4
) -> ResultMatrix
```

- A path: one read for each target (decision 3 of section 2.4). A `Sequence`
  object: exactly one target, or an error of the run.
- `limits_from_sequence=True` with a path is an error of the run (decision
  4). With an object, a target with no gradient limits uses
  `seq.system`, and `limits_source` records it.
- No target is an error of the run (R2).
- A required ID that is not a known check is an error of the run.
- Selection by `fast_only` does not make a check required (R4).

`read_check_config(path) -> CheckConfig` (`config.py`, decision 9): a TOML
or JSON file with `format = 1`, the paths of the target profiles (relative
to the file), `select`, `required` and `fast_only`. `pulseq-check` and
pulseq-reports both read it with this function. The same unknown-key rule as
the profile applies.

### 4.7 The version 1 check rules (phase 5)

| ID | Module | Measurement | Rule | Inputs | Location |
|---|---|---|---|---|---|
| `timing.rasters` | `checks/timing.py` | `seq.definitions` of the file | The specification gives the rule for `equal` and `multiple`, and its direction (R6) | `rasters.*` | None |
| `timing.pypulseq` | `checks/timing.py` | `seq.check_timing()` | Pass when the error list is empty | `opts` (rasters, dead times, ringdown) | The first error block |
| `gradient.amplitude.axis` | `checks/gradient.py` | `gradient_limits` with the `HardwareLimits` of the target | For each logical axis, pass when the peak is at or below `max_grad * (1 + 1e-9)`; the value is the axis with the largest ratio | `opts.max_grad` | `peak_block`, `peak_time_s` |
| `gradient.slew.axis` | `checks/gradient.py` | the same | The same, with the slew and `max_slew` | `opts.max_slew` | `slew_block`, `slew_time_s` |
| `gradient.amplitude.any-orientation` | `checks/gradient.py` | the same | Pass when the \|G\| peak is at or below `max_grad * (1 + 1e-9)` | `opts.max_grad` | `vector_peak_block`, `vector_peak_time_s` |
| `pns.safe` | `checks/pns.py` | `pns_levels` with the SAFE parameters of the profile (phase 2) | Pass when the peak is below 100 % | `models.pns.safe` | The block at the peak time |

- A file with the rotation extension: the measurement raises
  `NotImplementedError`, and the result is "error" (R1). With pypulseq
  1.5.0.post1, `Sequence.read` raises `ValueError` for such a file first:
  that is an error of the run.
- The gradient checks use the whole file. The windows of the card are not in
  version 1.
- The gradient checks never call `gradient_limits` with `limits=None`
  (design section 7.2).
- The PNS check never uses `safe_example_hw()` or `EXAMPLE_HARDWARE`.

### 4.8 The command `pulseq-check` (phase 6)

```
pulseq-check SEQ_FILE (--config FILE | --target PROFILE ...)
             [--check ID ...] [--fast] [--json OUT] [--quiet]
```

- `--check ID` selects a check and makes it required for each target
  (decision 3).
- `--json OUT` writes `ResultMatrix.to_json()`. `-` writes to stdout.
- The summary for a person: one line for each check and target, then the
  "not evaluated" and "error" results with their reasons, then the unused
  profile sections.
- The exit status: `ResultMatrix.exit_status()`, or 1 for an error of the
  run.
- There is no flag for the `seq.system` limits (decision 4).

## 5. Phases

Each phase: its branch (section 3.4), its tasks, and the checks before its
PR. A task names its tier (section 3.2).

---

### Phase 0: Python scaffolding

Branch: `chore/python-scaffolding`. Wave 1.

**Task 0.1.** Tier M. Make `pyproject.toml` from section 4.2 ("Configuration")
and decisions 1 and 2 of section 2.4: the name `pulseq-checks`, the version
`0.1.0.dev0`, `requires-python = ">=3.12"`, the hatchling build of
`src/pulseq_checks`, and no entry points yet. Make
`src/pulseq_checks/__init__.py` with a module docstring only.

**Task 0.2.** Tier M. Copy `tests/conftest.py` and
`scripts/check_tests_md.py` (section 4.2). Write `TESTS.md`: the introduction
and section 1 (section 4.2), and section 2.0 for `tests/test_package.py`.
That file has one test: `import pulseq_checks` works, and the installed
distribution `pulseq-checks` has the version of `pyproject.toml`. Thus
pytest has a test to run from phase 0. Change `scripts/check` to run, in
this order: `uv sync --frozen`, `ruff check .`, `ruff format --check .`,
pytest with `--collected-tests-file`, `scripts/check_tests_md.py
--collected`, and shellcheck (the pulseq-reports form, without Node.js).

**Task 0.3.** Tier X.

1. `nix develop --command uv lock`. Confirm that `uv.lock` has pypulseq from
   the fork at `a74ab06`.
2. Change the dependency sync line of `CLAUDE.md`: remove "(after
   `pyproject.toml` exists; until then there is nothing to sync)".
3. Add the fork item to `TODO.md` (decision 2 of section 2.4).
4. Confirm that CI runs the new `scripts/check` in the `ci` devShell (fact
   10). Change `.github/workflows/check.yml` only if it fails.
5. Review each diff.

Tasks 0.1 and 0.2 run at the same time.

Checks:

- [ ] `scripts/check` passes, with the one test of `tests/test_package.py`.
- [ ] `uv.lock` pins the fork commit `a74ab06`.
- [ ] CI passes.

---

### Phase 1: move the measurement modules

Branch: `refactor/move-measurements`. Wave 2. Section 4.2.

**Task 1.1.** Tier M. Copy the eight source modules (section 4.2, "Source
code"). Apply the move rule.

**Task 1.2.** Tier M. Copy the test files and the test helpers (section 4.2,
"Tests" and "Test helpers", except the files of phase 0). Make
`tests/scale_sequences.py`. Apply the move rule and the listed removals.

**Task 1.3.** Tier M. Copy the `TESTS.md` sections (section 4.2,
"`TESTS.md`") as sections 2.1 to 2.7.

**Task 1.4.** Tier X.

1. Run the move rule diff (section 3.5) for each copied file. Put the output
   in the PR description.
2. Confirm that the number of tests is the number of fact 2, minus the
   three tests that stay: 101 - 3 = 98 tests (a parametrized test is one
   test for `TESTS.md`).
3. Tell the user: from now on, a change to a moved module happens here
   first (R7).
4. Review each diff.

Tasks 1.1, 1.2 and 1.3 run at the same time. They share no file.

Checks:

- [ ] The move rule diff shows only the changes of section 4.2.
- [ ] Each moved test passes, with no change to its assertions.
- [ ] `TESTS.md` has an entry for each test, and no other.
- [ ] `scripts/check` passes.

---

### Phase 2: PNS with the hardware of a profile

Branch: `feature/pns-hardware`. Wave 3. Section 4.7 (`pns.safe`).

**Task 2.1.** Tier H. Add a keyword `hardware` to `pns_levels` and
`pns.pns_levels_for`: a SAFE hardware struct (the form of `asc_to_hw`) and
its label. `gradient_asc` and `hardware` together are a `ValueError`. With
neither, the behavior does not change (pulseq-reports uses it). Correct the
docstrings that name pulseq-reports cards in the functions that the task
edits. Add the tests:

1. `hardware=safe_example_hw()` gives a result equal to the result with no
   hardware, except the label (exact equality of the arrays and the peak).
2. `hardware=` from `asc_to_hw` of a `write_gradient_asc` file gives a
   result equal to `gradient_asc=` of the same file.
3. Both keywords raise `ValueError`.

Add their `TESTS.md` entries (sections 2.2 and 2.7).

**Task 2.2.** Tier X. Review the diff. Confirm that the tests of phase 1 do
not change.

Checks:

- [ ] The new tests pass. The moved PNS tests pass with no change.
- [ ] `scripts/check` passes.

---

### Phase 3: the core (profile, results, rules, run, configuration)

Branch: `feature/check-core`. Wave 3. Sections 4.3, 4.5 and 4.6.

**Task 3.1.** Tier H. `profile.py`: `TargetProfile`, `HardwareLimits` from
the `Opts` values, `ProfileError` and `read_profile` (section 4.3, rules 1 to
6; rule 4 with a stub that phase 4 replaces: the reader of the `asc` key is
the entry point `siemens-asc`, and with no reader installed the key is an
error). `tests/test_profile.py` and `tests/profiles/` (small TOML and JSON
profiles). The tests: each rule of section 4.3, TOML and JSON give equal
profiles, and a round trip of each example.

**Task 3.2.** Tier H. `results.py`: `State`, `Result`, `ResultMatrix` with
`exit_status()` (each row of design section 5.6, and R3), `to_json()` and
`from_json()`. `tests/test_results.py`: each exit status case, and the round
trip.

**Task 3.3.** Tier H. `rules.py` (`CheckSpec`, `CheckRule`, `RunContext`),
`registry.py` (the three entry-point groups, decision 7 of section 2.4; a
duplicate check ID is an error that names both packages), `run.py`
(`run_checks`, section 4.6) and `config.py` (`read_check_config`).
`tests/test_run.py` with test check rules defined in the test file: "not
evaluated" for a missing input, "error" for an exception, `measure` runs
one time for each target, `required`, `fast_only`, the path and object
cases, and `limits_from_sequence`. `tests/test_config.py`.

**Task 3.4.** Tier X. Before the workers start: confirm that section 4 is
complete enough for three workers in parallel. The interfaces between the
tasks are the dataclasses of sections 4.3 and 4.5, and `__init__.py` is
the executing agent's (it adds the exports at the end). Review each diff.

Tasks 3.1, 3.2 and 3.3 run at the same time. Task 3.3 imports the types of
tasks 3.1 and 3.2 by the names of section 4. If a worker needs a change to
a type of a different task, it stops and reports.

Checks:

- [ ] The public API of section 4.1 is in `__init__.py`.
- [ ] `scripts/check` passes.

---

### Phase 4: the Siemens `.asc` profile reader

Branch: `feature/asc-profile-reader`. Wave 3. Section 4.4.

**Task 4.1.** Tier M. `asc_profile.py`: the SAFE parameters and the
acoustic resonances (section 4.4). Register it as `siemens-asc` in the
entry-point group `pulseq_checks.profile_readers` in `pyproject.toml`.
`tests/test_asc_profile.py` with `write_gradient_asc`: the plain and the
split layout, the `$INCLUDE` file, and the resonances of both layouts.

**Task 4.2.** Tier H. The GPA limits (section 4.4). Add the GPA fields to
`write_gradient_asc`: a keyword with synthetic amplitudes and rise times for
each mode, and the default "no GPA fields", so that the tests of phase 1 do
not change. Do not use a value of a real file. Tests: each mode gives its
amplitude and `1000 / rise time`; no `asc_gradient_mode` gives no gradient
limits; an unknown mode, or a mode without `asc`, is an error; a profile
that gives `max_grad` and selects a mode is an error (section 4.3, rule 4).

**Task 4.3.** Tier X. Review each diff.

Tasks 4.1 and 4.2 edit the same new file, so they run one after the other.

Checks:

- [ ] `scripts/check` passes.
- [ ] No real `.asc` file or value is in the repository.

---

### Phase 5: the version 1 check rules

Branch: `feature/v1-checks`. Wave 4, after phases 2, 3 and 4 (task 4.1).
Section 4.7.

**Task 5.1.** Tier H. `checks/timing.py`: `timing.rasters` and
`timing.pypulseq`, with their `CheckSpec`s. The specification of
`timing.rasters` gives the direction of the `multiple` rule and why a file
with that raster plays correctly (R6). If the worker cannot justify a
direction from the Pulseq specification (the raster conventions of
`doc/specification.tex` of MATLAB Pulseq), it stops and reports; the
executing agent asks the user. `tests/test_check_timing.py`: each raster
case, and a synthetic sequence with a timing error on one target and not
on a different target.

**Task 5.2.** Tier H. `checks/gradient.py`: the three gradient checks and
their `CheckSpec`s. `tests/test_check_gradient.py`: at the limit, above the
limit by more than the tolerance, the axis with the largest ratio, |G| above
the limit when each axis is below it, and the location.

**Task 5.3.** Tier M. `checks/pns.py`: `pns.safe` and its `CheckSpec`, from
the table of section 4.7. `tests/test_check_pns.py`: "not evaluated" with no
SAFE parameters, a pass and a fail with `write_gradient_asc` and its
`limit_scale`, the location, and "error" for a rotation (a
`rotation_library` stub, as `test_extensions.py` makes one).

**Task 5.4.** Tier X. Add the entry points of the six checks to
`pyproject.toml`. Review each diff. Confirm that each `CheckSpec` has each
field of section 4.5 and `cost="slow"` (phase 8 sets the classes).

Tasks 5.1, 5.2 and 5.3 run at the same time. They share no file, except
their own `TESTS.md` sections.

Checks:

- [ ] Each check has a test for each state that it can give.
- [ ] `scripts/check` passes.

---

### Phase 6: the command and the documents

Branch: `feature/pulseq-check-command`. Wave 5. Section 4.8.

**Task 6.1.** Tier H. `cli.py` and `[project.scripts]`
`pulseq-check = "pulseq_checks.cli:main"`. `tests/test_cli.py`: each exit
status, `--json`, `--config`, `--check` makes a check required, and an
invalid profile gives 1 with a message.

**Task 6.2.** Tier M. `scripts/check_docs.py`: it writes `docs/checks.md`
from the `CheckSpec`s (one heading for each ID, with each field), and with
`--check` it exits 1 when the file is not up to date. Add the `--check` run
to `scripts/check` and to `TESTS.md` section 1.

**Task 6.3.** Tier H. `docs/usage.md` (the profile format with the TOML and
JSON examples, the check configuration, the Python API, the command, the
result JSON, how to write a plugin check with `CheckSpec` and
`RunContext.measure`) and `README.md` (what the package does, the install
by git URL and tag, and a short example).

**Task 6.4.** Tier X. Run `pulseq-check` on the ex-vivo file (fact of
section 2.1) with a profile of the synthetic limits. Put the output in the
PR description. Review each diff.

Tasks 6.1, 6.2 and 6.3 run at the same time.

Checks:

- [ ] `docs/checks.md` is up to date.
- [ ] `scripts/check` passes.

---

### Phase 7: the comparison with the pulseq-reports cards

Branch: `chore/compare-with-cards`. Wave 5, after phase 5. Section 3.6.

**Task 7.1.** Tier M. `scripts/compare_with_cards.py`: for each sequence and
each limit set of task 7.2, run the cards of the reference worktree
(`timing_card`, `gradient_limits_card` with `check_norms=True`, `pns_card`)
and `run_checks` of this branch, and write one JSON line for each pair. The
script takes the path of the reference worktree as an argument. It runs in
the devShell of each repository (two processes), because the two packages
have different environments.

**Task 7.2.** Tier X. The comparison set:

1. The synthetic sequences of `tests/synthetic.py`, and
   `build_repeating(1000)` and `build_worst(1000)`.
2. The ex-vivo file.
3. Three limit sets: the synthetic limits (28 mT/m, 150 T/m/s), limits that
   make each gradient check fail, and the SAFE example hardware scaled so
   that the PNS check fails (`write_gradient_asc`, `limit_scale`).

Expected results:

| New check | Card | Expected |
|---|---|---|
| `timing.pypulseq` | timing card | The same pass or fail, and the same error list |
| `gradient.amplitude.axis`, `gradient.slew.axis` | gradient limits card, whole file | The same pass or fail; the same values to 1e-12 relative |
| `gradient.amplitude.any-orientation` | gradient limits card, `check_norms=True` | Its |G| part: the same pass or fail and value |
| `pns.safe` | PNS card, the same `.asc` | The same peak (exact) and the same pass or fail |
| `timing.rasters` | none | Not compared |

**Task 7.3.** Tier X. Write `docs/comparison.md`: the commit of the
reference, the set, the commands and the results. A difference stops the
phase: report it to the user with its cause.

Checks:

- [ ] Each expected result of task 7.2 holds, or the user accepts each
      difference in writing.
- [ ] Tell the user that pulseq-reports can start its step 1.

---

### Phase 8: the time budget and the cost classes

Branch: `chore/time-budget`. Wave 5, after phase 5.

**Task 8.1.** Tier M. `scripts/budget.py`: build `build_repeating(n)` for 10⁶
blocks (`n` from `TR_BLOCKS` of `tests/scale_sequences.py`), write it to a
scratch `.seq` file, and time `run_checks` for each check alone, in a fresh
process, with the synthetic limits and the SAFE example hardware as a
profile. It prints one line for each check: the time and the peak RSS. It
stops a run at 5 minutes or at 8 GB of RSS.

**Task 8.2.** Tier M. `tests/test_budget.py`: build `build_repeating(n)`
for 10⁵ blocks, write it to `tmp_path`, and time `run_checks` with
`fast_only=True` and the synthetic profile. It fails when the time is above
`CI_BUDGET_S`, a constant at the top of the file that task 8.3 sets. Its
`TESTS.md` entry (section 2.17) says that it finds a large slowdown only and
is not the budget of decision 7.

**Task 8.3.** Tier X.

1. Run `scripts/budget.py` three times. Record the median of each check.
2. Propose to the user: the cost class of each check, and the budget of the
   fast checks together (the measured sum with a margin). The user approves
   them.
3. Set the `cost` field of each approved fast check. Make `docs/checks.md`
   again.
4. Run `tests/test_budget.py` three times locally and read the time of
   the latest CI run of the branch. Set `CI_BUDGET_S` to three times the
   largest of these times, and tell the user the number.
5. Write the numbers, the machine and the budget in the PR description and
   in section 8 of this plan (phase 9 copies them).

Checks:

- [ ] The fast checks together are within the approved budget.
- [ ] `tests/test_budget.py` passes in CI.
- [ ] `docs/checks.md` is up to date.
- [ ] `scripts/check` passes.

---

### Phase 9: release 0.1.0rc1

Branch: `chore/release-0.1.0rc1`. Wave 6, after phases 1 to 8.

**Task 9.1.** Tier X.

1. Set the version `0.1.0rc1` in `pyproject.toml`. Run `uv lock`.
2. Write `CHANGELOG.md` with the `0.1.0rc1` entry.
3. Run `scripts/budget.py` again. The fast checks must be within the budget.
4. Write the status and section 8 (results) of this plan, and the status
   of the design.
5. After the merge, and only when the user tells you to: tag `v0.1.0rc1` on
   the merge commit and push the tag.
6. Tell the user that pulseq-reports can start its step 3 with the tag
   `v0.1.0rc1`.

Checks:

- [ ] `scripts/check` passes.
- [ ] The tag exists on GitHub.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 0 | This plan is merged. |
| 2 | 1 | Phase 0 merged. |
| 3 | 2, 3, 4 | Phase 1 merged. |
| 4 | 5 | Phases 2 and 3 merged, and task 4.1 merged. |
| 5 | 6, 7, 8 | Phase 5 merged. |
| 6 | 9 | Phases 1 to 8 merged. |

Workers inside a phase:

| Phase | Workers | The executing agent |
|---|---|---|
| 0 | M for task 0.1, M for task 0.2, at the same time | Task 0.3 and the review |
| 1 | M for tasks 1.1, 1.2 and 1.3, at the same time | Task 1.4 (the move rule) and the review |
| 2 | H for task 2.1 | Task 2.2 and the review |
| 3 | H for tasks 3.1, 3.2 and 3.3, at the same time | Task 3.4 (interfaces first) and the review |
| 4 | M for task 4.1, then H for task 4.2 | Task 4.3 and the review |
| 5 | H for task 5.1, H for task 5.2, M for task 5.3, at the same time | Task 5.4 and the review |
| 6 | H for task 6.1, M for task 6.2, H for task 6.3, at the same time | Task 6.4 and the review |
| 7 | M for task 7.1 | Tasks 7.2 and 7.3 (the comparison) and the review |
| 8 | M for task 8.1, M for task 8.2, at the same time | Task 8.3 (the measurements and the user's approval) and the review |
| 9 | None | All tasks |

The cheaper tier (M) does each copy, the PNS rule, the `.asc` reader for
the values that pypulseq already reads, the documents script and the two
measurement scripts. The H tier does the tasks that set a public interface,
a rule with its specification, or a long document.

## 7. Questions still open

None. The user answered the three questions on 2026-09-30:

1. **The GPA limits (R5).** The fields are in the `.asc` file (section 2.3,
   fact 9). The user confirmed the units (mT/m, and µs per mT/m for the rise
   time), and chose that the profile names the operation mode
   (`asc_gradient_mode`, section 4.4). There is no default mode.
2. **The time budget.** A test at 10⁵ blocks with a large margin in
   `scripts/check`, and the budget of 10⁶ blocks before each tag (decision
   8).
3. **The decisions of section 2.4.** Approved, with the version `0.1.0rc1`
   and the tag `v0.1.0rc1` (decision 11).
