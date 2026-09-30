import importlib.metadata
from types import SimpleNamespace

import pypulseq as pp
import pytest
from synthetic import spin_echo_sequence

from pulseq_checks import registry
from pulseq_checks.grad_limits import HardwareLimits
from pulseq_checks.profile import TargetProfile
from pulseq_checks.registry import RegistryError
from pulseq_checks.results import Location, Result, State
from pulseq_checks.rules import DOCS_URL, CheckSpec, RunContext, spec_url
from pulseq_checks.run import RunError, run_checks


def make_spec(check_id, *, inputs=(), models=(), cost="slow", url=None):
    return CheckSpec(
        id=check_id,
        version=3,
        title=check_id,
        quantity="a test quantity",
        inputs=tuple(inputs),
        models=tuple(models),
        limit="a test limit",
        tolerance="none",
        pass_condition="always",
        cost=cost,
        url=url,
    )


class Rule:
    """A test check rule. `fn(ctx)` gives its result (default: a pass). `contexts` is the
    context of each call of `run`."""

    def __init__(self, spec, fn=None):
        self.spec = spec
        self.fn = fn
        self.contexts = []

    def run(self, ctx):
        self.contexts.append(ctx)
        if self.fn is None:
            return ctx.result(self.spec, State.PASS)
        return self.fn(ctx)


def make_profile(
    name="a", *, opts=None, inputs=(), models=(), hardware_limits=None, unused=()
) -> TargetProfile:
    return TargetProfile(
        name=name,
        vendor=None,
        format_version=1,
        source_path=None,
        opts=opts,
        hardware_limits=hardware_limits,
        rasters=None,
        models={model: {} for model in models},
        acoustic_resonances=None,
        sources={path: "profile" for path in inputs},
        unused_sections=tuple(unused),
    )


def install(monkeypatch, *rules):
    """Make `registry.check_rules` give `rules`, by ID."""
    monkeypatch.setattr(registry, "check_rules", lambda: {r.spec.id: r for r in rules})


def by_key(matrix):
    return {(r.check_id, r.target): r for r in matrix.results}


@pytest.fixture
def seq_file(tmp_path):
    path = tmp_path / "spin_echo.seq"
    spin_echo_sequence().write(str(path))
    return path


def test_a_missing_input_gives_not_evaluated_and_run_is_not_called(monkeypatch):
    rule = Rule(make_spec("t.a", inputs=("opts.max_grad", "opts.max_slew")))
    install(monkeypatch, rule)
    target = make_profile(inputs=("opts.max_grad",))
    matrix = run_checks(spin_echo_sequence(), [target])
    (result,) = matrix.results
    assert result.state is State.NOT_EVALUATED
    assert "opts.max_slew" in result.reason
    assert "opts.max_grad" not in result.reason
    assert (result.check_id, result.spec_version, result.target) == ("t.a", 3, "a")
    assert rule.contexts == []


def test_a_missing_model_gives_not_evaluated_and_run_is_not_called(monkeypatch):
    rule = Rule(make_spec("t.a", models=("m.one", "m.two")))
    install(monkeypatch, rule)
    target = make_profile(models=("m.one",))
    (result,) = run_checks(spin_echo_sequence(), [target]).results
    assert result.state is State.NOT_EVALUATED
    assert "m.two" in result.reason
    assert "m.one" not in result.reason
    assert rule.contexts == []


def test_a_rule_with_its_input_and_model_is_called(monkeypatch):
    rule = Rule(make_spec("t.a", inputs=("opts.max_grad",), models=("m.one",)))
    install(monkeypatch, rule)
    target = make_profile(inputs=("opts.max_grad",), models=("m.one",))
    (result,) = run_checks(spin_echo_sequence(), [target]).results
    assert result.state is State.PASS
    assert len(rule.contexts) == 1


def test_an_exception_of_run_gives_error_and_the_other_checks_run(monkeypatch):
    def fail(ctx):
        raise ValueError("a test failure")

    bad = Rule(make_spec("t.a"), fail)
    good = Rule(make_spec("t.b"))
    install(monkeypatch, bad, good)
    matrix = run_checks(spin_echo_sequence(), [make_profile()])
    results = by_key(matrix)
    assert results["t.a", "a"].state is State.ERROR
    assert results["t.a", "a"].reason == "ValueError: a test failure"
    assert results["t.b", "a"].state is State.PASS


