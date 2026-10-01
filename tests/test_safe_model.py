import dataclasses
import math

import numpy as np
import pytest
from pulseq_analysis.pns_levels import SAFE_FIELDS, PnsLevels, pns_levels
from pypulseq.utils.safe_pns_prediction import safe_example_hw
from synthetic import spin_echo_sequence

from pulseq_checks.safe_model import SAFE_MODEL, hw_from_dict


def _assert_levels_equal(a: PnsLevels, b: PnsLevels, *, ignore: tuple[str, ...]) -> None:
    """Every field of `a` and `b` is exactly equal, except the fields named in `ignore`
    (`numpy.array_equal` for the arrays, `==` for the rest)."""
    for field in dataclasses.fields(PnsLevels):
        if field.name in ignore:
            continue
        x, y = getattr(a, field.name), getattr(b, field.name)
        if isinstance(x, np.ndarray):
            assert np.array_equal(x, y), field.name
        else:
            assert x == y, field.name


def _safe_dict(name: str | None = "MP_GPA_EXAMPLE") -> dict:
    """The parameters of `safe_example_hw()` as the dict of `SAFE_MODEL.read`, with the
    `name` when it is not None."""
    hw = safe_example_hw()
    params = {"name": name} if name is not None else {}
    for axis in "xyz":
        params[axis] = {field: getattr(getattr(hw, axis), field) for field in SAFE_FIELDS}
    return params


def test_safe_model_reads_a_valid_dict():
    """`SAFE_MODEL.read` of the example parameters gives an equal new dict of floats, and
    the model has the name `pns.safe` and the version 1. An int is read as a float, and
    `name` is optional."""
    assert SAFE_MODEL.name == "pns.safe"
    assert SAFE_MODEL.version == 1
    params = _safe_dict()
    result = SAFE_MODEL.read(params)
    assert result == params
    assert result is not params
    assert result["x"] is not params["x"]
    assert all(type(v) is float for axis in "xyz" for v in result[axis].values())

    assert "name" not in SAFE_MODEL.read(_safe_dict(name=None))
    params["y"]["stim_limit"] = 15  # an int
    read = SAFE_MODEL.read(params)["y"]["stim_limit"]
    assert read == 15.0
    assert type(read) is float


@pytest.mark.parametrize(
    ("edit", "key"),
    [
        (lambda p: p.update(extra=1.0), "extra"),
        (lambda p: p["z"].update(tau4=1.0), "z.tau4"),
    ],
    ids=["axis level", "field level"],
)
def test_safe_model_refuses_an_unknown_key(edit, key):
    """`SAFE_MODEL.read` raises `ValueError` that names an unknown key (with its axis for
    a field)."""
    params = _safe_dict()
    edit(params)
    with pytest.raises(ValueError, match="unknown key") as info:
        SAFE_MODEL.read(params)
    assert key in str(info.value)


def test_safe_model_refuses_a_missing_field_or_axis():
    """`SAFE_MODEL.read` raises `ValueError` that names a missing field (with its axis)
    or a missing axis."""
    params = _safe_dict()
    del params["y"]["a2"]
    with pytest.raises(ValueError, match="missing key 'y.a2'"):
        SAFE_MODEL.read(params)

    params = _safe_dict()
    del params["z"]
    with pytest.raises(ValueError, match="missing key 'z'"):
        SAFE_MODEL.read(params)


@pytest.mark.parametrize("value", [True, False, "1.0", None, [1.0], math.nan, math.inf, -math.inf])
def test_safe_model_refuses_a_value_that_is_not_a_real_number(value):
    """`SAFE_MODEL.read` raises `ValueError` that names the key of a field whose value is a
    bool, another type that is not an int or a float, or a float that is not finite; a
    `name` that is not a str raises too."""
    params = _safe_dict()
    params["x"]["tau2"] = value
    with pytest.raises(ValueError, match=r"x\.tau2"):
        SAFE_MODEL.read(params)

    params = _safe_dict(name=None)
    params["name"] = 1
    with pytest.raises(ValueError, match="name"):
        SAFE_MODEL.read(params)


def test_hw_from_dict_gives_the_example_hardware():
    """`hw_from_dict(SAFE_MODEL.read(params))` has the name and the 27 values of
    `safe_example_hw()`, "unknown" without a name, and used as `hardware` it gives the
    levels of the example hardware exactly (except the label)."""
    hw = hw_from_dict(SAFE_MODEL.read(_safe_dict()))
    example = safe_example_hw()
    assert hw.name == example.name
    for axis in "xyz":
        for field in SAFE_FIELDS:
            assert getattr(getattr(hw, axis), field) == getattr(getattr(example, axis), field)
    assert hw_from_dict(SAFE_MODEL.read(_safe_dict(name=None))).name == "unknown"

    seq = spin_echo_sequence()
    levels = pns_levels(seq, hardware=(hw, "LABEL"))
    _assert_levels_equal(levels, pns_levels(seq), ignore=("hardware",))
