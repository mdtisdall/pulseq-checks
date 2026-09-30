import importlib.metadata
import json
import re
from pathlib import Path

import pytest
from synthetic import spin_echo_sequence

from pulseq_checks import registry
from pulseq_checks.cli import main
from pulseq_checks.profile import read_profile
from pulseq_checks.results import ResultMatrix, State
from pulseq_checks.rules import CheckSpec
from pulseq_checks.run import run_checks

PROFILES = Path(__file__).parent / "profiles"


class Rule:
    """A test check rule that gives `state` for each target. The spec needs `inputs` (value
    paths) and has the cost class `cost`."""

    def __init__(self, check_id, state=State.PASS, *, cost="slow", inputs=(), detail=None):
        self.spec = CheckSpec(
            id=check_id,
            version=1,
            title=check_id,
            quantity="a test quantity",
            inputs=tuple(inputs),
            models=(),
            limit="a test limit",
            tolerance="none",
            pass_condition="always",
            cost=cost,
        )
        self.state = state
        self.detail = detail

    def run(self, ctx):
        reason = self.detail
        if self.state in (State.NOT_EVALUATED, State.ERROR):
            reason = reason or "a test reason"
        return ctx.result(self.spec, self.state, value=1.5, limit=2.0, unit="mT/m", reason=reason)


def install(monkeypatch, *rules):
    """Make `registry.check_rules` give `rules`, by ID."""
    monkeypatch.setattr(registry, "check_rules", lambda: {r.spec.id: r for r in rules})


