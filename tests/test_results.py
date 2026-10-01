"""Tests for `pulseq_checks.results`: `Finding`, the exit status and the JSON form of a result
matrix, and `ResultMatrix.with_max_findings`."""

from __future__ import annotations

import json
import math

import pytest

from pulseq_checks.results import (
    FORMAT,
    Finding,
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
                findings=(
                    Finding(
                        code="PEAK",
                        message="the peak is above the limit",
                        location=Location(block=17, time_s=0.1 + 0.2),
                        data={"axis": "y", "value": 103.25},
                    ),
                ),
                findings_omitted=2,
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


def _matrix_with_findings() -> ResultMatrix:
    return _matrix(
        _result(
            State.FAIL,
            findings=(
                Finding(
                    code="A",
                    message="a finding with each type of value",
                    location=Location(block=3, time_s=0.5),
                    data={
                        "text": "a string",
                        "int": 7,
                        "float": 0.1 + 0.2,
                        "whole float": 2.0,
                        "true": True,
                        "false": False,
                        "none": None,
                    },
                ),
                Finding(code="B", message="a finding with no location and no data"),
                Finding(code="C", message="a location with no block", location=Location(None, 1.0)),
            ),
        ),
        _result(State.PASS, findings=(Finding(code="D", message="d"),), findings_omitted=5),
        _result(State.ERROR, reason="an error", findings_omitted=1),
    )


def _matrix_with_non_finite_data() -> ResultMatrix:
    return _matrix(
        _result(
            State.FAIL,
            findings=(
                Finding(
                    code="A",
                    message="m",
                    data={"inf": math.inf, "-inf": -math.inf, "finite": 1.5, "int": 3},
                ),
            ),
        )
    )


@pytest.mark.parametrize(
    "make",
    [
        _full_matrix,
        _matrix_with_nones,
        _matrix_with_two_targets,
        _matrix_with_inf,
        _matrix_with_no_block,
        _matrix_with_findings,
        _matrix_with_non_finite_data,
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
    assert obj["format"] == 2 == FORMAT
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
        "findings",
        "findings_omitted",
    ]
    assert result["state"] == "fail"
    assert result["location"] == {"block": 17, "time_s": 0.1 + 0.2}
    assert result["findings_omitted"] == 2
    assert len(result["findings"]) == 1
    assert list(result["findings"][0]) == ["code", "message", "location", "data"]
    assert result["findings"][0]["code"] == "PEAK"
    assert result["findings"][0]["location"] == {"block": 17, "time_s": 0.1 + 0.2}
    assert result["findings"][0]["data"] == {"axis": "y", "value": 103.25}
    assert json.loads(_matrix_with_nones().to_json())["results"][0]["location"] is None
    assert json.loads(_matrix_with_nones().to_json())["results"][0]["state"] == "not evaluated"
    assert json.loads(_matrix_with_nones().to_json())["results"][0]["findings"] == []
    assert json.loads(_matrix_with_nones().to_json())["results"][0]["findings_omitted"] == 0


def test_json_writes_a_float_that_is_not_finite_as_a_string():
    obj = json.loads(_matrix_with_inf().to_json())
    assert obj["results"][0]["value"] == "inf"
    assert obj["results"][0]["limit"] == "-inf"
    assert obj["results"][1]["location"]["time_s"] == "inf"


def test_json_writes_the_data_of_a_finding_with_its_types():
    obj = json.loads(_matrix_with_findings().to_json())
    findings = obj["results"][0]["findings"]
    assert findings[0]["data"] == {
        "text": "a string",
        "int": 7,
        "float": 0.1 + 0.2,
        "whole float": 2.0,
        "true": True,
        "false": False,
        "none": None,
    }
    assert findings[1]["location"] is None
    assert findings[1]["data"] == {}
    assert findings[2]["location"] == {"block": None, "time_s": 1.0}
    text = _matrix_with_findings().to_json()
    assert '"int": 7,' in text
    assert '"whole float": 2.0,' in text


def test_json_writes_a_float_in_the_data_of_a_finding_that_is_not_finite_as_a_string():
    m = _matrix_with_non_finite_data()
    data = json.loads(m.to_json())["results"][0]["findings"][0]["data"]
    assert data == {"inf": "inf", "-inf": "-inf", "finite": 1.5, "int": 3}
    back = ResultMatrix.from_json(m.to_json()).results[0].findings[0].data
    assert back["inf"] == math.inf
    assert back["-inf"] == -math.inf
    assert isinstance(back["inf"], float)
    assert isinstance(back["int"], int)
    assert back["finite"] == 1.5


def test_json_reads_nan_in_the_data_of_a_finding_as_a_float():
    m = _matrix(_result(State.FAIL, findings=(Finding("A", "m", data={"x": math.nan}),)))
    text = m.to_json()
    assert json.loads(text)["results"][0]["findings"][0]["data"] == {"x": "nan"}
    value = ResultMatrix.from_json(text).results[0].findings[0].data["x"]
    assert isinstance(value, float)
    assert math.isnan(value)


def test_from_json_reads_format_1_with_no_findings():
    obj = json.loads(_full_matrix().to_json())
    obj["format"] = 1
    for result in obj["results"]:
        del result["findings"]
        del result["findings_omitted"]
    back = ResultMatrix.from_json(json.dumps(obj))
    assert back.results[0].findings == ()
    assert back.results[0].findings_omitted == 0
    assert back.results[0].check_id == "pns.safe"
    assert back.results[0].value == 103.25


def test_from_json_rejects_a_findings_key_in_format_1():
    obj = json.loads(_full_matrix().to_json())
    obj["format"] = 1
    with pytest.raises(ValueError, match="unknown key 'findings'"):
        ResultMatrix.from_json(json.dumps(obj))


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
        ["results", 0, "findings", 0, "extra"],
        ["results", 0, "findings", 0, "location", "extra"],
    ],
    ids=["matrix", "target", "result", "location", "finding", "finding location"],
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
        ["results", 0, "findings"],
        ["results", 0, "findings_omitted"],
        ["results", 0, "findings", 0, "message"],
        ["results", 0, "findings", 0, "data"],
        ["results", 0, "findings", 0, "location", "block"],
    ],
    ids=[
        "matrix",
        "target",
        "result",
        "location",
        "findings",
        "findings_omitted",
        "finding",
        "finding data",
        "finding location",
    ],
)
def test_from_json_rejects_a_missing_key(path):
    with pytest.raises(ValueError, match=f"missing key '{path[-1]}'"):
        ResultMatrix.from_json(_set(path, _DELETE))


