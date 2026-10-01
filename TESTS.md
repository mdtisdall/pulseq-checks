# Tests

This file describes each check that CI runs. CI runs `scripts/check` in the
`ci` Nix devShell on every pull request and on every push to `main`. The `ci`
devShell has only the tools that `scripts/check` uses. Run the same checks
locally with:

```bash
nix develop --command scripts/check
```

Each check below has:

- **Checks:** one statement of what the check makes sure of.
- **How:** the logic of the check, in words.
- **Assumptions:** what the check takes as true without testing it, and what
  it does not cover. A check can pass while one of its assumptions is false.

When you add, remove or change a test, update this file in the same pull
request. CI fails when a test has no entry here (see
[TESTS.md coverage](#testsmd-coverage)).

Terms used below:

- **Synthetic sequences** are the small sequences in `tests/synthetic.py`,
  built with pypulseq only. They use the system limits 28 mT/m and
  150 T/m/s, RF dead time 100 µs, RF ringdown 20 µs and ADC dead time 10 µs.

Contents:

1. [Static checks](#1-static-checks)
2. [Tests](#2-tests): the package; the shared sequence helpers, the sequence
   index, the raster sampler and the sequence extensions; the analyses (PNS and
   the PNS levels, and the gradient limits); the target profile, the results,
   the run function and the check configuration; the Siemens `.asc` profile
   reader; the version 1 checks (timing, gradient and PNS); the command; the
   time budget

---

## 1. Static checks

### Dependency install

**Checks:** The locked dependencies install.

**How:** uv installs the project and its dependencies at the exact versions in
`uv.lock`, into the project environment. Every later step uses this
environment.

**Assumptions:**

- The install uses `--frozen`, which reads `uv.lock` and does not compare it to
  `pyproject.toml`. CI does not fail when `pyproject.toml` has a dependency
  change that is not in `uv.lock`.
- The Python version is the one from the Nix devShell (3.12). No other version
  is tested.

### Lint

**Checks:** The Python code has no findings from the rules that ruff turns on
by default.

**How:** ruff checks every Python file in the repository. The project sets
only the line length (100), so ruff uses its default rule set. `uv.lock` has
ruff 0.16.9.

**Assumptions:**

- The rule set is ruff's default, not a choice that the project makes. The
  project does not pin ruff in `pyproject.toml`, so an update of ruff in
  `uv.lock` can add or remove rules.
- Some common rules are not in the default set, so ruff does not report them:
  line length (E501), function complexity (C901), `print` calls (T201),
  `assert` statements (S101), too many arguments (PLR0913) and magic numbers
  (PLR2004). The format check wraps most long lines of code, but it does not
  split long strings or comments, so a line can still be longer than 100.
- ruff does not check types. No type checker runs in CI.

### Format

**Checks:** The Python code is formatted as ruff format would format it.

**How:** ruff format runs in check mode. It fails when any file would change.
The line length is 100.

**Assumptions:** None.

### Shell scripts

**Checks:** The shell scripts have no shellcheck warnings or errors.

**How:** shellcheck runs on `scripts/check` and the hook
`.claude/hooks/block-main-writes.sh`, at severity warning and above.

**Assumptions:**

- Only these two files are checked. A new shell script is not checked until
  it is added to the list in `scripts/check`.
- Info and style findings do not fail the check.

### TESTS.md coverage

**Checks:** TESTS.md has exactly one entry for each test that pytest collects,
in the section of that test's file, and no entry for a test that does not
exist.

**How:** In `scripts/check`, the pytest run writes the ID of each test that
it collects to a temporary file (option `--collected-tests-file`, from
`tests/conftest.py`), and the check reads that file (option `--collected`).
When the check runs alone, without `--collected`, it runs
`pytest --collect-only`, which lists the tests without running them. Each
pytest test is identified by its file name and its function name. A
parametrized test is one test. The check also reads each file that matches
`tests/js/test_*.js` as a file of JavaScript tests. This repository has no
JavaScript tests, so the check finds none. The check reads TESTS.md and takes
each level-4 heading that is a test name in backticks as an entry. The entry
belongs to the test file named in the nearest level-3 heading above it. The
check then reports:

- each pytest test with no entry in its file's section;
- each entry for a test that does not exist in that file;
- each test with more than one entry;
- each entry that is not under a test file's heading.

It fails if it reports anything, if pytest cannot collect the tests, or if it
cannot read the file of test IDs.

**Assumptions:**

- In `scripts/check`, the check runs after pytest, although this file lists
  it before the tests. When a test fails, `scripts/check` stops, and the
  check does not run.
- In `scripts/check`, pytest runs on the `tests` directory without other
  test selection (no `-k`), so the file of test IDs lists every test.
- Test files are identified by file name only, without the directory. The
  check fails if two test files have the same name.
- The check looks only at the headings. It does not check that an entry has
  its Checks, How and Assumptions parts, or that the text is still correct
  after a test changes.
- A level-4 heading that is not a test name in backticks (for example a
  description of shared test sequences) is not an entry and is ignored.

### Check documents

**Checks:** `docs/checks.md` is the file that `scripts/check_docs.py` writes
from the specifications of the checks of this package.

**How:** `scripts/check_docs.py --check` loads the check entry points of the
distribution `pulseq-checks`, makes the text of `docs/checks.md` from their
`CheckSpec` data, and compares it with the file. It exits 1 and names the
file when they differ. It also fails when the GitHub anchor of the heading of
a check (the ID in backticks) is not the anchor that `spec_url` gives for that
check.

**Assumptions:**

- Only the checks of this package are in the file. A plugin documents its own
  checks.
- The anchor rule is GitHub's (lower case, punctuation removed except `-`).
  The script does not test how another site makes anchors.
- The check compares text. It does not check that the text of a specification
  is true.

---

## 2. Tests

### 2.0 The package (`test_package.py`)

`test_package.py` tests that the package installs and imports, and that the
installed package has the version that `pyproject.toml` gives.

#### `test_the_package_imports_and_has_the_version_of_pyproject`

**Checks:** The package `pulseq_checks` imports from `src/pulseq_checks` of
this repository, and the installed distribution `pulseq-checks` has the
version that `pyproject.toml` gives in `[project]`.

**How:** The test imports `pulseq_checks` and compares the directory of the
imported package with `src/pulseq_checks` of the repository root. It reads `pyproject.toml` from the
repository root with `tomllib` and takes the value of `[project] version`. It
asks `importlib.metadata` for the version of the distribution `pulseq-checks`
and compares the two versions.

**Assumptions:**

- The metadata of the distribution `pulseq-checks` is the metadata of the
  editable install that `uv sync` makes. The test does not check where the
  metadata comes from.
- The version in the installed metadata is the version from the time of the
  last `uv sync`. After a change to the version in `pyproject.toml`, the test
  fails until `uv sync` runs again.

### 2.1 Shared sequence helpers (`test_seq_utils.py`)

`test_seq_utils.py` tests the shared helpers in `seq_utils.py` that the
report cards use to read a pypulseq sequence: the RF resampling helper and
the gradient corner/sample helper. It also checks that the synthetic
sequences in `tests/synthetic.py` are legal Pulseq.

#### `test_gamma_and_time_tolerance`

**Checks:** The gyromagnetic ratio is 42.576 MHz/T and the time tolerance is
1 ns.

**How:** The test compares the two shared constants with these values.

**Assumptions:** None.

#### `test_hold_samples_keeps_uniform_shapes_unchanged`

**Checks:** An RF shape with uniform samples that fill the pulse duration is
used as it is.

**How:** The test makes a 3 ms sinc pulse. It checks that the sample times
are uniform and that the number of samples times the step is the pulse
duration. It then gets the held samples, and checks that the sample time and
the sample values are the same as the pulse's own.

**Assumptions:**

- pypulseq's sinc pulse has uniform samples that fill its duration. The test
  checks that before it tests the helper.

#### `test_hold_samples_interpolates_a_block_pulse`

**Checks:** A block pulse, which has samples only at its start and end, is
resampled on the RF raster with the correct number of samples, the correct
duration, and the correct flip angle.

**How:** The test makes a 2 ms, 60° block pulse. It checks that the pulse has
only two samples, which do not fill the duration. It gets the held samples on
the RF raster, and checks that the number of samples is the duration divided
by the raster, that the samples fill the duration, and that the sum of the
samples times the sample time is 60° as a fraction of a cycle (1/6).

**Assumptions:**

- The flip angle in cycles is the sum of B1 (Hz) × dt, which is correct for a
  pulse with constant phase.

#### `test_gradient_offsets_trapezoid`

**Checks:** `gradient_offsets` gives the delay and the four corner offsets and
amplitudes of a trapezoid gradient, with the offsets relative to the delay
(not including it).

**How:** The test makes an x trapezoid and calls `gradient_offsets`. It
compares the returned delay with the gradient's own `delay`, the returned
offsets with the running sum of the rise time, the flat time and the fall
time (starting at zero), and the returned amplitudes with zero, the plateau
amplitude twice, and zero.

**Assumptions:** None.

#### `test_gradient_offsets_arbitrary`

**Checks:** `gradient_offsets` gives the delay and the sample offsets and
amplitudes of an arbitrary gradient, with one added point at each end, at
offset 0.0 and at the shape duration, for the shape's `first` and `last`
values.

**How:** The test makes an x arbitrary gradient from a 10-point waveform and
calls `gradient_offsets`. It checks
that the first and last returned amplitudes are the gradient's `first` and
`last` values, and that the first and last returned offsets are 0.0 and the
shape duration. It checks that the interior offsets and amplitudes are the
gradient's own sample times (`g.tt`) and waveform, unchanged.

**Assumptions:**

- pypulseq's `make_arbitrary_grad` gives the shape both `first` and
  `shape_dur` by default. The test checks that before it tests the helper,
  so the case without them (used only for a shape that already has points at
  its own ends) is not covered here.

#### `test_gradient_points_matches_gradient_offsets_exactly`

**Checks:** `gradient_points(g, t0)` gives exactly `(t0 + delay) + offsets`
for the `delay` and `offsets` that `gradient_offsets(g)` returns, for both a
trapezoid and an arbitrary gradient. This is the relationship a later phase
depends on to rebuild point times from the stored offset tables.

**How:** The test is parametrized over a trapezoid and an arbitrary
gradient. For each, it calls `gradient_points` with a non-zero `t0` and
`gradient_offsets` on the same event, then compares the two with
`numpy.testing.assert_array_equal` — exact equality, not a tolerance.

**Assumptions:**

- Bit-for-bit equality is the right check here, not an approximation: the
  point in this test is that `gradient_points` is defined in terms of
  `gradient_offsets` with no room for a rounding difference to creep in.

#### `test_gradient_points_trapezoid`

**Checks:** `gradient_points` gives the four corner times and amplitudes of a
trapezoid gradient.

**How:** The test makes an x trapezoid and calls `gradient_points` with a
start time `t0`. It compares the returned times with `t0` plus the
gradient's delay plus the running sum of the rise time, the flat time and
the fall time, and compares the returned amplitudes with zero, the plateau
amplitude twice, and zero.

**Assumptions:** None.

#### `test_gradient_points_arbitrary`

**Checks:** `gradient_points` gives the sample times and amplitudes of an
arbitrary gradient, with one added point at each end for the shape's first
and last values.

**How:** The test makes an x arbitrary gradient from a 10-point waveform and
calls `gradient_points` with a start time `t0`. It checks that the first and
last returned amplitudes are the gradient's `first` and `last` values, and
that the first and last returned times are `t0` plus the delay, and `t0`
plus the delay plus the shape duration. It checks that the interior points
are the waveform samples unchanged, at `t0` plus the delay plus the
gradient's own sample times (`g.tt`).

**Assumptions:** None.

#### `test_synthetic_sequences_pass_the_timing_check`

**Checks:** Each synthetic sequence builder in `tests/synthetic.py` passes
pypulseq's timing check.

**How:** The test runs once for each of four builders — `spin_echo_sequence`,
`gre_sequence`, `empty_sequence` and `arbitrary_gradient_sequence` — builds
the sequence, calls its `check_timing` method, and asserts that the check
passes, showing the report if it does not.

**Assumptions:**

- pypulseq's timing check is trusted to cover raster alignment, RF dead time
  and ringdown, and ADC dead time before and after the ADC. This test does
  not check the report cards' own reading of the sequence, only that the
  synthetic sequences are legal Pulseq.

### 2.2 PNS levels (`test_pns_levels.py`)

`test_pns_levels.py` tests `pns_levels.py` (`docs/plans/diagram-lanes.md`, section
4.1, item 2, and section 4.2): `pns_levels`, which samples the gradients block by
block (`GradientSampler.block_samples`), runs the SAFE model of the pinned pypulseq
fork (`_safe_gwf_to_pns_chunk`) over them in chunks, and keeps only the stored level
(the minimum and the maximum of the total in fixed time bins) and the summary (the
peak, the peak time and the axis peaks); and `bin_samples_for`, which picks the bin
size. The reference for most tests is `seq.calculate_pns` of the pinned fork
(decision 6 of section 2.2 of the plan: this project does not test pypulseq itself,
only compares this library's output with pypulseq's or with its own other output).
`calc_pns` samples `seq.get_gradients()` at the file times `(k + 0.5) * dt`, which
drift off the ideal raster grid by float rounding of the block start time sums
(section 2.3, item 1, of the plan); `pns_levels` samples each block at its own local
raster times, with no such drift. Both then run the same chunk function, so a
relative 1e-6-of-peak tolerance (section 3.5, item 2, of the plan) covers the whole
difference, except for a file with a block off the gradient raster, where both
sample at file times and a relative 1e-9 suffices.

`pns_levels` takes the hardware of the SAFE model from one of three sources: the
example hardware (`safe_example_hw()`, with no argument), a gradient `.asc` file
(`gradient_asc`), or a pair `(struct, label)` (`hardware`), where `struct` is a SAFE
hardware struct in the form of pypulseq's `asc_to_hw`. The last tests of this section
check the `hardware` keyword against the other two sources, and `SAFE_MODEL` (the
model `pns.safe` of the target profile, which reads and checks the nine fields of each
axis) and `hw_from_dict` (the struct of a checked dict). They compare the results
exactly: the same struct values give the same float operations.

#### `test_summary_matches_calculate_pns_within_the_fork_tolerance`

**Checks:** For a spin echo, a gradient echo, an arbitrary gradient, and a
hand-made "border" sequence (two extended-trapezoid blocks whose gradient is not
zero at the block border between them), `pns_levels`'s peak, peak time and axis
peaks equal `seq.calculate_pns`'s (example hardware) within a relative 1e-6 of the
peak. Also checks `reason`, `hardware`, `asc_file`, `dt_s` and `on_raster` for the
example-hardware, on-raster case.

**How:** Parametrized over `spin_echo_sequence()`, `gre_sequence()`,
`arbitrary_gradient_sequence()` and `synthetic.border_sequence()` (two
`pp.make_extended_trapezoid` blocks on x, the second continuing the first's
amplitude with no step, so `add_block` accepts the junction). The reference peak,
peak time (the first sample at or above `peak * (1 - PEAK_TOLERANCE)`, as
`PnsPrediction.peak_time_s`) and axis peaks come from
`seq.calculate_pns(safe_example_hw(), do_plots=False)`. `pns_levels(seq)`'s fields
are compared with `pytest.approx`: the
peak and axis peaks with `abs = 1e-6 * ref_peak`, the peak time with `abs = 1e-9`
(both use the same `(k + 0.5) * dt` formula, so the same sample index gives the same
float).

**Assumptions:** None of these sequences has two samples close enough together, in
value, to flip which one the tolerance-based peak-time search finds first.

#### `test_stored_bins_match_calculate_pns_totals`

**Checks:** Each stored bin's minimum and maximum equal the minimum and the maximum
of `seq.calculate_pns`'s totals over the same samples, within the same 1e-6-of-peak
tolerance, for the same four sequences.

**How:** Same parametrization and reference call as
`test_summary_matches_calculate_pns_within_the_fork_tolerance`. For each bin `i` of
`pns_levels(seq)`, `s0 = i * bin_samples`, `s1 = min(s0 + bin_samples,
levels.num_samples)` (the last bin can be shorter); the loop stops before a bin
whose `s1` is past the end of `calc_pns`'s own array (shorter than `pns_levels`'s
when a trailing block has no gradient event, for example `gre_sequence`'s TR
padding: `pns_levels` keeps sampling into the filters' own decay past where
`calc_pns` stopped, so a bin that straddles that point is not comparable). Each
compared bin's `level_min[i]`/`level_max[i]` are checked against
`norm[s0:s1].min()`/`.max()` with `pytest.approx(abs = 1e-6 * levels.peak)`. Asserts
at least one bin was compared.

**Assumptions:** None.

#### `test_cast_outward_bounds_every_input_value`

**Checks:** `_cast_outward` (the float32 rounding that keeps every bin's minimum and
maximum outside the float64 samples it was built from) never lands on the wrong
side of its input: the downward cast is at most the input, the upward cast is at
least the input.

**How:** 2000 uniform random float64 values in `[-1000, 1000)`
(`numpy.random.default_rng(0)`). Checks `_cast_outward(values,
down=True).astype(float64) <= values` and `_cast_outward(values,
down=False).astype(float64) >= values` elementwise, and that both results are
`float32`.

**Assumptions:** None of the 2000 values happens to already be exactly representable
in float32 for every one of them (which would make the nudging branch untested);
not arranged, only overwhelmingly likely for uniform random values.

#### `test_bin_samples_for_matches_the_formula`

**Checks:** `bin_samples_for` follows `max(floor(EXACT_MAX_S / (2 * DISPLAY_BINS) /
dt), ceil(num_samples / MAX_BINS), 1)`: 615 samples at the 10 us raster for any file
of up to 1,230,000,000 samples, and a coarser bin above that size or at a coarser
`dt`. A `pns_levels` call on a real sequence follows the same formula and gives that
many bins.

**How:** Direct calls: `bin_samples_for(0, 1e-5) == 615`,
`bin_samples_for(1_230_000_000, 1e-5) == 615`, `bin_samples_for(1_230_000_001, 1e-5)
== 616`, `bin_samples_for(2_000_000_000, 1e-5) == 1000`, `bin_samples_for(0, 2e-5) ==
307`. Then `pns_levels(gre_sequence(num_trs=6))`'s `bin_samples` is compared with
`bin_samples_for(levels.num_samples, levels.dt_s)`, and `len(levels.level_min) ==
len(levels.level_max)` equals the ceiling division of `num_samples` by
`bin_samples`.

**Assumptions:** None.

#### `test_result_does_not_depend_on_chunk_samples`

**Checks:** The stored level and the summary do not depend on the chunk size: exact
equality for chunks of 1, 2 and 7 bins and one chunk larger than the whole file.

**How:** `gre_sequence(num_trs=20)`, long enough that the smallest case (1 bin per
chunk) still has more than one chunk. `reference = pns_levels(seq)` (with the
`CHUNK_SAMPLES` of the module); then, for each size in `1`, `bin_samples + 1`,
`7 * bin_samples - 1` and `bin_samples * (num_samples // bin_samples + 10)`,
`monkeypatch.setattr` sets `CHUNK_SAMPLES` of `pulseq_reports.pns_levels` to it and
`pns_levels(seq)` runs again. `pns_levels` rounds the chunk up to a whole number of
bins, so the sizes give chunks of 1, 2 and 7 bins and one chunk bigger than the file.
`level_min`/`level_max` are compared with `numpy.array_equal`; `peak`, `peak_time_s`,
`axis_peaks`, `num_samples` and `bin_samples` with `==`.

**Assumptions:** None.

#### `test_no_gradients`

**Checks:** A sequence with no gradient event gives `reason=NO_GRADIENTS`, no
stored bins, a peak of 0, `peak_time_s` of `None`, zero axis peaks, and still the
example hardware and its `hw` fields.

**How:** `pns_levels(empty_sequence())`. Checks `reason`, `hardware`, `asc_file`,
the `(0,)` shape of `level_min`/`level_max`, `peak == 0.0`, `peak_time_s is None`,
`axis_peaks == {"x": 0.0, "y": 0.0, "z": 0.0}`, and `hw` against the 8 kept fields
of `safe_example_hw()`.

**Assumptions:** None.

#### `test_off_raster_block_falls_back_to_sampling`

**Checks:** A file with a block that is not on the gradient raster is reported as
`on_raster=False`, and its peak, peak time and axis peaks equal `seq.calculate_pns`
within a relative 1e-9 of the peak (tighter than the drift-based 1e-6 elsewhere in
this section, because both now sample with `GradientSampler.sample`/
`seq.get_gradients()` at the same file times; `test_sampling.py` established that
those two agree to about float rounding).

**How:** A trapezoid on x followed by `pp.make_delay(1.5 * dt)` (pypulseq's
`add_block` accepts this duration, though it is not a whole number of raster
steps). Compares `pns_levels(seq)`'s `on_raster`, `peak`, `peak_time_s` and
`axis_peaks` with the same-named values from `seq.calculate_pns(safe_example_hw(),
do_plots=False)`, as in `test_summary_matches_calculate_pns_within_the_fork_tolerance`
but with `abs = 1e-9 * ref_peak` (and `abs = 1e-9` for the peak time). It also checks
that `num_samples` is at least the length of `calculate_pns`'s result: `pns_levels`
covers the whole sequence, and `calc_pns` stops at the last gradient point.

**Assumptions:** None.

#### `test_asc_hardware_file_is_used_for_the_levels`

**Checks:** `pns_levels` reads the hardware name and the 8 kept fields of each axis
from a given gradient .asc file, instead of the example hardware, and its stored
level and summary then equal the default (example-hardware) call exactly, because
this .asc file encodes the example hardware's own numbers.

**How:** A local `write_gradient_asc` fixture (the technique of `test_pns.py`'s
fixture of the same name, not its confidential data: real .asc files are
confidential, so this one is built from pypulseq's own public
`safe_example_hw()`) writes an `asCOMP.tName` line and the `flGSWDTau*`,
`flGSWDA*`, `flGSWDStimulationLimit*`/`Threshold*` and `flGScaleFactor*` fields for
each axis. `pns_levels(spin_echo_sequence(), path)`'s `hardware`, `asc_file` and
`hw` are checked, then its `level_min`, `level_max`, `peak` and `peak_time_s` are
compared with a plain `pns_levels(seq)` call (`numpy.array_equal` for the arrays,
`==` for the scalars).

**Assumptions:** None.

#### `test_pns_levels_refuses_rotations`

**Checks:** `pns_levels` raises `NotImplementedError` for a sequence with a
rotation library, as `gradient_limits` does.

**How:** `gre_sequence(num_trs=2)` with a non-empty `rotation_library` (the
technique of `test_extensions.py`'s `_with_rotation_library`), inside
`pytest.raises(NotImplementedError, match="rotation extension")`.

**Assumptions:** None.

#### `test_pns_levels_is_a_frozen_dataclass`

**Checks:** `pns_levels` returns a `PnsLevels` instance.

**How:** `isinstance(pns_levels(spin_echo_sequence()), PnsLevels)`. A smoke test of
the interface; the other tests of this section check individual fields.

**Assumptions:** None.

#### `test_hardware_with_the_example_struct_gives_the_default_levels`

**Checks:** `pns_levels(seq, hardware=(safe_example_hw(), label))` gives the levels of
`pns_levels(seq)`, except `hardware`, which is the label: `asc_file` is None, and each
other field is exactly equal.

**How:** For `spin_echo_sequence()` (on the raster) and for a sequence with a block off
the raster, the test calls both and compares each field of the `PnsLevels` but
`hardware` (`numpy.array_equal` for the arrays, `==` for the rest).

**Assumptions:** None.

#### `test_hardware_from_an_asc_file_gives_the_levels_of_the_file`

**Checks:** `pns_levels(seq, hardware=(asc_to_hw(read_gradient_asc(path)), label))`
gives the levels of `pns_levels(seq, gradient_asc=path)`, except `hardware` (the label)
and `asc_file` (None).

**How:** The local `write_gradient_asc` fixture of this file writes the `.asc` file (the
plain layout; `test_pns.py` tests the layout of a scanner file). The test compares each
field but the two with `numpy.array_equal` and `==`.

**Assumptions:** None.

#### `test_pns_levels_refuses_both_gradient_asc_and_hardware`

**Checks:** `pns_levels` with `gradient_asc` and `hardware` together raises
`ValueError`.

**How:** `pns_levels(spin_echo_sequence(), gradient_asc=path, hardware=(safe_example_hw(),
"LABEL"))` inside `pytest.raises(ValueError, match="not both")`.

**Assumptions:** None.

#### `test_safe_model_reads_a_valid_dict`

**Checks:** `SAFE_MODEL` has the name `pns.safe` and the version 1. `SAFE_MODEL.read` of
a valid dict gives a new dict, with equal values, and each value is a float, also for an
int in the input. The `name` is optional.

**How:** The test builds the dict from `safe_example_hw()` (`name`, and for `x`, `y` and
`z` the nine fields) and compares `read(params)` with it (`==`, `is not` for the dict and
for one axis, `type(v) is float`). It then reads a dict without `name` (no `name` in the
result) and a dict with an int `stim_limit` (the float of it).

**Assumptions:** None.

#### `test_safe_model_refuses_an_unknown_key`

**Checks:** `SAFE_MODEL.read` raises `ValueError` for a key that is not `name`, `x`, `y`
or `z`, and for a field that is not one of the nine, and the message names the key with
its axis (`extra`, `z.tau4`).

**How:** Parametrized: a valid dict with the key `extra`, and a valid dict with the field
`tau4` in `z`. The test checks the message for `unknown key` and for the key.

**Assumptions:** None.

#### `test_safe_model_refuses_a_missing_field_or_axis`

**Checks:** `SAFE_MODEL.read` raises `ValueError` for a dict without one field of an
axis, or without an axis. The message names the key (`y.a2`, `z`).

**How:** The test deletes `a2` from `y` of a valid dict, then `z` from another, and
matches the message with `missing key`.

**Assumptions:** None.

#### `test_safe_model_refuses_a_value_that_is_not_a_real_number`

**Checks:** `SAFE_MODEL.read` raises `ValueError` that names the key (`x.tau2`) for a
field whose value is a bool (`True`, `False`), a str, `None`, a list, NaN or an infinity,
and for a `name` that is not a str.

**How:** Parametrized on the eight values, set as `x.tau2` in a valid dict. A second dict
has `name = 1`.

**Assumptions:** A bool is an int in Python. The model refuses it, so a TOML `true` is
not a number.

#### `test_hw_from_dict_gives_the_example_hardware`

**Checks:** `hw_from_dict(SAFE_MODEL.read(params))` for the example parameters has the
name and the 27 values of `safe_example_hw()`, its name is "unknown" when `params` has
no `name`, and, used as `hardware`, it gives exactly the levels of the example hardware,
except `hardware` (the label).

**How:** The test compares the name and each field of each axis with `==`, then compares
the levels of `spin_echo_sequence()` with `hardware=(hw, label)` with those of
`pns_levels(seq)`, as the first test of this list does.

**Assumptions:** None.

### 2.3 Sequence extensions (`test_extensions.py`)

`test_extensions.py` tests `extensions.refuse_rotations`, the guard that
`cards/spectrum.py`, `cards/pns.py` and `cards/gradient_limits.py` call
before they read any gradient. Task 6.1 of
`docs/plans/diagram-event-table.md` found that pypulseq 1.5.0.post1 cannot
make a rotation and that its `Sequence.read` raises `ValueError` for a
`.seq` file with a rotation section. This file therefore makes its own
rotation sequences by hand, the way pypulseq draft PR #372 stores a
rotation: a `rotation_library` event library on the `pp.Sequence`, a
`"ROTATIONS"` entry in `seq.extension_string_idx`, or, for the one test that
checks a `.seq` file directly, an `[EXTENSIONS]` section and an `extension
ROTATIONS` section written into the file text after `pp.Sequence.write`.

#### `test_refuse_rotations_accepts_synthetic_sequences`

**Checks:** `refuse_rotations` raises nothing for each synthetic sequence
builder in `tests/synthetic.py`: none of them uses the rotation extension.

**How:** The test is parametrized over `spin_echo_sequence`, `gre_sequence`,
`arbitrary_gradient_sequence` and `empty_sequence`. For each, it builds the
sequence and calls `refuse_rotations` on it.

**Assumptions:** None.

#### `test_refuse_rotations_raises_for_a_rotation_library`

**Checks:** `refuse_rotations` raises `NotImplementedError`, with "rotation
extension" in the message, for a sequence with a non-empty
`rotation_library`.

**How:** The test builds a `gre_sequence`, sets its `rotation_library` to a
new `EventLibrary` holding one scalar-first unit quaternion (the format PR
#372 uses), and calls `refuse_rotations` inside `pytest.raises`.

**Assumptions:** None.

#### `test_refuse_rotations_raises_for_a_rotations_extension_type`

**Checks:** `refuse_rotations` raises `NotImplementedError`, with "rotation
extension" in the message, for a sequence that has registered the
`"ROTATIONS"` extension type.

**How:** The test builds a `gre_sequence`, calls
`seq.set_extension_string_ID("ROTATIONS", 1)` (as PR #372's `Sequence.read`
does while reading a file with a rotation section), and calls
`refuse_rotations` inside `pytest.raises`.

**Assumptions:** None.

#### `test_refuse_rotations_ignores_an_empty_rotation_library`

**Checks:** A `rotation_library` attribute that exists but holds no data is
not a rotation: `refuse_rotations` raises nothing.

**How:** The test builds a `gre_sequence`, sets its `rotation_library` to a
new, empty `EventLibrary`, and calls `refuse_rotations` on it.

**Assumptions:** None.

### 2.4 Sequence index (`test_seq_index.py`)

`test_seq_index.py` tests `seq_index.py` (section 4.1 of
`docs/plans/cards-at-scale.md`): the dense RF, gradient and ADC event numbering of
`sequence_index`, its block times, its dtypes and its cache; `block_cache_off`; and
`rf_events`, `grad_events` and `adc_events`, which read each unique event one time with
the block cache off. The
reference numbering, `_reference_index`, is a plain loop over the blocks with one dict
for each event kind: the loop that `diagram_data.diagram_tables` had before it used the
index. Its `*_first` arrays hold play indexes, as `SequenceIndex` does (the old loop
kept block ids). The tests load `build_repeating` and `build_worst` from
`tests/scale_sequences.py`.

#### `test_dense_columns_and_first_arrays_match_the_reference_numbering`

**Checks:** `sequence_index`'s `rf`, `gx`, `gy`, `gz` and `adc` columns, `rf_first`,
`grad_first`, `grad_first_axis`, `adc_first` and `block_id` equal `_reference_index`'s,
for a synthetic spin echo, gradient echo, empty and arbitrary-gradient sequence, and
for `build_repeating`/`build_worst` at 50 TRs (250 blocks).

**How:** The test is parametrized over the four synthetic builders and two lambdas
wrapping `build_repeating(50)`/`build_worst(50)`. For each, it builds the sequence,
computes `sequence_index(seq)` and `_reference_index(seq)`, and compares every one of
those nine arrays with `numpy.array_equal` (the dense columns cast to `int64` first,
since `sequence_index` narrows their dtype while the reference always uses `int64`).

**Assumptions:** None.

#### `test_grad_dense_numbering_follows_gx_then_gy_then_gz_within_a_block`

**Checks:** The dense numbering of gradient events follows gx before gy before gz
within one block, and reusing an already-numbered event on a different axis of a later
block does not add a new dense index, with the expected numbers worked out by hand.

**How:** The test builds a 3-block sequence by hand: block 0 has only a gz trapezoid;
block 1 has a gx and a gy trapezoid, each a different amplitude; block 2 reuses block
0's gz trapezoid object (a shallow copy with its `channel` changed to `"x"`) on gx. It
checks `index.gx`, `gy`, `gz`, `grad_first` and `grad_first_axis` against the
hand-worked values, then checks that `grad_events` yields the three events in dense
order 1, 2, 3 with the expected amplitudes (1e5, 2e5, 3e5).

**Assumptions:**

- pypulseq's gradient library keys an event by its shape and amplitude data, not by
  the channel it is later read from, so the same trapezoid object can be reused on a
  different axis and keep the same library id. This was checked directly against
  `seq.block_events` and `seq.grad_library` while writing this test; the test itself
  then relies on it to make the hand-worked expected numbers correct.

#### `test_start_s_is_the_sequential_sum_and_end_s_is_its_final_value`

**Checks:** `index.start_s` is the sequential sum of the block durations from 0.0,
`index.end_s` is that sum's final value, and `index.duration_s` is
`seq.block_durations` in play order.

**How:** The test builds `build_repeating(50)`, computes `sequence_index(seq)`, and
independently walks `seq.block_events.keys()` with a running total `t` (starting at
0.0, recording `t` before adding each block's own duration from
`seq.block_durations`). It compares `index.start_s` to that running list with
`numpy.array_equal`, `index.end_s` to the final `t` with `==`, and `index.duration_s`
to a plain array of the `seq.block_durations` values in play order with
`numpy.array_equal`.

**Assumptions:** None.

#### `test_dtype_is_uint8_for_a_sequence_with_few_unique_events`

**Checks:** For a sequence with 255 or fewer unique events of each kind, every one of
`sequence_index`'s dense columns (`rf`, `gx`, `gy`, `gz`, `adc`) has dtype `uint8`.

**How:** The test builds `gre_sequence()` (the default 4 TRs), checks that
`rf_first`, `grad_first` and `adc_first` each have at most 255 entries, and checks the
dtype of each of the five dense columns.

**Assumptions:** None.

#### `test_dtype_widens_to_uint16_past_255_unique_gradient_events`

**Checks:** Once a sequence has more than 255 unique gradient events, `gx`, `gy` and
`gz` widen to `uint16`.

**How:** The test builds `build_repeating(260)`. `build_repeating`'s phase-encode
table has 256 amplitudes (`PE_STEPS`), so 260 TRs give more than 255 unique gradient
events overall (the phase-encode events, plus the readout and the spoiler, each reused
every TR). It checks that `grad_first` has more than 255 entries and that `gx`, `gy`
and `gz` have dtype `uint16`.

**Assumptions:**

- `build_repeating`'s phase-encode table size (`PE_STEPS = 256` in
  `tests/scale_sequences.py`) is large enough, on its own, to push the total past 255
  once combined with the readout and spoiler events; this is read from that script,
  not re-derived here.

#### `test_sequence_index_of_a_sequence_with_no_blocks`

**Checks:** `sequence_index` of a `pp.Sequence` with no blocks added has `num_blocks`
0, `end_s` 0.0, and every array (`block_id`, `start_s`, `duration_s`, `rf`, `gx`,
`gy`, `gz`, `adc`, `rf_first`, `grad_first`, `grad_first_axis`, `adc_first`) empty.

**How:** The test builds `pp.Sequence(SYSTEM)` with no `add_block` call, computes
`sequence_index(seq)`, and checks `num_blocks`, `end_s`, and the size of each of the
twelve arrays.

**Assumptions:** None.

#### `test_sequence_index_is_kept_for_one_sequence_object_and_rebuilt_after_add_block`

**Checks:** `sequence_index(seq)` returns the same object on a second call for the
same sequence, and a new, longer index after `add_block`.

**How:** The test builds `gre_sequence()`, calls `sequence_index(seq)` twice and
checks the two results are the same object (`is`), then calls
`seq.add_block(pp.make_delay(1e-3))` and checks that a third call returns a different
object whose `num_blocks` is one more than the first.

**Assumptions:** None.

#### `test_block_cache_off_restores_use_block_cache_true`

**Checks:** `block_cache_off` sets `use_block_cache` to `False` inside the block, and
restores it to `True` afterward when that was the value beforehand.

**How:** The test sets `seq.use_block_cache = True`, checks it is `False` inside
`block_cache_off`, and checks it is `True` again afterward.

**Assumptions:** None.

#### `test_block_cache_off_restores_use_block_cache_false`

**Checks:** `block_cache_off` sets `use_block_cache` to `False` inside the block, and
restores it to `False` afterward when that was already the value beforehand.

**How:** The test sets `seq.use_block_cache = False`, checks it is still `False`
inside `block_cache_off`, and checks it is `False` again afterward.

**Assumptions:** None.

#### `test_block_cache_off_restores_the_old_value_after_an_exception`

**Checks:** `block_cache_off` restores the old `use_block_cache` value even when an
exception is raised inside the block.

**How:** The test sets `seq.use_block_cache = True`, raises a `ValueError` inside
`block_cache_off` (after checking it reads `False` there), catches it with
`pytest.raises`, and checks `use_block_cache` is `True` again afterward.

**Assumptions:** None.

#### `test_block_cache_off_does_not_remove_blocks_already_in_the_cache`

**Checks:** `block_cache_off` does not remove a block that was already in
`seq.block_cache` before it ran.

**How:** The test builds `gre_sequence()`, calls `seq.get_block` on the first block id
to populate the cache, checks it is in `seq.block_cache`, runs an empty
`block_cache_off` block, and checks the block is still in `seq.block_cache` afterward.

**Assumptions:** None.

#### `test_rf_events_reads_each_unique_event_once_with_the_cache_off`

**Checks:** `rf_events` calls `seq.get_block` exactly once for each unique RF event,
with the block cache off during every call and restored afterward; it yields dense
indexes 1 to K in order; and each yielded event equals the same block's `rf` event
read separately.

**How:** The test builds `spin_echo_sequence()` (two distinct RF events), wraps
`seq.get_block` with a counting wrapper (monkeypatched onto the instance) that also
records `seq.use_block_cache` at each call, sets `seq.use_block_cache = True`, and
calls `rf_events(seq, index)`, collecting its results. It checks the call count
against the number of unique first-use blocks (`numpy.unique(index.rf_first).size`),
that every recorded cache flag is `False`, and that `use_block_cache` is `True` again
afterward. It checks the yielded dense indexes are 1 to K in order, and, for each
result, that its `delay`, `type` and `signal` equal the `rf` attribute of
`seq.get_block(block_id)` read again through the saved, unwrapped `get_block`.

**Assumptions:** None.

#### `test_grad_events_reads_each_unique_first_use_block_once_with_the_cache_off`

**Checks:** `grad_events` calls `seq.get_block` exactly once for each distinct
first-use block, not once for each unique gradient event, when two axes of one block
are both first uses; the block cache is off during every call and restored afterward;
the yielded dense indexes are 1 to K in order; and each yielded event equals the
corresponding axis attribute of that block, read separately.

**How:** The test builds a 3-block sequence where block 1 introduces both a gx and a
gy event (so it is the first-use block of two dense indexes at once), wraps
`seq.get_block` as in the RF test, and calls `grad_events(seq, index)`. It checks the
call count is 2 (the two distinct first-use blocks, not the three dense events), that
every recorded cache flag is `False`, and that `use_block_cache` is restored to
`True`. It checks the yielded dense indexes are 1, 2, 3 in order, and, for each, that
its `delay`, `type` and `amplitude` equal the `gx`/`gy`/`gz` attribute (picked by
`grad_first_axis`) of that block, read separately with the saved, unwrapped
`get_block`.

**Assumptions:** None.

#### `test_adc_events_reads_each_unique_event_once_with_the_cache_off`

**Checks:** `adc_events` calls `seq.get_block` exactly once for the sequence's one
unique ADC event (reused every TR), with the block cache off during the call and
restored afterward, and the yielded event equals that block's `adc` attribute read
separately.

**How:** The test builds `gre_sequence(num_trs=5)`, whose ADC event is the same
object reused every TR, and repeats the wrapper technique of the RF and gradient
tests. It checks the call count is 1, that the recorded cache flag is `False`, that
`use_block_cache` is restored to `True`, and that the yielded event's `delay`,
`num_samples` and `dwell` equal the `adc` attribute of that block read separately.

**Assumptions:** None.

### 2.5 Raster sampler (`test_sampling.py`)

`test_sampling.py` tests `sampling.py` (section 4.3 of
`docs/plans/cards-at-scale.md`): `GradientSampler`, which gives the gradient waveform of one axis at sorted times, from
the sequence index and the unique gradient events. The reference is pypulseq's
`seq.get_gradients()`: `_assert_matches_pypulseq` compares `sample(axis, t)` with the
`PPoly` of each axis at the same times, within a relative 1e-12 and an absolute 1e-12
times the largest |value| of the reference (section 3.5, item 2, of the plan). They are
not bit-exact: `seq_utils.gradient_offsets` adds a trapezoid's corner times in a
different order than pypulseq's `waveforms()`, and `PPoly` evaluates a line segment with
a different formula than `numpy.interp`. The comparison checks `GradientSampler`, not
pypulseq.

#### `test_whole_file_matches_pypulseq_for_synthetic_sequences`

**Checks:** For each of the four synthetic sequence builders (a spin echo, a gradient
echo, the arbitrary gradient, and the empty sequence), `GradientSampler.sample` gives
the same three-axis waveform as `seq.get_gradients()`, sampled at the raster centres
of the whole file.

**How:** Parametrized over `spin_echo_sequence()`, `gre_sequence()`,
`arbitrary_gradient_sequence()` and `empty_sequence()`. For each, `t` is
`(k + 0.5) * grad_raster_time` for `k` in `range(ceil(duration / raster))`, with
`duration` the sequence index's `end_s`; the test compares all three axes against
`seq.get_gradients()` with `_assert_matches_pypulseq`.

**Assumptions:**

- None of these raster-centre times falls within `get_gradients()`'s excluded 1e-12 s
  band around the first or last point of an axis (the `teps` zero points it adds); this
  was not arranged, only observed to hold for these four sequences.

#### `test_subrange_that_cuts_blocks_matches_pypulseq`

**Checks:** A sample range that starts in the middle of one block and ends in the
middle of another gives the same waveform as `seq.get_gradients()` on all three axes,
including an axis whose only event in the file is entirely before the range.

**How:** Builds `gre_sequence(num_trs=1)` (5 blocks: RF, phase-encode on y, readout on
x with an ADC, spoiler on z, delay). `t` is 500 evenly spaced points from the middle of
block 2 (the readout, which the range cuts) to the middle of block 4 (the delay, after
the spoiler); the phase-encode event of block 1 is entirely before this range, so it
also checks that gy is 0 for the rest of the file after its one event. Compares with
`_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_subrange_inside_a_gap_matches_pypulseq`

**Checks:** A sample range entirely inside a gap between two gradient events on the
same axis (a block with no event of its own) still gives the pypulseq value: a
straight line between the earlier event's last point and the later event's first
point.

**How:** Builds a trapezoid on x, a 2 ms delay block, and a second trapezoid on x. `t`
is 200 evenly spaced points strictly inside the delay block, 50 µs in from each edge.
Compares with `_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_single_sample_matches_pypulseq`

**Checks:** `sample` gives the pypulseq value for a `t` array of length 1.

**How:** Builds `gre_sequence(num_trs=1)`, samples at one time (the middle of the
readout block), and compares with `_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_amplitude_continues_across_a_block_junction`

**Checks:** Two extended trapezoids that together make one trapezoid, split into two
blocks at the middle of the flat top so the amplitude continues unchanged from one
block into the next, give the same waveform as `seq.get_gradients()` around the
junction: the join rule's dropped point does not create a spurious step.

**How:** `_junction_sequence(step_hz_per_m=0.0)` builds the two extended trapezoids
from the rise, flat and fall of one area-1000 trapezoid, split at the middle of the
flat top, and returns the junction time. `t` is 41 points evenly spaced over 40
gradient-raster periods centred on the junction. Compares with
`_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_tolerated_step_at_a_block_junction_matches_pypulseq`

**Checks:** A step at a block junction that is inside what pypulseq's `add_block`
accepts (up to `max_slew * grad_raster_time`) still gives the same waveform as
`seq.get_gradients()`: the join rule keeps the value of the earlier event at the
junction time even when the two events do not meet exactly.

**How:** Same construction as `test_amplitude_continues_across_a_block_junction`, with
`_junction_sequence`'s `step_hz_per_m` set to half of `max_slew * grad_raster_time`
instead of 0. The test does not check that `add_block` accepts the step; that is
pypulseq's own check, exercised here only because building the sequence requires it to
pass.

**Assumptions:** None.

#### `test_triangle_trapezoid_matches_pypulseq`

**Checks:** A trapezoid with no flat time (`make_trapezoid` gives `flat_time == 0.0`),
whose `gradient_offsets` therefore has two points at the same time with the same
value, gives the same waveform as `seq.get_gradients()`: the join rule's
duplicate-point removal does not change the value.

**How:** Builds a single-block sequence with one small-area trapezoid on x, asserts
`flat_time == 0.0` to confirm the construction is the intended triangle, samples the
whole file at the raster centres, and compares with `_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_sample_matches_the_added_events_for_an_oversampled_arbitrary_gradient`

**Checks:** `sample` gives the correct waveform for a file with an oversampled
arbitrary gradient (`make_arbitrary_grad(oversampling=True)`): B4 of
`docs/reviews/2026-09-28-code-review.md` (pypulseq issue #423), fixed by the project's
pypulseq pin (`pulseq-reports-pin-1`, the fix of pypulseq PR #424). The reference is not
`seq.get_gradients()`: pypulseq's `waveforms()` leaves out the first and the last point
of an oversampled gradient (a separate pypulseq bug, draft 03 of
`github.com/mdtisdall/pypulseq-issues`), so `_assert_matches_pypulseq`'s own reference
would be wrong for this event by construction, not only by the bug under test. The
reference is instead the polyline of the added events (the objects `make_*` returns,
before `add_block`), which does not depend on either pypulseq bug.

**How:** Builds three blocks with `SYSTEM` of `synthetic.py`: an oversampled ramp
(`make_arbitrary_grad("x", ..., oversampling=True)`, 21 samples at 50 % of `max_slew`
over half a raster, ending at a value that is not 0), an extended trapezoid back down to
0, and an ordinary trapezoid. The waveform is kept within the real `max_slew` by the
test itself, because `make_arbitrary_grad(oversampling=True)` checks the slew rate 4
times too leniently (pypulseq issue #421). The reference polyline is built from each
added event's own corner or sample points (`[0, *g.tt, g.shape_dur]` and `[g.first,
*g.waveform, g.last]` for the arbitrary and extended-trapezoid events, the rise/flat/fall
corners for the trapezoid), offset by each block's start (`numpy.cumsum` of
`seq.block_durations`) and the event's own delay, with a point dropped when it is not
more than 1e-9 s after the point before it (the same join rule as `GradientSampler`).
`GradientSampler.sample("gx", t)` is compared with `numpy.interp` on that polyline at
3999 points evenly spaced over the file, within an absolute 1e-12 times the peak of the
reference (`rtol=0`). Before the pin's fix, this test's own error is about 40 % of the
peak (checked against a pypulseq checkout at the old pin, `20b9e5e`).

**Assumptions:**

- The pin (`pulseq-reports-pin-1`) has the fix of pypulseq PR #424. A pypulseq without
  it fails this test: checked against a checkout of the old pin (`20b9e5e`).

#### `test_axis_without_events_is_zero`

**Checks:** An axis with no gradient event anywhere in the file (`get_gradients()`
gives `None` for it) samples to exactly 0 at every time.

**How:** Builds `spin_echo_sequence()` (gx and gy only), asserts
`seq.get_gradients()[2] is None` to document that gz has no event, samples gz at the
raster centres of the whole file, and checks the result against `numpy.zeros` with
`numpy.testing.assert_array_equal` (an exact check, not a tolerance).

**Assumptions:** None.

#### `test_zero_before_the_first_event_and_after_the_last`

**Checks:** The waveform is exactly 0 before the first gradient event of the file and
after the last one.

**How:** Builds a delay block, one trapezoid on x, and a second delay block. Samples
50 points inside the first delay block (before the event) and 50 points inside the
second delay block (after the event), and checks both against `numpy.zeros` exactly.

**Assumptions:** None.

#### `test_empty_sequence_is_zero_for_any_t`

**Checks:** A sequence with no gradient event on any axis gives exactly 0 for any `t`,
including a time past the sequence's own duration.

**How:** Builds `empty_sequence()` (one delay block; no RF, gradients or ADC). Samples
all three axes at `t = [0.0, 1e-3, 5.0]` (5.0 s is far past the sequence's 2 ms), and
checks each result against `numpy.zeros` exactly, with `dtype == float64`.

**Assumptions:** None.

#### `test_empty_times_gives_empty_output`

**Checks:** `sample` with an empty `t` returns an empty `float64` array, not an error.

**How:** Builds `gre_sequence(num_trs=1)`, calls `sample("gx", numpy.array([]))`, and
checks the result's dtype and shape.

**Assumptions:** None.

#### `test_invalid_axis_name_raises_value_error`

**Checks:** `sample` raises `ValueError` for an axis name other than "gx", "gy" or
"gz".

**How:** Builds `gre_sequence(num_trs=1)`, calls `sample("gw", ...)` inside
`pytest.raises(ValueError)`.

**Assumptions:** None.

The remaining tests of this section are for `GradientSampler.block_samples` and
`raster_block_lengths` (`docs/plans/diagram-lanes.md`, phase 2, task 2.0, section 4.1,
item 3): the PNS lane's per-block samples at the local times `(j + 0.5) * dt`, 0 before
a block's first gradient point and after its last, with no line across a gap and no
time drift from the block start sums. This is the rule of `PnsLanes` (`_eventSamples`
in `assets/pns_lanes.js`), not the rule of `sample`.

#### `test_block_samples_matches_sample_at_file_raster_times`

**Checks:** `block_samples` over all the blocks of a file agrees with `sample` at the
file times `(k + 0.5) * dt`, within 1e-9 of the largest |g| of the axis, for the
spin-echo, gradient-echo and arbitrary-gradient synthetic sequences.

**How:** Parametrized over `spin_echo_sequence()`, `gre_sequence()` and
`arbitrary_gradient_sequence()`. `raster_block_lengths(index, dt)` gives each block's
sample count and confirms the file is on the raster; `t_file` is `(k + 0.5) * dt` for
`k` in `range(total_samples)`. For each axis, `block_samples(axis, 0, num_blocks, dt)`
is compared with `sample(axis, t_file)` with `numpy.testing.assert_allclose`, `atol =
1e-9 * peak` and `rtol = 0`, `peak` the largest `|value|` of `sample`'s result. The two
are not exactly equal: `block_samples` computes each block's samples from its own local
raster grid, with no accumulated float error, while `sample` reads the waveform at the
block's actual start time (the sequential sum of the durations before it), which drifts
off the ideal raster grid by float rounding (`docs/plans/diagram-lanes.md`, section 2.3,
item 1). The difference is that drift only.

**Assumptions:** None.

#### `test_hand_made_ramp_and_no_event_block`

**Checks:** `block_samples` gives the exact values of a hand-made sequence: a gradient
that ramps to a nonzero value and stops there (unlike an ordinary trapezoid, whose
event is 0 at both ends), inside a block longer than the ramp, and a later block with
no gradient event on any axis.

**How:** Builds a two-block sequence: block 0 has `pp.make_extended_trapezoid` on x,
ramping from 0 to `amp = 1000.0` Hz/m over `n_ramp = 4` raster steps, and
`pp.make_trapezoid` on z with an explicit `duration` of `n_block = 7` raster steps (so
the block is longer than the x ramp); block 1 is `pp.make_delay(n_block * dt)`, with no
gradient event at all. The expected x samples of block 0 are computed by hand from the
linear-interpolation rule (`amp * t / rise` while `t` is before the ramp's own last
point, 0 after it) and compared with `numpy.testing.assert_allclose` (`rtol = atol =
1e-12`): a division (the same rule, computed by a different sequence of floating-point
operations) makes exact equality unlikely. gy, which has no event anywhere in the file,
and block 1's gx and gz, which have no event in that block, are checked against exact
zero with `numpy.testing.assert_array_equal`.

**Assumptions:** None.

#### `test_range_inside_the_file_equals_the_same_slice_of_the_whole_file`

**Checks:** `block_samples` for a range that starts and ends inside the file gives
exactly the same values as the matching slice of `block_samples` for the whole file.

**How:** Builds `gre_sequence(num_trs=3)`. `raster_block_lengths` gives each block's
sample count, used to find the sample offset and length of a block range `[2, num_blocks
- 1)`. For each axis, `block_samples(axis, 0, num_blocks, dt)` and `block_samples(axis,
2, num_blocks - 1, dt)` are compared with `numpy.array_equal` after slicing the whole-file
result to the same sample offset and length.

**Assumptions:** None.

#### `test_block_samples_invalid_axis_name_raises_value_error`

**Checks:** `block_samples` raises `ValueError` for an axis name other than "gx", "gy"
or "gz".

**How:** Builds `gre_sequence(num_trs=1)`, calls `block_samples("gw", 0, 1, dt)` inside
`pytest.raises(ValueError)`.

**Assumptions:** None.

#### `test_block_samples_bad_range_raises_value_error`

**Checks:** `block_samples` raises `ValueError` when `first`/`stop` are outside `0 <=
first <= stop <= num_blocks`: a negative `first`, a `first` greater than `stop`, and a
`stop` past the number of blocks.

**How:** Parametrized over `(first, stop) = (-1, 1)`, `(3, 1)` and `(0, 100)` on
`gre_sequence(num_trs=1)` (5 blocks), each inside `pytest.raises(ValueError)`.

**Assumptions:** None.

#### `test_block_samples_off_raster_block_raises_value_error`

**Checks:** `block_samples` raises `ValueError` for a block whose duration is not a
whole number of raster steps.

**How:** `pp.make_delay(1.5 * dt)` (pypulseq accepts this duration), the block's own
sequence, and `block_samples("gx", 0, 1, dt)` inside `pytest.raises(ValueError)`.

**Assumptions:** None.

#### `test_raster_block_lengths_with_different_block_lengths`

**Checks:** `raster_block_lengths` gives `round(duration / dt)` for each block of a
file whose blocks do not all have the same duration, and reports the file as on the
raster.

**How:** Builds `gre_sequence(num_trs=2)` (RF, phase-encode, readout, spoiler and delay
blocks, of different durations; confirmed with `len(set(index.duration_s.tolist())) >
1`). Compares `raster_block_lengths(index, dt)`'s `n` with `numpy.rint(index.duration_s
/ dt)` cast to `int64`, with `numpy.testing.assert_array_equal`, and checks `on_raster`
is `True`.

**Assumptions:** None.

#### `test_raster_block_lengths_detects_a_block_off_the_raster`

**Checks:** `raster_block_lengths` reports a file as not on the raster when one block's
duration is not within `ON_RASTER_TOLERANCE` samples of a whole number, while still
giving a sample count (the nearest whole number) for every block.

**How:** A two-block sequence: `pp.make_delay(2 * dt)`, then `pp.make_delay(1.5 *
dt)`. `raster_block_lengths(index, dt)` must give `on_raster = False` and `n =
[2, 2]` (`numpy.rint` rounds 1.5 to 2, ties-to-even).

**Assumptions:** None.

### 2.6 Gradient limits (`test_grad_limits.py`)

`test_grad_limits.py` tests `grad_limits.py`: the peak amplitude, the peak slew
rate and the RMS amplitude of a sequence's gradients, on each logical axis and
as a three-axis vector, over the whole sequence or over a window. Every
expected value is computed by hand from the parameters of the trapezoid or
arbitrary gradient that the test builds, not by calling `gradient_limits`
itself for the expected value.

Since phase 4 of `docs/plans/cards-at-scale.md`, `grad_limits.py` computes its values from
the per-event values of `seq_index.grad_events` and the columns of `seq_index.sequence_index`,
instead of reading every block with `get_block`, and its slew also includes the step at each
block junction (decision 6 of section 2.5 of that plan). The tests below the first group add:
the largest slew of an arbitrary gradient and of an extended trapezoid (computed from the
event's own corner points, the same way as the peak amplitude tests above), the credited block
for a value that several blocks and axes share, a window that keeps only part of a ramp's
slew, the vector peak of two blocks with different triples of active gradients, the three
junction-step cases of section 4.6 item 6, a window that starts inside a block after a
junction step, and comparisons with the oracle
(`tests/oracles/grad_limits.py`, the implementation from before phase 4).

#### `test_trapezoid_peak_slew_and_rms_match_hand_computed_values`

**Checks:** For a single x trapezoid, `gradient_limits` gives the peak
amplitude, the peak slew rate and the RMS amplitude that hand computation from
the trapezoid's own rise time, flat time and amplitude predicts.

**How:** The test builds one block with an x trapezoid of a given amplitude,
rise time and flat time, and calls `gradient_limits` on it. It computes the
expected peak as the amplitude in mT/m, the expected slew as the amplitude
divided by the rise time in T/m/s, and the expected RMS from the energy of the
two ramps (each `amplitude^2 * rise_time / 3`) plus the flat top
(`amplitude^2 * flat_time`), divided by the block's duration and square
rooted. It checks that the x axis result matches each expected value, that
`reason` is None, and that the peak and the slew are attributed to the
trapezoid's own block ID.

**Assumptions:**

- The trapezoid's `fall_time` equals its `rise_time`, which is
  `pp.make_trapezoid`'s default when only `rise_time` is given.

#### `test_same_trapezoid_on_x_and_y_gives_vector_peak_root_2_times_axis_peak`

**Checks:** The same trapezoid, played on x and on y at the same time, gives a
vector peak that is the axis peak times the square root of 2.

**How:** The test builds one block with the same trapezoid on x and on y, and
calls `gradient_limits`. Because Gx equals Gy at every point, `|G|` is
`sqrt(2)` times `|Gx|` at every point, and so at the peak. It checks that the
vector peak equals the x axis peak times `sqrt(2)`, and that the x and y axis
peaks are equal.

**Assumptions:** None.

#### `test_window_that_cuts_a_ramp_gives_hand_computed_rms`

**Checks:** A window that ends partway up a trapezoid's rising ramp gives an
RMS amplitude equal to the value hand-computed from the piece that the window
keeps, cut at the window edge.

**How:** The test builds one block with an x trapezoid and a window from 0 to
half the rise time. It computes the expected RMS from the one linear piece the
window keeps, from `(0, 0)` to `(rise_time / 2, amplitude / 2)`, with
`Delta t * (a^2 + a*b + b^2) / 3` divided by the window length. It checks that
`range_s` equals the window and that the x axis RMS matches.

**Assumptions:** None.

#### `test_arbitrary_gradient_peak_is_the_largest_of_first_last_and_waveform`

**Checks:** For an arbitrary gradient, the peak amplitude is the largest
absolute value among the shape's `first`, `last` and interior waveform
samples.

**How:** The test builds an x arbitrary gradient from an asymmetric sine-lobe
waveform, whose largest magnitude is not at the shape's first or last sample,
and calls `gradient_limits`. It computes the expected peak as the largest of
`abs(first)`, `abs(last)` and the largest absolute waveform sample, taken from
the block's own gradient event, converted to mT/m. It checks that the x axis
peak matches.

**Assumptions:**

- `seq_utils.gradient_points` adds `first` and `last` as extra points at the
  ends of an arbitrary gradient's shape (checked by `test_gradient_points_arbitrary`
  in `test_seq_utils.py`), so they can hold the largest magnitude even when
  every interior waveform sample is smaller.

#### `test_no_gradients_sets_reason`

**Checks:** A sequence with no gradient events at all gives a set `reason`,
and every numeric field is its zero value: 0.0 for an amplitude, slew or RMS
field, and None for a block field.

**How:** The test builds a sequence with one delay block and no gradients, and
calls `gradient_limits`. It checks that `reason` is
"no gradient events in the sequence", that the vector peak and its time are
0.0, and that every axis's peak, slew and RMS are 0.0 with `peak_block` and
`slew_block` both None.

**Assumptions:** None.

#### `test_default_limits_come_from_seq_system`

**Checks:** With `limits=None`, the limits are `seq.system.max_grad` and
`seq.system.max_slew`, converted to mT/m and T/m/s, with the label
"pypulseq system limits".

**How:** The test builds a sequence with one x trapezoid and calls
`gradient_limits` with no `limits` argument. It checks that the result's
`limits.label` is "pypulseq system limits", and that `max_grad_mt_per_m` and
`max_slew_t_per_m_per_s` equal `seq.system.max_grad` and `seq.system.max_slew`
converted with the gyromagnetic ratio, the same conversion the function itself
documents.

**Assumptions:**

- `seq.system.max_grad` and `seq.system.max_slew` are always in Hz/m and
  Hz/m/s, whatever unit was given to `pp.Opts`, because `pp.Opts` converts to
  Hz/m (respectively Hz/m/s) before it stores the value. This is a fact about
  pypulseq, not about the function under test, and is not itself checked here.

#### `test_arbitrary_gradient_max_slew_is_the_largest_neighbouring_slope`

**Checks:** The largest slew of an arbitrary gradient is the largest
`|delta g / delta t|` between its neighbouring corner points (the shape's
`first`, its waveform samples, and its `last`).

**How:** The test builds an x arbitrary gradient from an asymmetric sine-lobe
waveform and calls `gradient_limits`. It computes the expected slew from
`block.gx.first`, `block.gx.waveform`, `block.gx.last` and their own offset
and shape-duration fields (the same corner points `gradient_offsets` builds),
as the largest `|diff(amplitude) / diff(time)|`, not by calling
`gradient_limits` for the expected value. It checks that the x axis slew
matches.

**Assumptions:** None.

#### `test_extended_trapezoid_max_slew_is_the_largest_segment_slope`

**Checks:** The largest slew of an extended trapezoid is the largest
`|delta g / delta t|` between its neighbouring control points.

**How:** The test builds an x extended trapezoid from five explicit times and
amplitudes and calls `gradient_limits`. It computes the expected slew as the
largest `|diff(amplitudes) / diff(times)|` of the same arrays given to
`make_extended_trapezoid`. It checks that the x axis slew matches.

**Assumptions:** None.

#### `test_largest_over_several_blocks_and_axes_credits_the_first_block_with_that_value`

**Checks:** With several blocks on several axes, the peak amplitude and the
peak slew of each axis are the largest over every block with an event on that
axis, credited to the first block, in play order, whose event reaches that
value; a later block that repeats the very same event does not move the
credit.

**How:** The test builds four blocks: a small x trapezoid, a y trapezoid, a
larger x trapezoid, and the same larger x trapezoid again. It checks that the
x axis peak and slew equal the larger trapezoid's own amplitude and slew
(divided by its rise time), each credited to the third block (the first
block with that event, not the fourth), and that the y axis peak equals the y
trapezoid's amplitude.

**Assumptions:** None.

#### `test_window_that_cuts_a_ramp_gives_the_slew_of_the_part_inside_the_window`

**Checks:** A window that includes only part of an extended trapezoid, over a
segment with a smaller slope than another segment outside the window: the
slew over the window is the slope of the part inside the window, not the
largest slope of the whole event, and the slew time is the window start, where
the window cuts that segment.

**How:** The test builds an x extended trapezoid with four segments of
different slopes and a window that lies inside the two segments with the
smallest slopes, excluding the segment with the largest. It computes the
expected slew by hand from the times and amplitudes of the segment the window
keeps. It checks that the x axis slew matches, not the whole event's own
largest segment slope, and that `slew_time_s` is the window start (100 µs).

**Assumptions:** None.

#### `test_slew_time_is_the_start_of_the_steepest_segment`

**Checks:** The slew time of an axis is the start of its steepest segment.

**How:** The test builds one x extended trapezoid whose last segment (900 to
1100 µs) is its steepest. It checks that the x slew is that segment's slope,
computed by hand, and that `slew_time_s` is 900 µs.

**Assumptions:** None.

#### `test_vector_peak_of_g_compares_different_triples_across_blocks`

**Checks:** Two blocks with different triples of active gradients: the
vector peak of `|G|` is the largest magnitude found across the two different
triples, not just the largest single-axis peak, and the vector peak block and
time are those of the block that reaches it.

**How:** The test builds one block with a large x trapezoid alone, and a
second block with a smaller, equal-amplitude trapezoid on both x and y (whose
combined vector magnitude, `sqrt(2)` times the smaller amplitude, is larger
than the first block's lone peak). It checks that the vector peak equals the
hand-computed combined magnitude of the second block's triple, that
`vector_peak_block` is the second block, and that `vector_peak_time_s` is the
end of the second block's rise (1.0 ms, after the 0.8 ms of the first block).

**Assumptions:** None.

#### `test_junction_step_between_extended_trapezoids_is_reported_as_the_slew`

**Checks:** A step at the junction between two extended trapezoids, within
the tolerance that `add_block` accepts (`max_slew * grad_raster_time`) and
larger than any segment's own slope: the reported slew is the step divided
by `grad_raster_time`, credited to the block after the junction, at the time
of the junction.

**How:** The test builds two x extended trapezoids whose junction step is 90%
of the largest step `add_block` accepts, and whose own segment slopes are
smaller than that step. It computes the expected slew by hand as the step
divided by `grad_raster_time`. It checks that the x axis slew matches, is
credited to the second block, and that `slew_time_s` is the junction (0.2 ms).

**Assumptions:** None.

#### `test_junction_step_uses_the_gradient_raster_of_the_file_not_of_seq_system`

**Checks:** The step at a block junction is divided by the gradient raster of the
sequence, `seq.grad_raster_time` (the `GradientRasterTime` that the file declares),
not by `seq.system.grad_raster_time`. A sequence read from a file gives the same value
as the sequence object that wrote it.

**How:** `raster_4us_sequence` builds two y extended trapezoids with a 4 µs gradient
raster: the slopes are 40 and 39.4 T/m/s and the junction step is 0.24 mT/m, so the
junction is 60 T/m/s with 4 µs (24 T/m/s with 10 µs). The test writes the sequence to
a file in `tmp_path` and reads it with `pp.Sequence()`, whose `system` has 10 µs. For
the sequence that was read and for the sequence object, it checks that the y slew is
60 T/m/s, credited to the second block, at the junction (0.8 ms).

**Assumptions:** The file stores the amplitudes with fewer digits than the sequence
object, so the comparison has a relative tolerance of 1e-4.

#### `test_gradient_ending_non_zero_before_a_block_with_no_gradient_is_a_junction_step`

**Checks:** A gradient that ends at a non-zero value (within the tolerance
`add_block` accepts) right before a block with no gradient on that axis: the
junction step uses 0 for the block with no event, and is credited to that
block (the block after the junction).

**How:** The test builds an x extended trapezoid ending at 90% of the largest
step `add_block` accepts, followed by a delay block with no gradient. It
computes the expected slew by hand as that ending value divided by
`grad_raster_time`. It checks that the x axis slew matches and is credited to
the delay block.

**Assumptions:** None.

#### `test_first_block_not_starting_at_zero_is_a_junction_step_before_the_first_block`

**Checks:** A first block whose gradient starts at a non-zero value within
the tolerance `add_block` accepts: the junction before the first block uses 0
for "the block before" (there is none), and is credited to the first block.

**How:** The test builds a single x extended trapezoid starting at 90% of the
largest step `add_block` accepts. It computes the expected slew by hand as
that starting value divided by `grad_raster_time`. It checks that the x axis
slew matches and is credited to the first (only) block.

**Assumptions:** None.

#### `test_window_inside_a_block_with_no_gradient_ignores_the_junction_before_it`

**Checks:** A window entirely inside a block with no gradient, right after a gradient
event that ends at a non-zero value (within the tolerance `add_block` accepts) in the
block before: the window does not use the junction between the two blocks, because
that block starts before the window (`docs/plans/review-bugs.md`, B1, decision 14), so
the window has no gradient event and 0 slew. A window that starts exactly at that
junction still uses it.

**How:** The test builds an x extended trapezoid ending at 90% of the largest step
`add_block` accepts, followed by a delay block with no gradient. It calls
`gradient_limits` with a window from partway into the delay block to its end, and
checks that `reason` is "no gradient events in the window", the x slew is 0.0, and
`slew_block` is None. It then calls `gradient_limits` with a window that starts
exactly at the junction (the end of the trapezoid block) and checks that the x slew
equals the ending value divided by `grad_raster_time` and is credited to the delay
block.

**Assumptions:** None.

#### `test_window_that_cuts_a_block_credits_it_on_a_tie_with_a_later_block`

**Checks:** When a block that the window start cuts and a later block fully inside the
window reach the same peak and the same slew, both are credited to the cut block, the first
in play order, as a single pass over the blocks would (finding L3 of
`docs/reviews/2026-09-28-code-review.md`). The peak time and the vector peak time are the
first time the cut block reaches the peak.

**How:** The test builds two blocks with the same x trapezoid (rise 0.2 ms, flat 0.4 ms,
fall 0.2 ms), then a delay block. The window starts at 0.4 ms, in the flat top of block 1,
so block 1's fall ramp and all of block 2 are inside the window. It checks that the x
`peak_block` and `slew_block` are block 1, and that the x `peak_time_s` and
`vector_peak_time_s` are 0.4 ms, the window start.

**Assumptions:** The slope of block 1's fall ramp, clipped by the window, equals bit for bit
the slope of the same event in block 2, because block 1 starts at 0 and the clip keeps the
ramp's own corner points. The oracle is not used: it computes slopes from absolute corner
times, so its slope of block 2 differs by a rounding error.

#### `test_vector_peak_time_on_a_tie_is_the_first_time_in_play_order`

**Checks:** When two blocks with different triples of events reach the same |G| peak, the
vector peak time is the first time the earlier block reaches it, not a time in the later
block, and the vector peak block is the earlier block. The triples are found with
`numpy.unique`, whose order is not the play order.

**How:** The test builds the same trapezoid on x in block 1 and on y in block 2, and checks
that `vector_peak_time_s` is 0.2 ms, the end of block 1's rise, and that
`vector_peak_block` is block 1.

**Assumptions:** None.

#### `test_axis_whose_only_event_is_zero_credits_no_block`

**Checks:** An axis whose only event has amplitude 0 has a peak and a slew of 0, and no block
is credited for either (`peak_block` and `slew_block` are None).

**How:** The test builds one block with an x trapezoid and a y trapezoid scaled to amplitude
0 with `pp.scale_grad`, and checks the y axis's peak, slew and block fields.

**Assumptions:** None.

#### `test_matches_oracle_on_synthetic_sequences`

**Checks:** `gradient_limits` matches the oracle (`tests/oracles/grad_limits.py`, the
implementation from before phase 4 of `docs/plans/cards-at-scale.md`) on the whole file, and
on a window covering the first half of the sequence, for each of `tests/synthetic.py`'s
sequences (parametrized: `spin_echo_sequence`, `gre_sequence`, `empty_sequence`,
`arbitrary_gradient_sequence`).

**How:** For each sequence, the test calls both `gradient_limits` and the oracle's, with no
window and with a window from 0 to half the total duration, and compares every field (`reason`,
`range_s`, each axis's peak, slew and RMS, and the vector peak), within a tolerance derived
from the sequence (`_rounding_tol`): `1e-12 + 4 * eps * duration / shortest segment`, relative
to the value or to the limit of the same kind. It checks only whether a block is credited, not
which one, because `gre_sequence` repeats its readout, phase-encode and spoiler events every TR,
and the oracle's own choice among such a tie can depend on the same rounding.

**Assumptions:**

- The user chose this tolerance on 2026-09-28. The oracle adds each block's absolute start
  time to an event's corner points before it takes a slope, so each corner time is rounded to
  about eps times the start time, and a slope divides the difference of two such times by the
  segment's duration. The new code computes each event one time from its own offsets. On the
  synthetic and random sequences the differences are at most about 2% of this bound.

#### `test_matches_oracle_on_random_gradient_sequences`

**Checks:** 200 random sequences of trapezoids, extended trapezoids and arbitrary gradients on
random axes, each event built so that it starts and ends at 0 (so every block junction step is
0, and the result is only the per-event, non-junction part that the tests above cover on their
own): `gradient_limits` matches the oracle, on the whole file and on a random window, and the
window's `whole_rms_mt_per_m` (computed in the same call, for the card's "RMS over whole file"
column) matches the oracle's own whole-file RMS.

**How:** For each of 200 seeds, the test builds a sequence of 2 to 6 blocks, each with 0 to 3
random axes, each a trapezoid, an extended trapezoid or an arbitrary gradient built with
pypulseq's `make_*` functions (so pypulseq's own limit checks apply) and an explicit `first` and
`last` of 0 where the function does not default to that. It compares the whole-file result and
a random window's result with the oracle's, field by field, with the same derived tolerance and
the same block-attribution exception as `test_matches_oracle_on_synthetic_sequences`, and separately
compares `whole_rms_mt_per_m` against a fresh whole-file oracle call.

**Assumptions:**

- `make_arbitrary_grad`'s `first` and `last` default to a linear extrapolation of the
  waveform's own edge samples, not to 0 (`docs/notes/slew-definitions.md`'s pypulseq source
  reading confirms this), so the random arbitrary-gradient builder passes `first=0.0, last=0.0`
  explicitly to keep every event zero-ended. This is a fact about pypulseq, not about the
  function under test, and is not itself checked here.

#### `test_gradient_limits_refuses_rotations`

**Checks:** `gradient_limits` raises `NotImplementedError` for a sequence with a
rotation library.

**How:** `gre_sequence(num_trs=2)` with a non-empty `rotation_library` (the
`_with_rotation_library` helper of `test_extensions.py`), inside
`pytest.raises(NotImplementedError, match="rotation extension")`.

**Assumptions:** None.

### 2.7 PNS prediction (`test_pns.py`)

`test_pns.py` tests `pns.py`. `PnsPrediction` is now summary-only (`reason`,
`hardware`, `asc_file`, `peak`, `peak_time_s`, `axis_peaks`; no `t_s`,
`norm` or `axes`), built by `pns_prediction` from `pns_levels_for(seq,
gradient_asc=...)` — the SAFE model itself (`pns_levels.pns_levels`, the pinned
pypulseq fork's chunked SAFE recursion) has moved there. `pns_levels_for`
keeps one `PnsLevels` for each (sequence object, hardware), the hardware
being the example hardware, the resolved path of the gradient `.asc`
file, or a `hardware` pair `(struct, label)` (its key is the label and the 27
values of the struct, so two pairs with the same label and values are one
hardware), and the rule of `seq_index.sequence_index` for staleness (all are
rebuilt when the number of blocks or the last block id changes), so that a page with both the PNS summary card and the
diagram's PNS lane for one sequence runs the SAFE model once.
`peak_tr_window` is the start and end of the TR that holds the
prediction's peak, counted from the sequence start in steps of the TR
definition. Without a gradient `.asc` file, the prediction uses pypulseq's
example hardware, which is not a real scanner. The tests of `hardware` are the last
ones of this section.

The real `.asc` files are confidential, so the tests write a test `.asc` file
with the PNS parameters of pypulseq's example hardware, with the
`write_gradient_asc` fixture of `tests/conftest.py`. The stimulation limits
and thresholds in it can be multiplied by a scale factor. The test file can
also have the layout of a scanner file: a main file with an `ASCCONV` block,
CRLF line ends and the name in `asCOMP[0].tName`, which includes a
`_GSWD_SAFETY.asc` file with the PNS parameters under `GradPatSup.Phys.PNS`.

Most of the tests use the synthetic spin echo sequence
(`tests/synthetic.py`'s `spin_echo_sequence`). The `peak_tr_window` tests use
a three-TR sequence built in this file (`_three_trs`): three 50 ms TRs, each a
y trapezoid on the synthetic system and a delay, with a TR definition of
50 ms. One of the three TRs (the "peak TR") has a 0.1 ms rise and fall time,
against 0.4 ms for the others, so its faster slew rate gives it the highest
PNS.

**Assumptions for the whole file:**

- pypulseq's SAFE model is correct. No test compares it with a published
  result or with a scanner.
- No test uses the parameters of a real scanner. A PNS value for the
  synthetic sequences on the scanner is not tested.
- A faster slew rate gives a higher PNS prediction. The SAFE model is driven
  by the slew rate, so this is expected but not calculated in the tests.

#### `test_example_hardware_for_spin_echo`

**Checks:** For the synthetic spin echo sequence on the example hardware, the summary
equals `pns_levels.pns_levels` of the same sequence and hardware, is below the
stimulation limit, and is highest on y.

**How:** The test runs the prediction without an `.asc` file (the module-scoped
`example` fixture) and, separately, `pns_levels.pns_levels` on the same sequence
object. It checks that there is no reason, that the hardware is the example hardware,
and that there is no `.asc` file name. It checks that the axis peaks are keyed x, y and
z, and that the peak is more than 0 and less than 1 (100 % of the limit). The axis with
the highest peak must be y, where the crushers are. `peak`, `peak_time_s` and
`axis_peaks` must equal `pns_levels`'s own fields exactly.

**Assumptions:**

- "Below the limit" is for the example hardware only.
- The crushers (on y) give the synthetic sequence's highest per-axis PNS. This was
  checked against a direct run of the prediction, not derived by hand.
- `pns_prediction` and a fresh `pns_levels.pns_levels` call on the same sequence and
  hardware give bit-identical numbers (no randomness in the pipeline), so the
  comparison is exact equality, not a tolerance.

#### `test_asc_file_with_the_example_parameters`

**Checks:** An `.asc` file with the example hardware's parameters gives the same
prediction as the example hardware, and the file's hardware name and file name.

**How:** The test writes a test `.asc` file with scale factor 1 and runs the
prediction with it. There must be no reason, the hardware name must be the name in the
file, and the file name must be the name of the file. `peak`, `peak_time_s` and each
axis of `axis_peaks` must equal the example hardware's own summary within a relative
10⁻⁹.

**Assumptions:**

- The test file has only the fields that pypulseq's `.asc` reader needs for PNS. A
  real file has many more fields, in the same format.

#### `test_asc_file_that_includes_the_pns_parameters`

**Checks:** A main `.asc` file that includes the PNS parameters from a second file
with `$INCLUDE` gives the same prediction as the example hardware, and the hardware
name in `asCOMP[0].tName`.

**How:** The test writes a test `.asc` file with the scanner layout and scale factor
1, and runs the prediction with the main file. There must be no reason, the hardware
name must be the name in the main file, and the file name must be the name of the main
file. `peak`, `peak_time_s` and each axis of `axis_peaks` must equal the example
hardware's own summary within a relative 10⁻⁹.

**Assumptions:**

- The layout is the layout of the `MP_GradSys_K2309_2250V_951A_XR_AS82.asc` files from
  the XA60 IDEA installation: the `$INCLUDE` line names a file in the same directory,
  without quotes. Other software versions are not tested.

#### `test_asc_file_with_a_missing_include`

**Checks:** When a file that `$INCLUDE` names is not there, reading the `.asc`
file stops with an error that names both files.

**How:** The test writes a test `.asc` file with the scanner layout, deletes
the `_GSWD_SAFETY.asc` file, and reads the main file. It must raise
`FileNotFoundError` with a message that has the main file name and the
included file name.

**Assumptions:** None.

#### `test_included_fields_replace_fields_with_the_same_name`

**Checks:** The fields of an included file are merged into the fields of the
main file, and a field in both files gets the value of the included file.

**How:** The test writes a main file with `a.b[0] = 1`, `a.b[1] = 2`,
`c = "old"` and a `$INCLUDE` line, and an included file with `a.b[1] = 3` and
`c = "new"`. The fields read must be `a.b[0] = 1`, `a.b[1] = 3` and
`c = "new"`.

**Assumptions:**

- In the real files, the `$INCLUDE` line is the last field of the main file,
  so the included values are the last values, as in the file order. A field
  after a `$INCLUDE` line that is also in the included file is not tested.

#### `test_hardware_name`

**Checks:** The hardware name comes from `asCOMP[0].tName` (a scanner file) or
`asCOMP.tName`, and is "unknown" without either.

**How:** The test gives the name function the fields for each of the three
cases and checks the name.

**Assumptions:** None.

#### `test_prediction_scales_with_the_stimulation_limit`

**Checks:** A stimulation limit 10 times lower gives a prediction 10 times
higher, above the limit.

**How:** The test writes a test `.asc` file with scale factor 0.1 and runs the
prediction. The peak must be 10 times the example hardware peak within a
relative 10⁻⁹, and more than 1.

**Assumptions:**

- In the SAFE model, the prediction is inversely proportional to the
  stimulation limit.

#### `test_no_gradients`

**Checks:** A sequence without gradients has no prediction, with the reason
"no gradients", a peak of 0 and no peak time.

**How:** The test makes the synthetic sequence with only a delay block
(`tests/synthetic.py`'s `empty_sequence`) and checks the reason, the hardware
name, the peak and the peak time.

**Assumptions:** None.

#### `test_no_gradients_with_rf_and_adc`

**Checks:** A sequence with RF and ADC events but no gradient events has no
prediction, with the reason "no gradients".

**How:** The test makes a sequence with a block pulse block and an ADC block,
and checks the reason.

**Assumptions:**

- `pns.py` finds "no gradients" from the gradient columns of
  `seq.block_events`. This test and `test_no_gradients` check that other
  events do not count as gradients.

#### `test_a_gradient_on_one_axis_has_a_prediction`

**Checks:** A sequence with a gradient on one axis only, x, y or z, has a
prediction.

**How:** For each axis, the test makes a sequence with a delay block and a
trapezoid block on that axis. There must be no reason, and the peak must be
more than 0.

**Assumptions:**

- A gradient in a block after the first block counts. The delay block comes
  first, so a check of the first block only would fail.

#### `test_prediction_does_not_build_the_gradients_for_an_on_raster_sequence`

**Checks:** The prediction never calls `seq.get_gradients()` for an on-raster sequence.

**How:** The test replaces `get_gradients` of a synthetic spin echo sequence with a
wrapper that counts the calls, and runs the prediction. There must be no calls.

**Assumptions:**

- `pns_levels.pns_levels` samples an on-raster sequence with
  `GradientSampler.block_samples`, not `seq.get_gradients()`/`seq.calculate_pns` (that
  was the old, now-removed, implementation, which is why the old test expected exactly
  one call). `test_pns_levels.py` and `test_sampling.py` test `block_samples` and its
  agreement with `sample`/`get_gradients()` directly; this test only checks that the
  fast path is actually taken from `pns_prediction`.

#### `test_prediction_keeps_no_blocks_and_gives_back_the_cache_setting`

**Checks:** The prediction does not fill pypulseq's block cache, and the
cache setting of the sequence is the same after the prediction.

**How:** For `use_block_cache` True and False, the test sets it on a
synthetic spin echo sequence, empties `seq.block_cache`, and runs the
prediction. After it, `use_block_cache` must have the same value and
`seq.block_cache` must be empty.

**Assumptions:**

- `calculate_pns` reads every block with `get_block`, which keeps each block
  in `seq.block_cache` when `use_block_cache` is True. An empty cache after
  the prediction shows that the cache was off while it ran.

#### `test_prediction_propagates_an_error_and_keeps_the_cache_setting`

**Checks:** An error deep inside the SAFE model propagates out of `pns_prediction`, and
the sequence's block-cache setting and contents are unaffected.

**How:** The test sets `use_block_cache` to True on a synthetic spin echo sequence and
replaces `pns_levels._safe_gwf_to_pns_chunk` (the pinned fork's chunk function) with a
function that raises `RuntimeError`. The prediction must raise the error,
`use_block_cache` must be True and `seq.block_cache` must be empty afterward.

**Assumptions:**

- The block cache is touched only inside `seq_index.block_cache_off`'s own
  `try`/`finally`, which has already restored `use_block_cache` by the time the chunk
  function runs (`GradientSampler` is built, with the block cache off, before the
  chunk loop starts). So this test checks that the error propagates and that nothing
  else in `pns_levels_for`/`pns_prediction` touches the cache setting outside that
  narrower guarantee, not that the guarantee itself is new.

#### `test_peak_tr_window_finds_the_tr_with_the_peak`

**Checks:** For each position of the peak TR (first, second or third) in the
three-TR sequence, `peak_tr_window` returns that whole TR, and the
prediction's peak time is inside it.

**How:** For peak TR k = 0, 1 and 2, the test builds `_three_trs(k)`, runs the
prediction, and calls `peak_tr_window` with the peak time. The window must be
50k s to 50(k + 1) ms (converted to seconds), and the peak time must be
inside it.

**Assumptions:**

- TRs are counted from the start of the sequence, in steps of the TR
  definition.

#### `test_peak_tr_window_without_a_tr_definition_is_none`

**Checks:** Without a TR definition, `peak_tr_window` returns None.

**How:** The test builds the three-TR sequence, removes its TR definition,
runs the prediction, and calls `peak_tr_window` with the peak time. The
result must be None.

**Assumptions:** None.

#### `test_peak_tr_window_with_one_tr_is_none`

**Checks:** When the sequence is not longer than one TR, `peak_tr_window`
returns None.

**How:** The test takes the synthetic spin echo sequence, whose duration is
much less than a TR, and sets its TR definition to its own duration exactly.
`peak_tr_window` with any peak time must return None.

**Assumptions:** None.

#### `test_peak_tr_window_without_a_peak_time_is_none`

**Checks:** With no peak time (`None`), `peak_tr_window` returns None.

**How:** The test builds the three-TR sequence and calls `peak_tr_window`
with `peak_time_s=None`. The result must be None.

**Assumptions:** None.

#### `test_pns_levels_for_keeps_one_result_for_each_asc_file`

**Checks:** `pns_levels_for` keeps one result for each (sequence, gradient `.asc`
file): a different `.asc` file for the same sequence computes once, and going back to
an earlier file does not compute again.

**How:** The test patches `pns.pns_levels` the same way as the test above, and calls
`pns.pns_levels_for(seq, gradient_asc=path)` for two different `.asc` files (`path_a`,
`path_b`) built by the `write_gradient_asc` fixture of `tests/conftest.py`, in the order a, a, b, a. It
checks the call count is 1, 1 (cached), 2 (a different file), 2 (back to `path_a`,
restored from the kept results).

**Assumptions:** None.

#### `test_pns_levels_for_alternating_two_hardwares_runs_the_model_two_times`

**Checks:** Two hardwares of one sequence alternated (a, b, a, b) run the SAFE model two
times, not four: the cache keeps one result for each hardware.

**How:** The test patches `pns.pns_levels` as above, and calls
`pns.pns_levels_for(seq, gradient_asc=...)` with the keys `None` (the example hardware),
a `.asc` file, `None`, the same file. It checks there were 2 calls.

**Assumptions:** None.

#### `test_pns_levels_for_hardware_from_an_asc_file_gives_the_levels_of_the_file`

**Checks:** `pns_levels_for(seq, hardware=(asc_to_hw(read_gradient_asc(path)), label))`
gives the levels of `pns_levels_for(seq, gradient_asc=path)`, except `hardware` (the
label) and `asc_file` (None), for the plain layout and for the layout of a scanner file.

**How:** Parametrized on `split`. The `write_gradient_asc` fixture of `tests/conftest.py`
writes the file. The test compares each field but the two (`numpy.array_equal` for the
arrays, `==` for the rest).

**Assumptions:** None.

#### `test_pns_levels_for_refuses_both_gradient_asc_and_hardware`

**Checks:** `pns_levels_for` with `gradient_asc` and `hardware` together raises
`ValueError`, and does not run the SAFE model.

**How:** The test patches `pns.pns_levels` as in the tests below, calls
`pns_levels_for` with both inside `pytest.raises(ValueError, match="not both")`, and
checks that the patch recorded no call.

**Assumptions:** None.

#### `test_pns_levels_for_keeps_one_result_for_equal_hardware_pairs`

**Checks:** Two `hardware` pairs with the same label and the same field values, with two
different struct objects, are one hardware: the second call runs no model and gives the
kept result.

**How:** The test patches `pns.pns_levels` as above and calls `pns_levels_for(seq,
hardware=(safe_example_hw(), "LABEL"))` two times, each with a new struct. It checks
that there was 1 call and that the second result `is` the first.

**Assumptions:** None.

#### `test_pns_levels_for_computes_again_for_another_label_or_value`

**Checks:** A `hardware` pair with another label, or with one other field value, runs
the model; going back to an earlier pair does not run it again.

**How:** The test patches `pns.pns_levels` as above and calls with the pairs a, a, b (the
label "B"), c (`z.stim_thresh` plus 1), a, c, each with a new struct where the values are
the same. It checks the call count after each change: 1, 1, 2, 3, 3.

**Assumptions:** None.

#### `test_pns_levels_for_hardware_pair_is_not_the_example_hardware_or_a_file`

**Checks:** A `hardware` pair has its own key: the example hardware (no argument), a
`.asc` file, and a pair with the values and the label of the example hardware are three
hardwares of one sequence. Each runs the model one time.

**How:** The test patches `pns.pns_levels` as above, and calls the three two times in
the same order. It checks that there were 3 calls.

### 2.8 Target profile (`test_profile.py`)

`test_profile.py` tests `profile.py` (plan section 4.3, rules 1 to 6, and section 4.9):
`read_profile`, which reads a target profile from a TOML or a JSON file, and the fields
and methods of `TargetProfile`. The example profiles are in `tests/profiles/`:
`prisma.toml` and `prisma.json` (the example of plan section 4.3 without `asc`),
`minimal.toml`, `hz_units.toml`, `unused.toml` and `with_asc.toml`. The other profiles
are written in `tmp_path`. The SAFE sections of the example files have the parameters of
pypulseq's example hardware (`safe_example_hw`), not of a real scanner. Except one test,
the tests do not use an installed model or an installed reader: an autouse fixture
replaces `registry.models` (one test model, "pns.safe", that
has the keys of the SAFE model and checks only the names) and `registry.profile_reader`
(no reader), and a test that needs the reader "siemens-asc" installs a test reader,
which returns sections and sources that the test gives. No test reads real `.asc` data.
A test of an error case matches the message against the file name, because each
`ProfileError` must name the profile file.

#### `test_toml_and_json_give_equal_profiles_except_for_the_path`

**Checks:** `tests/profiles/prisma.toml` and `tests/profiles/prisma.json`, the example
of plan section 4.3 without `asc`, read to equal `TargetProfile` objects except for
`source_path`.

**How:** The test reads both files and compares the two profiles with `==`, after it
sets `source_path` of both to None. It first checks that the two `source_path` values
differ.

**Assumptions:** The JSON file is the output of `json.dump` for the parsed TOML file.
The test does not check that the two files have the same text in another form.

#### `test_the_example_of_plan_section_4_3_reads_to_the_expected_values`

**Checks:** The example of plan section 4.3 (without `asc`, with the test model in place
of the SAFE model) reads to the values that the file gives, in every field of `TargetProfile`.

**How:** The test reads `prisma.toml` and compares `name`, `vendor`, `format_version`,
`opts`, `rasters`, `models` (the return value of the test model),
`acoustic_resonances` (a tuple of float pairs) and `unused_sections` with values written
in the test. It checks that `hardware_limits` exists and has the profile name as its
label.

**Assumptions:** The test model returns its parameters with one added key, so the test
sees that `read` ran. The numbers of the limits are in the tests of the hardware limits.

#### `test_an_example_file_converted_to_json_reads_to_an_equal_profile`

**Checks:** Each example file in `tests/profiles/` (`prisma`, `minimal`, `hz_units`,
`unused`) gives an equal profile from its TOML text and from the same data as JSON.

**How:** The test is parametrized over the four names. It parses the TOML file with
`tomllib`, writes the data with `json.dumps` to a JSON file in `tmp_path`, reads both
with `read_profile`, and compares the profiles with `==` after it sets `source_path` of
both to None.

**Assumptions:** This is the round trip between the two formats. The test does not write
a profile back to a file, because `read_profile` is the only function that the plan
gives for files.

#### `test_an_example_file_reads_with_the_installed_models`

**Checks:** Each example profile (`prisma`, `minimal`, `hz_units`, `unused`) is valid for
the models that this package installs, and the SAFE sections of `prisma.toml` and
`unused.toml` read to the parameters of pypulseq's example hardware.

**How:** The test sets `registry.models` back to the function of the package (the
autouse fixture replaced it with the test model), reads each file with `read_profile`,
and compares `models` for the two files that have a SAFE section.

**Assumptions:** The entry point of `pns_levels.SAFE_MODEL` is installed (`uv sync` after
the change of `pyproject.toml`). `with_asc.toml` is not read: it needs an `.asc` file.

#### `test_the_path_can_be_a_string_and_source_path_is_resolved`

**Checks:** `read_profile` takes a `str` path, and `source_path` is the absolute,
resolved path of the file.

**How:** The test changes the working directory to `tests/profiles`, reads "prisma.toml"
as a relative `str`, and compares `source_path` with the resolved path of the file.

**Assumptions:** None.

#### `test_another_suffix_is_a_profile_error_that_names_the_file`

**Checks:** Rule 1: a file with a suffix other than `.toml` or `.json` (`.yaml`, `.txt`,
no suffix) is a `ProfileError` whose message has the file name.

**How:** The test is parametrized over three file names. It writes a valid TOML text to
each and calls `read_profile`.

**Assumptions:** The content of the file is valid, so the suffix is the only reason for
the error.

#### `test_a_profile_error_is_an_error_of_the_run`

**Checks:** `ProfileError` is a subclass of `CheckRunError`, so that the command gives
exit status 1 for it.

**How:** The test calls `issubclass`.

**Assumptions:** The test does not run the command. The command tests check the exit
status.

#### `test_a_missing_file_is_a_profile_error_that_names_the_file`

**Checks:** Rule 1: a file that does not exist is a `ProfileError` whose message has the
file name.

**How:** The test calls `read_profile` for a `.toml` path in `tmp_path` that does not
exist.

**Assumptions:** None.

#### `test_a_file_that_does_not_parse_is_a_profile_error_that_names_the_file`

**Checks:** Rule 1: a file with a TOML or JSON syntax error, a JSON file whose top level
is a list, and a file that is not UTF-8 are each a `ProfileError` whose message has the
file name.

**How:** The test is parametrized over four files: a TOML file with a key that has no
value, a JSON file that stops in the middle, a JSON list and a `.toml` file with bytes
that are not UTF-8. It calls `read_profile` for each.

**Assumptions:** None.

#### `test_the_format_is_necessary`

**Checks:** Rule 2: a profile without the key `format` is a `ProfileError` whose message
has the file name and the key.

**How:** The test writes a JSON profile with only a name and calls `read_profile`.

**Assumptions:** None.

#### `test_the_format_must_be_an_integer`

**Checks:** Rule 2: a `format` that is a string, a float, a bool, null or a list is a
`ProfileError`.

**How:** The test is parametrized over five values. It writes a JSON profile with the
value and calls `read_profile`.

**Assumptions:** A bool is an `int` in Python, so the test has `True` to show that the
reader refuses it.

#### `test_a_format_below_1_is_an_error`

**Checks:** Rule 2: a `format` of 0 or -1 is a `ProfileError`.

**How:** The test is parametrized over the two values and calls `read_profile` for a
JSON profile with each.

**Assumptions:** None.

#### `test_a_newer_format_is_an_error_that_names_both_versions`

**Checks:** Rule 2: a `format` above `FORMAT_VERSION` is a `ProfileError` whose message
has the version of the file and the version of the reader.

**How:** The test writes a profile with `FORMAT_VERSION + 1` and matches the message
against "format N ... format M" with both numbers.

**Assumptions:** The test reads `FORMAT_VERSION` from the module, so it does not change
when the version changes.

#### `test_the_name_is_necessary_and_a_non_empty_string`

**Checks:** A profile without `name`, or with an empty string, a number or a list as the
name, is a `ProfileError` that names the key.

**How:** The test is parametrized over four values (the first is a missing key) and
calls `read_profile` for a JSON profile.

**Assumptions:** None.

#### `test_the_optional_top_level_keys_must_be_strings`

**Checks:** `vendor` (a number), `asc` (a number, an empty string) and
`asc_gradient_mode` (a number) that are not strings are each a `ProfileError` that names
the key.

**How:** The test is parametrized over four pairs. It writes a JSON profile with the
pair (and an `asc` key, so that `asc_gradient_mode` is not refused for a missing `asc`
first) and calls `read_profile`.

**Assumptions:** None.

#### `test_an_unknown_top_level_key_with_a_value_that_is_not_a_table_is_an_error`

**Checks:** Rule 3: an unknown key at the top level with a scalar or a list value is a
`ProfileError` that names the key and the top level.

**How:** The test is parametrized over five values (a number, a string, two lists, a
bool). It writes a JSON profile with the key `colour` and calls `read_profile`.

**Assumptions:** The plan says that an unknown key in a known section is an error. The
top level is a known section with a rule of its own: an unknown key with a table value
is a section.

#### `test_an_unknown_top_level_table_is_kept_as_an_unused_section`

**Checks:** Rule 3: an unknown top-level key with a table value is in `unused_sections`
by its name, in the order of the file, and the profile is valid.

**How:** The test writes a JSON profile with two unknown tables (one with a nested
table) and compares `unused_sections` with the two names.

**Assumptions:** None.

#### `test_an_unused_section_does_not_add_a_value_or_a_source`

**Checks:** An unknown top-level table that has a key named like a known section
(`opts`) gives no value and no source.

**How:** The test writes a profile with `notes = {opts = {max_grad = 1}}` and checks
that `sources` is empty and that `has_value("opts.max_grad")` is False.

**Assumptions:** None.

#### `test_a_known_section_that_is_not_a_table_is_an_error`

**Checks:** `opts`, `rasters`, `models` or `acoustic` with a list as its value is a
`ProfileError` that names the section.

**How:** The test is parametrized over the four sections and calls `read_profile` for a
JSON profile.

**Assumptions:** None.

#### `test_an_unknown_key_in_a_known_section_is_an_error_that_names_the_key_and_the_section`

**Checks:** Rule 3: an unknown key in `opts` (`max_slwe`, and `self`, which is an
argument of `pp.Opts.__init__` but not a keyword that a profile can give), `rasters` or
`acoustic` is a `ProfileError` that names the key and the section.

**How:** The test is parametrized over four cases and matches the message against "key
... [section]".

**Assumptions:** The unknown key of `models` is a section that is not installed, and it
is not an error: the tests of the unused sections have it. The keys of a model section
are the work of the model.

#### `test_the_keys_of_opts_are_the_keywords_of_pp_opts`

**Checks:** Each keyword of `pp.Opts.__init__` that is not a raster is a known key of
`[opts]`, and it is in `opts` and in `sources` after the read.

**How:** The test writes a profile with 11 keywords (the dead times, `gamma`, the limits
and their units, the ADC sample limits, `B0`) and compares `opts` with the same dict. It
checks `has_value` for each key.

**Assumptions:** The test does not have each keyword of `pp.Opts` that the installed
pypulseq has: the reader builds the set from `inspect.signature`, so a keyword of a
newer pypulseq is known without a change here.

#### `test_a_raster_keyword_in_opts_is_an_error_that_points_to_the_rasters`

**Checks:** Each of the four raster keywords of `pp.Opts` (`grad_raster_time`,
`rf_raster_time`, `adc_raster_time`, `block_duration_raster`) in `[opts]` is a
`ProfileError` that says that the rasters go in `[rasters]` with their reserved names.

**How:** The test is parametrized over the four keywords and matches the message against
"keyword ... [rasters] ... reserved".

**Assumptions:** None.

#### `test_each_raster_name_is_read_and_given_to_its_opts_keyword`

**Checks:** The four reserved raster names are read into `rasters`, and `make_opts()`
gives each to the matching `pp.Opts` attribute.

**How:** The test writes a profile with the four names and different values. It compares
`rasters` with the dict and the four attributes of `make_opts()` with the values.

**Assumptions:** None.

#### `test_a_raster_rule_is_an_error_because_the_check_needs_equal_rasters`

**Checks:** A `rasters.rule` ("equal" or "multiple") is a `ProfileError`, because
version 1 has no rule: the message names `rasters.rule` and says that the raster check
needs equal rasters. A profile made for a later version that asks for "multiple" is
refused, not checked for equality in silence.

**How:** The test is parametrized over the two rules. It writes a profile with only the
rule and matches the message of the error.

**Assumptions:** None.

#### `test_a_raster_must_be_a_positive_number`

**Checks:** A raster of 0, a negative number, a string, a bool, null, a list or NaN is a
`ProfileError` that names the raster.

**How:** The test is parametrized over seven values. It writes a JSON profile (Python's
`json` writes NaN as a token that it reads again) and calls `read_profile`.

**Assumptions:** None.

#### `test_a_raster_of_the_toml_file_can_be_an_integer`

**Checks:** A raster that is an integer in a TOML file is a valid positive number.

**How:** The test writes `GradientRasterTime = 1` in a TOML file and compares `rasters`.

**Assumptions:** The value 1 s is not a real raster. The test checks the type only.

#### `test_the_acoustic_resonances_are_a_tuple_of_float_pairs`

**Checks:** `acoustic.resonances` is read into `acoustic_resonances` as a tuple of float
pairs, and it is in `sources`.

**How:** The test writes integer and float pairs, and compares the tuple and the types
of the numbers.

**Assumptions:** None.

#### `test_malformed_acoustic_resonances_are_an_error`

**Checks:** `acoustic.resonances` that is not a list of [frequency, bandwidth] pairs of
numbers (a number, a flat list, a pair with one or three numbers, strings, bools, a
dict, a string) is a `ProfileError` that names the value.

**How:** The test is parametrized over eight values and calls `read_profile`.

**Assumptions:** None.

#### `test_an_empty_acoustic_resonances_list_is_an_empty_tuple`

**Checks:** An empty list of resonances is valid, and it is the empty tuple (not None).

**How:** The test writes an empty list and compares `acoustic_resonances` with `()`.

**Assumptions:** The reader does not judge if a profile with no resonance is useful.

#### `test_a_null_value_in_opts_is_an_error_because_pp_opts_would_use_its_default`

**Checks:** A null value (JSON) in `[opts]` is a `ProfileError`: `pp.Opts` takes None as
"use the default", and rule 6 gives no default.

**How:** The test writes `max_grad: null` in a JSON profile and matches the message
against the file name and "opts.max_grad is null".

**Assumptions:** None.

#### `test_a_bad_value_for_pp_opts_is_a_profile_error_that_names_the_file`

**Checks:** A value that `pp.Opts` refuses (here an unknown unit) is a `ProfileError`
whose message has the file name and the text of the `pp.Opts` error.

**How:** The test writes `grad_unit = "furlong"` and matches the message.

**Assumptions:** The reader does not check value ranges or types. `pp.Opts` checks only
the units, so a limit that is a negative number is valid here.

#### `test_a_limit_that_is_not_a_number_is_a_profile_error`

**Checks:** A `max_grad` that is a string or a list, with a valid `max_slew`, is a
`ProfileError` that names the file, although `pp.Opts` accepts it.

**How:** The test is parametrized over two values. The `TypeError` comes from the
calculation of the hardware limits, and the reader turns it into the error.

**Assumptions:** The test covers `max_grad` and `max_slew` only (the two values that the
reader uses). Another key with a value of the wrong type is an error of `pp.Opts` or of
a check later.

#### `test_the_model_section_is_read_by_its_installed_model_and_stored_by_name`

**Checks:** A `[models.pns.safe]` section is given to `read` of the installed model
"pns.safe"; the return value is in `models["pns.safe"]`, and `sources` has
`models.pns.safe`.

**How:** The test installs the test model with `monkeypatch.setattr(registry, "models",
...)`, writes a profile with nested tables and compares `models`, `sources`, `has_value`
and `unused_sections`.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_profile_without_a_model_section_has_no_models`

**Checks:** A profile with no `models` key has an empty `models` mapping, and no source
for a model.

**How:** The test reads a profile with the name only while the test model is installed.

**Assumptions:** None.

#### `test_a_model_that_is_not_installed_makes_its_section_unused`

**Checks:** With no installed model, the section `models.pns.safe` is not read: `models`
is empty, and `unused_sections` is `("models.pns",)`, the highest table without an
installed model under it.

**How:** The test installs no model and reads a profile with `[models.pns.safe]`.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_model_error_is_a_profile_error_that_names_the_section`

**Checks:** A `ValueError` of `Model.read` is a `ProfileError` whose message has the
file name, the section `models.pns.safe` and the text of the `ValueError`.

**How:** The test gives the test model a section with an unknown key and matches the
message.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_model_section_that_is_not_a_table_is_a_profile_error`

**Checks:** A `models.pns.safe` that is a number, with an installed model "pns.safe", is
a `ProfileError` that names `models.pns.safe`.

**How:** The test writes the number and calls `read_profile`.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_value_directly_under_models_that_is_not_a_table_is_an_error`

**Checks:** A value that is not a table under `models` (a number, a string, a list) is a
`ProfileError` that names the path (`models.pns`).

**How:** The test is parametrized over three values.

**Assumptions:** The reader applies the same rule to a value that is not a table at each
level under `models` that leads to an installed model.

#### `test_the_tables_of_models_with_no_installed_model_are_unused_sections`

**Checks:** In `tests/profiles/unused.toml`, `[notes]`, `[models.pns.other]` and
`[models.ge.pns]` are unused sections (`notes`, `models.pns.other` and `models.ge`), in
the order of the file, and the installed `[models.pns.safe]` is read.

**How:** The test reads the file and compares `unused_sections`, the names in `models`
and `sources`.

**Assumptions:** The name of the last entry is `models.ge`, not `models.ge.pns`: the
reader gives the highest table that has no installed model under it.

#### `test_the_highest_table_without_an_installed_model_is_the_unused_section`

**Checks:** A table with tables under it and no installed model anywhere under it is one
unused section, with the name of the table that is the highest one (`models.ge` for
`ge.pns.params`, `models.philips`).

**How:** The test writes a JSON profile with both and compares `unused_sections`.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_the_hardware_limits_are_in_mt_per_m_and_t_per_m_per_s`

**Checks:** `hardware_limits` has the limits in mT/m and T/m/s for the same limits that
the profile gives in mT/m and T/m/s, in Hz/m and Hz/m/s (the defaults of `pp.Opts`) and
in rad/ms/mm and T/m/s; its label is the name of the profile.

**How:** The test is parametrized over three profiles that give 80 mT/m and 200 T/m/s in
three units, and compares the two numbers with `pytest.approx`.

**Assumptions:** The numbers in Hz use the gamma of `pp.Opts` (42.576 MHz/T).

#### `test_the_hardware_limits_of_a_profile_in_hz_units_come_from_the_example_file`

**Checks:** `tests/profiles/hz_units.toml`, which gives the limits in the units that
`pp.Opts` has by default, reads to 100 mT/m and 100 T/m/s, with the label of the
profile.

**How:** The test reads the file and compares the limits.

**Assumptions:** None.

#### `test_the_hardware_limits_use_the_gamma_of_the_opts_object`

**Checks:** With a `gamma` in `[opts]`, the limits in mT/m and T/m/s are the values that
the profile gives, and `make_opts()` has a different Hz/m value from a profile without
`gamma`.

**How:** The test reads two profiles with the same limits in mT/m and T/m/s, one of them
with `gamma = 10e6`, and compares the limits and `make_opts().max_grad`.

**Assumptions:** None.

#### `test_hardware_limits_need_both_max_grad_and_max_slew`

**Checks:** With only `max_grad` or only `max_slew`, `hardware_limits` is None.

**How:** The test is parametrized over the two keys.

**Assumptions:** None.

#### `test_max_grad_with_rise_time_gives_the_slew_limit_that_pp_opts_calculates`

**Checks:** A TOML profile with `max_grad = 30` mT/m and `rise_time = 200e-6` and no
`max_slew` gives `opts.max_slew` (`has_value`), has no source for `opts.max_slew`, and
has `hardware_limits` of 30 mT/m and 150 T/m/s (`max_grad / rise_time`, the value of
`pp.Opts`).

**How:** The test writes a TOML profile with these `[opts]` and reads it.

**Assumptions:** None.

#### `test_rise_time_without_max_grad_does_not_give_the_slew_limit`

**Checks:** A profile with `rise_time` and no `max_grad` does not give `opts.max_slew`,
and `hardware_limits` is None. `pp.Opts` would divide its default `max_grad`.

**How:** The test reads a profile with `rise_time` only.

**Assumptions:** None.

#### `test_max_slew_with_rise_time_is_an_error_because_pp_opts_replaces_max_slew`

**Checks:** A profile that gives both `max_slew` and `rise_time` is a `ProfileError` that
names the file and both values.

**How:** The test reads a JSON profile with both keys and matches the message.

**Assumptions:** None.

#### `test_max_slew_from_the_asc_reader_with_rise_time_from_the_profile_is_an_error`

**Checks:** `max_slew` from the `.asc` reader and `rise_time` from the profile file is a
`ProfileError` that names both sources.

**How:** A `FakeReader` gives the GPA limits of the mode "fast"; the profile gives
`rise_time`. The test matches the message.

**Assumptions:** None.

#### `test_a_profile_with_the_name_only_has_no_default_value`

**Checks:** Rule 6: a profile with `format` and `name` only has None for `opts`,
`rasters`, `hardware_limits`, `vendor` and `acoustic_resonances`, and empty `models`,
`sources` and `unused_sections`.

**How:** The test compares the whole profile with a `TargetProfile` that it makes.

**Assumptions:** None.

#### `test_an_empty_known_section_gives_no_value`

**Checks:** An empty `[opts]`, `[rasters]`, `[acoustic]` or `[models]` gives no value,
no source and None (not an empty mapping) for the optional fields.

**How:** The test is parametrized over four profiles.

**Assumptions:** None.

#### `test_the_sources_name_each_value_that_the_profile_gives`

**Checks:** For `prisma.toml`, `sources` has each value path (`opts.<key>` for each key,
`rasters.<name>` for the four names, `models.pns.safe`,
`acoustic.resonances`) with the label "profile", and no other.

**How:** The test builds the list of value paths from `opts` and `RASTER_OPTS` and
compares it with `sources`.

**Assumptions:** None.

#### `test_has_value_is_true_for_a_path_in_the_sources_only`

**Checks:** `has_value(path)` is True for a path in `sources`, and False for a path that
is not.

**How:** The test reads a profile with `opts.B0` and calls `has_value` for three paths.

**Assumptions:** None.

#### `test_make_opts_builds_pp_opts_from_the_opts_and_the_rasters`

**Checks:** `make_opts()` gives a `pp.Opts` with the limits (in Hz/m and Hz/m/s), the
dead time, `B0` and three of the rasters that `prisma.toml` gives.

**How:** The test reads the file and compares the attributes of the object.

**Assumptions:** None.

#### `test_the_asc_reader_is_called_with_the_path_relative_to_the_profile_and_the_mode`

**Checks:** Rule 4: the reader "siemens-asc" gets the `asc` path relative to the
directory of the profile file, resolved, and the `asc_gradient_mode` of the profile as a
keyword.

**How:** The test installs a test reader and reads `tests/profiles/with_asc.toml` (`asc
= "gpa/test.asc"`, mode "fast"). It compares the arguments of the call.

**Assumptions:** The file `gpa/test.asc` does not exist: the test reader does not open
it. The test model and the test reader are classes in the test file, not the real ones.

#### `test_the_asc_reader_gets_no_mode_when_the_profile_selects_none`

**Checks:** Without `asc_gradient_mode`, the reader gets `gradient_mode=None`.

**How:** The test reads a profile with `asc` only and compares the mode of the call.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_the_sections_of_the_asc_reader_are_merged_with_the_values_of_the_profile`

**Checks:** The sections of the reader (`opts`, `models`, `acoustic`) and the values of
the profile (other `opts` keys and a raster) give one profile.

**How:** The test installs a test reader with sections and sources, reads a profile that
gives `B0` and a raster, and compares `opts`, `rasters`, `acoustic_resonances` and
`models`.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_the_sources_label_each_value_with_the_profile_or_the_label_of_the_reader`

**Checks:** `sources` has "profile" for the values of the profile file and the label of
the reader (here "gpa.asc (fast)" and "gpa.asc") for the values that it gives, and
`has_value` is True for both.

**How:** The test compares `sources` with the dict of both.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_the_hardware_limits_can_come_from_the_values_of_the_asc_reader`

**Checks:** `hardware_limits` exists when the reader gives `max_grad` and `max_slew`
(and their units), and its label is the profile name.

**How:** The test reads a profile with `asc` and a mode whose test reader gives 60 mT/m
and 150 T/m/s, and compares the limits.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_reader_without_opts_leaves_the_opts_to_the_profile`

**Checks:** When the reader gives no `opts` and the profile has no `[opts]`, `opts` and
`hardware_limits` are None, and the model of the reader is read.

**How:** The test installs a test reader with a model section only.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_value_from_the_profile_and_the_asc_reader_is_an_error_that_names_both_sources`

**Checks:** Rule 4: a value path that the profile file and the reader both give
(`opts.max_grad`, `opts.grad_unit`, `models.pns.safe`, `acoustic.resonances`) is a
`ProfileError` whose message has the file name, the path, "profile" and the label of the
reader.

**How:** The test is parametrized over four value paths. It installs a test reader that
gives all four, writes a profile that gives one of them and matches the message.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_profile_that_gives_max_grad_and_selects_a_mode_is_an_error`

**Checks:** The case of plan section 4.9: a profile that gives `max_grad` and selects a
mode, for which the reader gives `max_grad`, is a `ProfileError` that names
`opts.max_grad` and both labels, "profile" and "gpa.asc (fast)".

**How:** The test matches the message against the path and the two labels in this order.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_raster_from_the_profile_and_one_from_the_reader_is_an_error`

**Checks:** A raster that both the profile and the reader give is a `ProfileError` that
names `rasters.GradientRasterTime`.

**How:** The test installs a test reader that gives the raster.

**Assumptions:** The reader of phase 4 does not give rasters. The test checks that the
duplicate rule is for each section.

#### `test_the_asc_model_sections_go_through_the_model_read`

**Checks:** A model section from the reader goes through `Model.read`: a `ValueError` is
a `ProfileError` that names the file and `models.pns.safe`.

**How:** The test installs a test reader with a model section with an unknown key.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_an_asc_model_that_is_not_installed_is_an_unused_section`

**Checks:** A model section from the reader for a model that is not installed is in
`unused_sections` (`models.pns`), and not in `models`.

**How:** The test installs no model and a test reader that gives `models.pns.safe`.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_gradient_mode_without_asc_is_an_error`

**Checks:** An `asc_gradient_mode` without `asc` is a `ProfileError` that names the file
and the key, and the reader is not called.

**How:** The test installs a test reader that keeps its calls, reads a profile with a
mode only and checks that the list of calls is empty.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_asc_without_an_installed_reader_is_an_error`

**Checks:** With `asc` and no reader "siemens-asc" (`registry.profile_reader` gives
None), `read_profile` raises a `ProfileError` that names the file and the reader.

**How:** The test uses the default of the file, a `profile_reader` that gives None.

**Assumptions:** None.

#### `test_a_reader_error_is_a_profile_error_that_names_the_profile_and_the_asc_file`

**Checks:** A `ValueError`, a `FileNotFoundError` or another `OSError` of the reader is
a `ProfileError` whose message has the profile file, the `.asc` file and the text of the
error.

**How:** The test is parametrized over three errors, with a test reader that raises
them.

**Assumptions:** The test model and the test reader are classes in the test file, not
the real ones.

#### `test_a_value_of_the_asc_reader_that_is_not_valid_is_a_profile_error`

**Checks:** A reader result with an unknown `opts` key, a value that has no source, an
unknown top-level section or a malformed list of resonances is a `ProfileError` that
names the profile file and the `.asc` file.

**How:** The test is parametrized over four results of a test reader.

**Assumptions:** The reader of phase 4 makes a valid result. The test checks that
`read_profile` does not trust a plugin reader.

### 2.9 Results (`test_results.py`)

These tests cover `Finding` (plan check-findings, section 4.1), `ResultMatrix`: its exit status
(design section 5.6, R3), its JSON form (decision 9 of the plan, with the findings of plan
check-findings, section 4.5) and `ResultMatrix.with_max_findings` (section 4.6). They build
the results directly, with no sequence.

#### `test_exit_status`

**Checks:** `ResultMatrix.exit_status()` gives the status of each row of the table of design
section 5.6: no result or all pass gives 0; a fail gives 2 (required or not); an error gives
1; a required "not evaluated" gives 1; a "not evaluated" that is not required gives 0. When
statuses 1 and 2 both apply, the status is 1 (R3): a fail with an error, and a fail with a
required "not evaluated".

**How:** The test is parametrized. Each case is a list of `Result` objects with a state and a
`required` flag, in a matrix with one target. The test compares `exit_status()` with the
status of the case.

**Assumptions:** An empty result list gives 0. A run with no target is an error of the run, not
a state of the matrix.

#### `test_json_round_trip`

**Checks:** `ResultMatrix.from_json(m.to_json()) == m`, and the new matrix gives the same text
again, for seven matrices: one with every field set (also a finding with a location and data,
and a `findings_omitted`), one with `None` fields, one with two targets, one with `inf` and
`-inf` in a value, a limit and a time, one with a location whose block is `None`, one with
findings (each type of `data` value: a string, an int, a float, a float with a whole value, the
two bools and `None`; a finding with a location, one with no location and no data, and one with
a location whose block is `None`; a result that is "pass" with a finding, and one that is
"error" with no finding and a `findings_omitted`), and one with `inf` and `-inf` in the `data`
of a finding next to a finite float and an int. The text is strict JSON (it has no `Infinity`
or `NaN`).

**How:** The test is parametrized over a function for each matrix. It writes the text, reads it
back, and compares the matrices and the two texts. It parses the text again with a
`parse_constant` function that fails the test on a non-finite constant.

**Assumptions:** `nan` is not in the cases, because `nan != nan`: a matrix with `nan` is never
equal to itself. `test_json_reads_nan_in_the_data_of_a_finding_as_a_float` covers `nan` in the
`data` of a finding.

#### `test_json_round_trip_keeps_floats_exactly`

**Checks:** A float of a result comes back with the same value, not a rounded one.

**How:** The test uses `0.1 + 0.2` as a value and `1 / 3` as a limit, and compares the values
after the round trip with `==`.

**Assumptions:** The JSON module of Python writes the shortest text that gives the same float
back.

#### `test_json_has_the_keys_of_decision_9`

**Checks:** The JSON object has `"format": 1` and the keys of decision 9, in a fixed order:
`format`, `package_version`, `sequence`, `targets`, `results`. A target has `name`, `sources`
(an object), `unused_sections` (a list) and `limits_source`. A result has each `Result` field,
with `state` as its value text (for example "not evaluated") and `location` as
`{"block": ..., "time_s": ...}` or `null`, and the keys `findings` (a list) and
`findings_omitted` (an integer) after `spec_url`. A finding is an object with the keys `code`,
`message`, `location` and `data`, in this order. A result with no findings has `"findings": []`
and `"findings_omitted": 0`.

**How:** The test parses the text of a matrix with every field set, and compares the lists of
keys and some values, also those of its finding. It checks the state text, the `null` location,
and the empty findings on a second matrix.

**Assumptions:** None.

#### `test_json_writes_a_float_that_is_not_finite_as_a_string`

**Checks:** `inf` and `-inf` are written as the strings "inf" and "-inf", in a value, a limit
and the time of a location. Strict JSON has no such number.

**How:** The test parses the text of a matrix with these values and checks the strings.

**Assumptions:** `to_json` writes `nan` as "nan" in the same way, and `from_json` reads it, but
no test covers it.

#### `test_json_writes_the_data_of_a_finding_with_its_types`

**Checks:** The `data` of a finding keeps the type of each value in the text: a string, an int
(written "7", not "7.0"), a float, a float with a whole value (written "2.0", not "2"), `true`,
`false` and `null`. A finding with no location has `"location": null`, and a location whose
block is `None` is written with `"block": null`. A finding with no data has `"data": {}`.

**How:** The test parses the text of a matrix with these findings and compares the objects. It
also looks for the text `"int": 7,` and `"whole float": 2.0,` in the written text, because
Python compares `7 == 7.0`.

**Assumptions:** None.

#### `test_json_writes_a_float_in_the_data_of_a_finding_that_is_not_finite_as_a_string`

**Checks:** `inf` and `-inf` in the `data` of a finding are written as the strings "inf" and
"-inf", and a finite float and an int next to them stay numbers. `from_json` reads the two
strings back as floats, and the int stays an `int`.

**How:** The test parses the text of a matrix with these values and compares the `data` object.
It reads the matrix back and checks the values and their types (`float` for the two infinities
and `int` for the int).

**Assumptions:** None.

#### `test_json_reads_nan_in_the_data_of_a_finding_as_a_float`

**Checks:** `nan` in the `data` of a finding is written as the string "nan", and `from_json`
reads it back as a float that is not a number.

**How:** The test writes a matrix with `nan` in a finding, checks the text, reads it back and
tests the value with `math.isnan`.

**Assumptions:** The test does not compare the matrices, because `nan != nan`.

#### `test_from_json_rejects_a_newer_format`

**Checks:** `from_json` raises `ValueError` for a format above `FORMAT` (format 2 now), and the
message names both versions (the format of the text and the format that the package reads).

**How:** The test changes `format` to `FORMAT + 1` in the JSON object of a matrix and matches
the two numbers in the message.

**Assumptions:** None.

#### `test_from_json_rejects_a_format_that_is_not_an_integer`

**Checks:** `from_json` raises `ValueError` for a `format` that is `null`, a string, a float or
a bool.

**How:** The test is parametrized over these values. It writes each one in the `format` key
and expects `ValueError`.

**Assumptions:** A bool is not an integer for this check, although Python counts `True` as an
`int`.

#### `test_from_json_rejects_a_missing_format`

**Checks:** `from_json` raises `ValueError` for an object that has no `format` key.

**How:** The test deletes `format` from the JSON object of a matrix and expects `ValueError`.

**Assumptions:** None.

#### `test_from_json_rejects_an_unknown_key`

**Checks:** An unknown key is a `ValueError` that names the key, in the matrix, in a target, in
a result, in a location, in a finding and in the location of a finding (the same rule as the
unknown keys of a profile).

**How:** The test is parametrized over the six places. It adds a key `extra` there and matches
the name in the message.

**Assumptions:** None.

#### `test_from_json_rejects_a_missing_key`

**Checks:** A missing key is a `ValueError` that names the key, in the matrix, in a target, in
a result, in a location, in the findings keys of a result (`findings`, `findings_omitted`), in a
finding (`message`, `data`) and in the location of a finding (`block`).

**How:** The test is parametrized over the nine places. It deletes one key there (`sequence`,
`sources`, `required`, `time_s`, `findings`, `findings_omitted`, `message`, `data`, `block`)
and matches the name in the message.

**Assumptions:** None.

#### `test_from_json_rejects_a_bad_finding`

**Checks:** A finding of the wrong type in the JSON text is a `ValueError` (not a `TypeError`):
`findings` that is an object or `null`; a finding that is a string; a `code` that is an integer
or empty; a `message` that is `null`; `data` that is a list; a data value that is a list or an
object; a `location` that is an integer; a location time that is a string other than "inf",
"-inf" or "nan".

**How:** The test is parametrized over eleven cases. It sets the value in the JSON object of a
matrix with a finding and expects `ValueError`.

**Assumptions:** A caller of `from_json` catches one type for a bad text, as for the other
objects.

#### `test_from_json_rejects_a_findings_omitted_that_is_not_an_integer_of_0_or_more`

**Checks:** `findings_omitted` that is a string, a float (also one with a whole value), a bool,
a negative integer, `null` or a list is a `ValueError` that names the key.

**How:** The test is parametrized over these values. It sets each one in the JSON object of a
matrix and matches the name in the message.

**Assumptions:** A bool is not an integer for this check, as for `format`.

#### `test_from_json_keeps_a_data_string_that_is_not_a_non_finite_float`

**Checks:** A string in the `data` of a finding that is not "inf", "-inf" or "nan" (here
"infinity") stays a string.

**How:** The test sets this string as a data value in the JSON object of a matrix, reads the
text and compares the value.

**Assumptions:** None.

#### `test_finding_rejects_a_bad_value`

**Checks:** `Finding.__post_init__` refuses each of these: a `code` that is not a string
(`TypeError`) or is empty (`ValueError`); a `message` that is not a string; a `location` that is
not a `Location` or `None` (a tuple, an integer); `data` that is not a mapping; a key of `data`
that is not a string; a value of `data` that is a list, a dict or bytes (`TypeError`); and a
string value of `data` that is "inf", "-inf" or "nan" (`ValueError`).

**How:** The test is parametrized over fifteen cases. Each gives the arguments of `Finding` and
the type of the error that it expects.

**Assumptions:** The plan does not list the check that `data` is a mapping. The code makes it,
because `data.items()` needs one.

#### `test_finding_accepts_each_type_of_data_value`

**Checks:** A `Finding` accepts a string, an int, a float, `inf`, `nan`, a bool and `None` as
data values, also the string "Inf" (which is not one of the three refused strings). The
default `data` is an empty mapping and the default `location` is `None`.

**How:** The test makes one `Finding` with these values and a location, and checks the bool
value, the default `data` and the default `location` of a second one.

**Assumptions:** None.

#### `test_a_result_has_no_findings_by_default`

**Checks:** A `Result` made with no findings arguments has `findings == ()` and
`findings_omitted == 0`.

**How:** The test makes a `Result` and compares the two fields.

**Assumptions:** None.

#### `test_with_max_findings_zero_keeps_none_and_counts_all`

**Checks:** `with_max_findings(0)` keeps no finding in any result, and adds the number of
findings that it removed to `findings_omitted`: 3 findings with 2 omitted before give 5, and a
result with no findings keeps its 2.

**How:** The test makes a matrix of two results with 3 and 0 findings and a `findings_omitted`
of 2, calls the method and compares the two fields of each result.

**Assumptions:** None.

#### `test_with_max_findings_below_the_count_keeps_the_first_ones`

**Checks:** For a result with 5 findings, `with_max_findings(2)` keeps the first two (in their
order), and `findings_omitted` is 3. The other fields of the result and the targets are the
same, and the matrix that the method was called on does not change.

**How:** The test calls the method and compares the codes of the kept findings, the count, the
`check_id`, the targets and the fields of the original matrix.

**Assumptions:** None.

#### `test_with_max_findings_at_or_above_the_count_changes_nothing`

**Checks:** When `n` is equal to the largest number of findings of a result, or larger, the new
matrix is equal to the old one, with the existing `findings_omitted` (7) unchanged.

**How:** The test is parametrized over `n` of 3, 4 and 100, on a matrix with results of 3 and 1
findings. It compares the matrices with `==`.

**Assumptions:** None.

#### `test_with_max_findings_adds_to_an_existing_findings_omitted`

**Checks:** The number of removed findings is added to the `findings_omitted` that the result
had: 4 findings with 10 omitted and `n` of 1 give 13. A second call with 0 gives 14.

**How:** The test calls the method and compares the counts.

**Assumptions:** None.

#### `test_with_max_findings_limits_each_result_separately`

**Checks:** In a matrix with results of 1, 3 and 5 findings, `with_max_findings(2)` keeps 1, 2
and 2 findings, and `findings_omitted` is 0, 1 and 3.

**How:** The test calls the method and compares the two lists.

**Assumptions:** None.

#### `test_with_max_findings_survives_a_json_round_trip`

**Checks:** The matrix that `with_max_findings` gives is equal to its own read-back from the
JSON text, so the removed findings stay visible in `findings_omitted`.

**How:** The test limits the matrix with findings to 1, writes the text, reads it back and
compares the matrices.

**Assumptions:** None.

#### `test_with_max_findings_rejects_a_bad_n`

**Checks:** `with_max_findings` raises `ValueError` for a negative integer, a bool, a float
(also one with a whole value), a string and `None`. The message names the maximum number of
findings.

**How:** The test is parametrized over these values and matches the message.

**Assumptions:** A bool is not an integer for this check, as for `format`.

### 2.10 The run function (`test_run.py`)

These tests check `run_checks`, the `RunContext` that it gives to a rule, `spec_url`, and
the entry-point registry (`registry.py`). No test uses an installed check. Each test
defines its own check rules: a small class with a `CheckSpec` and a `run` function. A test
installs them by replacing `registry.check_rules` with monkeypatch. The registry tests
replace `importlib.metadata.entry_points` and use fake entry points with a name, a `load`
function and a `dist` with a package name. The targets are `TargetProfile` objects that the
test builds directly (`make_profile`), so the tests do not read a profile file. The tests
read the results from `ResultMatrix.results` and `ResultMatrix.targets`, and do not use the
exit status or the JSON form. The sequences are `spin_echo_sequence()` of
`tests/synthetic.py`, as an object or as a `.seq` file in `tmp_path`.

#### `test_a_missing_input_gives_not_evaluated_and_run_is_not_called`

**Checks:** When a target does not give one of the inputs of a check, the result is "not
evaluated", its reason names the missing input and not the present one, and `run` is not
called.

**How:** The test makes a rule with two inputs, `opts.max_grad` and `opts.max_slew`, and a
target that gives only the first. It runs the check and checks the state, the reason, the
check ID, the specification version and the target name of the result, and that the rule
has no call.

**Assumptions:** The rule counts its calls itself. The test does not check the complete
text of the reason.

#### `test_a_missing_model_gives_not_evaluated_and_run_is_not_called`

**Checks:** When a target does not have one of the models of a check, the result is "not
evaluated", its reason names the missing model and not the present one, and `run` is not
called.

**How:** The test makes a rule with the models `m.one` and `m.two`, and a target with only
`m.one`. It checks the state, the reason, and that the rule has no call.

**Assumptions:** The model parameters of the test target are empty dicts. The function
checks only the keys of `TargetProfile.models`.

#### `test_a_rule_with_its_input_and_model_is_called`

**Checks:** When the target gives each input and each model of a check, `run` is called one
time and its result is in the matrix.

**How:** The test makes a rule with one input and one model, and a target that has both. It
checks that the state is "pass" and that the rule has one call.

**Assumptions:** None.

#### `test_an_exception_of_run_gives_error_and_the_other_checks_run`

**Checks:** An exception of `run` gives the state "error" with the reason
`"<exception type>: <message>"`, and the other checks of the run still give their results.

**How:** The test makes a rule that raises `ValueError("a test failure")` and a rule that
passes, and runs both on one target. It checks the state and the reason of the first, and
the state of the second.

**Assumptions:** The test does not raise an exception that is not a subclass of
`Exception`.

#### `test_a_result_for_another_check_or_target_gives_error`

**Checks:** A rule whose result has a different check ID, a different target, or is not a
`Result` gives the state "error" for its own check ID, with a reason that names the
difference.

**How:** The test makes three rules: one that returns a result of a different specification,
one that returns a `Result` for the target `other`, and one that returns `None`. It checks
that each result has the state "error", the check ID of its rule, and a reason that has the
other check ID, the other target name, or `NoneType`.

**Assumptions:** The test does not check the complete text of the reasons.

#### `test_a_result_of_a_rule_keeps_its_fields_and_gets_the_spec_link`

**Checks:** `ctx.result` fills the check ID, the specification version, the target name and
the link to the specification, and keeps the fields that the rule gives. The run function
leaves a result that is correct as it is, and sets `required` to False for a check that is
not required.

**How:** The test makes a rule that returns a failing result with a value, a limit, a unit
and a location. It compares the complete result with an expected `Result`. The link is the
documentation URL with the ID `t.a.b` without its dots.

**Assumptions:** The test repeats the rule for the link (`DOCS_URL` and the ID without dots)
and does not check that the heading exists in `docs/checks.md`.

#### `test_the_findings_of_a_rule_arrive_in_the_matrix_unchanged`

**Checks:** The findings and the `findings_omitted` that a rule gives are in the result of
the matrix without a change, with and without `findings_omitted`, and the run function still
sets `required`.

**How:** The test makes two rules, one with two findings and a `findings_omitted` of 3 and
one with the same findings and no `findings_omitted`. It runs both, with the first one
required for all targets. It checks the state, the findings, `findings_omitted` (3, and the
default 0) and `required` of each result.

**Assumptions:** The findings are valid `Finding` objects, one with a location and data and
one without.

#### `test_findings_that_are_not_valid_give_error`

**Checks:** When a rule gives findings as a list, a finding that is not a `Finding` (a
string, also an empty string), or a `findings_omitted` of -1, of True or of 1.5, the state
is "error", the reason names the problem, and the result has no findings of the rule.

**How:** One parametrized test. For each case, a rule makes its result with `ctx.result` and
the bad field. The test checks that the state is "error", that the reason has the word that
names the problem ("findings", "str" or "findings_omitted"), and that `findings` is empty and
`findings_omitted` is 0.

**Assumptions:** `Result` does not check its own fields, so a rule can make a result with a
bad field. The test does not check the complete text of the reason.

#### `test_spec_url_is_the_url_of_the_spec_or_the_heading_of_its_id`

**Checks:** `spec_url` gives `spec.url` when it is not `None`, and otherwise the
documentation URL with the ID without its dots. It keeps the hyphens of an ID.

**How:** The test calls `spec_url` for `gradient.slew.axis`, for `a.b-c` and for a
specification with its own URL, and compares the values.

**Assumptions:** None.

#### `test_the_matrix_has_the_sequence_the_version_and_the_targets`

**Checks:** The matrix has `sequence` as the string of the path (for a `str` and for a
`Path`) or `"<Sequence object>"`, `package_version` as the installed version of
`pulseq-checks`, and one `TargetInfo` for each target with its name, its sources, its unused
sections and the limits source `"profile"`.

**How:** The test runs one check for a target with one source and one unused section, with
a path, with a `Path` and with an object. It compares the fields of the matrix with the
expected values.

**Assumptions:** The installed version is correct (`test_package.py` checks it against
`pyproject.toml`).

#### `test_the_results_are_in_the_order_of_the_targets_and_the_check_ids`

**Checks:** The results are in the order of the targets, and for each target in the order of
the check IDs, whatever the order in which the registry gives the rules. The targets of the
matrix are in the order of the call.

**How:** The test installs three rules in the order `t.b`, `t.a`, `t.c` and runs two
targets, `y` and `x`. It compares the list of target and check ID of each result, and the
names of the targets.

**Assumptions:** None.

#### `test_measure_runs_one_time_for_each_target`

**Checks:** `ctx.measure` calculates a value one time for each name and target: two rules of
one target get the same object, and two targets calculate it two times, each one on its own
sequence.

**How:** The test installs two rules that call `ctx.measure("m", fn)`, and runs a `.seq` file
for two targets. `fn` counts its calls. The test checks that there are two calls, with two
different sequence objects, that the two rules of one target got the same value, and that
the two targets got different values.

**Assumptions:** The rules run in the same process, one after the other.

#### `test_measure_keeps_a_value_for_each_name`

**Checks:** `ctx.measure` keeps one value for each name. A second call with the same name
gives the first value and does not call the new function. A different name calls its
function.

**How:** A rule calls `ctx.measure` with `"one"`, with `"two"` and again with `"one"` and a
function that would give a different value. It checks the three values.

**Assumptions:** None.

#### `test_required_for_all_targets_with_none`

**Checks:** A check that `required` maps to `None` is required for each target, and a check
that it does not name is not required.

**How:** The test runs two checks on two targets with `required={"t.a": None}` and compares
the `required` field of each result.

**Assumptions:** None.

#### `test_required_for_named_targets`

**Checks:** A check that `required` maps to a list of target names is required only for
those targets.

**How:** The test runs one check on the targets `x` and `y` with `required={"t.a": ["y"]}`.
It checks that the result for `x` is not required and the result for `y` is required.

**Assumptions:** None.

#### `test_required_is_set_for_not_evaluated_and_error_results`

**Checks:** The field `required` is True also for a required check that gave "not
evaluated" (from the run function) or "error" (from an exception).

**How:** The test makes a rule with a missing input and a rule that raises an exception,
and makes both required for the one target. It checks the state and `required` of each
result.

**Assumptions:** None.

#### `test_required_with_an_unknown_check_id_is_an_error`

**Checks:** A check ID in `required` that no installed rule has is a `RunError` that names
the ID.

**How:** The test calls `run_checks` with `required={"t.unknown": None}` and checks the
exception and its message.

**Assumptions:** None.

#### `test_required_with_an_unknown_target_is_an_error`

**Checks:** A target name in `required` that is not a target of the run is a `RunError`
that names the target.

**How:** The test calls `run_checks` with `required={"t.a": ["nowhere"]}` for one target
named `a` and checks the exception and its message.

**Assumptions:** None.

#### `test_select_runs_only_the_selected_checks`

**Checks:** With `select`, only the named checks run, in the order of their IDs. With no
`select`, all installed checks run.

**How:** The test installs three rules and runs with `select=["t.c", "t.a"]`. It checks the
check IDs of the results and that the rule `t.b` has no call. It then runs with no `select`
and checks that all three give a result.

**Assumptions:** None.

#### `test_select_with_an_unknown_check_id_is_an_error`

**Checks:** A check ID in `select` that no installed rule has is a `RunError` that names the
ID.

**How:** The test calls `run_checks` with `select=["t.a", "t.unknown"]` and checks the
exception and its message.

**Assumptions:** None.

#### `test_a_required_check_runs_when_select_does_not_name_it`

**Checks:** The checks that run are the selected checks and the required checks. A required
check that `select` does not name runs and is marked as required.

**How:** The test installs three rules and runs with `select=["t.a"]` and
`required={"t.c": None}`. It compares the check ID and the `required` field of each
result.

**Assumptions:** None.

#### `test_fast_only_runs_the_fast_checks_and_the_slow_required_checks`

**Checks:** With `fast_only`, a slow check that is not required does not run, a slow check
that `required` names runs (also when it names no target for it), and `fast_only` does not
make a check required (R4).

**How:** The test installs one fast rule and three slow rules. One slow rule is required
for all targets, one has an empty list of target names in `required`, and one is not
required. It runs with `fast_only=True` and compares the check ID and `required` of each
result.

**Assumptions:** None.

#### `test_fast_only_with_select_removes_the_slow_selected_checks`

**Checks:** With `fast_only` and `select`, a slow check that `select` names and that is not
required does not run, and a fast check that `select` does not name does not run.

**How:** The test installs two fast rules and one slow rule, and runs with
`select=["t.fast", "t.slow"]` and `fast_only=True`. It checks that only `t.fast` gives a
result.

**Assumptions:** None.

#### `test_a_path_is_read_one_time_for_each_target_with_the_opts_of_that_target`

**Checks:** For a path, the run function reads the `.seq` file one time for each target,
with the `Opts` of that target (decision 3): each target has its own `Sequence` object, and
its `system.adc_dead_time` is the value of that target.

**How:** The test replaces `pp.Sequence.read` with a function that counts its calls and
calls the real one. It runs a `.seq` file of the spin-echo sequence for two targets with
the ADC dead times 5 µs and 40 µs. It checks that there are two reads of the path, with two
different objects, that the rule sees these objects in the order of the targets, that each
has the dead time of its target and the number of blocks of the file.

**Assumptions:** `Sequence.read` keeps the `Opts` of the constructor in `seq.system` (the
test checks it only through the dead time). The test does not check that an ADC event of
the file has the dead time.

#### `test_a_path_that_cannot_be_read_is_an_error_that_names_the_file_and_the_target`

**Checks:** An exception of the read of a `.seq` file is a `RunError` that names the file,
the target and the exception type.

**How:** The test runs a path that does not exist, and a file with text that is not a
sequence, for the target `scanner`. It checks that the message has the path and the target
name, and for the missing file `FileNotFoundError`.

**Assumptions:** pypulseq raises an exception for a file that is not a sequence. The test
does not check which one.

#### `test_a_sequence_object_is_used_for_its_one_target`

**Checks:** With a `Sequence` object and one target, the rule gets the same object, and the
limits source is `"profile"`.

**How:** The test runs a rule on an object and compares `ctx.sequence` with the object and
`ctx.limits_source` with `"profile"`.

**Assumptions:** None.

#### `test_a_sequence_object_with_two_targets_is_an_error`

**Checks:** A `Sequence` object with two targets is a `RunError` that says that an object
gives exactly one target.

**How:** The test calls `run_checks` with an object and two targets and checks the
exception and its message.

**Assumptions:** None.

#### `test_no_target_is_an_error`

**Checks:** An empty list or tuple of targets is a `RunError`, for a path and for an
object.

**How:** The test calls `run_checks` with no target and a path, and with no target and an
object, and checks the exception and its message.

**Assumptions:** None.

#### `test_two_targets_with_one_name_are_an_error`

**Checks:** Two targets with one name are a `RunError` that names it.

**How:** The test calls `run_checks` with the targets `x`, `y`, `x` and checks the
exception and its message.

**Assumptions:** None.

#### `test_limits_from_sequence_takes_the_limits_of_seq_system_for_a_target_with_none`

**Checks:** With `limits_from_sequence=True`, a `Sequence` object and a target with neither
`opts.max_grad` nor `opts.max_slew`, the context has `limits_source` `"sequence object"`
and the limits of `seq.system` in mT/m and T/m/s with the label `"sequence object"`. A
check that needs `opts.max_grad` and `opts.max_slew` is called, and the matrix records the
limits source of the target.

**How:** The test runs a rule with these two inputs on the spin-echo sequence (28 mT/m and
150 T/m/s) and a target that gives no value. It checks the limits of the context with
`pytest.approx`, the label, the limits source of the context and of `TargetInfo`, and that
the result is "pass".

**Assumptions:** The limits are the values of `SYSTEM` in `tests/synthetic.py`. The test
does not check the conversion of the units in another way than through these values.

#### `test_a_target_with_limits_keeps_its_limits_with_limits_from_sequence`

**Checks:** With `limits_from_sequence=True`, a target that gives both limits keeps its own
`hardware_limits` and the limits source `"profile"`.

**How:** The test runs a rule on a target with both inputs and its own `HardwareLimits`. It
compares `ctx.hardware_limits` with the profile limits, and the limits source of the
context and of the matrix with `"profile"`.

**Assumptions:** None.

#### `test_a_target_with_one_limit_keeps_its_profile_with_limits_from_sequence`

**Checks:** With `limits_from_sequence=True`, a target that gives only one of the two limits
does not get the limits of the sequence: the limits source is `"profile"`, and a check that
needs the other limit is "not evaluated".

**How:** The test runs a rule with the inputs `opts.max_grad` and `opts.max_slew` on a
target that gives only the first. It checks the limits source, the state and that the
reason names `opts.max_slew`.

**Assumptions:** None.

#### `test_without_limits_from_sequence_a_target_with_no_limits_is_not_evaluated`

**Checks:** Without the opt-in, a target with no gradient limits gives "not evaluated" for
a check that needs one, also for a `Sequence` object, and the limits source is `"profile"`.

**How:** The test runs a rule with the input `opts.max_grad` on an object and a target with
no input. It checks the state, the limits source of the matrix and that the rule has no
call.

**Assumptions:** None.

#### `test_limits_from_sequence_with_a_path_is_an_error`

**Checks:** `limits_from_sequence=True` with a path, as a `str` or as a `Path`, is a
`RunError`.

**How:** The test calls `run_checks` with the path and the opt-in in both forms and checks
the exception and that its message names `limits_from_sequence`.

**Assumptions:** None.

#### `test_has_input_is_true_for_a_value_path_of_the_profile_only_without_the_opt_in`

**Checks:** `ctx.has_input` is True for a value path that the profile gives. With the limits
source `"sequence object"` it is also True for `opts.max_grad` and `opts.max_slew`, and not
for another path.

**How:** The test makes a context for a target with `opts.max_grad`, without and with the
limits source `"sequence object"`, and checks `opts.max_grad`, `opts.max_slew` and
`opts.adc_dead_time`.

**Assumptions:** The test calls `RunContext` directly, and does not use the run function.

#### `test_check_rules_are_keyed_by_spec_id`

**Checks:** `registry.check_rules()` gives a dict of the loaded rules by `spec.id`, in any
order of the entry points.

**How:** The test installs two fake entry points and compares the dict with the expected
one.

**Assumptions:** `ep.load()` of a real entry point gives the rule object. The test uses
fake entry points and does not load a real one.

#### `test_two_check_rules_with_one_id_are_an_error_that_names_both_packages`

**Checks:** Two check entry points that give one check ID are a `RegistryError` that names
the ID and both packages.

**How:** The test installs two fake entry points with rules of the ID `t.a` and the
packages `pkg-one` and `pkg-two`, and checks the exception and its message.

**Assumptions:** The package name is `ep.dist.name` of the entry point.

#### `test_a_check_entry_point_that_cannot_be_loaded_is_an_error_that_names_it`

**Checks:** A check entry point whose `load` raises an exception is a `RegistryError` that
names the entry point, its package and the exception type and message.

**How:** The test installs a fake entry point whose `load` raises `ImportError` and checks
the message.

**Assumptions:** None.

#### `test_a_check_entry_point_without_a_spec_is_an_error_that_names_it`

**Checks:** A check entry point whose object has no `spec.id` is a `RegistryError` that
names the entry point.

**How:** The test installs a fake entry point that loads a plain `object()` and checks the
message.

**Assumptions:** None.

#### `test_models_are_keyed_by_name_and_two_with_one_name_are_an_error`

**Checks:** `registry.models()` gives the loaded models by `name`. Two models with one name
are a `RegistryError` that names the name and the package of the first. The second
entry point has no `dist`, and the error does not fail for it.

**How:** The test installs two models with different names and compares the dict. It then
installs two models with the name `m.one`, the second with no `dist`, and checks the
message.

**Assumptions:** None.

#### `test_a_model_entry_point_that_cannot_be_loaded_is_an_error_that_names_it`

**Checks:** A model entry point whose `load` raises an exception is a `RegistryError` that
names the entry point and its package.

**How:** The test installs a fake entry point whose `load` raises `RuntimeError` and checks
the message.

**Assumptions:** None.

#### `test_profile_reader_gives_the_reader_by_name_or_none`

**Checks:** `registry.profile_reader(name)` gives the loaded reader of that name, and
`None` when no entry point has the name, also when there is no entry point in the group.

**How:** The test installs two fake readers and calls the function for `siemens-asc`, for a
name that is not installed, and with no entry point in the group.

**Assumptions:** None.

#### `test_two_profile_readers_with_one_name_are_an_error_that_names_both_packages`

**Checks:** Two reader entry points with the name asked for are a `RegistryError` that
names both packages. A different name is not affected.

**How:** The test installs two fake readers named `siemens-asc` from `pkg-one` and
`pkg-two`, checks the message of the error, and checks that a name that is not installed
still gives `None`.

**Assumptions:** None.

### 2.11 Check configuration (`test_config.py`)

These tests check `read_check_config`. They write small TOML and JSON files in `tmp_path`.
No test reads a profile or uses the registry: the function does not read the target
profiles, and it does not compare the check IDs with the installed checks (`run_checks`
does).

#### `test_a_toml_file_gives_the_config`

**Checks:** A TOML file with each key gives the `CheckConfig` with the source path, the
format version, the target paths relative to the file, `select`, `required` (`true` as
`None`, a list as a tuple) and `fast_only`.

**How:** The test writes the file and compares the result with an expected `CheckConfig`.

**Assumptions:** None.

#### `test_the_toml_and_json_forms_give_equal_configs`

**Checks:** A TOML file and a JSON file with the same content give equal configs, except
for the source path.

**How:** The test reads both files and compares the two configs after it sets the source
path of the second to that of the first.

**Assumptions:** None.

#### `test_a_file_with_only_format_and_targets_gives_the_defaults`

**Checks:** With only `format` and `targets`, `select` is `None`, `required` is empty and
`fast_only` is False, in TOML and in JSON.

**How:** The test reads a TOML file and a JSON file with these two keys and checks the
defaults and that the two configs are equal.

**Assumptions:** None.

#### `test_target_paths_are_relative_to_the_config_file_not_to_the_working_directory`

**Checks:** The target paths are joined to the folder of the config file, as the function
was called, and not resolved against the working directory. An absolute target path stays
as it is.

**How:** The test writes a file in a sub-folder, changes the working directory to its
parent, and reads the file with a relative path and with an absolute path. It compares the
target paths and the source path.

**Assumptions:** The function does not call `resolve`, so a `..` stays in the path.

#### `test_a_config_does_not_read_the_profiles_or_check_the_check_ids`

**Checks:** A target file that does not exist, a check ID that no check has, and a target
name in `required` that no profile has are not errors of `read_check_config`.

**How:** The test writes a file with these names and checks that it reads and that the
config has the values.

**Assumptions:** `run_checks` makes these checks (tested in `test_run.py`).

#### `test_config_error_is_an_error_of_the_run`

**Checks:** `ConfigError` is a subclass of `CheckRunError`, so that the command gives exit
status 1 for it.

**How:** The test checks `issubclass`.

**Assumptions:** The command catches `CheckRunError` (phase 6).

#### `test_each_invalid_toml_config_is_an_error_that_names_the_file`

**Checks:** Each invalid config in TOML is a `ConfigError` that names the file and the
problem: no `format`, a newer format, a `format` that is not a whole number of 1 or more, no
`targets`, `targets` that is empty, not a list, not of strings or with an empty path, a
`select` that is not a list of strings, a `fast_only` that is not a boolean, a `required`
that is not a table, a `required` value that is not `true` or a list of strings, an unknown
key (also `limits_from_sequence`), and a file that is not valid TOML.

**How:** The test is parametrized with the text of each file and a part of the expected
message. For each one it writes the file, reads it, and checks the exception and that the
message has the path of the file and that part.

**Assumptions:** The tests check a part of the message and not the complete text.

#### `test_a_newer_format_names_both_versions`

**Checks:** A `format` above the version of the reader is a `ConfigError` that names the
file, the version of the file and the version of the reader.

**How:** The test writes a JSON file with `"format": 7` and checks that the message has the
file, `version 7` and `version 1`.

**Assumptions:** The version of the reader is 1.

#### `test_each_invalid_json_config_is_an_error_that_names_the_file`

**Checks:** The same rules apply to a JSON file: no `format`, an unknown key, a
`fast_only` that is `null`, a `required` value that is `null`, a top level that is not an
object, and a file that is not valid JSON are each a `ConfigError` that names the file.

**How:** The test writes a file for each case, reads it, and checks that the message has
the path and the part of the expected message.

**Assumptions:** The test checks a part of the message and not the complete text.

#### `test_a_missing_file_and_a_wrong_suffix_are_errors_that_name_the_file`

**Checks:** A file that does not exist and a suffix that is not `.toml` or `.json` are each
a `ConfigError` that names the file.

**How:** The test reads a path that does not exist and a `.yaml` file that exists, and
checks the exceptions and that the messages have the path.

**Assumptions:** None.

### 2.12 Siemens .asc profile reader (`test_asc_profile.py`)

These tests cover `asc_profile.read_asc_profile` for the SAFE parameters, the acoustic
resonances and the GPA limits of a `gradient_mode`. They use the `write_gradient_asc`
fixture of `tests/conftest.py`, which writes synthetic values with the PNS parameters of
pypulseq's example hardware (and, with its `gpa` keyword, synthetic amplitudes and rise
times for each mode), and lines that the tests append with synthetic resonances and GPA
fields. No test uses a real `.asc` file.

The reader supplies no default (decision R2): a group of values that the file has in part
(SAFE fields without all of them or without the gradient scale factors, a resonance without
its bandwidth) and a mode that the file does not have are a `ValueError`.

The last four tests read a profile file with `profile.read_profile`, which calls the
installed reader `siemens-asc` (plan section 4.3, rule 4, and section 4.9).

#### `test_read_asc_profile_gives_the_safe_parameters`

**Checks:** For the plain layout and for the split layout (an `ASCCONV` block with CRLF
line ends and a `$INCLUDE` file), the sections are `models.pns.safe` only, with `name`
and, for each of `x`, `y` and `z`, the nine float fields of `safe_example_hw()`. The
sources map `models.pns.safe` to the file name.

**How:** The test writes the file with the fixture, for each layout, and compares the
result of `read_asc_profile` with a dict that it builds from `safe_example_hw()`.

**Assumptions:** The fixture writes the values of `safe_example_hw()` with `repr`, so
that they read back exactly.

#### `test_read_asc_profile_with_a_missing_include_file_is_an_os_error`

**Checks:** A `$INCLUDE` file that is not in the directory is an `OSError`.

**How:** The test writes the split layout, deletes the included `_GSWD_SAFETY.asc` file,
and calls `read_asc_profile`.

**Assumptions:** `FileNotFoundError` is a subclass of `OSError`.

#### `test_read_asc_profile_gives_the_acoustic_resonances`

**Checks:** Both layouts that pypulseq reads (`aflGCAcousticResonanceFrequency`, and
`asGPAParameters[0].sGCParameters.aflAcousticResonanceFrequency`, each with its
bandwidths) give the same `[frequency, bandwidth]` float pairs, without the pair that has
frequency 0, and the source of `acoustic.resonances` is the file name. The SAFE section
stays. The second layout is tested in the plain and in the split file.

**How:** The test writes the file with the fixture, appends synthetic resonance lines (in
the split file, before the end of the `ASCCONV` block), and compares the result with the
expected pairs.

**Assumptions:** The frequency 0 is an unused entry, as in pypulseq's
`asc_to_acoustic_resonances`.

#### `test_read_asc_profile_gives_only_the_sections_that_the_file_has`

**Checks:** A file with no resonances has no `acoustic` section and no
`acoustic.resonances` source. A file with no SAFE parameters gives no sections and no
sources.

**How:** The test reads a fixture file without resonances, and a small `.asc` file with
only `asCOMP.tName`.

**Assumptions:** None.

#### `test_read_asc_profile_is_a_registered_profile_reader`

**Checks:** The entry-point group `pulseq_checks.profile_readers` has `siemens-asc`, and
it loads `read_asc_profile`.

**How:** The test reads the group with `importlib.metadata.entry_points` and loads the
entry point.

**Assumptions:** The installed metadata is current: after a change in `pyproject.toml`,
`uv sync --reinstall-package pulseq-checks` updates it.

#### `test_read_asc_profile_gives_the_gpa_limits_of_the_mode`

**Checks:** For each of the six modes (`absolute`, `normal`, `fast`, `ultrafast`,
`whisper`, `boost`), in the plain and in the split layout, `opts` has `max_grad` equal to
`flGradMaxAmpl<Mode>` and `max_slew` equal to `1000 / flGradMinRiseTime<Mode>` (exact float
equality; both are floats, also when the file has integers), with `grad_unit` `"mT/m"` and
`slew_unit` `"T/m/s"`. The four `opts.*` sources are `<file name> (<mode>)`, and the SAFE
section and its source are as without a mode.

**How:** The test writes a file with the six synthetic pairs of the fixture's `gpa`
keyword, reads it with each mode, and compares the result with the pair of that mode and
the same expression `1000 / rise_time`.

**Assumptions:** The Siemens units (amplitude in mT/m, rise time in µs per mT/m) of plan
section 2.3, fact 9. The values are synthetic and differ from mode to mode, so a reader
that takes the wrong mode fails.

#### `test_read_asc_profile_ignores_the_default_twins_of_the_gpa_fields`

**Checks:** A file whose `flDefGradMaxAmpl<Mode>` and `flDefGradMinRiseTime<Mode>` have
other values than the `flGrad...` fields gives the values of the `flGrad...` fields.

**How:** The test writes the `Fast` limits with the fixture, appends the two `flDefGrad...`
lines with other values (plain and split layout), and reads the mode `fast`.

**Assumptions:** The `flDefGrad...` fields are twins that hold the default, and the
reader uses `flGrad...` (plan section 2.3, fact 9).

#### `test_read_asc_profile_without_a_gradient_mode_gives_no_opts`

**Checks:** Without `gradient_mode`, there is no `opts` section and no `opts.*` source,
also when the file has the GPA fields of all modes.

**How:** The test writes a file with the six modes and reads it without a mode.

**Assumptions:** There is no default mode, because there are no default limits (R2).

#### `test_read_asc_profile_with_an_unknown_gradient_mode_is_a_value_error`

**Checks:** The modes `nominal` (it has no rise time), `Fast` and `UltraFast` (a wrong
case), `turbo` and the empty string are a `ValueError` that names all six known modes,
also when the file has limits of a `Nominal` mode.

**How:** The test writes a file with the six modes and a `Nominal` pair, and reads it with
each mode.

**Assumptions:** The mode names of the profile are lower case (plan section 4.4).

#### `test_read_asc_profile_with_a_mode_that_the_file_does_not_have_is_a_value_error`

**Checks:** A mode whose amplitude field is missing, whose rise time field is missing, or
that has neither, is a `ValueError` that names the file, the mode and the first missing
field.

**How:** The test writes a file with the `Fast` limits, appends none, one or the other of
the `Boost` lines, and reads the mode `boost`.

**Assumptions:** The limits of another mode in the file are not a substitute.

#### `test_read_asc_profile_with_an_invalid_gpa_value_is_a_value_error`

**Checks:** An amplitude or a rise time that is 0, negative, infinite, or a string is a
`ValueError` that names the file, the mode and the field.

**How:** The test writes a file, appends the two `Fast` lines with one of the values of a
list (`0.0`, `0`, `-5.0`, `1e999`, `"text"`), and reads the mode `fast`.

**Assumptions:** `readasc` reads `1e999` as `inf`. A rise time of 0 would be a division
by zero.

#### `test_read_asc_profile_with_safe_parameters_but_no_scale_factor_is_a_value_error`

**Checks:** A file with the `flGSWD*` fields but without one of the gradient scale factors
(`flGScaleFactorX`, `Y`, `Z`), or without all three, is a `ValueError` that names the file
and the first missing field, in the plain and in the split layout.

**How:** The test writes the fixture file, removes the scale factor lines, and reads it.

**Assumptions:** pypulseq's `asc_to_hw` would assume 1/pi and print a warning; the reader
does not supply that default (R2).

#### `test_read_asc_profile_with_some_safe_fields_but_not_all_is_a_value_error`

**Checks:** A file that has some `flGSWD*` fields but lacks one (an entry of an array, a
stimulation limit) is a `ValueError` "incomplete SAFE parameters" that names the file, in
the plain layout and in the split layout (where the field is in the `$INCLUDE` file).

**How:** The test writes the fixture file, removes one `flGSWD*` line, and reads it.

**Assumptions:** None.

#### `test_read_asc_profile_with_mismatched_acoustic_resonances_is_a_value_error`

**Checks:** In both layouts, frequencies without a bandwidth list, bandwidths without a
frequency list, a bandwidth list with one entry less, and a bandwidth list with the same
count but another index are a `ValueError` that names the file.

**How:** The test appends the lines of each layout with one of the four changes and reads
the file.

**Assumptions:** `readasc` gives a list as a dict of index to value, and a frequency and a
bandwidth are a pair when they have the same index, so the reader compares the index
sets, not only the counts. A missing bandwidth list would be a `KeyError` in pypulseq, and
a shorter one would drop the last resonances without a message.

#### `test_read_profile_gives_the_gpa_limits_of_the_asc_file`

**Checks:** A profile that names an `.asc` file and the mode `fast` gets the GPA limits of
that mode (50 mT/m, and 1000 / 10 = 100 T/m/s) in its `hardware_limits`, and the source of
the four `opts` values is the file name followed by ` (fast)`.

**How:** The test writes an `.asc` file with the `gpa` keyword of `write_gradient_asc` and a
profile file next to it, and reads the profile with `read_profile`. It compares the limits
with a relative tolerance of 1e-12 and the four sources exactly.

**Assumptions:** The entry point `siemens-asc` is installed (`uv sync` after the change of
`pyproject.toml`). The limits go through `pp.Opts`, which stores them in Hz/m and Hz/m/s
and back, so they are equal only to rounding.

#### `test_read_profile_with_max_grad_and_a_gradient_mode_is_an_error`

**Checks:** A profile that gives `max_grad` in `[opts]` and also selects a mode of its
`.asc` file is a `ProfileError` that names `opts.max_grad`, the source `profile` and the
source of the `.asc` file with the mode.

**How:** The test writes the `.asc` file and a profile with `asc`, `asc_gradient_mode` and
`max_grad = 80`, and matches the message of the error.

**Assumptions:** None.

#### `test_read_profile_with_a_gradient_mode_and_no_asc_is_an_error`

**Checks:** A profile with `asc_gradient_mode` and no `asc` is a `ProfileError`.

**How:** The test writes such a profile and matches `asc_gradient_mode` in the message.

**Assumptions:** None.

#### `test_read_profile_with_an_unknown_gradient_mode_is_an_error`

**Checks:** The `ValueError` of the reader for the unknown mode `nominal` reaches the caller
of `read_profile` as a `ProfileError` that names the `.asc` file.

**How:** The test writes the `.asc` file and a profile with `asc_gradient_mode =
"nominal"`, and matches the file name in the message.

**Assumptions:** None.

### 2.13 Timing checks (`test_check_timing.py`)

These tests cover the two timing checks of `checks/timing.py`: `timing.rasters` (`RASTERS`)
and `timing.pypulseq` (`PYPULSEQ`). They do not use the installed checks and do not need
the other checks of the package: the tests replace `registry.check_rules` with monkeypatch
so that it gives the two timing checks only, and they select one check with `select`. A
few tests call `rule.run` directly with a `RunContext` that they build. The sequence is a
`.seq` file that a test writes in `tmp_path` with `seq.write`: a delay of 1 ms, an RF
pulse with a delay of 100 µs, a delay of 2 ms and a second RF pulse (from
`block_pulse` of `tests/synthetic.py`). It has no gradient and no ADC. The raster tests
change the [DEFINITIONS] entries of the file before they write it, because the check
reads only the declared values. The targets are `TargetProfile` objects that the tests
build directly (`make_target`), with the rasters 10 µs (gradient), 1 µs (RF), 100 ns (ADC)
and 10 µs (block duration), and the RF dead time 100 µs, RF ringdown 20 µs and ADC dead
time 10 µs, unless a test says otherwise.

The tests of the findings of `timing.pypulseq` use two more sequences. `error_sequence` is
the sequence above and a fifth block with an ADC (a delay of 10 µs, 64 samples of 20 µs),
written as a `.seq` file. The test reads it with the `Opts` of a target with an RF dead
time of 200 µs, an RF ringdown of 50 µs and an ADC dead time of 30 µs (`ERROR_OPTS`), so
that `check_timing` gives BLOCK_DURATION_MISMATCH, RF_DEAD_TIME and RF_RINGDOWN_TIME in
blocks 2 and 4, and BLOCK_DURATION_MISMATCH, ADC_DEAD_TIME and POST_ADC_DEAD_TIME in block
5. `raster_error_sequence` has a delay of 1 ms, an ADC with a dwell of 20051.5 ns and a
delay of 1001.23 µs. It stays in memory, because pypulseq does not write a block whose
duration is not on the raster, and it gives three RASTER errors. The expected values of
`data` are computed by hand from the parameters of the sequences. The tests compare a
message with the text that `print_error_report` of pypulseq prints.

The tests of the findings of `timing.rasters` use the same files and the same direct calls
as its other tests. The expected values of `data` are the target rasters and the factors
that the test gives to the declared rasters.

#### `test_equal_rasters_pass`

**Checks:** With a file that declares the rasters of the target, the result is "pass"
with the unit `s` and no location. Its value is the gradient raster of
the file, its limit the gradient raster of the target, and its reason (the detail of a
pass or a fail) starts with `GradientRasterTime: `.

**How:** The test writes the file with the four rasters of the target, runs
`timing.rasters` through `run_checks`, and checks the fields of the result.

**Assumptions:** When the deviations of all rasters are equal, the result shows the first
raster (the gradient raster). The test checks only the start of the reason text.

The result of a pass also has no findings and no omitted findings.

#### `test_equal_rasters_fail_when_one_raster_differs`

**Checks:** A file where one of the four rasters is 1.5 times the raster of the target
gives "fail", with the file raster as the value and the target raster as the limit. The
test does this for each raster.

**How:** For each of the four names, the test writes a file where that raster is 1.5 times
the target value, and runs the check. It checks the state, the value (to the nine digits
that the file keeps), the limit, the unit, the location, and that the reason starts with
the name of that raster.

**Assumptions:** The gradient raster and the block duration raster of the target are both
10 µs, so for these two names the test does not tell which of the two the result shows.
The test with the worst raster tells it apart.

#### `test_the_worst_raster_is_the_one_with_the_largest_deviation`

**Checks:** When two rasters differ, the value and the limit of the result are those of the
raster with the largest relative deviation.

**How:** The test writes a file where the gradient raster is 1.1 times the target value and
the ADC raster is 1.5 times. It checks the "fail" state, and that the value is the ADC
raster of the file (150 ns) and the limit the ADC raster of the target (100 ns).

**Assumptions:** The deviation is the relative one of the specification, so the ADC raster
(0.5) is worse than the gradient raster (0.1) although both differences in seconds are
small.

#### `test_rasters_fail_when_the_file_raster_is_a_ratio_other_than_one`

**Checks:** A file raster that is half, two times or three times the raster of the target
gives "fail", for each of the four rasters, with the file raster as the value and the
target raster as the limit. Version 1 has no rule for unequal rasters, so neither a
finer raster nor an integer multiple passes.

**How:** The test is parametrized over the three ratios and the four names. It writes a
file where that raster is the ratio times the target value (the others are equal), runs
the check, and checks the state "fail", the value (to the nine digits that the file keeps)
and the limit.

**Assumptions:** None.

#### `test_the_tolerance_of_a_raster_is_relative_1e_8`

**Checks:** A file raster that differs from the target raster by a relative 5e-9 (the
rounding of a nine-digit definition) passes, and one that differs by 1e-7 fails, in both
directions.

**How:** The test sets the four definitions of a `pp.Sequence` to the target values times
a factor (1 ± 5e-9 and 1 ± 1e-7), runs `RASTERS.run` with a `RunContext`, and checks the
state. It also checks the number of findings: none for a raster within the tolerance, and
one for each of the four rasters outside it.

**Assumptions:** The test sets the definitions in the object and does not write a file, so
it does not test the nine-digit rounding of the file itself. The tolerance is 1e-8. All
four rasters have the same factor, so the findings are all or none.

#### `test_a_raster_that_the_file_does_not_declare_gives_error`

**Checks:** A file that does not declare one of the four rasters gives "error" with a
reason that names the raster, and no value and no limit. The test does this for each
raster.

**How:** For each name, the test removes that definition from the sequence before it writes
the file, runs the check, and checks the state, that the name is in the reason, and that
the value and the limit are None.

**Assumptions:** The test writes a file of format 1.5.0, where the four definitions are
required. A file of a format older than 1.4.0 is not tested: pypulseq fills its missing
definitions with the rasters of the target when it reads the file, so the check cannot see
the missing declaration (see the specification of `timing.rasters`). pypulseq warns for a
missing block duration raster, and the test ignores this warning.

#### `test_a_declared_raster_that_is_not_one_positive_number_gives_error`

**Checks:** A declared raster that is a string, a list of two numbers, zero, negative,
"not a number" or infinite gives "error" with a reason that names the raster.

**How:** For each value, the test sets the gradient raster definition of a `pp.Sequence`
to it and runs `RASTERS.run` with a `RunContext`. It checks the state and that the name is
in the reason.

**Assumptions:** The test sets the values in the object and does not write a file, because
pypulseq uses a declared raster when it reads the file. The other three definitions are
not set, so the reason also names them as not declared; the test checks only that it names
the gradient raster, and not its complete text.

#### `test_a_raster_that_differs_gives_one_mismatch_finding`

**Checks:** A file where one of the four rasters is 1.5 times the raster of the target
gives "fail" and exactly one finding with the code RASTER_MISMATCH and no location. Its
`data` has the name of the raster, `file_s` (1.5 times the target), `target_s` and the
deviation 0.5, all Python types. Its message is `<name>: <F> s in the file, <T> s on the
target`, and it is the reason of the result, which keeps its value (the file raster) and
its limit (the target raster).

**How:** For each of the four names, the test writes the file, runs `timing.rasters`
through `run_checks`, and compares the finding with the expected values (the numbers to a
relative 1e-6, because the file keeps nine digits) and the types with `type(v) in
(str, int, float, bool, NoneType)`. The message is built from the value of the result.

**Assumptions:** The test builds the expected message with the same form as the check, so
it tests that the message and the reason are the same text and that the numbers are those
of the result, not the wording of the text.

#### `test_two_rasters_that_differ_give_two_findings_in_the_order_of_the_rasters`

**Checks:** When two rasters differ, the result is "fail" with two RASTER_MISMATCH
findings, in the order GradientRasterTime, RadiofrequencyRasterTime, AdcRasterTime,
BlockDurationRaster, and not in the order of the deviation. The value and the limit are
still those of the raster with the largest deviation.

**How:** The test has two cases. In the first, the RF raster is 1.1 times and the ADC
raster is 1.5 times the target, so the later raster of the two (ADC) has the larger
deviation. In the second, the gradient raster is 2 times and the block duration raster 1.1
times, so the earlier raster of the two has the larger deviation. The test checks the names of the findings in the
order, their `data` and that the reason and the limit are those of the worst raster.

**Assumptions:** The rasters that the test does not change equal the target, so they give
no finding.

#### `test_a_raster_that_the_file_does_not_declare_gives_one_finding`

**Checks:** A file that does not declare one of the four rasters gives "error" and one
finding with the code RASTER_NOT_DECLARED, no location, the message `the file does not
declare <name>` (also the reason of the result) and `data` with the name and `target_s`
only.

**How:** For each name, the test removes the definition before it writes the file, runs the
check, and compares the finding.

**Assumptions:** As in `test_a_raster_that_the_file_does_not_declare_gives_error`: the file
has format 1.5.0, and the warning of pypulseq for a missing block duration raster is
ignored.

#### `test_a_declared_raster_that_is_not_valid_gives_one_invalid_finding`

**Checks:** A declared gradient raster that is a string, a list of two numbers (an array),
a list with one number, a bool, zero, negative (also in an array of one element), "not a
number" or infinite (both signs) gives "error" and one RASTER_INVALID finding with no
location and the message that is the reason of the result. Its `data` has, in this order,
the name, `declared` and `target_s`. `declared` is a Python `float` when the value is one
number (also when it is zero, negative or not finite), and else the `repr` text of the value
(a `str`).

**How:** The test sets the four definitions of a `pp.Sequence` to the target values and then
the gradient raster to the case, runs `RASTERS.run` with a `RunContext`, and checks the
finding. For "not a number", it checks `math.isnan`, because nan is not equal to itself.

**Assumptions:** The test sets the values in the object and does not write a file, as the
test of the error does. An array of one element is a number: its `item()` is used, as in
the check. The `repr` text of a string has quotes, so it is never one of the strings "inf",
"-inf" and "nan" that `Finding` refuses; the test does not check this separately.

#### `test_an_error_lists_the_mismatches_of_the_other_rasters_too`

**Checks:** For a file with a gradient raster of 1.5 times the target, no ADC raster and a
block duration raster of 2 times the target, the result is "error" with three findings, in
the order of the rasters: RASTER_MISMATCH of the gradient raster, RASTER_NOT_DECLARED of the
ADC raster and RASTER_MISMATCH of the block duration raster. No finding has a location. The
reason is only the text of the missing raster, and the value and the limit are None.

**How:** The test writes the file, runs `timing.rasters` through `run_checks`, and compares
the codes, the names and the `data` of the findings and the three fields of the result.

**Assumptions:** The test removes the ADC raster and not the block duration raster, so it
does not need the filter for the warning of pypulseq about a missing block duration raster.

#### `test_the_findings_of_an_error_survive_the_json_round_trip`

**Checks:** A result with the state "error" and three findings (a RASTER_INVALID with a
text value, a RASTER_INVALID with a "not a number" value and a RASTER_MISMATCH) is the same
after `to_json` and `from_json` of the matrix: the codes, the messages, the locations (None)
and the `data`, with the nan as a nan and the text `'abc'` as that text, and the reason.

**How:** The test makes a `pp.Sequence` in memory with the gradient raster `"abc"`, the RF
raster `nan`, the ADC raster of the target and a block duration raster of 2 times the target,
runs `timing.rasters` through `run_checks`, and reads the JSON back. It compares the
findings with `==`, except the nan one, where it checks `math.isnan` and compares the other
fields.

**Assumptions:** `Finding` with a nan in its data is not equal to itself, so the test cannot
compare the whole matrix. The JSON form of the nan is tested in `test_results.py`.

#### `test_rasters_are_not_evaluated_without_a_target_raster`

**Checks:** A target that does not give one of the four rasters gives "not evaluated"
with a reason that names the missing input and no value.

**How:** For each of the four inputs, the test builds a target without it and runs
`timing.rasters` through `run_checks`. It checks the state, that the reason names the
input, and that the value is None.

**Assumptions:** The run function gives the state before it calls `run`. The test does not
check that `run` is not called (`test_run.py` does).

#### `test_timing_errors_depend_on_the_target`

**Checks:** One file gives no timing error for a target with an RF dead time of 100 µs and
timing errors for a target with 200 µs. The value of the failing result is the number of
errors, the limit is 0, and the unit is None.

**How:** The test runs `timing.pypulseq` through `run_checks` on the file with two targets
that differ in `opts.rf_dead_time`, so that the run function reads the file one time for
each target. The RF pulses of both RF blocks have a delay of 100 µs. The test checks the
first result (pass, value 0, limit 0, no unit, no location, no reason) and the second
(fail, two errors, limit 0, no unit, and a reason that starts with
`first of 2 errors: block 2`).

**Assumptions:** `check_timing` gives one error for each of the two blocks. The test does
not check the other error types of `check_timing`; pypulseq tests them.

#### `test_the_location_is_the_first_error_block_and_its_start_time`

**Checks:** The location of a failing result is the block ID of the first error and the
start time of that block.

**How:** The test runs the check for the target with an RF dead time of 200 µs. The first
block (a delay) has no error, so the first error is in block 2, which starts at 1 ms. The
test compares the location with block 2 and 1 ms.

**Assumptions:** The start time is the sum of the block durations of `sequence_index`. The
block IDs are the pypulseq block numbers, from 1.

#### `test_one_finding_for_each_error_in_the_order_of_check_timing`

**Checks:** For the target with an RF dead time of 200 µs, the result of `timing.pypulseq`
has one finding for each error of `check_timing`, with the codes of the errors in the same
order (here two RF_DEAD_TIME), and no omitted findings. The value of the result is the
number of errors, its limit 0, its location the location of the first finding, and its
reason `first of 2 errors: block 2, rf.delay: RF_DEAD_TIME`.

**How:** The test runs the check through `run_checks`. It reads the same file with the
`Opts` of the target and calls `check_timing` on it, and compares the codes and the block
IDs of the findings with the errors.

**Assumptions:** `check_timing` gives the same errors when the check and the test read the
file, so the test compares the codes with a second reading and not with fixed names, and
also checks the names. The reason text did not change from before the findings.

#### `test_the_location_of_a_finding_is_its_block_and_the_start_of_that_block`

**Checks:** The location of each finding is the block of its error and the start time of
that block: block 2 at 1 ms and block 4 at 4.12 ms.

**How:** The test runs the check for the target with an RF dead time of 200 µs and compares
the locations of the two findings with the two expected locations.

**Assumptions:** Block 4 starts after a delay of 1 ms, block 2 (1.12 ms: a delay of 100 µs,
a pulse of 1 ms and the ringdown of 20 µs) and a delay of 2 ms. The block IDs are the
pypulseq block numbers, from 1.

#### `test_the_findings_of_each_error_type_have_the_data_of_the_record`

**Checks:** For each of the error types BLOCK_DURATION_MISMATCH, RF_DEAD_TIME,
RF_RINGDOWN_TIME, ADC_DEAD_TIME and POST_ADC_DEAD_TIME, the `data` of the finding has
exactly the fields of the record of `check_timing`, except the block and the error type,
with the expected values in seconds. Each value has the type `str`, `int`, `float`, `bool`
or None, and not a NumPy type.

**How:** The test runs `PYPULSEQ.run` with a `RunContext` on `error_sequence` read with
`ERROR_OPTS`, and takes the first finding of each pair of block and code. It compares the
data with the hand-computed values (to a relative 1e-9) and checks the types with
`type(v) in (str, int, float, bool, NoneType)`, which a NumPy scalar does not satisfy.
It also checks that the records of `check_timing` have NumPy types, so the conversion is
needed.

**Assumptions:** The values are the ones in the file, so they have the rounding of the
`.seq` format; the relative tolerance covers it. The test does not make an error of the
types NEGATIVE_DELAY and the soft delay types. A data value that is an `int` stays an
`int`: no field of the five types is an `int`, so the test does not check this.

#### `test_the_findings_of_a_raster_error_have_the_data_of_the_record`

**Checks:** The three RASTER errors of `raster_error_sequence` give three findings with the
code RASTER, in the order of the errors, in blocks 2, 2 and 3. Their `data` has the fields
event, field, value, value_rounded, error and raster. The raster names are
`block_duration_raster` for a block duration and `adc_raster_time` for an ADC dwell. The
values of the dwell (20.0515 µs, 20.1 µs, -48.5 ns) and the block duration of block 3
(1001.23 µs, 1000 µs, 1.23 µs) are the expected ones, and each value has a Python type.

**How:** The test runs `PYPULSEQ.run` on the sequence in memory and compares the data with
the expected values (to a relative 1e-6).

**Assumptions:** The test does not check the data of the first finding (the block duration
of block 2) except its event, field and raster.

#### `test_the_message_of_a_finding_is_the_text_of_the_error_report_of_pypulseq`

**Checks:** The message of each finding of `error_sequence` (nine findings of five types)
is the text that `print_error_report` of pypulseq prints for the same error, in the same
order, and the codes are the five types.

**How:** The test calls `print_error_report(seq, errors, full_report=True, colored=False)`
and reads the lines that start with `- ` with `capsys`. It compares them, as a list, with
`- event.field: ` and the message of each finding.

**Assumptions:** The report of pypulseq adds a line "Block n:" for each block, and a trace
line when the sequence has a trace of the creation of the blocks. A sequence that is read
from a file has none, so the only lines that start with `- ` are the error lines.

#### `test_the_message_of_a_raster_finding_is_in_us_and_the_message_of_a_dwell_is_in_ns`

**Checks:** The messages of the three RASTER findings of `raster_error_sequence` are the
lines of the error report of pypulseq. The message of a block duration ends with ` us)` and
the message of an ADC dwell ends with ` ns)` and has no ` us`.

**How:** As in the test above, with the sequence in memory. Then the test checks the end of
the first two messages.

**Assumptions:** The unit of the report is "ns" for the field `dwell` and "us" for the
others.

#### `test_a_record_without_a_message_template_gives_the_fallback_message`

**Checks:** A record with an error type that has no template (`NO_SUCH_TYPE`) gives the
message `rf.delay: NO_SUCH_TYPE`. A record of the type RASTER that lacks the fields of the
template gives `adc.dwell: RASTER`. In both cases the code is the error type, the location
is block 2 at 1 ms, and the data are the fields event, field and value of the record.

**How:** The test replaces `check_timing` of the sequence with a function that returns the
record (monkeypatch) and runs `PYPULSEQ.run`. It checks the finding.

**Assumptions:** The record is a `SimpleNamespace` of the same kind as the records of
pypulseq. A template that fails for another reason (for example a zero division) goes
through the same `except`; the test does not make it.

#### `test_a_pass_has_no_findings`

**Checks:** A sequence without timing errors gives "pass" with no findings and no omitted
findings.

**How:** The test runs `PYPULSEQ.run` on the file read with the `Opts` of the default
target.

**Assumptions:** None.

#### `test_timing_pypulseq_is_not_evaluated_without_an_input`

**Checks:** A target without one of the four rasters, the RF dead time, the RF ringdown or
the ADC dead time gives "not evaluated" for `timing.pypulseq`, with a reason that names the
input.

**How:** For each of the seven inputs, the test builds a target without it, runs the check
through `run_checks`, and checks the state, the reason and that the value is None.

**Assumptions:** The file has no ADC. The check still needs `opts.adc_dead_time`, so that
a default of pypulseq is never used (see its specification).

#### `test_check_timing_does_not_change_the_sequence`

**Checks:** `timing.pypulseq` leaves the sequence as it was: the block events, the block
durations, the definitions, the `use_block_cache` setting and an empty block cache.

**How:** The test reads the file with the `Opts` of a target, copies the block events, the
block durations and the definitions, runs `PYPULSEQ.run` with a `RunContext` for a target
with a timing error, and compares each of them with the copy. It checks that the block
cache is empty.

**Assumptions:** `Sequence.check_timing` alone fills the block cache (one entry for each
block); the check turns the cache off. The test does not compare the event libraries or
the shapes.

#### `test_each_field_of_a_spec_is_set`

**Checks:** The `CheckSpec` of each timing check has the version 1, its cost class
(`fast` for `timing.rasters`, `slow` for `timing.pypulseq`), no URL, no models, a text in each of `title`, `quantity`, `limit`, `tolerance` and
`pass_condition`, and inputs with no duplicate.

**How:** The test reads the fields of `RASTERS.spec` and `PYPULSEQ.spec`.

**Assumptions:** The test does not check the content of the texts, only that they are not
empty. The cost classes are the ones of task 8.3 of the plan, from `scripts/budget.py`.

#### `test_the_spec_of_timing_pypulseq_has_findings_and_keeps_version_1`

**Checks:** The specification of `timing.pypulseq` has the version 1 and a `findings` text
that is not empty and names each error type that pypulseq has a message template for.

**How:** The test reads the fields of the specification, and checks the names of the keys of
`error_messages` of pypulseq in the text.

**Assumptions:** A newer pypulseq with another template needs a change of the text; the
test finds it. The test does not check the other words of the text.

#### `test_the_spec_of_timing_rasters_has_findings_and_keeps_version_1`

**Checks:** The specification of `timing.rasters` has the version 1 and a `findings` text
that is not empty and names the three codes RASTER_NOT_DECLARED, RASTER_INVALID and
RASTER_MISMATCH.

**How:** The test reads the fields of the specification and looks for the three codes in the
text.

**Assumptions:** The test checks the names of the codes only, not the other words of the
text. That each code in the text is the code that the check gives is tested by the tests of
the findings.

#### `test_the_ids_and_inputs_of_the_specs`

**Checks:** The IDs are `timing.rasters` and `timing.pypulseq`. The inputs of the raster
check are the four raster paths. The inputs of the pypulseq check are the four raster
paths and `opts.rf_dead_time`, `opts.rf_ringdown_time` and `opts.adc_dead_time`. The
pypulseq function is `Sequence.check_timing` for the second check and None for the first.

**How:** The test compares the fields with the expected values. The raster paths come from
`RASTER_OPTS` of `profile.py`.

**Assumptions:** The inputs of the pypulseq check are the values that `check_timing` of the
pinned pypulseq reads from `seq.system` (the four rasters, the two RF times and the ADC
dead time). A newer pypulseq that reads more values needs a change here and in the
specification.

### 2.14 Gradient checks (`test_check_gradient.py`)

These tests check the three gradient check rules of `checks/gradient.py`:
`gradient.amplitude.axis`, `gradient.slew.axis` and `gradient.amplitude.any-orientation`.
The tests call a rule directly with a `RunContext` (`run_one`), or through `run_checks`
with `registry.check_rules` replaced by monkeypatch, so that they do not need the other
checks of the package or the installed entry points. The targets are `TargetProfile`
objects that the test builds (`make_profile`), with limits in mT/m and T/m/s. The
sequences are small sequences that the test builds with pypulseq: trapezoids of a known
amplitude and with the rise time 100 µs, so that an amplitude of x mT/m has the slew
10 · x T/m/s. The sequences use a system with the limits 100 mT/m and 1000 T/m/s, which
are larger than the limits of the profiles, so that a sequence can be above the limit of
a profile. Each expected value is computed by hand from the parameters of the
trapezoids, not by calling `gradient_limits`. Where a test needs a value that is exactly
the limit (at the limit, and around the tolerance), it takes the value from a first run
of the same check with a limit that the sequence does not reach, and sets the limit from
that value. Some of the tests use a table of three cases (`CASES`): each case is one rule
with a sequence whose value, unit and location are known (for the amplitude rule 20
mT/m, for the slew rule 200 T/m/s, in both cases the trapezoid in block 3 of a sequence
with two earlier blocks; for the vector rule x and y at 12 mT/m at the same time in
block 3, so |G| = 12 · sqrt(2) mT/m).

#### `test_below_the_limit_passes_with_the_value_the_limit_and_the_unit`

**Checks:** For each of the three rules, a value below the limit gives the state "pass",
the value of the measurement, the limit of the target and the unit of the rule (mT/m, or
T/m/s for the slew), and the detail of the value as its reason: `axis x` for the two
axis rules, none for the vector rule.

**How:** The test runs the rule on the sequence of its case with the limit twice the
expected value. It checks the state, the value against the hand-computed one
(`pytest.approx`), that the limit is the one of the profile, the unit and the reason.

**Assumptions:** The limit that the case does not use is very large, so that it does not
matter.

#### `test_a_value_equal_to_the_limit_passes`

**Checks:** A value that is exactly the limit passes.

**How:** The test runs the rule with a very large limit and takes the value of the
result. It runs the rule again with that value as the limit, and checks that the value
and the limit are equal and that the state is "pass".

**Assumptions:** The value of the first run is the same as the one of the second run,
because the sequence and the measurement are the same. The test does not check the value
against a hand-computed one (other tests do).

#### `test_a_value_within_the_tolerance_above_the_limit_passes`

**Checks:** A value above the limit by less than the relative tolerance 1e-9 passes
(decision 5 of the plan).

**How:** The test takes the value of a run with a very large limit, and sets the limit to
`value / (1 + 5e-10)`: the value is then 5e-10 of the limit above it. It checks that the
value is above the limit and that the state is "pass".

**Assumptions:** The test does not check the exact bound: a value above the limit by
1e-9 is not tried. The next test checks a value above the tolerance.

#### `test_a_value_above_the_limit_by_more_than_the_tolerance_fails`

**Checks:** A value above the limit by more than the tolerance gives "fail", with the
value, the limit and the same reason as a pass. This holds for a value that is just
above the tolerance (2e-9 of the limit) and for one that is clearly above (10 %).

**How:** The test takes the value of a run with a very large limit, and sets the limit to
`value / factor` for each of the two factors `1 + 2e-9` and 1.1. It checks the state, the
value, the limit and the reason of the result.

**Assumptions:** None.

#### `test_the_location_is_the_block_and_the_time_of_the_value`

**Checks:** The location of the result is the block ID and the time of the value: for
the amplitude and the vector rules, the first time where the peak is reached (the end of
the rise of the trapezoid), and for the slew rule, the start of the steepest segment
(the start of the rise).

**How:** Each case has a sequence with a smaller trapezoid in block 1, a delay of 1 ms in
block 2 and the trapezoid of the value in block 3. The block starts at the duration of
block 1 (500 µs) plus the delay, and the test adds the rise time of 100 µs for the
amplitude and the vector rules. It checks that the block is 3 and the time, with a
tolerance of 1 ns.

**Assumptions:** The block IDs are the pypulseq IDs, which start at 1.

#### `test_the_axis_with_the_largest_ratio_gives_the_value`

**Checks:** For the amplitude rule and the slew rule, the value is the peak of the axis
with the largest ratio of the peak to the limit, which has the largest peak because the
limit is the same for each axis: the state, the value, the limit and the location are the
ones of that axis. A sequence whose other axes are below the limit gives "pass" with the
same value, and a limit below the peak of that axis gives "fail".

**How:** The test builds three blocks: x at 10 mT/m, y at 18 mT/m and z at 14 mT/m (slew
100, 180 and 140 T/m/s). It runs each rule with a limit below (16 mT/m, 160 T/m/s) and a
limit above (20 mT/m, 200 T/m/s) the peak of y. The value must be the one of y (18 mT/m,
180 T/m/s) with the state "fail", respectively "pass", the location the block 2 and its
time, and the reason `axis y`.

**Assumptions:** None.

#### `test_two_axes_with_the_same_peak_give_the_first_axis_in_x_y_z_order`

**Checks:** When two axes have the same peak, the value and the location are the ones of
the first axis in the order x, y, z, and not those of the earlier block.

**How:** The test builds y at 15 mT/m in block 1 and x at 15 mT/m in block 2, and runs the
amplitude rule and the slew rule. The location must be block 2 (x), and the reason
`axis x`.

**Assumptions:** The two trapezoids are made with the same parameters, so that their
peaks and slew rates are exactly equal.

#### `test_the_vector_peak_is_above_the_limit_when_each_axis_is_below_it`

**Checks:** With x and y each at 0.8 of the amplitude limit at the same time, the
amplitude rule passes and the any-orientation rule fails.

**How:** The test builds one block with x and y trapezoids at 16 mT/m, with the limit 20
mT/m. It checks that the amplitude rule passes with the value 16 mT/m, and that the
any-orientation rule fails with the value 16 · sqrt(2) = 22.6 mT/m and the limit 20
mT/m. Both locations are block 1.

**Assumptions:** None.

#### `test_a_sequence_with_no_gradient_passes_with_the_value_0_and_no_location`

**Checks:** For each rule, a sequence with no gradient event gives "pass", the value 0.0,
the limit and the unit of the rule, and no location.

**How:** The test runs each rule on `empty_sequence()` (one delay block) and checks the
state, the value, the location, the limit and the unit.

**Assumptions:** None.

#### `test_a_value_of_0_has_no_location`

**Checks:** When the largest value is 0 but the sequence has a gradient event, the result
is "pass" with the value 0.0 and no location, for each rule.

**How:** The test builds one block with a y trapezoid that `pp.scale_grad` scales to the
amplitude 0. The measurement has an event but credits no block. The test checks the state,
the value and that the location is None.

**Assumptions:** `gradient_limits` credits no block for the value 0 (tested in
`test_grad_limits.py`).

#### `test_a_value_with_no_block_has_a_location_with_the_time_only`

**Checks:** When the measurement gives a value above 0 and no block, the location of the
amplitude rule and of the any-orientation rule has the time and the block None.

**How:** The test replaces `gradient_limits` in the check module with a function that
gives a `GradientLimits` made by hand, with the peak 5 mT/m at 0.25 s and no block, and
checks the value and that the location is `Location(block=None, time_s=0.25)`.

**Assumptions:** A real measurement does not give this result, so the test uses a made
result. It tests the rule of the check only.

#### `test_a_target_with_one_limit_gives_not_evaluated_for_the_checks_of_the_other`

**Checks:** With `run_checks`, a target with only `opts.max_grad` gets results for the two
amplitude rules (with the limit converted from the profile) and "not evaluated" for the
slew rule, with a reason that names `opts.max_slew`. A target with only `opts.max_slew`
gets the reverse. A target with neither gets "not evaluated" for the three rules.

**How:** The test runs the three rules on a sequence for the three targets, and checks
the state of each result, the limit of the results that ran (`pytest.approx`) and the
reason of the slew result.

**Assumptions:** None.

#### `test_a_target_with_one_limit_gives_the_other_as_nan_and_its_name_as_the_label`

**Checks:** For a target with only `opts.max_grad`, the rules call `gradient_limits` with
`HardwareLimits` that has the limit from the `pp.Opts` of the target (in mT/m, with the
gamma of that Opts), nan for the other limit, and the name of the target as the label. The
limits are not None.

**How:** The test spies on `gradient_limits` in the check module (the spy calls the real
function and keeps its keyword arguments), runs the three rules on a target with
`max_grad` 20 mT/m and `gamma` 40 MHz/T, and checks the limits of the only call: the limit
is 20 mT/m (with 42.576 MHz/T it would be 18.8), the other one is nan and the label is
the name of the target.

**Assumptions:** `gradient_limits` uses `limits` only as a label (checked in its code, not
by this test), so a nan limit does not change the numbers.

#### `test_a_target_with_only_max_slew_gives_max_grad_as_nan`

**Checks:** The same for a target with only `opts.max_slew`: the slew limit is in T/m/s,
the amplitude limit is nan, and the label is the name of the target.

**How:** The same spy, with a target with `max_slew` 300 T/m/s. It checks the limits of
the call.

**Assumptions:** The same as in the test above.

#### `test_max_grad_with_rise_time_gives_the_slew_limit_max_grad_over_rise_time`

**Checks:** A target with `opts.max_grad` 30 mT/m and `opts.rise_time` and no
`opts.max_slew` gets a result for `gradient.slew.axis` with the limit `max_grad /
rise_time`: a pass at 100 µs (300 T/m/s) and a fail at 200 µs (150 T/m/s), for a peak slew
of 200 T/m/s.

**How:** `run_checks` with a `TargetProfile` without `hardware_limits`, so the limit comes
from `_hardware_limits` and the `pp.Opts` of the target. Parametrized over the two rise
times.

**Assumptions:** None.

#### `test_rise_time_without_max_grad_gives_not_evaluated_for_the_slew`

**Checks:** A target with `opts.rise_time` and no `opts.max_grad` gets "not evaluated"
for `gradient.slew.axis`, with `opts.max_slew` in the reason.

**How:** `run_checks` with the slew rule only.

**Assumptions:** None.

#### `test_the_three_checks_share_one_measurement_for_each_target`

**Checks:** For a `.seq` file and two targets, `gradient_limits` runs one time for each
target (two times for the three rules, not six), always over the whole file (no window)
and with the hardware limits of that target, never with None.

**How:** The test writes a `.seq` file, runs the three rules for two targets with
different limits and the spy on `gradient_limits`. It checks that all six results are
"pass", that there are two calls, that the keyword arguments of each call are only
`limits`, and that the limits are `hardware_limits` of the target, in the order of the
targets.

**Assumptions:** `run_checks` reads the file one time for each target (tested in
`test_run.py`).

#### `test_the_three_checks_of_one_target_call_gradient_limits_one_time`

**Checks:** For a `Sequence` object and one target, the three rules call `gradient_limits`
one time, with the hardware limits of the target.

**How:** The test runs the three rules with the spy and checks that there is one call and
that its `limits` is the `hardware_limits` of the profile.

**Assumptions:** None.

#### `test_limits_from_sequence_uses_the_limits_of_seq_system`

**Checks:** With `limits_from_sequence=True`, a `Sequence` object and a target with no
limits, the three rules run and compare with the limits of `seq.system`, 28 mT/m and
150 T/m/s.

**How:** The test builds an x trapezoid at 20 mT/m with the rise time 200 µs (slew
100 T/m/s) with the `SYSTEM` of `tests/synthetic.py`, and runs the rules on a target that
gives no value. It checks that the three results are "pass", and their values and limits:
20 and 28 mT/m for the two amplitude rules, and 100 and 150 T/m/s for the slew rule.

**Assumptions:** The limits of `SYSTEM` are 28 mT/m and 150 T/m/s. The conversion of the
units of `seq.system` is tested in `test_run.py`, not here.

#### `test_a_rotation_gives_error_for_the_three_checks`

**Checks:** For a sequence that uses the rotation extension, each of the three rules gives
the state "error" with a reason that starts with `NotImplementedError`, and no value.

**How:** The test gives a sequence a non-empty `rotation_library` (the way pypulseq draft
PR #372 stores rotations, as `tests/test_extensions.py` does) and runs the three rules
with `run_checks`. It checks the state, the reason and that the value is None.

**Assumptions:** The test uses a rotation library that is set by hand: pypulseq 1.5.0.post1
cannot make a rotation, and its `Sequence.read` raises `ValueError` for a file with one
(the run function makes that an error of the run, not a result). The test does not cover a
later pypulseq that stores a rotation in another way (see `refuse_rotations`).

#### `test_the_spec_sets_each_field`

**Checks:** For each of the three rules, the `CheckSpec` has the expected ID, version 1,
cost class `"fast"` (task 8.3 of the plan), `url` None, no model, the expected input (`opts.max_slew` for the slew
rule, `opts.max_grad` for the other two), and a non-empty title, quantity, limit,
tolerance and pass condition.

**How:** The test compares each field, and checks that each of the five texts is a string
with a character that is not white space.

**Assumptions:** The test does not check the text of the specification: a person reads it
in `docs/checks.md` (phase 6). It does not check the entry points in `pyproject.toml`.

#### `test_the_slew_of_a_junction_uses_the_gradient_raster_of_the_file_for_any_target`

**Checks:** `gradient.slew.axis` measures the junction step with the gradient raster
of the file, for a target with no `[rasters]`, with `GradientRasterTime = 4e-6` and
with `GradientRasterTime = 10e-6`. Each run fails with the junction value, at the
second block, at the time of the junction.

**How:** The test writes `raster_4us_sequence` (4 µs gradient raster, slopes 40 and
39.4 T/m/s, junction 60 T/m/s) to a file in `tmp_path` and calls `run_checks` with the
path and a profile with `max_slew = 50`. For each of the three profiles it checks
that the state is fail, the value is 60 T/m/s, the block is 2 and the time is 0.8 ms.
Before the fix, the profiles with no rasters and with 10 µs gave 40 T/m/s and passed.

**Assumptions:** The file stores the amplitudes with fewer digits, so the value has a
relative tolerance of 1e-4.

### 2.15 PNS check (`test_check_pns.py`)

These tests cover the check rule `pns.safe` (`checks/pns.py`). They run it through
`run_checks` with a `.seq` file or a `Sequence` object, and with `registry.check_rules`
replaced by a function that gives only this check, so that they do not need the other
checks. The profiles name a synthetic `.asc` file from the `write_gradient_asc` fixture,
whose `limit_scale` sets the stimulation limits: a large scale gives a pass and a small one
a fail. The sequences are small.

#### `test_no_safe_parameters_gives_not_evaluated`

**Checks:** A profile without `models.pns.safe` gives the state "not evaluated", with a
reason that names `pns.safe`, and no value.

**How:** The test reads a profile with a name only and runs the check on a `.seq` file.

**Assumptions:** The run function makes the result before it calls `run`.

#### `test_the_peak_against_the_stimulation_limit`

**Checks:** With a large `limit_scale` the state is "pass", and with a small one it is
"fail". The value is 100 times the peak of `pns_levels_for` with the same hardware, the
limit is 100.0, the unit is `%`, the model is `pns.safe` with `SAFE_MODEL.version`, and
the check ID and the specification version are those of the spec.

**How:** The test writes the `.asc` file and a profile that names it, reads the profile,
and runs the check on a two-repetition gradient-echo `.seq` file. It compares the value
exactly with 100 times the peak of `pns_levels_for` for the same file, read with the
`Opts` of the profile as `run_checks` reads it, with `hardware` from the profile.

**Assumptions:** The two scales are far from the limit, so the states do not depend on the
rounding of the values in the file.

#### `test_the_location_is_the_block_of_the_peak`

**Checks:** The location has the time `PnsLevels.peak_time_s`, and the block ID of the last
block that starts at or before that time (`sequence_index`). The time is inside that
block.

**How:** The test runs the failing case and computes the block from `sequence_index` and
`pns_levels_for` itself.

**Assumptions:** The object and the file give the same block starts.

#### `test_safe_parameters_in_the_profile_file_match_the_asc_file`

**Checks:** SAFE parameters written in `[models.pns.safe]` of the profile (the values of
`safe_example_hw()`, with the two stimulation fields scaled) give the same parameters as
the `.asc` file with that scale, and the same state, value and location.

**How:** The test builds the TOML text from `safe_example_hw()` in a second directory,
reads both profiles and compares their SAFE parameters and their results.

**Assumptions:** The `.asc` fixture writes the values of `safe_example_hw()` with the
stimulation limit and threshold multiplied by `limit_scale`.

#### `test_a_rotation_gives_error`

**Checks:** A `Sequence` object with a `rotation_library` gives the state "error", and the
reason names `NotImplementedError`.

**How:** The test builds the object with the helper of `test_extensions.py` and runs the
check on it.

**Assumptions:** The check does not catch the exception of `pns_levels`.

#### `test_a_sequence_without_gradients_passes_with_zero`

**Checks:** A sequence with a delay block only gives "pass", value 0.0, no location, and
the model and its version.

**How:** The test runs the check on `empty_sequence()`, with the failing scale.

**Assumptions:** None.

#### `test_the_spec_gives_each_field`

**Checks:** The ID is `pns.safe`, the version is 1, `models` is `("pns.safe",)`, `inputs`
is empty, `cost` is "slow", `url` is None, the other text fields are not empty, and
`pypulseq` names `_safe_gwf_to_pns_chunk`.

**How:** The test reads the fields of `SAFE.spec`.

**Assumptions:** None.

### 2.16 The command (`test_cli.py`)

These tests check `pulseq-check` (`pulseq_checks.cli.main`). They call `main([...])` in the
test process and read its return value, `capsys` and the files that it writes. Most tests
replace `registry.check_rules` with small test rules, as `test_run.py` does, so that the
state of each result is controlled. They write small profile files, config files and a
synthetic spin-echo `.seq` file (`tests/synthetic.py`) in `tmp_path`. A test rule gives the
value 1.5 and the limit 2 with the unit mT/m, and, for "not evaluated" and "error", a
reason. A test rule with an input that the profile does not give ends as "not evaluated"
before it runs. A test rule can also give findings (`FINDINGS` in `test_cli.py`: one with a
block and a time, one with a time only and a message of two lines, and one with no
location). `run_to_matrix` runs `main` with `--json` and `--quiet`, and reads the
file back with `ResultMatrix.from_json`, to see which checks ran and which are required.

#### `test_the_exit_status_follows_the_states_of_the_results`

**Checks:** The status is 0 when all results pass, 2 when a result fails, 1 when a result
is an error, and 1 when a result fails and another is an error (1 wins over 2).

**How:** A parametrized test installs two test rules with the given states, runs `main`
with `--target` and `--quiet`, and compares the return value.

**Assumptions:** The logic of the status is `ResultMatrix.exit_status` (`test_results.py`).
This test shows only that the command returns it.

#### `test_a_required_check_that_is_not_evaluated_gives_status_1`

**Checks:** A check that a config names in `required` and that is not evaluated gives
status 1, and the summary says so.

**How:** A test rule needs `opts.max_grad`, which the profile does not give. The config
makes it required. The test checks the status and that the summary has "exit status 1".

**Assumptions:** None.

#### `test_a_check_that_is_not_required_and_not_evaluated_gives_status_0`

**Checks:** The same test rule, when it is not required, gives status 0, and the summary
shows its state "not evaluated".

**How:** The test runs `main` with `--target` only and checks the status and the summary.

**Assumptions:** None.

#### `test_json_to_a_file_reads_back_as_the_matrix`

**Checks:** `--json OUT` writes a file that `ResultMatrix.from_json` reads back as the
matrix that `run_checks` gives for the same sequence, profile and checks, and the summary
is still on stdout. The status is that of the matrix (2 here).

**How:** The test runs `main` with one passing and one failing test rule, reads the file,
and compares it to the result of `run_checks` with `read_profile` of the same file. It
checks that stdout has the exit status line.

**Assumptions:** The matrix does not contain anything that changes from one run to the
next (there is no time stamp). This holds for the matrix of version 1.

#### `test_json_to_stdout_is_only_the_json_and_the_summary_goes_to_stderr`

**Checks:** With `--json -`, stdout is the JSON result and nothing else, and the summary
is on stderr.

**How:** The test reads the whole of stdout with `ResultMatrix.from_json` (an extra line
would be an error), and checks that stderr has the check IDs and the exit status line.

**Assumptions:** None.

#### `test_json_to_stdout_with_quiet_writes_nothing_to_stderr`

**Checks:** With `--json -` and `--quiet`, stdout is JSON and stderr is empty.

**How:** The test runs `main`, parses stdout as JSON, and compares stderr to the empty
string.

**Assumptions:** None.

#### `test_json_to_a_path_that_cannot_be_written_gives_status_1`

**Checks:** A `--json` path in a folder that does not exist is an error of the run: status
1, and a message on stderr that starts with `pulseq-check: error:` and names the path.

**How:** The test gives a path in a folder that it did not make.

**Assumptions:** Other causes of a failed write (a full disk, no permission) go through the
same `OSError` handling, and the test does not make them.

#### `test_quiet_writes_no_summary_but_keeps_the_status`

**Checks:** `--quiet` writes nothing to stdout and stderr, and the status is still that of
the results (2 for a failing check).

**How:** The test runs `main` with a failing test rule and `--quiet`.

**Assumptions:** None.

#### `test_quiet_still_prints_an_error_of_the_run`

**Checks:** With `--quiet`, an error of the run (here a profile with no name) still gives
its message on stderr, starting with `pulseq-check: error:`, and status 1. stdout is empty.

**How:** The test runs `main` with an invalid profile and `--quiet`.

**Assumptions:** None.

#### `test_a_config_gives_the_targets_relative_to_its_file_select_required_and_fast_only`

**Checks:** With `--config`, the command reads the target profiles at the paths relative
to the config file, not to the working directory, and it uses `select`, `required` and
`fast_only` of the file.

**How:** The test writes two profiles in a sub-folder of a config folder and a config with
`select` of three checks, `fast_only = true` and `required` for one check and one target,
and it changes the working directory to another folder. It reads the `--json` result: the
targets are both profiles, the slow check is not in it (`fast_only`), the check that is not
selected is not in it, and only the check of `required` for the target `b` is required. The
status is 1, because that required check is not evaluated for `b`.

**Assumptions:** None.

#### `test_a_config_without_select_or_fast_only_runs_every_check`

**Checks:** A JSON config with only `format` and `targets` runs all the installed checks,
and no check is required.

**How:** The test runs `main` with such a file and two test rules (one fast) and reads the
IDs of the results and the status (0).

**Assumptions:** None.

#### `test_check_selects_the_check_and_makes_it_required`

**Checks:** With `--target`, `--check` runs only the named checks, in the order of the
check IDs, and makes each one required.

**How:** Three test rules are installed, two are named twice with `--check` in the wrong
order. The test reads the IDs of the results and that each result is required.

**Assumptions:** None.

#### `test_a_check_that_is_not_evaluated_gives_status_1`

**Checks:** A check that is not evaluated gives status 0 when it is not named, and status
1 when `--check` names it.

**How:** The same test rule (with an input that the profile does not give) is run twice,
without and with `--check`, and the two statuses are compared.

**Assumptions:** None.

#### `test_check_is_required_for_each_target`

**Checks:** `--check` makes the check required for each target of the run.

**How:** The test runs with two `--target` profiles and reads which results are required.

**Assumptions:** None.

#### `test_check_with_a_config_is_added_to_select_and_required`

**Checks:** With `--config`, the IDs of `--check` are added to the `select` of the file,
and are required for all targets on top of the `required` of the file. A check that the
file requires for one target only is then required for both.

**How:** The config selects two checks and requires one for all targets and one for the
target `a`. `--check` names one more check and the second one again. The test checks that
the selected checks (not the fourth) ran, and that the three are required for both targets.

**Assumptions:** None.

#### `test_check_with_a_config_without_select_keeps_every_check_selected`

**Checks:** With `--config` and a file with no `select`, `--check` does not reduce the
selection to the named checks: all checks run, and only the named one is required.

**How:** The test runs two test rules with `--check` for the second and reads the IDs and
the `required` flags.

**Assumptions:** None.

#### `test_a_check_that_is_not_installed_gives_status_1`

**Checks:** A `--check` ID that no installed check has is an error of the run: status 1,
and a message that names the ID.

**How:** The test runs `main` with a check ID that the test rules do not have.

**Assumptions:** The message comes from `run_checks` (`test_run.py`).

#### `test_fast_runs_only_the_fast_checks_and_does_not_make_them_required`

**Checks:** `--fast` removes the checks that are not of the cost class "fast", does not
make the fast checks required, and does not remove a check that `--check` names.

**How:** One fast and one slow test rule. With `--fast` the result has the fast check, and
it is not required. With `--fast --check` for the slow check, only the slow check is in the
result, and it is required (`--check` selects only the named check).

**Assumptions:** None.

#### `test_fast_overrides_fast_only_false_of_a_config`

**Checks:** With a config that has `fast_only = false`, all checks run, and with `--fast`
only the fast checks run.

**How:** The test runs `main` with the same config without and with `--fast`.

**Assumptions:** The case of a config with `fast_only = true` is in the test of the config.

#### `test_an_invalid_profile_gives_status_1_and_a_message_that_names_the_file`

**Checks:** An invalid profile (an unknown key in `opts`) gives status 1, nothing on
stdout, and a message on stderr that starts with `pulseq-check: error:` and names the file.

**How:** The test writes the file and runs `main` with `--target`.

**Assumptions:** The content of the message comes from `read_profile` (`test_profile.py`).

#### `test_a_config_that_names_an_invalid_profile_gives_status_1_and_names_the_file`

**Checks:** A config with a target path that does not exist gives status 1 and a message
that names that path.

**How:** The test writes a config with the path of a file that it did not write.

**Assumptions:** None.

#### `test_an_invalid_config_gives_status_1_and_names_the_file`

**Checks:** An invalid config (no `format`) gives status 1 and a message that names the
config file.

**How:** The test writes such a file and runs `main` with `--config`.

**Assumptions:** None.

#### `test_a_sequence_file_that_is_missing_gives_status_1_and_names_the_file`

**Checks:** A `.seq` file that does not exist is an error of the run: status 1, nothing on
stdout, and a message that names the file.

**How:** The test gives the path of a file that does not exist with a valid profile.

**Assumptions:** The other reasons that the read of a `.seq` file can fail give the same
`RunError` (`test_run.py`).

#### `test_an_error_in_the_arguments_gives_status_1_not_2`

**Checks:** No `--config` and no `--target`, both of them, an unknown option, and an option
without its value give status 1 (argparse gives 2 by default), no stdout, and a message on
stderr that has `pulseq-check: error:`.

**How:** A parametrized test runs `main` with each argument list.

**Assumptions:** None.

#### `test_a_missing_sequence_argument_gives_status_1`

**Checks:** A command line with no `SEQ_FILE` gives status 1 and the same message.

**How:** The test runs `main(["--target", path])`.

**Assumptions:** None.

#### `test_help_gives_status_0_and_lists_the_options`

**Checks:** `--help` gives status 0 (it is not an error in the arguments), and the help
text names each option.

**How:** The test runs `main(["--help"])` and looks for each option name in stdout.

**Assumptions:** The test does not check the wording of the help.

#### `test_the_summary_has_a_line_for_each_check_and_target_and_the_reasons_below_them`

**Checks:** The summary has one line for each check and target, by target in the order of
the config and then by check ID, with the state, the ID, the target, the value with its
unit and the limit, the detail of a fail, and `*` on a required result only. The reason of
a "not evaluated" result is below the table, once for each result, and not in its line.
The summary ends with the exit status line.

**How:** Two test rules (a failing one that gives the detail "axis y", and one that is not
evaluated) run for two targets from a config that makes the failing one required for the
target `b`. The test splits the output at the blank lines and compares the first line of
each block, the state, the ID and the target of each row, and the required marker. It
checks the text of the value and of the detail in the row of the fail, and that the reason
is only in the block of the problems, twice.

**Assumptions:** The test depends on the layout of the summary: blocks that blank lines
separate, and columns that two spaces separate. It does not check the exact widths.

#### `test_the_summary_lists_the_errors_and_the_unused_sections_of_each_target`

**Checks:** The summary lists each "error" result with its reason, and, for each target
that has unused profile sections, one line with the target name and the sections. A target
with none has no line. The last line says that status 1 means an error or a required check
that was not evaluated.

**How:** A test rule gives an error. The command runs on `tests/profiles/unused.toml` and a
plain profile. The test checks the first lines of the blocks, the text of the error block,
and the one line of the unused sections.

**Assumptions:** The unused sections of `unused.toml` include `notes`. The sections of
`models` that no installed model reads are in the list too, and the test does not check
them.

#### `test_the_last_line_says_that_a_failure_comes_with_an_error`

**Checks:** With a fail and an error, the last line of the summary is for status 1 and says
that a check failed too.

**How:** The test installs one failing and one erroring test rule and reads the last line.

**Assumptions:** None.

#### `test_end_to_end_with_the_installed_checks_and_the_prisma_profile`

**Checks:** The command runs the installed checks on a synthetic spin-echo sequence with
`tests/profiles/prisma.toml`, and writes a summary that has a line for each of three checks
and ends with the exit status line of the status that it returns.

**How:** The test runs `main` with no test rules and checks that the status is 0 or 2, that
the IDs `gradient.amplitude.axis`, `pns.safe` and `timing.rasters` are in the output, and
the last line.

**Assumptions:** The test does not check the numbers or the states of the checks. The
status can be 0 or 2, because the timing of the synthetic sequence depends on the profile
that the test uses.

#### `test_the_summary_has_a_count_line_for_each_result_with_findings_and_no_finding_line`

**Checks:** By default, the summary has a findings part after the results and before the
exit status, with the header "findings (each one is in the JSON result; --show-findings
lists them here):" and one count line for each result with findings ("t.f, target a: 3
findings"). A result without findings has no line, and the code of no finding is in the
output. The status is 0.

**How:** One test rule gives no findings and one gives the three findings of `FINDINGS`.
The test splits the output at the blank lines and compares the first line of each block, the
lines of the findings block, and checks that no finding code is in the output.

**Assumptions:** The test depends on the layout of the summary: blocks that blank lines
separate. The findings pass through `ctx.result` as a field of the result (`test_run.py`).

#### `test_a_result_with_one_finding_says_1_finding`

**Checks:** The count line of a result with one finding says "1 finding", not "1 findings".

**How:** A test rule gives the first finding of `FINDINGS`. The test compares the lines of
the findings block after the header.

**Assumptions:** None.

#### `test_show_findings_lists_each_finding_after_the_line_of_its_result`

**Checks:** With `--show-findings`, the header is "findings:", and each kept finding is
below the count line of its result, in the order of the results (the targets in the order of
the command, then the check IDs), indented by 4 spaces. A finding with a block is written
"block 1 at 0 s: CODE: message", one with a time and no block "at 0.5 s: CODE: message", and
one with no location "CODE: message". The second line of a message has 6 spaces. The
findings part is between the results and the exit status line.

**How:** Two test rules (three findings, and one finding) run for two targets. The test
compares all the lines of the findings block with the expected lines, and the first lines of
the last two blocks.

**Assumptions:** The format of the time is `:.6g`; the values 0 and 0.5 do not test other
values.

#### `test_json_to_a_file_has_all_the_findings_and_the_console_has_no_finding_line`

**Checks:** With `--json FILE` and no limit, the file has all the findings of each result,
in order, with `findings_omitted` 0, and the console output has the count line and no
finding code.

**How:** The test runs `main`, reads the file with `ResultMatrix.from_json`, and compares the
findings and the omitted number of each result. It compares the findings block of the
console output and checks that no finding code is in it.

**Assumptions:** The round trip of a finding through JSON is in `test_results.py`.

#### `test_json_to_stdout_with_findings_is_only_the_json_and_the_findings_do_not_go_to_stderr`

**Checks:** With `--json -`, the standard output is only the JSON result, with all the
findings, and the standard error has the summary as before: the count line and no finding
line. With `--quiet`, the standard error is empty.

**How:** The test reads stdout with `ResultMatrix.from_json`, which refuses any other text,
and compares the findings. It compares the findings block of stderr, checks that no finding
code is in it, and runs again with `--quiet`.

**Assumptions:** None.

#### `test_max_findings_limits_the_json_and_the_summary_and_records_the_omitted_number`

**Checks:** With `--max-findings 1` and with `--max-findings 0` (parametrized), the JSON
result keeps the first N findings of the result with three, and has `findings_omitted` 3
minus N. The result without findings does not change. The summary count line says "3
findings (N kept, 3-N omitted)", and with `--show-findings` it lists only the kept findings.

**How:** The test runs `main` with `--json FILE` and `--show-findings`, reads the file back,
and compares the findings and the omitted number of each result. It compares the first two
lines of the findings block, the number of its lines, and the start of the first finding line
when one is kept.

**Assumptions:** The logic of the truncation is `ResultMatrix.with_max_findings`
(`test_results.py`). This test shows only that the command applies it before the JSON result
and the summary.

#### `test_max_findings_at_or_above_the_count_changes_nothing`

**Checks:** With `--max-findings 3` for a result with three findings, the JSON result has
all the findings and `findings_omitted` 0, and the count line has no "kept" or "omitted".

**How:** The test runs `main` with `--json FILE`, reads it back, and compares the result and
the lines of the findings block.

**Assumptions:** None.

#### `test_max_findings_that_is_not_an_integer_of_0_or_more_gives_status_1`

**Checks:** `--max-findings` with "-1", "x" or "1.5" gives status 1, nothing on stdout, and
a message on stderr that has `pulseq-check: error:` and names the option.

**How:** A parametrized test runs `main` with each value and a valid sequence and profile.

**Assumptions:** The message of argparse for the value comes from `ArgumentTypeError`; the
test does not check its wording.

#### `test_the_findings_do_not_change_the_status`

**Checks:** A failing result with findings gives status 2 with `--show-findings`, and the
last line of the summary is "exit status 2: a check failed", the same as without findings.

**How:** The test runs `main` with a failing test rule that gives findings, checks the status
and the last line, and then runs a failing test rule without findings and checks the status.

**Assumptions:** The status of a passing result with findings is checked by the count-line
test (status 0).

#### `test_a_run_without_findings_has_no_findings_part_and_the_flags_change_nothing`

**Checks:** When no result has findings, the summary has no findings part: the blocks are the
sequence, the results and the exit status. `--show-findings` and `--max-findings 0` give
exactly the same output.

**How:** One passing and one failing test rule run two times: with no flag, and with both
flags. The test compares the first line of each block of the first output, that it has no
findings block, and the whole of the second output with the first.

**Assumptions:** The test does not compare the summary with a text from before the change;
the other summary tests of this file did not change and pass.

#### `test_the_console_script_is_the_main_function_of_the_cli`

**Checks:** The installed package has the console script `pulseq-check` with the target
`pulseq_checks.cli:main`, and it loads the `main` function.

**How:** The test reads the `console_scripts` entry points and compares the value and the
loaded object.

**Assumptions:** The environment has the package installed after the last change to the
entry points (`uv sync --reinstall-package pulseq-checks`). The test does not run the
script, and it does not check that the script uses the return value as the exit status: the
wrapper that the build backend writes does that.

### 2.17 Time budget (`test_budget.py`)

#### `test_the_fast_checks_of_100000_blocks_are_within_the_ci_budget`

**Checks:** The fast checks, run with `fast_only=True` on a repeating sequence of 100 000
blocks, take at most `CI_BUDGET_S` seconds, and none of their results is "error".

**How:** The test builds `build_repeating` of `scale_sequences.py` for 100 000 blocks,
writes it to `tmp_path`, and writes a profile with the synthetic limits of
`synthetic.SYSTEM` and the default rasters. It times `run_checks` (one read of the file and
the fast checks) with `time.perf_counter`. The build and the write are not timed. The
test also asserts that the fast checks ran (at least one result) and that no result is
"error" or "not evaluated", so that a broken or skipped check does not look fast.

**Assumptions:** The test finds a large slowdown only: `CI_BUDGET_S` has a large margin,
which keeps the test stable on shared CI machines. It is not the budget of decision 7 of
the plan: that budget is the measurement of `scripts/budget.py` on 10^6 blocks, made
before each tag. The fast checks are the ones of task 8.3 (`timing.rasters` and the three
gradient checks); the profile has no SAFE parameters because `pns.safe` is slow.
