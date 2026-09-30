"""Tests for `pulseq_checks.results`: the exit status and the JSON form of a result matrix."""

from __future__ import annotations

import json
import math

import pytest

from pulseq_checks.results import (
    FORMAT,
    Location,
    Result,
    ResultMatrix,
    State,
    TargetInfo,
)


def _result(state: State, required: bool = False, **kwargs) -> Result:
    return Result(
        check_id="gradient.slew.axis",
        spec_version=1,
        target="scanner-a",
        state=state,
        required=required,
        **kwargs,
    )


def _matrix(*results: Result) -> ResultMatrix:
    return ResultMatrix(
        sequence="test.seq",
        package_version="0.1.0rc1",
        targets=(TargetInfo(name="scanner-a", sources={}, unused_sections=()),),
        results=tuple(results),
    )


P, F, N, E = State.PASS, State.FAIL, State.NOT_EVALUATED, State.ERROR


@pytest.mark.parametrize(
    "results, status",
    [
        ([], 0),
        ([_result(P), _result(P, required=True)], 0),
        ([_result(P), _result(F)], 2),
        ([_result(P), _result(E)], 1),
        ([_result(P), _result(N, required=True)], 1),
        ([_result(P), _result(N, required=False)], 0),
        ([_result(F), _result(E)], 1),
        ([_result(F), _result(N, required=True)], 1),
        ([_result(F, required=True)], 2),
        ([_result(F, required=True), _result(N)], 2),
        ([_result(E, required=True)], 1),
    ],
    ids=[
        "no results",
        "all pass",
        "one fail",
        "one error",
        "required not evaluated",
        "not required not evaluated",
        "fail and error",
        "fail and required not evaluated",
        "required fail",
        "required fail and not required not evaluated",
        "required error",
    ],
)
def test_exit_status(results, status):
    assert _matrix(*results).exit_status() == status


def _full_matrix() -> ResultMatrix:
    return ResultMatrix(
        sequence="examples/test.seq",
        package_version="0.1.0rc1",
        targets=(
            TargetInfo(
                name="scanner-a",
                sources={"opts.max_grad": "profile", "models.pns.safe": "MP_GPA.asc (fast)"},
                unused_sections=("models.pns.other",),
                limits_source="sequence object",
            ),
        ),
        results=(
            Result(
                check_id="pns.safe",
                spec_version=2,
                target="scanner-a",
                state=State.FAIL,
                value=103.25,
                limit=100.0,
                unit="%",
                location=Location(block=17, time_s=0.1 + 0.2),
                model="pns.safe",
                model_version=1,
                reason="the peak is above the limit",
                required=True,
                spec_url="https://example.org/checks.md#pnssafe",
            ),
        ),
    )


def _matrix_with_nones() -> ResultMatrix:
    return _matrix(
        _result(State.NOT_EVALUATED, reason="no profile value opts.max_slew"),
        _result(State.PASS),
    )


def _matrix_with_two_targets() -> ResultMatrix:
    return ResultMatrix(
        sequence="<Sequence object>",
        package_version="0.1.0rc1",
        targets=(
            TargetInfo(name="a", sources={"opts.max_grad": "profile"}, unused_sections=()),
            TargetInfo(name="b", sources={}, unused_sections=("x", "y")),
        ),
        results=(
            Result("c1", 1, "a", State.PASS, value=1.0, limit=2.0, unit="mT/m"),
            Result("c1", 1, "b", State.ERROR, reason="ValueError: a message"),
        ),
    )


def _matrix_with_inf() -> ResultMatrix:
    return _matrix(
        _result(State.PASS, value=math.inf, limit=-math.inf),
        _result(State.PASS, location=Location(block=None, time_s=math.inf)),
    )


def _matrix_with_no_block() -> ResultMatrix:
    return _matrix(_result(State.FAIL, value=1.5, location=Location(block=None, time_s=0.25)))


