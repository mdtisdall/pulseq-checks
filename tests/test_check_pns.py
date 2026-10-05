import copy
import math
from dataclasses import replace

import pypulseq as pp
import pytest
from pulseq_analysis.analyses import PNS_SAFE_LEVELS
from pulseq_analysis.pns import pns_levels_for
from pulseq_analysis.pns_levels import PNS_LIMIT
from pulseq_analysis.seq_index import sequence_index
from pypulseq.event_lib import EventLibrary
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from synthetic import GAMMA, SYSTEM, empty_sequence, gre_sequence
from test_asc_profile import FIELDS, write_profile

from pulseq_checks import registry
from pulseq_checks.checks.pns import SAFE
from pulseq_checks.profile import read_profile
from pulseq_checks.results import State
from pulseq_checks.run import run_checks
from pulseq_checks.safe_model import SAFE_MODEL, hw_from_dict

# A scalar-first unit quaternion (angle 45 deg about z): q0=cos(22.5deg), qz=sin(22.5deg).
_QUATERNION = (0.9238795325112867, 0.0, 0.0, 0.3826834323650898)


def _with_rotation_library() -> pp.Sequence:
    """A `gre_sequence` with one rotation stored the way pypulseq draft PR #372 stores
    it: a `rotation_library` (an `EventLibrary` of scalar-first unit quaternions)."""
    seq = gre_sequence(num_trs=2)
    seq.rotation_library = EventLibrary()
    seq.rotation_library.insert(1, _QUATERNION)
    return seq


PASS_SCALE = 1000.0
FAIL_SCALE = 0.01
GAMMA_40 = 40e6  # Hz/T, a gamma that is not the 42.576 MHz/T of pypulseq


@pytest.fixture(autouse=True)
def only_pns(monkeypatch):
    """Load the PNS check only: the other checks are in other modules."""
    monkeypatch.setattr(registry, "check_rules", lambda: {"pns.safe": SAFE})


@pytest.fixture
def seq_file(tmp_path):
    path = tmp_path / "gre.seq"
    gre_sequence(num_trs=2).write(str(path))
    return path


@pytest.fixture
def target(write_gradient_asc, tmp_path):
    """A function: the profile of an `.asc` file with the limits multiplied by `scale`, and
    `opts.gamma` when `gamma` is not None."""

    def make(scale, gamma=None):
        asc = write_gradient_asc(limit_scale=scale)
        lines = [f'asc = "{asc.name}"']
        if gamma is not None:
            lines += ["[opts]", f"gamma = {gamma!r}"]
        return read_profile(write_profile(tmp_path, lines))

    return make


def run_one(seq, profile):
    (result,) = run_checks(seq, [profile]).results
    return result


def with_raster(profile, name, value):
    """`profile` with the `[rasters]` value `name`, and its source."""
    return replace(
        profile, rasters={name: value}, sources={**profile.sources, f"rasters.{name}": "profile"}
    )


def without_definition(path, name):
    """Remove the line of the definition `name` from the file `path`."""
    lines = path.read_text().split("\n")
    kept = [line for line in lines if not line.startswith(name + " ")]
    assert len(kept) == len(lines) - 1
    path.write_text("\n".join(kept))


def gamma_of(profile):
    """The magnitude of the gamma of `profile`, in Hz/T, which the check uses to convert. The
    profiles of this file give no gamma, so it is the gamma of pypulseq."""
    return abs(profile.make_opts().gamma)


def threshold_of(profile):
    """The stimulation limit of `profile` in Hz/T, the threshold of the binding."""
    return PNS_LIMIT * gamma_of(profile)


def percent(value_hz_per_t, profile):
    """A PNS value in Hz/T in percent of the stimulation limit, as the check converts it."""
    return 100 * value_hz_per_t / gamma_of(profile)


def levels_of(seq, profile):
    """The `PnsLevels` of `seq` for the SAFE parameters and the threshold of `profile`, as
    `run_checks` gets them."""
    params = profile.models["pns.safe"]
    return pns_levels_for(
        seq,
        hardware=(hw_from_dict(params), params["name"]),
        thresholds_hz_per_t=(threshold_of(profile),),
    )


def expected_peak(seq_file, profile):
    """The peak, in Hz/T, of `pns_levels_for` for the `.seq` file read with the `Opts` of
    `profile`, as `run_checks` reads it, and the SAFE parameters of `profile`."""
    seq = pp.Sequence(system=profile.make_opts())
    seq.read(str(seq_file))
    return levels_of(seq, profile).peak_hz_per_t


