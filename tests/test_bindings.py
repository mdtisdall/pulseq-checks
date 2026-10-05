"""Tests for `pulseq_checks.bindings`: the arguments that each binding gives to `compute`, and
the reasons that `unavailable` gives."""

import dataclasses

import pypulseq as pp
from pulseq_analysis.grad_limits import gradient_limits
from pulseq_analysis.pns_levels import PNS_LIMIT
from synthetic import spin_echo_sequence
from test_run import FakeAnalysis, make_profile, safe_params, safe_profile

from pulseq_checks import registry
from pulseq_checks.bindings import (
    BINDINGS,
    Binding,
    gamma,
    gamma_magnitude,
    pns_threshold_hz_per_t,
    unavailable,
)
from pulseq_checks.rules import RunContext
from pulseq_checks.safe_model import hw_from_dict

# The gamma of a profile and of a sequence object, in Hz/T: neither is the pypulseq default.
PROFILE_GAMMA = 40e6
SEQUENCE_GAMMA = 43e6


def pns_context(**kwargs):
    """A context for a sequence object and a target with the SAFE parameters."""
    return RunContext(spin_echo_sequence(), safe_profile(), **kwargs)


def test_each_analysis_of_pulseq_analysis_but_gradient_spectrum_has_a_binding():
    analyses = registry.analyses()
    assert set(BINDINGS) == set(analyses) - {"gradient.spectrum"}
    assert analyses["gradient.spectrum"].spec.params == ()
    assert BINDINGS["seq.index"] == Binding()
    assert BINDINGS["gradient.limits"].inputs == ()
    assert BINDINGS["gradient.limits"].models == ()
    assert BINDINGS["gradient.blocks"].inputs == ()
    assert BINDINGS["gradient.blocks"].models == ()
    assert BINDINGS["pns.safe.levels"].inputs == ()
    assert BINDINGS["pns.safe.levels"].models == ("pns.safe",)
    assert Binding().arguments(pns_context()) == {}
    assert BINDINGS["seq.index"].arguments(pns_context()) == {}


def test_each_binding_gives_the_parameters_of_its_analysis():
    ctx = pns_context()
    analyses = registry.analyses()
    for analysis_id, binding in BINDINGS.items():
        assert set(binding.arguments(ctx)) == set(analyses[analysis_id].spec.params), analysis_id


def test_the_gamma_is_the_gamma_of_the_profile_and_the_gradient_analyses_take_no_argument():
    profile = make_profile(opts={"gamma": PROFILE_GAMMA})
    ctx = RunContext(spin_echo_sequence(), profile)
    assert gamma(ctx) == PROFILE_GAMMA
    for analysis_id in ("gradient.limits", "gradient.blocks"):
        assert BINDINGS[analysis_id].arguments(ctx) == {}


def test_the_gamma_of_a_sequence_object_with_the_limits_from_it_is_the_gamma_of_the_sequence():
    """The gamma that converts the limits, not the gamma of the profile (decision P3)."""
    system = pp.Opts(
        max_grad=28, grad_unit="mT/m", max_slew=150, slew_unit="T/m/s", gamma=SEQUENCE_GAMMA
    )
    seq = pp.Sequence(system)
    seq.add_block(pp.make_trapezoid(channel="x", area=1000, system=system))
    assert seq.system.gamma == SEQUENCE_GAMMA
    profile = make_profile(opts={"gamma": PROFILE_GAMMA})
    ctx = RunContext(seq, profile, limits_source="sequence object")
    assert gamma(ctx) == SEQUENCE_GAMMA
    for analysis_id in ("gradient.limits", "gradient.blocks"):
        assert BINDINGS[analysis_id].arguments(ctx) == {}
    # The analysis takes no gamma: the checks convert its values with the gamma.
    assert ctx.analysis("gradient.limits") == gradient_limits(seq)
    # With the limits of the profile, the same sequence gets the gamma of the profile.
    assert gamma(RunContext(seq, profile)) == PROFILE_GAMMA


def test_the_binding_of_pns_safe_levels_gives_the_safe_hardware_and_the_stimulation_threshold():
    ctx = pns_context()
    arguments = BINDINGS["pns.safe.levels"].arguments(ctx)
    assert set(arguments) == {"hardware", "thresholds_hz_per_t"}
    hardware, label = arguments["hardware"]
    assert hardware == hw_from_dict(safe_params())
    assert label == "MP_GPA_EXAMPLE"
    # The stimulation limit in Hz/T: 1 (a fraction) times the gamma of pypulseq.
    assert PNS_LIMIT == 1.0
    assert arguments["thresholds_hz_per_t"] == (pns_threshold_hz_per_t(ctx),) == (42.576e6,)


