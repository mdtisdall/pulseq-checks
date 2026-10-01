import math
from dataclasses import dataclass, replace
from typing import Any

import pypulseq as pp
import pytest
from pypulseq.event_lib import EventLibrary
from synthetic import (
    RASTER_4US_JUNCTION,
    RASTER_4US_JUNCTION_TIME,
    SYSTEM,
    empty_sequence,
    raster_4us_sequence,
)

from pulseq_checks import registry
from pulseq_checks.checks import gradient as gradient_module
from pulseq_checks.checks.gradient import (
    AMPLITUDE_ANY_ORIENTATION,
    AMPLITUDE_AXIS,
    SLEW_AXIS,
)
from pulseq_checks.grad_limits import AxisResult, GradientLimits, HardwareLimits
from pulseq_checks.profile import TargetProfile
from pulseq_checks.results import Location, State
from pulseq_checks.rules import CheckSpec, RunContext
from pulseq_checks.run import run_checks
from pulseq_checks.seq_utils import GAMMA

CHECKS = (AMPLITUDE_AXIS, SLEW_AXIS, AMPLITUDE_ANY_ORIENTATION)
# The sequences use a system with larger limits than the profiles, so that a sequence can be
# above the limit of a profile.
BIG = pp.Opts(max_grad=100, grad_unit="mT/m", max_slew=1000, slew_unit="T/m/s")
RISE = 100e-6  # s
FLAT = 300e-6  # s
TRAPEZOID = 2 * RISE + FLAT  # s, the duration of trap()
DELAY = 1e-3  # s
# A limit that no sequence of these tests reaches, for the limit that a test does not use.
FAR = 1e6
GAMMA_40 = 40e6  # Hz/T, a gamma that is not the 42.576 MHz/T of pypulseq


def trap(axis: str, amplitude_mt_per_m: float, system: pp.Opts = BIG):
    """A trapezoid of the given amplitude, with the rise time RISE: its slew rate is
    amplitude_mt_per_m * 1e-3 / RISE = 10 * amplitude_mt_per_m T/m/s."""
    return pp.make_trapezoid(
        channel=axis,
        amplitude=amplitude_mt_per_m * 1e-3 * GAMMA,
        rise_time=RISE,
        flat_time=FLAT,
        system=system,
    )


def build(*blocks, system: pp.Opts = BIG) -> pp.Sequence:
    """A sequence with one block for each tuple of events in `blocks`."""
    seq = pp.Sequence(system)
    for events in blocks:
        seq.add_block(*events)
    return seq


def peak_sequence() -> pp.Sequence:
    """Block 1: x at 5 mT/m. Block 2: a delay. Block 3: x at 20 mT/m (200 T/m/s)."""
    return build((trap("x", 5),), (pp.make_delay(DELAY),), (trap("x", 20),))


def vector_sequence() -> pp.Sequence:
    """Block 1: x at 5 mT/m. Block 2: a delay. Block 3: x and y at 12 mT/m at the same time
    (|G| = 12 * sqrt(2) mT/m)."""
    return build((trap("x", 5),), (pp.make_delay(DELAY),), (trap("x", 12), trap("y", 12)))


def make_profile(
    max_grad: float | None = None, max_slew: float | None = None, name: str = "t", **opts
) -> TargetProfile:
    """A target with the given limits (mT/m and T/m/s) and other `opts` keywords. The
    hardware limits are there when both limits are."""
    values: dict[str, Any] = dict(opts)
    if max_grad is not None:
        values.update(max_grad=max_grad, grad_unit="mT/m")
    if max_slew is not None:
        values.update(max_slew=max_slew, slew_unit="T/m/s")
    limits = None
    if max_grad is not None and max_slew is not None:
        limits = HardwareLimits(max_grad, max_slew, name)
    return TargetProfile(
        name=name,
        vendor=None,
        format_version=1,
        source_path=None,
        opts=values or None,
        hardware_limits=limits,
        rasters=None,
        models={},
        acoustic_resonances=None,
        sources={f"opts.{key}": "profile" for key in values},
        unused_sections=(),
    )