def test_a_result_for_another_check_or_target_gives_error(monkeypatch):
    other_check = Rule(make_spec("t.a"), lambda ctx: ctx.result(make_spec("t.other"), State.PASS))
    other_target = Rule(
        make_spec("t.b"),
        lambda ctx: Result(check_id="t.b", spec_version=3, target="other", state=State.PASS),
    )
    not_a_result = Rule(make_spec("t.c"), lambda ctx: None)
    install(monkeypatch, other_check, other_target, not_a_result)
    results = by_key(run_checks(spin_echo_sequence(), [make_profile()]))
    for key, text in [("t.a", "t.other"), ("t.b", "other"), ("t.c", "NoneType")]:
        result = results[key, "a"]
        assert result.state is State.ERROR
        assert text in result.reason
        assert result.check_id == key


def test_a_result_of_a_rule_keeps_its_fields_and_gets_the_spec_link(monkeypatch):
    def fn(ctx):
        return ctx.result(
            rule.spec,
            State.FAIL,
            value=2.0,
            limit=1.0,
            unit="u",
            location=Location(block=4, time_s=0.5),
        )

    rule = Rule(make_spec("t.a.b"), fn)
    install(monkeypatch, rule)
    (result,) = run_checks(spin_echo_sequence(), [make_profile()]).results
    assert result == Result(
        check_id="t.a.b",
        spec_version=3,
        target="a",
        state=State.FAIL,
        value=2.0,
        limit=1.0,
        unit="u",
        location=Location(block=4, time_s=0.5),
        required=False,
        spec_url=DOCS_URL + "#tab",
    )


def test_spec_url_is_the_url_of_the_spec_or_the_heading_of_its_id():
    assert spec_url(make_spec("gradient.slew.axis")) == DOCS_URL + "#gradientslewaxis"
    assert spec_url(make_spec("a.b-c")) == DOCS_URL + "#ab-c"
    assert spec_url(make_spec("a.b", url="https://example.org/a")) == "https://example.org/a"


def test_the_matrix_has_the_sequence_the_version_and_the_targets(monkeypatch, seq_file):
    install(monkeypatch, Rule(make_spec("t.a")))
    target = make_profile("p", inputs=("opts.max_grad",), unused=("models.other",))
    matrix = run_checks(str(seq_file), [target])
    assert matrix.sequence == str(seq_file)
    assert matrix.package_version == importlib.metadata.version("pulseq-checks")
    (info,) = matrix.targets
    assert info.name == "p"
    assert info.sources == {"opts.max_grad": "profile"}
    assert info.unused_sections == ("models.other",)
    assert info.limits_source == "profile"
    assert run_checks(seq_file, [target]).sequence == str(seq_file)
    assert run_checks(spin_echo_sequence(), [target]).sequence == "<Sequence object>"


def test_the_results_are_in_the_order_of_the_targets_and_the_check_ids(monkeypatch, seq_file):
    install(monkeypatch, Rule(make_spec("t.b")), Rule(make_spec("t.a")), Rule(make_spec("t.c")))
    matrix = run_checks(seq_file, [make_profile("y"), make_profile("x")])
    assert [(r.target, r.check_id) for r in matrix.results] == [
        ("y", "t.a"),
        ("y", "t.b"),
        ("y", "t.c"),
        ("x", "t.a"),
        ("x", "t.b"),
        ("x", "t.c"),
    ]
    assert [t.name for t in matrix.targets] == ["y", "x"]


def test_measure_runs_one_time_for_each_target(monkeypatch, seq_file):
    calls = []

    def fn(seq):
        calls.append(seq)
        return object()

    seen = {}

    def make_rule(check_id):
        def run(ctx):
            seen[check_id, ctx.profile.name] = ctx.measure("m", fn)
            return ctx.result(rule.spec, State.PASS)

        rule = Rule(make_spec(check_id), run)
        return rule

    install(monkeypatch, make_rule("t.a"), make_rule("t.b"))
    run_checks(seq_file, [make_profile("x"), make_profile("y")])
    assert len(calls) == 2
    assert calls[0] is not calls[1]
    assert seen["t.a", "x"] is seen["t.b", "x"]
    assert seen["t.a", "y"] is seen["t.b", "y"]
    assert seen["t.a", "x"] is not seen["t.a", "y"]


