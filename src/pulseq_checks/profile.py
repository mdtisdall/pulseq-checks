"""The target profile (plan section 4.3, design section 5.11): `TargetProfile`, the profile
file reader `read_profile`, and `ProfileError`."""

from __future__ import annotations

import inspect
import json
import math
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, NoReturn

import pypulseq as pp

from . import registry
from .grad_limits import HardwareLimits
from .results import CheckRunError

# The newest profile format that this reader reads (the "format" key).
FORMAT_VERSION = 1
# The reserved [DEFINITIONS] names of the rasters, and the pp.Opts keyword of each.
RASTER_OPTS = {
    "GradientRasterTime": "grad_raster_time",
    "RadiofrequencyRasterTime": "rf_raster_time",
    "AdcRasterTime": "adc_raster_time",
    "BlockDurationRaster": "block_duration_raster",
}
# The keys of the top level of a profile file, and its sections (plan section 4.3, rule 3).
_TOP_KEYS = frozenset({"format", "name", "vendor", "asc", "asc_gradient_mode"})
_SECTIONS = ("opts", "rasters", "models", "acoustic")
# The label of the values of the profile file in `TargetProfile.sources`.
_PROFILE_LABEL = "profile"
# The value paths that pp.Opts calculates from other values: pp.Opts sets max_slew to
# max_grad / rise_time when it gets rise_time. All the values of the tuple are necessary,
# because pp.Opts uses its default max_grad when the profile does not give one.
_CALCULATED = {"opts.max_slew": ("opts.max_grad", "opts.rise_time")}


class ProfileError(CheckRunError):
    """A target profile that is missing or not valid: an error of the run (R2)."""


@dataclass(frozen=True)
class TargetProfile:
    """A target: the values of one profile file and of the `.asc` file that it names.

    A value that no source gives is None (or not in the mapping); the reader supplies no
    default (rule 6). `sources` maps the value path of each value that a source gives
    ("opts.max_grad", "rasters.GradientRasterTime", "models.pns.safe",
    "acoustic.resonances") to "profile" or to the label of the `.asc` reader.
    `hardware_limits` comes from `opts.max_grad` and the slew limit (both necessary, see
    `has_value`), in mT/m and T/m/s, with the label `name`. `rasters` has the reserved names of
    `RASTER_OPTS`. `models` maps a model name ("pns.safe") to the parameters that its model
    `read` returned."""

    name: str
    vendor: str | None
    format_version: int
    source_path: Path | None
    opts: Mapping[str, Any] | None
    hardware_limits: HardwareLimits | None
    rasters: Mapping[str, float] | None
    models: Mapping[str, Mapping[str, Any]]
    acoustic_resonances: tuple[tuple[float, float], ...] | None
    sources: Mapping[str, str]
    unused_sections: tuple[str, ...]

    def make_opts(self) -> pp.Opts:
        """`pp.Opts(**opts)`, with the rasters given to their `RASTER_OPTS` keywords. A value
        that the profile does not give has the default of pypulseq here, so a check must
        not use it: the run function gives "not evaluated" for a missing input."""
        keywords = dict(self.opts or {})
        for name, value in (self.rasters or {}).items():
            keywords[RASTER_OPTS[name]] = value
        return pp.Opts(**keywords)

    def has_value(self, path: str) -> bool:
        """True when a source gives the value path `path` (a key of `sources`), or gives all
        the values from which pp.Opts calculates it: `opts.max_slew` is given also by
        `opts.max_grad` with `opts.rise_time` (max_grad / rise_time). `sources` has only the
        values that a source gives."""
        if path in self.sources:
            return True
        needs = _CALCULATED.get(path)
        return needs is not None and all(p in self.sources for p in needs)


def _opts_keys() -> frozenset[str]:
    """The keyword names of `pp.Opts.__init__`, less the four raster keywords."""
    names = set(inspect.signature(pp.Opts.__init__).parameters) - {"self"}
    return frozenset(names - set(RASTER_OPTS.values()))


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _load(path: Path, fail: Callable[[str], NoReturn]) -> dict:
    """The top-level table of the TOML or JSON file `path` (rule 1)."""
    if path.suffix == ".toml":
        parse = tomllib.loads
    elif path.suffix == ".json":
        parse = json.loads
    else:
        fail(f"the suffix {path.suffix!r} is not .toml or .json")
    try:
        data = parse(path.read_bytes().decode("utf-8"))
    except OSError as e:
        fail(f"cannot read the file: {e}")
    except ValueError as e:  # TOMLDecodeError, JSONDecodeError and UnicodeDecodeError
        fail(f"cannot parse the file: {e}")
    if not isinstance(data, dict):
        fail("the top level is not a table")
    return data


