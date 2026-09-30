import dataclasses
import math

import numpy as np
import pypulseq as pp
import pytest
from pypulseq.event_lib import EventLibrary
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from pypulseq.utils.siemens.asc_to_hw import asc_to_hw
from synthetic import (
    SYSTEM,
    arbitrary_gradient_sequence,
    border_sequence,
    empty_sequence,
    gre_sequence,
    spin_echo_sequence,
)

from pulseq_checks.asc import EXAMPLE_HARDWARE, read_gradient_asc
from pulseq_checks.pns_levels import (
    NO_GRADIENTS,
    PEAK_TOLERANCE,
    SAFE_FIELDS,
    SAFE_MODEL,
    PnsLevels,
    _cast_outward,
    bin_samples_for,
    hw_from_dict,
    pns_levels,
)

_HW_FIELDS = ("tau1", "tau2", "tau3", "a1", "a2", "a3", "stim_limit", "g_scale")


def _hw_dict(hw_ns) -> dict:
    return {
        axis: {field: getattr(getattr(hw_ns, axis), field) for field in _HW_FIELDS}
        for axis in "xyz"
    }


def _off_raster_sequence() -> pp.Sequence:
    """A trapezoid on x (so there is a gradient to predict PNS from), followed by a
    delay block whose duration (1.5 gradient-raster steps) pypulseq's `add_block`
    accepts but which is not a whole number of raster steps."""
    dt = SYSTEM.grad_raster_time
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_trapezoid(channel="x", area=1000, system=SYSTEM))
    seq.add_block(pp.make_delay(1.5 * dt))
    return seq


_QUATERNION = (0.9238795325112867, 0.0, 0.0, 0.3826834323650898)  # 45 deg about z


def _with_rotation_library() -> pp.Sequence:
    seq = gre_sequence(num_trs=2)
    seq.rotation_library = EventLibrary()
    seq.rotation_library.insert(1, _QUATERNION)
    return seq


_SEQUENCES = {
    "spin_echo": spin_echo_sequence,
    "gre": gre_sequence,
    "arbitrary_gradient": arbitrary_gradient_sequence,
    "border": border_sequence,
}


@pytest.mark.parametrize("build", _SEQUENCES.values(), ids=_SEQUENCES.keys())
def test_summary_matches_calculate_pns_within_the_fork_tolerance(build):
    """The peak, the peak time and the axis peaks of `pns_levels` (example hardware)
    equal `seq.calculate_pns` of the pinned fork within a relative 1e-6 of the peak
    (`docs/plans/diagram-lanes.md`, section 3.5, item 2).

    The two are not exactly equal: `calc_pns` samples `seq.get_gradients()` at the
    file times `(k + 0.5) * dt`, which drift off the ideal raster grid by float
    rounding of the block start time sums (section 2.3, item 1 of the plan), while
    `pns_levels` samples each block at its own local raster times `(j + 0.5) * dt`
    (`GradientSampler.block_samples`), with no such drift. Both then run the same
    `_safe_gwf_to_pns_chunk`, so the whole difference is that drift.
    """
    seq = build()
    hw = safe_example_hw()
    _, norm, comp, t = seq.calculate_pns(hw, do_plots=False)
    ref_peak = float(norm.max())
    threshold = ref_peak * (1 - PEAK_TOLERANCE)
    ref_peak_time = float(t[int(np.flatnonzero(norm >= threshold)[0])])
    ref_axis_peaks = {axis: float(comp[:, i].max()) for i, axis in enumerate("xyz")}

    levels = pns_levels(seq)
    tol = 1e-6 * ref_peak

    assert levels.reason is None
    assert levels.hardware == EXAMPLE_HARDWARE
    assert levels.asc_file is None
    assert levels.dt_s == seq.grad_raster_time
    assert levels.on_raster is True
    assert levels.peak == pytest.approx(ref_peak, abs=tol)
    assert levels.peak_time_s == pytest.approx(ref_peak_time, abs=1e-9)
    for axis in "xyz":
        assert levels.axis_peaks[axis] == pytest.approx(ref_axis_peaks[axis], abs=tol)


