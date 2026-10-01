"""The gradient check rules (plan section 4.7): `gradient.amplitude.axis`,
`gradient.slew.axis` and `gradient.amplitude.any-orientation`.

The three rules share one measurement, `gradient_limits` over the whole file, which
`ctx.measure` calculates one time for each target. `gradient_limits` uses its `limits`
argument only as a label of its result (the numbers do not depend on it), but the rules never
give it `None`, because then it would take the limits of `seq.system` (design section 7.2).
The limit of a rule comes from the `HardwareLimits` of the target, which `_hardware_limits`
builds for all three rules in one way."""

from __future__ import annotations

import math

from ..grad_limits import GradientLimits, HardwareLimits, gradient_limits
from ..results import Location, Result, State
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


def _measurement(ctx: RunContext) -> tuple[GradientLimits, HardwareLimits]:
    """The measurement of the whole file, calculated one time for each target, and the
    `HardwareLimits` of the target."""
    limits = _hardware_limits(ctx)
    return ctx.measure("gradient_limits", lambda seq: gradient_limits(seq, limits=limits)), limits


class _GradientCheck:
    """A gradient check: `spec`, its `unit`, the limit that it uses, and the candidates for
    its value. A subclass gives `_limit` and `_candidates`."""

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
        state = State.PASS if value <= limit * (1.0 + _LIMIT_TOLERANCE) else State.FAIL
        return ctx.result(
            self.spec,
            state,
            value=value,
            limit=limit,
            unit=self.unit,
            location=location,
            reason=detail,
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
            "mT/m with gamma = 42.576 MHz/T. "
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
            "peak of any axis is above it. " + _NO_GRADIENTS + " " + _ROTATION
        ),
        cost="fast",
        pypulseq=None,
        url=None,
    )
    unit = "mT/m"

    def _limit(self, limits: HardwareLimits) -> float:
        return limits.max_grad_mt_per_m

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
        version=2,
        title="Peak gradient slew rate of each logical axis",
        quantity=(
            "For each logical axis x, y and z, the peak slew rate in T/m/s: the largest of two "
            "kinds of value. (a) The slope of each straight segment of each gradient event, "
            "the change of the amplitude between two neighbouring corner points divided by "
            "the time between them (a segment shorter than 1 ns is not used). "
            + _SEGMENTS
            + " (b) The step at each block junction divided by the gradient raster time of the "
            "sequence: the absolute difference between the last amplitude of the gradient of "
            "the previous block and the first amplitude of the gradient of this block. A "
            "block with no gradient on the axis counts as 0, and so does the value before the "
            "first block. Part (b) finds the step where a gradient does not start or end at "
            "0, as with an extended trapezoid; pypulseq limits this step in add_block. The "
            "return to 0 after the last block is not a junction and is not counted. The slew "
            "is converted from Hz/m/s to T/m/s with gamma = 42.576 MHz/T. "
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
            "when the peak slew of any axis is above it. " + _NO_GRADIENTS + " " + _ROTATION
        ),
        cost="fast",
        pypulseq=None,
        url=None,
    )
    unit = "T/m/s"

    def _limit(self, limits: HardwareLimits) -> float:
        return limits.max_slew_t_per_m_per_s

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
            "at one of them. The amplitude is converted from Hz/m to mT/m with gamma = "
            "42.576 MHz/T. "
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
        ),
        cost="fast",
        pypulseq=None,
        url=None,
    )
    unit = "mT/m"

    def _limit(self, limits: HardwareLimits) -> float:
        return limits.max_grad_mt_per_m

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