def test_measure_keeps_a_value_for_each_name(monkeypatch):
    def run(ctx):
        first = ctx.measure("one", lambda seq: [1])
        second = ctx.measure("two", lambda seq: [2])
        again = ctx.measure("one", lambda seq: [3])
        assert (first, second, again) == ([1], [2], [1])
        return ctx.result(rule.spec, State.PASS)

    rule = Rule(make_spec("t.a"), run)
    install(monkeypatch, rule)
    (result,) = run_checks(spin_echo_sequence(), [make_profile()]).results
    assert result.state is State.PASS


def test_required_for_all_targets_with_none(monkeypatch, seq_file):
    install(monkeypatch, Rule(make_spec("t.a")), Rule(make_spec("t.b")))
    matrix = run_checks(seq_file, [make_profile("x"), make_profile("y")], required={"t.a": None})
    results = by_key(matrix)
    assert [results["t.a", n].required for n in "xy"] == [True, True]
    assert [results["t.b", n].required for n in "xy"] == [False, False]


def test_required_for_named_targets(monkeypatch, seq_file):
    install(monkeypatch, Rule(make_spec("t.a")))
    matrix = run_checks(seq_file, [make_profile("x"), make_profile("y")], required={"t.a": ["y"]})
    results = by_key(matrix)
    assert results["t.a", "x"].required is False
    assert results["t.a", "y"].required is True


def test_required_is_set_for_not_evaluated_and_error_results(monkeypatch):
    def fail(ctx):
        raise RuntimeError("x")

    install(
        monkeypatch,
        Rule(make_spec("t.a", inputs=("opts.max_grad",))),
        Rule(make_spec("t.b"), fail),
    )
    matrix = run_checks(spin_echo_sequence(), [make_profile()], required={"t.a": None, "t.b": None})
    assert [(r.state, r.required) for r in matrix.results] == [
        (State.NOT_EVALUATED, True),
        (State.ERROR, True),
    ]


def test_required_with_an_unknown_check_id_is_an_error(monkeypatch):
    install(monkeypatch, Rule(make_spec("t.a")))
    with pytest.raises(RunError, match="t.unknown"):
        run_checks(spin_echo_sequence(), [make_profile()], required={"t.unknown": None})


def test_required_with_an_unknown_target_is_an_error(monkeypatch):
    install(monkeypatch, Rule(make_spec("t.a")))
    with pytest.raises(RunError, match="nowhere"):
        run_checks(spin_echo_sequence(), [make_profile()], required={"t.a": ["nowhere"]})


def test_select_runs_only_the_selected_checks(monkeypatch):
    rules = [Rule(make_spec(f"t.{n}")) for n in "abc"]
    install(monkeypatch, *rules)
    matrix = run_checks(spin_echo_sequence(), [make_profile()], select=["t.c", "t.a"])
    assert [r.check_id for r in matrix.results] == ["t.a", "t.c"]
    assert len(rules[1].contexts) == 0
    all_checks = run_checks(spin_echo_sequence(), [make_profile()])
    assert [r.check_id for r in all_checks.results] == ["t.a", "t.b", "t.c"]


def test_select_with_an_unknown_check_id_is_an_error(monkeypatch):
    install(monkeypatch, Rule(make_spec("t.a")))
    with pytest.raises(RunError, match="t.unknown"):
        run_checks(spin_echo_sequence(), [make_profile()], select=["t.a", "t.unknown"])


def test_a_required_check_runs_when_select_does_not_name_it(monkeypatch):
    install(monkeypatch, Rule(make_spec("t.a")), Rule(make_spec("t.b")), Rule(make_spec("t.c")))
    matrix = run_checks(
        spin_echo_sequence(), [make_profile()], select=["t.a"], required={"t.c": None}
    )
    assert [(r.check_id, r.required) for r in matrix.results] == [("t.a", False), ("t.c", True)]


