"""Tests for the check `acoustic.resonance-energy` (plan acoustic-resonance-check, section 4).

Most tests give the check a hand-made `GradientSpectrum` through a fake analysis
`gradient.spectrum`, so that the expected percent is a count of frequencies."""

import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pypulseq as pp
import pytest
from pulseq_analysis import analyses as analysis_module
from pulseq_analysis.grad_spectrum import NO_GRADIENTS, GradientSpectrum
from synthetic import SYSTEM, empty_sequence, gre_sequence, spin_echo_sequence
from test_check_pns import _with_rotation_library
from test_run import FakeAnalysis, make_profile

from pulseq_checks import registry
from pulseq_checks.checks.acoustic import ACOUSTIC_BAND_ENERGY_LIMIT, RESONANCE_ENERGY
from pulseq_checks.profile import read_profile
from pulseq_checks.results import State
from pulseq_checks.rules import RunContext
from pulseq_checks.run import run_checks

PRISMA = Path(__file__).parent / "profiles" / "prisma.toml"
# The bands of prisma.toml.
PRISMA_BANDS = ((590.0, 100.0), (1140.0, 220.0))


@pytest.fixture(autouse=True)
def only_acoustic(monkeypatch):
    """Load the acoustic check only: the other checks are in other modules."""
    monkeypatch.setattr(
        registry, "check_rules", lambda: {"acoustic.resonance-energy": RESONANCE_ENERGY}
    )


def spectrum(rss, step=10.0):
    """A `GradientSpectrum` with the RSS values `rss` at 0, `step`, 2 * `step`, ... Hz, all on
    the axis x. The arguments are those of pypulseq, and `max_frequency_hz` is the last
    frequency."""
    rss = np.asarray(rss, dtype=np.float64)
    zeros = np.zeros_like(rss)
    return GradientSpectrum(
        reason=None,
        frequency_hz=np.arange(len(rss)) * step,
        axes={"x": rss, "y": zeros, "z": zeros},
        rss=rss,
        max_frequency_hz=(len(rss) - 1) * step,
        window_s=0.05,
        frequency_oversampling=3.0,
    )


def target(resonances):
    """A target that gives `resonances` (None: the target does not give them)."""
    profile = make_profile("a")
    if resonances is None:
        return profile
    return replace(
        profile,
        acoustic_resonances=tuple(resonances),
        sources={**profile.sources, "acoustic.resonances": "profile"},
    )


def run_with(value, resonances):
    """The result of the check for a target with `resonances` and the spectrum `value`."""
    fake = FakeAnalysis("gradient.spectrum", value=value)
    ctx = RunContext(spin_echo_sequence(), target(resonances), analyses={"gradient.spectrum": fake})
    return RESONANCE_ENERGY.run(ctx)


def bipolar_train(frequency_hz, num_lobes, weights):
    """Trapezoids of alternate sign, about `frequency_hz` Hz, on the axes of `weights` (axis
    to factor), then 50 ms of nothing. The factors of a rotation give the same |G|."""
    rise = 2e-4
    half = 1 / (2 * frequency_hz)
    flat = round((half - 2 * rise) / SYSTEM.grad_raster_time) * SYSTEM.grad_raster_time
    seq = pp.Sequence(system=SYSTEM)
    for i in range(num_lobes):
        sign = 1 if i % 2 == 0 else -1
        seq.add_block(
            *[
                pp.make_trapezoid(
                    axis,
                    amplitude=sign * w * 10e-3 * SYSTEM.gamma,
                    rise_time=rise,
                    flat_time=flat,
                    system=SYSTEM,
                )
                for axis, w in weights.items()
            ]
        )
    seq.add_block(pp.make_delay(50e-3))
    return seq


def run_real(seq, resonances=PRISMA_BANDS):
    """The result of the check with the real analysis `gradient.spectrum`."""
    return RESONANCE_ENERGY.run(RunContext(seq, target(resonances)))


def test_the_value_is_the_percent_of_the_energy_in_the_band():
    # 201 frequencies 0, 10, ..., 2000 Hz with the same value; the band [540, 640] has 11.
    result = run_with(spectrum(np.ones(201)), [(590.0, 100.0)])
    assert result.state is State.PASS
    assert result.value == pytest.approx(100 * 11 / 201, rel=1e-12)
    assert (result.limit, result.unit, result.location) == (ACOUSTIC_BAND_ENERGY_LIMIT, "%", None)
    assert result.reason == "1 resonance band"
    assert (result.check_id, result.spec_version) == ("acoustic.resonance-energy", 1)


def test_30_percent_passes_and_more_fails():
    # 10 frequencies 0, 10, ..., 90 Hz. The band [10, 30] holds 3 of them: 30 % of the energy.
    assert ACOUSTIC_BAND_ENERGY_LIMIT == 30.0
    result = run_with(spectrum(np.ones(10)), [(20.0, 20.0)])
    assert result.value == 30.0
    assert result.state is State.PASS
    # A bit less energy outside the band: a bit more than 30 % inside.
    rss = np.ones(10)
    rss[9] = 0.999
    result = run_with(spectrum(rss), [(20.0, 20.0)])
    assert result.value == pytest.approx(300 / (9 + 0.999**2), rel=1e-12)
    assert result.value > 30.0
    assert result.state is State.FAIL


def test_the_band_edges_are_closed():
    flat = spectrum(np.ones(10))
    # [10, 30]: the edges are on two frequencies, so 10, 20 and 30 are in the band.
    assert run_with(flat, [(20.0, 20.0)]).value == 30.0
    # [10.01, 29.99]: only 20 is in the band.
    assert run_with(flat, [(20.0, 19.98)]).value == pytest.approx(10.0, rel=1e-12)


