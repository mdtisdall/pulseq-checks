"""The gradient check rules (plan section 4.7): `gradient.amplitude.axis`,
`gradient.slew.axis` and `gradient.amplitude.any-orientation`.

The three rules share one measurement, `gradient_limits` over the whole file, which
`ctx.measure` calculates one time for each target. `gradient_limits` uses its `limits`
argument only as a label of its result (the numbers do not depend on it), but the rules never
give it `None`, because then it would take the limits of `seq.system` (design section 7.2).
The limit of a rule comes from the `HardwareLimits` of the target, which `_hardware_limits`
builds for all three rules in one way.

A rule that fails also gives each block that is above its limit as a finding. The values of
each block come from a second measurement, `gradient_blocks` (`block_gradient_values`), which
`ctx.measure` calculates one time for each target too, and only when a rule fails."""

from __future__ import annotations

import math

import numpy as np

from ..grad_limits import (
    BlockGradientValues,
    GradientLimits,
    HardwareLimits,
    block_gradient_values,
    gradient_limits,
)
from ..results import Finding, Location, Result, State
from ..rules import CheckSpec, RunContext

# The rule of the gradient limits card of pulseq-reports (fact 8 of the plan): a value passes
# when value <= limit * (1 + _LIMIT_TOLERANCE).
_LIMIT_TOLERANCE = 1e-9
_AXES = ("x", "y", "z")

_TOLERANCE = (
    "Relative, 1e-9: a value passes when value <= limit * (1 + 1e-9). This absorbs only the "
    "rounding of floating-point arithmetic in the conversion of the units (a sequence that is "
    "built exactly at the limit passes). It is far below any change that a sequence author "
    "makes. It is the tolerance of the gradient limits card of pulseq-reports."
)
_NO_GRADIENTS = (
    "A sequence with no gradient event passes with the value 0.0 and no location: nothing "
    "can be above the limit."
)
_ROTATION = (
    "A file that uses the Pulseq rotation extension is an error of the check, not a pass or a "
    "fail: the gradient events of the file are not the gradients on the scanner, and the "
    "measurement refuses such a file."
)
_SEGMENTS = (
    "A gradient event is piecewise linear between its corner points (the corners of a "
    "trapezoid; the first point, the samples and the last point of an arbitrary or an "
    "extended gradient)."
)
_WHOLE_FILE = "The check covers the whole file, not windows of it."
_LOGICAL_AXES = (
    "The axes are the logical axes of the sequence, not the physical gradient axes of a scanner."
)
_GAMMA = (
    "The value is converted with the gamma of the target (opts.gamma, or 42.576 MHz/T, the "
    "value of pypulseq, when the profile does not give it), or with the gamma of seq.system "
    "when the limits come from the sequence object. The limit uses the same gamma, so the "
    "value and the limit are in the same units."
)
_FINDINGS_SENTENCE = "The result also gives each block above the limit as a finding (see Findings)."
_FINDINGS_FOR_FAIL = (
    "The findings are calculated only for a fail: a pass gives no finding. A block is above "
    "the limit by the rule of the state: its value is above limit * (1 + 1e-9). Thus the "
    "largest value of the findings is the value of the result."
)
_RASTERS = ("GradientRasterTime", "BlockDurationRaster")
_NOT_EVALUATED_RASTERS = (
    'The check is "not evaluated" when the file does not declare GradientRasterTime or '
    "BlockDurationRaster and the target does not give that raster (rasters.GradientRasterTime "
    "or rasters.BlockDurationRaster). The check does not use a default of pypulseq for a raster."
)


def _hardware_limits(ctx: RunContext) -> HardwareLimits:
    """The `HardwareLimits` that all three rules use for the target of `ctx`:
    `ctx.hardware_limits` when it is not None (both limits of the profile, or the limits of
    `seq.system` with the opt-in of decision 4). Otherwise the target gives only one of
    `opts.max_grad` and `opts.max_slew` (the run function gives "not evaluated" to a rule
    that needs the other one), and the other limit is nan. `opts.max_slew` is given also by
    `opts.max_grad` with `opts.rise_time` (`TargetProfile.has_value`), and then the Opts has
    max_grad / rise_time in `max_slew`. The label is the name of the
    target."""
    if ctx.hardware_limits is not None:
        return ctx.hardware_limits
    # The conversion of `profile.read_profile`: pp.Opts stores max_grad in Hz/m and max_slew
    # in Hz/m/s, whatever unit the profile gives.
    opts = ctx.profile.make_opts()
    max_grad, max_slew = math.nan, math.nan
    if ctx.profile.has_value("opts.max_grad"):
        max_grad = opts.max_grad / opts.gamma * 1e3
    if ctx.profile.has_value("opts.max_slew"):
        max_slew = opts.max_slew / opts.gamma
    return HardwareLimits(
        max_grad_mt_per_m=max_grad, max_slew_t_per_m_per_s=max_slew, label=ctx.profile.name
    )