def test_fast_only_runs_the_fast_checks_and_the_slow_required_checks(monkeypatch):
    install(
        monkeypatch,
        Rule(make_spec("t.fast", cost="fast")),
        Rule(make_spec("t.slow", cost="slow")),
        Rule(make_spec("t.slow-required", cost="slow")),
        Rule(make_spec("t.slow-other-target", cost="slow")),
    )
    matrix = run_checks(
        spin_echo_sequence(),
        [make_profile()],
        fast_only=True,
        required={"t.slow-required": None, "t.slow-other-target": []},
    )
    assert [(r.check_id, r.required) for r in matrix.results] == [
        ("t.fast", False),
        ("t.slow-other-target", False),
        ("t.slow-required", True),
    ]


def test_fast_only_with_select_removes_the_slow_selected_checks(monkeypatch):
    install(
        monkeypatch,
        Rule(make_spec("t.fast", cost="fast")),
        Rule(make_spec("t.slow")),
        Rule(make_spec("t.other", cost="fast")),
    )
    matrix = run_checks(
        spin_echo_sequence(), [make_profile()], select=["t.fast", "t.slow"], fast_only=True
    )
    assert [r.check_id for r in matrix.results] == ["t.fast"]


def test_a_path_is_read_one_time_for_each_target_with_the_opts_of_that_target(
    monkeypatch, seq_file
):
    reads = []
    original = pp.Sequence.read

    def counting_read(self, path, *args, **kwargs):
        reads.append((self, path))
        return original(self, path, *args, **kwargs)

    monkeypatch.setattr(pp.Sequence, "read", counting_read)
    seen = []

    def fn(ctx):
        seen.append(
            (
                ctx.profile.name,
                ctx.sequence,
                ctx.sequence.system.adc_dead_time,
                len(ctx.sequence.block_events),
            )
        )
        return ctx.result(rule.spec, State.PASS)

    rule = Rule(make_spec("t.a"), fn)
    install(monkeypatch, rule, Rule(make_spec("t.b")))
    targets = [
        make_profile("x", opts={"adc_dead_time": 5e-6}),
        make_profile("y", opts={"adc_dead_time": 40e-6}),
    ]
    run_checks(str(seq_file), targets)
    assert [path for _, path in reads] == [str(seq_file)] * 2
    assert reads[0][0] is not reads[1][0]
    assert [(name, dead_time) for name, _, dead_time, _ in seen] == [("x", 5e-6), ("y", 40e-6)]
    assert [seq for _, seq, _, _ in seen] == [seq for seq, _ in reads]
    n_blocks = len(spin_echo_sequence().block_events)
    assert [n for _, _, _, n in seen] == [n_blocks, n_blocks]


def test_a_path_that_cannot_be_read_is_an_error_that_names_the_file_and_the_target(
    monkeypatch, tmp_path
):
    install(monkeypatch, Rule(make_spec("t.a")))
    missing = tmp_path / "missing.seq"
    with pytest.raises(RunError) as excinfo:
        run_checks(missing, [make_profile("scanner")])
    assert str(missing) in str(excinfo.value)
    assert "scanner" in str(excinfo.value)
    assert "FileNotFoundError" in str(excinfo.value)
    bad = tmp_path / "bad.seq"
    bad.write_text("this is not a sequence file\n")
    with pytest.raises(RunError) as excinfo:
        run_checks(bad, [make_profile("scanner")])
    assert str(bad) in str(excinfo.value)
    assert "scanner" in str(excinfo.value)


def test_a_sequence_object_is_used_for_its_one_target(monkeypatch):
    rule = Rule(make_spec("t.a"))
    install(monkeypatch, rule)
    seq = spin_echo_sequence()
    run_checks(seq, [make_profile()])
    (ctx,) = rule.contexts
    assert ctx.sequence is seq
    assert ctx.limits_source == "profile"


def test_a_sequence_object_with_two_targets_is_an_error(monkeypatch):
    install(monkeypatch, Rule(make_spec("t.a")))
    with pytest.raises(RunError, match="exactly one target"):
        run_checks(spin_echo_sequence(), [make_profile("x"), make_profile("y")])


def test_no_target_is_an_error(monkeypatch, seq_file):
    install(monkeypatch, Rule(make_spec("t.a")))
    with pytest.raises(RunError, match="no target"):
        run_checks(seq_file, [])
    with pytest.raises(RunError, match="no target"):
        run_checks(spin_echo_sequence(), ())