def _split_models(
    table: Mapping[str, Any],
    installed: Mapping[str, Any],
    prefix: str,
    fail: Callable[[str], NoReturn],
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    """The sections of the installed models in `table` (a table under `models`, at the
    dotted path `prefix`), and the names of the highest tables with no installed model
    under them."""
    found: dict[str, Mapping[str, Any]] = {}
    unused: list[str] = []
    for key, value in table.items():
        dotted = prefix + key
        if not isinstance(value, dict):
            fail(f"models.{dotted} is not a table")
        if dotted in installed:
            found[dotted] = value
        elif any(name.startswith(dotted + ".") for name in installed):
            sub_found, sub_unused = _split_models(value, installed, dotted + ".", fail)
            found.update(sub_found)
            unused.extend(sub_unused)
        else:
            unused.append(f"models.{dotted}")
    return found, unused


def _read_values(
    sections: Mapping[str, Any],
    installed: Mapping[str, Any],
    fail: Callable[[str], NoReturn],
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]], list[str]]:
    """Check the sections `opts`, `rasters`, `models` and `acoustic` of `sections` (the
    profile file or the output of a profile reader). Returns the value of each value path
    (not the models), the section of each installed model by its name, and the unused
    model sections."""
    values: dict[str, Any] = {}
    for section in sections:
        if section not in _SECTIONS:
            fail(f"unknown section {section!r}")
        if not isinstance(sections[section], dict):
            fail(f"[{section}] is not a table")

    known = _opts_keys()
    for key, value in sections.get("opts", {}).items():
        if key in RASTER_OPTS.values():
            names = [name for name, keyword in RASTER_OPTS.items() if keyword == key]
            fail(
                f"{key!r} is not a key of [opts]: the rasters go in [rasters] "
                f"with their reserved names, here {names[0]!r}"
            )
        if key not in known:
            fail(f"unknown key {key!r} in [opts]")
        if value is None:  # pp.Opts takes None as "use the default" (rule 6)
            fail(f"opts.{key} is null")
        values[f"opts.{key}"] = value

    for key, value in sections.get("rasters", {}).items():
        if key == "rule":
            fail(
                "rasters.rule is not a key of [rasters]: the raster check of this version "
                "needs equal rasters and has no rule"
            )
        if key not in RASTER_OPTS:
            fail(f"unknown key {key!r} in [rasters]")
        elif not (_is_number(value) and math.isfinite(value) and value > 0):
            fail(f"rasters.{key} must be a positive number, not {value!r}")
        values[f"rasters.{key}"] = value

    for key, value in sections.get("acoustic", {}).items():
        if key != "resonances":
            fail(f"unknown key {key!r} in [acoustic]")
        if not isinstance(value, list) or not all(
            isinstance(pair, list) and len(pair) == 2 and all(map(_is_number, pair))
            for pair in value
        ):
            fail("acoustic.resonances must be a list of [frequency, bandwidth] pairs")
        values["acoustic.resonances"] = tuple((float(f), float(bw)) for f, bw in value)

    model_sections, unused = _split_models(sections.get("models", {}), installed, "", fail)
    return values, model_sections, unused


