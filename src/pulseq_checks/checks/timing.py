"""The timing checks (plan section 4.7): `RASTERS`, `timing.rasters`, the rasters that the
`.seq` file declares against the rasters of the target; and `PYPULSEQ`, `timing.pypulseq`,
`Sequence.check_timing` with the `Opts` of the target."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..profile import RASTER_OPTS
from ..results import Location, Result, State
from ..rules import CheckSpec, RunContext
from ..seq_index import block_cache_off, sequence_index

# The relative tolerance of a comparison of two rasters. pypulseq writes a definition with
# nine significant digits (`0.9g`), so the value in the file differs from the raster that the
# author used by 5e-9 at most; rasters that are different differ by far more (10 µs and
# 10.1 µs differ by 1e-2).
RASTER_REL_TOL = 1e-8

_RASTER_DEFINITIONS = tuple(RASTER_OPTS)
_RASTER_INPUTS = tuple(f"rasters.{name}" for name in _RASTER_DEFINITIONS)


def _declared_raster(definitions: dict[str, Any], name: str) -> float:
    """The raster `name` of `definitions`, in seconds. Raises `ValueError` when the file
    does not declare it, or declares a value that is not one positive finite number."""
    if name not in definitions:
        raise ValueError(f"the file does not declare {name}")
    value = definitions[name]
    if isinstance(value, np.ndarray) and value.size == 1:
        value = value.item()
    if not isinstance(value, int | float) or isinstance(value, bool):
        # `run` catches this `ValueError`, like the others (hence the noqa).
        raise ValueError(f"the file declares {name} as {value!r}, not as one number")  # noqa: TRY004
    if not (math.isfinite(value) and value > 0):
        raise ValueError(f"the file declares {name} as {value!r}, not as a positive number")
    return float(value)


def _deviation(declared: float, target: float) -> float:
    """`|F/T - 1|` for the raster `declared` (F) of the file and the raster `target` (T)."""
    return abs(declared / target - 1)


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
            "compares the rasters of the target with themselves and passes."
        ),
        cost="fast",
        pypulseq=None,
        url=None,
    )

    def run(self, ctx: RunContext) -> Result:
        definitions = ctx.sequence.definitions
        targets = ctx.profile.rasters
        problems: list[str] = []
        worst: tuple[float, float, float, str] | None = None  # (deviation, F, T, name)
        for name in _RASTER_DEFINITIONS:
            try:
                declared = _declared_raster(definitions, name)
            except ValueError as e:
                problems.append(str(e))
                continue
            target = targets[name]
            deviation = _deviation(declared, target)
            if worst is None or deviation > worst[0]:
                worst = (deviation, declared, target, name)
        if problems:
            return ctx.result(self.spec, State.ERROR, reason="; ".join(problems))
        assert worst is not None  # no problem, so each raster was compared
        state = State.PASS if worst[0] <= RASTER_REL_TOL else State.FAIL
        _, declared, target, name = worst
        detail = f"{name}: {declared!r} s in the file, {target!r} s on the target"
        return ctx.result(self.spec, state, value=declared, limit=target, unit="s", reason=detail)


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
            "block ID, and the start time of that block in seconds. check_timing does not "
            "change the sequence, except that it fills the block cache of the sequence "
            "object (a dictionary of the blocks that it read); this check turns the cache "
            "off, so that the other checks of the target see the same sequence, and a "
            "sequence of many blocks does not keep all its blocks in memory."
        ),
        cost="slow",
        pypulseq="Sequence.check_timing",
        url=None,
    )

    def run(self, ctx: RunContext) -> Result:
        seq = ctx.sequence
        with block_cache_off(seq):
            _, errors = seq.check_timing()
        if not errors:
            return ctx.result(self.spec, State.PASS, value=0.0, limit=0.0)
        index = ctx.measure("index", sequence_index)
        block = int(errors[0].block)
        position = int(np.flatnonzero(index.block_id == block)[0])
        location = Location(block=block, time_s=float(index.start_s[position]))
        first = errors[0]
        detail = (
            f"first of {len(errors)} errors: block {block}, {first.event}.{first.field}: "
            f"{first.error_type}"
        )
        return ctx.result(
            self.spec,
            State.FAIL,
            value=float(len(errors)),
            limit=0.0,
            location=location,
            reason=detail,
        )


RASTERS = _Rasters()
PYPULSEQ = _Pypulseq()