@pytest.mark.parametrize("build", _SEQUENCES.values(), ids=_SEQUENCES.keys())
def test_stored_bins_match_calculate_pns_totals(build):
    """Each stored bin's minimum and maximum equal the minimum and the maximum of
    `seq.calculate_pns`'s totals over the same samples, within the same 1e-6-of-peak
    tolerance as `test_summary_matches_calculate_pns_within_the_fork_tolerance` (same
    reason: the file-time drift of `calc_pns`'s own gradient sampling).

    `calc_pns`'s own array can be shorter than `pns_levels`'s (a trailing block with no
    gradient event, for example `gre_sequence`'s TR padding, extends `pns_levels`'s
    sample count, and its bins, past the last gradient sample `calc_pns` used, into the
    filters' own decay); only a bin that lies entirely inside `calc_pns`'s array is
    compared, so that a bin straddling the end of that array (part of it decaying past
    where `calc_pns` stopped, part of it inside) is not mistaken for a mismatch.
    """
    seq = build()
    hw = safe_example_hw()
    _, norm, _, _ = seq.calculate_pns(hw, do_plots=False)
    levels = pns_levels(seq)
    tol = 1e-6 * levels.peak
    nt_ref = norm.shape[0]
    bin_samples = levels.bin_samples
    compared = 0

    for i in range(len(levels.level_min)):
        s0 = i * bin_samples
        s1 = min(s0 + bin_samples, levels.num_samples)  # the last bin can be shorter
        if s1 > nt_ref:
            break
        segment = norm[s0:s1]
        assert float(levels.level_min[i]) == pytest.approx(float(segment.min()), abs=tol)
        assert float(levels.level_max[i]) == pytest.approx(float(segment.max()), abs=tol)
        compared += 1
    assert compared > 0


def test_cast_outward_bounds_every_input_value():
    """`_cast_outward` (the float32 rounding of item 4 of `pns_levels`'s docstring)
    never lands on the wrong side of its float64 input: the downward cast (used for a
    bin's minimum) is at most the input, and the upward cast (used for a maximum) is
    at least the input, for values that generally fall strictly between two
    representable float32 numbers."""
    rng = np.random.default_rng(0)
    values = rng.uniform(-1000.0, 1000.0, size=2000)
    down = _cast_outward(values, down=True)
    up = _cast_outward(values, down=False)
    assert down.dtype == np.float32
    assert up.dtype == np.float32
    assert np.all(down.astype(np.float64) <= values)
    assert np.all(up.astype(np.float64) >= values)