def test_the_limit_is_for_all_the_bands_together():
    # Two bands of 2 frequencies each, 20 % each of 10 frequencies: 40 %, a fail.
    bands = [(15.0, 10.0), (65.0, 10.0)]
    result = run_with(spectrum(np.ones(10)), bands)
    assert result.value == pytest.approx(40.0, rel=1e-12)
    assert result.state is State.FAIL
    # The same bands, 10 % each of 20 frequencies: 20 %, a pass.
    result = run_with(spectrum(np.ones(20)), bands)
    assert result.value == pytest.approx(20.0, rel=1e-12)
    assert result.state is State.PASS
    assert result.reason == "2 resonance bands"


def test_a_frequency_in_two_bands_counts_one_time():
    # [10, 30] and [30, 50] share 30 Hz: 5 frequencies, not 6.
    result = run_with(spectrum(np.ones(20)), [(20.0, 20.0), (40.0, 20.0)])
    assert result.value == pytest.approx(25.0, rel=1e-12)


def test_a_fail_has_one_finding_for_all_the_bands():
    result = run_with(spectrum(np.ones(10)), [(15.0, 10.0), (65.0, 10.0)])
    assert result.state is State.FAIL
    (finding,) = result.findings
    assert finding.code == "ACOUSTIC_BAND_ENERGY"
    assert finding.location is None
    assert finding.data == {
        "energy_percent": result.value,
        "limit_percent": 30.0,
        "num_bands": 2,
        "max_frequency_hz": 90.0,
        "window_s": 0.05,
        "frequency_oversampling": 3.0,
    }
    assert finding.message == "40 % of the gradient energy is in the 2 resonance bands (limit 30 %)"


def test_a_pass_has_no_finding():
    result = run_with(spectrum(np.ones(10)), [(15.0, 10.0)])
    assert result.state is State.PASS
    assert result.findings == ()


def test_no_gradient_event_and_no_energy_pass_with_0_percent():
    no_gradients = replace(spectrum(np.zeros(10)), reason=NO_GRADIENTS)
    result = run_with(no_gradients, [(20.0, 20.0)])
    assert (result.state, result.value, result.reason) == (
        State.PASS,
        0.0,
        "no gradient event",
    )
    result = run_with(spectrum(np.zeros(10)), [(20.0, 20.0)])
    assert (result.state, result.value, result.findings) == (State.PASS, 0.0, ())
    # The real analysis for a sequence with no gradient event.
    result = run_real(empty_sequence())
    assert (result.state, result.value) == (State.PASS, 0.0)


def test_an_empty_list_of_resonances_passes_with_0_percent():
    result = run_with(spectrum(np.ones(10)), [])
    assert (result.state, result.value, result.findings) == (State.PASS, 0.0, ())
    assert result.reason == "no resonance band"


def test_a_target_without_resonances_is_not_evaluated():
    (result,) = run_checks(spin_echo_sequence(), [target(None)]).results
    assert result.state is State.NOT_EVALUATED
    assert "acoustic.resonances" in result.reason
    assert result.value is None


def test_a_band_above_the_spectrum_is_not_evaluated():
    # The spectrum ends at 90 Hz. The band [80, 100] reaches above it.
    result = run_with(spectrum(np.ones(10)), [(20.0, 20.0), (90.0, 20.0)])
    assert result.state is State.NOT_EVALUATED
    assert result.value is None
    assert result.reason == (
        "the band 90 Hz, 20 Hz wide reaches 100 Hz, above the spectrum (0 Hz to 90 Hz)"
    )
    # A band that ends at the last frequency is evaluated.
    assert run_with(spectrum(np.ones(10)), [(80.0, 20.0)]).state is State.PASS


def test_a_train_at_a_resonance_fails_and_a_train_at_300_hz_passes():
    # Section 2.3 of the plan: about 98 % and 0.06 %.
    at_resonance = run_real(bipolar_train(1140, 200, {"x": 1.0}))
    assert at_resonance.state is State.FAIL
    assert at_resonance.value > 90
    away = run_real(bipolar_train(300, 60, {"x": 1.0}))
    assert away.state is State.PASS
    assert away.value < 1


def test_a_rotation_of_the_axes_does_not_change_the_value():
    on_x = run_real(bipolar_train(1140, 200, {"x": 1.0}))
    rotated = run_real(bipolar_train(1140, 200, {"x": math.cos(0.6), "y": math.sin(0.6)}))
    assert rotated.value == pytest.approx(on_x.value, rel=1e-9)


def test_the_check_and_the_analysis_result_share_one_spectrum(monkeypatch, tmp_path):
    calls = []
    real = analysis_module.gradient_spectrum_for

    def counted(seq, *args, **kwargs):
        calls.append(seq)
        return real(seq, *args, **kwargs)

    monkeypatch.setattr(analysis_module, "gradient_spectrum_for", counted)
    path = tmp_path / "gre.seq"
    gre_sequence(num_trs=2).write(str(path))
    matrix = run_checks(path, [read_profile(PRISMA)], analyses=["gradient.spectrum"])
    assert len(calls) == 1
    (result,) = matrix.results
    assert result.state is State.PASS
    (analysis,) = matrix.analyses
    assert analysis.series[0].name == "gradient_spectrum"


def test_the_rotation_extension_is_an_error():
    seq = _with_rotation_library()
    (result,) = run_checks(seq, [target(PRISMA_BANDS)]).results
    assert result.state is State.ERROR
    assert "NotImplementedError" in result.reason
