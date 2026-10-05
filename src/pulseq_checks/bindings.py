"""The bindings of the analyses of pulseq-analysis (design section 4.5): what an analysis
needs from the target, and the keyword arguments of its `compute`.

`analyses.registry()` of pulseq-analysis gives the analyses, and each one has a
`spec.params`, the names of the arguments of `compute`. pulseq-checks gives their values
from the target. `BINDINGS` has one `Binding` for each analysis of pulseq-analysis except
`gradient.spectrum`; the binding of an analysis that needs no value of the target is
`Binding()`. No analysis takes a gamma: the checks convert with `gamma_magnitude`. An
analysis that has no binding here is available only when its `spec.params` is empty
(`unavailable`). `RunContext.analysis` and `run_checks` use the
bindings."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pulseq_analysis.pns_levels import PNS_LIMIT

from .safe_model import hw_from_dict

if TYPE_CHECKING:
    from pulseq_analysis.analyses import Analysis

    from .rules import RunContext


def _no_arguments(ctx: RunContext) -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class Binding:
    """What an analysis needs from the target. `inputs` and `models` are the paths and the
    model names that the target must give, as in `CheckSpec`. `arguments` gives the keyword
    arguments of `compute` from the `RunContext`; its keys are the `spec.params` of the
    analysis. The default gives no argument."""

    inputs: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    arguments: Callable[[RunContext], dict[str, Any]] = _no_arguments


def gamma(ctx: RunContext) -> float:
    """The gamma, in Hz/T, of the target of `ctx`: `seq.system.gamma` when the gradient limits
    come from the sequence object, else the gamma of the `Opts` of the profile. It is the
    gamma that converts the gradient limits. It is signed, and a negative gamma is valid. No
    analysis uses it: to convert a value of an analysis, use `gamma_magnitude`."""
    if ctx.limits_source == "sequence object":
        return ctx.sequence.system.gamma
    return ctx.profile.make_opts().gamma


def gamma_magnitude(ctx: RunContext) -> float:
    """`abs(gamma(ctx))`, in Hz/T. Each limit of a check (max_grad, max_slew, the PNS
    stimulation limit) and each value that a check compares with it is a magnitude, so the
    checks convert the Hz values of the analyses with the magnitude of the gamma."""
    return abs(gamma(ctx))


def pns_threshold_hz_per_t(ctx: RunContext) -> float:
    """The PNS stimulation limit of the target of `ctx`, in Hz/T: `PNS_LIMIT` (a fraction)
    times `gamma_magnitude(ctx)`. The binding of `pns.safe.levels` gives it as the one
    threshold, and a check indexes `PnsLevels.above` with this same float."""
    return PNS_LIMIT * gamma_magnitude(ctx)


def _pns_safe_arguments(ctx: RunContext) -> dict[str, Any]:
    """The SAFE hardware of the model `pns.safe` of the target, with the name in the model or
    the label of the source of the model, and the stimulation limit as the one threshold."""
    params = ctx.profile.models["pns.safe"]
    label = params.get("name") or ctx.profile.sources["models.pns.safe"]
    return {
        "hardware": (hw_from_dict(params), label),
        "thresholds_hz_per_t": (pns_threshold_hz_per_t(ctx),),
    }


BINDINGS: Mapping[str, Binding] = {
    "seq.index": Binding(),
    "gradient.limits": Binding(),
    "gradient.blocks": Binding(),
    "pns.safe.levels": Binding(models=("pns.safe",), arguments=_pns_safe_arguments),
}


def unavailable(ctx: RunContext, analysis: Analysis) -> list[str]:
    """The reasons that `analysis` is not available for the target of `ctx`, each one with
    the ID of the analysis. An empty list means that it is available. The reasons are:

    - the target does not give an input or a model of the binding of the analysis;
    - the file does not declare a raster of `analysis.spec.rasters` and the target does not
      give it (it would be a pypulseq default);
    - the analysis has no binding in `BINDINGS` and has parameters, because the values of
      the target for them are not known. An analysis with no binding and no parameter is
      available."""
    # Imported here because `run` imports this module.
    from .run import RASTER_DEFAULT

    spec = analysis.spec
    reasons = []
    binding = BINDINGS.get(spec.id)
    if binding is None:
        if spec.params:
            reasons.append(
                f"for the analysis {spec.id}, pulseq-checks has no binding for its "
                f"parameters {', '.join(spec.params)}"
            )
    else:
        missing = [f"input {path}" for path in binding.inputs if not ctx.has_input(path)]
        missing += [f"model {name}" for name in binding.models if name not in ctx.profile.models]
        if missing:
            reasons.append(
                f"for the analysis {spec.id}, the target {ctx.profile.name!r} does not give: "
                f"{', '.join(missing)}"
            )
    defaults = [name for name in spec.rasters if ctx.raster_sources.get(name) == RASTER_DEFAULT]
    if defaults:
        reasons.append(
            f"for the analysis {spec.id}, the file does not declare {' and '.join(defaults)} "
            f"and the target {ctx.profile.name!r} does not give "
            f"{', '.join(f'rasters.{name}' for name in defaults)}"
        )
    return reasons
