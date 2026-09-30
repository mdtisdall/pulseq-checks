"""The Siemens `.asc` profile reader (entry point `siemens-asc` in the group
`pulseq_checks.profile_readers`): `read_asc_profile` reads the gradient system's `.asc` file
(with its `$INCLUDE` files) and gives the sections of a target profile and the source of
each value path. It gives only what the file has: the SAFE PNS parameters as
`models.pns.safe`, the acoustic resonances as `acoustic.resonances`, and, for a
`gradient_mode`, the GPA limits as `opts` (`max_grad`, `max_slew` and their units). A value
that the file does not have is not given, and that is not an error: the profile file can
give it. The reader supplies no default: a part of a group of values that the file has (the
SAFE parameters without a gradient scale factor, a resonance without its bandwidth) and a
`gradient_mode` that the file does not have are a `ValueError`. A missing file, or a
missing `$INCLUDE` file, is an `OSError`."""

import math
from pathlib import Path

from pypulseq.utils.siemens.asc_to_hw import asc_to_hw

from pulseq_checks.asc import hardware_name, read_gradient_asc

_FIELDS = ("tau1", "tau2", "tau3", "a1", "a2", "a3", "stim_limit", "stim_thresh", "g_scale")
# The mode names of the profile, and the names that the fields of the file use. "nominal" is
# not here: the file gives it no rise time.
_GRADIENT_MODES = {
    "absolute": "Absolute",
    "normal": "Normal",
    "fast": "Fast",
    "ultrafast": "UltraFast",
    "whisper": "Whisper",
    "boost": "Boost",
}


def read_asc_profile(
    path: Path, *, gradient_mode: str | None = None
) -> tuple[dict, dict[str, str]]:
    """The sections and the sources of the `.asc` file `path`. The source of each value
    path is `path.name`, followed by ` (<gradient_mode>)` for the GPA limits.

    With a `gradient_mode` (`absolute`, `normal`, `fast`, `ultrafast`, `whisper` or `boost`),
    `opts` has the limits of that operation mode: `max_grad` in mT/m from
    `asGPAParameters[0].flGradMaxAmpl<Mode>`, and `max_slew` in T/m/s, which is
    `1000 / asGPAParameters[0].flGradMinRiseTime<Mode>` (the rise time is in µs per mT/m).
    Without a `gradient_mode`, there is no `opts` section. An unknown mode, or a mode that the
    file does not have (a missing field, or a value that is not a positive finite number),
    is a `ValueError`."""
    if gradient_mode is not None and gradient_mode not in _GRADIENT_MODES:
        raise ValueError(
            f"unknown gradient mode {gradient_mode!r}; the known modes are "
            f"{', '.join(_GRADIENT_MODES)}"
        )
    path = Path(path)
    asc = read_gradient_asc(path)
    sections: dict = {}
    sources: dict[str, str] = {}

    if gradient_mode is not None:
        sections["opts"] = _gradient_limits(asc, path, gradient_mode)
        for key in sections["opts"]:
            sources[f"opts.{key}"] = f"{path.name} ({gradient_mode})"

    safe = _safe_parameters(asc, path)
    if safe is not None:
        sections["models"] = {"pns": {"safe": safe}}
        sources["models.pns.safe"] = path.name

    resonances = _resonances(asc, path)
    if resonances:
        sections["acoustic"] = {"resonances": resonances}
        sources["acoustic.resonances"] = path.name
    return sections, sources


def _gpa_parameters(asc: dict) -> dict:
    """`asGPAParameters[0]` of `asc`; empty when the file has none."""
    return asc.get("asGPAParameters", {}).get(0, {})


