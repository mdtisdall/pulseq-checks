import json
import math
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from pulseq_checks import registry
from pulseq_checks.profile import (
    FORMAT_VERSION,
    RASTER_OPTS,
    ProfileError,
    TargetProfile,
    read_profile,
)
from pulseq_checks.results import CheckRunError

PROFILES = Path(__file__).parent / "profiles"
BASE = {"format": 1, "name": "Test target"}
SAFE_PARAMS = {"name": "test model", "x": {"a1": 0.5}, "y": {"a1": 0.6}, "z": {"a1": 0.7}}


class SafeLikeModel:
    """A test model with the name and the keys of the SAFE model, and two fields less."""

    name = "pns.safe"
    version = 1

    def read(self, params):
        unknown = set(params) - {"name", "x", "y", "z"}
        if unknown:
            raise ValueError(f"unknown key {min(unknown)!r}")
        for axis in "xyz":
            if axis not in params:
                raise ValueError(f"missing key {axis!r}")
        return {"checked": True, **params}


class FakeReader:
    """A test `.asc` profile reader: returns the given sections and sources, and keeps the
    arguments of its calls."""

    def __init__(self, sections=None, sources=None):
        self.sections = sections if sections is not None else {}
        self.sources = sources if sources is not None else {}
        self.calls = []

    def __call__(self, path, *, gradient_mode=None):
        self.calls.append((path, gradient_mode))
        return self.sections, self.sources


ASC_SECTIONS = {
    "opts": {"max_grad": 60, "grad_unit": "mT/m", "max_slew": 150, "slew_unit": "T/m/s"},
    "models": {"pns": {"safe": SAFE_PARAMS}},
    "acoustic": {"resonances": [[590, 100]]},
}
ASC_SOURCES = {
    "opts.max_grad": "gpa.asc (fast)",
    "opts.grad_unit": "gpa.asc (fast)",
    "opts.max_slew": "gpa.asc (fast)",
    "opts.slew_unit": "gpa.asc (fast)",
    "models.pns.safe": "gpa.asc",
    "acoustic.resonances": "gpa.asc",
}


@pytest.fixture(autouse=True)
def installed_models(monkeypatch):
    """One installed model, "pns.safe", and no profile reader."""
    monkeypatch.setattr(registry, "models", lambda: {"pns.safe": SafeLikeModel()})
    monkeypatch.setattr(registry, "profile_reader", lambda name: None)


@pytest.fixture
def install_reader(monkeypatch):
    """A function that installs a `FakeReader` as the profile reader "siemens-asc"."""

    def install(reader):
        monkeypatch.setattr(
            registry, "profile_reader", lambda name: reader if name == "siemens-asc" else None
        )
        return reader

    return install


@pytest.fixture
def write_json(tmp_path):
    """A function that writes a dict as a JSON profile file, and returns its path."""

    def write(data, name="profile.json"):
        path = tmp_path / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    return write


def test_toml_and_json_give_equal_profiles_except_for_the_path():
    toml_profile = read_profile(PROFILES / "prisma.toml")
    json_profile = read_profile(PROFILES / "prisma.json")

    assert toml_profile.source_path != json_profile.source_path
    assert replace(toml_profile, source_path=None) == replace(json_profile, source_path=None)


def test_the_example_of_plan_section_4_3_reads_to_the_expected_values():
    profile = read_profile(PROFILES / "prisma.toml")

    assert profile.name == "Prisma AS82"
    assert profile.vendor == "siemens"
    assert profile.format_version == 1
    assert profile.opts == {
        "max_grad": 80,
        "grad_unit": "mT/m",
        "max_slew": 200,
        "slew_unit": "T/m/s",
        "rf_dead_time": 100e-6,
        "rf_ringdown_time": 30e-6,
        "adc_dead_time": 10e-6,
        "B0": 2.89,
    }
    assert profile.rasters == {
        "GradientRasterTime": 10e-6,
        "RadiofrequencyRasterTime": 1e-6,
        "AdcRasterTime": 100e-9,
        "BlockDurationRaster": 10e-6,
    }
    assert profile.raster_rule == "equal"
    assert profile.models == {"pns.safe": {"checked": True, **SAFE_PARAMS}}
    assert profile.acoustic_resonances == ((590.0, 100.0), (1140.0, 220.0))
    assert profile.unused_sections == ()
    assert profile.hardware_limits is not None
    assert profile.hardware_limits.label == "Prisma AS82"


