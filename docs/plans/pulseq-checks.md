# Design: pulseq-checks

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: design. This is not an implementation plan. It gives the concepts, the
structure and the decisions that are still open (section 11). An
implementation plan follows after the user answers the open decisions.

Source: this document is the part of the pulseq-reports design
[`docs/plans/pulseq-checks.md`](https://github.com/mdtisdall/pulseq-reports/blob/51d95900637c0e5e74c7335f57db6659135dc4f4/docs/plans/pulseq-checks.md)
(pulseq-reports #102, commit `51d9590`, written on 2026-09-30) that applies to
this repository. The work in pulseq-reports is not in this document: the
removal of `Card.checks`, `check_norms` and the exit status 2 before `0.2.0`
final, the check summary card, the exit status of `pulseq-report`, and the
removal of the moved modules from pulseq-reports. The section numbers are the
same as in the source, so that the two documents can refer to each other.
In this document, "pulseq-reports" means that repository, and a path such as
`src/pulseq_reports/...` is a path in it.

## 1. Goal

`pulseq-checks` is a pure-Python library that **checks** a Pulseq sequence. A
check compares a sequence with a specification, for example the hardware
limits of one scanner, and gives pass or fail. CI uses checks. A check must be
fast, its result must be binary, and its specification must be clear to a
person who reads it.

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
| Output | Pass, fail or not evaluated, for each named rule. A machine can read it. | An HTML page that describes the sequence. It needs no verdict. |
| Cost | Fast. It calculates only what its rules need. | It can be slow and complete. |
| Defaults | No default limits. A missing input is an error. | Sensible defaults are permitted. |
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
| Measurements | `pulseq-checks` | Calculations only: the gradient peaks and slew, PNS, and later the spectrum and RF exposure. Each measurement gives values and where they occur. It gives no verdict. |
| Checks | `pulseq-checks` | Target profiles, models, check rules, results and the `pulseq-check` command. |
| Reports | `pulseq-reports` | Cards, the page, the JavaScript and the `pulseq-report` command. A card describes. A card does not decide. |

`pulseq-reports` uses `pulseq-checks`. `pulseq-checks` never uses
`pulseq-reports`. The package boundary enforces this direction.

### 5.2 The parts of a check

Four parts change independently. Each part is a plugin point.

| Part | What it is | Examples |
|---|---|---|
| Target profile | What one scanner and its Pulseq interpreter can do, and what they expect | Rasters, dead times, gradient limits, B0, the coil `.asc` file, the supported file versions and extensions, coordinate conventions |
| Profile reader | Makes a target profile from vendor files | A Siemens `.asc` reader now. GE and Philips readers later. |
| Model | Calculates a physical quantity from a sequence and a target | SAFE PNS (pypulseq), a dB/dt model, a neurodynamic body model, a SAR model |
| Check rule | Compares a quantity with a limit. It has a written specification. | "The PNS is below 100 %." "The slew of each physical axis is at or below the limit." |

A new PNS model is a new model plugin. The PNS check rule does not change.
The target profile tells which model applies to that scanner.

Each check rule declares the profile fields and the models that it needs.

The target profile replaces `HardwareLimits` of pulseq-reports (decision 8).
A report can use a target profile as context, for example to show a limit as
a line on a chart. Thus the target profile is a public type of this package.

### 5.3 Results

Each result has:

- the check ID and the version of its specification,
- the target,
- the state: pass, fail or not evaluated,
- the measured value, the limit and where the value occurs (block and time),
- the model and its version, when the check uses a model,
- the reason, when the state is "not evaluated".

"Not evaluated" is a state of its own. It is not a pass and not a fail. A
check gets it when the target profile does not have a necessary field, or
when a necessary model is not available. Examples:

- PNS with no `.asc` file: not evaluated. The pypulseq example hardware is
  not a real scanner, so it does not give a pass.
- Handedness with no declared convention: not evaluated (section 6.2).

A check run takes one sequence and a list of targets. The result is a matrix
of checks and targets. The same matrix is the output for CI and the summary
in a report.

### 5.4 The specification of each check

Each check has a stable ID, for example `gradient.slew.axis`. A document in
this repository gives one entry for each ID:

- the quantity and its exact definition,
- the inputs from the target profile,
- the limit and the tolerance,
- the pass condition,
- the cost (fast, or slow for a large file),
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
  evaluated" result: the reason. The reader of a report must see what was not
  asserted, not only what passed.
- **Locations that a card can use.** A card can point to a result, for
  example the "Show" button of the gradient limits card on the value that
  failed. Thus the location (block and time) uses the same block index as the
  measurements.
- **No default limits.** With no target profile, no checks run. This package
  does not supply default limits to a report.

### 5.6 The `pulseq-check` command and its exit status

| Status | Meaning |
|---|---|
| 0 | Each check passed. |
| 2 | At least one check failed. |
| 1 | An error in the arguments or the profiles, or a check that was not evaluated. |

Decision 3 in section 11 asks if "not evaluated" gives 1, or a status of its
own. The command writes a result that a machine can read (JSON, and maybe
JUnit XML for CI dashboards) and a short summary for a person.

To stop CI on a failed check is the work of `pulseq-check`, not of
`pulseq-report`.

### 5.7 Plugins

`pulseq-checks` has three entry-point groups: profile readers, models and
check rules. A project can add a check for its site without a card.
(`pulseq-reports` keeps its entry-point group for cards.)

The configuration file and option code of the command line of pulseq-reports
(`options.py`, and the configuration reader in `cli.py`) is written for cards
now. Decision 9 asks if the shared part comes to this package.

### 5.8 Rely on pypulseq

A check uses the pypulseq rule when pypulseq has one. The timing check calls
`check_timing`. The PNS check calls the SAFE model of pypulseq. The gradient
limits check uses the slew definition of pypulseq (pulseq-reports
[`docs/notes/slew-definitions.md`](https://github.com/mdtisdall/pulseq-reports/blob/51d95900637c0e5e74c7335f57db6659135dc4f4/docs/notes/slew-definitions.md)).
`pulseq-checks` does not copy a rule that pypulseq has.

## 6. Kinds of checks that we can see now

The design must accept these kinds without a new structure. Version 1 does
only some of them (section 8). Many of them come from one need: to use one
`.seq` file on different scanners, possibly from different vendors.

### 6.1 The kinds

| Kind | Examples | Possible from the `.seq` file only? |
|---|---|---|
| Timing and rasters | The rasters of the gradients, RF, ADC and blocks are different for each vendor (for example, 10 µs gradient raster on Siemens, 4 µs on GE). Dead times and ringdown. The ADC dwell step. | Yes, with a target profile. `check_timing` already takes these values from `Opts`. |
| Gradient hardware | Amplitude and slew. The limit on each physical axis or on the vector. A slew limit that decreases at high amplitude. Gradient RMS, duty cycle and heating over a time window. Acoustic resonance bands. | Yes, with a target profile. |
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
must not invent it alone. Until a convention exists, the declaration can be in
the check configuration file, next to the targets (decision 10).

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

pulseq-reports will depend on this package by git URL and tag. Thus this
repository makes tagged releases.

### 7.3 Costs

- This repository has its own CI, releases and token. The dev-workflow setup
  is done (#1).
- A change that touches both packages needs two pull requests, in sequence.
  First `pulseq-checks` makes a tag, then `pulseq-reports` changes its pin.
  There will be more of these changes at the start, while the measurement
  code changes for the checks.
- The option and configuration code of the command line (section 5.7).

## 8. Version 1

Version 1 of this package is small:

- one target profile format, and a Siemens `.asc` profile reader,
- a list of targets for each check run,
- the timing check (a wrapper of `check_timing`),
- the gradient amplitude check and the gradient slew check of each axis, for
  a finished file. The \|G\| amplitude check is optional (it replaces
  `check_norms` of pulseq-reports).
- the PNS check with the SAFE model of pypulseq, only with a real `.asc` file,
- the result matrix, the JSON output and the `pulseq-check` command.

The check summary card is in pulseq-reports, not in this package. It uses the
interface of section 5.5.

The other kinds of section 6 come later. The structure of section 5 accepts
them without a new design.

## 9. Order of work

The source gives four steps. Steps 1 and 3 are in pulseq-reports. This
repository has step 2 and a part of step 4.

1. **Step 1 of the source (in pulseq-reports).** pulseq-reports removes
   `Card.checks`, the `check_norms` option and the exit status 2 before
   `0.2.0` final. This repository does not wait for it.
2. **Make `pulseq-checks`.**
   1. The dev-workflow setup. Done (#1).
   2. Move the measurement modules of section 7.2 with their tests, from
      pulseq-reports `main`.
   3. Add the target profile, the profile reader, the check rules, the
      results and `pulseq-check`.
   4. Compare the results of the new timing, gradient and PNS checks with the
      current checks of the cards of pulseq-reports.
   5. Make a tag that pulseq-reports can pin.
3. **Step 3 of the source (in pulseq-reports).** pulseq-reports uses this
   package, removes its copies of the moved modules and adds the check summary
   card. It needs the tag of step 2.5.
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

## 11. Decisions still open

The numbers are the same as in the source. Decisions 1 and 2 (the timing of
the removal before `0.2.0`, and the exit status of `pulseq-report`) are
decisions for pulseq-reports. They are not in this document.

3. **The exit status of "not evaluated".** Is it 1, like an error, or a
   status of its own? Can a caller mark a check as "may be not evaluated"?
4. **Limits from the sequence.** Can a check use the `seq.system` limits of
   the file? Recommended: only with an explicit opt-in, and the result records
   the source of the limits.
5. **Rasters.** `seq.read` keeps the raster times of the file.
   `check_timing` uses the rasters of `seq.system`. Must a separate check
   compare the rasters of the file with the rasters of the target?
6. **The target profile format.** TOML, or another format? How much comes
   from the Siemens `.asc` file (the GPA limits, the SAFE parameters, the
   acoustic resonances), and how much from the profile file? Is a site
   profile a file in the repository of the sequence?
7. **The speed budget.** For example: "the version 1 checks of a file with
   10⁶ blocks take less than N seconds". PNS can be slow for a large file.
   Does each check have a cost class, and can the caller select checks?
8. **`HardwareLimits`.** It is public in pulseq-reports `0.2.0`. Does it move
   to `pulseq-checks` and `pulseq-reports` export it again? Or does the target
   profile replace it?
9. **The shared command-line code.** Does the option and configuration code
   move to `pulseq-checks`, or does each package have its own?
10. **The convention declaration.** Where does it go until the Pulseq
    community has a convention? Do we propose a `[DEFINITIONS]` key to
    pypulseq and MATLAB Pulseq?
11. **The worst case under rotation.** Version 1 or later?
12. **The name and the repository.** Answered: `mdtisdall/pulseq-checks`,
    public, with the same dev-workflow as `pulseq-reports` (#1). The MIT
    license is in #2.

## 12. Terms

- **Check.** A rule that compares a measured quantity with a limit and gives
  pass, fail or not evaluated.
- **Check rule.** The code of one check. It has an ID and a specification.
- **Measurement.** A calculation that gives values and their locations, and
  no verdict.
- **Model.** A measurement of a physical quantity that depends on the target,
  for example a PNS model.
- **Target** or **target profile.** One scanner and its Pulseq interpreter:
  their limits, their rasters, their models and their conventions.
- **Profile reader.** Code that makes a target profile from vendor files.
- **Result matrix.** The results of all checks for all targets of one
  sequence.
- **Report.** An HTML page that pulseq-reports makes to describe a sequence.
  It can include a summary of a result matrix.
