# Using pulseq-checks

This document is the reference for a user of `pulseq-checks`. The
specification of each check (its quantity, limit, tolerance and pass
condition) is in [`checks.md`](checks.md). This document does not copy it.

Contents:

1. [What the package checks](#1-what-the-package-checks)
2. [The target profile](#2-the-target-profile)
3. [The check configuration](#3-the-check-configuration)
4. [The command `pulseq-check`](#4-the-command-pulseq-check)
5. [The Python API](#5-the-python-api)
6. [The result JSON](#6-the-result-json)
7. [Writing a plugin](#7-writing-a-plugin)
8. [Limits of version 1](#8-limits-of-version-1)

## 1. What the package checks

A check compares a Pulseq sequence with a specification, for example the
hardware limits of one scanner, and gives a result. You give one `.seq` file
and one or more target profiles. You get one result for each check and each
target.

The checks of version 1:

| ID | What it needs from the target profile |
|---|---|
| `timing.rasters` | the four `[rasters]` values |
| `timing.pypulseq` | the four `[rasters]` values, and `opts.rf_dead_time`, `opts.rf_ringdown_time` and `opts.adc_dead_time` |
| `gradient.amplitude.axis` | `opts.max_grad`, and `rasters.GradientRasterTime` and `rasters.BlockDurationRaster` (when the file does not declare them) |
| `gradient.slew.axis` | `opts.max_slew`, or `opts.max_grad` and `opts.rise_time`, and `rasters.GradientRasterTime` and `rasters.BlockDurationRaster` (when the file does not declare them) |
| `gradient.amplitude.any-orientation` | `opts.max_grad`, and `rasters.GradientRasterTime` and `rasters.BlockDurationRaster` (when the file does not declare them) |
| `pns.safe` | the SAFE parameters, `[models.pns.safe]` (from the profile file or from an `.asc` file), and `rasters.GradientRasterTime` and `rasters.BlockDurationRaster` (when the file does not declare them) |

The quantity, the limit, the tolerance, the pass condition and the cost class
of each check are in [`checks.md`](checks.md). Each result links to its
heading there.

### The four states

| State | Meaning |
|---|---|
| pass | The check ran, and the sequence meets the limit. |
| fail | The check ran, and the sequence does not meet the limit. |
| not evaluated | The check did not run, because the target profile does not give a value or a model that the check needs, or because the file does not declare a raster that the check uses and the target does not give it. It is not a pass and not a fail. |
| error | The check cannot run on this sequence: an exception in the check, or an input that the measurement refuses (for example a file with the rotation extension). It is not a fail. |

Each result has the check ID and the version of its specification, the
target, the state, the value, the limit and its unit, where the value occurs
(the block ID and the time in seconds), the model and its version (when the
check uses a model), and the reason. The reason says why a result is "not
evaluated" or "error". For a pass or a fail it can give a short detail of the
value, for example the axis (`axis y`) or the raster that gave it.

### Findings

A result can also have findings: one finding for each problem that the check
found, not only the worst value. Each finding has a code (the kind of
problem), a message for a person, a location (the block ID and the time in
seconds) and data (the values of the problem, by name). `timing.pypulseq`
gives one finding for each error of `check_timing` of pypulseq, and
`timing.rasters` gives one finding for each raster that differs from the
target or that the file does not declare correctly. The three gradient checks
(`gradient.amplitude.axis`, `gradient.slew.axis` and
`gradient.amplitude.any-orientation`) give one finding for each block, and
axis, that is above the limit. `pns.safe` gives one finding for each interval
of samples where the SAFE total is at or above 100 %. A plugin check
can give its own ([section 7](#a-check-rule)). The specification of a check in
[`checks.md`](checks.md) says what its findings are.

The findings do not change the state of a result or the exit status. The
summary of the command gives only the number of findings of each result. The
JSON result has all of them. To pass them to another tool, see
[Passing the findings to another tool](#passing-the-findings-to-another-tool).

### No default limits

There are no default limits. A value that the profile does not give is not
replaced by a default. The check that needs it gives "not evaluated". For
example, `pns.safe` with no SAFE parameters is "not evaluated": the example
hardware of pypulseq is not a real scanner, so it never gives a pass.

The same rule holds for the rasters. A `.seq` file declares its rasters in
`[DEFINITIONS]` (`GradientRasterTime`, `RadiofrequencyRasterTime`,
`AdcRasterTime` and `BlockDurationRaster`). A file of format 1.4.0 or newer
can leave one out, and a file of an older format does not have them. For a
raster that the file does not declare, the check uses the raster of the
target (`[rasters]`), as the interpreter of the target does. When the target
does not give it either, pypulseq would use its own default (for example 10 µs
for `GradientRasterTime`). A check that uses that raster gives "not
evaluated" and says which raster is missing. The check does not use the
default. `CheckSpec.rasters` lists the rasters that a check uses
([section 7](#a-check-rule)).

A missing or invalid profile, a missing or invalid check configuration, or a
run with no target is an error of the run. It is not a result of a check (see
[the exit status](#exit-status)).

## 2. The target profile

A target profile describes one scanner and its Pulseq interpreter. It is a
TOML or a JSON file. The suffix (`.toml` or `.json`) selects the reader. The
two forms have the same structure. `read_profile` reads the file.

### 2.1 The keys of the top level

| Key | Type | Meaning |
|---|---|---|
| `format` | integer | Necessary. The version of the profile format. This version of the package reads `1`. A larger number is an error. |
| `name` | string | Necessary, not empty. The name of the target in the results. Two targets of one run must have different names. |
| `vendor` | string | Optional. Kept in `TargetProfile.vendor`. No check of version 1 uses it. |
| `asc` | string | Optional. The path of a Siemens `.asc` file, relative to the directory of the profile file (see [2.6](#26-the-asc-file)). |
| `asc_gradient_mode` | string | Optional. The operation mode of the GPA limits that the `.asc` file gives. It needs `asc`. |

The sections are `opts`, `rasters`, `models` and `acoustic`.

### 2.2 `[opts]`

The keywords of `pp.Opts(...)` of pypulseq, except the four raster keywords
(they are in `[rasters]`). The reader gives the section to `pp.Opts(...)`.

| Key | Unit | `mr.opts` name in MATLAB Pulseq |
|---|---|---|
| `max_grad` | `grad_unit` (default `Hz/m`) | `maxGrad` |
| `grad_unit` | `Hz/m`, `mT/m` or `rad/ms/mm` | `gradUnit` |
| `max_slew` | `slew_unit` (default `Hz/m/s`) | `maxSlew` |
| `slew_unit` | `Hz/m/s`, `mT/m/ms`, `T/m/s` or `rad/ms/mm/ms` | `slewUnit` |
| `rise_time` | s | `riseTime` |
| `rf_dead_time` | s | `rfDeadTime` |
| `rf_ringdown_time` | s | `rfRingdownTime` |
| `adc_dead_time` | s | `adcDeadTime` |
| `adc_samples_limit` | samples | `adcSamplesLimit` |
| `adc_samples_divisor` | samples | `adcSamplesDivisor` |
| `B0` | T | `B0` |
| `gamma` | Hz/T | `gamma` |

Notes:

- A key that is not in this table is an error. A raster keyword
  (`grad_raster_time`, `rf_raster_time`, `adc_raster_time` or
  `block_duration_raster`) is an error that names the reserved name to use in
  `[rasters]`.
- A check uses a value only when the profile gives it. A key that the profile
  does not give has the default of pypulseq inside the `Opts` object that
  reads the sequence, but no check uses such a value: the check gives "not
  evaluated". The one use of a default is `gamma` (pypulseq: 42.576 MHz/T) when
  the profile does not give it: for the units of the limits, for the units of
  the gradient values, and for the SAFE model.
- `rise_time` with `max_grad` gives the slew limit: pypulseq calculates
  `max_slew` as `max_grad / rise_time`. The checks then use this value as
  `opts.max_slew` (`TargetProfile.has_value("opts.max_slew")` is true), but
  `sources` has no entry for `opts.max_slew`. `rise_time` without `max_grad`
  does not give a slew limit, because pypulseq would divide its default
  `max_grad`.
- A profile that gives both `max_slew` and `rise_time` (from the profile file
  or from the `.asc` file) is an error, because pypulseq replaces `max_slew`
  with `max_grad / rise_time` without a message.
- The limits of the gradient checks are in mT/m and T/m/s, whatever unit the
  profile uses. `TargetProfile.hardware_limits` has them when the profile
  gives both `max_grad` and the slew limit (`max_slew`, or `rise_time`).
- In JSON, a `null` value is an error.

### 2.3 `[rasters]`

The four reserved `[DEFINITIONS]` names of the Pulseq file specification, each
a positive number in seconds:

| Key | `pp.Opts` keyword |
|---|---|
| `GradientRasterTime` | `grad_raster_time` |
| `RadiofrequencyRasterTime` | `rf_raster_time` |
| `AdcRasterTime` | `adc_raster_time` |
| `BlockDurationRaster` | `block_duration_raster` |

The reader gives them to the keywords of `pp.Opts(...)`. The raster check
compares the values with the same names in the `.seq` file.

There is no `rule` key. Version 1 needs equal rasters
([section 8](#8-limits-of-version-1)). The key `rasters.rule` is an error.

### 2.4 `[models.pns.safe]`

The parameters of the SAFE PNS model of Siemens, in the form of the hardware
struct of pypulseq (`safe_example_hw`, `asc_to_hw`):

- `name`: optional, a string.
- `x`, `y` and `z`: tables, each with exactly nine fields: `tau1`, `tau2`,
  `tau3`, `a1`, `a2`, `a3`, `stim_limit`, `stim_thresh` and `g_scale`. Each is
  a finite number.

A missing field, an unknown field and a value of a wrong type are an error
that names the key. A section under `models` that no installed model reads is
not an error (see [2.7](#27-the-rules)).

### 2.5 `[acoustic]`

`resonances`: a list of `[frequency, bandwidth]` pairs of the acoustic
resonances of the gradient system, in Hz. No check of version 1 uses it. It is
in `TargetProfile.acoustic_resonances`.

### 2.6 The `.asc` file

The key `asc` names a Siemens gradient system file (`MP_GPA_*.asc`, or
`MP_GradSys_*.asc` on newer software). The path is relative to the directory
of the profile file. The reader follows the `$INCLUDE` lines of the file (the
included files are in the same directory).

The `.asc` file fills only parts of the profile. It is never a complete
target, because it does not give the rasters, the dead times or B0. It gives:

| Value | From the `.asc` file |
|---|---|
| `models.pns.safe` | The SAFE parameters, with the name of the component (`asCOMP`). The file must also give the three gradient scale factors (`asGPAParameters[0].sGCParameters.flGScaleFactorX`, `Y` and `Z`). |
| `acoustic.resonances` | The resonance frequencies and bandwidths, in the two layouts that pypulseq reads. |
| `opts.max_grad`, `opts.grad_unit`, `opts.max_slew`, `opts.slew_unit` | The GPA limits of the operation mode in `asc_gradient_mode`. |

The GPA limits:

- `asc_gradient_mode` is one of `absolute`, `normal`, `fast`, `ultrafast`,
  `whisper` or `boost`. (`nominal` is not a mode for the limits: the file
  gives it no rise time.) There is no default mode.
- `max_grad` is `asGPAParameters[0].flGradMaxAmpl<Mode>` in mT/m
  (`grad_unit = "mT/m"`).
- `max_slew` is `1000 / asGPAParameters[0].flGradMinRiseTime<Mode>` in T/m/s
  (`slew_unit = "T/m/s"`). The rise time is in µs per mT/m.
- Without `asc_gradient_mode`, the `.asc` file gives no gradient limits. The
  profile file can give them in `[opts]`.
- `asc_gradient_mode` without `asc`, an unknown mode, and a mode that the file
  does not have are errors.

A value that the `.asc` file does not have is not given. That is not an error:
the profile file can give it. A value that both files give is an error (see
[2.7](#27-the-rules)). Thus a profile that selects a mode does not give
`max_grad`, `max_slew`, `grad_unit` or `slew_unit`, nor `rise_time` (see
[2.2](#22-opts)), and a profile with an `.asc` file that has SAFE parameters
does not give `[models.pns.safe]`.

The source of each value is recorded. For a GPA limit it is the file name
with the mode, for example `MP_GPA_K2309_2250V_951A_AS82.asc (fast)`.

### 2.7 The rules

1. The suffix must be `.toml` or `.json`.
2. `format` is necessary. A profile with a format that is newer than the
   reader is an error that names both versions.
3. A section that the reader does not know is accepted and ignored. This is a
   table at the top level (for example `[notes]`), and a table under `models`
   that no installed model reads (for example `[models.ge.pns]`, when no model
   `ge.pns` is installed). The reader lists it in `unused_sections`: the
   results and the summary show it.
4. A key that the reader does not know, in a section that it knows, is an
   error that names the key and the section. A key of the top level that is not
   a table and that the reader does not know is also an error. (A
   misspelled optional limit, ignored, could change a fail into a pass.)
5. A value that the profile file and the `.asc` file both give is an error
   that names the value and both sources.
6. The reader supplies no default for a value that the file does not give.
7. A new section does not raise `format`, because an older reader ignores it.
   A new key in a section that exists does.

### 2.8 Examples

The SAFE numbers in these examples are the parameters of the example hardware
of pypulseq. They are not a real scanner. The limits are those of an example
target, not of a real one.

A complete profile in TOML, with no `.asc` file:

```toml
format = 1
name = "Prisma AS82"
vendor = "siemens"

[opts]
max_grad = 80
grad_unit = "mT/m"
max_slew = 200
slew_unit = "T/m/s"
rf_dead_time = 100e-6
rf_ringdown_time = 30e-6
adc_dead_time = 10e-6
B0 = 2.89

[rasters]
GradientRasterTime = 10e-6
RadiofrequencyRasterTime = 1e-6
AdcRasterTime = 100e-9
BlockDurationRaster = 10e-6

# The SAFE parameters of the example hardware of pypulseq, not of a real scanner.
[models.pns.safe]
name = "pypulseq example hardware (not a real scanner)"

[models.pns.safe.x]
tau1 = 0.2
tau2 = 0.03
tau3 = 3.0
a1 = 0.4
a2 = 0.1
a3 = 0.5
stim_limit = 30.0
stim_thresh = 24.0
g_scale = 0.35

[models.pns.safe.y]
tau1 = 1.5
tau2 = 2.5
tau3 = 0.15
a1 = 0.55
a2 = 0.15
a3 = 0.3
stim_limit = 15.0
stim_thresh = 12.0
g_scale = 0.31

[models.pns.safe.z]
tau1 = 2.0
tau2 = 0.12
tau3 = 1.0
a1 = 0.42
a2 = 0.4
a3 = 0.18
stim_limit = 25.0
stim_thresh = 20.0
g_scale = 0.25

[acoustic]
resonances = [[590, 100], [1140, 220]]
```

The same profile in JSON:

```json
{
  "format": 1,
  "name": "Prisma AS82",
  "vendor": "siemens",
  "opts": {
    "max_grad": 80,
    "grad_unit": "mT/m",
    "max_slew": 200,
    "slew_unit": "T/m/s",
    "rf_dead_time": 1e-4,
    "rf_ringdown_time": 3e-5,
    "adc_dead_time": 1e-5,
    "B0": 2.89
  },
  "rasters": {
    "GradientRasterTime": 1e-5,
    "RadiofrequencyRasterTime": 1e-6,
    "AdcRasterTime": 1e-7,
    "BlockDurationRaster": 1e-5
  },
  "models": {
    "pns": {
      "safe": {
        "name": "pypulseq example hardware (not a real scanner)",
        "x": {"tau1": 0.2, "tau2": 0.03, "tau3": 3.0, "a1": 0.4, "a2": 0.1,
              "a3": 0.5, "stim_limit": 30.0, "stim_thresh": 24.0,
              "g_scale": 0.35},
        "y": {"tau1": 1.5, "tau2": 2.5, "tau3": 0.15, "a1": 0.55, "a2": 0.15,
              "a3": 0.3, "stim_limit": 15.0, "stim_thresh": 12.0,
              "g_scale": 0.31},
        "z": {"tau1": 2.0, "tau2": 0.12, "tau3": 1.0, "a1": 0.42, "a2": 0.4,
              "a3": 0.18, "stim_limit": 25.0, "stim_thresh": 20.0,
              "g_scale": 0.25}
      }
    }
  },
  "acoustic": {"resonances": [[590, 100], [1140, 220]]}
}
```

A profile with an `.asc` file. The file gives the SAFE parameters, the
acoustic resonances and the gradient limits of the mode `fast`. The profile
file gives the rest:

```toml
format = 1
name = "Prisma AS82 (asc)"
vendor = "siemens"
asc = "MP_GPA_K2309_2250V_951A_AS82.asc"
asc_gradient_mode = "fast"

[opts]
rf_dead_time = 100e-6
rf_ringdown_time = 30e-6
adc_dead_time = 10e-6
B0 = 2.89

[rasters]
GradientRasterTime = 10e-6
RadiofrequencyRasterTime = 1e-6
AdcRasterTime = 100e-9
BlockDurationRaster = 10e-6
```

## 3. The check configuration

A check configuration is a TOML or a JSON file that names the targets and the
checks. `pulseq-check --config` and `read_check_config` read it.

| Key | Type | Meaning |
|---|---|---|
| `format` | integer | Necessary. This version reads `1`. |
| `targets` | list of strings | Necessary, not empty. The paths of the target profile files, relative to the directory of the configuration file. |
| `select` | list of strings | Optional. The check IDs to run. Without it, all installed checks run. |
| `required` | table | Optional. Each key is a check ID. The value is `true` (required for each target) or a list of target names (`name` in the profile) for which it is required. |
| `fast_only` | boolean | Optional, default `false`. Run only the checks of the cost class `fast` (and the required checks). |

An unknown key is an error. The reader does not compare the check IDs with the
installed checks: `run_checks` does, and an ID that is not installed is an
error of the run. A required check runs whatever `select` and `fast_only`
say.

A check is required for a target when the caller names it: in `required`, or
with `--check`. Selection by `select` or `fast_only` does not make a check
required. A check that is not required and is not evaluated does not change
the exit status.

```toml
format = 1
targets = ["prisma.toml", "sites/vida.toml"]
select = ["timing.pypulseq", "gradient.amplitude.axis", "gradient.slew.axis", "pns.safe"]
fast_only = false

[required]
"timing.pypulseq" = true
"pns.safe" = ["Prisma AS82"]
```

The same in JSON:

```json
{
  "format": 1,
  "targets": ["prisma.toml", "sites/vida.toml"],
  "select": ["timing.pypulseq", "gradient.amplitude.axis",
             "gradient.slew.axis", "pns.safe"],
  "fast_only": false,
  "required": {
    "timing.pypulseq": true,
    "pns.safe": ["Prisma AS82"]
  }
}
```

Here `timing.pypulseq` is required for each target, and `pns.safe` is required
only for the target `Prisma AS82`.

## 4. The command `pulseq-check`

```
pulseq-check SEQ_FILE (--config FILE | --target PROFILE [--target PROFILE ...])
             [--check ID ...] [--fast] [--json OUT] [--max-findings N]
             [--show-findings] [--quiet]
```

| Argument | Meaning |
|---|---|
| `SEQ_FILE` | The `.seq` file. The command reads it one time for each target, with the `Opts` of that target. |
| `--config FILE` | A [check configuration](#3-the-check-configuration). Its targets are relative to the file. |
| `--target PROFILE` | A [target profile](#2-the-target-profile). Repeat it for more targets. |
| `--check ID` | Select this check, and make it required for each target. Repeat it for more checks. With `--config`, the IDs are added to its `select` (if it has one) and made required for all targets. |
| `--fast` | Run only the checks of the cost class `fast`, and the required checks. Selection by cost does not make a check required. The cost class of each check is in [`checks.md`](checks.md). A check that does not declare a class is `slow`. |
| `--json OUT` | Write the result as [JSON](#6-the-result-json) to the file `OUT`. `-` writes it to the standard output and the summary to the standard error. |
| `--max-findings N` | Keep only the first `N` findings of each result, in the JSON result and in the summary. `N` must be an integer of 0 or more. The result records the number of the others in `findings_omitted`. Without it, all findings are kept. |
| `--show-findings` | List each kept finding in the summary (see [the summary](#the-summary)). Without it, the summary gives only a count for each result with findings. |
| `--quiet` | Do not write the summary. |

Give exactly one of `--config` and `--target`. There is no flag for the limits
of a `Sequence` object: only the Python function has `limits_from_sequence`
([section 5](#5-the-python-api)).

### Exit status

| Status | Meaning |
|---|---|
| 0 | No check failed, no check gave an error, and each required check was evaluated. |
| 2 | At least one check failed. |
| 1 | An error in the arguments, in a profile or in the configuration, or in the run; a check that gave an error; or a required check that was not evaluated. |

When both 1 and 2 apply, the status is 1: the result set is not complete. The
summary still lists each failure. An error in the arguments is 1, not 2.

### The summary

The summary has five parts:

1. One line for each check and each target: the state, the check ID, the
   target, the value and the limit with the unit, a short detail (for example
   the axis or the raster), and a mark for a required check.
2. The "not evaluated" and "error" results, with their reasons.
3. The findings. This part is there only when a result has findings. It has
   one count line for each result with findings. After `--max-findings`, the
   count line also gives the numbers that the result kept and omitted, for
   example `4000 findings (1000 kept, 3000 omitted)`. With `--show-findings`,
   one line follows for each kept finding. The line is
   `block B at T s: CODE: message` for a finding with a block,
   `at T s: CODE: message` for a finding with a time and no block, and
   `CODE: message` for a finding with no location. A message of more than one
   line has its other lines indented.
4. The unused sections of each profile.
5. The meaning of the exit status.

For example, the spin echo of `tests/synthetic.py` against the profile
`tests/profiles/prisma.toml` (the sequence was made with an RF ringdown of
20 µs, and the target has 30 µs, so its blocks are too short for the target):

```text
$ pulseq-check spin_echo.seq --target prisma.toml
sequence: spin_echo.seq

results (* = required):
    state  check                               target       value                          detail
    pass   gradient.amplitude.any-orientation  Prisma AS82  27.72 mT/m (limit 80 mT/m)
    pass   gradient.amplitude.axis             Prisma AS82  27.72 mT/m (limit 80 mT/m)     axis x
    pass   gradient.slew.axis                  Prisma AS82  145.9 T/m/s (limit 200 T/m/s)  axis x
    pass   pns.safe                            Prisma AS82  86.6 % (limit 100 %)
    fail   timing.pypulseq                     Prisma AS82  4 (limit 0)                    first of 4 errors: block 1, block.duration: BLOCK_DURATION_MISMATCH
    pass   timing.rasters                      Prisma AS82  1e-05 s (limit 1e-05 s)        GradientRasterTime: 1e-05 s in the file, 1e-05 s on the target

findings (each one is in the JSON result; --show-findings lists them here):
  timing.pypulseq, target Prisma AS82: 4 findings

exit status 2: a check failed
```

The check `timing.pypulseq` gives one finding for each error. With
`--show-findings`, the part of the findings of the same run is:

```text
findings:
  timing.pypulseq, target Prisma AS82: 4 findings
    block 1 at 0 s: BLOCK_DURATION_MISMATCH: Inconsistency between the stored block duration (1120.00 us) and the content of the block (1130.00 us)
    block 1 at 0 s: RF_RINGDOWN_TIME: Time between the end of the RF pulse at 1100.00 us and the end of the block at 1120.00 us is shorter than rf_ringdown_time (30 us)
    block 4 at 0.00247 s: BLOCK_DURATION_MISMATCH: Inconsistency between the stored block duration (1120.00 us) and the content of the block (1130.00 us)
    block 4 at 0.00247 s: RF_RINGDOWN_TIME: Time between the end of the RF pulse at 1100.00 us and the end of the block at 1120.00 us is shorter than rf_ringdown_time (30 us)
```

The findings never go to the standard error on their own. They are a part of
the summary, which goes to the standard output (to the standard error only with
`--json -`), and `--quiet` removes them with the rest of the summary. The
findings do not change the exit status: a result with findings has the state
that the check gave it. To get all findings with no change to the console
output, write `--json FILE`. The file has all findings of each result, unless
you also give `--max-findings`. [Passing the findings to another
tool](#passing-the-findings-to-another-tool) shows how a different tool reads
them.

A required check has `*` in the first column. When a result is "not
evaluated" or "error", a block `not evaluated and errors:` follows the table
with the reason of each. When a result has findings, a block `findings` follows.
A block `unused profile sections` lists the sections that no check used.

## 5. The Python API

```python
from pulseq_checks import read_check_config, read_profile, run_checks

config = read_check_config("checks.toml")
targets = [read_profile(path) for path in config.targets]
matrix = run_checks(
    "scan.seq",
    targets,
    select=config.select,
    required=config.required,
    fast_only=config.fast_only,
)
for result in matrix.results:
    print(result.state.value, result.check_id, result.target, result.value)
raise SystemExit(matrix.exit_status())
```

This is what the command does. The package exports `read_profile`,
`read_check_config`, `run_checks`, `TargetProfile`, `HardwareLimits`,
`CheckConfig`, `Result`, `ResultMatrix`, `State`, `Location`, `TargetInfo`,
`Finding`, `CheckSpec`, `CheckRule`, `RunContext` and the errors.

### `read_profile(path) -> TargetProfile`

Reads a [target profile](#2-the-target-profile). Raises `ProfileError`.
`TargetProfile` is a frozen dataclass:

| Field | Meaning |
|---|---|
| `name`, `vendor`, `format_version`, `source_path` | From the file. `source_path` is the resolved path. |
| `opts` | The `[opts]` values (and the `.asc` limits) as a mapping, or `None`. |
| `hardware_limits` | A `HardwareLimits` (`max_grad_mt_per_m`, `max_slew_t_per_m_per_s`, `label`), or `None`. It is there only when the profile gives both `opts.max_grad` and the slew limit (`opts.max_slew`, or `opts.rise_time`). |
| `rasters` | The `[rasters]` values by their reserved names, or `None`. |
| `models` | A mapping from a model name (`"pns.safe"`) to the checked parameters. |
| `acoustic_resonances` | A tuple of (frequency, bandwidth) pairs, or `None`. |
| `sources` | A mapping from each value path (`"opts.max_grad"`, `"models.pns.safe"`) to `"profile"` or to the label of the `.asc` file. |
| `unused_sections` | The names of the sections that the reader did not use. |

Two methods: `make_opts()` returns `pp.Opts(...)` with the `[opts]` and
`[rasters]` values, and `has_value(path)` is true when a source gives the
value path.

### `read_check_config(path) -> CheckConfig`

Reads a [check configuration](#3-the-check-configuration). Raises
`ConfigError`. `CheckConfig` has `source_path`, `format_version`, `targets`
(a tuple of the paths of the profile files, made relative to the
configuration file), `select` (a tuple, or `None` for all checks), `required`
(a dict from a check ID to a tuple of target names, or `None` for all targets)
and `fast_only`.

### `run_checks(...) -> ResultMatrix`

```python
def run_checks(
    sequence,
    targets,
    *,
    select=None,
    required=None,
    fast_only=False,
    limits_from_sequence=False,
) -> ResultMatrix: ...
```

| Argument | Meaning |
|---|---|
| `sequence` | A `.seq` path (`str` or `Path`), or a `pp.Sequence` object. |
| `targets` | A list of `TargetProfile`. It must not be empty. The names must be different. |
| `select` | The check IDs to run. `None` runs all installed checks. |
| `required` | A mapping from a check ID to the target names for which it is required, or to `None` for all targets. `None` (the default) means that no check is required. A required check runs whatever `select` and `fast_only` say. |
| `fast_only` | Run only the checks of the cost class `fast`, and the required checks. It does not make a check required. |
| `limits_from_sequence` | The opt-in to the limits of the sequence. Only with a `Sequence` object (see below). |

The results are in the order of the targets, then of the check IDs.
`run_checks` raises `RunError` for an error of the run: no target, two
targets with one name, an ID in `select` or `required` that is not an
installed check, a target name in `required` that is not a target, a `.seq`
file that cannot be read, or an argument combination that is not allowed. An
exception inside a check is not an error of the run: it is the result "error"
of that check.

**A path.** `run_checks` reads the file one time for each target, with the
`Opts` of that target. (A sequence that is read with the `Opts` of one target
is not correct for another target: pypulseq stores the dead times of the
`Opts` in the events that it reads.) `limits_from_sequence=True` with a path is
an error.

**A `Sequence` object.** It gives exactly one target. `run_checks` uses the
object as it is. Make it with `pp.Sequence(system=target.make_opts())`, so that
`timing.pypulseq` compares it with the target, because `check_timing`
compares with `seq.system`.

With `limits_from_sequence=True`, a target that gives neither `opts.max_grad`
nor `opts.max_slew` gets its gradient limits from `seq.system`. The result
records it: `TargetInfo.limits_source` is `"sequence object"`. The caller is
responsible for the system of the object. A `Sequence` that `seq.read` reads
from a file has only the default values of pypulseq in `seq.system`, because
the file does not contain the limits of its author. There is no default and no
other way: no command flag and no profile entry.

```python
import pypulseq as pp
from pulseq_checks import read_profile, run_checks

target = read_profile("no_gradient_limits.toml")
system = pp.Opts(max_grad=28, grad_unit="mT/m", max_slew=150, slew_unit="T/m/s")
seq = pp.Sequence(system=system)
# ... add the blocks ...
matrix = run_checks(seq, [target], limits_from_sequence=True)
```

### `ResultMatrix`

A frozen dataclass:

| Field or method | Meaning |
|---|---|
| `sequence` | The path as the caller gave it, or `"<Sequence object>"`. |
| `package_version` | The version of `pulseq-checks` that made the matrix. |
| `targets` | A tuple of `TargetInfo`: `name`, `sources`, `unused_sections` and `limits_source` (`"profile"` or `"sequence object"`). |
| `results` | A tuple of `Result`. |
| `exit_status()` | 0, 2 or 1, by the [table above](#exit-status). |
| `with_max_findings(n)` | A new matrix in which each result with more than `n` findings keeps the first `n`, and its `findings_omitted` has the number of the others added. `n` must be an `int` of 0 or more (not a `bool`), else `ValueError`. |
| `to_json()` | The [JSON](#6-the-result-json) text. |
| `ResultMatrix.from_json(text)` | The matrix of a text from `to_json`. `from_json(m.to_json()) == m`. Raises `ValueError` for a format that is newer than this package, and for an unknown or a missing key. |

### `Result`

A frozen dataclass:

| Field | Meaning |
|---|---|
| `check_id`, `spec_version` | The check and the version of its specification. |
| `target` | The name of the target. |
| `state` | A `State`: `PASS`, `FAIL`, `NOT_EVALUATED` or `ERROR` (the values `"pass"`, `"fail"`, `"not evaluated"`, `"error"`). |
| `value`, `limit`, `unit` | The measured value, the limit and the unit. `None` when the check did not run. |
| `location` | A `Location(block, time_s)`, or `None`. `block` is the block ID (or `None` when no block has the value), and `time_s` is the time in seconds from the start of the sequence. |
| `model`, `model_version` | The model and its version, or `None`. |
| `reason` | Why the state is "not evaluated" or "error". For a pass or a fail: a short detail, or `None`. |
| `required` | `True` when the caller named the check for this target. |
| `spec_url` | The link to the specification. |
| `findings` | A tuple of `Finding`: the problems that the check found, in the order that the check gave them. The default is `()`. A result of any state can have findings. They do not change the state. |
| `findings_omitted` | The number of findings that are not in `findings`, because `with_max_findings` removed them. The default is `0`. |

### `Finding`

A frozen dataclass: one problem that a check found.

| Field | Meaning |
|---|---|
| `code` | A short, stable name of the kind of finding. A string that is not empty. |
| `message` | One line of text for a person. A string. |
| `location` | A `Location`, or `None` (the default). |
| `data` | A mapping from a name to a value, for a machine. The default is an empty dict. |

`__post_init__` refuses a value that is not valid: `TypeError` when `code` or
`message` is not a string, when `location` is not a `Location` or `None`, when
`data` is not a mapping, when a key of `data` is not a string, and when a value
of `data` is not a string, an `int`, a `float`, a `bool` or `None`; `ValueError`
when `code` is empty, and when a string value of `data` is `"inf"`, `"-inf"` or
`"nan"`. The last rule is there because the [JSON](#6-the-result-json) writes a
float that is not finite as one of these strings, and `from_json` turns the
string back into a float. A string with the same text could not be told apart.
A `Finding` with data is not hashable.

To read the findings of a matrix:

```python
from pulseq_checks import ResultMatrix, read_profile, run_checks

matrix = run_checks("scan.seq", [read_profile("prisma.toml")])
for result in matrix.results:
    total = len(result.findings) + result.findings_omitted
    print(result.check_id, result.target, total, "findings")
    for finding in result.findings:
        print(" ", finding.code, finding.location, finding.data)

small = matrix.with_max_findings(100)  # for a report page
text = small.to_json()  # the findings and findings_omitted go with it
again = ResultMatrix.from_json(text)
```

### The errors

`CheckRunError` is the base class of each error of the run. Its subclasses:

| Error | Raised by |
|---|---|
| `ProfileError` | `read_profile`. |
| `ConfigError` | `read_check_config`. |
| `RunError` | `run_checks`. |
| `RegistryError` (in `pulseq_checks.registry`) | Two packages that give one check ID, model name or reader name, and an entry point that cannot be loaded. |

The command catches `CheckRunError` and gives exit status 1.

## 6. The result JSON

`ResultMatrix.to_json()` and `pulseq-check --json` write one object:

| Key | Meaning |
|---|---|
| `format` | `1`. `from_json` refuses a larger number. In the release candidates the format stays 1 when the JSON changes: a reader of `0.1.0rc1` refuses a result of this version, because of the unknown key `findings`. |
| `package_version` | The version of `pulseq-checks`. |
| `sequence` | The path of the `.seq` file, or `"<Sequence object>"`. |
| `targets` | One object for each target: `name`, `sources` (each value path, with `"profile"` or the `.asc` file as its source), `unused_sections` and `limits_source`. |
| `results` | One object for each check and target, with the keys of `Result`. `state` is a string. `location` is `null` or `{"block": ..., "time_s": ...}`. `findings` is a list of finding objects, and `findings_omitted` is an integer of 0 or more. |

A finding object has the keys `code`, `message`, `location` and `data`, in this
order. `location` is `null` or `{"block": ..., "time_s": ...}`, and `data` is an
object. A value of `data` that is a float that is not finite is a string.

The JSON is strict. A float that is not finite is a string: `"inf"`, `"-inf"`
or `"nan"`. This example is a run of the checks `gradient.amplitude.axis`,
`gradient.slew.axis` and `pns.safe` on a sequence that was built for a
scanner with a slew limit of 250 T/m/s. The profile gives the limits of
80 mT/m and 200 T/m/s and no SAFE parameters, and `gradient.slew.axis` is
named as required:

```json
{
  "format": 1,
  "package_version": "0.1.0.dev0",
  "sequence": "scan.seq",
  "targets": [
    {
      "name": "Prisma AS82",
      "sources": {
        "opts.max_grad": "profile",
        "opts.grad_unit": "profile",
        "opts.max_slew": "profile",
        "opts.slew_unit": "profile"
      },
      "unused_sections": [],
      "limits_source": "profile"
    }
  ],
  "results": [
    {
      "check_id": "gradient.amplitude.axis",
      "spec_version": 1,
      "target": "Prisma AS82",
      "state": "pass",
      "value": 40.0,
      "limit": 80.0,
      "unit": "mT/m",
      "location": {
        "block": 1,
        "time_s": 0.00016
      },
      "model": null,
      "model_version": null,
      "reason": "axis x",
      "required": false,
      "spec_url": "https://github.com/mdtisdall/pulseq-checks/blob/main/docs/checks.md#gradientamplitudeaxis",
      "findings": [],
      "findings_omitted": 0
    },
    {
      "check_id": "gradient.slew.axis",
      "spec_version": 1,
      "target": "Prisma AS82",
      "state": "fail",
      "value": 250.0,
      "limit": 200.0,
      "unit": "T/m/s",
      "location": {
        "block": 1,
        "time_s": 0.0
      },
      "model": null,
      "model_version": null,
      "reason": "axis x",
      "required": true,
      "spec_url": "https://github.com/mdtisdall/pulseq-checks/blob/main/docs/checks.md#gradientslewaxis",
      "findings": [],
      "findings_omitted": 0
    },
    {
      "check_id": "pns.safe",
      "spec_version": 1,
      "target": "Prisma AS82",
      "state": "not evaluated",
      "value": null,
      "limit": null,
      "unit": null,
      "location": null,
      "model": null,
      "model_version": null,
      "reason": "the target 'Prisma AS82' does not give: model pns.safe",
      "required": false,
      "spec_url": "https://github.com/mdtisdall/pulseq-checks/blob/main/docs/checks.md#pnssafe",
      "findings": [],
      "findings_omitted": 0
    }
  ]
}
```

The exit status of this run is 2: one check failed, and no required check was
"not evaluated". `pns.safe` is not required.

### Passing the findings to another tool

The JSON result is the output that carries the findings to the next tool. The
console output stays short: the summary has only a count line for each result
with findings. Write the result to a file:

```
pulseq-check spin_echo.seq --target prisma.toml --json result.json
```

or to the standard output, for a pipe. Then the summary goes to the standard
error, so the next tool gets only the JSON:

```
pulseq-check spin_echo.seq --target prisma.toml --json - | next-tool
```

For the spin echo of [section 4](#the-summary), the result of
`timing.pypulseq` has four findings. The first one is:

```json
{
  "code": "BLOCK_DURATION_MISMATCH",
  "message": "Inconsistency between the stored block duration (1120.00 us) and the content of the block (1130.00 us)",
  "location": {
    "block": 1,
    "time_s": 0.0
  },
  "data": {
    "event": "block",
    "field": "duration",
    "value": 0.0011300000000000001,
    "duration": 0.0011200000000000001
  }
}
```

The `data` of a finding are in SI units (here seconds). The `message` gives
the same values for a person. The specification of the check in
[`checks.md`](checks.md) gives its codes and the keys of its `data`.

A tool that does not use `pulseq-checks` reads the JSON directly. With `jq`,
one line for each finding:

```
jq -r '.results[] | .check_id as $c | .findings[] | [$c, .code, .location.block, .message] | @tsv' result.json
```

With Python and no other package:

```python
import json

with open("result.json") as f:
    result = json.load(f)
for r in result["results"]:
    for finding in r["findings"]:
        print(r["check_id"], finding["code"], finding["location"]["block"])
    if r["findings_omitted"]:
        print(r["check_id"], r["findings_omitted"], "findings omitted")
```

A Python tool that uses `pulseq-checks` reads the file with
`ResultMatrix.from_json(Path("result.json").read_text())`. It gets each
finding as a `Finding` ([section 5](#finding)), and `from_json` refuses a text
with a missing or an unknown key. A program that runs the checks itself gives
the matrix to the next tool with `matrix.to_json()`.

A sequence with many errors can give many findings: on 10⁶ blocks with an
error in each TR, `timing.pypulseq` gives 4 × 10⁵ findings, and the JSON
result is about 200 MB. `--max-findings N` (or
`ResultMatrix.with_max_findings(N)` in Python) keeps the first `N` findings of
each result. The number of the others is in `findings_omitted`, so the next
tool knows that the list is not complete. With `--max-findings 1000`, the same
result is 0.5 MB. A gradient check that fails in each TR gives one finding for
each such block and axis, so `--max-findings` matters there too.

## 7. Writing a plugin

A package can add checks, models and profile readers. Each is an object that
the package registers as an entry point. `pulseq-checks` loads the entry
points of all installed packages.

| Entry-point group | The object | Used for |
|---|---|---|
| `pulseq_checks.checks` | A check rule | A new check. |
| `pulseq_checks.models` | A model | The parameters of a physical model in `[models.<name>]` of a profile. |
| `pulseq_checks.profile_readers` | A function | A reader that fills a profile from a vendor file. |

Two packages that give one check ID (or one model name, or one reader name)
are an error of the run (`RegistryError`). It names both packages.

### A check rule

A check rule is an object with `spec` (a `CheckSpec`) and a method
`run(ctx) -> Result`. `CheckSpec` is a frozen dataclass. The specification is
data: `scripts/check_docs.py` makes [`checks.md`](checks.md) from the
specifications of this package, and the documentation of a plugin can do the
same.

| Field | Meaning |
|---|---|
| `id` | A stable ID, for example `"site.block-duration"`. |
| `version` | An integer. It changes when the rule changes, so that old results stay clear. |
| `title` | A short title. |
| `quantity` | The quantity and its exact definition. |
| `inputs` | A tuple of the value paths that the check needs from the profile (`"opts.max_grad"`, `"rasters.GradientRasterTime"`, `"acoustic.resonances"`). |
| `models` | A tuple of the model names that the check needs (`"pns.safe"`). |
| `limit` | The limit, and where it comes from. |
| `tolerance` | The tolerance. |
| `pass_condition` | The pass condition. |
| `cost` | `"fast"` or `"slow"`. The default is `"slow"`, so that a check that nobody measured does not make the fast set slow. |
| `pypulseq` | The pypulseq function that the check uses, or `None`. |
| `url` | The link to the documentation of the check. A plugin sets it. With `None`, a result links to the heading of the ID in the `checks.md` of this package, which is wrong for a plugin. |
| `findings` | A text, or `None` (the default). A check that gives findings documents them here: what one finding is, its codes, its location, the keys of `data` and the order of the findings. A check that gives none leaves it `None`. |
| `rasters` | A tuple of the raster names that the measurement of the check uses (`"GradientRasterTime"`, `"RadiofrequencyRasterTime"`, `"AdcRasterTime"`, `"BlockDurationRaster"`). The default is `()`. Put it after `findings` when you give the fields by position. |

The run function does these steps for each target:

1. It makes a `RunContext`. The sequence is read with the `Opts` of the target.
2. When a value path of `spec.inputs` is missing, or a model of `spec.models`
   is not in the profile, or a raster of `spec.rasters` is neither in the file
   nor in the profile, the result is "not evaluated" **before** `run` is
   called. The reason names what is missing. Thus `run` can use these values
   without a check.
3. It calls `rule.run(ctx)`. An exception gives the result "error", with the
   reason `<exception type>: <message>`. A `run` that returns a result for a
   different check or target, or returns something that is not a `Result`, is
   an "error" too. So is a result whose `findings` is not a tuple of
   `Finding`, or whose `findings_omitted` is not an `int` (not a `bool`) of 0
   or more.
4. It sets `required` on the result.

`RunContext` has:

| Member | Meaning |
|---|---|
| `ctx.sequence` | The `pp.Sequence` of this target. |
| `ctx.profile` | The `TargetProfile`. |
| `ctx.limits_source` | `"profile"`, or `"sequence object"` ([section 5](#5-the-python-api)). |
| `ctx.hardware_limits` | The `HardwareLimits` for the gradient checks, or `None`. |
| `ctx.raster_sources` | A dict from each raster name to where its value comes from: `"file"` (the file declares it), `"target"` (the file does not, and the profile gives it), `"sequence object"` (the sequence is a `Sequence` object) or `"pypulseq default"` (neither gives it). A `RunContext` that you make by hand has `"sequence object"` for all four. |
| `ctx.has_input(path)` | True when the target gives the value path. |
| `ctx.measure(name, fn)` | `fn(ctx.sequence)`, calculated one time for each `name` and each target. The other rules of the target get the kept value. |
| `ctx.result(spec, state, **fields)` | A `Result` with `check_id`, `spec_version`, `target` and `spec_url` set. `fields` are `value`, `limit`, `unit`, `location`, `model`, `model_version`, `reason` and `findings`. Do not set `required`. |

`ctx.measure` makes a measurement once when several checks use it. The first
call for a name calculates. Later calls with that name return the kept value
and do not call their `fn`. The names of version 1 are:

| Name | The value | The function |
|---|---|---|
| `"index"` | The block table of the sequence | `pulseq_checks.seq_index.sequence_index` |
| `"gradient_limits"` | The peaks over the whole file | `pulseq_checks.grad_limits.gradient_limits(seq, limits=...)` |
| `"gradient_blocks"` | The gradient values of each block | `pulseq_checks.grad_limits.block_gradient_values(seq, gamma=...)` |
| `"pns_levels"` | The SAFE PNS levels | `pulseq_checks.pns.pns_levels_for(seq, hardware=(hw, label))` |

Use a name only with the function in this table. A plugin that uses the name
`"index"` with a different function gets the value of whichever check called
first. Give your own measurement a name of your own (for example
`"site.block-duration"`). Never call `gradient_limits` with `limits=None`: it
would take the limits of `seq.system`.

An example: a check of a fixed limit on the duration of a block. The limit is
a part of the specification, so `inputs` is empty. The result gives the
longest block, and one finding for each block that is too long.

```python
import numpy as np

from pulseq_checks import CheckSpec, Finding, Location, Result, RunContext, State
from pulseq_checks.seq_index import sequence_index

MAX_BLOCK_S = 0.1


class _BlockDuration:
    spec = CheckSpec(
        id="site.block-duration",
        version=1,
        title="Longest block of the sequence",
        quantity="The longest block duration of the sequence, in seconds.",
        inputs=(),
        models=(),
        limit="0.1 s. The limit is fixed by this check, not by the target.",
        tolerance="None.",
        pass_condition="Pass when the longest block is at most 0.1 s.",
        cost="fast",
        url="https://example.org/site-checks/block-duration",
        findings=(
            "One finding for each block that is longer than 0.1 s, in the play order of "
            "the blocks. The code is BLOCK_TOO_LONG. The location is the block and its "
            "start time. data has duration_s: the duration of the block, in seconds."
        ),
    )

    def run(self, ctx: RunContext) -> Result:
        index = ctx.measure("index", sequence_index)
        if index.num_blocks == 0:
            return ctx.result(self.spec, State.PASS, value=0.0, limit=MAX_BLOCK_S, unit="s")
        findings = []
        for i in np.flatnonzero(index.duration_s > MAX_BLOCK_S):
            block, duration = int(index.block_id[i]), float(index.duration_s[i])
            findings.append(
                Finding(
                    code="BLOCK_TOO_LONG",
                    message=f"block {block} lasts {duration:g} s",
                    location=Location(block=block, time_s=float(index.start_s[i])),
                    data={"duration_s": duration},
                )
            )
        i = int(index.duration_s.argmax())
        value = float(index.duration_s[i])
        location = Location(block=int(index.block_id[i]), time_s=float(index.start_s[i]))
        state = State.PASS if value <= MAX_BLOCK_S else State.FAIL
        return ctx.result(
            self.spec,
            state,
            value=value,
            limit=MAX_BLOCK_S,
            unit="s",
            location=location,
            findings=tuple(findings),
        )


BLOCK_DURATION = _BlockDuration()
```

Register it in the `pyproject.toml` of the plugin package:

```toml
[project.entry-points."pulseq_checks.checks"]
"site.block-duration" = "site_checks.blocks:BLOCK_DURATION"
```

A rule gives its findings with the argument `findings` of `ctx.result`: a
tuple of `Finding` ([section 5](#finding)), in a fixed order. A result of any
state can have findings, and they do not change the state. The rule gives all
of its findings and does not set `findings_omitted`: the command and
`ResultMatrix.with_max_findings` set it when they remove findings. The rule
must document its findings in `CheckSpec.findings`: what one finding is, its
codes, its location, the keys of `data` and the order of the findings. A value
of `data` must be a `str`, `int`, `float`, `bool` or `None`. A NumPy integer
is not an `int`: convert each NumPy value with `int(x)` or `float(x)`, as the
example does.

With a sequence of four delays of 0.05, 0.2, 0.01 and 0.15 s, the summary of
this check with `--show-findings` is:

```text
results (* = required):
    state  check                target       value                detail
    fail   site.block-duration  Prisma AS82  0.2 s (limit 0.1 s)

findings:
  site.block-duration, target Prisma AS82: 2 findings
    block 2 at 0.05 s: BLOCK_TOO_LONG: block 2 lasts 0.2 s
    block 4 at 0.26 s: BLOCK_TOO_LONG: block 4 lasts 0.15 s
```

To test a rule alone, make `RunContext(sequence, profile)` and call
`rule.run(ctx)`. The run function gives the "not evaluated" and "error"
results, not the rule.

### A model

An object with `name` (the dotted path of its section under `models`, for
example `"pns.safe"` for `[models.pns.safe]`), `version` (an integer, given in
the result) and `read(params) -> dict`. `read` checks the parameters and
returns them as a plain dict of JSON types. It raises `ValueError` for an
unknown or a missing key, and `read_profile` turns it into a `ProfileError`
that names the section. The entry point of the SAFE model is
`"pns.safe" = "pulseq_checks.pns_levels:SAFE_MODEL"` in the group
`pulseq_checks.models`. A check that needs a model names it in
`spec.models` and reads `ctx.profile.models[name]`.

### A profile reader

A function `read(path, *, gradient_mode=None) -> (sections, sources)` in the
group `pulseq_checks.profile_readers`. `sections` has the nested form of the
profile file (`opts`, `models`, `acoustic`), with only the values that the
vendor file gives. `sources` maps each value path to a label. It raises
`ValueError` for a value that is not valid and `OSError` for a file that it
cannot read. In version 1, the key `asc` of a profile uses only the reader
named `siemens-asc` (this package gives it). No profile key selects another
reader.

## 8. Limits of version 1

- **Rotation extension.** The gradient and PNS measurements refuse a file with
  the Pulseq rotation extension, because the gradients of the file are not the
  gradients on the scanner. With pypulseq 1.5.0.post1, `Sequence.read` raises
  `ValueError` for such a file first, and that is an error of the run (status
  1). A later pypulseq that reads it gives the result "error" for these checks.
- **Equal rasters only.** `timing.rasters` passes only when each raster of the
  file equals the raster of the target. There is no rule for unequal rasters.
  Whether a file with other rasters plays correctly depends on how the
  interpreter of the target resamples the shapes, and the Pulseq specification
  does not say. A rule must come from the behavior of specific interpreters.
  The item is in [`TODO.md`](../TODO.md). The other checks still run with the
  rasters of the target.
- **No default limits, and no limits of the sequence in the command.** Only
  the Python function has `limits_from_sequence`, and only for a `Sequence`
  object.
- **No convention checks** (handedness, axis mapping), and no worst-case slew
  under rotation. They come later.
- **No JUnit output.**
- **The pypulseq fork.** This package needs pypulseq 1.5.0.post1 with four
  commits that are not in a release: the SAFE PNS filter as a recursion,
  `calc_pns` in chunks, the `get_block` fix for oversampled arbitrary
  gradients, and the read fix of upstream #359. `pyproject.toml` pins the fork
  `mdtisdall/pypulseq` in `[tool.uv.sources]`. uv applies this pin for a
  project that depends on `pulseq-checks` by git URL. pip does not: with pip,
  install the fork commit of the pin yourself. [`TODO.md`](../TODO.md) lists
  the commits and the plan to go back to a pypulseq release.