@pytest.mark.parametrize("name", ["prisma", "minimal", "hz_units", "unused"])
def test_an_example_file_converted_to_json_reads_to_an_equal_profile(tmp_path, name):
    with open(PROFILES / f"{name}.toml", "rb") as f:
        data = tomllib.load(f)
    json_path = tmp_path / f"{name}.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    from_toml = read_profile(PROFILES / f"{name}.toml")
    from_json = read_profile(json_path)

    assert replace(from_toml, source_path=None) == replace(from_json, source_path=None)


def test_the_path_can_be_a_string_and_source_path_is_resolved(monkeypatch):
    monkeypatch.chdir(PROFILES)

    profile = read_profile("prisma.toml")

    assert profile.source_path == (PROFILES / "prisma.toml").resolve()
    assert profile.source_path.is_absolute()


@pytest.mark.parametrize("name", ["profile.yaml", "profile.txt", "profile"])
def test_another_suffix_is_a_profile_error_that_names_the_file(tmp_path, name):
    path = tmp_path / name
    path.write_text('format = 1\nname = "x"\n', encoding="utf-8")

    with pytest.raises(ProfileError, match=name):
        read_profile(path)


def test_a_profile_error_is_an_error_of_the_run():
    assert issubclass(ProfileError, CheckRunError)


def test_a_missing_file_is_a_profile_error_that_names_the_file(tmp_path):
    with pytest.raises(ProfileError, match="nothing.toml"):
        read_profile(tmp_path / "nothing.toml")


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("bad.toml", "format = 1\nname = \n"),
        ("bad.json", '{"format": 1, "name": '),
        ("list.json", "[1, 2]"),
        ("binary.toml", None),
    ],
)
def test_a_file_that_does_not_parse_is_a_profile_error_that_names_the_file(tmp_path, name, text):
    path = tmp_path / name
    if text is None:
        path.write_bytes(b"\xff\xfe\x00")
    else:
        path.write_text(text, encoding="utf-8")

    with pytest.raises(ProfileError, match=name):
        read_profile(path)


def test_the_format_is_necessary(write_json):
    path = write_json({"name": "x"}, "no_format.json")

    with pytest.raises(ProfileError, match="no_format.json.*format"):
        read_profile(path)


@pytest.mark.parametrize("value", ["1", 1.0, True, None, [1]])
def test_the_format_must_be_an_integer(write_json, value):
    path = write_json({"format": value, "name": "x"})

    with pytest.raises(ProfileError, match="format"):
        read_profile(path)


@pytest.mark.parametrize("value", [0, -1])
def test_a_format_below_1_is_an_error(write_json, value):
    path = write_json({"format": value, "name": "x"})

    with pytest.raises(ProfileError, match="format"):
        read_profile(path)


def test_a_newer_format_is_an_error_that_names_both_versions(write_json):
    newer = FORMAT_VERSION + 1
    path = write_json({"format": newer, "name": "x"})

    with pytest.raises(ProfileError, match=rf"format {newer}.*format {FORMAT_VERSION}"):
        read_profile(path)


@pytest.mark.parametrize("value", [None, "", 3, ["x"]])
def test_the_name_is_necessary_and_a_non_empty_string(write_json, value):
    data = {"format": 1} if value is None else {"format": 1, "name": value}

    with pytest.raises(ProfileError, match='"name"'):
        read_profile(write_json(data))


@pytest.mark.parametrize(
    ("key", "value"),
    [("vendor", 3), ("asc", 3), ("asc", ""), ("asc_gradient_mode", 3)],
)
def test_the_optional_top_level_keys_must_be_strings(write_json, key, value):
    data = {**BASE, "asc": "x.asc", key: value}

    with pytest.raises(ProfileError, match=key):
        read_profile(write_json(data))


@pytest.mark.parametrize("value", [3, "text", [1, 2], [{"a": 1}], True])
def test_an_unknown_top_level_key_with_a_value_that_is_not_a_table_is_an_error(write_json, value):
    path = write_json({**BASE, "colour": value})

    with pytest.raises(ProfileError, match="colour.*top level"):
        read_profile(path)


def test_an_unknown_top_level_table_is_kept_as_an_unused_section(write_json):
    path = write_json({**BASE, "notes": {"author": "x"}, "tool": {"a": {"b": 1}}})

    profile = read_profile(path)

    assert profile.unused_sections == ("notes", "tool")
    assert profile.opts is None