def run_one(check, seq: pp.Sequence, profile: TargetProfile):
    """The result of `check` for `seq` and `profile`, with no run function."""
    return check.run(RunContext(seq, profile, hardware_limits=profile.hardware_limits))


def install(monkeypatch, *rules):
    """Make `registry.check_rules` give `rules`, by ID (the other checks of the package are
    not needed here)."""
    monkeypatch.setattr(registry, "check_rules", lambda: {r.spec.id: r for r in rules})


def spy_on_gradient_limits(monkeypatch) -> list[dict]:
    """Replace `gradient_limits` in the check module with a function that calls the real one
    and keeps the keyword arguments of each call; returns that list."""
    calls: list[dict] = []
    real = gradient_module.gradient_limits

    def spy(seq, **kwargs):
        calls.append(kwargs)
        return real(seq, **kwargs)

    monkeypatch.setattr(gradient_module, "gradient_limits", spy)
    return calls


@dataclass(frozen=True)
class Case:
    """One check with a sequence whose value, location and limit the test knows by hand.
    `key` is the profile limit that the check uses, `per_mt` the limit that is
    `per_mt * x` for an amplitude limit of x mT/m (the slew of a trapezoid of x mT/m is
    `10 * x` T/m/s), `block` and `time_s` the location of the value."""

    check: Any
    key: str
    make_sequence: Any
    value: float
    unit: str
    per_mt: float
    block: int
    time_s: float


# In block 3 of peak_sequence, the peak amplitude is first reached when the rise ends, and the
# peak slew starts with the rise. The block starts after block 1 and the delay.
_BLOCK_3 = TRAPEZOID + DELAY
CASES = [
    Case(AMPLITUDE_AXIS, "max_grad", peak_sequence, 20.0, "mT/m", 1.0, 3, _BLOCK_3 + RISE),
    Case(SLEW_AXIS, "max_slew", peak_sequence, 200.0, "T/m/s", 10.0, 3, _BLOCK_3),
    Case(
        AMPLITUDE_ANY_ORIENTATION,
        "max_grad",
        vector_sequence,
        12 * math.sqrt(2),
        "mT/m",
        1.0,
        3,
        _BLOCK_3 + RISE,
    ),
]
CASE_IDS = [case.check.spec.id for case in CASES]


def detail(case):
    """The `reason` of a pass or a fail of `case`: the axis for the axis checks (each case
    sequence has its peak on x), none for |G|."""
    return None if case.check is AMPLITUDE_ANY_ORIENTATION else "axis x"


def profile_for(case: Case, limit: float) -> TargetProfile:
    """A target with `limit` for the limit that `case` uses and FAR for the other."""
    return make_profile(**{"max_grad": FAR, "max_slew": FAR, case.key: limit})


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_below_the_limit_passes_with_the_value_the_limit_and_the_unit(case):
    profile = profile_for(case, 2 * case.value)

    result = run_one(case.check, case.make_sequence(), profile)

    assert result.state is State.PASS
    assert result.value == pytest.approx(case.value)
    assert result.limit == 2 * case.value
    assert result.unit == case.unit
    assert result.reason == detail(case)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_a_value_equal_to_the_limit_passes(case):
    # The value of a check is the value of its own measurement, so the test takes the limit
    # from the first result: an exact equality that hand arithmetic could miss by a rounding.
    value = run_one(case.check, case.make_sequence(), profile_for(case, FAR)).value

    result = run_one(case.check, case.make_sequence(), profile_for(case, value))

    assert result.value == result.limit == value
    assert result.state is State.PASS


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_a_value_within_the_tolerance_above_the_limit_passes(case):
    value = run_one(case.check, case.make_sequence(), profile_for(case, FAR)).value
    limit = value / (1 + 5e-10)  # value = limit * (1 + 5e-10), below limit * (1 + 1e-9)
    assert value > limit

    result = run_one(case.check, case.make_sequence(), profile_for(case, limit))

    assert result.state is State.PASS


