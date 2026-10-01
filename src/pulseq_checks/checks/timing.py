"""The timing checks (plan section 4.7): `RASTERS`, `timing.rasters`, the rasters that the
`.seq` file declares against the rasters of the target; and `PYPULSEQ`, `timing.pypulseq`,
`Sequence.check_timing` with the `Opts` of the target."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pulseq_analysis.seq_index import block_cache_off, sequence_index
from pypulseq.check_timing import error_messages

from ..profile import RASTER_OPTS
from ..results import Finding, Location, Result, State
from ..rules import CheckSpec, RunContext

# The relative tolerance of a comparison of two rasters. pypulseq writes a definition with
# nine significant digits (`0.9g`), so the value in the file differs from the raster that the
# author used by 5e-9 at most; rasters that are different differ by far more (10 µs and
# 10.1 µs differ by 1e-2).
RASTER_REL_TOL = 1e-8

_RASTER_DEFINITIONS = tuple(RASTER_OPTS)
_RASTER_INPUTS = tuple(f"rasters.{name}" for name in _RASTER_DEFINITIONS)


class _RasterProblem(ValueError):
    """A raster that the file does not declare (`code` RASTER_NOT_DECLARED), or declares as a
    value that is not one positive finite number (`code` RASTER_INVALID). `data` has the
    values of the problem for its finding: the declared value of RASTER_INVALID, as a float
    when it is one number, else as the `repr` text of the value."""

    def __init__(self, message: str, code: str, data: dict[str, str | float] | None = None):
        super().__init__(message)
        self.code = code
        self.data = data or {}


def _declared_raster(definitions: dict[str, Any], name: str) -> float:
    """The raster `name` of `definitions`, in seconds. Raises `_RasterProblem` (a
    `ValueError`) when the file does not declare it, or declares a value that is not one
    positive finite number."""
    if name not in definitions:
        raise _RasterProblem(f"the file does not declare {name}", "RASTER_NOT_DECLARED")
    value = definitions[name]
    if isinstance(value, np.ndarray) and value.size == 1:
        value = value.item()
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise _RasterProblem(
            f"the file declares {name} as {value!r}, not as one number",
            "RASTER_INVALID",
            {"declared": repr(value)},
        )
    if not (math.isfinite(value) and value > 0):
        raise _RasterProblem(
            f"the file declares {name} as {value!r}, not as a positive number",
            "RASTER_INVALID",
            {"declared": float(value)},
        )
    return float(value)


def _deviation(declared: float, target: float) -> float:
    """`|F/T - 1|` for the raster `declared` (F) of the file and the raster `target` (T)."""
    return abs(declared / target - 1)


def _mismatch_message(name: str, declared: float, target: float) -> str:
    """The text of a raster `declared` in the file against the raster `target`: the detail
    of a pass or a fail, and the message of a RASTER_MISMATCH finding."""
    return f"{name}: {declared!r} s in the file, {target!r} s on the target"


class _Rasters:
    spec = CheckSpec(
        id="timing.rasters",
        version=1,
        title="Rasters of the file against the rasters of the target",
        quantity=(
            "For each of the four rasters GradientRasterTime, RadiofrequencyRasterTime, "
            "AdcRasterTime and BlockDurationRaster: F, the raster that the [DEFINITIONS] "
            "section of the .seq file declares, in seconds, and T, the raster of the target "
            "(rasters.<name> of the target profile). The deviation of a raster is "
            "|F/T - 1|. The result value is the F of the raster with the largest deviation "
            "(the first in the order above for equal deviations), in seconds. The reason of "
            "the result names that raster, with F and T."
        ),
        inputs=_RASTER_INPUTS,
        models=(),
        limit=(
            "T of the raster of the result value, in seconds. The target profile gives it "
            "(rasters.<name>) and has no default."
        ),
        tolerance=(
            f"A relative tolerance of {RASTER_REL_TOL:g} on the deviation of each raster. "
            "pypulseq writes a definition with nine significant digits, so the value in the "
            "file differs from the raster that its author used by 5e-9 at most. Two "
            "different rasters differ by much more (10 us and 10.1 us differ by 1e-2)."
        ),
        pass_condition=(
            "Pass when each of the four rasters that the file declares equals the raster of "
            "the target: F = T within the tolerance, so the deviation of each raster is at "
            f"most {RASTER_REL_TOL:g}. Fail when a deviation is larger. Error when the "
            "file does not declare a raster, or declares a value that is not one positive "
            "finite number.\n\n"
            "Version 1 has no rule for rasters that are not equal. Whether a file with "
            "other rasters plays correctly on the target depends on how the interpreter "
            "resamples the shapes: the samples of a gradient or RF shape are values at the "
            "centers of the raster steps of the file (t_n = t_start + F (0.5 + n), by the "
            "Pulseq file specification), and the specification does not say how an "
            "interpreter reconstructs a shape between its samples. So the check does not "
            "pass a file whose rasters differ from the rasters of the target, for a finer "
            "raster or for a coarser one.\n\n"
            "A raster that the file does not declare is an error, not a fail: the "
            "specification requires the four definitions from format 1.4.0, and pypulseq "
            "1.5.0 writes them, but pypulseq uses the raster of the target for a missing "
            "definition, so the check has no value to compare. A file of a format older "
            "than 1.4.0 declares no raster, and pypulseq fills the four definitions with the "
            "rasters of the target when it reads the file. For such a file the check "
            "compares the rasters of the target with themselves and passes.\n\n"
            "The result also gives each raster with a problem as a finding (see Findings)."
        ),
        cost="fast",
        pypulseq=None,
        url=None,
        findings=(
            "One finding for each of the four rasters that has a problem, in the order "
            "GradientRasterTime, RadiofrequencyRasterTime, AdcRasterTime, "
            "BlockDurationRaster. A raster without a problem gives no finding. The code is "
            "RASTER_NOT_DECLARED when the file does not declare the raster; RASTER_INVALID "
            "when the file declares a value that is not one positive finite number; "
            "RASTER_MISMATCH when the file declares a valid raster whose deviation is above "
            'the tolerance. A "fail" result has one RASTER_MISMATCH finding for each raster '
            'that differs from the target. An "error" result lists every problem: the '
            "RASTER_NOT_DECLARED and RASTER_INVALID findings, and also a RASTER_MISMATCH "
            "finding for each raster that the file declares validly and that differs from the "
            "target. The location is none, because a raster is a definition of the whole "
            "file, not of a block. The data of each code have the key name (the name of the "
            "raster, a text: for example GradientRasterTime) and the key target_s (the raster "
            "of the target, in seconds). RASTER_INVALID has declared: a number in seconds when "
            "the value in the file is one number (also one that is not finite, zero or "
            "negative), else the Python repr text of the value in the file (for example of a "
            "list or a string). RASTER_MISMATCH has file_s (the raster of the file, in "
            "seconds) and deviation (|F/T - 1|, a ratio with no unit). The message of "
            "RASTER_NOT_DECLARED and RASTER_INVALID is the text of the problem, for example "
            '"the file does not declare GradientRasterTime"; the message of RASTER_MISMATCH '
            'is the name, a colon, the raster of the file in seconds, "s in the file", a '
            'comma, the raster of the target in seconds and "s on the target".'
        ),
    )

    def run(self, ctx: RunContext) -> Result:
        definitions = ctx.sequence.definitions
        targets = ctx.profile.rasters
        problems: list[str] = []
        findings: list[Finding] = []
        worst: tuple[float, float, float, str] | None = None  # (deviation, F, T, name)
        for name in _RASTER_DEFINITIONS:
            target = targets[name]
            try:
                declared = _declared_raster(definitions, name)
            except _RasterProblem as e:
                problems.append(str(e))
                findings.append(
                    Finding(
                        code=e.code,
                        message=str(e),
                        data={"name": name, **e.data, "target_s": target},
                    )
                )
                continue
            deviation = _deviation(declared, target)
            if worst is None or deviation > worst[0]:
                worst = (deviation, declared, target, name)
            if deviation > RASTER_REL_TOL:
                findings.append(
                    Finding(
                        code="RASTER_MISMATCH",
                        message=_mismatch_message(name, declared, target),
                        data={
                            "name": name,
                            "file_s": declared,
                            "target_s": target,
                            "deviation": deviation,
                        },
                    )
                )
        if problems:
            return ctx.result(
                self.spec, State.ERROR, reason="; ".join(problems), findings=tuple(findings)
            )
        assert worst is not None  # no problem, so each raster was compared
        state = State.PASS if worst[0] <= RASTER_REL_TOL else State.FAIL
        _, declared, target, name = worst
        return ctx.result(
            self.spec,
            state,
            value=declared,
            limit=target,
            unit="s",
            reason=_mismatch_message(name, declared, target),
            findings=tuple(findings),
        )


# The compiled message template of each error type. `format_string` of pypulseq compiles
# `f"""<template>"""` again for each error, which took 6.9 s for 4 x 10^5 errors; compiled one
# time for each type, the same texts took 0.5 s (plan check-findings, section 9.2).
_MESSAGE_CODE: dict[str, Any] = {}


def _finding_message(record: Any) -> str:
    """The message of the finding of one record of `check_timing`: the text that
    `print_error_report` of pypulseq makes for it (times in us, in ns for an ADC dwell),
    without the "- event.field: " prefix. It evaluates the template as `format_string` of
    pypulseq does. A type without a template, or a template that fails, gives
    "<event>.<field>: <error_type>"."""
    unit, multiplier = ("ns", 1e9) if getattr(record, "field", None) == "dwell" else ("us", 1e6)
    try:
        code = _MESSAGE_CODE.get(record.error_type)
        if code is None:
            template = error_messages[record.error_type]
            code = compile(f'f"""{template}"""', "<pypulseq error message>", "eval")
            _MESSAGE_CODE[record.error_type] = code
        # The code is a template of pypulseq, not text of the file; the record fields are
        # only its variables.
        return eval(code, {**vars(record), "unit": unit, "multiplier": multiplier})
    except Exception:  # noqa: BLE001 (the fallback text replaces a template that fails)
        event = getattr(record, "event", "?")
        field = getattr(record, "field", "?")
        return f"{event}.{field}: {getattr(record, 'error_type', '?')}"


def _finding_data(record: Any) -> dict[str, str | int | float | bool | None]:
    """The attributes of one record of `check_timing`, except `block` and `error_type`, as
    Python scalars (a NumPy scalar becomes the Python scalar of the same kind)."""
    return {
        name: value.item() if isinstance(value, np.generic) else value
        for name, value in vars(record).items()
        if name not in ("block", "error_type")
    }


class _Pypulseq:
    spec = CheckSpec(
        id="timing.pypulseq",
        version=1,
        title="Timing check of pypulseq with the system of the target",
        quantity=(
            "The number of timing errors that Sequence.check_timing of pypulseq reports for "
            "the sequence. The sequence is read with the Opts of the target, so "
            "check_timing compares the file with the rasters, the dead times and the "
            "ringdown of the target. check_timing gives one error for each violated "
            "condition of an event of a block: a time that is not an integer multiple of "
            "its raster (block duration and block event times against "
            "BlockDurationRaster, RadiofrequencyRasterTime and GradientRasterTime, ADC "
            "dwell against AdcRasterTime); a negative delay; an RF delay shorter than "
            "opts.rf_dead_time; an RF pulse that ends less than opts.rf_ringdown_time "
            "before the end of its block; an ADC delay shorter than opts.adc_dead_time; an "
            "ADC that ends less than opts.adc_dead_time before the end of its block; a "
            "stored block duration that is not the duration of the content of the block; "
            "and the conditions of soft delays. The result value is this number. The "
            "inputs are the values that check_timing reads from the system of the target: "
            "the four rasters, opts.rf_dead_time, opts.rf_ringdown_time and "
            "opts.adc_dead_time. They are necessary whether or not the sequence has an RF "
            "pulse or an ADC, so that a default value of pypulseq is never used."
        ),
        inputs=(
            *_RASTER_INPUTS,
            "opts.rf_dead_time",
            "opts.rf_ringdown_time",
            "opts.adc_dead_time",
        ),
        models=(),
        limit="0 timing errors. The target does not give a limit.",
        tolerance=(
            "The tolerance of check_timing, which this check does not change: a time is on a "
            "raster when its ratio to the raster is within 1e-6 of an integer; dead times, "
            "ringdown and block durations are compared with a tolerance of 1e-9 s "
            "(pypulseq.eps)."
        ),
        pass_condition=(
            "Pass when check_timing gives no error. Fail when it gives one or more errors. "
            "The result location is the first error in the play order of the blocks: its "
            "block ID, and the start time of that block in seconds. The result also gives each "
            "error as a finding (see Findings). check_timing does not change the sequence, "
            "except that it fills the block cache of the sequence "
            "object (a dictionary of the blocks that it read); this check turns the cache "
            "off, so that the other checks of the target see the same sequence, and a "
            "sequence of many blocks does not keep all its blocks in memory."
        ),
        cost="slow",
        pypulseq="Sequence.check_timing",
        url=None,
        findings=(
            "One finding for each error that check_timing gives, in the order of "
            "check_timing (the play order of the blocks). The code is the error type of "
            "check_timing: RASTER, BLOCK_DURATION_MISMATCH, NEGATIVE_DELAY, RF_DEAD_TIME, "
            "RF_RINGDOWN_TIME, ADC_DEAD_TIME, POST_ADC_DEAD_TIME, SOFT_DELAY_FACTOR or "
            "SOFT_DELAY_DUR_INCONSISTENCY. pypulseq also has a message template for "
            "SOFT_DELAY_HINT_INCONSISTENCY and SOFT_DELAY_INVALID_NUMID, but the pinned "
            "check_timing does not give these two types. The location is the block of the "
            "error (its block ID) and the start time of that block, in seconds. The data are "
            "the fields of the error record of check_timing, except the block and the type: "
            "event and field (the names of the event and of the value in the block), value, "
            "and the other fields of the type. All times are in seconds, except the factor "
            "of SOFT_DELAY_FACTOR (its value), the hint and the numeric ID of the soft delay "
            "types, and the name of the raster of RASTER (a text: for example "
            "rf_raster_time). The "
            "other fields are value_rounded and error (RASTER), duration (RF_RINGDOWN_TIME, "
            "BLOCK_DURATION_MISMATCH and POST_ADC_DEAD_TIME), dead_time (RF_DEAD_TIME, "
            "ADC_DEAD_TIME and POST_ADC_DEAD_TIME), ringdown_time (RF_RINGDOWN_TIME), and "
            "hint and numID (the two soft delay types). The message is the text of the error "
            "report of pypulseq for the error, with times in us, and in ns for an ADC dwell, "
            "without the prefix of the event and the field. For an error type without a "
            "template, or when the template fails, the message is the event, a point, the "
            "field, a colon and the error type."
        ),
    )

    def run(self, ctx: RunContext) -> Result:
        seq = ctx.sequence
        with block_cache_off(seq):
            _, errors = seq.check_timing()
        if not errors:
            return ctx.result(self.spec, State.PASS, value=0.0, limit=0.0)
        index = ctx.measure("index", sequence_index)
        # One map for all errors: a sequence of 10^6 blocks can give 4 x 10^5 errors.
        starts = dict(zip(index.block_id.tolist(), index.start_s.tolist(), strict=True))
        findings = tuple(
            Finding(
                code=record.error_type,
                message=_finding_message(record),
                location=Location(block=int(record.block), time_s=starts[int(record.block)]),
                data=_finding_data(record),
            )
            for record in errors
        )
        first = errors[0]
        detail = (
            f"first of {len(errors)} errors: block {int(first.block)}, {first.event}.{first.field}: "
            f"{first.error_type}"
        )
        return ctx.result(
            self.spec,
            State.FAIL,
            value=float(len(errors)),
            limit=0.0,
            location=findings[0].location,
            reason=detail,
            findings=findings,
        )


RASTERS = _Rasters()
PYPULSEQ = _Pypulseq()