def test_an_unused_section_does_not_add_a_value_or_a_source(write_json):
    path = write_json({**BASE, "notes": {"opts": {"max_grad": 1}}})

    profile = read_profile(path)

    assert profile.sources == {}
    assert not profile.has_value("opts.max_grad")


@pytest.mark.parametrize("section", ["opts", "rasters", "models", "acoustic"])
def test_a_known_section_that_is_not_a_table_is_an_error(write_json, section):
    path = write_json({**BASE, section: [1, 2]})

    with pytest.raises(ProfileError, match=rf"\[{section}\]"):
        read_profile(path)


@pytest.mark.parametrize(
    ("section", "data", "key"),
    [
        ("opts", {"max_slwe": 200}, "max_slwe"),
        ("opts", {"self": 1}, "self"),
        ("rasters", {"GradRasterTime": 1e-5}, "GradRasterTime"),
        ("acoustic", {"resonance": [[1, 2]]}, "resonance"),
    ],
)
def test_an_unknown_key_in_a_known_section_is_an_error_that_names_the_key_and_the_section(
    write_json, section, data, key
):
    path = write_json({**BASE, section: data})

    with pytest.raises(ProfileError, match=rf"{key}.*\[{section}\]"):
        read_profile(path)


def test_the_keys_of_opts_are_the_keywords_of_pp_opts(write_json):
    opts = {
        "adc_dead_time": 1e-5,
        "gamma": 42.576e6,
        "grad_unit": "mT/m",
        "max_grad": 40,
        "max_slew": 150,
        "rf_dead_time": 1e-4,
        "rf_ringdown_time": 3e-5,
        "adc_samples_limit": 8192,
        "adc_samples_divisor": 4,
        "slew_unit": "T/m/s",
        "B0": 3.0,
    }

    profile = read_profile(write_json({**BASE, "opts": opts}))

    assert profile.opts == opts
    assert all(profile.has_value(f"opts.{key}") for key in opts)


@pytest.mark.parametrize("keyword", list(RASTER_OPTS.values()))
def test_a_raster_keyword_in_opts_is_an_error_that_points_to_the_rasters(write_json, keyword):
    path = write_json({**BASE, "opts": {keyword: 1e-5}})

    with pytest.raises(ProfileError, match=rf"{keyword}.*\[rasters\].*reserved"):
        read_profile(path)


def test_each_raster_name_is_read_and_given_to_its_opts_keyword(write_json):
    rasters = {
        "GradientRasterTime": 10e-6,
        "RadiofrequencyRasterTime": 2e-6,
        "AdcRasterTime": 200e-9,
        "BlockDurationRaster": 20e-6,
    }

    profile = read_profile(write_json({**BASE, "rasters": rasters}))
    opts = profile.make_opts()

    assert profile.rasters == rasters
    assert opts.grad_raster_time == 10e-6
    assert opts.rf_raster_time == 2e-6
    assert opts.adc_raster_time == 200e-9
    assert opts.block_duration_raster == 20e-6


@pytest.mark.parametrize("rule", ["equal", "multiple"])
def test_the_raster_rule_is_read(write_json, rule):
    profile = read_profile(write_json({**BASE, "rasters": {"rule": rule}}))

    assert profile.raster_rule == rule
    assert profile.rasters is None
    assert profile.sources == {"rasters.rule": "profile"}


@pytest.mark.parametrize("rule", ["exact", "", 1, None])
def test_another_raster_rule_is_an_error(write_json, rule):
    path = write_json({**BASE, "rasters": {"rule": rule}})

    with pytest.raises(ProfileError, match="rasters.rule"):
        read_profile(path)


@pytest.mark.parametrize("value", [0, -1e-5, "1e-5", True, None, [1e-5], float("nan")])
def test_a_raster_must_be_a_positive_number(write_json, value):
    path = write_json({**BASE, "rasters": {"GradientRasterTime": value}})

    with pytest.raises(ProfileError, match="rasters.GradientRasterTime"):
        read_profile(path)


def test_a_raster_of_the_toml_file_can_be_an_integer(tmp_path):
    path = tmp_path / "profile.toml"
    path.write_text('format = 1\nname = "x"\n[rasters]\nGradientRasterTime = 1\n')

    assert read_profile(path).rasters == {"GradientRasterTime": 1}