def block_at(index, t):
    """The block ID of the last block that starts at or before `t` (the first block when none
    does), by a loop over the blocks, not by the `np.searchsorted` of the check."""
    starts = [i for i in range(index.num_blocks) if index.start_s[i] <= t]
    return int(index.block_id[max(starts, default=0)])


def two_trapezoids():
    """A trapezoid on x, a delay of 50 ms and the same trapezoid, and the trapezoid alone."""
    trapezoid = pp.make_trapezoid(channel="x", area=1000, system=SYSTEM)
    one = pp.Sequence(SYSTEM)
    one.add_block(trapezoid)
    two = pp.Sequence(SYSTEM)
    two.add_block(trapezoid)
    two.add_block(pp.make_delay(50e-3))
    two.add_block(trapezoid)
    return one, two


def test_no_safe_parameters_gives_not_evaluated(tmp_path, seq_file):
    profile = read_profile(write_profile(tmp_path, []))
    result = run_one(seq_file, profile)
    assert result.state is State.NOT_EVALUATED
    assert "pns.safe" in result.reason
    assert result.value is None


@pytest.mark.parametrize(("scale", "state"), [(PASS_SCALE, State.PASS), (FAIL_SCALE, State.FAIL)])
def test_the_peak_against_the_stimulation_limit(target, seq_file, scale, state):
    profile = target(scale)
    result = run_one(seq_file, profile)
    assert result.state is state
    peak = expected_peak(seq_file, profile)
    assert (peak < threshold_of(profile)) == (state is State.PASS)
    assert result.value == percent(peak, profile)
    assert (result.limit, result.unit) == (100.0, "%")
    assert (result.model, result.model_version) == ("pns.safe", SAFE_MODEL.version)
    assert result.check_id == "pns.safe"
    assert result.spec_version == 1


def test_the_location_is_the_block_of_the_peak(target, seq_file):
    profile = target(FAIL_SCALE)
    result = run_one(seq_file, profile)
    seq = gre_sequence(num_trs=2)
    levels = levels_of(seq, profile)
    index = sequence_index(seq)
    t = levels.peak_time_s
    i = max(i for i in range(index.num_blocks) if index.start_s[i] <= t)
    assert result.location.time_s == t
    assert result.location.block == int(index.block_id[i])
    assert index.start_s[i] <= t < index.start_s[i] + index.duration_s[i] + 1e-12


def test_safe_parameters_in_the_profile_file_match_the_asc_file(
    write_gradient_asc, tmp_path, seq_file
):
    scale = 0.05
    from_asc = read_profile(
        write_profile(tmp_path, [f'asc = "{write_gradient_asc(limit_scale=scale).name}"'])
    )
    hw = safe_example_hw()
    lines = ["[models.pns.safe]", 'name = "MP_GPA_TEST"']
    for axis in "xyz":
        lines.append(f"[models.pns.safe.{axis}]")
        for field in FIELDS:
            value = float(getattr(getattr(hw, axis), field))
            if field in ("stim_limit", "stim_thresh"):
                value *= scale
            lines.append(f"{field} = {value!r}")
    direct_dir = tmp_path / "direct"
    direct_dir.mkdir()
    direct = read_profile(write_profile(direct_dir, lines))
    assert direct.models["pns.safe"] == from_asc.models["pns.safe"]
    a, b = run_one(seq_file, from_asc), run_one(seq_file, direct)
    assert (a.state, a.value, a.location) == (b.state, b.value, b.location)
    assert a.value == percent(expected_peak(seq_file, direct), direct)


def test_a_rotation_gives_error(target):
    result = run_one(_with_rotation_library(), target(PASS_SCALE))
    assert result.state is State.ERROR
    assert "NotImplementedError" in result.reason


def test_a_sequence_without_gradients_passes_with_zero(target):
    result = run_one(empty_sequence(), target(FAIL_SCALE))
    assert result.state is State.PASS
    assert result.value == 0.0
    assert result.location is None
    assert (result.model, result.model_version) == ("pns.safe", SAFE_MODEL.version)


@pytest.mark.filterwarnings("ignore:No BlockDurationRaster found:UserWarning")
@pytest.mark.parametrize("name", ["GradientRasterTime", "BlockDurationRaster"])
def test_a_raster_that_the_file_does_not_declare_and_the_target_does_not_give_is_not_evaluated(
    target, seq_file, name
):
    without_definition(seq_file, name)
    result = run_one(seq_file, target(FAIL_SCALE))
    assert result.state is State.NOT_EVALUATED
    assert result.reason == (
        f"the file does not declare {name} and the target 'Test target' does not give "
        f"rasters.{name}"
    )
    assert result.value is None