@pytest.mark.parametrize("factor", [1 + 2e-9, 1.1])
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_a_value_above_the_limit_by_more_than_the_tolerance_fails(case, factor):
    value = run_one(case.check, case.make_sequence(), profile_for(case, FAR)).value

    result = run_one(case.check, case.make_sequence(), profile_for(case, value / factor))

    assert result.state is State.FAIL
    assert result.value == value
    assert result.limit == value / factor
    assert result.reason == detail(case)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_the_location_is_the_block_and_the_time_of_the_value(case):
    result = run_one(case.check, case.make_sequence(), profile_for(case, FAR))

    assert result.location is not None
    assert result.location.block == case.block
    assert result.location.time_s == pytest.approx(case.time_s, abs=1e-9)


def axes_sequence(first: tuple[str, float], *others: tuple[str, float]) -> pp.Sequence:
    """One block for each (axis, amplitude in mT/m), in the order given."""
    return build(*[(trap(axis, amplitude),) for axis, amplitude in (first, *others)])


@pytest.mark.parametrize(
    ("limit_mt", "state"), [(16.0, State.FAIL), (20.0, State.PASS)], ids=["fail", "pass"]
)
@pytest.mark.parametrize("case", CASES[:2], ids=CASE_IDS[:2])
def test_the_axis_with_the_largest_ratio_gives_the_value(case, limit_mt, state):
    """x at 10, y at 18 and z at 14 mT/m (slew 100, 180 and 140 T/m/s), each in its own
    block. The limit is one number for all axes, so the largest ratio is the largest peak,
    y, in block 2 (which starts after the 500 us of block 1)."""
    seq = axes_sequence(("x", 10), ("y", 18), ("z", 14))
    value = 18.0 if case.key == "max_grad" else 180.0
    limit = case.per_mt * limit_mt

    result = run_one(case.check, seq, profile_for(case, limit))

    assert result.state is state
    assert result.value == pytest.approx(value)
    assert result.limit == limit
    assert result.location.block == 2
    assert result.reason == "axis y"
    time_s = TRAPEZOID + (RISE if case.key == "max_grad" else 0.0)
    assert result.location.time_s == pytest.approx(time_s, abs=1e-9)


@pytest.mark.parametrize("case", CASES[:2], ids=CASE_IDS[:2])
def test_two_axes_with_the_same_peak_give_the_first_axis_in_x_y_z_order(case):
    """y (block 1) and x (block 2) have the same peak: the value is the one of x, in block 2,
    not the one of the earlier block."""
    seq = axes_sequence(("y", 15), ("x", 15))

    result = run_one(case.check, seq, profile_for(case, FAR))

    assert result.location.block == 2
    assert result.reason == "axis x"


def test_the_vector_peak_is_above_the_limit_when_each_axis_is_below_it():
    """x and y at 16 mT/m (0.8 of the 20 mT/m limit) at the same time: each axis passes, and
    |G| = 16 * sqrt(2) = 22.6 mT/m is above the limit."""
    seq = build((trap("x", 16), trap("y", 16)))
    profile = make_profile(max_grad=20.0, max_slew=FAR)

    axis = run_one(AMPLITUDE_AXIS, seq, profile)
    vector = run_one(AMPLITUDE_ANY_ORIENTATION, seq, profile)

    assert axis.state is State.PASS
    assert axis.value == pytest.approx(16.0)
    assert axis.location.block == 1
    assert vector.state is State.FAIL
    assert vector.value == pytest.approx(16 * math.sqrt(2))
    assert vector.limit == 20.0
    assert vector.location.block == 1


@pytest.mark.parametrize("check", CHECKS, ids=[c.spec.id for c in CHECKS])
def test_a_sequence_with_no_gradient_passes_with_the_value_0_and_no_location(check):
    profile = make_profile(max_grad=20.0, max_slew=200.0)

    result = run_one(check, empty_sequence(), profile)

    assert result.state is State.PASS
    assert result.value == 0.0
    assert result.location is None
    assert result.limit == (200.0 if check is SLEW_AXIS else 20.0)
    assert result.unit == ("T/m/s" if check is SLEW_AXIS else "mT/m")


