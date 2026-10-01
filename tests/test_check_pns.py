from dataclasses import replace

import pypulseq as pp
import pytest
from pulseq_analysis.pns import pns_levels_for
from pulseq_analysis.pns_levels import PNS_LIMIT
from pulseq_analysis.seq_index import sequence_index
from pypulseq.event_lib import EventLibrary
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from synthetic import SYSTEM, empty_sequence, gre_sequence
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
    """A function: the profile of an `.asc` file with the limits multiplied by `scale`."""

    def make(scale):
        asc = write_gradient_asc(limit_scale=scale)
        return read_profile(write_profile(tmp_path, [f'asc = "{asc.name}"']))

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


def expected_peak(seq_file, profile):
    """The peak of `pns_levels_for` for the `.seq` file read with the `Opts` of `profile`, as
    `run_checks` reads it, and the SAFE parameters of `profile`."""
    seq = pp.Sequence(system=profile.make_opts())
    seq.read(str(seq_file))
    params = profile.models["pns.safe"]
    return pns_levels_for(seq, hardware=(hw_from_dict(params), params["name"])).peak


def levels_of(seq, profile):
    """The `PnsLevels` of `seq` for the SAFE parameters of `profile`, as `run_checks` gets them."""
    params = profile.models["pns.safe"]
    return pns_levels_for(seq, hardware=(hw_from_dict(params), params["name"]))


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
    assert (peak < 1) == (state is State.PASS)
    assert result.value == 100 * peak
    assert (result.limit, result.unit) == (100.0, "%")
    assert (result.model, result.model_version) == ("pns.safe", SAFE_MODEL.version)
    assert result.check_id == "pns.safe"
    assert result.spec_version == 1


def test_the_location_is_the_block_of_the_peak(target, seq_file):
    profile = target(FAIL_SCALE)
    result = run_one(seq_file, profile)
    seq = gre_sequence(num_trs=2)
    params = profile.models["pns.safe"]
    levels = pns_levels_for(seq, hardware=(hw_from_dict(params), params["name"]))
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
    assert a.value == 100 * expected_peak(seq_file, direct)


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
        assert result.value == 100 * expected_peak(seq_file, profile)
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
    assert result.state is State.FAIL
    assert len(levels.above[PNS_LIMIT]) >= 1
    assert len(result.findings) == len(levels.above[PNS_LIMIT])
    for finding, interval in zip(result.findings, levels.above[PNS_LIMIT], strict=True):
        assert finding.code == "PNS_ABOVE_LIMIT"
        assert finding.location.time_s == interval.start_s
        assert finding.location.block == block_at(index, interval.start_s)
        assert finding.data == {
            "start_s": interval.start_s,
            "end_s": interval.end_s,
            "peak_percent": 100 * interval.peak,
            "peak_time_s": interval.peak_time_s,
            "num_samples": interval.num_samples,
        }
        assert finding.message == (
            f"PNS at or above 100 % from {interval.start_s:.6g} s to {interval.end_s:.6g} s, "
            f"peak {100 * interval.peak:.4g} %"
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
    assert result.value == 100 * levels.peak
    assert (result.limit, result.unit) == (100.0, "%")
    assert result.location.time_s == levels.peak_time_s
    assert result.location.block == block_at(index, levels.peak_time_s)
    assert result.reason is None


def test_two_separate_intervals_give_two_findings_in_time_order(target):
    """The limit scale is the peak of one trapezoid on the example hardware divided by 1.02, so
    that only the larger hump of the total of a trapezoid is at or above 100 %."""
    one, two = two_trapezoids()
    profile = target(levels_of(one, target(1.0)).peak / 1.02)
    assert len(levels_of(one, profile).above[PNS_LIMIT]) == 1
    result = run_one(two, profile)
    index = sequence_index(two)
    levels = levels_of(two, profile)
    assert len(levels.above[PNS_LIMIT]) == 2
    first, second = result.findings
    assert (first.code, second.code) == ("PNS_ABOVE_LIMIT", "PNS_ABOVE_LIMIT")
    assert [f.location.time_s for f in (first, second)] == [
        i.start_s for i in levels.above[PNS_LIMIT]
    ]
    assert first.location.time_s < second.location.time_s
    assert first.data["end_s"] < second.data["start_s"]
    assert [f.location.block for f in (first, second)] == [
        block_at(index, i.start_s) for i in levels.above[PNS_LIMIT]
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
