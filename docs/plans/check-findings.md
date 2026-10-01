# Plan: all the findings of a check

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: approved (2026-09-30). The user approved the recommended answers of
section 5. Phase 1 has not started.

## 1. Goal

A check can find more problems than its result shows. `timing.pypulseq` is
the first example: `Sequence.check_timing` gives a list of all the timing
errors, but the result keeps only the number of errors and the first one.
This plan:

1. Adds one general way for a check to give a list of findings with its
   result: the `Finding`. Each check, also a plugin check, can use it.
2. Keeps all the findings in the `ResultMatrix`, so that the Python API, the
   JSON result and `ResultMatrix.from_json` carry them to the next reader
   (for example pulseq-reports).
3. Keeps the summary of `pulseq-check` short. The summary gives the number of
   findings of each result. It lists the findings only when the user asks for
   them.
4. Makes `timing.pypulseq` give each error of `check_timing` as a finding.

Not in this plan: findings for the other checks (section 8), and a release.

## 2. Context (verified on 2026-09-30)

1. **The timing check loses the list.** `_Pypulseq.run` in
   `src/pulseq_checks/checks/timing.py` calls `seq.check_timing()`, keeps
   `len(errors)` as the value and the first error as `reason` and
   `location`, and discards the other errors.
2. **The records of pypulseq.** `pypulseq/check_timing.py` (the pinned fork)
   gives a `SimpleNamespace` for each error. Each has `block`, `event`,
   `field`, `error_type` and `value`. Some types have more fields:
   `value_rounded`, `error` and `raster` (`RASTER`); `duration`
   (`BLOCK_DURATION_MISMATCH`, `POST_ADC_DEAD_TIME`, `RF_RINGDOWN_TIME`);
   `dead_time` (`RF_DEAD_TIME`, `ADC_DEAD_TIME`, `POST_ADC_DEAD_TIME`);
   `ringdown_time` (`RF_RINGDOWN_TIME`); `hint` and `numID` (the two soft
   delay types). The values are `str`, `int` or `float`. The dictionary
   `error_messages` of that module has a text template for each type, and
   `print_error_report` fills it with `format_string`, in µs (ns for
   `dwell`).
3. **The number of findings can be large.** Measured on
   `build_repeating(1000)` of `tests/scale_sequences.py` (5000 blocks)
   against `tests/profiles/prisma.toml` (RF ringdown 30 µs; the sequence
   used 20 µs): 2000 errors, one `RF_RINGDOWN_TIME` and one
   `BLOCK_DURATION_MISMATCH` for each TR. A finding in the JSON form of
   section 4.5 is about 330 bytes with `indent=2` (235 bytes compact). For
   the 10⁶ blocks of the time budget, that is 4 × 10⁵ findings and about
   130 MB of JSON. A target with a longer dead time than the sequence is a
   usual case, not a special one.
4. **The streams of the command now.** `cli.main` writes the summary to the
   standard output. With `--json -`, it writes the JSON to the standard
   output and the summary to the standard error. An error of the run goes to
   the standard error. With `--json FILE`, the JSON goes to the file and the
   summary to the standard output.
5. **The JSON reader is strict.** `results.FORMAT` is 1. `from_json` refuses
   a larger format, and an unknown or a missing key in each object. Thus a
   new key needs format 2 (design section 5.11 uses the same rule for
   profiles).
6. **pulseq-reports does not read the JSON yet.** Its step 3 will pin a tag
   of this package. A reader of version `0.1.0rc1` refuses format 2, as
   intended.

## 3. Where the findings go: the result, not the standard error

The question was: can the findings go to the standard error, so that the
console output does not change? This plan does not use the standard error
for the findings. The reasons:

1. **The standard error already has two uses.** With `--json -`, the summary
   goes to the standard error. An error of the run also goes there. A reader
   of the standard error cannot separate the findings from these texts
   reliably.
2. **The API has no standard error.** `run_checks` returns a
   `ResultMatrix`. A second channel for the API (for example `logging` or
   `warnings`) is not data that a caller can keep, write and read again
   (design section 5.5). Thus the API needs the findings in the result
   anyway. A second channel for the command duplicates that.