def write_profile(folder, name="a", *, filename=None, extra=""):
    """A profile file in `folder` with only the format and the name, and `extra` TOML."""
    path = Path(folder) / (filename or f"{name}.toml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'format = 1\nname = "{name}"\n{extra}')
    return path


@pytest.fixture
def seq_file(tmp_path):
    path = tmp_path / "spin_echo.seq"
    spin_echo_sequence().write(str(path))
    return path


@pytest.fixture
def profile_a(tmp_path):
    return write_profile(tmp_path, "a")


def run_to_matrix(tmp_path, argv, capsys):
    """The status and the `ResultMatrix` of `main(argv)`, read from a `--json` file."""
    out = tmp_path / "out.json"
    status = main([*argv, "--json", str(out), "--quiet"])
    capsys.readouterr()
    return status, ResultMatrix.from_json(out.read_text())


def ids(matrix, target=None):
    return [r.check_id for r in matrix.results if target in (None, r.target)]


@pytest.mark.parametrize(
    ("states", "status"),
    [
        ((State.PASS, State.PASS), 0),
        ((State.PASS, State.FAIL), 2),
        ((State.PASS, State.ERROR), 1),
        ((State.FAIL, State.ERROR), 1),
    ],
)
def test_the_exit_status_follows_the_states_of_the_results(
    monkeypatch, seq_file, profile_a, states, status
):
    install(monkeypatch, *(Rule(f"t.{i}", state) for i, state in enumerate(states)))
    assert main([str(seq_file), "--target", str(profile_a), "--quiet"]) == status


def test_a_required_check_that_is_not_evaluated_gives_status_1(
    monkeypatch, tmp_path, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a", inputs=("opts.max_grad",)), Rule("t.b"))
    config = tmp_path / "check.toml"
    config.write_text(f'format = 1\ntargets = ["{profile_a.name}"]\nrequired = {{"t.a" = true}}\n')
    assert main([str(seq_file), "--config", str(config)]) == 1
    out = capsys.readouterr().out
    assert "exit status 1" in out


def test_a_check_that_is_not_required_and_not_evaluated_gives_status_0(
    monkeypatch, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a", inputs=("opts.max_grad",)), Rule("t.b"))
    status = main([str(seq_file), "--target", str(profile_a)])
    assert status == 0
    out = capsys.readouterr().out
    assert "not evaluated" in out
    assert "exit status 0" in out


def test_json_to_a_file_reads_back_as_the_matrix(
    monkeypatch, tmp_path, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a"), Rule("t.b", State.FAIL, detail="axis y"))
    out = tmp_path / "result.json"
    status = main([str(seq_file), "--target", str(profile_a), "--json", str(out)])
    assert status == 2
    expected = run_checks(str(seq_file), [read_profile(profile_a)])
    assert ResultMatrix.from_json(out.read_text()) == expected
    assert "exit status 2" in capsys.readouterr().out  # the summary is still on stdout


def test_json_to_stdout_is_only_the_json_and_the_summary_goes_to_stderr(
    monkeypatch, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a"), Rule("t.b", State.FAIL))
    status = main([str(seq_file), "--target", str(profile_a), "--json", "-"])
    assert status == 2
    captured = capsys.readouterr()
    matrix = ResultMatrix.from_json(captured.out)
    assert ids(matrix) == ["t.a", "t.b"]
    assert "exit status 2" in captured.err
    assert "t.b" in captured.err


def test_json_to_stdout_with_quiet_writes_nothing_to_stderr(
    monkeypatch, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a"))
    assert main([str(seq_file), "--target", str(profile_a), "--json", "-", "--quiet"]) == 0
    captured = capsys.readouterr()
    json.loads(captured.out)
    assert captured.err == ""


def test_json_to_a_path_that_cannot_be_written_gives_status_1(
    monkeypatch, tmp_path, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a"))
    out = tmp_path / "no_folder" / "result.json"
    status = main([str(seq_file), "--target", str(profile_a), "--json", str(out)])
    assert status == 1
    err = capsys.readouterr().err
    assert err.startswith("pulseq-check: error:")
    assert "result.json" in err


def test_quiet_writes_no_summary_but_keeps_the_status(monkeypatch, seq_file, profile_a, capsys):
    install(monkeypatch, Rule("t.a", State.FAIL))
    assert main([str(seq_file), "--target", str(profile_a), "--quiet"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_quiet_still_prints_an_error_of_the_run(seq_file, tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("format = 1\n")
    assert main([str(seq_file), "--target", str(bad), "--quiet"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("pulseq-check: error:")


def test_a_config_gives_the_targets_relative_to_its_file_select_required_and_fast_only(
    monkeypatch, tmp_path, seq_file, capsys
):
    install(
        monkeypatch,
        Rule("t.fast", cost="fast"),
        Rule("t.slow"),
        Rule("t.other", State.FAIL),
        Rule("t.req", State.PASS, inputs=("opts.max_grad",)),
    )
    folder = tmp_path / "configs"
    write_profile(folder / "profiles", "a")
    write_profile(folder / "profiles", "b")
    config = folder / "check.toml"
    config.write_text(
        'format = 1\ntargets = ["profiles/a.toml", "profiles/b.toml"]\n'
        'select = ["t.fast", "t.slow", "t.req"]\nfast_only = true\n'
        'required = {"t.req" = ["b"]}\n'
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    status, matrix = run_to_matrix(tmp_path, [str(seq_file), "--config", str(config)], capsys)
    # t.slow is removed by fast_only, t.other is not selected, and t.req is required for b
    # only (it is not evaluated, because the profiles have no opts.max_grad).
    assert [t.name for t in matrix.targets] == ["a", "b"]
    assert ids(matrix, "a") == ["t.fast", "t.req"]
    assert ids(matrix, "b") == ["t.fast", "t.req"]
    required = {(r.check_id, r.target) for r in matrix.results if r.required}
    assert required == {("t.req", "b")}
    assert status == 1


def test_a_config_without_select_or_fast_only_runs_every_check(
    monkeypatch, tmp_path, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a", cost="fast"), Rule("t.b"))
    config = tmp_path / "check.json"
    config.write_text(json.dumps({"format": 1, "targets": [profile_a.name]}))
    status, matrix = run_to_matrix(tmp_path, [str(seq_file), "--config", str(config)], capsys)
    assert status == 0
    assert ids(matrix) == ["t.a", "t.b"]


def test_check_selects_the_check_and_makes_it_required(
    monkeypatch, tmp_path, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a"), Rule("t.b"), Rule("t.c"))
    argv = [str(seq_file), "--target", str(profile_a), "--check", "t.c", "--check", "t.a"]
    status, matrix = run_to_matrix(tmp_path, argv, capsys)
    assert status == 0
    assert ids(matrix) == ["t.a", "t.c"]
    assert all(r.required for r in matrix.results)


def test_a_check_that_is_not_evaluated_gives_status_1(monkeypatch, seq_file, profile_a):
    install(monkeypatch, Rule("t.a", inputs=("opts.max_grad",)), Rule("t.b"))
    assert main([str(seq_file), "--target", str(profile_a), "--quiet"]) == 0
    assert main([str(seq_file), "--target", str(profile_a), "--check", "t.a", "--quiet"]) == 1


def test_check_is_required_for_each_target(monkeypatch, tmp_path, seq_file, profile_a, capsys):
    install(monkeypatch, Rule("t.a"))
    profile_b = write_profile(tmp_path, "b")
    argv = [str(seq_file), "--target", str(profile_a), "--target", str(profile_b)]
    _, matrix = run_to_matrix(tmp_path, [*argv, "--check", "t.a"], capsys)
    assert [(r.target, r.required) for r in matrix.results] == [("a", True), ("b", True)]


def test_check_with_a_config_is_added_to_select_and_required(
    monkeypatch, tmp_path, seq_file, capsys
):
    install(monkeypatch, Rule("t.a"), Rule("t.b"), Rule("t.c"), Rule("t.d"))
    write_profile(tmp_path, "a")
    write_profile(tmp_path, "b")
    config = tmp_path / "check.toml"
    config.write_text(
        'format = 1\ntargets = ["a.toml", "b.toml"]\nselect = ["t.a", "t.b"]\n'
        'required = {"t.a" = true, "t.b" = ["a"]}\n'
    )
    argv = [str(seq_file), "--config", str(config), "--check", "t.c", "--check", "t.b"]
    _, matrix = run_to_matrix(tmp_path, argv, capsys)
    assert ids(matrix, "a") == ["t.a", "t.b", "t.c"]  # t.d is not selected
    required = {(r.check_id, r.target) for r in matrix.results if r.required}
    # t.b was required for a only: --check makes it required for each target.
    assert required == {(c, t) for c in ("t.a", "t.b", "t.c") for t in ("a", "b")}


def test_check_with_a_config_without_select_keeps_every_check_selected(
    monkeypatch, tmp_path, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a"), Rule("t.b"))
    config = tmp_path / "check.toml"
    config.write_text(f'format = 1\ntargets = ["{profile_a.name}"]\n')
    argv = [str(seq_file), "--config", str(config), "--check", "t.b"]
    _, matrix = run_to_matrix(tmp_path, argv, capsys)
    assert ids(matrix) == ["t.a", "t.b"]
    assert [r.required for r in matrix.results] == [False, True]


def test_a_check_that_is_not_installed_gives_status_1(monkeypatch, seq_file, profile_a, capsys):
    install(monkeypatch, Rule("t.a"))
    assert main([str(seq_file), "--target", str(profile_a), "--check", "t.zzz"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("pulseq-check: error:")
    assert "t.zzz" in err


def test_fast_runs_only_the_fast_checks_and_does_not_make_them_required(
    monkeypatch, tmp_path, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.fast", cost="fast"), Rule("t.slow"))
    argv = [str(seq_file), "--target", str(profile_a)]
    _, matrix = run_to_matrix(tmp_path, [*argv, "--fast"], capsys)
    assert ids(matrix) == ["t.fast"]
    assert not matrix.results[0].required
    # A required check runs whatever --fast says.
    _, matrix = run_to_matrix(tmp_path, [*argv, "--fast", "--check", "t.slow"], capsys)
    assert ids(matrix) == ["t.slow"]  # t.fast is selected by default, and --check selects
    assert matrix.results[0].required


def test_fast_overrides_fast_only_false_of_a_config(
    monkeypatch, tmp_path, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.fast", cost="fast"), Rule("t.slow"))
    config = tmp_path / "check.toml"
    config.write_text(f'format = 1\ntargets = ["{profile_a.name}"]\nfast_only = false\n')
    argv = [str(seq_file), "--config", str(config)]
    _, matrix = run_to_matrix(tmp_path, argv, capsys)
    assert ids(matrix) == ["t.fast", "t.slow"]
    _, matrix = run_to_matrix(tmp_path, [*argv, "--fast"], capsys)
    assert ids(matrix) == ["t.fast"]


def test_an_invalid_profile_gives_status_1_and_a_message_that_names_the_file(
    monkeypatch, seq_file, tmp_path, capsys
):
    install(monkeypatch, Rule("t.a"))
    bad = tmp_path / "bad_profile.toml"
    bad.write_text('format = 1\nname = "x"\n[opts]\nnot_an_opts_key = 1\n')
    status = main([str(seq_file), "--target", str(bad)])
    assert status == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("pulseq-check: error:")
    assert "bad_profile.toml" in captured.err


def test_a_config_that_names_an_invalid_profile_gives_status_1_and_names_the_file(
    monkeypatch, seq_file, tmp_path, capsys
):
    install(monkeypatch, Rule("t.a"))
    config = tmp_path / "check.toml"
    config.write_text('format = 1\ntargets = ["missing_profile.toml"]\n')
    assert main([str(seq_file), "--config", str(config)]) == 1
    assert "missing_profile.toml" in capsys.readouterr().err


def test_an_invalid_config_gives_status_1_and_names_the_file(seq_file, tmp_path, capsys):
    config = tmp_path / "check.toml"
    config.write_text("targets = []\n")
    assert main([str(seq_file), "--config", str(config)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("pulseq-check: error:")
    assert "check.toml" in err


def test_a_sequence_file_that_is_missing_gives_status_1_and_names_the_file(
    monkeypatch, tmp_path, profile_a, capsys
):
    install(monkeypatch, Rule("t.a"))
    status = main([str(tmp_path / "no_such.seq"), "--target", str(profile_a)])
    assert status == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("pulseq-check: error:")
    assert "no_such.seq" in captured.err


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--config", "c.toml", "--target", "a.toml"],
        ["--target", "a.toml", "--unknown-option"],
        ["--target", "a.toml", "--json"],
    ],
    ids=["no config or target", "both", "unknown option", "option without its value"],
)
def test_an_error_in_the_arguments_gives_status_1_not_2(seq_file, capsys, extra):
    assert main([str(seq_file), *extra]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "pulseq-check: error:" in captured.err


def test_a_missing_sequence_argument_gives_status_1(profile_a, capsys):
    assert main(["--target", str(profile_a)]) == 1
    assert "pulseq-check: error:" in capsys.readouterr().err


def test_help_gives_status_0_and_lists_the_options(capsys):
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    for option in ("--config", "--target", "--check", "--fast", "--json", "--quiet"):
        assert option in out


def summary_blocks(out):
    """The blocks of a summary, by the blank lines between them."""
    return out.strip().split("\n\n")


def test_the_summary_has_a_line_for_each_check_and_target_and_the_reasons_below_them(
    monkeypatch, tmp_path, seq_file, capsys
):
    install(
        monkeypatch,
        Rule("t.b", State.FAIL, detail="axis y"),
        Rule("t.a", inputs=("opts.max_grad",)),
    )
    write_profile(tmp_path, "a")
    write_profile(tmp_path, "b")
    config = tmp_path / "check.toml"
    config.write_text('format = 1\ntargets = ["b.toml", "a.toml"]\nrequired = {"t.b" = ["b"]}\n')
    assert main([str(seq_file), "--config", str(config)]) == 2
    blocks = summary_blocks(capsys.readouterr().out)
    assert [block.splitlines()[0] for block in blocks] == [
        f"sequence: {seq_file}",
        "results (* = required):",
        "not evaluated and errors:",
        "exit status 2: a check failed",
    ]
    # One line for each check and target: the targets in the order of the command, then the
    # check IDs. The marker is on the required result only.
    rows = blocks[1].splitlines()[2:]
    cells = [re.split(r"\s{2,}", row[4:].strip()) for row in rows]
    assert [(row[2] == "*", c[:3]) for row, c in zip(rows, cells, strict=True)] == [
        (False, ["not evaluated", "t.a", "b"]),
        (True, ["fail", "t.b", "b"]),
        (False, ["not evaluated", "t.a", "a"]),
        (False, ["fail", "t.b", "a"]),
    ]
    # The value with its unit and the limit, and the detail of a fail, are in the line; the
    # reason of a "not evaluated" is below, once for each result.
    assert "1.5 mT/m (limit 2 mT/m)" in rows[1]
    assert rows[1].endswith("axis y")
    assert "opts.max_grad" not in blocks[1]
    assert blocks[2].count("opts.max_grad") == 2
    assert "t.a, target b" in blocks[2]
    assert "t.a, target a" in blocks[2]


def test_the_summary_lists_the_errors_and_the_unused_sections_of_each_target(
    monkeypatch, tmp_path, seq_file, capsys
):
    install(monkeypatch, Rule("t.a", State.ERROR, detail="ValueError: broken"))
    argv = [str(seq_file), "--target", str(PROFILES / "unused.toml"), "--target"]
    assert main([*argv, str(write_profile(tmp_path, "plain"))]) == 1
    blocks = summary_blocks(capsys.readouterr().out)
    assert [block.splitlines()[0] for block in blocks][-3:] == [
        "not evaluated and errors:",
        "unused profile sections (no check used them):",
        "exit status 1: a check gave an error, or a required check was not evaluated",
    ]
    assert "error: t.a, target Unused sections" in blocks[-3]
    assert "ValueError: broken" in blocks[-3]
    unused = blocks[-2].splitlines()[1:]
    assert len(unused) == 1  # the target "plain" has none
    assert unused[0].startswith("  Unused sections: ")
    assert "notes" in unused[0]


def test_the_last_line_says_that_a_failure_comes_with_an_error(
    monkeypatch, seq_file, profile_a, capsys
):
    install(monkeypatch, Rule("t.a", State.FAIL), Rule("t.b", State.ERROR))
    assert main([str(seq_file), "--target", str(profile_a)]) == 1
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("exit status 1:")
    assert "fail" in last


def test_end_to_end_with_the_installed_checks_and_the_prisma_profile(seq_file, capsys):
    status = main([str(seq_file), "--target", str(PROFILES / "prisma.toml")])
    out = capsys.readouterr().out
    assert status in (0, 2)
    for check_id in ("gradient.amplitude.axis", "pns.safe", "timing.rasters"):
        assert check_id in out
    assert out.rstrip().splitlines()[-1].startswith(f"exit status {status}:")


def test_the_console_script_is_the_main_function_of_the_cli():
    scripts = importlib.metadata.entry_points(group="console_scripts")
    assert scripts["pulseq-check"].value == "pulseq_checks.cli:main"
    assert scripts["pulseq-check"].load() is main
