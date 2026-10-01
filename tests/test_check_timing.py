import math
from types import SimpleNamespace

import numpy as np
import pypulseq as pp
import pytest
from pypulseq.check_timing import error_messages, print_error_report
from synthetic import SYSTEM, block_pulse

from pulseq_checks import registry
from pulseq_checks.checks.timing import PYPULSEQ, RASTERS
from pulseq_checks.profile import RASTER_OPTS, TargetProfile
from pulseq_checks.results import Finding, Location, State
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
# The `opts` values for the findings tests, in seconds: the RF dead time and the ADC dead time are
# longer, and the RF ringdown time is longer, than those of the sequence that `error_sequence`
# builds.
ERROR_OPTS = {"rf_dead_time": 200e-6, "rf_ringdown_time": 50e-6, "adc_dead_time": 30e-6}
# The Python types of the values of the `data` of a finding.
DATA_TYPES = (str, int, float, bool, type(None))
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


def error_sequence(tmp_path):
    """`timing_sequence()` and a block 5 with an ADC (a delay of 10 µs, 64 samples of 20 µs),
    as a .seq file. For `ERROR_OPTS` it has the errors BLOCK_DURATION_MISMATCH, RF_DEAD_TIME
    and RF_RINGDOWN_TIME in blocks 2 and 4, and BLOCK_DURATION_MISMATCH, ADC_DEAD_TIME and
    POST_ADC_DEAD_TIME in block 5."""
    seq = timing_sequence()
    seq.add_block(pp.make_adc(num_samples=64, dwell=20e-6, delay=10e-6, system=SYSTEM))
    path = tmp_path / "errors.seq"
    seq.write(str(path))
    return path