def test_the_acoustic_resonances_are_a_tuple_of_float_pairs(write_json):
    path = write_json({**BASE, "acoustic": {"resonances": [[590, 100], [1140.5, 220]]}})

    profile = read_profile(path)

    assert profile.acoustic_resonances == ((590.0, 100.0), (1140.5, 220.0))
    assert all(isinstance(x, float) for pair in profile.acoustic_resonances for x in pair)
    assert profile.sources == {"acoustic.resonances": "profile"}


@pytest.mark.parametrize(
    "resonances",
    [590, [590, 100], [[590]], [[590, 100, 1]], [["a", 100]], [[True, 100]], [{"f": 1}], "x"],
)
def test_malformed_acoustic_resonances_are_an_error(write_json, resonances):
    path = write_json({**BASE, "acoustic": {"resonances": resonances}})

    with pytest.raises(ProfileError, match="acoustic.resonances"):
        read_profile(path)


def test_an_empty_acoustic_resonances_list_is_an_empty_tuple(write_json):
    profile = read_profile(write_json({**BASE, "acoustic": {"resonances": []}}))

    assert profile.acoustic_resonances == ()


def test_a_null_value_in_opts_is_an_error_because_pp_opts_would_use_its_default(write_json):
    path = write_json({**BASE, "opts": {"max_grad": None}})

    with pytest.raises(ProfileError, match=r"profile.json.*opts\.max_grad is null"):
        read_profile(path)


def test_a_bad_value_for_pp_opts_is_a_profile_error_that_names_the_file(write_json):
    path = write_json({**BASE, "opts": {"max_grad": 40, "grad_unit": "furlong"}})

    with pytest.raises(ProfileError, match="profile.json.*furlong"):
        read_profile(path)


@pytest.mark.parametrize("value", ["forty", [40]])
def test_a_limit_that_is_not_a_number_is_a_profile_error(write_json, value):
    path = write_json({**BASE, "opts": {"max_grad": value, "max_slew": 150}})

    with pytest.raises(ProfileError, match="profile.json"):
        read_profile(path)


def test_the_model_section_is_read_by_its_installed_model_and_stored_by_name(write_json):
    path = write_json({**BASE, "models": {"pns": {"safe": SAFE_PARAMS}}})

    profile = read_profile(path)

    assert profile.models == {"pns.safe": {"checked": True, **SAFE_PARAMS}}
    assert profile.sources == {"models.pns.safe": "profile"}
    assert profile.has_value("models.pns.safe")
    assert profile.unused_sections == ()


def test_a_profile_without_a_model_section_has_no_models(write_json):
    profile = read_profile(write_json(BASE))

    assert profile.models == {}
    assert not profile.has_value("models.pns.safe")


def test_a_model_that_is_not_installed_makes_its_section_unused(write_json, monkeypatch):
    monkeypatch.setattr(registry, "models", dict)
    path = write_json({**BASE, "models": {"pns": {"safe": SAFE_PARAMS}}})

    profile = read_profile(path)

    assert profile.models == {}
    assert profile.unused_sections == ("models.pns",)


def test_a_model_error_is_a_profile_error_that_names_the_section(write_json):
    path = write_json({**BASE, "models": {"pns": {"safe": {"x": {}, "y": {}, "w": 1}}}})

    with pytest.raises(ProfileError, match=r"profile.json.*models\.pns\.safe.*'w'"):
        read_profile(path)


def test_a_model_section_that_is_not_a_table_is_a_profile_error(write_json):
    path = write_json({**BASE, "models": {"pns": {"safe": 3}}})

    with pytest.raises(ProfileError, match=r"models\.pns\.safe"):
        read_profile(path)


@pytest.mark.parametrize("value", [3, "x", [{"a": 1}]])
def test_a_value_directly_under_models_that_is_not_a_table_is_an_error(write_json, value):
    path = write_json({**BASE, "models": {"pns": value}})

    with pytest.raises(ProfileError, match=r"models\.pns"):
        read_profile(path)


def test_the_tables_of_models_with_no_installed_model_are_unused_sections():
    profile = read_profile(PROFILES / "unused.toml")

    assert profile.unused_sections == ("notes", "models.pns.other", "models.ge")
    assert list(profile.models) == ["pns.safe"]
    assert profile.sources == {"models.pns.safe": "profile"}