def test_two_targets_with_one_name_are_an_error(monkeypatch, seq_file):
    install(monkeypatch, Rule(make_spec("t.a")))
    with pytest.raises(RunError, match="'x'"):
        run_checks(seq_file, [make_profile("x"), make_profile("y"), make_profile("x")])


def test_limits_from_sequence_takes_the_limits_of_seq_system_for_a_target_with_none(monkeypatch):
    rule = Rule(make_spec("t.a", inputs=("opts.max_grad", "opts.max_slew")))
    install(monkeypatch, rule)
    matrix = run_checks(spin_echo_sequence(), [make_profile()], limits_from_sequence=True)
    (ctx,) = rule.contexts
    assert ctx.limits_source == "sequence object"
    limits = ctx.hardware_limits
    assert limits.max_grad_mt_per_m == pytest.approx(28)
    assert limits.max_slew_t_per_m_per_s == pytest.approx(150)
    assert limits.label == "sequence object"
    assert matrix.targets[0].limits_source == "sequence object"
    assert matrix.results[0].state is State.PASS


def test_a_target_with_limits_keeps_its_limits_with_limits_from_sequence(monkeypatch):
    rule = Rule(make_spec("t.a"))
    install(monkeypatch, rule)
    own = HardwareLimits(max_grad_mt_per_m=80, max_slew_t_per_m_per_s=200, label="own")
    target = make_profile(inputs=("opts.max_grad", "opts.max_slew"), hardware_limits=own)
    matrix = run_checks(spin_echo_sequence(), [target], limits_from_sequence=True)
    (ctx,) = rule.contexts
    assert ctx.limits_source == "profile"
    assert ctx.hardware_limits == own
    assert matrix.targets[0].limits_source == "profile"


def test_a_target_with_one_limit_keeps_its_profile_with_limits_from_sequence(monkeypatch):
    rule = Rule(make_spec("t.a", inputs=("opts.max_grad", "opts.max_slew")))
    install(monkeypatch, rule)
    target = make_profile(inputs=("opts.max_grad",))
    matrix = run_checks(spin_echo_sequence(), [target], limits_from_sequence=True)
    assert matrix.targets[0].limits_source == "profile"
    assert matrix.results[0].state is State.NOT_EVALUATED
    assert "opts.max_slew" in matrix.results[0].reason


def test_without_limits_from_sequence_a_target_with_no_limits_is_not_evaluated(monkeypatch):
    rule = Rule(make_spec("t.a", inputs=("opts.max_grad",)))
    install(monkeypatch, rule)
    matrix = run_checks(spin_echo_sequence(), [make_profile()])
    assert matrix.results[0].state is State.NOT_EVALUATED
    assert matrix.targets[0].limits_source == "profile"
    assert rule.contexts == []


def test_limits_from_sequence_with_a_path_is_an_error(monkeypatch, seq_file):
    install(monkeypatch, Rule(make_spec("t.a")))
    with pytest.raises(RunError, match="limits_from_sequence"):
        run_checks(seq_file, [make_profile()], limits_from_sequence=True)
    with pytest.raises(RunError, match="limits_from_sequence"):
        run_checks(str(seq_file), [make_profile()], limits_from_sequence=True)


def test_has_input_is_true_for_a_value_path_of_the_profile_only_without_the_opt_in():
    target = make_profile(inputs=("opts.max_grad",))
    ctx = RunContext(spin_echo_sequence(), target)
    assert ctx.has_input("opts.max_grad")
    assert not ctx.has_input("opts.max_slew")
    assert not ctx.has_input("opts.adc_dead_time")
    ctx = RunContext(spin_echo_sequence(), target, limits_source="sequence object")
    assert ctx.has_input("opts.max_slew")
    assert not ctx.has_input("opts.adc_dead_time")


class EntryPoint:
    """A fake entry point: `load` gives `obj`, or raises `obj` when it is an exception."""

    def __init__(self, name, obj, package="a-package"):
        self.name = name
        self.obj = obj
        self.dist = None if package is None else SimpleNamespace(name=package)

    def load(self):
        if isinstance(self.obj, Exception):
            raise self.obj
        return self.obj


