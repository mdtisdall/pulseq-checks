"""Check rules (plan section 4.5): `CheckSpec`, the specification of a check as data;
`CheckRule`, a check with its specification; and `RunContext`, what a rule gets for one
target."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from . import registry
from .bindings import BINDINGS, unavailable
from .profile import RASTER_OPTS, HardwareLimits
from .results import Result, State

if TYPE_CHECKING:
    import pypulseq as pp
    from pulseq_analysis.analyses import Analysis

    from .profile import TargetProfile

# The specifications of the checks of this package, made by scripts/check_docs.py (phase 6).
DOCS_URL = "https://github.com/mdtisdall/pulseq-checks/blob/main/docs/checks.md"


@dataclass(frozen=True)
class CheckPromise:
    """What a check promises (design section 5.4): `on_pass`, what a pass guarantees;
    `on_fail`, what a fail means; and `not_promised`, what the check does not promise, also
    with a pass. Each is a text for a user of the result."""

    on_pass: str
    on_fail: str
    not_promised: str


@dataclass(frozen=True)
class CheckSpec:
    """The specification of a check (design section 5.4). `inputs` are the profile value
    paths that the check needs (`TargetProfile.sources` keys, for example "opts.max_grad"),
    and `models` the model names (for example "pns.safe"). A plugin check gives its own
    `url`; a check of this package gives None. For a check that gives findings, `findings`
    says what one finding is, its codes, its location, the keys of `data`, and the order of
    the findings (plan check-findings, section 4.3); None for a check that gives none.
    `rasters` are the raster names that the measurement of the check uses ("GradientRasterTime",
    "RadiofrequencyRasterTime", "AdcRasterTime", "BlockDurationRaster"). The run function gives
    "not evaluated" when the file does not declare one of them and the target does not give
    it. `promise` says what a pass and a fail of the check mean for the user; each check of
    this package gives one, and a plugin can leave it None. `analyses` are the IDs of the
    analyses of pulseq-analysis that the check gets with `RunContext.analysis`. The run
    function gives "not evaluated" when one of them is not available for the target
    (`bindings.unavailable`)."""

    id: str
    version: int
    title: str
    quantity: str
    inputs: tuple[str, ...]
    models: tuple[str, ...]
    limit: str
    tolerance: str
    pass_condition: str
    cost: str = "slow"
    pypulseq: str | None = None
    url: str | None = None
    findings: str | None = None
    rasters: tuple[str, ...] = ()
    promise: CheckPromise | None = None
    analyses: tuple[str, ...] = ()


def spec_url(spec: CheckSpec) -> str:
    """`spec.url`, or the heading of `spec.id` in docs/checks.md: the ID with the dots
    removed (plan section 4.9)."""
    if spec.url is not None:
        return spec.url
    return DOCS_URL + "#" + spec.id.replace(".", "")


class RunContext:
    """What a check rule gets for one target (plan section 4.5).

    `sequence` is read with the `Opts` of the target, `profile` is the target, and
    `limits_source` is "profile" or "sequence object" (decision 4). `hardware_limits` is
    the gradient limits that the gradient checks use: `profile.hardware_limits`, or the
    limits of `seq.system` with the opt-in of decision 4, or None.

    `raster_sources` maps each raster name of `RASTER_OPTS` to where its value comes from:
    "file" (the file declares it), "target" (the file does not, and the profile gives it),
    "sequence object" (the sequence is a `pp.Sequence` object, not a file) or "pypulseq
    default" (neither the file nor the profile gives it). The default is "sequence object" for
    all four rasters: a context that is made by hand has a sequence object, and no rule is
    "not evaluated" for it.

    `analyses` are the installed analyses by ID (`registry.analyses()`). The run function
    gives the dict that it loaded one time for all targets. A context that is made by hand
    loads them in its first call of `analysis`."""

    def __init__(
        self,
        sequence: pp.Sequence,
        profile: TargetProfile,
        *,
        limits_source: str = "profile",
        hardware_limits: HardwareLimits | None = None,
        raster_sources: Mapping[str, str] | None = None,
        analyses: Mapping[str, Analysis] | None = None,
    ) -> None:
        self.sequence = sequence
        self.profile = profile
        self.limits_source = limits_source
        self.hardware_limits = hardware_limits
        self.raster_sources = (
            {name: "sequence object" for name in RASTER_OPTS}
            if raster_sources is None
            else dict(raster_sources)
        )
        self._installed_analyses = analyses
        self._measurements: dict[str, Any] = {}
        # The value of `compute` of each analysis, or the exception that it raised.
        self._analyses: dict[str, Any] = {}

    def analysis(self, analysis_id: str) -> Any:
        """The value of `compute` of the analysis `analysis_id` for this target, with the
        keyword arguments of its binding (`bindings.BINDINGS`). `compute` runs one time for
        each ID in this context. The value, or the exception that `compute` raised, is kept:
        a second call gives the value, or raises the same exception again.

        Raises `LookupError`, with the reason, when the analysis is not installed or is not
        available for the target (`bindings.unavailable`)."""
        if analysis_id not in self._analyses:
            if self._installed_analyses is None:
                self._installed_analyses = registry.analyses()
            analysis = self._installed_analyses.get(analysis_id)
            if analysis is None:
                raise LookupError(f"the analysis {analysis_id!r} is not installed")
            reasons = unavailable(self, analysis)
            if reasons:
                raise LookupError("; ".join(reasons))
            binding = BINDINGS.get(analysis_id)
            try:
                arguments = {} if binding is None else binding.arguments(self)
                self._analyses[analysis_id] = analysis.compute(self.sequence, **arguments)
            except Exception as e:  # noqa: BLE001 (kept, and raised again for each caller)
                self._analyses[analysis_id] = e
        kept = self._analyses[analysis_id]
        if isinstance(kept, Exception):
            raise kept
        return kept

    def measure(self, name: str, fn: Callable[[pp.Sequence], Any]) -> Any:
        """`fn(self.sequence)`, calculated one time for each `name` in this context and kept
        for the other rules of this target. It is for the measurements of a plugin. The analyses
        of pulseq-analysis are in `analysis`."""
        if name not in self._measurements:
            self._measurements[name] = fn(self.sequence)
        return self._measurements[name]

    def has_input(self, path: str) -> bool:
        """True when the target gives the value path `path`: the profile has it, or it is
        "opts.max_grad" or "opts.max_slew" and the limits come from the sequence object."""
        if self.limits_source == "sequence object" and path in ("opts.max_grad", "opts.max_slew"):
            return True
        return self.profile.has_value(path)

    def result(self, spec: CheckSpec, state: State, **fields: Any) -> Result:
        """A `Result` of `spec` for this target, with `check_id`, `spec_version`, `target`
        and `spec_url` from `spec` and the context, and the other fields from `fields`. The
        run function sets `required`."""
        return Result(
            check_id=spec.id,
            spec_version=spec.version,
            target=self.profile.name,
            state=state,
            spec_url=spec_url(spec),
            **fields,
        )


class CheckRule(Protocol):
    """A check: its specification, and `run`, which returns its result for one target (made
    with `ctx.result`). The run function gives "not evaluated" before `run` when an input, a
    model or an analysis is missing, and "error" when `run` raises or when the result is not
    valid: its findings are not a tuple of `Finding`, or its `findings_omitted` is not an `int`
    of 0 or more (plan check-findings, section 4.4)."""

    spec: CheckSpec

    def run(self, ctx: RunContext) -> Result: ...