def raster_error_sequence() -> pp.Sequence:
    """A delay of 1 ms (block 1), an ADC with a dwell of 20051.5 ns (block 2), and a delay of
    1001.23 µs (block 3), in memory (pypulseq does not write a block that is not on the
    block duration raster). For the target of `make_target` it has these RASTER errors, in
    this order: the duration of block 2, the dwell of the ADC of block 2, and the duration
    of block 3."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_delay(1e-3))
    seq.add_block(pp.make_adc(num_samples=64, dwell=20.0515e-6, delay=10e-6, system=SYSTEM))
    seq.add_block(pp.make_delay(1.00123e-3))
    return seq


def read_with(path, target):
    """The sequence in the .seq file `path`, read with the `Opts` of `target`."""
    seq = pp.Sequence(system=target.make_opts())
    seq.read(str(path))
    return seq


def start_of(seq, block):
    """The start time of `block`: the sum of the stored durations of the blocks before it."""
    return sum(d for b, d in seq.block_durations.items() if b < block)


def printed_error_lines(capsys, seq, errors):
    """The lines "- event.field: text" that `print_error_report` of pypulseq prints for
    `errors`, without colors."""
    capsys.readouterr()
    print_error_report(seq, errors, full_report=True, colored=False)
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("- ")]


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


def test_one_finding_for_each_error_in_the_order_of_check_timing(tmp_path, monkeypatch):
    install(monkeypatch)
    target = make_target(opts={**TIMING_OPTS, "rf_dead_time": 200e-6})
    path = write_seq(tmp_path)
    (result,) = run_checks(path, [target], select=[PYPULSEQ_ID]).results
    _, errors = read_with(path, target).check_timing()
    assert result.state is State.FAIL
    assert len(errors) == 2
    assert all(isinstance(f, Finding) for f in result.findings)
    assert [f.code for f in result.findings] == [e.error_type for e in errors]
    assert [f.code for f in result.findings] == ["RF_DEAD_TIME", "RF_DEAD_TIME"]
    assert [f.location.block for f in result.findings] == [int(e.block) for e in errors]
    assert result.findings_omitted == 0
    # The value, the limit, the location and the reason are the ones of the first error.
    assert result.value == len(errors)
    assert result.limit == 0
    assert result.location == result.findings[0].location
    assert result.reason == "first of 2 errors: block 2, rf.delay: RF_DEAD_TIME"


def test_the_location_of_a_finding_is_its_block_and_the_start_of_that_block(tmp_path, monkeypatch):
    install(monkeypatch)
    target = make_target(opts={**TIMING_OPTS, "rf_dead_time": 200e-6})
    (result,) = run_checks(write_seq(tmp_path), [target], select=[PYPULSEQ_ID]).results
    # Block 2 starts after the delay of 1 ms. Block 4 starts after the delay, block 2 (a delay of
    # 100 µs, a pulse of 1 ms and the ringdown of 20 µs) and the delay of 2 ms of block 3.
    assert [f.location for f in result.findings] == [
        Location(block=2, time_s=pytest.approx(1e-3)),
        Location(block=4, time_s=pytest.approx(4.12e-3)),
    ]


def test_the_findings_of_each_error_type_have_the_data_of_the_record(tmp_path):
    target = make_target(opts=ERROR_OPTS)
    seq = read_with(error_sequence(tmp_path), target)
    findings = {}
    for finding in direct_result(PYPULSEQ, seq, target).findings:
        findings.setdefault((finding.location.block, finding.code), finding)
    mismatch = {"event": "block", "field": "duration"}
    expected = {
        (2, "BLOCK_DURATION_MISMATCH"): {**mismatch, "value": 1150e-6, "duration": 1120e-6},
        (2, "RF_DEAD_TIME"): {
            "event": "rf",
            "field": "delay",
            "value": 100e-6,
            "dead_time": 200e-6,
        },
        (2, "RF_RINGDOWN_TIME"): {
            "event": "rf",
            "field": "duration",
            "value": 1100e-6,
            "duration": 1120e-6,
            "ringdown_time": 50e-6,
        },
        (5, "BLOCK_DURATION_MISMATCH"): {**mismatch, "value": 1320e-6, "duration": 1300e-6},
        (5, "ADC_DEAD_TIME"): {
            "event": "adc",
            "field": "delay",
            "value": 10e-6,
            "dead_time": 30e-6,
        },
        (5, "POST_ADC_DEAD_TIME"): {
            "event": "adc",
            "field": "duration",
            "value": 1290e-6,
            "duration": 1300e-6,
            "dead_time": 30e-6,
        },
    }
    assert {finding.code for finding in findings.values()} >= {k[1] for k in expected}
    for key, data in expected.items():
        assert dict(findings[key].data) == pytest.approx(data, rel=1e-9), key
    for finding in findings.values():
        assert all(type(v) in DATA_TYPES for v in finding.data.values()), finding.code
    # NumPy scalars of the records are Python scalars in the data.
    _, errors = seq.check_timing()
    assert isinstance(errors[0].block, np.integer)
    assert isinstance(errors[0].value, np.floating)


def test_the_findings_of_a_raster_error_have_the_data_of_the_record():
    target = make_target()
    result = direct_result(PYPULSEQ, raster_error_sequence(), target)
    assert [(f.code, f.location.block) for f in result.findings] == [("RASTER", 2)] * 2 + [
        ("RASTER", 3)
    ]
    data = [dict(f.data) for f in result.findings]
    assert [(d["event"], d["field"], d["raster"]) for d in data] == [
        ("block", "duration", "block_duration_raster"),
        ("adc", "dwell", "adc_raster_time"),
        ("block", "duration", "block_duration_raster"),
    ]
    assert data[1] == pytest.approx(
        {**data[1], "value": 20.0515e-6, "value_rounded": 20.1e-6, "error": -48.5e-9}, rel=1e-6
    )
    assert data[2] == pytest.approx(
        {**data[2], "value": 1001.23e-6, "value_rounded": 1000e-6, "error": 1.23e-6}, rel=1e-6
    )
    assert all(
        set(d) == {"event", "field", "value", "value_rounded", "error", "raster"} for d in data
    )
    assert all(type(v) in DATA_TYPES for d in data for v in d.values())


def test_the_message_of_a_finding_is_the_text_of_the_error_report_of_pypulseq(tmp_path, capsys):
    target = make_target(opts=ERROR_OPTS)
    seq = read_with(error_sequence(tmp_path), target)
    findings = direct_result(PYPULSEQ, seq, target).findings
    _, errors = seq.check_timing()
    assert len(findings) == len(errors) == 9
    expected = [
        f"- {e.event}.{e.field}: {f.message}" for e, f in zip(errors, findings, strict=True)
    ]
    assert printed_error_lines(capsys, seq, errors) == expected
    assert {f.code for f in findings} == {
        "BLOCK_DURATION_MISMATCH",
        "RF_DEAD_TIME",
        "RF_RINGDOWN_TIME",
        "ADC_DEAD_TIME",
        "POST_ADC_DEAD_TIME",
    }


def test_the_message_of_a_raster_finding_is_in_us_and_the_message_of_a_dwell_is_in_ns(capsys):
    target = make_target()
    seq = raster_error_sequence()
    findings = direct_result(PYPULSEQ, seq, target).findings
    _, errors = seq.check_timing()
    expected = [
        f"- {e.event}.{e.field}: {f.message}" for e, f in zip(errors, findings, strict=True)
    ]
    assert printed_error_lines(capsys, seq, errors) == expected
    duration, dwell, _ = (f.message for f in findings)
    assert duration.endswith(" us)")
    assert dwell.endswith(" ns)")
    assert " us" not in dwell


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (
            SimpleNamespace(
                block=2, event="rf", field="delay", error_type="NO_SUCH_TYPE", value=1.0
            ),
            "rf.delay: NO_SUCH_TYPE",
        ),
        # A type with a template, and a record that lacks a field of the template.
        (
            SimpleNamespace(block=2, event="adc", field="dwell", error_type="RASTER", value=1.0),
            "adc.dwell: RASTER",
        ),
    ],
)
def test_a_record_without_a_message_template_gives_the_fallback_message(
    tmp_path, monkeypatch, record, message
):
    target = make_target()
    seq = read_with(write_seq(tmp_path), target)
    monkeypatch.setattr(seq, "check_timing", lambda: (False, [record]))
    result = direct_result(PYPULSEQ, seq, target)
    assert result.state is State.FAIL
    (finding,) = result.findings
    assert finding.code == record.error_type
    assert finding.message == message
    assert finding.location == Location(block=2, time_s=pytest.approx(1e-3))
    assert dict(finding.data) == {"event": record.event, "field": record.field, "value": 1.0}


def test_a_pass_has_no_findings(tmp_path):
    target = make_target()
    result = direct_result(PYPULSEQ, read_with(write_seq(tmp_path), target), target)
    assert result.state is State.PASS
    assert result.findings == ()
    assert result.findings_omitted == 0


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


def test_the_spec_of_timing_pypulseq_has_findings_and_keeps_version_1():
    assert PYPULSEQ.spec.version == 1
    assert PYPULSEQ.spec.findings.strip()
    # The text names each error type that pypulseq has a message template for.
    assert all(code in PYPULSEQ.spec.findings for code in error_messages)
    assert RASTERS.spec.findings is None


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
