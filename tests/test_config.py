import dataclasses
import json
from pathlib import Path

import pytest

from pulseq_checks.config import CheckConfig, ConfigError, read_check_config
from pulseq_checks.results import CheckRunError

TOML = """
format = 1
targets = ["prisma.toml", "profiles/terra.json"]
select = ["gradient.slew.axis", "timing.rasters"]
fast_only = true

[required]
"timing.rasters" = true
"pns.safe" = ["prisma"]
"""

JSON = {
    "format": 1,
    "targets": ["prisma.toml", "profiles/terra.json"],
    "select": ["gradient.slew.axis", "timing.rasters"],
    "fast_only": True,
    "required": {"timing.rasters": True, "pns.safe": ["prisma"]},
}


def write_toml(tmp_path, text, name="check.toml"):
    path = tmp_path / name
    path.write_text(text)
    return path


def write_json(tmp_path, data, name="check.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def test_a_toml_file_gives_the_config(tmp_path):
    path = write_toml(tmp_path, TOML)
    assert read_check_config(path) == CheckConfig(
        source_path=path,
        format_version=1,
        targets=(tmp_path / "prisma.toml", tmp_path / "profiles" / "terra.json"),
        select=("gradient.slew.axis", "timing.rasters"),
        required={"timing.rasters": None, "pns.safe": ("prisma",)},
        fast_only=True,
    )


def test_the_toml_and_json_forms_give_equal_configs(tmp_path):
    from_toml = read_check_config(write_toml(tmp_path, TOML))
    from_json = read_check_config(write_json(tmp_path, JSON))
    assert from_toml.source_path != from_json.source_path
    same_path = dataclasses.replace(from_json, source_path=from_toml.source_path)
    assert from_toml == same_path


def test_a_file_with_only_format_and_targets_gives_the_defaults(tmp_path):
    path = write_toml(tmp_path, 'format = 1\ntargets = ["a.toml"]\n')
    config = read_check_config(path)
    assert config.select is None
    assert config.required == {}
    assert config.fast_only is False
    path = write_json(tmp_path, {"format": 1, "targets": ["a.toml"]})
    assert read_check_config(path) == dataclasses.replace(config, source_path=path)


def test_target_paths_are_relative_to_the_config_file_not_to_the_working_directory(
    tmp_path, monkeypatch
):
    folder = tmp_path / "configs"
    folder.mkdir()
    monkeypatch.chdir(tmp_path)
    path = write_toml(
        folder, 'format = 1\ntargets = ["a.toml", "../b.toml", "/abs/c.toml"]\n', "c.toml"
    )
    config = read_check_config(Path("configs") / "c.toml")
    assert config.targets == (
        Path("configs") / "a.toml",
        Path("configs") / ".." / "b.toml",
        Path("/abs/c.toml"),
    )
    assert config.source_path == Path("configs") / "c.toml"
    assert read_check_config(str(path)).targets[0] == folder / "a.toml"


def test_a_config_does_not_read_the_profiles_or_check_the_check_ids(tmp_path):
    path = write_toml(
        tmp_path,
        'format = 1\ntargets = ["missing.toml"]\nselect = ["no.such.check"]\n'
        '[required]\n"other.check" = ["no-such-target"]\n',
    )
    config = read_check_config(path)
    assert config.targets == (tmp_path / "missing.toml",)
    assert config.select == ("no.such.check",)
    assert config.required == {"other.check": ("no-such-target",)}


def test_config_error_is_an_error_of_the_run():
    assert issubclass(ConfigError, CheckRunError)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('targets = ["a.toml"]\n', '"format" is necessary'),
        ('format = 2\ntargets = ["a.toml"]\n', "version 2"),
        ('format = "1"\ntargets = ["a.toml"]\n', '"format"'),
        ('format = 1.0\ntargets = ["a.toml"]\n', '"format"'),
        ('format = true\ntargets = ["a.toml"]\n', '"format"'),
        ('format = 0\ntargets = ["a.toml"]\n', '"format"'),
        ("format = 1\n", '"targets" is necessary'),
        ("format = 1\ntargets = []\n", '"targets"'),
        ('format = 1\ntargets = "a.toml"\n', '"targets"'),
        ("format = 1\ntargets = [1]\n", '"targets"'),
        ('format = 1\ntargets = [""]\n', "empty path"),
        ('format = 1\ntargets = ["a.toml"]\nselect = "timing.rasters"\n', '"select"'),
        ('format = 1\ntargets = ["a.toml"]\nselect = [1]\n', '"select"'),
        ('format = 1\ntargets = ["a.toml"]\nfast_only = "yes"\n', '"fast_only"'),
        ('format = 1\ntargets = ["a.toml"]\nfast_only = 1\n', '"fast_only"'),
        ('format = 1\ntargets = ["a.toml"]\nrequired = ["timing.rasters"]\n', '"required"'),
        (
            'format = 1\ntargets = ["a.toml"]\n[required]\n"timing.rasters" = false\n',
            "timing.rasters",
        ),
        (
            'format = 1\ntargets = ["a.toml"]\n[required]\n"timing.rasters" = "all"\n',
            "timing.rasters",
        ),
        (
            'format = 1\ntargets = ["a.toml"]\n[required]\n"timing.rasters" = [1]\n',
            "timing.rasters",
        ),
        ('format = 1\ntargets = ["a.toml"]\nselekt = []\n', "'selekt'"),
        ('format = 1\ntargets = ["a.toml"]\nlimits_from_sequence = true\n', "limits_from_sequence"),
        ("format = 1\ntargets = [\n", "not valid TOML"),
    ],
)
def test_each_invalid_toml_config_is_an_error_that_names_the_file(tmp_path, text, message):
    path = write_toml(tmp_path, text)
    with pytest.raises(ConfigError) as excinfo:
        read_check_config(path)
    assert str(path) in str(excinfo.value)
    assert message in str(excinfo.value)