def install_entry_points(monkeypatch, **groups):
    """Make `importlib.metadata.entry_points(group=...)` give the fake entry points of
    `groups` (keys `readers`, `models` and `checks`)."""
    by_group = {
        registry.PROFILE_READERS: groups.get("readers", []),
        registry.MODELS: groups.get("models", []),
        registry.CHECKS: groups.get("checks", []),
    }
    monkeypatch.setattr(
        importlib.metadata, "entry_points", lambda *, group: list(by_group.get(group, []))
    )


def test_check_rules_are_keyed_by_spec_id(monkeypatch):
    a, b = Rule(make_spec("t.a")), Rule(make_spec("t.b"))
    install_entry_points(monkeypatch, checks=[EntryPoint("x", b), EntryPoint("y", a)])
    assert registry.check_rules() == {"t.a": a, "t.b": b}


def test_two_check_rules_with_one_id_are_an_error_that_names_both_packages(monkeypatch):
    install_entry_points(
        monkeypatch,
        checks=[
            EntryPoint("x", Rule(make_spec("t.a")), package="pkg-one"),
            EntryPoint("y", Rule(make_spec("t.a")), package="pkg-two"),
        ],
    )
    with pytest.raises(RegistryError) as excinfo:
        registry.check_rules()
    message = str(excinfo.value)
    assert "t.a" in message
    assert "pkg-one" in message
    assert "pkg-two" in message


def test_a_check_entry_point_that_cannot_be_loaded_is_an_error_that_names_it(monkeypatch):
    install_entry_points(
        monkeypatch,
        checks=[EntryPoint("broken-check", ImportError("no module named foo"), package="pkg-bad")],
    )
    with pytest.raises(RegistryError) as excinfo:
        registry.check_rules()
    message = str(excinfo.value)
    assert "broken-check" in message
    assert "pkg-bad" in message
    assert "ImportError" in message
    assert "no module named foo" in message


def test_a_check_entry_point_without_a_spec_is_an_error_that_names_it(monkeypatch):
    install_entry_points(monkeypatch, checks=[EntryPoint("no-spec", object(), package="pkg-x")])
    with pytest.raises(RegistryError, match="no-spec"):
        registry.check_rules()


def test_models_are_keyed_by_name_and_two_with_one_name_are_an_error(monkeypatch):
    one = SimpleNamespace(name="m.one", version=1)
    two = SimpleNamespace(name="m.two", version=2)
    install_entry_points(monkeypatch, models=[EntryPoint("a", one), EntryPoint("b", two)])
    assert registry.models() == {"m.one": one, "m.two": two}
    install_entry_points(
        monkeypatch,
        models=[
            EntryPoint("a", one, package="pkg-one"),
            EntryPoint("b", SimpleNamespace(name="m.one", version=2), package=None),
        ],
    )
    with pytest.raises(RegistryError) as excinfo:
        registry.models()
    assert "m.one" in str(excinfo.value)
    assert "pkg-one" in str(excinfo.value)


def test_a_model_entry_point_that_cannot_be_loaded_is_an_error_that_names_it(monkeypatch):
    install_entry_points(
        monkeypatch, models=[EntryPoint("broken-model", RuntimeError("boom"), package="pkg-bad")]
    )
    with pytest.raises(RegistryError) as excinfo:
        registry.models()
    assert "broken-model" in str(excinfo.value)
    assert "pkg-bad" in str(excinfo.value)


def test_profile_reader_gives_the_reader_by_name_or_none(monkeypatch):
    def reader(path):
        return {}, {}

    install_entry_points(
        monkeypatch,
        readers=[EntryPoint("siemens-asc", reader), EntryPoint("other", lambda path: None)],
    )
    assert registry.profile_reader("siemens-asc") is reader
    assert registry.profile_reader("missing") is None
    install_entry_points(monkeypatch)
    assert registry.profile_reader("siemens-asc") is None


def test_two_profile_readers_with_one_name_are_an_error_that_names_both_packages(monkeypatch):
    install_entry_points(
        monkeypatch,
        readers=[
            EntryPoint("siemens-asc", print, package="pkg-one"),
            EntryPoint("siemens-asc", repr, package="pkg-two"),
        ],
    )
    with pytest.raises(RegistryError) as excinfo:
        registry.profile_reader("siemens-asc")
    assert "pkg-one" in str(excinfo.value)
    assert "pkg-two" in str(excinfo.value)
    assert registry.profile_reader("other") is None