@pytest.mark.parametrize("check", CHECKS, ids=[c.spec.id for c in CHECKS])
def test_a_value_of_0_has_no_location(check):
    """A y gradient scaled to the amplitude 0 is an event, so the sequence has a gradient, but
    every value is 0 and the measurement gives no block."""
    seq = build((pp.scale_grad(trap("y", 10), 0.0),))

    result = run_one(check, seq, make_profile(max_grad=20.0, max_slew=200.0))

    assert result.state is State.PASS
    assert result.value == 0.0
    assert result.location is None


@pytest.mark.parametrize("check", CHECKS[::2], ids=["amplitude", "any-orientation"])
def test_a_value_with_no_block_has_a_location_with_the_time_only(monkeypatch, check):
    """The measurement can give a value above 0 and no block. The location has the time and
    no block ID."""
    axes = {a: AxisResult(5.0, 0.25, None, 50.0, 0.125, None, 1.0) for a in "xyz"}
    measured = GradientLimits(
        reason=None,
        range_s=(0.0, 1.0),
        axes=axes,
        vector_peak_mt_per_m=5.0,
        vector_peak_time_s=0.25,
        vector_peak_block=None,
        limits=HardwareLimits(20.0, 200.0, "t"),
    )
    monkeypatch.setattr(gradient_module, "gradient_limits", lambda seq, **kwargs: measured)

    result = run_one(check, peak_sequence(), make_profile(max_grad=20.0, max_slew=200.0))

    assert result.value == 5.0
    assert result.location == Location(block=None, time_s=0.25)


def test_a_target_with_one_limit_gives_not_evaluated_for_the_checks_of_the_other(monkeypatch):
    install(monkeypatch, *CHECKS)

    only_grad = run_checks(peak_sequence(), [make_profile(max_grad=30.0)])
    only_slew = run_checks(peak_sequence(), [make_profile(max_slew=300.0)])
    neither = run_checks(peak_sequence(), [make_profile()])

    def states(matrix):
        return {r.check_id: r for r in matrix.results}

    grad = states(only_grad)
    assert grad["gradient.amplitude.axis"].state is State.PASS
    assert grad["gradient.amplitude.axis"].limit == pytest.approx(30.0)
    assert grad["gradient.amplitude.any-orientation"].state is State.PASS
    assert grad["gradient.slew.axis"].state is State.NOT_EVALUATED
    assert "opts.max_slew" in grad["gradient.slew.axis"].reason
    slew = states(only_slew)
    assert slew["gradient.slew.axis"].state is State.PASS
    assert slew["gradient.slew.axis"].limit == pytest.approx(300.0)
    assert slew["gradient.amplitude.axis"].state is State.NOT_EVALUATED
    assert slew["gradient.amplitude.any-orientation"].state is State.NOT_EVALUATED
    assert {r.state for r in neither.results} == {State.NOT_EVALUATED}


def test_a_target_with_one_limit_gives_the_other_as_nan_and_its_name_as_the_label(monkeypatch):
    """The limits of a target with only `opts.max_grad` come from its `pp.Opts`, with the gamma
    of that Opts (40 MHz/T, the gamma that the measurement uses too), and the other limit is
    nan. `gradient_limits` is not called with None."""
    install(monkeypatch, *CHECKS)
    calls = spy_on_gradient_limits(monkeypatch)
    profile = make_profile(max_grad=20.0, name="only grad", gamma=40e6)

    run_checks(peak_sequence(), [profile])

    (call,) = calls
    limits = call["limits"]
    assert limits.max_grad_mt_per_m == pytest.approx(20.0)
    assert math.isnan(limits.max_slew_t_per_m_per_s)
    assert limits.label == "only grad"


def test_a_target_with_only_max_slew_gives_max_grad_as_nan(monkeypatch):
    install(monkeypatch, *CHECKS)
    calls = spy_on_gradient_limits(monkeypatch)

    run_checks(peak_sequence(), [make_profile(max_slew=300.0, name="only slew")])

    (call,) = calls
    assert call["limits"].max_slew_t_per_m_per_s == pytest.approx(300.0)
    assert math.isnan(call["limits"].max_grad_mt_per_m)
    assert call["limits"].label == "only slew"