@pytest.mark.parametrize(
    "make",
    [
        _full_matrix,
        _matrix_with_nones,
        _matrix_with_two_targets,
        _matrix_with_inf,
        _matrix_with_no_block,
    ],
)
def test_json_round_trip(make):
    m = make()
    text = m.to_json()
    back = ResultMatrix.from_json(text)
    assert back == m
    assert back.to_json() == text
    json.loads(text, parse_constant=lambda c: pytest.fail(f"non-strict JSON constant {c}"))


def test_json_round_trip_keeps_floats_exactly():
    value = 0.1 + 0.2
    m = _matrix(_result(State.PASS, value=value, limit=1 / 3))
    back = ResultMatrix.from_json(m.to_json())
    assert back.results[0].value == value
    assert back.results[0].limit == 1 / 3


def test_json_has_the_keys_of_decision_9():
    obj = json.loads(_full_matrix().to_json())
    assert list(obj) == ["format", "package_version", "sequence", "targets", "results"]
    assert obj["format"] == 1 == FORMAT
    assert list(obj["targets"][0]) == ["name", "sources", "unused_sections", "limits_source"]
    assert obj["targets"][0]["sources"]["models.pns.safe"] == "MP_GPA.asc (fast)"
    assert obj["targets"][0]["unused_sections"] == ["models.pns.other"]
    result = obj["results"][0]
    assert list(result) == [
        "check_id",
        "spec_version",
        "target",
        "state",
        "value",
        "limit",
        "unit",
        "location",
        "model",
        "model_version",
        "reason",
        "required",
        "spec_url",
    ]
    assert result["state"] == "fail"
    assert result["location"] == {"block": 17, "time_s": 0.1 + 0.2}
    assert json.loads(_matrix_with_nones().to_json())["results"][0]["location"] is None
    assert json.loads(_matrix_with_nones().to_json())["results"][0]["state"] == "not evaluated"


def test_json_writes_a_float_that_is_not_finite_as_a_string():
    obj = json.loads(_matrix_with_inf().to_json())
    assert obj["results"][0]["value"] == "inf"
    assert obj["results"][0]["limit"] == "-inf"
    assert obj["results"][1]["location"]["time_s"] == "inf"


def test_from_json_rejects_a_newer_format():
    obj = json.loads(_full_matrix().to_json())
    obj["format"] = FORMAT + 1
    with pytest.raises(ValueError, match=rf"format {FORMAT + 1}.*format {FORMAT}"):
        ResultMatrix.from_json(json.dumps(obj))


@pytest.mark.parametrize("bad", [None, "1", 1.0, True])
def test_from_json_rejects_a_format_that_is_not_an_integer(bad):
    obj = json.loads(_full_matrix().to_json())
    obj["format"] = bad
    with pytest.raises(ValueError, match="format"):
        ResultMatrix.from_json(json.dumps(obj))


def test_from_json_rejects_a_missing_format():
    obj = json.loads(_full_matrix().to_json())
    del obj["format"]
    with pytest.raises(ValueError, match="format"):
        ResultMatrix.from_json(json.dumps(obj))


def _set(path, value):
    """The JSON text of the full matrix with `value` at `path` (keys and list indexes)."""
    obj = json.loads(_full_matrix().to_json())
    node = obj
    for key in path[:-1]:
        node = node[key]
    if value is _DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return json.dumps(obj)


_DELETE = object()


@pytest.mark.parametrize(
    "path",
    [
        ["extra"],
        ["targets", 0, "extra"],
        ["results", 0, "extra"],
        ["results", 0, "location", "extra"],
    ],
    ids=["matrix", "target", "result", "location"],
)
def test_from_json_rejects_an_unknown_key(path):
    with pytest.raises(ValueError, match="unknown key 'extra'"):
        ResultMatrix.from_json(_set(path, 1))


@pytest.mark.parametrize(
    "path",
    [
        ["sequence"],
        ["targets", 0, "sources"],
        ["results", 0, "required"],
        ["results", 0, "location", "time_s"],
    ],
    ids=["matrix", "target", "result", "location"],
)
def test_from_json_rejects_a_missing_key(path):
    with pytest.raises(ValueError, match=f"missing key '{path[-1]}'"):
        ResultMatrix.from_json(_set(path, _DELETE))
