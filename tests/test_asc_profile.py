import importlib.metadata

import pytest
from pypulseq.utils.safe_pns_prediction import safe_example_hw

from pulseq_checks import asc_profile
from pulseq_checks.profile import ProfileError, read_profile

FIELDS = ("tau1", "tau2", "tau3", "a1", "a2", "a3", "stim_limit", "stim_thresh", "g_scale")
LAYOUT_1 = [
    "aflGCAcousticResonanceFrequency[0] = 1100.5",
    "aflGCAcousticResonanceFrequency[1] = 0",
    "aflGCAcousticResonanceFrequency[2] = 2200.0",
    "aflGCAcousticResonanceBandwidth[0] = 210.5",
    "aflGCAcousticResonanceBandwidth[1] = 99.0",
    "aflGCAcousticResonanceBandwidth[2] = 300.0",
]
_GC = "asGPAParameters[0].sGCParameters."
LAYOUT_2 = [line.replace("aflGC", _GC + "afl") for line in LAYOUT_1]
PAIRS = [[1100.5, 210.5], [2200.0, 300.0]]
# Synthetic GPA limits for each Siemens mode name: (amplitude in mT/m, rise time in µs per
# mT/m). The values of Normal are integers, as a line of a file can have them.
GPA = {
    "Absolute": (80.0, 5.0),
    "Normal": (40, 20),
    "Fast": (50.0, 10.0),
    "UltraFast": (45.5, 12.0),
    "Whisper": (22.0, 25.0),
    "Boost": (60.0, 8.0),
}
MODES = {
    "absolute": "Absolute",
    "normal": "Normal",
    "fast": "Fast",
    "ultrafast": "UltraFast",
    "whisper": "Whisper",
    "boost": "Boost",
}


def expected_safe(name):
    hw = safe_example_hw()
    safe = {"name": name}
    for axis in "xyz":
        safe[axis] = {field: float(getattr(getattr(hw, axis), field)) for field in FIELDS}
    return safe


def append_lines(path, lines, split=False):
    """Append `lines` to the `.asc` file; in the split layout, before the end of its
    `ASCCONV` block."""
    text = path.read_bytes().decode()
    if split:
        end = "### ASCCONV END ###"
        text = text.replace(end, "\r\n".join(lines) + "\r\n" + end)
    else:
        text += "\n".join(lines) + "\n"
    path.write_bytes(text.encode())


def drop_lines(path, *substrings):
    """Remove the lines of the `.asc` file that have one of `substrings`."""
    lines = path.read_bytes().decode().splitlines(keepends=True)
    kept = [line for line in lines if not any(text in line for text in substrings)]
    assert len(kept) < len(lines)
    path.write_bytes("".join(kept).encode())


@pytest.mark.parametrize("split", [False, True])
def test_read_asc_profile_gives_the_safe_parameters(write_gradient_asc, split):
    path = write_gradient_asc(name="MP_GPA_TEST", split=split)
    sections, sources = asc_profile.read_asc_profile(path)
    assert sections == {"models": {"pns": {"safe": expected_safe("MP_GPA_TEST")}}}
    assert sources == {"models.pns.safe": path.name}


def test_read_asc_profile_with_a_missing_include_file_is_an_os_error(write_gradient_asc):
    path = write_gradient_asc(split=True)
    path.with_name(f"{path.stem}_GSWD_SAFETY.asc").unlink()
    with pytest.raises(OSError):
        asc_profile.read_asc_profile(path)


@pytest.mark.parametrize(
    ("layout", "split"),
    [(LAYOUT_1, False), (LAYOUT_2, False), (LAYOUT_2, True)],
    ids=["aflGC-plain", "sGCParameters-plain", "sGCParameters-split"],
)
def test_read_asc_profile_gives_the_acoustic_resonances(write_gradient_asc, layout, split):
    path = write_gradient_asc(split=split)
    append_lines(path, layout, split=split)
    sections, sources = asc_profile.read_asc_profile(path)
    assert sections["acoustic"] == {"resonances": PAIRS}
    assert all(isinstance(v, float) for pair in sections["acoustic"]["resonances"] for v in pair)
    assert sources["acoustic.resonances"] == path.name
    assert sections["models"]["pns"]["safe"] == expected_safe("MP_GPA_TEST")


def test_read_asc_profile_gives_only_the_sections_that_the_file_has(write_gradient_asc, tmp_path):
    sections, sources = asc_profile.read_asc_profile(write_gradient_asc())
    assert "acoustic" not in sections
    assert "acoustic.resonances" not in sources

    bare = tmp_path / "bare.asc"
    bare.write_text('asCOMP.tName = "BARE"\n')
    assert asc_profile.read_asc_profile(bare) == ({}, {})