@pytest.mark.parametrize(
    ("rise_time", "limit", "state"),
    [(100e-6, 300.0, State.PASS), (200e-6, 150.0, State.FAIL)],
)
def test_max_grad_with_rise_time_gives_the_slew_limit_max_grad_over_rise_time(
    monkeypatch, rise_time, limit, state
):
    """The peak slew of `peak_sequence` is 200 T/m/s. The limit is 30 mT/m / rise_time."""
    install(monkeypatch, SLEW_AXIS)

    matrix = run_checks(peak_sequence(), [make_profile(max_grad=30.0, rise_time=rise_time)])

    (result,) = matrix.results
    assert result.state is state
    assert result.limit == pytest.approx(limit)
    assert result.value == pytest.approx(200.0)


def test_rise_time_without_max_grad_gives_not_evaluated_for_the_slew(monkeypatch):
    install(monkeypatch, SLEW_AXIS)

    matrix = run_checks(peak_sequence(), [make_profile(rise_time=100e-6)])

    (result,) = matrix.results
    assert result.state is State.NOT_EVALUATED
    assert "opts.max_slew" in result.reason


def test_the_three_checks_share_one_measurement_for_each_target(monkeypatch, tmp_path):
    """`gradient_limits` runs one time for each target, over the whole file, with the hardware
    limits of the target and never with None."""
    install(monkeypatch, *CHECKS)
    calls = spy_on_gradient_limits(monkeypatch)
    path = tmp_path / "peak.seq"
    peak_sequence().write(str(path))
    targets = [make_profile(25.0, 250.0, name="a"), make_profile(30.0, 300.0, name="b")]

    matrix = run_checks(path, targets)

    assert len(matrix.results) == 6
    assert {r.state for r in matrix.results} == {State.PASS}
    assert len(calls) == 2
    assert [call["limits"] for call in calls] == [t.hardware_limits for t in targets]
    assert all(call.keys() == {"limits", "gamma"} for call in calls)
    assert [call["gamma"] for call in calls] == [GAMMA, GAMMA]


def test_the_three_checks_of_one_target_call_gradient_limits_one_time(monkeypatch):
    install(monkeypatch, *CHECKS)
    calls = spy_on_gradient_limits(monkeypatch)
    profile = make_profile(25.0, 250.0)

    run_checks(peak_sequence(), [profile])

    assert len(calls) == 1
    assert calls[0]["limits"] == profile.hardware_limits


def test_limits_from_sequence_uses_the_limits_of_seq_system(monkeypatch):
    """With the opt-in and a `Sequence` object, a target with no limits gets the 28 mT/m and
    150 T/m/s of `SYSTEM`: the three checks compare with them."""
    install(monkeypatch, *CHECKS)
    gx = pp.make_trapezoid(
        channel="x", amplitude=20e-3 * GAMMA, rise_time=200e-6, flat_time=400e-6, system=SYSTEM
    )
    seq = build((gx,), system=SYSTEM)

    matrix = run_checks(seq, [make_profile()], limits_from_sequence=True)

    results = {r.check_id: r for r in matrix.results}
    assert {r.state for r in results.values()} == {State.PASS}
    amplitude = results["gradient.amplitude.axis"]
    assert (amplitude.value, amplitude.limit) == (pytest.approx(20.0), pytest.approx(28.0))
    slew = results["gradient.slew.axis"]
    assert (slew.value, slew.limit) == (pytest.approx(100.0), pytest.approx(150.0))
    vector = results["gradient.amplitude.any-orientation"]
    assert (vector.value, vector.limit) == (pytest.approx(20.0), pytest.approx(28.0))


