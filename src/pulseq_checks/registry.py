"""The entry-point groups of pulseq-checks (decision 7 of the plan, design section 5.7):
profile readers, models and check rules. The checks of this package use the same group as
a plugin. `analyses()` gives the analyses of pulseq-analysis, which has its own group.

Interface stub (plan section 4.9): the names and the signatures are fixed. Task 3.3 writes
the bodies. Callers use `registry.<function>()` (not `from .registry import ...`), so that
a test can replace a function with monkeypatch."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Protocol

from pulseq_analysis import analyses as analysis_registry

from .results import CheckRunError

if TYPE_CHECKING:
    from pulseq_analysis.analyses import Analysis

    from .rules import CheckRule

PROFILE_READERS = "pulseq_checks.profile_readers"
MODELS = "pulseq_checks.models"
CHECKS = "pulseq_checks.checks"


class RegistryError(CheckRunError):
    """An entry point that cannot be used, for example two packages that give one check
    ID: an error of the run."""


class Model(Protocol):
    """A model entry point (plan section 4.9): its dotted section name under `models` (for
    example "pns.safe"), its version, and `read`, which checks its parameters and raises
    `ValueError` for an unknown or a missing key."""

    name: str
    version: int

    def read(self, params: Mapping[str, Any]) -> dict: ...


def profile_reader(name: str) -> Callable[..., tuple[dict, dict[str, str]]] | None:
    """The loaded profile reader `name` of `PROFILE_READERS` (for example "siemens-asc"),
    or None when no installed package gives it. Two packages that give the name are a
    `RegistryError`."""
    found = [ep for ep in importlib.metadata.entry_points(group=PROFILE_READERS) if ep.name == name]
    if not found:
        return None
    if len(found) > 1:
        packages = " and ".join(repr(_package(ep)) for ep in found)
        raise RegistryError(f"the packages {packages} both give the profile reader {name!r}")
    return _load(found[0], PROFILE_READERS)


def models() -> dict[str, Model]:
    """The installed models of `MODELS`, by `Model.name`. Two models with one name are a
    `RegistryError` that names both packages."""
    found: dict[str, tuple[Model, str]] = {}
    for ep in importlib.metadata.entry_points(group=MODELS):
        model = _load(ep, MODELS)
        try:
            name = model.name
        except AttributeError as e:
            raise RegistryError(
                f"the model entry point {ep.name!r} of the package {_package(ep)!r} has no name"
            ) from e
        _add(found, name, model, ep, f"the model {name!r}")
    return {name: model for name, (model, _) in found.items()}


def check_rules() -> dict[str, CheckRule]:
    """The installed check rules of `CHECKS`, by `spec.id`. Two rules with one ID are a
    `RegistryError` that names both packages."""
    found: dict[str, tuple[CheckRule, str]] = {}
    for ep in importlib.metadata.entry_points(group=CHECKS):
        rule = _load(ep, CHECKS)
        try:
            check_id = rule.spec.id
        except AttributeError as e:
            raise RegistryError(
                f"the check entry point {ep.name!r} of the package {_package(ep)!r} "
                "has no `spec.id`"
            ) from e
        _add(found, check_id, rule, ep, f"the check ID {check_id!r}")
    return {check_id: rule for check_id, (rule, _) in found.items()}


def analyses() -> dict[str, Analysis]:
    """The installed analyses of pulseq-analysis, by `spec.id` (`analyses.registry()`). Its
    `RegistryError` is a `RegistryError` of this module, so it is an error of the run."""
    try:
        return analysis_registry.registry()
    except analysis_registry.RegistryError as e:
        raise RegistryError(str(e)) from e


def _package(ep: Any) -> str:
    """The name of the distribution of the entry point `ep`, when it is known."""
    dist = getattr(ep, "dist", None)
    return dist.name if dist is not None else "an unknown package"


def _load(ep: Any, group: str) -> Any:
    """The object of the entry point `ep`. A failure is a `RegistryError` that names the
    entry point and its package."""
    try:
        return ep.load()
    except Exception as e:
        raise RegistryError(
            f"cannot load the entry point {ep.name!r} of the group {group!r} from the package "
            f"{_package(ep)!r}: {type(e).__name__}: {e}"
        ) from e


def _add(found: dict[str, tuple[Any, str]], key: str, obj: Any, ep: Any, what: str) -> None:
    """Add `obj` with the package of `ep` to `found`. A key that is in `found` is a
    `RegistryError` that names both packages."""
    package = _package(ep)
    if key in found:
        raise RegistryError(f"the packages {found[key][1]!r} and {package!r} both give {what}")
    found[key] = (obj, package)
