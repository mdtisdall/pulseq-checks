# Rasters and timing

This document explains why the raster and timing checks of `pulseq-checks`
are stricter than `checkTiming` of MATLAB Pulseq and `check_timing` of
pypulseq, and it gives the decisions about rasters that follow from that, with
the reason for each. The exact rule of each check is in
[`checks.md`](checks.md). This document does not copy it.

Contents:

1. [Summary](#1-summary)
2. [Two rasters in one sequence object](#2-two-rasters-in-one-sequence-object)
3. [What checkTiming and check_timing check](#3-what-checktiming-and-check_timing-check)
4. [Why that is not enough for a target](#4-why-that-is-not-enough-for-a-target)
5. [The decisions of pulseq-checks](#5-the-decisions-of-pulseq-checks)
6. [Open questions](#6-open-questions)

The facts about the two libraries are for pypulseq 1.5.0.post1 at the commit
`a74ab06` of the fork that this package pins, and for MATLAB Pulseq at the
commit `c746912` of `pulseq/pulseq` (2026-09-17).

## 1. Summary

A `.seq` file declares four rasters in `[DEFINITIONS]`: `GradientRasterTime`,
`RadiofrequencyRasterTime`, `AdcRasterTime` and `BlockDurationRaster`. A
scanner has its own rasters, for example a gradient raster of 10 µs on Siemens
and 4 µs on GE. In this package, the target profile gives the rasters of the
scanner (`[rasters]`).

MATLAB Pulseq and pypulseq keep both sets of rasters in a sequence object
after a read. Their timing checks compare some times of the file with the
rasters of the system, but not all of them. A file on a 4 µs gradient raster
can pass `check_timing` against a 10 µs system, although its gradient shapes
are not on the 10 µs raster (section 4).

`pulseq-checks` has a separate rule: the rasters of the file must equal the
rasters of the target (`timing.rasters`). The checks that measure the gradient
waveform measure the file on its own rasters. When a raster that such a check
uses is different on the target, the waveform on the scanner is not known, so
the check gives "error", not a value (decided, not yet in the code). Section 5
gives the decisions and their reasons.

## 2. Two rasters in one sequence object

Both libraries have a system object (the hardware) and raster attributes on
the sequence object (the file).

| | MATLAB Pulseq | pypulseq |
|---|---|---|
| The system | `obj.sys` | `seq.system` |
| The rasters of the sequence | `obj.gradRasterTime`, `obj.rfRasterTime`, `obj.adcRasterTime`, `obj.blockDurationRaster` | `seq.grad_raster_time`, `seq.rf_raster_time`, `seq.adc_raster_time`, `seq.block_duration_raster` |
| The constructor | Stores the system, and copies its rasters to the sequence | The same |
| A read of a file | Replaces the rasters of the sequence with the rasters that the file declares. Does not change `obj.sys`. | The same: does not change `seq.system` |

When you build a sequence, the two sets are equal. After a read, they are
different when the file declares other rasters than the system that the
reader gives. For example, a file with a 4 µs gradient raster, read with
`pp.Sequence()` (the default system):

```
seq.grad_raster_time         4e-06   the raster of the file
seq.system.grad_raster_time  1e-05   the raster of the system
```

Both libraries use the two sets for different work:

- **The rasters of the sequence** make the waveforms of the file: the times of
  the shape samples, the gradient durations, the waveforms for plots and for
  PNS, and the k-space trajectory.
- **The rasters of the system** are the hardware in the checks: the timing
  check, and the limit of the step at a block junction
  (`max_slew * grad_raster_time` of the system).

The junction check runs only when you add a block. A read fills the block
table directly, so the junctions of a file that you read are never checked.

## 3. What checkTiming and check_timing check

`checkTiming` (MATLAB, `mr.checkTiming` for each block, called by
`Sequence.checkTiming`) and `check_timing` (pypulseq) compare these times with
the rasters of the system:

| Time | Raster of the system | MATLAB | pypulseq |
|---|---|---|---|
| Block duration | block duration raster | Yes | Yes |
| Delay of each event | gradient raster for a gradient, RF raster for RF and ADC | Yes | Yes |
| Rise, flat and fall time of a trapezoid | gradient raster | Yes | Yes |
| ADC dwell | ADC raster | Yes | Yes |
| Time points of an RF shape | RF raster | Yes | No |
| Sample times and corner points of an arbitrary gradient or an extended trapezoid | gradient raster | **No** | **No** |
| Step at a block junction, after a read | `max_slew * grad_raster_time` | **No** | **No** |
| The rasters that the file declares | the rasters of the system | **No** | **No** |

MATLAB also checks the block duration against the block duration raster of
the file. The tolerance on a ratio to a raster is 1e-9 in MATLAB and 1e-6 in
pypulseq.

Thus the two libraries check the events whose times are fields (delays,
durations, trapezoid times). They do not check the times of a shaped gradient,
and they do not compare the declared rasters.

## 4. Why that is not enough for a target

### Shapes that are not on the raster of the target pass

Two files on a 4 µs gradient raster, read with a 10 µs system (pypulseq):

| File | Times that are not on 10 µs | `check_timing` |
|---|---|---|
| An arbitrary gradient of 50 samples (200 µs) | The samples, at 2, 6, 10, 14, … µs | True, no errors |
| An extended trapezoid with corners at 0, 12, 188 and 200 µs | The corners at 12 and 188 µs | True, no errors |

A 10 µs scanner cannot play these shapes as the file gives them: its
interpreter must make other samples, and the next part shows that the
specification does not say how.

### Times on the raster of the target are not enough

A rule that checks each time of the file against the raster of the target
still does not show that the shapes play correctly. By the Pulseq
specification, the samples of a gradient or RF shape are values at the centres
of the raster steps of the file: `t_n = t_start + F (0.5 + n)` for a file
raster F. A file on 20 µs has its samples at 10, 30, 50, … µs. A 10 µs scanner
plays samples at 5, 15, 25, … µs. All the edges of the file are on the
raster of the target, but the interpreter must still make new samples.

The specification does not say how an interpreter makes a shape on another
raster. So a check that passes a file with other rasters says something about
the interpreter that the check does not know. This is true for a coarser file
raster and for a finer one.

### What the libraries check is for the author

In both libraries the system is mainly a tool to build a sequence. When you
build it, the system is the raster of the sequence, so the gaps of section 3
do not occur. `check_timing` then checks the work of the author. When you read
a file with the system of another scanner, the same function is not a check
that the file suits that scanner.

## 5. The decisions of pulseq-checks

The design document ([`plans/pulseq-checks.md`](plans/pulseq-checks.md),
section 5.10) records the decisions R6 and R8, and the decisions D2 and D3 of
the plan for the source of the rasters. This section explains them.

### 5.1 Version 1: the rasters of the file must equal the rasters of the target (R6)

`timing.rasters` compares each of the four rasters that the file declares with
the raster of the target. It passes only when each is equal, with a relative
tolerance of 1e-8 (pypulseq writes a definition with nine significant digits).
It fails when a raster is different, coarser or finer.

**Why:** section 4. With unequal rasters, the waveform on the target depends on
how the interpreter makes new samples, and the Pulseq specification does not
say. The check does not know whether such a file plays correctly, so it does
not pass it.

This rule does not say that a file with other rasters is always wrong. It says
that version 1 cannot tell. Section 6.2 describes what a later version needs
to pass some of these files.

### 5.2 The timing check is check_timing with the target (decision 5)

`timing.pypulseq` reads the file with the `pp.Opts` of the target and gives
the errors of `check_timing`. It does not add rules to `check_timing`.

**Why:** the gaps of `check_timing` (section 3) are about rasters, and
`timing.rasters` covers them for all events: when the rasters are equal, the
shapes of the file are on the raster of the target. The dead times, the
ringdown and the block durations are the rules of pypulseq, and this package
keeps them as pypulseq gives them.

### 5.3 The measurements use the rasters of the file (R8)

The gradient checks and `pns.safe` measure the waveform of the file with the
rasters of the file (`seq.grad_raster_time` and the block durations of the
file), not with the rasters of `seq.system`. For example, `gradient.slew.axis`
divides the step at a block junction by the gradient raster of the file.

**Why:** the value describes the waveform that the file gives. MATLAB Pulseq
and pypulseq make the waveforms of a file with its own rasters too
(section 2). Before this decision, a file on 4 µs, read with a 10 µs target or
with no `[rasters]`, had junction steps 2.5 times too small.

When `timing.rasters` passes, the two rasters are equal, so this decision
changes nothing. When a raster that the check uses is different, the check
gives "error" (section 5.6). Thus the decision is important for a measurement
with no target, for example a call of
`pulseq_analysis.grad_limits.gradient_limits` on a file that you read with
`pp.Sequence()`.

### 5.4 A raster that the file does not declare (D2)

A file of format 1.4.0 or newer must declare the four rasters. An older file
does not declare them, and a damaged file can leave one out. For a raster that
the file does not declare, the checks use the raster of the target, as the
interpreter of the target does. When the target does not give it either, a
check that uses that raster is "not evaluated" and its reason names the
raster.

`timing.rasters` itself gives "error" for a raster that the file does not
declare: there is no value of the file to compare.

**Why:** pypulseq uses the raster of `seq.system` for a raster that the file
does not declare, and that is its own default when the target does not give
one. A default of pypulseq is not a property of the target, so a result from
it says nothing about the target.

### 5.5 The rasters that each check uses (D3)

Each check lists in `CheckSpec.rasters` the rasters that its measurement
uses. The three gradient checks and `pns.safe` list `GradientRasterTime` and
`BlockDurationRaster`. `timing.rasters` and `timing.pypulseq` list none: they
need all four rasters of the target as inputs.

**Why:** the rule of section 5.4 needs to know which checks a missing raster
stops.

### 5.6 A different raster stops the waveform checks (R10)

Decided on 2026-10-02. **The code does not do this yet.** Until it does, the
four checks run and give the values of the file, as the table below says
under "Version 1 now".

When a raster that a check lists in `CheckSpec.rasters` is different in the
file and in the target, these four checks give "error", with a reason that
names the raster, the value of the file and the value of the target:

- `gradient.amplitude.axis`
- `gradient.amplitude.any-orientation`
- `gradient.slew.axis`
- `pns.safe`

Each of them lists `GradientRasterTime` and `BlockDurationRaster` (section
5.5). A difference in `RadiofrequencyRasterTime` or `AdcRasterTime` only does
not stop them: the gradient waveform is the same.

**Why:** these checks measure the gradient waveform. With a different
gradient raster or block duration raster, the scanner plays a waveform that
the interpreter makes from the file, and the checks do not know how
(section 4). A value of the waveform of the file is then not a value of the
waveform on the scanner, so a pass or a fail would be a prediction that the
check cannot make. This is the principle of section 5.1, applied to the
measurements.

**Why "error":** it is the state for a file whose gradient events are not the
gradients on the scanner. The rotation extension already gives "error" for
this reason ([`usage.md`](usage.md#the-four-states)). "Not evaluated" is for a
value that the target does not give, and here the target gives all its
values. An "error" gives exit status 1 (decision R1 of the design), also for
a check that is not required.

**Why only the rasters of `CheckSpec.rasters`:** a raster that the
measurement does not use does not change its value. `CheckSpec.rasters`
already lists the rasters of each measurement (section 5.5).

The evidence. Each file was checked against a target with the rasters of the
file, and against a target with the other raster (the target profile
`tests/profiles/prisma.toml`, 10 µs gradient raster and 1 µs RF raster), with
the code of version 1:

| File | Raster that differs | `timing.rasters` | The other five checks |
|---|---|---|---|
| `raster_4us_sequence` (a junction step) | gradient, 4 µs | fail | The same state and value for both targets. `timing.pypulseq` passes. |
| An arbitrary gradient of 50 samples | gradient, 4 µs | fail | The same for both targets. `timing.pypulseq` passes, with the samples at 2, 6, 10, … µs. |
| An extended trapezoid with corners at 12 and 188 µs | gradient, 4 µs | fail | The same for both targets. `timing.pypulseq` passes. |
| A block pulse and a trapezoid | RF, 2 µs | fail | The same for both targets. `timing.pypulseq` passes. |

Thus in version 1 the raster of the target does not change the result of a
waveform check. The checks and the decision for each:

| Check | Rasters that its value depends on | Version 1 now, when a raster differs | What the value says about the target | Decision |
|---|---|---|---|---|
| `gradient.amplitude.axis` | `GradientRasterTime` and `BlockDurationRaster`, of the file (`CheckSpec.rasters`) | Runs on the samples and corners of the file. The raster changes only the time of the location. | The peak of the samples of the file. The interpreter makes other samples, and the peak of those is not known unless the method of the interpreter is known. | "error" |
| `gradient.amplitude.any-orientation` | The same | Runs. \|G\| combines the axes at the times of the file, so the raster changes which values occur at the same time. | The peak of \|G\| of the file. The samples of the target can be at other times on each axis. | "error" |
| `gradient.slew.axis` | The same | Runs. The segment slopes use the times of the file, and a junction step is divided by the gradient raster of the file. | The slew of the waveform of the file. For `raster_4us_sequence` the step gives 60 T/m/s with the 4 µs raster of the file, and 24 T/m/s if the target plays it over its 10 µs raster. The value on the target depends on the interpreter. | "error" |
| `pns.safe` | The same | Runs. The SAFE model filters the waveform of the file, sampled at the gradient raster of the file. | The PNS of the waveform of the file. The PNS depends on the slew, so it has the same problem as `gradient.slew.axis`. | "error" |
| `timing.pypulseq` | All four, of the target (the `pp.Opts` of the read) | Runs. Fails an event time that is a field (a delay, a trapezoid time, a block duration, an ADC dwell) and is not on the raster of the target. Passes the samples and corners of a shaped gradient that are not on it. | Part of the answer: a pass does not show that the file plays on the target (section 4). | Open (section 6.1) |

`timing.rasters` is not in this table: it is the check that finds the
difference, and it stays the only result that reports it.

## 6. Open questions

### 6.1 `timing.pypulseq` when the rasters are different

`timing.pypulseq` is not a measurement of the waveform, so section 5.6 does
not decide it. Before its behaviour with different rasters can be decided, its
purpose must be clear.

**What the check says now.** Its specification
([`checks.md`](checks.md#timingpypulseq)) defines it by the procedure: the
value is the number of errors that `check_timing` of pypulseq gives for the
file, read with the `pp.Opts` of the target, and the check passes when there
is no error. The design (section 5.8 of
[`plans/pulseq-checks.md`](plans/pulseq-checks.md), "Rely on pypulseq") makes
it a thin wrapper: a check uses the rule of pypulseq when pypulseq has one. So
a pass says "pypulseq finds no timing error against the system of the target".
It does not say "the timing of the file works on the target": section 3 shows
that `check_timing` does not look at the times of shaped gradients.

**Three kinds of rule in one check.** The rules of `check_timing` are of three
kinds, and a difference of rasters changes only one of them:

| Kind | Rules | Depends on | With different rasters |
|---|---|---|---|
| Raster alignment | The block duration, the delay of each event, the rise, flat and fall times of a trapezoid, and the ADC dwell, each on its raster of the target | The rasters of the target | A failure is still a real problem on the target. A pass says nothing about the shapes. |
| Hardware timing | The RF dead time, the RF ringdown, the ADC dead time before and after the ADC | The dead times and the ringdown of the target, not its rasters | Each result is still true |
| File integrity | A negative delay, a stored block duration that is not the duration of the block content, the soft delays | The file only | Each result is still true |

Raster alignment is useful also when the rasters are equal: a file can declare
the raster of the target and still have a delay of 15 µs on a 10 µs gradient
raster.

**A proposal for the purpose.** The events of the file meet the timing rules
of the target: each time is on the raster of the target, each RF pulse and ADC
respects the dead times and the ringdown of the target, and the timing of the
file is consistent in itself.

With this purpose, the gap is clear: with different rasters the check cannot
assert the raster part for the shapes, but it can assert the other two parts.
Two ways to follow it:

1. **Divide the check** along the three kinds of the table. The raster
   alignment check gives "error" for a different raster, as the checks of
   section 5.6. The other two run as now.
2. **Keep one check**, and give "error" only for its raster part, with the
   results of the other two parts as findings.

Both ways depart from the "thin wrapper" principle of section 5.8, because the
check then divides the result of `check_timing`. That principle is a decision
to review together with this one.

**Other questions for the study:**

- Can a failure come only from the difference of the rasters, for example a
  block duration of the file in units of its own `BlockDurationRaster`?
- `checkTiming` of MATLAB also checks the time points of an RF shape, and
  pypulseq does not. Does the check need that rule?

### 6.2 A later rule that passes some unequal rasters

Section 5.1 is the rule of version 1, because nothing better is known now. A
file with other rasters is not necessarily wrong. An interpreter can play it
correctly, if it makes the samples on its own raster in a known way. The rule
of version 1 fails such a file only because the check cannot know the result.

A later version can pass some files with unequal rasters, for one interpreter
at a time, when the behaviour of that interpreter is known. Such a rule needs
these facts about the interpreter:

| Fact | Example of a question |
|---|---|
| Which pairs of rasters it accepts | Does it accept a file raster that is an integer multiple of its own raster (a coarser file)? A finer file? Any raster? Does it refuse the file, or play it? |
| How it makes its samples from the samples of the file | Does it hold each sample, interpolate linearly between the sample centres, or use another method? What does it do at the start and the end of a shape? |
| Which times must still be on its raster | Must the block durations, the event delays and the ADC dwell be on its rasters, as `check_timing` requires now? |
| Which version of the interpreter | Is the behaviour the same in each version? |

With these facts, the rule has two parts:

1. **`timing.rasters`** passes a pair of rasters that the interpreter
   accepts, and fails the other pairs as now.
2. **The measurements** (the waveform checks of section 5.6) measure the
   waveform that the interpreter plays: they resample the file in the same way
   as the interpreter, and measure the result with the raster of the target.
   Without this part, the values of the gradient checks and of `pns.safe`
   describe the file, not the scanner, and section 5.6 gives "error".

The target profile then must say which interpreter it has, so that the checks
use its rule. None of these facts are known now. The study is an item of
[`TODO.md`](../TODO.md). Until then, version 1 keeps the rule of section 5.1,
and section 5.6 says what the waveform checks give.