def test_the_highest_table_without_an_installed_model_is_the_unused_section(write_json):
    models = {"ge": {"pns": {"params": {"a": 1}}}, "philips": {"x": 1}}
    path = write_json({**BASE, "models": models})

    profile = read_profile(path)

    assert profile.unused_sections == ("models.ge", "models.philips")


@pytest.mark.parametrize(
    "data",
    [
        {"opts": {"max_grad": 80, "grad_unit": "mT/m", "max_slew": 200, "slew_unit": "T/m/s"}},
        {"opts": {"max_grad": 8e4 * 42.576, "max_slew": 200 * 42.576e6}},
        {
            "opts": {
                "max_grad": 80 * 42.576e3 * 2 * math.pi / 1e6,
                "max_slew": 200,
                "grad_unit": "rad/ms/mm",
                "slew_unit": "T/m/s",
            }
        },
    ],
    ids=["mT/m and T/m/s", "Hz/m and Hz/m/s", "rad/ms/mm and T/m/s"],
)
def test_the_hardware_limits_are_in_mt_per_m_and_t_per_m_per_s(write_json, data):
    profile = read_profile(write_json({**BASE, **data}))

    assert profile.hardware_limits is not None
    assert profile.hardware_limits.max_grad_mt_per_m == pytest.approx(80, rel=1e-3)
    assert profile.hardware_limits.max_slew_t_per_m_per_s == pytest.approx(200, rel=1e-3)
    assert profile.hardware_limits.label == "Test target"


def test_the_hardware_limits_of_a_profile_in_hz_units_come_from_the_example_file():
    profile = read_profile(PROFILES / "hz_units.toml")

    assert profile.hardware_limits is not None
    assert profile.hardware_limits.max_grad_mt_per_m == pytest.approx(100)
    assert profile.hardware_limits.max_slew_t_per_m_per_s == pytest.approx(100)
    assert profile.hardware_limits.label == "Hz units"


def test_the_hardware_limits_use_the_gamma_of_the_opts_object(write_json):
    data = {"max_grad": 80, "grad_unit": "mT/m", "max_slew": 200, "slew_unit": "T/m/s"}

    default = read_profile(write_json({**BASE, "opts": data}))
    other = read_profile(write_json({**BASE, "opts": {**data, "gamma": 10e6}}))

    # pp.Opts converts the limits to Hz/m with its gamma, and the profile converts them back.
    assert other.hardware_limits.max_grad_mt_per_m == pytest.approx(80)
    assert other.hardware_limits.max_slew_t_per_m_per_s == pytest.approx(200)
    assert other.make_opts().max_grad != default.make_opts().max_grad


@pytest.mark.parametrize("given", ["max_grad", "max_slew"])
def test_hardware_limits_need_both_max_grad_and_max_slew(write_json, given):
    path = write_json({**BASE, "opts": {given: 10, "B0": 3.0}})

    assert read_profile(path).hardware_limits is None


def test_a_profile_with_the_name_only_has_no_default_value():
    profile = read_profile(PROFILES / "minimal.toml")

    assert profile == TargetProfile(
        name="Minimal",
        vendor=None,
        format_version=1,
        source_path=(PROFILES / "minimal.toml").resolve(),
        opts=None,
        hardware_limits=None,
        rasters=None,
        raster_rule=None,
        models={},
        acoustic_resonances=None,
        sources={},
        unused_sections=(),
    )


@pytest.mark.parametrize("data", [{"opts": {}}, {"rasters": {}}, {"acoustic": {}}, {"models": {}}])
def test_an_empty_known_section_gives_no_value(write_json, data):
    profile = read_profile(write_json({**BASE, **data}))

    assert profile.opts is None
    assert profile.rasters is None
    assert profile.acoustic_resonances is None
    assert profile.sources == {}


def test_the_sources_name_each_value_that_the_profile_gives():
    profile = read_profile(PROFILES / "prisma.toml")

    expected = (
        [f"opts.{key}" for key in profile.opts]
        + [f"rasters.{name}" for name in RASTER_OPTS]
        + ["rasters.rule", "models.pns.safe", "acoustic.resonances"]
    )
    assert sorted(profile.sources) == sorted(expected)
    assert set(profile.sources.values()) == {"profile"}


def test_has_value_is_true_for_a_path_in_the_sources_only(write_json):
    profile = read_profile(write_json({**BASE, "opts": {"B0": 3.0}}))

    assert profile.has_value("opts.B0")
    assert not profile.has_value("opts.max_grad")
    assert not profile.has_value("rasters.rule")