def test_a_negative_gamma_is_signed_in_gamma_and_positive_in_its_magnitude_and_the_threshold():
    """A negative gamma is valid. `gamma` keeps its sign, and `gamma_magnitude` and the PNS
    threshold of the binding (which pulseq-analysis requires above 0) use its magnitude, for
    the gamma of a profile and of a sequence object with the limits from it."""
    profile = make_profile(opts={"gamma": -PROFILE_GAMMA})
    system = pp.Opts(
        max_grad=28, grad_unit="mT/m", max_slew=150, slew_unit="T/m/s", gamma=-SEQUENCE_GAMMA
    )
    from_profile = RunContext(spin_echo_sequence(), profile)
    from_sequence = RunContext(pp.Sequence(system), profile, limits_source="sequence object")
    for ctx, expected in ((from_profile, PROFILE_GAMMA), (from_sequence, SEQUENCE_GAMMA)):
        assert gamma(ctx) == -expected
        assert gamma_magnitude(ctx) == expected
        assert pns_threshold_hz_per_t(ctx) == PNS_LIMIT * expected > 0


def test_the_label_of_the_safe_hardware_is_the_source_of_the_model_without_a_name():
    params = safe_params()
    del params["name"]
    profile = dataclasses.replace(
        safe_profile(), models={"pns.safe": params}, sources={"models.pns.safe": "x.asc"}
    )
    hardware, label = BINDINGS["pns.safe.levels"].arguments(
        RunContext(spin_echo_sequence(), profile)
    )["hardware"]
    assert label == "x.asc"
    assert hardware == hw_from_dict(params)
    assert hardware.name == "unknown"


def test_each_analysis_is_available_for_a_target_that_gives_its_values():
    ctx = pns_context()
    for analysis_id, analysis in registry.analyses().items():
        assert unavailable(ctx, analysis) == [], analysis_id


def test_a_target_without_the_model_makes_pns_safe_levels_unavailable():
    ctx = RunContext(spin_echo_sequence(), make_profile("scanner"))
    analyses = registry.analyses()
    assert unavailable(ctx, analyses["pns.safe.levels"]) == [
        "for the analysis pns.safe.levels, the target 'scanner' does not give: model pns.safe"
    ]
    for analysis_id in ("seq.index", "gradient.limits", "gradient.blocks", "gradient.spectrum"):
        assert unavailable(ctx, analyses[analysis_id]) == []


def test_an_input_that_the_target_does_not_give_is_a_reason_and_one_that_it_gives_is_not(
    monkeypatch,
):
    monkeypatch.setitem(
        BINDINGS, "t.in", Binding(inputs=("opts.max_grad", "opts.max_slew"), models=("m.one",))
    )
    analysis = FakeAnalysis("t.in")
    ctx = RunContext(spin_echo_sequence(), make_profile("x", inputs=("opts.max_grad",)))
    assert unavailable(ctx, analysis) == [
        "for the analysis t.in, the target 'x' does not give: input opts.max_slew, model m.one"
    ]
    target = make_profile("x", inputs=("opts.max_grad", "opts.max_slew"), models=("m.one",))
    assert unavailable(RunContext(spin_echo_sequence(), target), analysis) == []
    # The limits of a sequence object give both limits.
    ctx = RunContext(
        spin_echo_sequence(), make_profile("x", models=("m.one",)), limits_source="sequence object"
    )
    assert unavailable(ctx, analysis) == []


def test_a_raster_that_is_a_pypulseq_default_is_a_reason_for_the_analyses_that_use_it():
    sources = {
        "GradientRasterTime": "file",
        "RadiofrequencyRasterTime": "pypulseq default",
        "AdcRasterTime": "pypulseq default",
        "BlockDurationRaster": "target",
    }
    ctx = RunContext(spin_echo_sequence(), safe_profile(), raster_sources=sources)
    analyses = registry.analyses()
    assert [unavailable(ctx, analyses[i]) for i in sorted(analyses)] == [[]] * 5
    fake = FakeAnalysis("t.r", rasters=("GradientRasterTime", "AdcRasterTime"))
    assert unavailable(ctx, fake) == [
        (
            "for the analysis t.r, the file does not declare AdcRasterTime and the target 'a' "
            "does not give rasters.AdcRasterTime"
        )
    ]
    sources["GradientRasterTime"] = "pypulseq default"
    ctx = RunContext(spin_echo_sequence(), safe_profile(), raster_sources=sources)
    assert unavailable(ctx, analyses["seq.index"]) == []
    for analysis_id in (
        "gradient.limits",
        "gradient.blocks",
        "gradient.spectrum",
        "pns.safe.levels",
    ):
        assert unavailable(ctx, analyses[analysis_id]) == [
            (
                f"for the analysis {analysis_id}, the file does not declare GradientRasterTime "
                "and the target 'a' does not give rasters.GradientRasterTime"
            )
        ]


def test_an_analysis_without_a_binding_is_unavailable_only_when_it_has_parameters():
    ctx = pns_context()
    assert unavailable(ctx, FakeAnalysis("t.plain")) == []
    assert unavailable(ctx, FakeAnalysis("t.params", params=("p", "q"))) == [
        "for the analysis t.params, pulseq-checks has no binding for its parameters p, q"
    ]


def test_each_reason_that_applies_is_in_the_list():
    ctx = RunContext(
        spin_echo_sequence(),
        make_profile("x"),
        raster_sources={"GradientRasterTime": "pypulseq default"},
    )
    reasons = unavailable(ctx, registry.analyses()["pns.safe.levels"])
    assert len(reasons) == 2
    assert "model pns.safe" in reasons[0]
    assert "GradientRasterTime" in reasons[1]
    assert all("pns.safe.levels" in reason for reason in reasons)