def test_a_raster_that_the_file_does_not_declare_comes_from_the_target(target, seq_file):
    """The file has a 10 µs gradient raster, and the target gives 4 µs: `pns_levels` uses the
    4 µs, so the value is not the value for 10 µs."""
    without_definition(seq_file, "GradientRasterTime")
    values = {}
    for raster in (4e-6, 10e-6):
        profile = with_raster(target(FAIL_SCALE), "GradientRasterTime", raster)
        result = run_one(seq_file, profile)
        assert result.state is State.FAIL
        assert result.value == percent(expected_peak(seq_file, profile), profile)
        values[raster] = result.value
    assert values[4e-6] != pytest.approx(values[10e-6], rel=1e-3)


def test_a_pass_has_no_findings(target, seq_file):
    result = run_one(seq_file, target(PASS_SCALE))
    assert result.state is State.PASS
    assert result.findings == ()
    assert result.findings_omitted == 0


def test_a_sequence_without_gradients_has_no_findings(target):
    result = run_one(empty_sequence(), target(FAIL_SCALE))
    assert result.findings == ()


def test_a_fail_gives_one_finding_for_each_interval_in_time_order(target):
    seq = gre_sequence(num_trs=2)
    profile = target(FAIL_SCALE)
    result = run_one(seq, profile)
    levels = levels_of(seq, profile)
    index = sequence_index(seq)
    intervals = levels.above[threshold_of(profile)]
    assert result.state is State.FAIL
    assert len(intervals) >= 1
    assert len(result.findings) == len(intervals)
    for finding, interval in zip(result.findings, intervals, strict=True):
        assert finding.code == "PNS_ABOVE_LIMIT"
        assert finding.location.time_s == interval.start_s
        assert finding.location.block == block_at(index, interval.start_s)
        assert finding.data == {
            "start_s": interval.start_s,
            "end_s": interval.end_s,
            "peak_percent": percent(interval.peak_hz_per_t, profile),
            "peak_time_s": interval.peak_time_s,
            "num_samples": interval.num_samples,
        }
        assert finding.message == (
            f"PNS at or above 100 % from {interval.start_s:.6g} s to {interval.end_s:.6g} s, "
            f"peak {percent(interval.peak_hz_per_t, profile):.4g} %"
        )
    times = [finding.location.time_s for finding in result.findings]
    assert times == sorted(times)


def test_the_data_and_the_location_of_a_finding_are_python_scalars(target):
    result = run_one(gre_sequence(num_trs=2), target(FAIL_SCALE))
    assert result.findings
    for finding in result.findings:
        assert type(finding.location.block) is int
        assert type(finding.location.time_s) is float
        for key, value in finding.data.items():
            assert type(value) is (int if key == "num_samples" else float), key


def test_the_value_and_the_location_of_the_result_do_not_change_with_the_findings(target):
    seq = gre_sequence(num_trs=2)
    profile = target(FAIL_SCALE)
    result = run_one(seq, profile)
    levels = levels_of(seq, profile)
    index = sequence_index(seq)
    assert max(f.data["peak_percent"] for f in result.findings) == result.value
    assert result.value == percent(levels.peak_hz_per_t, profile)
    assert (result.limit, result.unit) == (100.0, "%")
    assert result.location.time_s == levels.peak_time_s
    assert result.location.block == block_at(index, levels.peak_time_s)
    assert result.reason is None


def test_two_separate_intervals_give_two_findings_in_time_order(target):
    """The limit scale is the peak of one trapezoid on the example hardware divided by 1.02, so
    that only the larger hump of the total of a trapezoid is at or above 100 %."""
    one, two = two_trapezoids()
    unscaled = target(1.0)
    profile = target(levels_of(one, unscaled).peak_hz_per_t / gamma_of(unscaled) / 1.02)
    assert len(levels_of(one, profile).above[threshold_of(profile)]) == 1
    result = run_one(two, profile)
    index = sequence_index(two)
    intervals = levels_of(two, profile).above[threshold_of(profile)]
    assert len(intervals) == 2
    first, second = result.findings
    assert (first.code, second.code) == ("PNS_ABOVE_LIMIT", "PNS_ABOVE_LIMIT")
    assert [f.location.time_s for f in (first, second)] == [i.start_s for i in intervals]
    assert first.location.time_s < second.location.time_s
    assert first.data["end_s"] < second.data["start_s"]
    assert [f.location.block for f in (first, second)] == [
        block_at(index, i.start_s) for i in intervals
    ]
    assert first.location.block != second.location.block