3. **The command already separates the two outputs.** The JSON result is the
   output for a machine, and the summary is the output for a person. When
   the findings are in the JSON result, the console is not affected:
   `--json result.json` puts all the findings in the file, and the console
   shows the summary only.
4. **One file for the next reader.** The findings are in the same object as
   their result, with the check ID, the target and the state. A reader does
   not join two files.

The options:

| Option | API | Command | Console | Next reader |
|---|---|---|---|---|
| A. The findings go to the standard error | Needs a second channel | Mixed with the summary (`--json -`) and the errors of the run | Changed, unless redirected | Must parse text |
| B. The findings are a field of `Result` (chosen, D1) | `result.findings` | In the JSON result | A count only, by default | One JSON object, read by `from_json` |
| C. A separate findings file (`--findings OUT`, JSON Lines) | `result.findings` | A second file | A count only | Must join two files by check ID and target |

Option C makes the JSON result small when there are many findings. Option B
gets the same effect with `--max-findings` (section 4.6). Option C can come
later as an output form of option B, if a reader needs it.

## 4. Design

### 4.1 `Finding` (`results.py`)

```python
@dataclass(frozen=True)
class Finding:
    """One problem that a check found (plan check-findings, section 4.1)."""

    code: str
    message: str
    location: Location | None = None
    data: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)
```

- `code`: a short, stable name of the kind of finding, for example
  `"RF_RINGDOWN_TIME"`. The specification of the check lists its codes
  (section 4.3). A reader can count or filter the findings by code.
- `message`: one line of text for a person.
- `location`: the same `Location` as a result (block ID and time from the
  sequence start), or `None`.
- `data`: the values of the finding, by name, for a machine. Only JSON
  scalars.
- `__post_init__` raises `TypeError` or `ValueError` when: `code` is not a
  string that is not empty; `message` is not a string; `location` is not a
  `Location` or `None`; a key of `data` is not a string; a value of `data` is
  not `str`, `int`, `float`, `bool` or `None`; or a string value of `data` is
  `"inf"`, `"-inf"` or `"nan"` (section 4.5). A check that makes a bad
  `Finding` raises in `run`, so the run function gives "error" (R1).
- A `Finding` with data is not hashable, as `TargetInfo` is not. Thus a
  `Result` with such a finding is not hashable. No code in `src/` hashes a
  `Result` (verified on 2026-09-30).

### 4.2 The new fields of `Result`

Two fields, after `spec_url`, with defaults, so that each existing call
stays correct:

| Field | Type | Meaning |
|---|---|---|
| `findings` | `tuple[Finding, ...]`, default `()` | The findings of the check, in the order that the check gives. A result of any state can have findings. |
| `findings_omitted` | `int`, default `0` | The number of findings that are not in `findings`, because `ResultMatrix.with_max_findings` (section 4.6) removed them. |

The total number of findings is `len(findings) + findings_omitted`. The
findings do not change the state, and they do not change the exit status.

### 4.3 `CheckSpec.findings` (`rules.py`)

A new field `findings: str | None = None`, after `pypulseq`. For a check that
gives findings, it says: what one finding is, its codes, its location, the
keys of `data`, and the order. `scripts/check_docs.py` adds the row
"Findings" to the table of each check in `docs/checks.md` (`spec.findings`,
or "None"). A plugin check documents its findings in the same field.

### 4.4 The run function (`run.py`)

`_run_rule` already makes "error" for a result that is not a `Result`, or a
result of a different check or target. It also makes "error" when
`findings` is not a tuple of `Finding`, or `findings_omitted` is not an `int`
(not a `bool`) of 0 or more. The reason names the problem. `run_checks` gets
no new argument.

### 4.5 The JSON result: format 2

- `FORMAT` becomes 2. Each result object gets the keys `"findings"` (a list,
  always present) and `"findings_omitted"` (an integer), after
  `"spec_url"`.