def read_profile(path: str | Path) -> TargetProfile:
    """The target profile in the TOML or JSON file `path` (plan section 4.3, rules 1 to 6,
    and section 4.9). Raises `ProfileError`."""
    path = Path(path)

    def fail(message: str) -> NoReturn:
        raise ProfileError(f"target profile {path}: {message}")

    raw = _load(path, fail)

    version = raw.get("format")
    if version is None:
        fail('the necessary key "format" is missing')
    if not isinstance(version, int) or isinstance(version, bool):
        fail(f'"format" must be an integer, not {version!r}')
    if version > FORMAT_VERSION:
        fail(
            f"the profile has format {version}, and this reader reads format "
            f"{FORMAT_VERSION} at most"
        )
    if version < 1:
        fail(f'"format" must be 1 or more, not {version}')

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        fail('the necessary key "name" must be a non-empty string')
    vendor = raw.get("vendor")
    if vendor is not None and not isinstance(vendor, str):
        fail(f'"vendor" must be a string, not {vendor!r}')
    asc = raw.get("asc")
    if asc is not None and (not isinstance(asc, str) or not asc):
        fail(f'"asc" must be a non-empty string, not {asc!r}')
    mode = raw.get("asc_gradient_mode")
    if mode is not None and not isinstance(mode, str):
        fail(f'"asc_gradient_mode" must be a string, not {mode!r}')
    if mode is not None and asc is None:
        fail('"asc_gradient_mode" needs "asc"')

    unused: list[str] = []
    for key, value in raw.items():
        if key in _TOP_KEYS or key in _SECTIONS:
            continue
        if not isinstance(value, dict):
            fail(f"unknown key {key!r} in the top level")
        unused.append(key)

    installed = registry.models()
    values, model_sections, unused_models = _read_values(
        {key: raw[key] for key in _SECTIONS if key in raw}, installed, fail
    )
    unused.extend(unused_models)
    sources = {
        **{value_path: _PROFILE_LABEL for value_path in values},
        **{f"models.{model_name}": _PROFILE_LABEL for model_name in model_sections},
    }

    source_path = path.resolve()
    if asc is not None:
        reader = registry.profile_reader("siemens-asc")
        asc_path = source_path.parent / asc
        if reader is None:
            fail('"asc" needs the profile reader "siemens-asc", and no package gives it')
        try:
            asc_sections, asc_sources = reader(asc_path, gradient_mode=mode)
        except (ValueError, OSError) as e:
            fail(f"cannot read the .asc file {asc_path}: {e}")

        def asc_fail(message: str) -> NoReturn:
            fail(f"the reader of {asc_path} gave {message}")

        asc_values, asc_models, asc_unused = _read_values(asc_sections, installed, asc_fail)
        asc_values.update({f"models.{n}": section for n, section in asc_models.items()})
        for value_path in asc_values:
            label = asc_sources.get(value_path)
            if label is None:
                asc_fail(f"the value {value_path} without a source")
            if value_path in sources:
                fail(f"{value_path} is given twice: by {sources[value_path]!r} and by {label!r}")
            sources[value_path] = label
        values.update({p: v for p, v in asc_values.items() if not p.startswith("models.")})
        model_sections.update(asc_models)
        unused.extend(u for u in asc_unused if u not in unused)

    # pp.Opts replaces max_slew with max_grad / rise_time, without a message.
    if "opts.max_slew" in sources and "opts.rise_time" in sources:
        fail(
            f"opts.max_slew (given by {sources['opts.max_slew']!r}) and opts.rise_time (given "
            f"by {sources['opts.rise_time']!r}) both give the slew limit: give only one of them"
        )

    models: dict[str, Mapping[str, Any]] = {}
    for model_name, section in model_sections.items():
        try:
            models[model_name] = installed[model_name].read(section)
        except ValueError as e:
            fail(f"models.{model_name} is not valid: {e}")

    opts = {p.removeprefix("opts."): v for p, v in values.items() if p.startswith("opts.")}
    rasters = {p.removeprefix("rasters."): v for p, v in values.items() if p.startswith("rasters.")}
    profile = TargetProfile(
        name=name,
        vendor=vendor,
        format_version=version,
        source_path=source_path,
        opts=opts or None,
        hardware_limits=None,
        rasters=rasters or None,
        models=models,
        acoustic_resonances=values.get("acoustic.resonances"),
        sources=sources,
        unused_sections=tuple(unused),
    )
    if not (opts or rasters):
        return profile

    # pp.Opts checks the units only. A value that is not a number gives a TypeError when it is
    # used, for the hardware limits here.
    try:
        built = profile.make_opts()
        if profile.has_value("opts.max_grad") and profile.has_value("opts.max_slew"):
            limits = HardwareLimits(
                max_grad_mt_per_m=built.max_grad / built.gamma * 1e3,
                max_slew_t_per_m_per_s=built.max_slew / built.gamma,
                label=name,
            )
            profile = replace(profile, hardware_limits=limits)
    except (ValueError, TypeError, ArithmeticError) as e:
        fail(f"pp.Opts does not accept the values of [opts] and [rasters]: {e}")
    return profile
