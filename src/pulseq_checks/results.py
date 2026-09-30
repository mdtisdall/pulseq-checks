"""The results of a check run (design section 5.3): `State`, `Location`, `Result`,
`TargetInfo` and `ResultMatrix`, with its exit status (design section 5.6) and its JSON form
(decision 9 of the plan). Also `CheckRunError`, the base of each error of the run.

The JSON form cannot hold a float that is not finite (strict JSON), so `to_json` writes
infinity and "not a number" as the strings "inf", "-inf" and "nan", and `from_json` reads
them back in the float fields. A matrix with "nan" does not compare equal to itself, because
`nan != nan`."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum
from typing import Any

# The version of the JSON form of a `ResultMatrix` (the "format" key).
FORMAT = 1


class CheckRunError(Exception):
    """An error of the run, not a result of a check: exit status 1 (design section 5.6).
    `ProfileError`, `ConfigError` and `RunError` are its subclasses."""


class State(Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUATED = "not evaluated"
    ERROR = "error"


@dataclass(frozen=True)
class Location:
    """Where the value of a result occurs: the block ID (`seq_index.SequenceIndex.block_id`,
    or None when no block has the value) and the time in seconds from the sequence start."""

    block: int | None
    time_s: float


@dataclass(frozen=True)
class Result:
    """The result of one check for one target (design section 5.3, plan section 4.5).

    `reason` is necessary for "not evaluated" and "error". For "pass" and "fail" it can give a
    short detail of the value, for example "axis y" (design section 5.3). `required` is True
    when the caller named the check for this target (decision 3). `spec_url` links to the
    specification."""

    check_id: str
    spec_version: int
    target: str
    state: State
    value: float | None = None
    limit: float | None = None
    unit: str | None = None
    location: Location | None = None
    model: str | None = None
    model_version: int | None = None
    reason: str | None = None
    required: bool = False
    spec_url: str | None = None


@dataclass(frozen=True)
class TargetInfo:
    """A target of a run, as a result matrix keeps it: its name, the source of each value
    (value path to "profile" or an `.asc` label, `TargetProfile.sources`), the profile
    sections that the reader did not use, and the source of the gradient limits:
    "profile" or "sequence object" (decision 4)."""

    name: str
    sources: Mapping[str, str]
    unused_sections: tuple[str, ...]
    limits_source: str = "profile"


@dataclass(frozen=True)
class ResultMatrix:
    """The results of one run: one sequence, its targets, and one result for each check and
    target. `sequence` is the path of the `.seq` file as the caller gave it, or
    "<Sequence object>". `package_version` is the version of pulseq-checks that made it."""

    sequence: str
    package_version: str
    targets: tuple[TargetInfo, ...]
    results: tuple[Result, ...]

    def exit_status(self) -> int:
        """0, 2 or 1 by design section 5.6: 1 when a result is "error" or a required result
        is "not evaluated"; else 2 when a result is "fail"; else 0 (1 wins over 2, R3)."""
        if any(
            r.state is State.ERROR or (r.required and r.state is State.NOT_EVALUATED)
            for r in self.results
        ):
            return 1
        if any(r.state is State.FAIL for r in self.results):
            return 2
        return 0

    def to_json(self) -> str:
        """One JSON object with `"format": FORMAT` (decision 9). The keys are in a fixed
        order; a float that is not finite is written as a string (module docstring)."""
        obj = {
            "format": FORMAT,
            "package_version": self.package_version,
            "sequence": self.sequence,
            "targets": [
                {
                    "name": t.name,
                    "sources": dict(t.sources),
                    "unused_sections": list(t.unused_sections),
                    "limits_source": t.limits_source,
                }
                for t in self.targets
            ],
            "results": [_result_to_obj(r) for r in self.results],
        }
        return json.dumps(obj, indent=2, allow_nan=False)

    @classmethod
    def from_json(cls, text: str) -> ResultMatrix:
        """The matrix of `to_json`: `from_json(m.to_json()) == m`. A format above `FORMAT`
        is a `ValueError` that names both versions. An unknown key or a missing key in any
        object is a `ValueError` that names it."""
        # A value of a wrong type is a `ValueError` too (hence the `noqa: TRY004`): a caller
        # of `from_json` catches one type for a bad text.
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("a result matrix must be a JSON object")  # noqa: TRY004
        version = obj.get("format")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError(f'"format" must be an integer, not {version!r}')  # noqa: TRY004
        if version > FORMAT:
            raise ValueError(
                f"the result matrix has format {version}; this version of pulseq-checks "
                f"reads format {FORMAT} and lower"
            )
        _check_keys(
            obj, ("format", "package_version", "sequence", "targets", "results"), "the matrix"
        )
        targets = []
        for t in _list(obj["targets"], "targets"):
            _check_keys(t, ("name", "sources", "unused_sections", "limits_source"), "a target")
            targets.append(
                TargetInfo(
                    name=t["name"],
                    sources=dict(t["sources"]),
                    unused_sections=tuple(t["unused_sections"]),
                    limits_source=t["limits_source"],
                )
            )
        return cls(
            sequence=obj["sequence"],
            package_version=obj["package_version"],
            targets=tuple(targets),
            results=tuple(_result_from_obj(r) for r in _list(obj["results"], "results")),
        )


# The `Result` fields that hold a float (a float from JSON may be an int, or a string when
# it is not finite).
_FLOAT_FIELDS = ("value", "limit")
_RESULT_KEYS = tuple(f.name for f in fields(Result))


def _float_to_json(x: float | None) -> float | str | None:
    if x is None or math.isfinite(x):
        return x
    return "nan" if math.isnan(x) else ("inf" if x > 0 else "-inf")


def _float_from_json(x: Any, where: str) -> float | None:
    if x is None:
        return None
    if isinstance(x, str) and x in ("inf", "-inf", "nan"):
        return float(x)
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"{where} must be a number or null, not {x!r}")  # noqa: TRY004
    return float(x)


def _result_to_obj(r: Result) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for name in _RESULT_KEYS:
        v = getattr(r, name)
        if name == "state":
            v = v.value
        elif name == "location":
            v = None if v is None else {"block": v.block, "time_s": _float_to_json(v.time_s)}
        elif name in _FLOAT_FIELDS:
            v = _float_to_json(v)
        obj[name] = v
    return obj


def _result_from_obj(obj: Any) -> Result:
    _check_keys(obj, _RESULT_KEYS, "a result")
    kwargs = dict(obj)
    kwargs["state"] = State(obj["state"])
    for name in _FLOAT_FIELDS:
        kwargs[name] = _float_from_json(obj[name], f'"{name}"')
    loc = obj["location"]
    if loc is not None:
        _check_keys(loc, ("block", "time_s"), "a location")
        kwargs["location"] = Location(
            block=loc["block"], time_s=_float_from_json(loc["time_s"], '"time_s"')
        )
    return Result(**kwargs)


def _list(x: Any, name: str) -> list:
    if not isinstance(x, list):
        raise ValueError(f'"{name}" must be a list')  # noqa: TRY004
    return x


def _check_keys(obj: Any, keys: tuple[str, ...], what: str) -> None:
    """Raise `ValueError` when `obj` is not an object with exactly `keys`."""
    if not isinstance(obj, dict):
        raise ValueError(f"{what} must be a JSON object")  # noqa: TRY004
    for key in obj:
        if key not in keys:
            raise ValueError(f"unknown key {key!r} in {what}")
    for key in keys:
        if key not in obj:
            raise ValueError(f"missing key {key!r} in {what}")
