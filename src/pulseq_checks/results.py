"""The results of a check run (design section 5.3): `State`, `Location`, `Result`,
`Finding`, `TargetInfo` and `ResultMatrix`, with its exit status (design section 5.6) and its
JSON form (decision 9 of the plan, and plan check-findings, section 4.5). Also
`AnalysisState` and `AnalysisResult`, the result of an analysis of pulseq-analysis for one
target (plan pulseq-analysis, section 4.6), and `CheckRunError`, the base of each error of
the run.

The JSON form cannot hold a float that is not finite (strict JSON), so `to_json` writes
infinity and "not a number" as the strings "inf", "-inf" and "nan", and `from_json` reads
them back in the float fields, and in the values of the `data` of a finding. A matrix with
"nan" does not compare equal to itself, because `nan != nan`."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from enum import Enum
from typing import Any

from pulseq_analysis.series import Series

# The version of the JSON form of a `ResultMatrix` (the "format" key). It stays 1 in the
# release candidates: the findings keys of check-findings section 4.5 and the "analyses" key
# are part of format 1.
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


# The strings that stand for a float that is not finite in the JSON form.
_NON_FINITE = ("inf", "-inf", "nan")


@dataclass(frozen=True)
class Finding:
    """One problem that a check found (plan check-findings, section 4.1).

    `code` is a short, stable name of the kind of finding. `message` is one line of text for a
    person. `location` is where the finding occurs, or None. `data` holds the values of the
    finding by name, for a machine: only JSON scalars. A string value of `data` cannot be
    "inf", "-inf" or "nan", because the JSON form writes a float that is not finite as one of
    these strings. A `Finding` with data is not hashable, as `TargetInfo` is not."""

    code: str
    message: str
    location: Location | None = None
    data: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, str):
            raise TypeError(f"the code of a finding must be a string, not {self.code!r}")
        if not self.code:
            raise ValueError("the code of a finding must not be empty")
        if not isinstance(self.message, str):
            raise TypeError(f"the message of a finding must be a string, not {self.message!r}")
        if self.location is not None and not isinstance(self.location, Location):
            raise TypeError(
                f"the location of a finding must be a Location or None, not {self.location!r}"
            )
        if not isinstance(self.data, Mapping):
            raise TypeError(f"the data of a finding must be a mapping, not {self.data!r}")
        for key, value in self.data.items():
            if not isinstance(key, str):
                raise TypeError(f"a key of the data of a finding must be a string, not {key!r}")
            if value is not None and not isinstance(value, (str, int, float)):
                raise TypeError(
                    f"the data value {key!r} of a finding must be a string, a number, a bool "
                    f"or None, not {value!r}"
                )
            if isinstance(value, str) and value in _NON_FINITE:
                raise ValueError(
                    f"the data value {key!r} of a finding must not be the string {value!r}: "
                    "the JSON form uses it for a float that is not finite"
                )


@dataclass(frozen=True)
class Result:
    """The result of one check for one target (design section 5.3, plan section 4.5).

    `reason` is necessary for "not evaluated" and "error". For "pass" and "fail" it can give a
    short detail of the value, for example "axis y" (design section 5.3). `required` is True
    when the caller named the check for this target (decision 3). `spec_url` links to the
    specification. `findings` are the problems that the check found, in the order that the
    check gave them, for a result of any state (plan check-findings, section 4.2).
    `findings_omitted` is the number of findings that are not in `findings` because
    `ResultMatrix.with_max_findings` removed them. The findings do not change the state."""

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
    findings: tuple[Finding, ...] = ()
    findings_omitted: int = 0


class AnalysisState(Enum):
    DONE = "done"
    NOT_EVALUATED = "not evaluated"
    ERROR = "error"


@dataclass(frozen=True)
class AnalysisResult:
    """The result of one analysis for one target (plan pulseq-analysis, section 4.6). `id`
    and `version` are those of the `AnalysisSpec`. `state` is "done" with the `series` of
    `Analysis.to_series`, "not evaluated" when the analysis is not available for the target,
    or "error" when `compute` or `to_series` raised an exception. `reason` is necessary for
    "not evaluated" and "error". An analysis result is not a check result: it does not change
    the exit status of the matrix."""

    id: str
    version: int
    target: str
    state: AnalysisState
    reason: str | None = None
    series: tuple[Series, ...] = ()


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
    "<Sequence object>". `package_version` is the version of pulseq-checks that made it.
    `analyses` are the results of the analyses that the caller asked for, in the order of the
    targets, then of the analysis IDs."""

    sequence: str
    package_version: str
    targets: tuple[TargetInfo, ...]
    results: tuple[Result, ...]
    analyses: tuple[AnalysisResult, ...] = ()

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

    def with_max_findings(self, n: int) -> ResultMatrix:
        """A new matrix in which each result with more than `n` findings keeps the first `n`,
        and `findings_omitted` has the number of the others added. `n` must be an `int` of 0
        or more, else `ValueError`."""
        if not isinstance(n, int) or isinstance(n, bool):
            raise ValueError(f"the maximum number of findings must be an integer, not {n!r}")  # noqa: TRY004
        if n < 0:
            raise ValueError(f"the maximum number of findings must be 0 or more, not {n}")
        results = tuple(
            r
            if len(r.findings) <= n
            else replace(
                r,
                findings=r.findings[:n],
                findings_omitted=r.findings_omitted + len(r.findings) - n,
            )
            for r in self.results
        )
        return replace(self, results=results)

    def analysis(self, target: str, id: str) -> AnalysisResult | None:
        """The result of the analysis `id` for the target named `target`, or None when the
        matrix has none."""
        for a in self.analyses:
            if a.target == target and a.id == id:
                return a
        return None

    def without_series(self) -> ResultMatrix:
        """A new matrix in which each analysis result has no series. The other fields are the
        same."""
        return replace(self, analyses=tuple(replace(a, series=()) for a in self.analyses))

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
            "analyses": [_analysis_to_obj(a) for a in self.analyses],
        }
        return json.dumps(obj, indent=2, allow_nan=False)

    @classmethod
    def from_json(cls, text: str) -> ResultMatrix:
        """The matrix of `to_json`: `from_json(m.to_json()) == m`. A format above `FORMAT`
        is a `ValueError` that names both versions. An unknown key or a missing key in any
        object is a `ValueError` that names it; the matrix must have the key "analyses"
        (decision P5 of the implementation plan). A bad series is a `ValueError` too."""
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
            obj,
            ("format", "package_version", "sequence", "targets", "results", "analyses"),
            "the matrix",
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
            analyses=tuple(_analysis_from_obj(a) for a in _list(obj["analyses"], "analyses")),
        )