def test_make_opts_builds_pp_opts_from_the_opts_and_the_rasters():
    profile = read_profile(PROFILES / "prisma.toml")

    opts = profile.make_opts()

    assert opts.max_grad == pytest.approx(80 * 42.576e3)
    assert opts.max_slew == pytest.approx(200 * 42.576e6)
    assert opts.rf_dead_time == 100e-6
    assert opts.B0 == 2.89
    assert opts.grad_raster_time == 10e-6
    assert opts.adc_raster_time == 100e-9
    assert opts.block_duration_raster == 10e-6


def test_the_asc_reader_is_called_with_the_path_relative_to_the_profile_and_the_mode(
    install_reader,
):
    reader = install_reader(FakeReader())

    read_profile(PROFILES / "with_asc.toml")

    assert reader.calls == [((PROFILES / "gpa" / "test.asc").resolve(), "fast")]


def test_the_asc_reader_gets_no_mode_when_the_profile_selects_none(install_reader, write_json):
    reader = install_reader(FakeReader())

    read_profile(write_json({**BASE, "asc": "x.asc"}))

    assert [mode for _, mode in reader.calls] == [None]


def test_the_sections_of_the_asc_reader_are_merged_with_the_values_of_the_profile(
    install_reader, write_json
):
    install_reader(FakeReader(ASC_SECTIONS, ASC_SOURCES))
    data = {
        **BASE,
        "asc": "gpa.asc",
        "asc_gradient_mode": "fast",
        "opts": {"B0": 3.0},
        "rasters": {"GradientRasterTime": 10e-6, "rule": "equal"},
    }

    profile = read_profile(write_json(data))

    assert profile.opts == {**ASC_SECTIONS["opts"], "B0": 3.0}
    assert profile.rasters == {"GradientRasterTime": 10e-6}
    assert profile.raster_rule == "equal"
    assert profile.acoustic_resonances == ((590.0, 100.0),)
    assert profile.models == {"pns.safe": {"checked": True, **SAFE_PARAMS}}


def test_the_sources_label_each_value_with_the_profile_or_the_label_of_the_reader(
    install_reader, write_json
):
    install_reader(FakeReader(ASC_SECTIONS, ASC_SOURCES))
    data = {**BASE, "asc": "gpa.asc", "opts": {"B0": 3.0}, "rasters": {"rule": "equal"}}

    profile = read_profile(write_json(data))

    assert dict(profile.sources) == {
        "opts.B0": "profile",
        "rasters.rule": "profile",
        **ASC_SOURCES,
    }
    assert profile.has_value("opts.max_grad")


def test_the_hardware_limits_can_come_from_the_values_of_the_asc_reader(install_reader, write_json):
    install_reader(FakeReader(ASC_SECTIONS, ASC_SOURCES))

    profile = read_profile(write_json({**BASE, "asc": "gpa.asc", "asc_gradient_mode": "fast"}))

    assert profile.hardware_limits is not None
    assert profile.hardware_limits.max_grad_mt_per_m == pytest.approx(60)
    assert profile.hardware_limits.max_slew_t_per_m_per_s == pytest.approx(150)
    assert profile.hardware_limits.label == "Test target"


def test_a_reader_without_opts_leaves_the_opts_to_the_profile(install_reader, write_json):
    sections = {"models": ASC_SECTIONS["models"]}
    sources = {"models.pns.safe": "gpa.asc"}
    install_reader(FakeReader(sections, sources))

    profile = read_profile(write_json({**BASE, "asc": "gpa.asc"}))

    assert profile.opts is None
    assert profile.hardware_limits is None
    assert profile.models == {"pns.safe": {"checked": True, **SAFE_PARAMS}}


@pytest.mark.parametrize(
    ("profile_data", "path"),
    [
        ({"opts": {"max_grad": 80}}, "opts.max_grad"),
        ({"opts": {"grad_unit": "mT/m"}}, "opts.grad_unit"),
        ({"models": {"pns": {"safe": SAFE_PARAMS}}}, "models.pns.safe"),
        ({"acoustic": {"resonances": [[1, 2]]}}, "acoustic.resonances"),
    ],
)
def test_a_value_from_the_profile_and_the_asc_reader_is_an_error_that_names_both_sources(
    install_reader, write_json, profile_data, path
):
    install_reader(FakeReader(ASC_SECTIONS, ASC_SOURCES))
    data = {**BASE, "asc": "gpa.asc", "asc_gradient_mode": "fast", **profile_data}

    with pytest.raises(ProfileError) as info:
        read_profile(write_json(data))

    message = str(info.value)
    assert "profile.json" in message
    assert path in message
    assert "'profile'" in message
    assert f"'{ASC_SOURCES[path]}'" in message


