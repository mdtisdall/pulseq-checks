"""The check configuration (plan section 4.6, decision 9): `read_check_config` reads the
targets and the selected checks from a TOML or JSON file. `pulseq-check` and pulseq-reports
both read it with this function."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .results import CheckRunError

# The newest configuration format that this reader reads (the "format" key).
FORMAT_VERSION = 1
KEYS = ("format", "targets", "select", "required", "fast_only")


class ConfigError(CheckRunError):
    """A check configuration that is missing or not valid: an error of the run."""


@dataclass(frozen=True)
class CheckConfig:
    """A check configuration. `targets` are the paths of the profile files, relative to the
    configuration file (this function does not read them). `select` is the check IDs, or
    None for all. `required` maps a check ID to the target names for which it is required,
    or to None for all targets. This function does not compare the IDs with the installed
    checks: `run_checks` does."""

    source_path: Path
    format_version: int
    targets: tuple[Path, ...]
    select: tuple[str, ...] | None
    required: dict[str, tuple[str, ...] | None]
    fast_only: bool


def read_check_config(path: str | Path) -> CheckConfig:
    """The check configuration in the TOML or JSON file `path`. Raises `ConfigError`."""
    path = Path(path)
    data = _read_file(path)

    def fail(message: str) -> ConfigError:
        return ConfigError(f"{path}: {message}")

    for key in data:
        if key not in KEYS:
            raise fail(f"unknown key {key!r} (the keys are {', '.join(KEYS)})")

    if "format" not in data:
        raise fail('"format" is necessary')
    format_version = data["format"]
    if type(format_version) is not int or format_version < 1:
        raise fail(f'"format" must be a whole number of 1 or more, not {format_version!r}')
    if format_version > FORMAT_VERSION:
        raise fail(
            f"the format is version {format_version}, and this reader reads up to "
            f"version {FORMAT_VERSION}"
        )

    if "targets" not in data:
        raise fail('"targets" is necessary')
    targets = data["targets"]
    if not _is_list_of_str(targets) or not targets:
        raise fail(f'"targets" must be a non-empty list of profile file paths, not {targets!r}')
    if not all(targets):
        raise fail('"targets" has an empty path')

    select = data.get("select")
    if select is not None and not _is_list_of_str(select):
        raise fail(f'"select" must be a list of check IDs, not {select!r}')

    fast_only = data.get("fast_only", False)
    if type(fast_only) is not bool:
        raise fail(f'"fast_only" must be true or false, not {fast_only!r}')

    table = data.get("required", {})
    if not isinstance(table, dict):
        raise fail(f'"required" must be a table of check IDs, not {table!r}')
    required: dict[str, tuple[str, ...] | None] = {}
    for check_id, value in table.items():
        if value is True:
            required[check_id] = None
        elif _is_list_of_str(value):
            required[check_id] = tuple(value)
        else:
            raise fail(
                f'"required.{check_id}" must be true (all targets) or a list of target '
                f"names, not {value!r}"
            )

    return CheckConfig(
        source_path=path,
        format_version=format_version,
        targets=tuple(path.parent / target for target in targets),
        select=None if select is None else tuple(select),
        required=required,
        fast_only=fast_only,
    )


def _read_file(path: Path) -> dict[str, Any]:
    """The top-level table of the TOML or JSON file `path`, by its suffix."""
    readers = {".toml": tomllib.loads, ".json": json.loads}
    if path.suffix not in readers:
        raise ConfigError(f"{path}: the suffix must be .toml or .json, not {path.suffix!r}")
    try:
        data = readers[path.suffix](path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"{path}: cannot read the file: {e}") from e
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as e:
        raise ConfigError(f"{path}: the file is not valid {path.suffix[1:].upper()}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the file must have a table at the top level")
    return data


def _is_list_of_str(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
