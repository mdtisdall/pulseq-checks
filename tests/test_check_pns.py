import pypulseq as pp
import pytest
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from synthetic import empty_sequence, gre_sequence
from test_asc_profile import FIELDS, write_profile
from test_extensions import _with_rotation_library

from pulseq_checks import registry
from pulseq_checks.checks.pns import SAFE
from pulseq_checks.pns import pns_levels_for
from pulseq_checks.pns_levels import SAFE_MODEL, hw_from_dict
from pulseq_checks.profile import read_profile
from pulseq_checks.results import State
from pulseq_checks.run import run_checks
from pulseq_checks.seq_index import sequence_index

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


def expected_peak(seq_file, profile):
    """The peak of `pns_levels_for` for the `.seq` file read with the `Opts` of `profile`, as
    `run_checks` reads it, and the SAFE parameters of `profile`."""
    seq = pp.Sequence(system=profile.make_opts())
    seq.read(str(seq_file))
    params = profile.models["pns.safe"]
    return pns_levels_for(seq, hardware=(hw_from_dict(params), params["name"])).peak


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


def test_the_spec_gives_each_field():
    spec = SAFE.spec
    assert (spec.id, spec.version, spec.models, spec.inputs) == ("pns.safe", 1, ("pns.safe",), ())
    assert spec.cost == "slow"
    assert spec.url is None
    for field in ("title", "quantity", "limit", "tolerance", "pass_condition", "pypulseq"):
        assert getattr(spec, field)
    assert "_safe_gwf_to_pns_chunk" in spec.pypulseq
