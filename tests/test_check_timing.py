import math

import numpy as np
import pypulseq as pp
import pytest
from synthetic import SYSTEM, block_pulse

from pulseq_checks import registry
from pulseq_checks.checks.timing import PYPULSEQ, RASTERS
from pulseq_checks.profile import RASTER_OPTS, TargetProfile
from pulseq_checks.results import Location, State
from pulseq_checks.rules import RunContext
from pulseq_checks.run import run_checks

# The rasters of a typical target, in seconds, by their reserved [DEFINITIONS] names.
RASTER_VALUES = {
    "GradientRasterTime": 1e-5,
    "RadiofrequencyRasterTime": 1e-6,
    "AdcRasterTime": 1e-7,
    "BlockDurationRaster": 1e-5,
}
# The `opts` values that `check_timing` reads, in seconds (the values of `SYSTEM`).
TIMING_OPTS = {"rf_dead_time": 100e-6, "rf_ringdown_time": 20e-6, "adc_dead_time": 10e-6}
RASTER_IDS = RASTERS.spec.id
PYPULSEQ_ID = PYPULSEQ.spec.id


def make_target(name="a", *, rasters=RASTER_VALUES, opts=TIMING_OPTS):
    """A target with the given rasters and `opts`. A raster or an `opts` value that is None
    is not in the profile."""
    rasters = {k: v for k, v in rasters.items() if v is not None}
    opts = {k: v for k, v in opts.items() if v is not None}
    sources = {f"rasters.{k}": "profile" for k in rasters}
    sources.update({f"opts.{k}": "profile" for k in opts})
    return TargetProfile(
        name=name,
        vendor=None,
        format_version=1,
        source_path=None,
        opts=opts or None,
        hardware_limits=None,
        rasters=rasters or None,
        models={},
        acoustic_resonances=None,
        sources=sources,
        unused_sections=(),
    )