def test_read_asc_profile_is_a_registered_profile_reader():
    entry_points = importlib.metadata.entry_points(group="pulseq_checks.profile_readers")
    assert entry_points["siemens-asc"].load() is asc_profile.read_asc_profile


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize(("mode", "siemens"), MODES.items())
def test_read_asc_profile_gives_the_gpa_limits_of_the_mode(
    write_gradient_asc, mode, siemens, split
):
    path = write_gradient_asc(split=split, gpa=GPA)
    amplitude, rise_time = GPA[siemens]
    sections, sources = asc_profile.read_asc_profile(path, gradient_mode=mode)
    assert sections["opts"] == {
        "max_grad": amplitude,
        "grad_unit": "mT/m",
        "max_slew": 1000 / rise_time,
        "slew_unit": "T/m/s",
    }
    assert isinstance(sections["opts"]["max_grad"], float)
    assert isinstance(sections["opts"]["max_slew"], float)
    label = f"{path.name} ({mode})"
    assert {key: sources[f"opts.{key}"] for key in sections["opts"]} == dict.fromkeys(
        sections["opts"], label
    )
    assert sources["models.pns.safe"] == path.name
    assert sections["models"]["pns"]["safe"] == expected_safe("MP_GPA_TEST")


@pytest.mark.parametrize("split", [False, True])
def test_read_asc_profile_ignores_the_default_twins_of_the_gpa_fields(write_gradient_asc, split):
    path = write_gradient_asc(split=split, gpa={"Fast": (50.0, 10.0)})
    append_lines(
        path,
        [
            "asGPAParameters[0].flDefGradMaxAmplFast = 99.0",
            "asGPAParameters[0].flDefGradMinRiseTimeFast = 77.0",
        ],
        split=split,
    )
    sections, _ = asc_profile.read_asc_profile(path, gradient_mode="fast")
    assert sections["opts"]["max_grad"] == 50.0
    assert sections["opts"]["max_slew"] == 1000 / 10.0


def test_read_asc_profile_without_a_gradient_mode_gives_no_opts(write_gradient_asc):
    path = write_gradient_asc(gpa=GPA)
    sections, sources = asc_profile.read_asc_profile(path)
    assert "opts" not in sections
    assert not [key for key in sources if key.startswith("opts.")]


@pytest.mark.parametrize("mode", ["nominal", "Fast", "UltraFast", "turbo", ""])
def test_read_asc_profile_with_an_unknown_gradient_mode_is_a_value_error(write_gradient_asc, mode):
    path = write_gradient_asc(gpa={**GPA, "Nominal": (70.0, 1.0)})
    with pytest.raises(ValueError, match="unknown gradient mode") as error:
        asc_profile.read_asc_profile(path, gradient_mode=mode)
    assert all(known in str(error.value) for known in MODES)


@pytest.mark.parametrize(
    ("lines", "missing"),
    [
        ([], "flGradMaxAmplBoost"),
        (["asGPAParameters[0].flGradMinRiseTimeBoost = 8.0"], "flGradMaxAmplBoost"),
        (["asGPAParameters[0].flGradMaxAmplBoost = 60.0"], "flGradMinRiseTimeBoost"),
    ],
    ids=["no-fields", "no-amplitude", "no-rise-time"],
)
def test_read_asc_profile_with_a_mode_that_the_file_does_not_have_is_a_value_error(
    write_gradient_asc, lines, missing
):
    path = write_gradient_asc(gpa={"Fast": (50.0, 10.0)})
    append_lines(path, lines)
    with pytest.raises(ValueError, match=missing) as error:
        asc_profile.read_asc_profile(path, gradient_mode="boost")
    assert path.name in str(error.value)
    assert "boost" in str(error.value)