- A finding is the object
  `{"code": ..., "message": ..., "location": null | {"block": ..., "time_s": ...}, "data": {...}}`,
  with the keys in this order.
- A float in `data` that is not finite is written as `"inf"`, `"-inf"` or
  `"nan"`, as the other float fields are (the module docstring). `from_json`
  reads these three strings in `data` back as floats. This is why `Finding`
  refuses these three strings as values (section 4.1): the round trip
  `from_json(m.to_json()) == m` stays exact (except `nan`, as now).
- `from_json` reads format 1 and format 2. In format 1, a result object has
  no findings keys, and `from_json` gives `findings=()` and
  `findings_omitted=0`. In format 2, both keys are necessary. A format above
  2 is refused, as now.
- The indent stays 2. A compact form of the findings saves about 30 %
  (section 2, fact 3). It is not worth a custom writer now.

### 4.6 `ResultMatrix.with_max_findings(n)`

A method that returns a new `ResultMatrix`. In each result with more than
`n` findings, it keeps the first `n` and adds the number of the others to
`findings_omitted`. `n` must be an `int` of 0 or more, else `ValueError`.
The API caller and the command use it to limit the size of a matrix. The
truncation is visible to each next reader, because `findings_omitted` is in
the JSON result.

### 4.7 The command (`cli.py`)

- **`--max-findings N`**: apply `with_max_findings(N)` to the matrix before
  the JSON result and the summary are written. The default is no limit (all
  findings), decision D3. An `N` that is not an integer of 0 or more is an
  error in the arguments (status 1).
- **`--show-findings`**: list each finding that the matrix keeps in the
  summary.
- **The summary.** A new part, after "not evaluated and errors" and before
  "unused profile sections". It is present only when a result has findings:

  ```text
  findings (each one is in the JSON result; --show-findings lists them here):
    timing.pypulseq, target Prisma AS82: 4 findings
  ```

  With omitted findings, the line is
  `timing.pypulseq, target Prisma AS82: 4000 findings (1000 kept, 3000 omitted)`.
  With `--show-findings`, one indented line for each kept finding follows
  the line of its result:
  `block 1 at 0 s: BLOCK_DURATION_MISMATCH: <message>` (no location:
  `<code>: <message>`).
- The streams do not change (section 2, fact 4). The findings never go to
  the standard error by themselves.
- The exit status does not change.

### 4.8 `timing.pypulseq` gives its findings (`checks/timing.py`)

- One `Finding` for each record of `check_timing`, in the order of
  `check_timing` (the play order of the blocks).
- `code`: the `error_type` of the record.
- `location`: the block ID of the record and the start time of that block,
  from `ctx.measure("index", sequence_index)`. Make a map from block ID to
  start time one time, not one search for each finding.
- `data`: each field of the record except `block` and `error_type`, as a
  Python `str`, `int` or `float` (convert NumPy scalars).
- `message`: decision D5. The text of pypulseq, from
  `error_messages[error_type]` and `format_string`, with the units of
  `print_error_report` (µs; ns for `field == "dwell"`). When the type is not
  in `error_messages`, or the template fails, the message is
  `"<event>.<field>: <error_type>"`. The values of the template are numbers
  and the strings of the record; the template is the code of the pinned
  pypulseq, not data of the file.
- The value, the limit, the location and the reason of the result do not
  change. A pass has no findings.
- The specification gets its `findings` text (section 4.3). Its version
  stays 1 (decision D6): the quantity, the limit and the pass condition do
  not change, so an old result stays correct.
- The check stays `slow`. The phase measures the time and the JSON size of
  the 10⁶-block sequence of `scripts/budget.py` against a target that fails
  each TR (section 2, fact 3), and records them in section 9 of this plan.

### 4.9 The Python API, for the next reader

```python
matrix = run_checks("scan.seq", [read_profile("prisma.toml")])
for result in matrix.results:
    total = len(result.findings) + result.findings_omitted
    for finding in result.findings:
        print(result.check_id, finding.code, finding.location, finding.data)

small = matrix.with_max_findings(100)  # for a report page
text = small.to_json()  # the findings and findings_omitted go with it
again = ResultMatrix.from_json(text)
```