def timing_sequence() -> pp.Sequence:
    """A delay of 1 ms (block 1), an RF pulse with a delay of 100 µs (block 2), a delay of
    2 ms (block 3), and an RF pulse again (block 4). Block 2 starts at 1 ms. The pulses are
    correct for an RF dead time of 100 µs and an RF ringdown of 20 µs."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_delay(1e-3))
    seq.add_block(block_pulse("excitation", math.pi / 2))
    seq.add_block(pp.make_delay(2e-3))
    seq.add_block(block_pulse("refocusing", math.pi))
    return seq


def write_seq(tmp_path, *, definitions=None, remove=()):
    """`timing_sequence()` as a .seq file, with the [DEFINITIONS] entries of `definitions`
    set to different values and the entries named in `remove` left out."""
    seq = timing_sequence()
    for key, value in (definitions or {}).items():
        seq.set_definition(key, value)
    for key in remove:
        del seq.definitions[key]
    path = tmp_path / "timing.seq"
    seq.write(str(path))
    return path


def install(monkeypatch):
    """Make `registry.check_rules` give the two timing checks only."""
    rules = {RASTERS.spec.id: RASTERS, PYPULSEQ.spec.id: PYPULSEQ}
    monkeypatch.setattr(registry, "check_rules", lambda: rules)


def raster_result(tmp_path, monkeypatch, target, **file):
    """The result of `timing.rasters` for `target` on a file with the `write_seq`
    arguments `file`."""
    install(monkeypatch)
    matrix = run_checks(write_seq(tmp_path, **file), [target], select=[RASTER_IDS])
    (result,) = matrix.results
    return result


def direct_result(rule, seq, target):
    """The result of `rule.run` on `seq`, without the run function."""
    return rule.run(RunContext(seq, target))


def scaled(name, factor):
    """The definitions that set the raster `name` to `factor` times its target value."""
    return {name: RASTER_VALUES[name] * factor}


def test_equal_rasters_pass(tmp_path, monkeypatch):
    result = raster_result(tmp_path, monkeypatch, make_target())
    assert result.state is State.PASS
    assert result.check_id == "timing.rasters"
    assert result.unit == "s"
    assert result.location is None
    # The detail names the worst raster: the first in RASTER_OPTS order when all are equal.
    assert result.reason.startswith("GradientRasterTime: ")
    assert result.value == pytest.approx(1e-5, rel=1e-8)
    assert result.limit == 1e-5


@pytest.mark.parametrize("name", RASTER_VALUES)
def test_equal_rasters_fail_when_one_raster_differs(tmp_path, monkeypatch, name):
    result = raster_result(tmp_path, monkeypatch, make_target(), definitions=scaled(name, 1.5))
    assert result.state is State.FAIL
    assert result.value == pytest.approx(1.5 * RASTER_VALUES[name], rel=1e-8)
    assert result.limit == RASTER_VALUES[name]
    assert result.unit == "s"
    assert result.location is None
    assert result.reason.startswith(f"{name}: ")


def test_the_worst_raster_is_the_one_with_the_largest_deviation(tmp_path, monkeypatch):
    definitions = {**scaled("GradientRasterTime", 1.1), **scaled("AdcRasterTime", 1.5)}
    result = raster_result(tmp_path, monkeypatch, make_target(), definitions=definitions)
    assert result.state is State.FAIL
    assert result.value == pytest.approx(1.5e-7, rel=1e-8)
    assert result.limit == 1e-7


@pytest.mark.parametrize("factor", [0.5, 2, 3])
@pytest.mark.parametrize("name", RASTER_VALUES)
def test_rasters_fail_when_the_file_raster_is_a_ratio_other_than_one(
    tmp_path, monkeypatch, name, factor
):
    result = raster_result(tmp_path, monkeypatch, make_target(), definitions=scaled(name, factor))
    assert result.state is State.FAIL
    assert result.value == pytest.approx(factor * RASTER_VALUES[name], rel=1e-8)
    assert result.limit == RASTER_VALUES[name]


@pytest.mark.parametrize(
    ("factor", "state"),
    [
        (1 + 5e-9, State.PASS),  # the rounding of a nine-digit definition
        (1 - 5e-9, State.PASS),
        (1 + 1e-7, State.FAIL),
        (1 - 1e-7, State.FAIL),
    ],
)
def test_the_tolerance_of_a_raster_is_relative_1e_8(factor, state):
    seq = pp.Sequence(SYSTEM)
    seq.definitions.update({k: v * factor for k, v in RASTER_VALUES.items()})
    result = direct_result(RASTERS, seq, make_target())
    assert result.state is state


@pytest.mark.filterwarnings("ignore:No BlockDurationRaster found")  # from pypulseq's read
@pytest.mark.parametrize("name", RASTER_VALUES)
def test_a_raster_that_the_file_does_not_declare_gives_error(tmp_path, monkeypatch, name):
    result = raster_result(tmp_path, monkeypatch, make_target(), remove=[name])
    assert result.state is State.ERROR
    assert name in result.reason
    assert result.value is None
    assert result.limit is None


@pytest.mark.parametrize(
    "declared", ["abc", np.array([1e-5, 2e-5]), 0.0, -1e-5, math.nan, math.inf]
)
def test_a_declared_raster_that_is_not_one_positive_number_gives_error(declared):
    seq = pp.Sequence(SYSTEM)
    seq.definitions["GradientRasterTime"] = declared
    result = direct_result(RASTERS, seq, make_target())
    assert result.state is State.ERROR
    assert "GradientRasterTime" in result.reason


@pytest.mark.parametrize("name", RASTER_VALUES)
def test_rasters_are_not_evaluated_without_a_target_raster(tmp_path, monkeypatch, name):
    target = make_target(rasters={**RASTER_VALUES, name: None})
    result = raster_result(tmp_path, monkeypatch, target)
    assert result.state is State.NOT_EVALUATED
    assert f"rasters.{name}" in result.reason
    assert result.value is None


def test_timing_errors_depend_on_the_target(tmp_path, monkeypatch):
    install(monkeypatch)
    path = write_seq(tmp_path)
    targets = [
        make_target("dead-100", opts={**TIMING_OPTS, "rf_dead_time": 100e-6}),
        make_target("dead-200", opts={**TIMING_OPTS, "rf_dead_time": 200e-6}),
    ]
    matrix = run_checks(path, targets, select=[PYPULSEQ_ID])
    ok, bad = matrix.results
    assert (ok.target, ok.state) == ("dead-100", State.PASS)
    assert ok.value == 0
    assert ok.limit == 0
    assert ok.unit is None
    assert ok.location is None
    assert ok.reason is None
    assert (bad.target, bad.state) == ("dead-200", State.FAIL)
    assert bad.check_id == "timing.pypulseq"
    # Both RF pulses (blocks 2 and 4) have a delay of 100 µs: one error for each block.
    assert bad.value == 2
    assert bad.limit == 0
    assert bad.unit is None
    assert bad.reason.startswith("first of 2 errors: block 2")


def test_the_location_is_the_first_error_block_and_its_start_time(tmp_path, monkeypatch):
    install(monkeypatch)
    target = make_target(opts={**TIMING_OPTS, "rf_dead_time": 200e-6})
    matrix = run_checks(write_seq(tmp_path), [target], select=[PYPULSEQ_ID])
    (result,) = matrix.results
    assert result.state is State.FAIL
    assert result.location == Location(block=2, time_s=pytest.approx(1e-3))


@pytest.mark.parametrize(
    "missing",
    [f"rasters.{name}" for name in RASTER_VALUES] + [f"opts.{key}" for key in TIMING_OPTS],
)
def test_timing_pypulseq_is_not_evaluated_without_an_input(tmp_path, monkeypatch, missing):
    install(monkeypatch)
    kind, key = missing.split(".")
    if kind == "opts":
        target = make_target(opts={**TIMING_OPTS, key: None})
    else:
        target = make_target(rasters={**RASTER_VALUES, key: None})
    (result,) = run_checks(write_seq(tmp_path), [target], select=[PYPULSEQ_ID]).results
    assert result.state is State.NOT_EVALUATED
    assert missing in result.reason
    assert result.value is None


def test_check_timing_does_not_change_the_sequence(tmp_path):
    target = make_target(opts={**TIMING_OPTS, "rf_dead_time": 200e-6})
    seq = pp.Sequence(system=target.make_opts())
    seq.read(str(write_seq(tmp_path)))
    events = {k: v.copy() for k, v in seq.block_events.items()}
    durations = dict(seq.block_durations)
    definitions = dict(seq.definitions)
    cache_setting = seq.use_block_cache

    result = direct_result(PYPULSEQ, seq, target)

    assert result.state is State.FAIL
    assert list(seq.block_events) == list(events)
    assert all(np.array_equal(seq.block_events[k], events[k]) for k in events)
    assert seq.block_durations == durations
    assert seq.definitions == definitions
    assert seq.use_block_cache == cache_setting
    assert seq.block_cache == {}


@pytest.mark.parametrize("rule", [RASTERS, PYPULSEQ])
def test_each_field_of_a_spec_is_set(rule):
    spec = rule.spec
    assert spec.version == 1
    # The cost classes of task 8.3 of the plan, from scripts/budget.py on 10^6 blocks.
    assert spec.cost == {RASTERS: "fast", PYPULSEQ: "slow"}[rule]
    assert spec.url is None
    assert spec.models == ()
    for field in ("title", "quantity", "limit", "tolerance", "pass_condition"):
        assert getattr(spec, field).strip(), field
    assert spec.inputs
    assert len(set(spec.inputs)) == len(spec.inputs)


def test_the_ids_and_inputs_of_the_specs():
    raster_inputs = tuple(f"rasters.{name}" for name in RASTER_OPTS)
    assert RASTERS.spec.id == "timing.rasters"
    assert RASTERS.spec.inputs == raster_inputs
    assert RASTERS.spec.pypulseq is None
    assert PYPULSEQ.spec.id == "timing.pypulseq"
    assert PYPULSEQ.spec.inputs == (
        *raster_inputs,
        "opts.rf_dead_time",
        "opts.rf_ringdown_time",
        "opts.adc_dead_time",
    )
    assert PYPULSEQ.spec.pypulseq == "Sequence.check_timing"
