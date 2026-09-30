"""The run function (plan section 4.6): `run_checks` runs the check rules on one sequence for
one or more targets and gives the `ResultMatrix`. `RunError` is an error of the run."""

from __future__ import annotations

import dataclasses
import importlib.metadata
from collections.abc import Mapping, Sequence
from pathlib import Path

import pypulseq as pp

from . import registry
from .grad_limits import HardwareLimits
from .profile import TargetProfile
from .results import CheckRunError, Result, ResultMatrix, State, TargetInfo
from .rules import CheckRule, RunContext
from .seq_utils import GAMMA

# `ResultMatrix.sequence` for a `Sequence` object, and `TargetInfo.limits_source` and the
# label of the limits for the opt-in of decision 4.
SEQUENCE_OBJECT = "<Sequence object>"
LIMITS_FROM_SEQUENCE = "sequence object"


class RunError(CheckRunError):
    """An error of the run that `run_checks` finds: for example no target, a check ID that
    is not known, or a `.seq` file that cannot be read (exit status 1, R2)."""


def run_checks(
    sequence: str | Path | pp.Sequence,
    targets: Sequence[TargetProfile],
    *,
    select: Sequence[str] | None = None,
    required: Mapping[str, Sequence[str] | None] | None = None,
    fast_only: bool = False,
    limits_from_sequence: bool = False,
) -> ResultMatrix:
    """Run the check rules on `sequence` for each of `targets`. Raises `RunError`.

    `sequence` is a `.seq` path, which is read one time for each target with the `Opts` of
    that target (decision 3), or a `pp.Sequence` object with exactly one target.
    `select` is the check IDs to run (None: all). `required` maps a check ID to the target
    names for which it is required, or to None for all targets; a required check runs
    whatever `select` and `fast_only` say. `fast_only` removes the checks whose cost class is
    not "fast" and that are not required (R4: it does not make a check required).
    `limits_from_sequence` is the opt-in of decision 4: for a `Sequence` object, a target
    with neither `opts.max_grad` nor `opts.max_slew` gets its gradient limits from
    `seq.system`. The results are in the order of the targets, then of the check IDs."""
    required = {} if required is None else required
    is_path = isinstance(sequence, (str, Path))
    if not targets:
        raise RunError("no target: give at least one target profile")
    names = [target.name for target in targets]
    for name in names:
        if names.count(name) > 1:
            raise RunError(f"two targets have the name {name!r}")
    if is_path and limits_from_sequence:
        raise RunError(
            "limits_from_sequence needs a Sequence object: a .seq file has no limits of its "
            "author (decision 4)"
        )
    if not is_path and len(targets) != 1:
        raise RunError(
            f"a Sequence object gives exactly one target, not {len(targets)}: "
            "give a path to read the sequence for each target"
        )

    rules = registry.check_rules()
    run_ids = _checks_to_run(rules, select, required, names, fast_only)
    required_ids = {check_id: _required_targets(required[check_id], names) for check_id in required}

    target_infos = []
    results = []
    for target in targets:
        seq = _read_sequence(sequence, target) if is_path else sequence
        limits_source, hardware_limits = _hardware_limits(
            seq, target, limits_from_sequence and not is_path
        )
        ctx = RunContext(seq, target, limits_source=limits_source, hardware_limits=hardware_limits)
        for check_id in run_ids:
            result = _run_rule(rules[check_id], ctx)
            is_required = target.name in required_ids.get(check_id, ())
            results.append(dataclasses.replace(result, required=is_required))
        target_infos.append(
            TargetInfo(
                name=target.name,
                sources=dict(target.sources),
                unused_sections=tuple(target.unused_sections),
                limits_source=limits_source,
            )
        )
    return ResultMatrix(
        sequence=str(sequence) if is_path else SEQUENCE_OBJECT,
        package_version=importlib.metadata.version("pulseq-checks"),
        targets=tuple(target_infos),
        results=tuple(results),
    )