def test_a_profile_that_gives_max_grad_and_selects_a_mode_is_an_error(install_reader, write_json):
    install_reader(FakeReader(ASC_SECTIONS, ASC_SOURCES))
    data = {
        **BASE,
        "asc": "gpa.asc",
        "asc_gradient_mode": "fast",
        "opts": {"max_grad": 40, "grad_unit": "mT/m"},
    }

    with pytest.raises(ProfileError, match=r"opts\.max_grad.*'profile'.*gpa\.asc \(fast\)"):
        read_profile(write_json(data))


def test_a_raster_from_the_profile_and_one_from_the_reader_is_an_error(install_reader, write_json):
    sections = {"rasters": {"GradientRasterTime": 10e-6}}
    install_reader(FakeReader(sections, {"rasters.GradientRasterTime": "gpa.asc"}))
    data = {**BASE, "asc": "gpa.asc", "rasters": {"GradientRasterTime": 10e-6}}

    with pytest.raises(ProfileError, match=r"rasters\.GradientRasterTime"):
        read_profile(write_json(data))


def test_the_asc_model_sections_go_through_the_model_read(install_reader, write_json):
    bad = {"models": {"pns": {"safe": {"x": {}, "y": {}, "z": {}, "w": 1}}}}
    install_reader(FakeReader(bad, {"models.pns.safe": "gpa.asc"}))

    with pytest.raises(ProfileError, match=r"profile.json.*models\.pns\.safe.*'w'"):
        read_profile(write_json({**BASE, "asc": "gpa.asc"}))


def test_an_asc_model_that_is_not_installed_is_an_unused_section(
    install_reader, write_json, monkeypatch
):
    monkeypatch.setattr(registry, "models", dict)
    install_reader(FakeReader(ASC_SECTIONS, ASC_SOURCES))

    profile = read_profile(write_json({**BASE, "asc": "gpa.asc"}))

    assert profile.models == {}
    assert profile.unused_sections == ("models.pns",)


def test_a_gradient_mode_without_asc_is_an_error(install_reader, write_json):
    reader = install_reader(FakeReader())

    with pytest.raises(ProfileError, match="profile.json.*asc_gradient_mode"):
        read_profile(write_json({**BASE, "asc_gradient_mode": "fast"}))

    assert reader.calls == []


def test_asc_without_an_installed_reader_is_an_error(write_json):
    with pytest.raises(ProfileError, match=r"profile.json.*siemens-asc"):
        read_profile(write_json({**BASE, "asc": "gpa.asc"}))


@pytest.mark.parametrize(
    "error", [ValueError("no mode 'slow'"), FileNotFoundError("no such file"), OSError("denied")]
)
def test_a_reader_error_is_a_profile_error_that_names_the_profile_and_the_asc_file(
    install_reader, write_json, error
):
    def failing(path, *, gradient_mode=None):
        raise error

    install_reader(failing)

    with pytest.raises(ProfileError, match=r"profile.json.*gpa\.asc.*" + str(error.args[0])):
        read_profile(write_json({**BASE, "asc": "gpa.asc"}))


@pytest.mark.parametrize(
    ("sections", "sources", "message"),
    [
        ({"opts": {"max_slwe": 1}}, {"opts.max_slwe": "gpa.asc"}, r"max_slwe.*\[opts\]"),
        ({"opts": {"max_grad": 1}}, {}, r"opts\.max_grad.*source"),
        ({"vendor_data": {"a": 1}}, {}, "vendor_data"),
        ({"acoustic": {"resonances": 5}}, {"acoustic.resonances": "gpa.asc"}, "resonances"),
    ],
)
def test_a_value_of_the_asc_reader_that_is_not_valid_is_a_profile_error(
    install_reader, write_json, sections, sources, message
):
    install_reader(FakeReader(sections, sources))

    with pytest.raises(ProfileError, match=r"profile.json.*gpa\.asc.*" + message):
        read_profile(write_json({**BASE, "asc": "gpa.asc"}))