def test_the_spec_has_the_findings_text():
    spec = SAFE.spec
    assert spec.version == 1
    assert isinstance(spec.findings, str)
    assert "PNS_ABOVE_LIMIT" in spec.findings


def test_the_spec_gives_each_field():
    spec = SAFE.spec
    assert (spec.id, spec.version, spec.models, spec.inputs) == ("pns.safe", 1, ("pns.safe",), ())
    assert spec.cost == "slow"
    assert spec.rasters == ("GradientRasterTime", "BlockDurationRaster")
    assert spec.url is None
    for field in ("title", "quantity", "limit", "tolerance", "pass_condition", "pypulseq"):
        assert getattr(spec, field)
    assert "_safe_gwf_to_pns_chunk" in spec.pypulseq


@pytest.mark.parametrize(
    ("below", "state", "num_findings"), [(False, State.FAIL, 1), (True, State.PASS, 0)]
)
def test_the_state_is_decided_in_hz_per_t_by_the_rule_of_the_findings(
    monkeypatch, target, below, state, num_findings
):
    """A peak exactly at the threshold of the binding (in Hz/T), with its interval in `above`,
    fails with one finding. One float below, with no interval, passes with no finding. The
    check compares in Hz/T by the rule of `PnsLevels.above`, so the state and the findings
    agree."""
    seq = gre_sequence(num_trs=2)
    profile = target(FAIL_SCALE)
    threshold = threshold_of(profile)
    real = levels_of(seq, profile)
    interval = real.above[threshold][0]
    peak = math.nextafter(threshold, 0.0) if below else threshold
    intervals = () if below else (replace(interval, peak_hz_per_t=peak),)
    fake = replace(real, peak_hz_per_t=peak, above={threshold: intervals})
    monkeypatch.setattr(PNS_SAFE_LEVELS, "compute", lambda seq, **kwargs: fake)

    result = run_one(seq, profile)

    assert result.state is state
    assert len(result.findings) == num_findings
    assert result.value == percent(peak, profile)


def test_a_profile_with_another_gamma_converts_with_that_gamma(target, seq_file):
    """The model gives the same peak in Hz/T for each gamma. The check divides it by the
    gamma of the profile, so 40 MHz/T gives 42.576 / 40 times the percent of 42.576 MHz/T."""
    default, other = target(FAIL_SCALE), target(FAIL_SCALE, gamma=GAMMA_40)
    assert gamma_of(other) == GAMMA_40

    a, b = run_one(seq_file, default), run_one(seq_file, other)

    assert b.value == percent(expected_peak(seq_file, other), other)
    assert expected_peak(seq_file, other) == expected_peak(seq_file, default)
    assert b.value / a.value == pytest.approx(GAMMA / GAMMA_40, rel=1e-12)


def test_a_negative_gamma_gives_the_results_of_its_magnitude(target, seq_file):
    """A negative gamma is valid. The PNS values and the limit are magnitudes, so the check
    uses the magnitude of the gamma: -40 MHz/T gives the results of 40 MHz/T, findings too."""
    positive = run_one(seq_file, target(FAIL_SCALE, gamma=GAMMA_40))
    negative = run_one(seq_file, target(FAIL_SCALE, gamma=-GAMMA_40))

    assert negative.state is State.FAIL
    assert negative.value > 0
    assert (negative.state, negative.value, negative.location) == (
        positive.state,
        positive.value,
        positive.location,
    )
    assert negative.findings == positive.findings


def test_a_sequence_object_uses_the_gamma_of_the_gradient_checks(target):
    """D5 of docs/plans/pulseq-analysis-rc5.md: `seq.system` has 40 MHz/T, and the profile
    gives no gamma (42.576 MHz/T). With the limits from the profile, the check divides by the
    gamma of the profile; with the limits from the sequence object, by that of `seq.system`."""
    seq = gre_sequence(num_trs=2)
    seq.system = copy.copy(seq.system)
    seq.system.gamma = GAMMA_40
    profile = target(FAIL_SCALE)
    peak = levels_of(seq, profile).peak_hz_per_t

    from_profile = run_one(seq, profile)
    (from_sequence,) = run_checks(seq, [profile], limits_from_sequence=True).results

    assert from_profile.value == 100 * peak / GAMMA
    assert from_sequence.value == 100 * peak / GAMMA_40
