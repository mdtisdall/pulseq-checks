"""The SAFE model of the target profile (`[models.pns.safe]`), and `hw_from_dict`, which
makes the hardware argument of `pulseq_analysis.pns.pns_levels_for` from the parameters
of that model."""

import math
from collections.abc import Mapping
from types import SimpleNamespace

from pulseq_analysis.pns_levels import SAFE_FIELDS

_AXES3 = ("x", "y", "z")

# ---- The SAFE model of the target profile (`[models.pns.safe]`, docs/usage.md) ----


def _real(value: object, key: str) -> float:
    """`value` as a float, when it is a finite int or float and not a bool; ValueError that
    names `key` otherwise."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key}: must be a real number, not {type(value).__name__}")  # noqa: TRY004
    if not math.isfinite(value):
        raise ValueError(f"{key}: must be a finite number, not {value!r}")
    return float(value)


class _SafeModel:
    """The model `pns.safe` of the target profile (`[models.pns.safe]`): the hardware
    parameters of the SAFE PNS model."""

    name = "pns.safe"
    version = 1

    def read(self, params: Mapping) -> dict:
        """The checked parameters of `params` as a new plain dict with float values: an
        optional `name` (str) and the axes `x`, `y` and `z`, each a mapping with exactly the
        nine fields of `SAFE_FIELDS`. Raises ValueError, with a message that names the key
        (with its axis), for an unknown key, a missing key, a value of the wrong type or a
        value that is not finite."""
        if not isinstance(params, Mapping):
            raise ValueError("pns.safe: the parameters must be a mapping")  # noqa: TRY004
        for key in params:
            if key not in ("name", *_AXES3):
                raise ValueError(f"unknown key {key!r}")
        result: dict = {}
        if "name" in params:
            if not isinstance(params["name"], str):
                raise ValueError(f"name: must be a string, not {type(params['name']).__name__}")
            result["name"] = params["name"]
        for axis in _AXES3:
            if axis not in params:
                raise ValueError(f"missing key {axis!r}")
            fields = params[axis]
            if not isinstance(fields, Mapping):
                raise ValueError(f"{axis}: must be a mapping of the SAFE fields")  # noqa: TRY004
            for key in fields:
                if key not in SAFE_FIELDS:
                    raise ValueError(f"unknown key '{axis}.{key}'")
            for field in SAFE_FIELDS:
                if field not in fields:
                    raise ValueError(f"missing key '{axis}.{field}'")
            result[axis] = {field: _real(fields[field], f"{axis}.{field}") for field in SAFE_FIELDS}
        return result


SAFE_MODEL = _SafeModel()


def hw_from_dict(params: Mapping) -> SimpleNamespace:
    """The SAFE hardware struct in the form of pypulseq's `asc_to_hw` (for the `hardware`
    argument of `pns_levels`) from the parameters of `SAFE_MODEL.read`. It checks `params`
    with `SAFE_MODEL.read`, so it raises the same ValueError. `name` is the name in
    `params`, or "unknown" without one. `_safe_gwf_to_pns_chunk` does not use the `checksum`
    and `dependency` of `safe_example_hw`, so the struct does not have them."""
    checked = SAFE_MODEL.read(params)
    hw = SimpleNamespace(name=checked.get("name", "unknown"))
    for axis in _AXES3:
        setattr(hw, axis, SimpleNamespace(**checked[axis]))
    return hw