@pytest.mark.parametrize(
    ("amplitude", "rise_time"),
    [
        ("40.0", "0.0"),
        ("40.0", "0"),
        ("40.0", "-5.0"),
        ("0.0", "10.0"),
        ("-40.0", "10.0"),
        ("1e999", "10.0"),
        ("40.0", "1e999"),
        ('"text"', "10.0"),
    ],
)
def test_read_asc_profile_with_an_invalid_gpa_value_is_a_value_error(
    write_gradient_asc, amplitude, rise_time
):
    path = write_gradient_asc()
    append_lines(
        path,
        [
            f"asGPAParameters[0].flGradMaxAmplFast = {amplitude}",
            f"asGPAParameters[0].flGradMinRiseTimeFast = {rise_time}",
        ],
    )
    with pytest.raises(ValueError, match="flGrad") as error:
        asc_profile.read_asc_profile(path, gradient_mode="fast")
    assert path.name in str(error.value)
    assert "fast" in str(error.value)


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("axes", ["X", "Y", "Z", "XYZ"])
def test_read_asc_profile_with_safe_parameters_but_no_scale_factor_is_a_value_error(
    write_gradient_asc, split, axes
):
    path = write_gradient_asc(split=split)
    drop_lines(path, *(f"flGScaleFactor{axis}" for axis in axes))
    with pytest.raises(ValueError, match=f"flGScaleFactor{axes[0]}") as error:
        asc_profile.read_asc_profile(path)
    assert path.name in str(error.value)


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("field", ["flGSWDStimulationLimitY", "flGSWDTauX[2]", "flGSWDAZ[0]"])
def test_read_asc_profile_with_some_safe_fields_but_not_all_is_a_value_error(
    write_gradient_asc, split, field
):
    path = write_gradient_asc(split=split)
    drop_lines(path.with_name(f"{path.stem}_GSWD_SAFETY.asc") if split else path, field)
    with pytest.raises(ValueError, match="incomplete SAFE") as error:
        asc_profile.read_asc_profile(path)
    assert path.name in str(error.value)


@pytest.mark.parametrize("layout", [LAYOUT_1, LAYOUT_2], ids=["aflGC", "sGCParameters"])
@pytest.mark.parametrize(
    "mutate",
    [
        lambda lines: [line for line in lines if "Frequency" in line],
        lambda lines: [line for line in lines if "Bandwidth" in line],
        lambda lines: [line for line in lines if "Bandwidth[2]" not in line],
        lambda lines: [line.replace("Bandwidth[2]", "Bandwidth[3]") for line in lines],
    ],
    ids=["no-bandwidths", "no-frequencies", "fewer-bandwidths", "other-indices"],
)
def test_read_asc_profile_with_mismatched_acoustic_resonances_is_a_value_error(
    write_gradient_asc, layout, mutate
):
    path = write_gradient_asc()
    append_lines(path, mutate(layout))
    with pytest.raises(ValueError, match="acoustic resonance") as error:
        asc_profile.read_asc_profile(path)
    assert path.name in str(error.value)


# ---- Through read_profile (plan section 4.3, rule 4, and section 4.9) ----


def write_profile(tmp_path, lines):
    """A profile file `profile.toml` in `tmp_path`, with `format` and `name` and `lines`."""
    path = tmp_path / "profile.toml"
    path.write_text("\n".join(["format = 1", 'name = "Test target"', *lines]) + "\n")
    return path


def test_read_profile_gives_the_gpa_limits_of_the_asc_file(write_gradient_asc, tmp_path):
    """A profile that names an `.asc` file and a mode gets the GPA limits of that mode from the
    installed reader `siemens-asc`, with the file name and the mode as the source."""
    asc = write_gradient_asc(gpa=GPA)
    profile = read_profile(
        write_profile(tmp_path, [f'asc = "{asc.name}"', 'asc_gradient_mode = "fast"'])
    )
    assert profile.hardware_limits.max_grad_mt_per_m == pytest.approx(50.0, rel=1e-12)
    assert profile.hardware_limits.max_slew_t_per_m_per_s == pytest.approx(100.0, rel=1e-12)
    for key in ("max_grad", "grad_unit", "max_slew", "slew_unit"):
        assert profile.sources[f"opts.{key}"] == f"{asc.name} (fast)"


def test_read_profile_with_max_grad_and_a_gradient_mode_is_an_error(write_gradient_asc, tmp_path):
    """A profile that gives `max_grad` and also selects a mode of its `.asc` file gives the
    value twice: a `ProfileError` that names the value and both sources."""
    asc = write_gradient_asc(gpa=GPA)
    path = write_profile(
        tmp_path,
        [f'asc = "{asc.name}"', 'asc_gradient_mode = "fast"', "[opts]", "max_grad = 80"],
    )
    with pytest.raises(ProfileError, match=r"opts\.max_grad .*'profile'.*\(fast\)"):
        read_profile(path)


def test_read_profile_with_a_gradient_mode_and_no_asc_is_an_error(tmp_path):
    """`asc_gradient_mode` without `asc` is a `ProfileError`."""
    with pytest.raises(ProfileError, match="asc_gradient_mode"):
        read_profile(write_profile(tmp_path, ['asc_gradient_mode = "fast"']))


def test_read_profile_with_an_unknown_gradient_mode_is_an_error(write_gradient_asc, tmp_path):
    """The `ValueError` of the reader for an unknown mode is a `ProfileError` that names the
    `.asc` file."""
    asc = write_gradient_asc(gpa=GPA)
    path = write_profile(tmp_path, [f'asc = "{asc.name}"', 'asc_gradient_mode = "nominal"'])
    with pytest.raises(ProfileError, match=asc.name):
        read_profile(path)
