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
2. [Tests](#2-tests): the package; the SAFE model; the target profile, the
   results, the run function and the check configuration; the Siemens `.asc`
   profile reader; the version 1 checks (timing, gradient and PNS); the
   command; the time budget. The tests of the measurement modules are in the
   package pulseq-analysis.

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

### 2.1 The SAFE model (`test_safe_model.py`)

`test_safe_model.py` tests `safe_model.py`: `SAFE_MODEL`, the model `pns.safe` of the
target profile, which reads and checks the nine fields of each axis, and `hw_from_dict`,
which makes the hardware struct of a checked dict. The hardware struct and `pns_levels`
are in the package pulseq-analysis, which has its own tests. The tests here compare
the results exactly: the same struct values give the same float operations.

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
`pns_levels(seq)`.

**Assumptions:** None.

### 2.2 Target profile (`test_profile.py`)

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

**Assumptions:** The entry point of `safe_model.SAFE_MODEL` is installed (`uv sync` after
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

### 2.3 Results (`test_results.py`)

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

### 2.4 The run function (`test_run.py`)

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

#### `test_the_rasters_of_a_file_of_format_1_5_0_come_from_the_file`

**Checks:** For a `.seq` file of format 1.5.0 that pypulseq writes, `ctx.raster_sources` is
`"file"` for all four rasters, also when the profile gives a different
`GradientRasterTime`. `seq.grad_raster_time` is the raster of the file.

**How:** The test writes `spin_echo_sequence()` to a file, runs a rule with a target whose
`[rasters]` has `GradientRasterTime = 4e-6`, and reads `raster_sources` and the sequence from
the context that the rule got.

**Assumptions:** pypulseq writes the four rasters to `[DEFINITIONS]`.

#### `test_a_raster_that_a_file_of_format_1_5_0_does_not_declare_comes_from_the_target_or_pypulseq`

**Checks:** When the `GradientRasterTime` line is not in the file, its source is `"target"` for a
profile that gives `rasters.GradientRasterTime` and `"pypulseq default"` for a profile with no
`[rasters]`. The other three rasters stay `"file"`. The raster is not in `seq.definitions`
(pypulseq does not add it for a file of format 1.4.0 or newer), and `seq.grad_raster_time` is
4 µs for the target and the pypulseq default 10 µs without it.

**How:** The test writes `spin_echo_sequence()` to a file, removes the `GradientRasterTime`
line of the text, and runs a rule for the two targets.

**Assumptions:** The file has a 10 µs gradient raster and the removal of the line does not
change the blocks. This test also pins the behavior of pypulseq for a format 1.4.0 or newer
(a missing raster is not in `seq.definitions`).

#### `test_the_rasters_of_a_file_of_format_1_3_1_come_from_the_target_or_pypulseq`

**Checks:** For a hand-written file of format 1.3.1, with no `[DEFINITIONS]`, no raster is
`"file"`: the source is `"target"` for the rasters that the profile gives, and `"pypulseq
default"` for the others. The four rasters are in `seq.definitions`, with the value of the
target or of pypulseq. With no `[rasters]` all four are `"pypulseq default"`.

**How:** The test writes a minimal file (one block with a trapezoid on x) with `[VERSION]` 1
3 1 and no definitions. The target gives `GradientRasterTime` and `BlockDurationRaster`. The
test checks `raster_sources`, and that `seq.definitions` has all four names, with the 4 µs of
the target and the 1 µs of pypulseq for `RadiofrequencyRasterTime`. It runs the same file with
a target with no `[rasters]`.

**Assumptions:** This test pins the behavior of the pinned pypulseq (`read_seq.py`): for a
file older than 1.4.0 `read` calls `Sequence.set_definition` for each raster that the file
does not declare, and only there. If a new pypulseq changes that, this test fails and the
detection in `run._read_sequence` needs a change. The test hides the warnings of pypulseq for
an old file.

#### `test_the_rasters_of_a_sequence_object_come_from_the_sequence_object`

**Checks:** For a `Sequence` object, all four rasters have the source `"sequence object"`,
also when the profile gives a raster.

**How:** The test runs a rule on `spin_echo_sequence()` with a target that gives
`GradientRasterTime`, and checks the names and the sources.

**Assumptions:** None.

#### `test_the_read_of_a_file_does_not_change_set_definition_of_the_sequence`

**Checks:** After the read of a `.seq` file, the sequence has no instance attribute
`set_definition` (the record of the undeclared rasters is removed), and a raster that the
file declares has the value of the file. When `Sequence.read` raises, the instance attribute
is also removed, and the run function gives the `RunError` of the read.

**How:** The test runs a rule on a file and checks `vars(seq)` and `seq.definitions`. It
then replaces `pp.Sequence.read` with a function that keeps the sequence and raises
`ValueError`, runs `run_checks`, and checks the `RunError` and `vars(...)` of the kept
sequence.

**Assumptions:** The test checks the instance attribute, not that a later call of
`set_definition` works; the method of the class is not changed.

#### `test_a_default_raster_that_a_check_uses_gives_not_evaluated_and_run_is_not_called`

**Checks:** A check with `rasters` that lists two rasters that the file does not declare, for a
target with no `[rasters]`, gives "not evaluated". The reason names both rasters and the target.
`run` is not called.

**How:** The test removes the `GradientRasterTime` and `AdcRasterTime` lines from a file, runs
a rule that lists these two rasters, and compares the reason with the full text.

**Assumptions:** None.

#### `test_a_missing_input_and_a_default_raster_give_one_reason`

**Checks:** When a check lacks an input and a raster, the result is "not evaluated" with one reason
that has the text for the input (unchanged) and the text for the raster, separated by a
semicolon. `run` is not called.

**How:** The test runs a rule with the input `opts.max_grad` and the raster
`GradientRasterTime` on a file without that raster and a target without either, and compares
the reason with the full text.

**Assumptions:** None.

#### `test_a_raster_that_a_check_uses_and_the_target_or_the_file_gives_is_not_a_reason`

**Checks:** A check that lists a raster that the target gives (the file does not declare it) and a
raster that the file declares runs, and passes. The same check on a `Sequence` object runs for a
target with no `[rasters]`.

**How:** The test runs a rule with `rasters` of `GradientRasterTime` and `BlockDurationRaster`
on a file without the first line, for a target that gives it, and then on
`spin_echo_sequence()`.

**Assumptions:** None.

#### `test_a_spec_without_rasters_and_the_context_of_a_hand_made_run_work_as_before`

**Checks:** A `CheckSpec` that a plugin makes with the fields up to `findings` by position has
`rasters == ()` and runs as before. A `RunContext` that is made by hand has the source
`"sequence object"` for all four rasters.

**How:** The test makes a `CheckSpec` with 13 positional arguments, runs it with `run_checks`,
and makes `RunContext(sequence, profile)`.

**Assumptions:** The positional order of the earlier fields does not change. A rule that is
called directly (without `run_checks`) is not checked for rasters: only the run function does it.

#### `test_a_spec_without_a_promise_runs_as_before`

**Checks:** A `CheckSpec` that a plugin makes with the fields up to `rasters` by position has
`promise is None` and runs as before.

**How:** The test makes a `CheckSpec` with 14 positional arguments, checks that its `promise` is
`None`, and runs it with `run_checks` on a synthetic sequence: the result is a pass.

**Assumptions:** The positional order of the earlier fields does not change. The run function
does not read `promise`; the test does not check how a plugin documents a check without one.

#### `test_each_check_of_this_package_gives_a_promise_with_three_texts`

**Checks:** Each check of the distribution `pulseq-checks` has a `CheckPromise` in its
specification, with a text that is not empty for what a pass guarantees, what a fail means and
what the check does not promise.

**How:** The test loads the check entry points of the distribution `pulseq-checks`, compares
their IDs with the six checks of version 1, and checks the type of `spec.promise` and that each
of its three texts is a string that is not empty.

**Assumptions:** The test does not check that a text is true. `scripts/check_docs.py` shows the
texts in `docs/checks.md`, and the review of a change checks them. A new check of this package
must be added to the list of IDs.

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

### 2.5 Check configuration (`test_config.py`)

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

### 2.6 Siemens .asc profile reader (`test_asc_profile.py`)

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

### 2.7 Timing checks (`test_check_timing.py`)

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

### 2.8 Gradient checks (`test_check_gradient.py`)

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
`test_grad_limits.py` of pulseq-analysis).

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

**Checks:** For a target with only `opts.max_grad`, the rules compare with a
`HardwareLimits` that has the limit from the `pp.Opts` of the target (in mT/m, with the
gamma of that Opts), nan for the other limit, and the name of the target as the label.

**How:** The test spies on `_hardware_limits` in the check module (the spy calls the real
function and keeps each `HardwareLimits` that it gives), runs the three rules on a target
with `max_grad` 20 mT/m and `gamma` 40 MHz/T, and checks the first limits: the limit is
20 mT/m (with 42.576 MHz/T it would be 18.8), the other one is nan and the label is the
name of the target. The measurement uses the same gamma as the limits (see
`test_a_profile_with_another_gamma_compares_value_and_limit_with_that_gamma`).

**Assumptions:** `_hardware_limits` gives the same limits for each rule of one target (it
reads only the context). `gradient_limits` has no limits argument, so a nan limit cannot
change the numbers.

#### `test_a_target_with_only_max_slew_gives_max_grad_as_nan`

**Checks:** The same for a target with only `opts.max_slew`: the slew limit is in T/m/s,
the amplitude limit is nan, and the label is the name of the target.

**How:** The same spy on `_hardware_limits`, with a target with `max_slew` 300 T/m/s. It
checks the first limits.

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
and with the gamma of that target only, and the rules compare with the hardware limits of
the targets.

**How:** The test writes a `.seq` file, runs the three rules for two targets with
different limits, the spy on `gradient_limits` and the spy on `_hardware_limits`. It
checks that all six results are "pass", that there are two calls of `gradient_limits`,
that the only keyword argument of each call is `gamma`, that the gamma is 42.576 MHz/T
(the targets do not give `gamma`), and that the limits that the rules use are the
`hardware_limits` of the two targets.

**Assumptions:** `run_checks` reads the file one time for each target (tested in
`test_run.py`).

#### `test_the_three_checks_of_one_target_call_gradient_limits_one_time`

**Checks:** For a `Sequence` object and one target, the three rules call `gradient_limits`
one time, and compare with the hardware limits of the target.

**How:** The test runs the three rules with the spy on `gradient_limits` and the spy on
`_hardware_limits`. It checks that there is one call, and that each limits that the rules
use is the `hardware_limits` of the profile.

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

#### `test_limits_from_sequence_converts_values_and_limits_with_the_gamma_of_seq_system`

**Checks:** With `limits_from_sequence=True` and a `Sequence` object whose `system` has a
gamma of 40 MHz/T, the three rules convert the values and the limits with that gamma, not
with 42.576 MHz/T.

**How:** The test builds a `pp.Opts` with the gamma 40 MHz/T and the limits 28 mT/m and
150 T/m/s, and an x trapezoid of 20 mT/m with the rise time 200 µs (slew 100 T/m/s) with
it. It runs the rules on a target that gives no value, and checks that the three results
are "pass", with the values 20 mT/m, 100 T/m/s and 20 mT/m and the limits 28 mT/m,
150 T/m/s and 28 mT/m. With 42.576 MHz/T the values would be 18.8 mT/m and 94 T/m/s.

**Assumptions:** `pp.Opts` stores the limits in Hz/m and Hz/m/s with its own gamma, so the
limits in mT/m and T/m/s are the ones that the test gave.

#### `test_a_profile_with_another_gamma_compares_value_and_limit_with_that_gamma`

**Checks:** (R9 of `docs/plans/pulseq-checks.md`.) A profile with `gamma` 40 MHz/T
and the limits 20 mT/m and 200 T/m/s, and a file with a 21 mT/m gradient (slew 210 T/m/s),
give "fail" for each of the three rules, with the value 21 mT/m, 210 T/m/s and 21 mT/m and
the limit of the profile. The value and the limit use the same gamma.

**How:** The test builds a `pp.Opts` with gamma 40 MHz/T and an x trapezoid of
840 kHz/m (21 mT/m with that gamma) with the rise time 100 µs, writes the file to
`tmp_path`, and runs each rule alone with `run_checks` for the profile. It checks the
state, the value (`pytest.approx`), the limit and the unit. With the constant 42.576 MHz/T
the amplitude would be 19.7 mT/m and the rules would pass.

**Assumptions:** `run_checks` reads the file with the `pp.Opts` of the target, so
`seq.system.gamma` is 40 MHz/T. The tests of the other checks in this file give no `gamma`,
and so test the default of 42.576 MHz/T (the value of pypulseq).

#### `test_a_rotation_gives_error_for_the_three_checks`

**Checks:** For a sequence that uses the rotation extension, each of the three rules gives
the state "error" with a reason that starts with `NotImplementedError`, and no value.

**How:** The test gives a sequence a non-empty `rotation_library` (the way pypulseq draft PR
#372 stores rotations, as `tests/test_extensions.py` of pulseq-analysis does) and runs the three
rules with `run_checks`. It checks the state, the reason and that the value is None.

**Assumptions:** The test uses a rotation library that is set by hand: pypulseq 1.5.0.post1
cannot make a rotation, and its `Sequence.read` raises `ValueError` for a file with one
(the run function makes that an error of the run, not a result). The test does not cover a
later pypulseq that stores a rotation in another way (see `refuse_rotations`).

#### `test_the_spec_sets_each_field`

**Checks:** For each of the three rules, the `CheckSpec` has the expected ID, version 1,
cost class `"fast"` (task 8.3 of the plan), `url` None, no model, the expected input (`opts.max_slew` for the slew
rule, `opts.max_grad` for the other two), the rasters `GradientRasterTime` and
`BlockDurationRaster`, a non-empty title, quantity, limit, tolerance and pass condition, and a
`findings` text that names each code of the rule (`AMPLITUDE_ABOVE_LIMIT`; `SLEW_ABOVE_LIMIT`
and `JUNCTION_SLEW_ABOVE_LIMIT`; `VECTOR_AMPLITUDE_ABOVE_LIMIT`).

**How:** The test compares each field, checks that each of the five texts is a string
with a character that is not white space, and that `findings` is a string with each code of the
rule in it.

**Assumptions:** The test does not check the rest of the text of the specification: a person
reads it in `docs/checks.md` (phase 6). It does not check the entry points in
`pyproject.toml`. The version stays 1 (design section 5.4).

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

#### `test_a_raster_that_the_file_does_not_declare_and_the_target_does_not_give_is_not_evaluated`

**Checks:** When the file does not declare `GradientRasterTime` (or `BlockDurationRaster`) and
the profile has no `[rasters]`, all three gradient checks give "not evaluated", with the
reason "the file does not declare <raster> and the target 't' does not give rasters.<raster>"
and no value, although the profile gives both limits.

**How:** The test writes `raster_4us_sequence` to a file, removes the line of the raster from
`[DEFINITIONS]` and runs the three rules with `run_checks` for a profile with `max_grad = 100`
and `max_slew = 50`. Before the change, the checks passed or failed with a raster of pypulseq.

**Assumptions:** The test hides the warning of pypulseq for a missing `BlockDurationRaster`. It
does not run the checks of other modules.

#### `test_a_raster_that_the_file_does_not_declare_comes_from_the_target`

**Checks:** With the `GradientRasterTime` line removed and `rasters.GradientRasterTime` in the
profile, the three checks are evaluated with the raster of the target. With 4 µs the slew is
the junction value 60 T/m/s (a fail against 50 T/m/s). With 10 µs the times of the gradient
points are 2.5 times longer, and the slew is the junction value 24 T/m/s (a pass). The amplitude
checks pass with 16 mT/m in both cases.

**How:** The test writes `raster_4us_sequence`, removes the line, and runs the three rules
with a profile that gives both limits and the raster. The values have a relative tolerance of
1e-4 (the file stores the amplitudes with fewer digits). A profile with a raster is
`replace(profile, rasters=..., sources=...)`.

**Assumptions:** The raster of the target is the raster that pypulseq uses for the missing
definition (`seq.system`). This behavior did not change in this phase: the test pins it.

The next tests check the findings of the three rules (`docs/plans/gradient-pns-findings.md`,
sections 3.2 and 4). Most of them use `findings_sequence`: five blocks, with the rise time 100 µs
as in the other tests (block 1: x at 30 mT/m; block 2: a delay; block 3: y at 10 mT/m; block 4: x
at 25 and y at 40 mT/m at the same time; block 5: z at 22 and x at 5 mT/m). With the limit 20
mT/m (200 T/m/s) block 3 and the x of block 5 are below the limit, and block 4 has two axes above
it. |G| is 30, 10, hypot(25, 40) and hypot(22, 5) mT/m. The expected findings of each rule
(`FINDINGS_EXPECTED`) are written by hand from these amplitudes: the peak time of an amplitude is
the end of the rise (the start of the block plus 100 µs), the time of a slew is the start of the
block (the start of the rise).

#### `test_a_pass_has_no_findings_and_does_not_measure_the_blocks`

**Checks:** For each of the three rules, a result of "pass" has no findings, and the measurement
`gradient_blocks` is not calculated: `block_gradient_values` is not called, and the measurements
of the `RunContext` have `gradient_limits` and not `gradient_blocks`.

**How:** The test runs the rule on `findings_sequence` with a limit that is 3 times the limit of
the fail tests, with a `RunContext` that it makes, and with `block_gradient_values` of the check
module replaced by a function that keeps the calls of the real one. It checks the state, the
findings, the list of calls and the keys of `ctx._measurements`.

**Assumptions:** The test reads `ctx._measurements`, a private attribute, because the
measurement is not visible in the result.

#### `test_a_fail_has_one_finding_for_each_block_and_axis_above_the_limit_in_order`

**Checks:** For each rule, a fail has one finding for each block (and axis) above the limit, in
the play order of the blocks, and then in the order of the axes x, y, z. A block and an axis below
the limit give no finding (block 3, and the x of block 5). Each finding has the expected code,
the block, the time, the keys of `data` (`axis` for the two axis rules, the value and the limit
with their units), the value, the limit as the limit of the target, and the message with the
axis, the value (4 significant digits) and the limit. The amplitude rule gives 4 findings, the
slew rule 4 (all `SLEW_ABOVE_LIMIT`, because `findings_sequence` has no junction step), the
vector rule 3.

**How:** The test runs the rule with the limit 20 mT/m (or 200 T/m/s) and compares the findings
with `FINDINGS_EXPECTED`. The values and times have `pytest.approx`, the limit and the codes are
exact.

**Assumptions:** The trapezoids of `findings_sequence` have equal rise and fall slopes, so the
first segment (the rise) is the steepest one.

#### `test_the_data_of_a_finding_are_python_scalars`

**Checks:** The block of the location of each finding is a Python `int`, its time a Python
`float`, and each value of `data` a Python `float` or `str`, not a NumPy type.

**How:** The test checks `type(...)` of each of them for each of the three rules.

**Assumptions:** None.

#### `test_a_fail_measures_the_blocks_one_time_for_each_target_and_does_not_change_the_result`

**Checks:** A fail calls `block_gradient_values` one time for each target, with the gamma that
`gradient_limits` uses (the default 42.576 MHz/T for a profile without a gamma), and a second
run of the rule on the same `RunContext` gives the same findings without a second call. The value,
the location and the reason of the result are the ones that the rule gives for a limit that the
sequence does not reach; the limit and the unit are those of the target.

**How:** The test runs the rule two times on one `RunContext` and a third time on a new one
with the limit `FAR`, with `block_gradient_values` replaced as in the first test.

**Assumptions:** None.

#### `test_the_worst_finding_is_the_value_and_the_location_of_the_result`

**Checks:** The largest value of the findings is the value of the result (equal, not
approximately), and the location of that finding is the location of the result. Each finding is
above the limit.

**How:** The test takes the finding with the largest value in `data` and compares it with
the result.

**Assumptions:** The value of the finding is calculated by `block_gradient_values` and the value
of the result by `gradient_limits`, with the same arithmetic (`test_grad_limits.py` of
pulseq-analysis compares them with `==`).

#### `test_a_block_within_the_tolerance_of_the_limit_has_no_finding`

**Checks:** A block whose value is above the limit by 5e-10 (relative, within the tolerance
1e-9) gives no finding, while a block that is clearly above the limit does.

**How:** The test builds two blocks (x at 20 and x at 30 mT/m). It takes the value of the first
block from a run with the limit `FAR`, and sets the limit to that value divided by `1 + 5e-10`.
The result is a fail (block 2), and the only finding is for block 2.

**Assumptions:** The value of the x trapezoid at 20 mT/m is the same in the two sequences (the
same trapezoid).

#### `test_a_value_that_is_not_a_number_is_above_the_limit`

**Checks:** The rule that gives the state and selects the findings, "not at or below
`limit * (1 + 1e-9)`", counts a value that is not a number as above the limit, so such a
value fails, as it did before the findings, and is a finding. A value at the limit, and a
value above it by less than the tolerance, are not above it; a value above it by more than
the tolerance is.

**How:** The test calls `gradient._above_limit` with an array of nan, the limit, the limit
times `1 + 5e-10` and the limit times `1 + 2e-9`, and with the scalar nan, and compares the
results.

**Assumptions:** `gradient_limits` does not give nan for a normal file; the test covers the
rule only, not a sequence that makes nan.

#### `test_a_junction_step_and_a_segment_of_the_same_block_give_two_findings_the_step_first`

**Checks:** For a block with a step at its start and a segment, both above the slew limit on the
same axis, `gradient.slew.axis` gives two findings for that block and axis, the
`JUNCTION_SLEW_ABOVE_LIMIT` one before the `SLEW_ABOVE_LIMIT` one. Both have the block 2, the
start of block 2 as the time, the value 135 T/m/s and the limit 100 T/m/s, and the messages of
their codes. The result value is 135 T/m/s, at block 2.

**How:** The test builds two extended trapezoids on the system `SYSTEM` (the sequence of
`test_grad_limits.py` of pulseq-analysis, `_junction_and_segment_sequence`): block 1 ends at 8.4
mT/m, block 2 starts at 0.9 times the largest step that `add_block` accepts below it, and its
first segment returns in one gradient raster. The slew of block 1 is 84 T/m/s. It runs the rule
with the limit 100 T/m/s.

**Assumptions:** `add_block` accepts the step (it is 0.9 of the largest one).

#### `test_a_step_before_a_block_with_no_gradient_gives_a_finding_at_the_start_of_that_block`

**Checks:** A gradient that ends at a value that is not 0, followed by a block with no gradient
on that axis (a delay), gives one `JUNCTION_SLEW_ABOVE_LIMIT` finding at block 2 and the start
of block 2 (200 µs), with the value 135 T/m/s. No segment is above the limit.

**How:** The test builds the sequence on `SYSTEM` (as
`_gradient_ends_non_zero_before_delay_sequence` of `test_grad_limits.py` of pulseq-analysis) and
runs the slew rule with the limit 100 T/m/s.

**Assumptions:** None.

#### `test_a_profile_with_another_gamma_gives_findings_in_the_units_of_the_result`

**Checks:** For a profile with gamma 40 MHz/T, a 21 mT/m gradient (slew 210 T/m/s) and the limits
20 mT/m and 200 T/m/s, each rule fails with one finding whose value is equal to the value of the
result (21 mT/m, or 210 T/m/s for the slew), in the same units as the limit. With 42.576 MHz/T
the value would be 19.7 mT/m and pass.

**How:** The test builds the sequence in memory with a system with gamma 40 MHz/T, runs each
rule with `run_one`, and compares the value of the one finding with the value of the result
(equal) and with the hand-computed value (`pytest.approx`).

**Assumptions:** The sequence object is not written to a file, so the values have no rounding of
the file.

### 2.9 PNS check (`test_check_pns.py`)

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

**How:** The test builds the object with its helper `_with_rotation_library` (a
`gre_sequence` with a `rotation_library`, as pypulseq draft PR #372 stores rotations) and
runs the check on it.

**Assumptions:** The check does not catch the exception of `pns_levels`.

#### `test_a_sequence_without_gradients_passes_with_zero`

**Checks:** A sequence with a delay block only gives "pass", value 0.0, no location, and
the model and its version.

**How:** The test runs the check on `empty_sequence()`, with the failing scale.

**Assumptions:** None.

#### `test_a_raster_that_the_file_does_not_declare_and_the_target_does_not_give_is_not_evaluated`

**Checks:** When the file does not declare `GradientRasterTime` (or `BlockDurationRaster`) and
the profile has no `[rasters]`, `pns.safe` gives "not evaluated", with the reason "the file
does not declare <raster> and the target 'Test target' does not give rasters.<raster>" and no
value, although the profile has the SAFE parameters.

**How:** The test removes the line of the raster from the gradient-echo file and runs the
check with the failing scale.

**Assumptions:** The test hides the warning of pypulseq for a missing `BlockDurationRaster`.

#### `test_a_raster_that_the_file_does_not_declare_comes_from_the_target`

**Checks:** With the `GradientRasterTime` line removed and `rasters.GradientRasterTime` of 4 µs
or 10 µs in the profile, the check is evaluated (a fail with the failing scale). The value is
100 times the peak of `pns_levels_for` for the file read with the `Opts` of the profile, and
the value for 4 µs is not the value for 10 µs.

**How:** The test runs the check for each raster and compares the values with `expected_peak`,
and the two values with each other.

**Assumptions:** The raster of the target is the raster that pypulseq uses for the missing
definition (`seq.system`). The difference of the two values shows that `pns_levels` uses the
raster (`dt` and the sample times); the test does not check the size of the difference.

#### `test_a_pass_has_no_findings`

**Checks:** With the passing scale the state is "pass", `findings` is empty and
`findings_omitted` is 0.

**How:** The test runs the check on the gradient-echo `.seq` file with the passing scale.

**Assumptions:** None.

#### `test_a_sequence_without_gradients_has_no_findings`

**Checks:** A sequence with a delay block only gives no finding, also with the failing scale.

**How:** The test runs the check on `empty_sequence()`, with the failing scale.

**Assumptions:** None.

#### `test_a_fail_gives_one_finding_for_each_interval_in_time_order`

**Checks:** The failing case gives one finding for each interval of `above_limit` of
`pns_levels_for` (same sequence, same SAFE parameters), in the same order. Each finding has
the code `PNS_ABOVE_LIMIT`, the time `start_s` of its interval and the block ID of the last
block that starts at or before that time in its location, the five data values (`start_s`,
`end_s`, `peak_percent` as 100 times the interval peak, `peak_time_s`, `num_samples`), and
the message with the start, the end and the peak. The times of the locations do not
decrease.

**How:** The test runs the check on `gre_sequence(num_trs=2)` with the failing scale and
computes the expected values from `pns_levels_for` and `sequence_index`. It finds the block
with a loop over the blocks (`block_at`), not with `np.searchsorted`.

**Assumptions:** The failing case has at least one interval. The message is built in the
test with the same format as in the check, so a change of the format needs a change of the
test.

#### `test_the_data_and_the_location_of_a_finding_are_python_scalars`

**Checks:** The block of the location is a Python `int`, its time and each data value but
`num_samples` are Python `float`, and `num_samples` is a Python `int` (not NumPy scalars).

**How:** The test checks `type(value) is ...` for each finding of the failing case.

**Assumptions:** The failing case has at least one finding.

#### `test_the_value_and_the_location_of_the_result_do_not_change_with_the_findings`

**Checks:** The largest `peak_percent` of the findings equals the value of the result. The
value is 100 times the peak of `pns_levels_for`, the limit and unit are 100.0 and `%`, the
location is the time `peak_time_s` and its block, and `reason` is None.

**How:** The test runs the failing case and compares the result with `pns_levels_for` and
`sequence_index`.

**Assumptions:** The largest peak of the intervals is the peak (`pns_levels`,
`test_a_sequence_below_the_limit_has_no_interval_and_one_above_it_has_some` of
`test_pns_levels.py` of pulseq-analysis).

#### `test_two_separate_intervals_give_two_findings_in_time_order`

**Checks:** Two equal trapezoids on x with a 50 ms gap give two findings. They are in time
order, and the code, the location and the times of each are those of the interval of
`pns_levels_for` with the same number. The two findings have different blocks, and the end of
the first is before the start of the second.

**How:** The limit scale is the peak of one trapezoid with a scale of 1, divided by 1.02,
so that only the larger hump of the total of a trapezoid is at or above 100 %. The test
checks that one trapezoid gives one interval and that two trapezoids give two, then runs the
check on the sequence of two. The scale is the peak divided by 1.02 because the peak is
proportional to the inverse of the scale; the test checks the number of intervals, not that
proportion.

**Assumptions:** The decay of the filters after a trapezoid does not keep the total at or
above 100 % until the second trapezoid.

#### `test_the_spec_has_the_findings_text`

**Checks:** The version of the spec is 1, and its `findings` is a text that names the code
`PNS_ABOVE_LIMIT`.

**How:** The test reads `SAFE.spec`.

**Assumptions:** None.

#### `test_the_spec_gives_each_field`

**Checks:** The ID is `pns.safe`, the version is 1, `models` is `("pns.safe",)`, `inputs`
is empty, `rasters` is `("GradientRasterTime", "BlockDurationRaster")`, `cost` is "slow",
`url` is None, the other text fields are not empty, and
`pypulseq` names `_safe_gwf_to_pns_chunk`.

**How:** The test reads the fields of `SAFE.spec`.

**Assumptions:** None.

### 2.10 The command (`test_cli.py`)

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

### 2.11 Time budget (`test_budget.py`)

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