def test_bin_samples_for_matches_the_formula():
    """`bin_samples_for` follows `max(floor(EXACT_MAX_S / (2 * DISPLAY_BINS) / dt),
    ceil(num_samples / MAX_BINS), 1)`: 615 samples at the 10 us raster for any file of
    up to 1,230,000,000 samples (`615 * MAX_BINS`), and a coarser bin for a larger
    file, computed from `num_samples` alone. A `pns_levels` call on a real sequence
    also follows the same formula, and gives that many bins."""
    dt = 1e-5
    assert bin_samples_for(0, dt) == 615
    assert bin_samples_for(1_230_000_000, dt) == 615
    assert bin_samples_for(1_230_000_001, dt) == 616
    assert bin_samples_for(2_000_000_000, dt) == 1000
    assert bin_samples_for(0, 2e-5) == 307

    levels = pns_levels(gre_sequence(num_trs=6))
    assert levels.bin_samples == bin_samples_for(levels.num_samples, levels.dt_s)
    assert len(levels.level_min) == -(-levels.num_samples // levels.bin_samples)  # ceil division
    assert len(levels.level_max) == len(levels.level_min)


def test_result_does_not_depend_on_chunk_samples(monkeypatch):
    """The stored level and the summary do not depend on the chunk size: the fork's
    chunk function is exact for any chunk size (`docs/plans/diagram-lanes.md`, section
    2.6, item 2), so a difference would be an error of this library's own binning, not
    of the fork. The test sets `CHUNK_SAMPLES` of `pulseq_checks.pns_levels`, and
    `pns_levels` rounds the chunk up to a whole number of bins: 1 gives a chunk of 1 bin,
    `bin_samples + 1` gives 2, and `7 * bin_samples - 1` gives 7."""
    seq = gre_sequence(num_trs=20)
    reference = pns_levels(seq)
    bin_samples = reference.bin_samples
    assert reference.num_samples > bin_samples * 7  # so the smallest case has > 1 chunk

    sizes = [1, bin_samples + 1, 7 * bin_samples - 1]
    sizes.append(bin_samples * (reference.num_samples // bin_samples + 10))  # > the whole file

    for chunk_samples in sizes:
        monkeypatch.setattr("pulseq_checks.pns_levels.CHUNK_SAMPLES", chunk_samples)
        got = pns_levels(seq)
        assert np.array_equal(got.level_min, reference.level_min)
        assert np.array_equal(got.level_max, reference.level_max)
        assert got.peak == reference.peak
        assert got.peak_time_s == reference.peak_time_s
        assert got.axis_peaks == reference.axis_peaks
        assert got.num_samples == reference.num_samples
        assert got.bin_samples == reference.bin_samples


def test_no_gradients():
    """A sequence with no gradient event gives `reason=NO_GRADIENTS`, no stored
    bins, a peak of 0 and `peak_time_s` of None, but still the chosen hardware."""
    levels = pns_levels(empty_sequence())
    assert levels.reason == NO_GRADIENTS
    assert levels.hardware == EXAMPLE_HARDWARE
    assert levels.asc_file is None
    assert levels.level_min.shape == (0,)
    assert levels.level_max.shape == (0,)
    assert levels.peak == 0.0
    assert levels.peak_time_s is None
    assert levels.axis_peaks == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert levels.hw == _hw_dict(safe_example_hw())


def test_off_raster_block_falls_back_to_sampling():
    """A file with a block that is not on the gradient raster (`pp.make_delay(1.5 *
    dt)`, which pypulseq's `add_block` accepts) is reported as `on_raster=False`, and
    its summary equals `seq.calculate_pns` within a relative 1e-9 of the peak: both
    sample with `GradientSampler.sample`/`seq.get_gradients()` at the same file times
    now (`docs/plans/cards-at-scale.md`'s `test_sampling.py` established that the two
    agree to about float rounding), so no drift-based tolerance is needed here."""
    seq = _off_raster_sequence()
    hw = safe_example_hw()
    _, norm, comp, t = seq.calculate_pns(hw, do_plots=False)
    ref_peak = float(norm.max())
    tol = 1e-9 * ref_peak

    levels = pns_levels(seq)
    assert levels.on_raster is False
    # pns_levels covers the whole sequence; calculate_pns stops at the last gradient point.
    assert levels.num_samples >= norm.size
    assert levels.peak == pytest.approx(ref_peak, abs=tol)
    threshold = ref_peak * (1 - PEAK_TOLERANCE)
    ref_peak_time = float(t[int(np.flatnonzero(norm >= threshold)[0])])
    assert levels.peak_time_s == pytest.approx(ref_peak_time, abs=1e-9)
    for i, axis in enumerate("xyz"):
        assert levels.axis_peaks[axis] == pytest.approx(float(comp[:, i].max()), abs=tol)


@pytest.fixture
def write_gradient_asc(tmp_path):
    """A gradient .asc file with the PNS parameters of pypulseq's example hardware
    (the same technique as `test_pns.py`'s fixture of the same name: real .asc files
    are confidential, so this one is built from pypulseq's own public example
    hardware, not copied from a real scanner file)."""

    def write(name: str = "MP_GPA_TEST"):
        hw = safe_example_hw()
        lines = [f'asCOMP.tName = "{name}"']
        for axis in "xyz":
            a, suffix = getattr(hw, axis), axis.upper()
            lines += [f"flGSWDTau{suffix}[{i}] = {getattr(a, f'tau{i + 1}')!r}" for i in range(3)]
            lines += [f"flGSWDA{suffix}[{i}] = {getattr(a, f'a{i + 1}')!r}" for i in range(3)]
            lines += [
                f"flGSWDStimulationLimit{suffix} = {a.stim_limit!r}",
                f"flGSWDStimulationThreshold{suffix} = {a.stim_thresh!r}",
            ]
            lines.append(f"asGPAParameters[0].sGCParameters.flGScaleFactor{suffix} = {a.g_scale!r}")
        path = tmp_path / f"{name}.asc"
        path.write_text("\n".join(lines) + "\n")
        return path

    return write


def test_asc_hardware_file_is_used_for_the_levels(write_gradient_asc):
    """`pns_levels` reads the hardware name and the 8 kept fields of each axis from the
    given gradient .asc file, instead of the example hardware, and its stored level
    and summary then equal the default (example-hardware) call exactly: this .asc file
    encodes the example hardware's own numbers."""
    seq = spin_echo_sequence()
    path = write_gradient_asc()
    levels = pns_levels(seq, gradient_asc=path)
    assert levels.hardware == "MP_GPA_TEST"
    assert levels.asc_file == path.name
    assert levels.hw == _hw_dict(safe_example_hw())

    default = pns_levels(seq)
    assert np.array_equal(levels.level_min, default.level_min)
    assert np.array_equal(levels.level_max, default.level_max)
    assert levels.peak == default.peak
    assert levels.peak_time_s == default.peak_time_s


def test_pns_levels_refuses_rotations():
    """`pns_levels` raises `NotImplementedError` for a sequence with a rotation
    library, as `gradient_limits` does (`extensions.refuse_rotations`)."""
    with pytest.raises(NotImplementedError, match="rotation extension"):
        pns_levels(_with_rotation_library())


def test_pns_levels_is_a_frozen_dataclass():
    """`pns_levels` returns a `PnsLevels` instance (a smoke test of the interface, not
    of a specific field: the other tests of this module check the fields)."""
    assert isinstance(pns_levels(spin_echo_sequence()), PnsLevels)


def _assert_levels_equal(a: PnsLevels, b: PnsLevels, *, ignore: tuple[str, ...]) -> None:
    """Every field of `a` and `b` is exactly equal, except the fields named in `ignore`
    (`numpy.array_equal` for the arrays, `==` for the rest)."""
    for field in dataclasses.fields(PnsLevels):
        if field.name in ignore:
            continue
        x, y = getattr(a, field.name), getattr(b, field.name)
        if isinstance(x, np.ndarray):
            assert np.array_equal(x, y), field.name
        else:
            assert x == y, field.name


def test_hardware_with_the_example_struct_gives_the_default_levels():
    """`hardware=(safe_example_hw(), label)` gives the levels of the default call, except
    the hardware name, which is the label, exactly, for a sequence on the raster and for
    one off it."""
    for seq in (spin_echo_sequence(), _off_raster_sequence()):
        default = pns_levels(seq)
        levels = pns_levels(seq, hardware=(safe_example_hw(), "LABEL"))
        assert levels.hardware == "LABEL"
        assert levels.asc_file is None
        _assert_levels_equal(levels, default, ignore=("hardware",))


def test_hardware_from_an_asc_file_gives_the_levels_of_the_file(write_gradient_asc):
    """`hardware=(asc_to_hw(read_gradient_asc(path)), label)` gives the levels of
    `gradient_asc=path`, except the hardware name (the label) and `asc_file` (None)."""
    seq = spin_echo_sequence()
    path = write_gradient_asc()
    from_file = pns_levels(seq, gradient_asc=path)
    levels = pns_levels(seq, hardware=(asc_to_hw(read_gradient_asc(path)), "LABEL"))
    assert from_file.asc_file == path.name
    assert levels.hardware == "LABEL"
    assert levels.asc_file is None
    _assert_levels_equal(levels, from_file, ignore=("hardware", "asc_file"))


def test_pns_levels_refuses_both_gradient_asc_and_hardware(write_gradient_asc):
    """`pns_levels` with `gradient_asc` and `hardware` together raises `ValueError`."""
    with pytest.raises(ValueError, match="not both"):
        pns_levels(
            spin_echo_sequence(),
            gradient_asc=write_gradient_asc(),
            hardware=(safe_example_hw(), "LABEL"),
        )


def _safe_dict(name: str | None = "MP_GPA_EXAMPLE") -> dict:
    """The parameters of `safe_example_hw()` as the dict of `SAFE_MODEL.read`, with the
    `name` when it is not None."""
    hw = safe_example_hw()
    params = {"name": name} if name is not None else {}
    for axis in "xyz":
        params[axis] = {field: getattr(getattr(hw, axis), field) for field in SAFE_FIELDS}
    return params


def test_safe_model_reads_a_valid_dict():
    """`SAFE_MODEL.read` of the example parameters gives an equal new dict of floats, and
    the model has the name `pns.safe` and the version 1. An int is read as a float, and
    `name` is optional."""
    assert SAFE_MODEL.name == "pns.safe"
    assert SAFE_MODEL.version == 1
    params = _safe_dict()
    result = SAFE_MODEL.read(params)
    assert result == params
    assert result is not params
    assert result["x"] is not params["x"]
    assert all(type(v) is float for axis in "xyz" for v in result[axis].values())

    assert "name" not in SAFE_MODEL.read(_safe_dict(name=None))
    params["y"]["stim_limit"] = 15  # an int
    read = SAFE_MODEL.read(params)["y"]["stim_limit"]
    assert read == 15.0
    assert type(read) is float


@pytest.mark.parametrize(
    ("edit", "key"),
    [
        (lambda p: p.update(extra=1.0), "extra"),
        (lambda p: p["z"].update(tau4=1.0), "z.tau4"),
    ],
    ids=["axis level", "field level"],
)
def test_safe_model_refuses_an_unknown_key(edit, key):
    """`SAFE_MODEL.read` raises `ValueError` that names an unknown key (with its axis for
    a field)."""
    params = _safe_dict()
    edit(params)
    with pytest.raises(ValueError, match="unknown key") as info:
        SAFE_MODEL.read(params)
    assert key in str(info.value)


def test_safe_model_refuses_a_missing_field_or_axis():
    """`SAFE_MODEL.read` raises `ValueError` that names a missing field (with its axis)
    or a missing axis."""
    params = _safe_dict()
    del params["y"]["a2"]
    with pytest.raises(ValueError, match="missing key 'y.a2'"):
        SAFE_MODEL.read(params)

    params = _safe_dict()
    del params["z"]
    with pytest.raises(ValueError, match="missing key 'z'"):
        SAFE_MODEL.read(params)


@pytest.mark.parametrize("value", [True, False, "1.0", None, [1.0], math.nan, math.inf, -math.inf])
def test_safe_model_refuses_a_value_that_is_not_a_real_number(value):
    """`SAFE_MODEL.read` raises `ValueError` that names the key of a field whose value is a
    bool, another type that is not an int or a float, or a float that is not finite; a
    `name` that is not a str raises too."""
    params = _safe_dict()
    params["x"]["tau2"] = value
    with pytest.raises(ValueError, match=r"x\.tau2"):
        SAFE_MODEL.read(params)

    params = _safe_dict(name=None)
    params["name"] = 1
    with pytest.raises(ValueError, match="name"):
        SAFE_MODEL.read(params)


def test_hw_from_dict_gives_the_example_hardware():
    """`hw_from_dict(SAFE_MODEL.read(params))` has the name and the 27 values of
    `safe_example_hw()`, "unknown" without a name, and used as `hardware` it gives the
    levels of the example hardware exactly (except the label)."""
    hw = hw_from_dict(SAFE_MODEL.read(_safe_dict()))
    example = safe_example_hw()
    assert hw.name == example.name
    for axis in "xyz":
        for field in SAFE_FIELDS:
            assert getattr(getattr(hw, axis), field) == getattr(getattr(example, axis), field)
    assert hw_from_dict(SAFE_MODEL.read(_safe_dict(name=None))).name == "unknown"

    seq = spin_echo_sequence()
    levels = pns_levels(seq, hardware=(hw, "LABEL"))
    _assert_levels_equal(levels, pns_levels(seq), ignore=("hardware",))