def _gamma(ctx: RunContext) -> float:
    """The gamma, in Hz/T, of the measurements of the target of `ctx`: the same gamma as the
    limits of `_hardware_limits`, so that value and limit are in the same units."""
    if ctx.limits_source == "sequence object":
        return ctx.sequence.system.gamma
    return ctx.profile.make_opts().gamma


def _measurement(ctx: RunContext) -> tuple[GradientLimits, HardwareLimits]:
    """The measurement of the whole file, calculated one time for each target, and the
    `HardwareLimits` of the target."""
    limits = _hardware_limits(ctx)
    gamma = _gamma(ctx)
    measurement = ctx.measure(
        "gradient_limits", lambda seq: gradient_limits(seq, limits=limits, gamma=gamma)
    )
    return measurement, limits


def _above_limit(value, limit: float):
    """True where `value` (a number, or an array of them) is above `limit` by the rule of the
    state of a check: not `value <= limit * (1 + _LIMIT_TOLERANCE)`. A value that is not a
    number is above the limit, so it fails, as before the findings."""
    return np.logical_not(value <= limit * (1.0 + _LIMIT_TOLERANCE))


def _entries_above_limit(
    blocks: BlockGradientValues,
    limit: float,
    columns: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[list[int], list[int], list[float], list[float]]:
    """The entries above `limit` of the (values, times) arrays in `columns` (one entry for each
    block in each array, in play order), in the play order of the blocks, and in the order of
    `columns` within one block. Returns the lists, with one item for each entry above the limit,
    of the index of its column, its block ID, its value and its time in seconds, as Python
    numbers."""
    plays, ranks, values, times = [], [], [], []
    for rank, (column_values, column_times) in enumerate(columns):
        play = np.flatnonzero(_above_limit(column_values, limit))
        plays.append(play)
        ranks.append(np.full(play.size, rank))
        values.append(column_values[play])
        times.append(column_times[play])
    play, rank = np.concatenate(plays), np.concatenate(ranks)
    # The last key of lexsort is the main key.
    order = np.lexsort((rank, play))
    return (
        rank[order].tolist(),
        blocks.block_id[play[order]].tolist(),
        np.concatenate(values)[order].tolist(),
        np.concatenate(times)[order].tolist(),
    )


class _GradientCheck:
    """A gradient check: `spec`, its `unit`, the limit that it uses, the candidates for its
    value, and its findings. A subclass gives `_limit`, `_candidates` and `_findings`."""

    spec: CheckSpec
    unit: str

    def _limit(self, limits: HardwareLimits) -> float:
        raise NotImplementedError

    def _candidates(
        self, measured: GradientLimits
    ) -> list[tuple[float, int | None, float, str | None]]:
        """The (value, block ID, time in seconds, detail) of each quantity that the check
        compares with its limit, in the order of the tie rule. The detail (for example
        "axis y") is the `reason` of a pass or a fail: which quantity gave the value."""
        raise NotImplementedError

    def _findings(self, blocks: BlockGradientValues, limit: float) -> tuple[Finding, ...]:
        """One finding for each block (and axis) of `blocks` that is above `limit`, in the
        order of the spec."""
        raise NotImplementedError

    def run(self, ctx: RunContext) -> Result:
        measured, limits = _measurement(ctx)
        limit = self._limit(limits)
        if measured.reason is not None:
            return ctx.result(
                self.spec, State.PASS, value=0.0, limit=limit, unit=self.unit, location=None
            )
        # The limit is one number for all candidates, so the candidate with the largest ratio
        # to the limit is the largest one. The first largest one wins a tie.
        candidates = self._candidates(measured)
        value, block, time_s, detail = candidates[0]
        for candidate in candidates[1:]:
            if candidate[0] > value:
                value, block, time_s, detail = candidate
        location = Location(block=block, time_s=time_s) if value > 0.0 else None
        state = State.FAIL if _above_limit(value, limit) else State.PASS
        findings: tuple[Finding, ...] = ()
        if state is State.FAIL:
            gamma = _gamma(ctx)
            blocks = ctx.measure(
                "gradient_blocks", lambda seq: block_gradient_values(seq, gamma=gamma)
            )
            findings = self._findings(blocks, limit)
        return ctx.result(
            self.spec,
            state,
            value=value,
            limit=limit,
            unit=self.unit,
            location=location,
            reason=detail,
            findings=findings,
        )


class _AmplitudeAxis(_GradientCheck):
    spec = CheckSpec(
        id="gradient.amplitude.axis",
        version=1,
        title="Peak gradient amplitude of each logical axis",
        quantity=(
            "For each logical axis x, y and z, the peak amplitude in mT/m: the largest "
            "absolute amplitude of any gradient event on that axis. "
            + _SEGMENTS
            + " The maximum is at a corner point. The amplitude is converted from Hz/m to "
            "mT/m. "
            + _GAMMA
            + " "
            + _WHOLE_FILE
            + " "
            + _LOGICAL_AXES
            + " The value of the result is the peak of the axis with the largest ratio of its "
            "peak to the limit. The limit is one number for all axes, so this is the axis "
            "with the largest peak (the first of x, y, z when two axes have the same peak). "
            "Its location is the block ID and the time, in seconds from the start of the "
            "sequence, of the first point where that peak is reached."
        ),
        inputs=("opts.max_grad",),
        models=(),
        limit=(
            "opts.max_grad of the target profile, in mT/m (converted from the unit of the "
            "profile with the gamma of its Opts). The same limit applies to each axis."
        ),
        tolerance=_TOLERANCE,
        pass_condition=(
            "Pass when the peak of each axis is at or below limit * (1 + 1e-9). Fail when the "
            "peak of any axis is above it. "
            + _NO_GRADIENTS
            + " "
            + _ROTATION
            + " "
            + _NOT_EVALUATED_RASTERS
            + " "
            + _FINDINGS_SENTENCE
        ),
        cost="fast",
        pypulseq=None,
        url=None,
        findings=(
            "One finding for each block and axis where the peak amplitude of the axis in that "
            "block is above the limit. A block that is above the limit on two axes gives two "
            "findings. The findings are in the play order of the blocks, then in the order of "
            "the axes x, y, z. The code is AMPLITUDE_ABOVE_LIMIT. The location is the block ID "
            "and the time, in seconds from the start of the sequence, of the first point where "
            "the peak of that axis is reached in that block. The data are axis (x, y or z, a "
            "text), value_mt_per_m (the peak amplitude of the axis in the block, in mT/m) and "
            "limit_mt_per_m (the limit, in mT/m). The message is the axis, the value and the "
            'limit, with up to 4 significant digits, for example "axis y: 103.2 mT/m, limit 80 '
            'mT/m". ' + _FINDINGS_FOR_FAIL
        ),
        rasters=_RASTERS,
    )
    unit = "mT/m"

    def _limit(self, limits: HardwareLimits) -> float:
        return limits.max_grad_mt_per_m

    def _findings(self, blocks: BlockGradientValues, limit: float) -> tuple[Finding, ...]:
        columns = [(blocks.peak_mt_per_m[a], blocks.peak_time_s[a]) for a in _AXES]
        axes, block_ids, values, times = _entries_above_limit(blocks, limit, columns)
        return tuple(
            Finding(
                code="AMPLITUDE_ABOVE_LIMIT",
                message=f"axis {_AXES[axis]}: {value:.4g} mT/m, limit {limit:.4g} mT/m",
                location=Location(block=block, time_s=time_s),
                data={
                    "axis": _AXES[axis],
                    "value_mt_per_m": value,
                    "limit_mt_per_m": limit,
                },
            )
            for axis, block, value, time_s in zip(axes, block_ids, values, times, strict=True)
        )

    def _candidates(
        self, measured: GradientLimits
    ) -> list[tuple[float, int | None, float, str | None]]:
        axes = measured.axes
        return [
            (axes[a].peak_mt_per_m, axes[a].peak_block, axes[a].peak_time_s, f"axis {a}")
            for a in _AXES
        ]


class _SlewAxis(_GradientCheck):
    spec = CheckSpec(
        id="gradient.slew.axis",
        version=1,
        title="Peak gradient slew rate of each logical axis",
        quantity=(
            "For each logical axis x, y and z, the peak slew rate in T/m/s: the largest of two "
            "kinds of value. (a) The slope of each straight segment of each gradient event, "
            "the change of the amplitude between two neighbouring corner points divided by "
            "the time between them (a segment shorter than 1 ns is not used). "
            + _SEGMENTS
            + " (b) The step at each block junction divided by the gradient raster time of the "
            "sequence (the GradientRasterTime that the file declares): the absolute difference "
            "between the last amplitude of the gradient of the previous block and the first "
            "amplitude of the gradient of this block. A "
            "block with no gradient on the axis counts as 0, and so does the value before the "
            "first block. Part (b) finds the step where a gradient does not start or end at "
            "0, as with an extended trapezoid; pypulseq limits this step in add_block. A "
            "difference between the raster of the file and the raster of the target is the "
            "subject of timing.rasters. The "
            "return to 0 after the last block is not a junction and is not counted. The slew "
            "is converted from Hz/m/s to T/m/s. "
            + _GAMMA
            + " "
            + _WHOLE_FILE
            + " "
            + _LOGICAL_AXES
            + " The value of the result is the peak slew of the axis with the largest ratio "
            "of its peak slew to the limit. The limit is one number for all axes, so this is "
            "the axis with the largest peak slew (the first of x, y, z on a tie). Its "
            "location is the block ID and the time, in seconds from the start of the "
            "sequence, of the start of the steepest segment, or of the junction for a junction "
            "step (the block ID is then the block after the junction)."
        ),
        inputs=("opts.max_slew",),
        models=(),
        limit=(
            "opts.max_slew of the target profile, in T/m/s (converted from the unit of the "
            "profile with the gamma of its Opts). A profile that gives opts.max_grad and "
            "opts.rise_time in place of opts.max_slew gives the slew limit max_grad / "
            "rise_time, the value that pp.Opts calculates. The same limit applies to each axis."
        ),
        tolerance=_TOLERANCE,
        pass_condition=(
            "Pass when the peak slew of each axis is at or below limit * (1 + 1e-9). Fail "
            "when the peak slew of any axis is above it. "
            + _NO_GRADIENTS
            + " "
            + _ROTATION
            + " "
            + _NOT_EVALUATED_RASTERS
            + " "
            + _FINDINGS_SENTENCE
        ),
        cost="fast",
        pypulseq=None,
        url=None,
        findings=(
            "One finding for each block and axis where the slew of a straight segment of the "
            "gradient event of that block, or the step at the start of the block, is above the "
            "limit. A segment and a step are two findings, also when they are in the same block "
            "and on the same axis. The findings are in the play order of the blocks, then in "
            "the order of the axes x, y, z, then the step before the segment, because the step "
            "is at the start of the block. The code is SLEW_ABOVE_LIMIT for a segment, and "
            "JUNCTION_SLEW_ABOVE_LIMIT for a step. For a segment, the finding is for the "
            "steepest segment of the event of the axis in the block (the first one of equal "
            "slew), and its location is the block ID and the start time of that segment, in "
            "seconds from the start of the sequence. For a step, the location is the block "
            "after the junction (its block ID) and the start time of that block. The data of "
            "both codes are axis (x, y or z, a text), value_t_per_m_per_s (the slew of the "
            "segment, or the step divided by the gradient raster time, in T/m/s) and "
            "limit_t_per_m_per_s (the limit, in T/m/s). The message of SLEW_ABOVE_LIMIT is "
            '"axis", the axis, a colon, "segment slew", the value and "T/m/s", a comma, "limit" '
            'and the limit and "T/m/s", for example "axis y: segment slew 103.2 T/m/s, limit '
            '80 T/m/s". The message of JUNCTION_SLEW_ABOVE_LIMIT has "step at the block start" '
            'in place of "segment slew", for example "axis y: step at the block start 103.2 '
            'T/m/s, limit 80 T/m/s". The values have up to 4 significant digits. '
            + _FINDINGS_FOR_FAIL
        ),
        rasters=_RASTERS,
    )
    unit = "T/m/s"

    def _limit(self, limits: HardwareLimits) -> float:
        return limits.max_slew_t_per_m_per_s

    def _findings(self, blocks: BlockGradientValues, limit: float) -> tuple[Finding, ...]:
        # The order of the columns is the order within a block: for each axis, the junction
        # (at the start of the block) and then the segment.
        columns = []
        for a in _AXES:
            columns.append((blocks.junction_t_per_m_per_s[a], blocks.start_s))
            columns.append((blocks.slew_t_per_m_per_s[a], blocks.slew_time_s[a]))
        ranks, block_ids, values, times = _entries_above_limit(blocks, limit, columns)
        findings = []
        for rank, block, value, time_s in zip(ranks, block_ids, values, times, strict=True):
            axis = _AXES[rank // 2]
            if rank % 2 == 0:
                code = "JUNCTION_SLEW_ABOVE_LIMIT"
                what = "step at the block start"
            else:
                code = "SLEW_ABOVE_LIMIT"
                what = "segment slew"
            findings.append(
                Finding(
                    code=code,
                    message=f"axis {axis}: {what} {value:.4g} T/m/s, limit {limit:.4g} T/m/s",
                    location=Location(block=block, time_s=time_s),
                    data={
                        "axis": axis,
                        "value_t_per_m_per_s": value,
                        "limit_t_per_m_per_s": limit,
                    },
                )
            )
        return tuple(findings)

    def _candidates(
        self, measured: GradientLimits
    ) -> list[tuple[float, int | None, float, str | None]]:
        axes = measured.axes
        return [
            (axes[a].max_slew_t_per_m_per_s, axes[a].slew_block, axes[a].slew_time_s, f"axis {a}")
            for a in _AXES
        ]


class _AmplitudeAnyOrientation(_GradientCheck):
    spec = CheckSpec(
        id="gradient.amplitude.any-orientation",
        version=1,
        title="Peak gradient amplitude under any orientation",
        quantity=(
            "The peak of |G| = sqrt(Gx^2 + Gy^2 + Gz^2) in mT/m over the file: the largest "
            "magnitude of the gradient vector of the three logical axes at the same time. "
            + _SEGMENTS
            + " |G| is convex between the corner points of the three axes, so the maximum is "
            "at one of them. The amplitude is converted from Hz/m to mT/m. "
            + _GAMMA
            + " "
            + _WHOLE_FILE
            + " A scanner rotates the logical axes onto its physical axes for the orientation "
            "of the scan. The amplitude on a physical axis is at most |G| at each time, and "
            "it is equal to |G| when that axis points along the gradient vector. Thus |G| is "
            "the worst case of the amplitude on a physical axis under any rotation of the "
            "logical axes (decision 11 of the design). This check does not know the "
            "orientation of the scan, and it uses the one amplitude limit for each physical "
            "axis. Its location is the block ID and the time, in seconds from the start of "
            "the sequence, of the first point where the peak of |G| is reached."
        ),
        inputs=("opts.max_grad",),
        models=(),
        limit=(
            "opts.max_grad of the target profile, in mT/m (converted from the unit of the "
            "profile with the gamma of its Opts), for each physical axis."
        ),
        tolerance=_TOLERANCE,
        pass_condition=(
            "Pass when the peak of |G| is at or below limit * (1 + 1e-9): then no orientation "
            "of the scan can give an amplitude above the limit on a physical axis. Fail when "
            "the peak of |G| is above it: an orientation exists that gives an amplitude above "
            "the limit, but the orientation of the real scan can be a different one. "
            + _NO_GRADIENTS
            + " "
            + _ROTATION
            + " "
            + _NOT_EVALUATED_RASTERS
            + " "
            + _FINDINGS_SENTENCE
        ),
        cost="fast",
        pypulseq=None,
        url=None,
        findings=(
            "One finding for each block where the peak of |G| in that block is above the "
            "limit, in the play order of the blocks. The code is VECTOR_AMPLITUDE_ABOVE_LIMIT. "
            "The location is the block ID and the time, in seconds from the start of the "
            "sequence, of the first point in the block where the peak of |G| is reached. The "
            "data are value_mt_per_m (the peak of |G| in the block, in mT/m) and "
            "limit_mt_per_m (the limit, in mT/m). The message is |G|, the value and the limit, "
            'with up to 4 significant digits, for example "|G| 103.2 mT/m, limit 80 mT/m". '
            + _FINDINGS_FOR_FAIL
        ),
        rasters=_RASTERS,
    )
    unit = "mT/m"

    def _limit(self, limits: HardwareLimits) -> float:
        return limits.max_grad_mt_per_m

    def _findings(self, blocks: BlockGradientValues, limit: float) -> tuple[Finding, ...]:
        _, block_ids, values, times = _entries_above_limit(
            blocks, limit, [(blocks.vector_peak_mt_per_m, blocks.vector_peak_time_s)]
        )
        return tuple(
            Finding(
                code="VECTOR_AMPLITUDE_ABOVE_LIMIT",
                message=f"|G| {value:.4g} mT/m, limit {limit:.4g} mT/m",
                location=Location(block=block, time_s=time_s),
                data={"value_mt_per_m": value, "limit_mt_per_m": limit},
            )
            for block, value, time_s in zip(block_ids, values, times, strict=True)
        )

    def _candidates(
        self, measured: GradientLimits
    ) -> list[tuple[float, int | None, float, str | None]]:
        return [
            (
                measured.vector_peak_mt_per_m,
                measured.vector_peak_block,
                measured.vector_peak_time_s,
                None,
            )
        ]


AMPLITUDE_AXIS = _AmplitudeAxis()
SLEW_AXIS = _SlewAxis()
AMPLITUDE_ANY_ORIENTATION = _AmplitudeAnyOrientation()
