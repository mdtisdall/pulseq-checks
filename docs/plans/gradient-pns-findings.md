# Plan: findings of the gradient checks and of `pns.safe`

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: approved (2026-10-01). The user approved the recommended answers of
section 5. Phase 1 has not started.

## 1. Goal

The rest of the `TODO.md` item "Findings of more checks"
(`docs/plans/check-findings.md`, section 8). `timing.pypulseq` (#24) and
`timing.rasters` (#31) give findings. This plan makes the four other checks
give them:

1. `gradient.amplitude.axis`: one finding for each block and axis where the
   amplitude is above the limit.
2. `gradient.slew.axis`: one finding for each block and axis where the slew
   of a segment, or the step at the start of the block, is above the limit.
3. `gradient.amplitude.any-orientation`: one finding for each block where
   |G| is above the limit.
4. `pns.safe`: one finding for each interval of samples where the SAFE total
   is at or above 100 %.

The general mechanism (`Finding`, `--max-findings`, the JSON keys) does not
change. Each check keeps its value, limit, location, state and reason, and
its specification stays version 1 (design section 5.4).

Not in this plan: findings for a window of the file (the checks cover the
whole file), and the port of the new measurement functions to
pulseq-reports.

## 2. Context (verified on 2026-10-01, `main` at `70f600e`)

### 2.1 The gradient measurement

1. `grad_limits.gradient_limits` gives one value for each axis (peak
   amplitude and peak slew) and the peak of |G|, each with its block and
   time. It does not keep a value for each block.
2. `_event_values` computes, for each unique gradient event (`K` events):
   `peak` and `peak_offset` (the largest |amplitude| of its corner points and
   its time from the block start), `slew` and `slew_offset` (the largest
   slope of a segment and the start of that segment), and `first` and `last`
   (the first and the last corner value). Units: Hz/m, Hz/m/s, s.
3. `SequenceIndex.gx`, `gy`, `gz` give the dense event index of each block
   on each axis (0: no event). Thus `ev.peak[col - 1]` is the peak of each
   block on that axis, with NumPy and no loop over the blocks. The same is
   true for `slew`.
4. `_range_result` computes the junction step of each block on each axis as
   an array: `|last of the previous block - first of this block| /
   seq.grad_raster_time` (0 before the first block, and 0 for a block without
   an event on the axis). The junction is at the start of the block.
5. The peak of |G| is computed one time for each distinct triple
   `(gx, gy, gz)` (`_triple_vector_peak`, from the corner points of the three
   events). `np.unique(..., return_inverse=True)` maps each block to its
   triple.
6. `checks/gradient.py` converts with the gamma of the target (#30) and
   passes when `value <= limit * (1 + 1e-9)` (`_LIMIT_TOLERANCE`). The three
   checks share the measurement `"gradient_limits"` of `ctx.measure`.
7. The three gradient checks are in the cost class `fast`. Their time is in
   the budget of decision 7 (10 s for 10⁶ blocks, `scripts/budget.py`) and in
   `tests/test_budget.py` (3.3 s for 10⁵ blocks, the fast checks together).
   Neither measures a file that fails the gradient checks in many blocks.
8. `grad_limits.py` is shared with pulseq-reports (`TODO.md`, the port).
   A change must keep each existing output.

### 2.2 The PNS measurement

1. `pns_levels.pns_levels` runs the SAFE model in chunks of about 30 000
   samples (`CHUNK_SAMPLES`). In the loop it has `total`, the SAFE total of
   each sample of the chunk (1 is the stimulation limit). It keeps only the
   minimum and maximum of each bin, the peak, the axis peaks, and the start
   state and maximum of each chunk.
2. The sample `k` is at the time `(k + 0.5) * dt`, with
   `dt = seq.grad_raster_time`.
3. `pns.safe` fails when `peak >= 1` (it passes when `peak < 1`). Its
   location is the block of `peak_time_s` (`np.searchsorted` on
   `index.start_s`).
4. `pns_levels_for` keeps the result for each sequence and hardware.
   `pns_levels.py` is shared with pulseq-reports, as `grad_limits.py` is.

### 2.3 Size

A file that is above the limit is usually above it in many blocks: each TR
of a sequence that repeats a gradient above the limit gives one finding for
each block and axis. For 10⁶ blocks, the gradient checks can give 10⁶
findings or more. `--max-findings` and `with_max_findings` limit them
(`docs/usage.md`, section 6).

## 3. Design

### 3.1 The values of each block (`grad_limits.py`)

A new public function, `block_gradient_values(seq, *, gamma=GAMMA)`, gives a
new frozen dataclass `BlockGradientValues`, with one entry for each block in
play order:

| Field | Meaning |
|---|---|
| `block_id`, `start_s` | From `sequence_index`. |
| `peak_mt_per_m[axis]` | The largest \|amplitude\| of the block on the axis (0 without an event). |
| `peak_time_s[axis]` | The time of that peak, from the sequence start. |
| `slew_t_per_m_per_s[axis]` | The largest slope of a segment of the block on the axis. |
| `slew_time_s[axis]` | The start of that segment. |
| `junction_t_per_m_per_s[axis]` | The step at the start of the block, divided by `seq.grad_raster_time`. |
| `vector_peak_mt_per_m`, `vector_peak_time_s` | The peak of \|G\| in the block, and its time. |

- It uses `sequence_index`, `_event_values`, the junction rule of
  `_range_result` and `_triple_vector_peak`, with NumPy over the blocks. It
  does not read a block with `get_block`.
- `gradient_limits` does not change. A test makes sure that the maximum of
  each field over the blocks equals the matching value of `gradient_limits`
  for the whole file, with the same block and time, on the synthetic and
  the scale sequences.
- It refuses the rotation extension (`refuse_rotations`), as
  `gradient_limits` does.

### 3.2 The findings of the gradient checks (`checks/gradient.py`)

- A check calls `ctx.measure("gradient_blocks", ...)` only when its result is
  a fail. A pass gives no findings and costs nothing more (section 2.1,
  item 7).
- A block above the limit: `value > limit * (1 + _LIMIT_TOLERANCE)`, the same
  rule as the state. Thus the worst finding is the value of the result.
- Order: the play order of the blocks, then the axes x, y, z, then (for the
  slew) the junction before the segment, because the junction is at the
  start of the block.

| Check | Code | Location | `data` |
|---|---|---|---|
| `gradient.amplitude.axis` | `AMPLITUDE_ABOVE_LIMIT` | The block, the time of its peak on the axis | `axis`, `value_mt_per_m`, `limit_mt_per_m` |
| `gradient.slew.axis` | `SLEW_ABOVE_LIMIT` | The block, the start of the segment | `axis`, `value_t_per_m_per_s`, `limit_t_per_m_per_s` |
| `gradient.slew.axis` | `JUNCTION_SLEW_ABOVE_LIMIT` | The block after the junction, its start time | `axis`, `value_t_per_m_per_s`, `limit_t_per_m_per_s` |
| `gradient.amplitude.any-orientation` | `VECTOR_AMPLITUDE_ABOVE_LIMIT` | The block, the time of its peak of \|G\| | `value_mt_per_m`, `limit_mt_per_m` |

- The message gives the axis, the value and the limit with their units, for
  example `"axis y: 103.2 mT/m, limit 80 mT/m"`.
- Each specification gets its `findings` text.
- The new measurement name `"gradient_blocks"` goes into the table of
  measurement names of `docs/usage.md`, section 7.

### 3.3 The intervals of `pns.safe` (`pns_levels.py`, `checks/pns.py`)

- `pns_levels` finds the intervals in its existing chunk loop: the runs of
  consecutive samples with `total >= 1`. A run that goes across the end of a
  chunk continues in the next chunk. For each run it keeps the first and the
  last sample, the largest total and its first sample. This needs no second
  pass over the samples, and the memory is a few numbers for each interval.
- `PnsLevels` gets a new field `above_limit` (a tuple of these intervals,
  default `()`), so each existing output stays the same.
- `pns.safe` gives one finding for each interval, in time order:

| Code | Location | `data` |
|---|---|---|
| `PNS_ABOVE_LIMIT` | The block of the first sample, the time of the first sample | `start_s`, `end_s` (the times of the first and the last sample), `peak_percent`, `peak_time_s` |

- The message: `"PNS at or above 100 % from 0.0123 s to 0.0125 s, peak 104.2 %"`.
- The specification gets its `findings` text.

## 4. Tests

### Phase 1 (gradient)

- `tests/test_grad_limits.py`: `block_gradient_values` against
  `gradient_limits` (section 3.1), on the synthetic and the scale sequences;
  a block without an event on an axis gives 0; the junction step of the
  first block uses 0 before it; the rotation extension is refused.
- `tests/test_check_gradient.py`: for each check, a pass has no findings; a
  fail has one finding for each block (and axis) above the limit, in order,
  with the codes, locations and data of section 3.2; a block at the limit
  within the tolerance gives no finding; the worst finding equals the result
  value; a junction step and a segment in the same block give two slew
  findings, the junction first; the spec has its `findings` text and version
  1.
- `TESTS.md`: the new tests.

### Phase 2 (PNS)

- `tests/test_pns_levels.py`: the intervals do not depend on the chunk size
  (a run across a chunk end is one interval); a sequence below the limit has
  none; the largest interval peak equals `peak`.
- `tests/test_check_pns.py`: a pass has no findings; a fail has one finding
  for each interval, with its location and data; the spec has its
  `findings` text and version 1.
- `TESTS.md`: the new tests.

## 5. Decisions (approved by the user on 2026-10-01)

The user approved the recommended answer of each decision. Do not open these
decisions again. The alternatives stay here as a record.

| # | Decision | Answer | Alternative (not chosen) |
|---|---|---|---|
| G1 | What one gradient finding is | One for each block and axis above the limit (section 3.2). The user sees each place in the file. | One for each unique gradient event above the limit (fewer findings, but one event can play in many blocks), or one for each run of consecutive blocks. |
| G2 | The junction step of the slew check | Its own code, `JUNCTION_SLEW_ABOVE_LIMIT`, at the start of the block. | One slew finding for each block and axis: the larger of the segment and the junction. |
| G3 | Where the values of each block come from | A new function `block_gradient_values` (section 3.1), called only for a fail. `gradient_limits` does not change. | Add the arrays to `gradient_limits` (every call pays for them, also a pass and pulseq-reports). |
| P1 | The PNS intervals | Exact: the samples with total `>= 1`, found in the chunk loop of `pns_levels` (section 3.3). | The bins of `level_max` (no change to `pns_levels`, but the interval ends are rounded to a bin of about 6 ms). |
| P2 | The PRs | Two: phase 1 (gradient), then phase 2 (PNS). | One PR. |

## 6. How to execute this plan

The workflow of `docs/plans/check-findings.md`, section 6: one branch and
one PR for each phase, from `origin/main`, in `.worktrees/<short-name>`;
`nix develop --command scripts/check` before each PR; the commit message is
approved before `git commit`.

| Phase | Branch | Files |
|---|---|---|
| 1 | `feature/gradient-findings` | `grad_limits.py`, `checks/gradient.py`, `tests/test_grad_limits.py`, `tests/test_check_gradient.py`, `TESTS.md`, `docs/checks.md` (made again), `docs/usage.md`, `README.md`, `TODO.md`, `CHANGELOG.md`, this plan (status) |
| 2 | `feature/pns-findings` | `pns_levels.py`, `checks/pns.py`, `tests/test_pns_levels.py`, `tests/test_check_pns.py`, `TESTS.md`, `docs/checks.md`, `docs/usage.md`, `README.md`, `TODO.md`, `CHANGELOG.md`, this plan (status and results) |

Each phase also:

1. Measures, on 10⁶ blocks (`build_repeating(200000)`), the time of its
   checks on a file that passes and on a file that fails in each TR, before
   and after, and the number of findings and the JSON size. The results go
   into section 7. If the time of a passing file changes by more than 5 %,
   or the fast checks together on the failing file take more than the budget
   of decision 7 (10 s), stop and ask the user.
2. Changes the docs that say which checks give findings (`docs/usage.md`
   sections 1 and 8, `README.md`, `TODO.md`).

## 7. Results

Empty until phase 1.