def test_limits_from_sequence_converts_values_and_limits_with_the_gamma_of_seq_system(
    monkeypatch,
):
    """`seq.system` has 40 MHz/T: its limits are 28 mT/m and 150 T/m/s, and the values of a 20
    mT/m trapezoid (rise time 200 us) are 20 mT/m and 100 T/m/s, all with that gamma."""
    install(monkeypatch, *CHECKS)
    system = pp.Opts(max_grad=28, grad_unit="mT/m", max_slew=150, slew_unit="T/m/s", gamma=GAMMA_40)
    gx = pp.make_trapezoid(
        channel="x", amplitude=20e-3 * GAMMA_40, rise_time=200e-6, flat_time=400e-6, system=system
    )
    seq = build((gx,), system=system)

    matrix = run_checks(seq, [make_profile()], limits_from_sequence=True)

    results = {r.check_id: r for r in matrix.results}
    assert {r.state for r in results.values()} == {State.PASS}
    for check_id, value, limit in [
        ("gradient.amplitude.axis", 20.0, 28.0),
        ("gradient.slew.axis", 100.0, 150.0),
        ("gradient.amplitude.any-orientation", 20.0, 28.0),
    ]:
        assert (results[check_id].value, results[check_id].limit) == (
            pytest.approx(value),
            pytest.approx(limit),
        ), check_id


@pytest.mark.parametrize(
    ("check", "value", "unit"),
    [
        (AMPLITUDE_AXIS, 21.0, "mT/m"),
        (SLEW_AXIS, 210.0, "T/m/s"),
        (AMPLITUDE_ANY_ORIENTATION, 21.0, "mT/m"),
    ],
    ids=[c.spec.id for c in CHECKS],
)
def test_a_profile_with_another_gamma_compares_value_and_limit_with_that_gamma(
    monkeypatch, tmp_path, check, value, unit
):
    """R3: gamma 40 MHz/T, a 21 mT/m gradient (840 kHz/m, slew 210 T/m/s) and the limits
    20 mT/m and 200 T/m/s. With 42.576 MHz/T the value would be 19.7 mT/m and pass."""
    install(monkeypatch, check)
    system = pp.Opts(
        max_grad=100, grad_unit="mT/m", max_slew=1000, slew_unit="T/m/s", gamma=GAMMA_40
    )
    gx = pp.make_trapezoid(
        channel="x", amplitude=21e-3 * GAMMA_40, rise_time=RISE, flat_time=FLAT, system=system
    )
    path = tmp_path / "gamma40.seq"
    build((gx,), system=system).write(str(path))
    profile = make_profile(max_grad=20.0, max_slew=200.0, gamma=GAMMA_40)

    (result,) = run_checks(path, [profile]).results

    assert result.state is State.FAIL
    assert result.value == pytest.approx(value, rel=1e-4)
    assert result.limit == pytest.approx(20.0 if unit == "mT/m" else 200.0)
    assert result.unit == unit


def test_a_rotation_gives_error_for_the_three_checks(monkeypatch):
    install(monkeypatch, *CHECKS)
    seq = peak_sequence()
    seq.rotation_library = EventLibrary()
    # A scalar-first unit quaternion (angle 45 deg about z), as tests/test_extensions.py uses.
    seq.rotation_library.insert(1, (0.9238795325112867, 0.0, 0.0, 0.3826834323650898))

    matrix = run_checks(seq, [make_profile(25.0, 250.0)])

    assert len(matrix.results) == 3
    for result in matrix.results:
        assert result.state is State.ERROR
        assert result.reason.startswith("NotImplementedError")
        assert result.value is None


@pytest.mark.parametrize("check", CHECKS, ids=[c.spec.id for c in CHECKS])
def test_the_spec_sets_each_field(check):
    spec = check.spec

    assert isinstance(spec, CheckSpec)
    assert (
        spec.id
        == {
            AMPLITUDE_AXIS: "gradient.amplitude.axis",
            SLEW_AXIS: "gradient.slew.axis",
            AMPLITUDE_ANY_ORIENTATION: "gradient.amplitude.any-orientation",
        }[check]
    )
    assert spec.version == 1
    assert spec.cost == "fast"  # task 8.3 of the plan, from scripts/budget.py
    assert spec.url is None
    assert spec.models == ()
    assert spec.inputs == (("opts.max_slew",) if check is SLEW_AXIS else ("opts.max_grad",))
    assert spec.rasters == ("GradientRasterTime", "BlockDurationRaster")
    for text in (spec.title, spec.quantity, spec.limit, spec.tolerance, spec.pass_condition):
        assert isinstance(text, str)
        assert text.strip()


