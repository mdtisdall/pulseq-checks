"""Check rules (plan section 4.5): `CheckSpec`, the specification of a check as data;
`CheckRule`, a check with its specification; and `RunContext`, what a rule gets for one
target."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from .grad_limits import HardwareLimits
from .results import Result, State

if TYPE_CHECKING:
    import pypulseq as pp

    from .profile import TargetProfile

# The specifications of the checks of this package, made by scripts/check_docs.py (phase 6).
DOCS_URL = "https://github.com/mdtisdall/pulseq-checks/blob/main/docs/checks.md"


@dataclass(frozen=True)
class CheckSpec:
    """The specification of a check (design section 5.4). `inputs` are the profile value
    paths that the check needs (`TargetProfile.sources` keys, for example "opts.max_grad"),
    and `models` the model names (for example "pns.safe"). A plugin check gives its own
    `url`; a check of this package gives None."""

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
    limits of `seq.system` with the opt-in of decision 4, or None."""

    def __init__(
        self,
        sequence: pp.Sequence,
        profile: TargetProfile,
        *,
        limits_source: str = "profile",
        hardware_limits: HardwareLimits | None = None,
    ) -> None:
        self.sequence = sequence
        self.profile = profile
        self.limits_source = limits_source
        self.hardware_limits = hardware_limits
        self._measurements: dict[str, Any] = {}

    def measure(self, name: str, fn: Callable[[pp.Sequence], Any]) -> Any:
        """`fn(self.sequence)`, calculated one time for each `name` in this context and kept
        for the other rules of this target. The version 1 names are "index",
        "gradient_limits" and "pns_levels"."""
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
    with `ctx.result`). The run function gives "not evaluated" before `run` when an input or
    a model is missing, and "error" when `run` raises."""

    spec: CheckSpec

    def run(self, ctx: RunContext) -> Result: ...