def test_a_newer_format_names_both_versions(tmp_path):
    path = write_json(tmp_path, {"format": 7, "targets": ["a.toml"]})
    with pytest.raises(ConfigError) as excinfo:
        read_check_config(path)
    assert str(path) in str(excinfo.value)
    assert "version 7" in str(excinfo.value)
    assert "version 1" in str(excinfo.value)


def test_each_invalid_json_config_is_an_error_that_names_the_file(tmp_path):
    cases = [
        ({"targets": ["a.toml"]}, '"format" is necessary'),
        ({"format": 1, "targets": ["a.toml"], "unknown": 1}, "'unknown'"),
        ({"format": 1, "targets": ["a.toml"], "fast_only": None}, '"fast_only"'),
        ({"format": 1, "targets": ["a.toml"], "required": {"timing.rasters": None}}, "timing"),
        (["format"], "table"),
    ]
    for data, message in cases:
        path = write_json(tmp_path, data)
        with pytest.raises(ConfigError) as excinfo:
            read_check_config(path)
        assert str(path) in str(excinfo.value)
        assert message in str(excinfo.value)
    path = tmp_path / "bad.json"
    path.write_text('{"format": 1,')
    with pytest.raises(ConfigError, match="not valid JSON") as excinfo:
        read_check_config(path)
    assert str(path) in str(excinfo.value)


def test_a_missing_file_and_a_wrong_suffix_are_errors_that_name_the_file(tmp_path):
    missing = tmp_path / "missing.toml"
    with pytest.raises(ConfigError, match="cannot read") as excinfo:
        read_check_config(missing)
    assert str(missing) in str(excinfo.value)
    wrong = tmp_path / "check.yaml"
    wrong.write_text("format: 1\n")
    with pytest.raises(ConfigError, match="suffix") as excinfo:
        read_check_config(wrong)
    assert str(wrong) in str(excinfo.value)