`Finding` is exported from `pulseq_checks`.

## 5. Decisions (approved by the user on 2026-09-30)

The user approved the recommended answer of each decision. Do not open these
decisions again. The alternatives stay here as a record.

| # | Decision | Answer | Alternative (not chosen) |
|---|---|---|---|
| D1 | The channel for the findings | A field of `Result`, in the JSON result (option B, section 3). | The standard error (A), or a separate file (C). |
| D2 | The names | `Finding` (`code`, `message`, `location`, `data`), `Result.findings`, `Result.findings_omitted`, `CheckSpec.findings`, `ResultMatrix.with_max_findings`. | Other names, for example `Issue` or `details`. |
| D3 | The default limit of the command | No limit: all findings go into the JSON result. `--max-findings N` limits them. | A default limit (for example 1000), with `--max-findings` to change it. |
| D4 | The findings in the summary | One count line for each result with findings; `--show-findings` lists them. | No count lines; or list them by default. |
| D5 | The message of a timing finding | The text of pypulseq (`error_messages` and `format_string`), with a fallback. | Only `"<event>.<field>: <error_type>"`; the numbers are in `data`. |
| D6 | The specification version of `timing.pypulseq` | Stays 1. | 2. |
| D7 | The JSON format | 2, and `from_json` reads 1 and 2. | — |
| D8 | The scope | Only `timing.pypulseq` gives findings in this plan. Section 8 lists the next checks in `TODO.md`. | Also `timing.rasters` (each raster that differs) in phase 2. |
| D9 | The PRs | Two: the general mechanism (phase 1), then the timing check (phase 2). | One PR. |

## 6. How to execute this plan

The workflow, the worker tiers and the review are those of
`docs/plans/pulseq-checks-v1.md`, sections 3.1 and 3.2:

1. Start each phase with the `dev-workflow:start-task` skill, from the latest
   `origin/main`. Then run `nix develop --command uv sync --frozen` one time
   in the worktree, before a worker starts.
2. Each test that a phase adds or changes gets its `TESTS.md` entry in the
   same PR.
3. Run `nix develop --command scripts/check` before each PR.
4. Show the commit message to the user, and wait for approval before
   `git commit`. Merge only when the user tells you to.
5. The executing agent reviews each worker's diff line by line.
6. When a phase finds that this plan is wrong, stop and ask the user.

### 6.1 File ownership

| Phase | Branch | Files |
|---|---|---|
| 1 | `feature/check-findings` | `results.py`, `rules.py`, `run.py`, `cli.py`, `__init__.py`, `scripts/check_docs.py`, `docs/checks.md` (made again), `docs/usage.md` (sections 4, 5, 6, 7), `CHANGELOG.md` (a new "Unreleased" entry), `tests/test_results.py`, `tests/test_run.py`, `tests/test_cli.py`, `TESTS.md` sections 2.9, 2.10 and 2.16, `docs/plans/check-findings.md` (status) |
| 2 | `feature/timing-findings` | `checks/timing.py`, `tests/test_check_timing.py`, `TESTS.md` section 2.13, `docs/checks.md` (made again), `docs/usage.md` (the summary example of section 4), `CHANGELOG.md`, `TODO.md` (section 8), `docs/plans/check-findings.md` (status and section 9) |

Phase 2 starts after phase 1 is merged.

## 7. Phases

### Phase 1: the general mechanism

Branch: `feature/check-findings`. Sections 4.1 to 4.7 and 4.9.

**Task 1.1.** Tier H. `results.py`: `Finding`, the two fields of `Result`,
format 2 with the read of format 1, and `with_max_findings`.
`__init__.py`: export `Finding`. `tests/test_results.py`:

- each refusal of `Finding.__post_init__`;
- the round trip of a matrix with findings, with each type of `data` value,
  with a location and without one, and with a float in `data` that is not
  finite;
- a format 1 text gives `findings=()` and `findings_omitted=0`;
- a format 2 result object without `"findings"` or `"findings_omitted"`
  is refused, and an unknown key in a finding is refused;