def _checks_to_run(
    rules: Mapping[str, CheckRule],
    select: Sequence[str] | None,
    required: Mapping[str, Sequence[str] | None],
    target_names: Sequence[str],
    fast_only: bool,
) -> list[str]:
    """The IDs of the checks that run, in the order of the IDs: the selected checks and the
    required checks, less the checks that `fast_only` removes. Raises `RunError` for an ID
    that is not a known check, and for a target name that is not a target."""
    for what, ids in (("select", select or ()), ("required", required)):
        for check_id in ids:
            if check_id not in rules:
                raise RunError(f"{what} names the check {check_id!r}, which is not installed")
    for check_id, names in required.items():
        for name in names or ():
            if name not in target_names:
                raise RunError(
                    f"required names the target {name!r} for the check {check_id!r}, "
                    "which is not a target of this run"
                )
    selected = set(rules) if select is None else set(select)
    run_ids = selected | set(required)
    if fast_only:
        run_ids = {
            check_id
            for check_id in run_ids
            if rules[check_id].spec.cost == "fast" or check_id in required
        }
    return sorted(run_ids)


def _required_targets(names: Sequence[str] | None, target_names: Sequence[str]) -> frozenset[str]:
    """The target names for which a check is required: `names`, or all targets for None."""
    return frozenset(target_names if names is None else names)


def _read_sequence(path: str | Path, target: TargetProfile) -> pp.Sequence:
    """The `.seq` file `path`, read with the `Opts` of `target` (fact 5 of the plan)."""
    try:
        seq = pp.Sequence(system=target.make_opts())
        seq.read(str(path))
    except Exception as e:
        raise RunError(
            f"cannot read the sequence {str(path)!r} for the target {target.name!r}: "
            f"{type(e).__name__}: {e}"
        ) from e
    return seq


def _hardware_limits(
    seq: pp.Sequence, target: TargetProfile, from_sequence: bool
) -> tuple[str, HardwareLimits | None]:
    """The source and the value of the gradient limits of this target: `seq.system` when
    `from_sequence` and the target gives neither `opts.max_grad` nor `opts.max_slew`, else
    the profile."""
    if from_sequence and not (
        target.has_value("opts.max_grad") or target.has_value("opts.max_slew")
    ):
        # pp.Opts stores max_grad in Hz/m and max_slew in Hz/m/s, whatever unit it was given.
        limits = HardwareLimits(
            max_grad_mt_per_m=seq.system.max_grad / GAMMA * 1e3,
            max_slew_t_per_m_per_s=seq.system.max_slew / GAMMA,
            label=LIMITS_FROM_SEQUENCE,
        )
        return LIMITS_FROM_SEQUENCE, limits
    return "profile", target.hardware_limits


def _run_rule(rule: CheckRule, ctx: RunContext) -> Result:
    """The result of `rule` for the target of `ctx`: "not evaluated" before `run` when an
    input or a model is missing, "error" when `run` raises an exception or gives a result
    of a different check or target."""
    spec = rule.spec
    missing = [f"input {path}" for path in spec.inputs if not ctx.has_input(path)]
    missing += [f"model {name}" for name in spec.models if name not in ctx.profile.models]
    if missing:
        reason = f"the target {ctx.profile.name!r} does not give: {', '.join(missing)}"
        return ctx.result(spec, State.NOT_EVALUATED, reason=reason)
    try:
        result = rule.run(ctx)
    except Exception as e:  # noqa: BLE001 (R1: an exception of a check is its result)
        return ctx.result(spec, State.ERROR, reason=f"{type(e).__name__}: {e}")
    if not isinstance(result, Result):
        reason = f"the check gave {type(result).__name__}, not a Result"
    elif result.check_id != spec.id or result.target != ctx.profile.name:
        reason = (
            f"the check gave a result for the check {result.check_id!r} and the target "
            f"{result.target!r}, not for {spec.id!r} and {ctx.profile.name!r}"
        )
    else:
        return result
    return ctx.result(spec, State.ERROR, reason=reason)