def _gradient_limits(asc: dict, path: Path, gradient_mode: str) -> dict:
    """The `opts` section for `gradient_mode` (a key of `_GRADIENT_MODES`). It reads the
    `flGrad...` fields, not their `flDefGrad...` twins."""
    siemens = _GRADIENT_MODES[gradient_mode]
    gpa = _gpa_parameters(asc)
    values = {}
    for name in (f"flGradMaxAmpl{siemens}", f"flGradMinRiseTime{siemens}"):
        if name not in gpa:
            raise ValueError(
                f"{path.name} has no gradient limits for the mode {gradient_mode!r}: "
                f"asGPAParameters[0].{name} is missing"
            )
        value = gpa[name]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(
                f"{path.name}, mode {gradient_mode!r}: asGPAParameters[0].{name} is "
                f"{value!r}, not a positive finite number"
            )
        values[name] = float(value)
    amplitude, rise_time = values.values()
    return {
        "max_grad": amplitude,
        "grad_unit": "mT/m",
        "max_slew": 1000 / rise_time,
        "slew_unit": "T/m/s",
    }


def _safe_parameters(asc: dict, path: Path) -> dict | None:
    """The SAFE parameters as pypulseq's `asc_to_hw` reads them, or None when the file has
    none: no `flGSWD*` field, in the `GradPatSup.Phys.PNS` block or at the top level. A file
    with some of the fields but not all, or with the fields but without the three gradient
    scale factors (`asGPAParameters[0].sGCParameters.flGScaleFactorX`, `Y`, `Z`; `asc_to_hw`
    would assume 1/pi), is a `ValueError`."""
    pns = asc.get("GradPatSup", {}).get("Phys", {}).get("PNS") if "GradPatSup" in asc else asc
    if not isinstance(pns, dict) or not any(key.startswith("flGSWD") for key in pns):
        return None
    scale_factors = _gpa_parameters(asc).get("sGCParameters", {})
    for axis in "XYZ":
        if f"flGScaleFactor{axis}" not in scale_factors:
            raise ValueError(
                f"{path.name} has SAFE parameters but no gradient scale factor: "
                f"asGPAParameters[0].sGCParameters.flGScaleFactor{axis} is missing"
            )
    try:
        hw = asc_to_hw(asc)
    except (KeyError, IndexError) as error:
        raise ValueError(f"{path.name} has incomplete SAFE parameters: {error!r}") from error
    safe: dict = {"name": hardware_name(asc)}
    for axis in "xyz":
        safe[axis] = {field: float(getattr(getattr(hw, axis), field)) for field in _FIELDS}
    return safe


def _resonances(asc: dict, path: Path) -> list[list[float]]:
    """The `[frequency, bandwidth]` pairs of the acoustic resonances, as pypulseq's
    `asc_to_acoustic_resonances` gives them (the frequencies that are not 0), in its two
    layouts, in the order of their indices. An empty list when the file has neither.

    `readasc` gives each list as a dict of index to value. A frequency and a bandwidth are a
    pair when they have the same index, so the two dicts must have the same indices: the
    same indices, not only the same count. Otherwise (a bandwidth list that is missing or
    that has other indices, also a bandwidth list without frequencies) it is a `ValueError`;
    pypulseq would raise a `KeyError` for a missing bandwidth list and drop the extra
    entries of the longer list."""
    if "aflGCAcousticResonanceFrequency" in asc or "aflGCAcousticResonanceBandwidth" in asc:
        freqs = asc.get("aflGCAcousticResonanceFrequency", {})
        bandwidths = asc.get("aflGCAcousticResonanceBandwidth", {})
    else:
        gc = _gpa_parameters(asc).get("sGCParameters", {})
        freqs = gc.get("aflAcousticResonanceFrequency", {})
        bandwidths = gc.get("aflAcousticResonanceBandwidth", {})
    if freqs.keys() != bandwidths.keys():
        raise ValueError(
            f"{path.name} has acoustic resonance frequencies at the indices {sorted(freqs)} "
            f"but bandwidths at the indices {sorted(bandwidths)}"
        )
    return [[float(freqs[i]), float(bandwidths[i])] for i in sorted(freqs) if freqs[i] != 0]