- format 3 is refused;
- `with_max_findings`: 0, a number below and above the count, the sum of
  `findings_omitted`, and a negative `n`.

**Task 1.2.** Tier M, after task 1.1. `rules.py`: `CheckSpec.findings`.
`scripts/check_docs.py`: the "Findings" row; make `docs/checks.md` again.
`run.py`: the checks of section 4.4. `tests/test_run.py`: a test rule that
gives findings (they arrive in the matrix unchanged), and a rule that gives
a list instead of a tuple, an object that is not a `Finding`, or a bad
`findings_omitted` (each gives "error" with a reason).

**Task 1.3.** Tier H, after task 1.1, at the same time as task 1.2.
`cli.py`: `--max-findings`, `--show-findings` and the summary part of
section 4.7. `tests/test_cli.py`, with a test check that gives findings
(monkeypatch `registry.check_rules`, as the existing tests do):

- the summary has the count line and no finding line by default;
- `--show-findings` lists each finding, with and without a location;
- `--json FILE` has all the findings, and the console output has none;
- `--json -`: the standard output is only the JSON, with all the findings;
- `--max-findings 1`: the JSON and the summary give the kept and the
  omitted numbers;
- `--max-findings -1` and `--max-findings x` give status 1;
- a run without findings gives the same summary as before this plan.

**Task 1.4.** Tier M, after tasks 1.2 and 1.3. `docs/usage.md`: the new
flags (section 4), `Finding` and the new fields (section 5), format 2 and the
finding object (section 6, with an example), and how a plugin check gives
findings and documents them in `CheckSpec.findings` (section 7).
`CHANGELOG.md`: the "Unreleased" entry. Note in it that a reader of
`0.1.0rc1` refuses format 2.

Checks:

- [ ] `scripts/check` passes.
- [ ] The summary of a run without findings is unchanged.

### Phase 2: the timing check gives its findings

Branch: `feature/timing-findings`. Section 4.8.

**Task 2.1.** Tier H. `checks/timing.py` and `tests/test_check_timing.py`:

- the synthetic sequence that fails on one target: one finding for each
  error of `check_timing`, in its order, with the same codes;
- the location of each finding is its block and the start time of that
  block;
- the `data` of each error type that a test can make (at least `RASTER`,
  `BLOCK_DURATION_MISMATCH`, `RF_DEAD_TIME`, `RF_RINGDOWN_TIME`,
  `ADC_DEAD_TIME`), and that each value is a Python scalar;
- the message for each type in `error_messages`, and the fallback for a type
  that it does not have (a stub record);
- a pass has no findings; the value, the limit, the location and the reason
  do not change;
- the specification has its `findings` text.

**Task 2.2.** Tier X. Measure the time and the JSON size of section 4.8 on
10⁶ blocks, with and without `--max-findings 1000`. Record them in section
9. If the time of `timing.pypulseq` grows by more than 20 %, stop and ask
the user.

**Task 2.3.** Tier M. Make `docs/checks.md` again. Change the summary
example of `docs/usage.md` section 4 (the spin echo now has a findings
part). `CHANGELOG.md`. `TODO.md`: the items of section 8. This plan: the
status and section 9.

Checks:

- [ ] `scripts/check` passes.
- [ ] `pulseq-check` on the spin echo of `tests/synthetic.py` against
  `tests/profiles/prisma.toml` gives 4 findings in the JSON result, and the
  summary gives one count line.

## 8. Later: other checks that can give findings

Phase 2 adds these to `TODO.md`. Each one is its own task, with its own
decision about its specification version:

- `timing.rasters`: one finding for each raster that differs from the
  target, and one for each raster that the file does not declare (the
  "error" reason now joins them with `;`).
- `gradient.amplitude.axis` and `gradient.slew.axis`: one finding for each
  block above the limit, by axis.
- `gradient.amplitude.any-orientation`: one finding for each block where
  |G| is above the limit.
- `pns.safe`: one finding for each interval where the PNS total is at or
  above 100 %.

## 9. Results

Empty until phase 2.