@pytest.mark.parametrize(
    "path, value",
    [
        (["results", 0, "findings"], {}),
        (["results", 0, "findings"], None),
        (["results", 0, "findings", 0], "a string"),
        (["results", 0, "findings", 0, "code"], 1),
        (["results", 0, "findings", 0, "code"], ""),
        (["results", 0, "findings", 0, "message"], None),
        (["results", 0, "findings", 0, "data"], []),
        (["results", 0, "findings", 0, "data", "axis"], ["y"]),
        (["results", 0, "findings", 0, "data", "axis"], {"a": 1}),
        (["results", 0, "findings", 0, "location"], 5),
        (["results", 0, "findings", 0, "location", "time_s"], "1"),
    ],
    ids=[
        "findings is an object",
        "findings is null",
        "finding is a string",
        "code is an integer",
        "code is empty",
        "message is null",
        "data is a list",
        "data value is a list",
        "data value is an object",
        "location is an integer",
        "time is a string",
    ],
)
def test_from_json_rejects_a_bad_finding(path, value):
    with pytest.raises(ValueError):
        ResultMatrix.from_json(_set(path, value))


@pytest.mark.parametrize("bad", ["1", 1.0, 1.5, True, -1, None, [0]])
def test_from_json_rejects_a_findings_omitted_that_is_not_an_integer_of_0_or_more(bad):
    with pytest.raises(ValueError, match="findings_omitted"):
        ResultMatrix.from_json(_set(["results", 0, "findings_omitted"], bad))