@pytest.mark.parametrize(
    "rasters", [None, {"GradientRasterTime": 4e-6}, {"GradientRasterTime": 10e-6}]
)
def test_the_slew_of_a_junction_uses_the_gradient_raster_of_the_file_for_any_target(
    monkeypatch, tmp_path, rasters
):
    install(monkeypatch, SLEW_AXIS)
    path = tmp_path / "raster_4us.seq"
    raster_4us_sequence().write(str(path))
    profile = replace(make_profile(max_slew=50.0), rasters=rasters)

    (result,) = run_checks(path, [profile]).results

    assert result.state is State.FAIL
    # The file stores the amplitudes with fewer digits: 2e-5 relative in the value.
    assert result.value == pytest.approx(RASTER_4US_JUNCTION, rel=1e-4)
    assert result.location is not None
    assert result.location.block == 2
    assert result.location.time_s == pytest.approx(RASTER_4US_JUNCTION_TIME)


def with_rasters(profile: TargetProfile, rasters: dict[str, float]) -> TargetProfile:
    """`profile` with the `[rasters]` values `rasters`, and their sources."""
    sources = {**profile.sources, **{f"rasters.{name}": "profile" for name in rasters}}
    return replace(profile, rasters=rasters, sources=sources)


def write_without_definition(path, name: str) -> None:
    """Write `raster_4us_sequence` to `path`, and remove the line of the definition `name`
    from its `[DEFINITIONS]`: the file does not declare that raster."""
    raster_4us_sequence().write(str(path))
    lines = path.read_text().split("\n")
    kept = [line for line in lines if not line.startswith(name + " ")]
    assert len(kept) == len(lines) - 1
    path.write_text("\n".join(kept))


@pytest.mark.parametrize("name", ["GradientRasterTime", "BlockDurationRaster"])
@pytest.mark.filterwarnings("ignore:No BlockDurationRaster found:UserWarning")
def test_a_raster_that_the_file_does_not_declare_and_the_target_does_not_give_is_not_evaluated(
    monkeypatch, tmp_path, name
):
    install(monkeypatch, *CHECKS)
    path = tmp_path / "no_raster.seq"
    write_without_definition(path, name)

    matrix = run_checks(path, [make_profile(max_grad=100.0, max_slew=50.0)])

    assert len(matrix.results) == 3
    for result in matrix.results:
        assert result.state is State.NOT_EVALUATED
        assert result.reason == (
            f"the file does not declare {name} and the target 't' does not give rasters.{name}"
        )
        assert result.value is None


@pytest.mark.parametrize(
    ("raster", "state", "slew"),
    [(4e-6, State.FAIL, RASTER_4US_JUNCTION), (10e-6, State.PASS, 24.0)],
    ids=["4 us", "10 us"],
)
def test_a_raster_that_the_file_does_not_declare_comes_from_the_target(
    monkeypatch, tmp_path, raster, state, slew
):
    """The junction step of `raster_4us_sequence` divided by the raster of the target: 60 T/m/s
    for 4 µs, and 24 T/m/s for 10 µs. The times of the gradient points are in units of the
    raster too, so with 10 µs the segment slopes are 2.5 times smaller (16 T/m/s)."""
    install(monkeypatch, *CHECKS)
    path = tmp_path / "no_raster.seq"
    write_without_definition(path, "GradientRasterTime")
    profile = with_rasters(
        make_profile(max_grad=100.0, max_slew=50.0), {"GradientRasterTime": raster}
    )

    results = {r.check_id: r for r in run_checks(path, [profile]).results}

    assert results["gradient.slew.axis"].state is state
    assert results["gradient.slew.axis"].value == pytest.approx(slew, rel=1e-4)
    for check_id in ("gradient.amplitude.axis", "gradient.amplitude.any-orientation"):
        assert results[check_id].state is State.PASS
        assert results[check_id].value == pytest.approx(16.0, rel=1e-4)