# The `Result` fields that hold a float (a float from JSON may be an int, or a string when
# it is not finite).
_FLOAT_FIELDS = ("value", "limit")
_RESULT_KEYS = tuple(f.name for f in fields(Result))
_FINDING_KEYS = tuple(f.name for f in fields(Finding))
_ANALYSIS_KEYS = tuple(f.name for f in fields(AnalysisResult))


def _float_to_json(x: float | None) -> float | str | None:
    if x is None or math.isfinite(x):
        return x
    return "nan" if math.isnan(x) else ("inf" if x > 0 else "-inf")


def _float_from_json(x: Any, where: str) -> float | None:
    if x is None:
        return None
    if isinstance(x, str) and x in _NON_FINITE:
        return float(x)
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"{where} must be a number or null, not {x!r}")  # noqa: TRY004
    return float(x)


def _location_to_obj(loc: Location | None) -> dict[str, Any] | None:
    return None if loc is None else {"block": loc.block, "time_s": _float_to_json(loc.time_s)}


def _location_from_obj(loc: Any) -> Location | None:
    if loc is None:
        return None
    _check_keys(loc, ("block", "time_s"), "a location")
    return Location(block=loc["block"], time_s=_float_from_json(loc["time_s"], '"time_s"'))


def _finding_to_obj(f: Finding) -> dict[str, Any]:
    return {
        "code": f.code,
        "message": f.message,
        "location": _location_to_obj(f.location),
        # An int stays an int, and a finite float stays a float.
        "data": {k: _float_to_json(v) if isinstance(v, float) else v for k, v in f.data.items()},
    }


def _finding_from_obj(obj: Any) -> Finding:
    _check_keys(obj, _FINDING_KEYS, "a finding")
    data = obj["data"]
    if not isinstance(data, dict):
        raise ValueError('"data" of a finding must be a JSON object')  # noqa: TRY004
    data = {k: float(v) if isinstance(v, str) and v in _NON_FINITE else v for k, v in data.items()}
    try:
        return Finding(
            code=obj["code"],
            message=obj["message"],
            location=_location_from_obj(obj["location"]),
            data=data,
        )
    except TypeError as exc:
        # A value of a wrong type is a `ValueError` too: a caller of `from_json` catches one
        # type for a bad text.
        raise ValueError(f"a bad finding: {exc}") from exc


def _result_to_obj(r: Result) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for name in _RESULT_KEYS:
        v = getattr(r, name)
        if name == "state":
            v = v.value
        elif name == "location":
            v = _location_to_obj(v)
        elif name in _FLOAT_FIELDS:
            v = _float_to_json(v)
        elif name == "findings":
            v = [_finding_to_obj(f) for f in v]
        obj[name] = v
    return obj


def _result_from_obj(obj: Any) -> Result:
    _check_keys(obj, _RESULT_KEYS, "a result")
    kwargs = dict(obj)
    kwargs["state"] = State(obj["state"])
    for name in _FLOAT_FIELDS:
        kwargs[name] = _float_from_json(obj[name], f'"{name}"')
    kwargs["location"] = _location_from_obj(obj["location"])
    kwargs["findings"] = tuple(_finding_from_obj(f) for f in _list(obj["findings"], "findings"))
    omitted = obj["findings_omitted"]
    if not isinstance(omitted, int) or isinstance(omitted, bool) or omitted < 0:
        raise ValueError(f'"findings_omitted" must be an integer of 0 or more, not {omitted!r}')
    return Result(**kwargs)


def _analysis_to_obj(a: AnalysisResult) -> dict[str, Any]:
    return {
        "id": a.id,
        "version": a.version,
        "target": a.target,
        "state": a.state.value,
        "reason": a.reason,
        "series": [s.to_obj() for s in a.series],
    }


def _analysis_from_obj(obj: Any) -> AnalysisResult:
    _check_keys(obj, _ANALYSIS_KEYS, "an analysis result")
    version = obj["version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValueError(f'"version" of an analysis result must be an integer, not {version!r}')  # noqa: TRY004
    return AnalysisResult(
        id=obj["id"],
        version=version,
        target=obj["target"],
        state=AnalysisState(obj["state"]),
        reason=obj["reason"],
        series=tuple(Series.from_obj(s) for s in _list(obj["series"], "series")),
    )


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
