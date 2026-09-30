# Design: pulseq-checks

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: step 2 is done (2026-09-30). Version 1 is the release `0.1.0rc1`
(tag `v0.1.0rc1`), made by the implementation plan
`docs/plans/pulseq-checks-v1.md`, whose section 8 gives the results. The user
answered the open decisions on 2026-09-30 (section 11); R6 was changed during
the implementation. This document gives the concepts, the structure and the
decisions.

Source: this document is the part of the pulseq-reports design
[`docs/plans/pulseq-checks.md`](https://github.com/mdtisdall/pulseq-reports/blob/8e66ea54eed9887ccc46662405e19a427c2b0d95/docs/plans/pulseq-checks.md)
that applies to this repository. The design was written in pulseq-reports #102
(commit `51d9590`), and its decisions were recorded in pulseq-reports #103
(commit `8e66ea5`), both on 2026-09-30. Decisions 4 and 6 in this document go
further than the source (section 11).

The work in pulseq-reports is not in this document: the removal of
`Card.checks`, `check_norms` and the exit status 2 before `0.2.0` final, the
check summary card, the exit status of `pulseq-report`, and the removal of
the moved modules from pulseq-reports. The section numbers are the
same as in the source, so that the two documents can refer to each other.
Section 5.11 is new in this document.
In this document, "pulseq-reports" means that repository, and a path such as
`src/pulseq_reports/...` is a path in it.

## 1. Goal

`pulseq-checks` is a pure-Python library that **checks** a Pulseq sequence. A
check compares a sequence with a specification, for example the hardware
limits of one scanner, and gives pass or fail. CI uses checks. A check must
be as fast as possible and declare its cost (section 5.9). Its result must be
clear: pass, fail, not evaluated or error (section 5.3). Its specification must
be clear to a person who reads it.

The checks come from `pulseq-reports`, where they are a part of the report
cards now. `pulseq-reports` will use `pulseq-checks`, and a report can show
the results of the checks. The main goal of a report is still to describe the
sequence, not to run the checks.

The key behavior of `pulseq-checks` is this: apply a specification to a `.seq`
file, when the author of the file did not use that specification. For
example, check a file that was written for one scanner against the limits of
a different scanner.

## 2. Checks and reports

| | Check (this package) | Report (pulseq-reports) |
|---|---|---|
| Question | "Does this sequence meet specification X?" | "How does this sequence behave?" |
| Inputs | The sequence and a specification. The specification is necessary. | The sequence. Context is optional. |
| Output | Pass, fail, not evaluated or error, for each named rule. A machine can read it. | An HTML page that describes the sequence. It needs no verdict. |
| Cost | Fast. It calculates only what its rules need. | It can be slow and complete. |
| Defaults | No default limits. A missing profile field gives "not evaluated". A missing or invalid profile is an error. | Sensible defaults are permitted. |
| Definition | A written specification: the quantity, its definition, the limit, the tolerance and the pass condition. | The documentation of the card. |

A report can include the results of the checks. But the report does not
define a check, and the report is not the tool that CI uses to run the checks.
This package defines the checks and runs them.

## 3. Problems in pulseq-reports that this package must not repeat

In pulseq-reports (`main` at `fd298d5`), the two uses are mixed. Each problem
below gives a requirement for this package.

1. **A check is a part of a card.** To get a pass or fail result, CI must
   build the full report, with the diagram, the spectrum and the RF profiles
   (`Card.checks`, `src/pulseq_reports/page.py:39`).
   Requirement: a check runs with no report, and calculates only what its
   rules need.
2. **One code path gives the verdict and draws the card.** No document gives
   the PNS rule as a specification (`src/pulseq_reports/cards/pns.py:61`).
   Requirement: each check has a written specification (section 5.4).
3. **Missing inputs get silent defaults.** With no limits, the gradient check
   uses `seq.system`, which is what the sequence says about itself. With no
   `.asc` file, the PNS check uses the example hardware of pypulseq
   (`asc.EXAMPLE_HARDWARE`). A pass against limits that are not real is not a
   compliance result.
   Requirement: no default limits. A missing input gives "not evaluated" or an
   error, never a pass (section 5.3, decision 4).
4. **The settings of a check are card options.** The limits, the `.asc` file,
   the coil and `check_norms` are card options. They do not describe a scanner
   as one object.
   Requirement: one target profile describes one scanner (section 5.2).
5. **"Could not calculate" and "failed" are the same result.** When a card
   raises an exception, the registry gives it a failed check with the name
   `error` (`src/pulseq_reports/registry.py:306`).
   Requirement: "not evaluated" and an error are states of their own, and
   they are not "fail" (sections 5.3 and 5.6).

## 4. What pypulseq already gives

Facts from pypulseq `1.5.0.post1`, the version that pulseq-reports pins.

| Check | In pypulseq? | What pypulseq has |
|---|---|---|
| Timing | Yes | `check_timing` returns `(ok, errors)`. It checks the rasters, the block duration, negative delays, the RF dead time and ringdown, the ADC dead times and the soft delays. |
| PNS | Yes | `calculate_pns` returns `ok = all(pns_norm < 1)`. The PNS card of pulseq-reports uses this SAFE model. |
| Gradient amplitude, each axis | Partly | Only when a sequence is built. `make_trapezoid`, `make_arbitrary_grad` and `make_extended_trapezoid` raise an error above `system.max_grad`. |
| Gradient slew, each axis | Partly | Only when a sequence is built. The same functions check the slew. `add_block` checks the steps at block junctions. All use `seq.system`. |
| \|G\| amplitude and slew | Values only | `test_report` writes the maximum of \|G\| and of its slew as text. It gives no verdict. |
| Acoustic resonances | Data and plot only | `asc_to_hw` reads the resonance frequencies and bandwidths from the `.asc` file. `calculate_gradient_spectrum` draws them. It gives no verdict. |
| RF peak B1, B1+rms, SAR | No | `calc_SAR` was removed. It raises an error that names PySar4seq. `Opts` has no B1 limits. |

Two more facts make "apply a new specification to a file" possible:

- `seq.read` does not read the hardware values from the file. The RF dead
  time, the RF ringdown and the ADC dead time come from the `Opts` that the
  caller gives to `pp.Sequence(system=...)`. The file gives only the raster
  times, in `[DEFINITIONS]`.
- `check_timing` compares with `seq.system`. Thus it compares with the
  specification that the caller gives, not with the values of the author.

Conclusion: for timing and PNS, pypulseq has the rule. A check in
`pulseq-checks` is a thin wrapper. For the gradient limits of a finished
file, pypulseq has no check. This gap is the main new function. The
measurement exists already, in `grad_limits.py` of pulseq-reports, and moves
to this package (section 7.2).

## 5. Design

### 5.1 Layers

There are three layers. Each layer uses only the layers below it. This
package has the two lower layers.

| Layer | Package | Contents |
|---|---|---|
| Measurements | `pulseq-checks` | Calculations only: the gradient peaks and slew, PNS, and later the spectrum and RF exposure. Each measurement gives values and where they occur. It gives no verdict. A model is a measurement that needs the parameters of a target, for example SAFE PNS. |
| Checks | `pulseq-checks` | Target profiles, check rules, results and the `pulseq-check` command. |
| Reports | `pulseq-reports` | Cards, the page, the JavaScript and the `pulseq-report` command. A card describes. A card does not decide. |

`pulseq-reports` uses `pulseq-checks`. `pulseq-checks` never uses
`pulseq-reports`. The package boundary enforces this direction.

### 5.2 The parts of a check

Four parts change independently. The profile readers, the models and the
check rules are plugin points (section 5.7). The target profile is data.

| Part | What it is | Examples |
|---|---|---|
| Target profile | What one scanner and its Pulseq interpreter can do, and what they expect | Rasters, dead times, gradient limits, B0, the coil `.asc` file, the supported file versions and extensions, coordinate conventions |
| Profile reader | Fills parts of a target profile from vendor files | A Siemens `.asc` reader now. GE and Philips readers later. |
| Model | Calculates a physical quantity from a sequence and a target | SAFE PNS (pypulseq), a dB/dt model, a neurodynamic body model, a SAR model |
| Check rule | Compares a quantity with a limit. It has a written specification. | "The PNS is below 100 %." "The slew of each logical axis is at or below the limit." |

A new PNS model is a new model plugin. The PNS check rule does not change.
The target profile tells which model applies to that scanner.

Each check rule declares the profile fields and the models that it needs.

A target profile is a TOML or JSON file. It gives the vendor, the rasters,
the dead times, B0 and the gradient limits. It can also give the parameters
of a model, for example the SAFE parameters, and the acoustic resonances. It
can name a Siemens `.asc` file, which gives the SAFE parameters, the acoustic
resonances and the GPA limits. An `.asc` file fills only parts of the profile
that names it. It is never a complete target, because it does not give the
rasters, the dead times or B0. When the profile file and the `.asc` file both
give one value, the result is an error, not a silent override. A site keeps its
profiles where it wants, for example next to its sequences. Section 5.11
gives the format (decision 6).

`HardwareLimits` moves to `pulseq-checks` with `grad_limits` (section 7.2),
and a target profile contains it. `pulseq-reports` exports it again, so its
callers do not break. Its gradient limits card uses it to show the percent of
each limit, with no verdict (decision 8). The target profile replaces the
card options `limits`, `gradient_asc` and `check_norms` of pulseq-reports. A
report can use a target profile as context, for example to show a limit as a
line on a chart. Thus the target profile is a public type of this package.

### 5.3 Results

Each result has:

- the check ID and the version of its specification,
- the target,
- the state: pass, fail, not evaluated or error,
- the measured value, the limit and where the value occurs (block and time),
- the model and its version, when the check uses a model,
- the reason, when the state is "not evaluated" or "error". For a pass or a
  fail, the reason can give a short detail of the value, for example the axis
  or the raster that gave it.

"Not evaluated" is a state of its own. It is not a pass and not a fail. A
check gets it when the target profile does not have a necessary field, or
when a necessary model is not available. Examples:

- PNS with no real SAFE parameters (no `.asc` file, and no SAFE parameters
  in the profile file): not evaluated. The pypulseq example hardware is not a
  real scanner, so it does not give a pass.
- Handedness with no declared convention: not evaluated (section 6.2).

"Error" is also a state of its own. A check gets it when it cannot run on the
sequence: an exception in the check, or an input that the measurement refuses
(for example, the gradient measurement refuses a file that uses the Pulseq
rotation extension). An error is not a fail.

A missing field in a profile gives "not evaluated". A missing or invalid
profile, or a run with no target, is an error of the run (exit status 1,
section 5.6), not a result of a check.

A check run takes one sequence and a list of targets. The result is a matrix
of checks and targets. The same matrix is the output for CI and the summary
in a report.

### 5.4 The specification of each check

Each check has a stable ID, for example `gradient.slew.axis`. The
specification of a check is data that goes with its check rule, and the
documentation is made from this data. A plugin check gives its specification
in the same way, and the documentation of its package shows it. The
specification of each check gives:

- the quantity and its exact definition,
- the inputs from the target profile,
- the limit and the tolerance,
- the pass condition,
- the cost class, `fast` or `slow` (section 5.9),
- the pypulseq function that the check uses, if any.

The message of a result gives the ID, so that a reader can find the
specification. The specification has a version. When a rule changes, its
version changes, so that old CI results stay clear.

### 5.5 What pulseq-reports needs from this package

pulseq-reports shows a summary of the checks near the top of a report. The
summary card is work in pulseq-reports. This package must supply:

- **One function that runs the checks.** It takes a sequence and a list of
  target profiles, and gives the result matrix. `pulseq-check` and
  pulseq-reports both use this function. The same code gives the verdict in
  CI and in a shared report, so the two cannot disagree.
- **Results that a caller can keep.** A caller can give a report a result set
  that was calculated before. Thus the result matrix can be written (JSON,
  section 5.6) and read again.
- **All the data for the summary.** For each target: the source of each
  limit. For each check and target: the ID, the state, the value and the
  limit, the location, and a link to the specification. For each "not
  evaluated" or "error" result: the reason. The reader of a report must see
  what was not asserted, not only what passed.
- **Locations that a card can use.** A card can point to a result, for
  example the "Show" button of the gradient limits card on the value that
  failed. Thus the location (block and time) uses the same block index as the
  measurements.
- **No default limits.** In a report with no target profile, no checks run.
  (For `pulseq-check`, a run with no target is an error, section 5.3.) This
  package does not supply default limits to a report.

### 5.6 The `pulseq-check` command and its exit status

| Status | Meaning |
|---|---|
| 0 | No check failed, no check gave an error, and each required check was evaluated. |
| 2 | At least one check failed. |
| 1 | An error in the arguments or the profiles, a check that gave an error, or a required check that was not evaluated. |

When statuses 1 and 2 both apply, the status is 1: the result set is not
complete. The output still lists each failure.

A check is required for a target when the caller names the check by its ID,
in the configuration file or with a flag. A named check is required for each
target, unless the configuration names the targets for it (for example, PNS
is required only for the Siemens targets). To select checks by cost class
("run the fast checks") does not make them required. A check that is not
required and does not have its inputs gives "not evaluated" in the output,
and the status does not change (decision 3).

A check uses the limits of the sequence (`seq.system`) only when the caller
permits it explicitly, with a keyword argument of the Python function that
runs the checks. The caller can permit it only when the caller gives a
`Sequence` object. `pulseq-check` has no flag for it, and a profile has no
entry for it. The result records that the limits came from the sequence
object. The caller is responsible for the system of that object. A
`Sequence` that `seq.read` reads from a `.seq` file has only the default
values of pypulseq in `seq.system`, because the file does not contain the
limits of its author (decision 4).

The command writes a result that a machine can read (JSON, and maybe JUnit
XML for CI dashboards) and a short summary for a person.

To stop CI on a failed check is the work of `pulseq-check`. In
pulseq-reports, an opt-in flag, for example `--fail-on-check`, makes
`pulseq-report` give a non-zero status when a check in its summary fails.

### 5.7 Plugins

`pulseq-checks` has three entry-point groups: profile readers, models and
check rules. A project can add a check for its site without a card.
(`pulseq-reports` keeps its entry-point group for cards.)

Each package has its own command line (decision 9). `pulseq-checks` has a
public function that reads a check configuration: the targets and the
selected checks. `pulseq-reports` keeps its card options (`options.py`,
`cli.py`) and calls that function. Thus the two commands read the same check
configuration file.

### 5.8 Rely on pypulseq

A check uses the pypulseq rule when pypulseq has one. The timing check calls
`check_timing`. The PNS check calls the SAFE model of pypulseq. The gradient
limits check uses the slew definition of pypulseq (pulseq-reports
[`docs/notes/slew-definitions.md`](https://github.com/mdtisdall/pulseq-reports/blob/51d95900637c0e5e74c7335f57db6659135dc4f4/docs/notes/slew-definitions.md)).
`pulseq-checks` does not copy a rule that pypulseq has.

### 5.9 Cost classes

Each check declares a cost class, `fast` or `slow` (decision 7). The cost
class is one field of the specification of the check, and its default is
`slow`. Thus a plugin check that nobody measured does not make the fast set
slow. A plugin author changes one field to put a check in the fast set.

The caller can select checks, or run only the fast checks. The fast checks of
`pulseq-checks` have a tested time budget on a file with 10⁶ blocks. The
implementation plan sets the number after a measurement. The budget test does
not include plugin checks. A plugin author can use the same timing helper to
measure a plugin check.

The user's condition for this decision: other developers must be able to add
their own checks easily. If a part of this design makes that difficult, open
the decision again.

### 5.10 Rasters

`seq.read` keeps the raster times of the file. `check_timing` uses the
rasters of `seq.system`, which come from the target. A separate check, the
raster check, compares the rasters that the file declares with the rasters of
the target. In version 1, the raster check passes only when each raster of
the file is equal to the raster of the target (R6). Whether a file with a
different raster plays correctly depends on how the interpreter of the target
resamples the gradient and RF shapes, and the Pulseq specification does not
say. A rule for unequal rasters is a later study, based on the behavior of
specific interpreters (`TODO.md`). The timing check then runs with the
rasters of the target (decision 5).

### 5.11 The target profile format

This section gives the facts and the rules for the format of section 5.2
(decision 6). We do not want a new format if an existing format can do the
work.

Facts from MATLAB Pulseq (commit `c746912`, the commit that pulseq-reports
pins), pypulseq `1.5.0.post1` and the Pulseq file specification
(`doc/specification.tex`):

- **No file format for the system parameters.** MATLAB `mr.opts` gives a
  struct. pypulseq `Opts` is a class. Neither library writes or reads them as
  a file. The two objects also have different fields: MATLAB has `maxB1`,
  `maxFreqOffset`, `rfSamplesLimit` and `flag_trid`, and pypulseq does not.
  The names are different (`maxGrad` and `max_grad`).
- **The `.seq` file has only the rasters.** The specification reserves four
  necessary `[DEFINITIONS]` keys: `GradientRasterTime`,
  `RadiofrequencyRasterTime`, `AdcRasterTime` and `BlockDurationRaster`. It
  also reserves `Name`, `FOV` and `TotalDuration`. Both libraries write the
  rasters and read them again. They do not write the gradient limits, the
  dead times, the ringdown or B0. The specification permits
  "hardware-dependent parameters" in `[DEFINITIONS]`, but it gives no keys
  for them.
- **The Siemens `.asc` file is the only file that both libraries read.**
  MATLAB `mr.Siemens.readasc` and pypulseq `readasc` and `asc_to_hw` read the
  same vendor file. It gives the SAFE PNS parameters, the cardiac model, the
  acoustic resonances, the gradient scale factors and the name of the
  gradient system. pypulseq `asc_to_hw` does not give the values of `Opts`
  (the gradient limits, the rasters, the dead times and B0). Thus the `.asc`
  profile reader of this package reads the GPA limits itself (section 8). The
  file is for Siemens only.
- **The values already have a shared form in memory.** MATLAB
  `calcPNS(hardware)` and pypulseq `calc_pns(hardware)` accept an `.asc` path
  or a hardware struct. The struct is the output of `asc_to_hw` (MATLAB
  refers to `safe_example_hw()` for it): `name`, and for each axis `x`, `y`
  and `z` the fields `tau1` to `tau3`, `a1` to `a3`, `stim_limit`,
  `stim_thresh` and `g_scale`. pypulseq reads the acoustic resonances from
  the `.asc` file into a list of frequency and bandwidth pairs, and
  `calc_grad_spectrum` accepts this list.
- **The PNS parameters are the parameters of one model.** The fields of the
  hardware struct are the parameters of the SAFE model, the model of
  Siemens. GE and Philips use different PNS models, with different
  parameters. The acoustic resonances, the gradient limits, the rasters, the
  dead times and B0 do not depend on a model.

Rules:

- **The file is TOML or JSON.** Python reads both with no new dependency
  (`tomllib`, `json`).
- **The profile file can give each value directly, for each vendor.** An
  `.asc` file is not necessary. The profile file uses the existing forms:
  - the values of `Opts` use the keywords of the constructor `pp.Opts(...)`,
    because this package uses pypulseq. This includes its unit keywords
    (`grad_unit`, `slew_unit`), so a limit can be in mT/m and T/m/s. The
    reader gives the section to `pp.Opts(...)`. The documentation of the
    format gives the `mr.opts` name of each entry. One exception: the
    rasters use the reserved `[DEFINITIONS]` names, so that the raster check
    compares values with the same names. The reader gives them to the
    raster keywords of `pp.Opts(...)`. The `HardwareLimits` of the profile
    (section 5.2) comes from the `Opts` values, in its own units.
  - the PNS parameters use the fields of the SAFE hardware struct, with the
    name of their model.
  - the acoustic resonances are a list of frequency and bandwidth pairs.
- **A Siemens `.asc` file is an optional source.** It can give the SAFE
  parameters, the acoustic resonances and the GPA limits. It is a profile
  reader (section 5.2), not a necessary input.
- **Other vendors.** For a scanner that does not use the SAFE model, the PNS
  check is "not evaluated" until a model plugin for its PNS model exists.
  Then the profile gives the parameters of that model. The other values of
  the profile file are the same for each vendor.
- **The source of each value.** Each result records the source of each value
  that it uses: the profile file or the `.asc` file.
- **A value from two sources is an error.** If the profile file gives a
  value, and it also names an `.asc` file that gives the same value, the
  profile is not valid. A rule that selects one source is not visible to the
  reader of a result.
- **Extension without a new version.** A new vendor or model adds its
  parameters to the profile, and an older version of this package can still
  read the profile. The file has a section for each model, with the name of
  the model (for example the SAFE parameters in a section `safe` under PNS).
  Each model plugin reads only its section. The rules for names that the
  reader does not know:
  - a section that the reader does not know (for example a model that is not
    installed, or data for a different tool) is accepted, and the reader
    ignores it. The result lists the sections that were not used.
  - a key that the reader does not know, inside a section that the reader
    knows (for example `max_slwe` in the `Opts` values), is an error. A
    necessary value that is misspelled gives "not evaluated". But an
    optional limit that is misspelled and ignored can change a fail into a
    pass.
  - the profile file declares the version of its format. A new section does
    not change the version, because an older reader ignores it. A new key in
    a section that exists raises the version. A reader refuses a profile with
    a newer version than its own, with a clear error. Thus a reader never
    ignores a key silently.
- **Later.** Propose `[DEFINITIONS]` keys for the system limits to the Pulseq
  community, together with the convention declaration of decision 10.

## 6. Kinds of checks that we can see now

The design must accept these kinds without a new structure. Version 1 does
only some of them (section 8). Many of them come from one need: to use one
`.seq` file on different scanners, possibly from different vendors.

### 6.1 The kinds

| Kind | Examples | Possible from the `.seq` file only? |
|---|---|---|
| Timing and rasters | The rasters of the gradients, RF, ADC and blocks are different for each vendor (for example, 10 µs gradient raster on Siemens, 4 µs on GE). Dead times and ringdown. The ADC dwell step. | Yes, with a target profile. `check_timing` already takes these values from `Opts`. |
| Gradient hardware | Amplitude and slew. The limit on each axis or on the vector. A `.seq` file has only the logical axes. They are the physical axes only at the orientation of the file (see the next row). A slew limit that decreases at high amplitude. Gradient RMS, duty cycle and heating over a time window. Acoustic resonance bands. | Yes, with a target profile. |
| Worst case under rotation | Does the sequence pass at the planned orientation, or at all orientations? This makes the \|G\| note of the gradient limits card of pulseq-reports into a check. | Yes. |
| Physiological safety | PNS, with more than one model. Cardiac stimulation (`asc_to_hw` has `cardiac_model`). The dB/dt operating mode (normal or first level, IEC 60601-2-33). Acoustic noise. | Yes, with a model. |
| RF and field strength | Peak B1 against the RF amplifier and coil of the target. SAR, which increases approximately with B0². A frequency offset in Hz that is correct at only one B0 (for example, fat saturation). pypulseq 1.5 can give such offsets in ppm. | Partly. A Hz offset needs a declared B0. |
| Interpreter compatibility | The Pulseq file version. The supported extensions (soft delays, rotations, triggers, RF use). Limits on the library size, the number of blocks, the ADC samples and the waveform length. Label and counter ranges. Structural rules of one vendor's interpreter. | Yes, with a target profile. |
| Coordinate and sign conventions | The handedness of the logical axes relative to the patient. Which physical axis each logical axis goes to. The sign of the RF phase and frequency offset relative to the gradient polarity. The direction of a slice or readout offset. | **No. It needs a declaration** (section 6.2). |
| Nucleus | A gamma that is not the proton gamma. Does the RF chain of the target support that nucleus? | Yes, with a target profile. |

### 6.2 Coordinate conventions and handedness

This kind is different from the others. A `.seq` file does not record the
convention that its author used. A gradient polarity and an RF frequency
offset are consistent in each handedness. The only difference is that the
slice is at the mirror position. Thus no check can find "wrong handedness"
from the waveforms only.

Two checks are possible:

1. **Declared against expected.** The sequence declares its conventions: the
   handedness, the axis mapping, and the signs of the phase and the frequency
   offset. The target profile gives what its interpreter expects. The check
   compares the two. With no declaration, the result is "not evaluated". In a
   report for several sites, this is the correct result to show.
2. **Internal consistency against the declaration.** For each slice-selective
   RF pulse, the frequency offset must be γ·G·position, with the declared
   sign. This check finds a sign error inside one sequence, also when all the
   scanners agree.

The correct location for the declaration is the `[DEFINITIONS]` section of
the `.seq` file. That is a convention for the Pulseq community. This library
must not invent it alone.

The location of the declaration is deferred (decision 10). Version 1 has no
convention checks. The item is in `TODO.md`.

## 7. A separate package

### 7.1 Why a separate package

1. **The dependency goes in one direction.** Reports use checks. Checks never
   use reports. A package boundary enforces this. In one package, only
   discipline enforces it, and the problems of section 3 started when the two
   uses were in one package.
2. **Different promises.** Checks are a contract. The check IDs, the
   specifications, the profile format and the model versions must stay
   stable, because CI results and compliance records refer to them. Reports
   are presentation, and must be free to change quickly. Two version numbers
   let each package keep its own promise.
3. **Different people.** Scanner physicists and people who work with vendors
   will write target profiles, profile readers and models. Many of them will
   not open a report. This repository keeps their issues, documents and
   plugin groups separate from the cards.
4. **Upstream.** The Pulseq community can adopt a small pure-Python check
   library more easily than a report generator. Parts of it can move to
   pypulseq, for example a gradient limits check of a finished file, or a
   convention declaration.

This package uses only `pypulseq`, `numpy` and `scipy`, the same as
pulseq-reports. A user of the checks gets a smaller API and fewer documents,
not fewer dependencies.

### 7.2 What moves in from pulseq-reports

The measurement modules that the checks need import nothing from the report
side. Their imports in pulseq-reports:

| Module | Imports in the package |
|---|---|
| `grad_limits` | `seq_index`, `seq_utils` |
| `pns` | `pns_levels`, `seq_index` |
| `pns_levels` | `asc`, `extensions`, `sampling`, `seq_index` |
| `sampling` | `seq_index`, `seq_utils` |
| `asc`, `extensions`, `seq_index`, `seq_utils` | none |
| `grad_spectrum` | `sampling`, `seq_index` |
| `rf_exposure` | none |

For version 1, these modules move to this package, with their tests:
`grad_limits`, `pns`, `pns_levels`, `asc`, `extensions`, `sampling`,
`seq_index` and `seq_utils`. `grad_spectrum` and `rf_exposure` move when a
check needs them (the acoustic check and the RF checks).

These do not move: the cards, the page, the JavaScript, `waveforms`,
`markup`, `rf_profiles`, `rf_sim`, `profile_metrics`, `diagram_data`, the
registry of cards and the `pulseq-report` command.

Two moved modules have defaults that section 3 (problem 3) does not permit
for a check: `asc` has `EXAMPLE_HARDWARE`, and `gradient_limits` uses
`seq.system` when it gets no limits. A report can use these defaults (section
2). The check layer never uses them.

pulseq-reports will depend on this package by git URL and tag. Thus this
repository makes tagged releases.

### 7.3 Costs

- This repository has its own CI, releases and token. The dev-workflow setup
  is done (#1).
- From step 2.2 to step 3 (section 9), both repositories have copies of the
  moved modules. A change to a moved module happens in this repository
  first. pulseq-reports changes its copy only for a bug fix, and the same fix
  comes to this repository. Step 3 then removes the copy in pulseq-reports,
  with no differences to merge.
- A change that touches both packages needs two pull requests, in sequence.
  First `pulseq-checks` makes a tag, then `pulseq-reports` changes its pin.
  There will be more of these changes at the start, while the measurement
  code changes for the checks.
- Each package has its own command line. Both read the same check
  configuration file through one function of this package (section 5.7).

## 8. Version 1

Version 1 of this package is small:

- one target profile format (TOML or JSON, section 5.11), and a Siemens
  `.asc` profile reader that gives the SAFE parameters, the acoustic
  resonances and the GPA limits,
- a list of targets for each check run,
- the cost classes and the time budget of the fast checks (section 5.9),
- the raster check (section 5.10),
- the timing check (a wrapper of `check_timing`),
- the gradient amplitude check and the gradient slew check of each logical
  axis, for a finished file,
- the worst-case amplitude under rotation: the peak of \|G\| against the
  amplitude limit. It replaces `check_norms` of pulseq-reports (decision 11).
- the PNS check with the SAFE model of pypulseq, only with real SAFE
  parameters: from a Siemens `.asc` file, or in the profile file (decision 6),
- the result matrix, the JSON output and the `pulseq-check` command.

The check summary card and its `--fail-on-check` flag are in pulseq-reports,
not in this package. The card uses the interface of section 5.5.

The worst-case slew under rotation needs a vector slew measurement. The
library does not have one yet, so that check comes later. The convention
checks come later (decision 10). The other kinds of section 6 come later.
The structure of section 5 accepts them without a new design.

## 9. Order of work

The source gives four steps. Steps 1 and 3 are in pulseq-reports. This
repository has step 2 and a part of step 4.

1. **Step 1 of the source (in pulseq-reports).** pulseq-reports removes
   `Card.checks`, the `check_norms` option and the exit status 2 before
   `0.2.0` final (decision 1). `HardwareLimits` stays in pulseq-reports until
   step 3. Step 1 waits for step 2.4, because step 2.4 compares the new
   checks with the card checks that step 1 removes.
2. **Make `pulseq-checks`.**
   1. The dev-workflow setup. Done (#1).
   2. Move the measurement modules of section 7.2 with their tests, from
      pulseq-reports `main`. Done (#10).
   3. Add the target profile, the profile reader, the check rules, the
      results and `pulseq-check`. Done (#11 to #15, #17).
   4. Compare the results of the new timing, gradient and PNS checks with the
      current checks of the cards of pulseq-reports, before step 1 removes
      them. Done (#16, `docs/comparison.md`).
   5. Make a tag that pulseq-reports can pin. `v0.1.0rc1`.
3. **Step 3 of the source (in pulseq-reports).** pulseq-reports uses this
   package, removes its copies of the moved modules, exports `HardwareLimits`
   again, and adds the check summary card and `--fail-on-check`. It needs the
   tag of step 2.5.
4. **Later.** More kinds of checks (section 6), more profile readers, JUnit
   output, and proposals to pypulseq.

Step 2 is a move, with no stage inside pulseq-reports. Thus the check layer
is not built two times.

## 10. Rules for the implementation plan

- The rules of `CLAUDE.md` apply: one branch and one pull request for each
  change, and the checks before each pull request.
- Do not add a dependency. If RF or SAR checks need one (for example
  PySar4seq), stop and ask the user.
- Do not test a rule that pypulseq already tests (rely on pypulseq).
- A proposal to pypulseq or to MATLAB Pulseq stands alone. It does not name
  `pulseq-reports` or `pulseq-checks`.

## 11. Decisions

The user made these decisions on 2026-09-30. Do not open them again. The
numbers are the same as in the source. Decisions 1 and 2 are decisions for
pulseq-reports: remove `Card.checks` and the exit status 2 before `0.2.0`
final, and give `pulseq-report` an opt-in `--fail-on-check` flag.

| # | Decision | Answer | Where |
|---|---|---|---|
| 3 | The exit status of "not evaluated" | Status 1 only for a required check (a check that the caller names by ID, for each target or for the targets that the configuration names). A check that is not required and is not evaluated does not change the status. | 5.6 |
| 4 | The limits of the sequence (`seq.system`) | Only with an explicit opt-in: a keyword argument of the Python function, only when the caller gives a `Sequence` object. No `pulseq-check` flag, no profile entry. The result records the source of the limits. | 5.6 |
| 5 | The rasters of the file and of the target | A separate raster check. In version 1 the rasters must be equal (R6). The timing check uses the rasters of the target. | 5.10 |
| 6 | The target profile format | A TOML or JSON file that can name a Siemens `.asc` file. A value in both files is an error. The profile file can also give the model parameters (for example SAFE) and the acoustic resonances directly, in a section for each model. An unknown section is ignored and listed. An unknown key in a known section is an error. A new key in a known section raises the format version, and a reader refuses a newer version. | 5.2, 5.11 |
| 7 | The speed budget | Cost classes (`fast`, `slow`) and a tested budget for the fast checks of the library. The user's condition: other developers must be able to add their own checks easily. The cost class is one field, with the default `slow`. | 5.9 |
| 8 | `HardwareLimits` | It moves to `pulseq-checks`, and a target profile contains it. `pulseq-reports` exports it again. | 5.2, 9 |
| 9 | The command-line code | Each package has its own. `pulseq-checks` has a public function that reads a check configuration, and `pulseq-reports` uses it. | 5.7 |
| 10 | The location of the convention declaration | Deferred. It is in `TODO.md`. Version 1 has no convention checks. | 6.2 |
| 11 | The worst case under rotation | Worst-case amplitude (the peak of \|G\|) in version 1. Worst-case slew later, after a vector slew measurement. | 8 |
| 12 | The name and the repository | `mdtisdall/pulseq-checks`: public, MIT, with the same dev-workflow as `pulseq-reports` (#1, #2). | 9 |

Two answers in this document go further than the source:

- **Decision 4.** The source permits the opt-in with a flag or a profile
  entry, for each sequence. Here, the opt-in is only a keyword argument of
  the Python function, for a `Sequence` object, because a `.seq` file does
  not contain the limits of its author (section 5.11).
- **Decision 6.** The source takes the SAFE parameters and the acoustic
  resonances only from an `.asc` file, and runs the PNS check only with a
  real `.asc` file. Here, the profile file can also give them, so that a site
  with no `.asc` file and other vendors can use the same format (section
  5.11).

### Decisions from the review of the design

The user made these decisions on 2026-09-30, in a review of this document.
They are for this repository. Do not open them again.

| # | Decision | Answer | Where |
|---|---|---|---|
| R1 | A check that cannot run | A fourth state, "error". It gives exit status 1, also for a check that is not required. | 5.3, 5.6 |
| R2 | A missing input | A missing profile field gives "not evaluated". A missing or invalid profile, or a run with no target, is an error of the run. | 2, 5.3 |
| R3 | Statuses 1 and 2 together | Status 1. The output lists each failure. | 5.6 |
| R4 | Selection by cost class | It does not make a check required. | 5.6 |
| R5 | The GPA limits in the `.asc` file | The version 1 `.asc` profile reader reads them. | 5.11, 8 |
| R6 | The direction of the raster rule | Version 1 has no rule for unequal rasters: the rasters of the file must equal the rasters of the target. A rule for unequal rasters must come from the behavior of specific interpreters, not from the Pulseq specification alone (decided 2026-09-30, in phase 5 of the plan). | 5.10 |
| R7 | The order of step 2.4 and step 1 | Step 2.4 comes before step 1 in pulseq-reports. Until step 3, a moved module changes here first; pulseq-reports changes its copy only for a bug fix, which also comes here. | 7.3, 9 |

Decision R7 changes the order of work of pulseq-reports. The pulseq-reports
design must record that its step 1 waits for step 2.4 of this repository.

## 12. Terms

- **Check.** A rule that compares a measured quantity with a limit and gives
  pass, fail, not evaluated or error.
- **Check rule.** The code of one check. It has an ID and a specification.
- **Measurement.** A calculation that gives values and their locations, and
  no verdict.
- **Model.** A measurement of a physical quantity that needs the parameters
  of the target, for example a PNS model. Models are in the measurement layer
  (section 5.1).
- **Target** or **target profile.** One scanner and its Pulseq interpreter:
  their limits, their rasters, their models and their conventions.
- **Profile reader.** Code that makes a target profile from vendor files.
- **Result matrix.** The results of all checks for all targets of one
  sequence.
- **Report.** An HTML page that pulseq-reports makes to describe a sequence.
  It can include a summary of a result matrix.