def test_from_json_keeps_a_data_string_that_is_not_a_non_finite_float():
    # Only "inf", "-inf" and "nan" are read as floats in the data.
    text = _set(["results", 0, "findings", 0, "data", "axis"], "infinity")
    back = ResultMatrix.from_json(text)
    assert back.results[0].findings[0].data["axis"] == "infinity"


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"code": 1, "message": "m"}, TypeError),
        ({"code": None, "message": "m"}, TypeError),
        ({"code": "", "message": "m"}, ValueError),
        ({"code": "A", "message": 1}, TypeError),
        ({"code": "A", "message": None}, TypeError),
        ({"code": "A", "message": "m", "location": (1, 0.5)}, TypeError),
        ({"code": "A", "message": "m", "location": 1}, TypeError),
        ({"code": "A", "message": "m", "data": [("a", 1)]}, TypeError),
        ({"code": "A", "message": "m", "data": {1: "x"}}, TypeError),
        ({"code": "A", "message": "m", "data": {"a": [1]}}, TypeError),
        ({"code": "A", "message": "m", "data": {"a": {"b": 1}}}, TypeError),
        ({"code": "A", "message": "m", "data": {"a": b"x"}}, TypeError),
        ({"code": "A", "message": "m", "data": {"a": "inf"}}, ValueError),
        ({"code": "A", "message": "m", "data": {"a": "-inf"}}, ValueError),
        ({"code": "A", "message": "m", "data": {"a": "nan"}}, ValueError),
    ],
    ids=[
        "code is an integer",
        "code is None",
        "code is empty",
        "message is an integer",
        "message is None",
        "location is a tuple",
        "location is an integer",
        "data is a list",
        "data key is an integer",
        "data value is a list",
        "data value is a dict",
        "data value is bytes",
        "data value is the string inf",
        "data value is the string -inf",
        "data value is the string nan",
    ],
)
def test_finding_rejects_a_bad_value(kwargs, error):
    with pytest.raises(error):
        Finding(**kwargs)


def test_finding_accepts_each_type_of_data_value():
    f = Finding(
        code="A",
        message="m",
        location=Location(block=1, time_s=0.0),
        data={
            "s": "text",
            "i": 1,
            "f": 1.5,
            "inf": math.inf,
            "nan": math.nan,
            "t": True,
            "n": None,
            "other string": "Inf",
        },
    )
    assert f.data["t"] is True
    assert Finding("A", "m").data == {}
    assert Finding("A", "m").location is None


def test_a_result_has_no_findings_by_default():
    r = _result(State.PASS)
    assert r.findings == ()
    assert r.findings_omitted == 0


def _matrix_with_counts(*counts: int, omitted: int = 0) -> ResultMatrix:
    return _matrix(
        *(
            _result(
                State.FAIL,
                findings=tuple(Finding(f"C{i}", f"finding {i}") for i in range(count)),
                findings_omitted=omitted,
            )
            for count in counts
        )
    )


def test_with_max_findings_zero_keeps_none_and_counts_all():
    m = _matrix_with_counts(3, 0, omitted=2).with_max_findings(0)
    assert [r.findings for r in m.results] == [(), ()]
    assert [r.findings_omitted for r in m.results] == [5, 2]


def test_with_max_findings_below_the_count_keeps_the_first_ones():
    original = _matrix_with_counts(5)
    m = original.with_max_findings(2)
    assert [f.code for f in m.results[0].findings] == ["C0", "C1"]
    assert m.results[0].findings_omitted == 3
    # The other fields are the same, and the original matrix does not change.
    assert m.results[0].check_id == original.results[0].check_id
    assert m.targets == original.targets
    assert len(original.results[0].findings) == 5
    assert original.results[0].findings_omitted == 0


@pytest.mark.parametrize("n", [3, 4, 100])
def test_with_max_findings_at_or_above_the_count_changes_nothing(n):
    original = _matrix_with_counts(3, 1, omitted=7)
    assert original.with_max_findings(n) == original


def test_with_max_findings_adds_to_an_existing_findings_omitted():
    m = _matrix_with_counts(4, omitted=10).with_max_findings(1)
    assert len(m.results[0].findings) == 1
    assert m.results[0].findings_omitted == 13
    again = m.with_max_findings(0)
    assert again.results[0].findings_omitted == 14


def test_with_max_findings_limits_each_result_separately():
    m = _matrix_with_counts(1, 3, 5).with_max_findings(2)
    assert [len(r.findings) for r in m.results] == [1, 2, 2]
    assert [r.findings_omitted for r in m.results] == [0, 1, 3]


def test_with_max_findings_survives_a_json_round_trip():
    m = _matrix_with_findings().with_max_findings(1)
    assert ResultMatrix.from_json(m.to_json()) == m


@pytest.mark.parametrize("bad", [-1, True, False, 1.0, "1", None])
def test_with_max_findings_rejects_a_bad_n(bad):
    with pytest.raises(ValueError, match="maximum number of findings"):
        _matrix_with_counts(2).with_max_findings(bad)
