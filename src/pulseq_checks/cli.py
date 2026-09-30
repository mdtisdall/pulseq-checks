"""The command `pulseq-check` (plan section 4.8, design sections 5.6 and 5.7): it runs the
checks on a `.seq` file for one or more target profiles, writes the summary for a person and
the JSON result, and gives the exit status of `ResultMatrix.exit_status` (0, 2 or 1). An
error of the run, and an error in the arguments, give status 1, not 2: status 2 means that a
check failed."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from .config import read_check_config
from .profile import read_profile
from .results import CheckRunError, Result, ResultMatrix, State
from .run import run_checks

PROG = "pulseq-check"

# The meaning of each exit status, for the last line of the summary (design section 5.6).
_STATUS_MEANING = {
    0: "no check failed",
    2: "a check failed",
    1: "a check gave an error, or a required check was not evaluated",
}


class _Parser(argparse.ArgumentParser):
    """An argument parser that exits with status 1 on an error in the arguments (argparse
    uses 2, and here 2 means that a check failed). `--help` still exits with 0."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _make_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog=PROG,
        description="Check a Pulseq .seq file against the limits of one or more target "
        "scanners. Exit status: 0 no check failed and each required check was evaluated; "
        "2 a check failed; 1 an error in the arguments or the profiles, a check that gave an "
        "error, or a required check that was not evaluated (1 wins over 2).",
        allow_abbrev=False,
    )
    parser.add_argument("seq_file", metavar="SEQ_FILE", type=Path, help="the .seq file to check")
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument(
        "--config",
        metavar="FILE",
        type=Path,
        help="a check configuration file (TOML or JSON) with the target profiles, and "
        "optionally select, required and fast_only",
    )
    targets.add_argument(
        "--target",
        metavar="PROFILE",
        type=Path,
        action="append",
        help="a target profile file (TOML or JSON); repeat it for more targets",
    )
    parser.add_argument(
        "--check",
        metavar="ID",
        action="append",
        default=[],
        help="select this check and make it required for each target; repeat it for more "
        "checks. With --config, it is added to the select and the required of the file",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="run only the checks of cost class fast (and the required checks)",
    )
    parser.add_argument(
        "--json",
        metavar="OUT",
        help="write the result as JSON to the file OUT; '-' is the standard output, and then "
        "the summary goes to the standard error",
    )
    parser.add_argument("--quiet", action="store_true", help="do not write the summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run `pulseq-check` with the arguments `argv` (default: `sys.argv[1:]`) and give the
    exit status. The console script passes it to `sys.exit`. `--help` and an error in the
    arguments give their status as the return value, and do not raise `SystemExit`."""
    try:
        args = _make_parser().parse_args(argv)
    except SystemExit as e:  # --help (status 0) or an error in the arguments (status 1)
        return e.code
    try:
        matrix = _run(args)
        summary_stream = sys.stderr if args.json == "-" else sys.stdout
        if args.json == "-":
            sys.stdout.write(matrix.to_json() + "\n")
        elif args.json is not None:
            _write_json(matrix, args.json)
    except CheckRunError as e:
        print(f"{PROG}: error: {e}", file=sys.stderr)
        return 1
    status = matrix.exit_status()
    if not args.quiet:
        summary_stream.write(summary(matrix))
    return status


def _run(args: argparse.Namespace) -> ResultMatrix:
    """The `ResultMatrix` of the run that `args` describes. Raises `CheckRunError`."""
    checks = list(dict.fromkeys(args.check))
    if args.config is not None:
        config = read_check_config(args.config)
        profile_paths = config.targets
        select = config.select
        if select is not None:
            select = (*select, *(c for c in checks if c not in select))
        required = dict(config.required)
        fast_only = config.fast_only
    else:
        profile_paths = args.target
        select = tuple(checks) if checks else None
        required = {}
        fast_only = False
    for check_id in checks:
        required[check_id] = None  # decision 3: a named check is required for each target
    targets = [read_profile(path) for path in profile_paths]
    return run_checks(
        args.seq_file,
        targets,
        select=select,
        required=required,
        fast_only=fast_only or args.fast,
    )


def _write_json(matrix: ResultMatrix, path: str) -> None:
    try:
        Path(path).write_text(matrix.to_json() + "\n", encoding="utf-8")
    except OSError as e:
        raise CheckRunError(f"cannot write the JSON result to {path!r}: {e}") from e


def summary(matrix: ResultMatrix) -> str:
    """The summary for a person (plan section 4.8), in plain text with aligned columns:
    one line for each check and target, then the "not evaluated" and "error" results with
    their reasons, then the unused profile sections of each target, then the meaning of
    the exit status. The lines of a check are in the order of `matrix.results`."""
    lines = [f"sequence: {matrix.sequence}", ""]

    if matrix.results:
        lines.append("results (* = required):")
        header = ("state", "check", "target", "value", "detail")
        rows = [
            (
                r.state.value,
                r.check_id,
                r.target,
                _value_text(r),
                (r.reason or "") if r.state in (State.PASS, State.FAIL) else "",
            )
            for r in matrix.results
        ]
        widths = [max(len(row[i]) for row in [header, *rows]) for i in range(4)]
        for required, row in zip([False, *(r.required for r in matrix.results)], [header, *rows]):
            cells = [cell.ljust(width) for cell, width in zip(row, widths)]
            lines.append(f"  {'*' if required else ' '} " + "  ".join([*cells, row[4]]).rstrip())
    else:
        lines.append("results: no check ran")

    problems = [r for r in matrix.results if r.state in (State.NOT_EVALUATED, State.ERROR)]
    if problems:
        lines += ["", "not evaluated and errors:"]
        for r in problems:
            required = " (required)" if r.required else ""
            lines.append(f"  {r.state.value}: {r.check_id}, target {r.target}{required}")
            lines += [f"    {line}" for line in (r.reason or "no reason given").splitlines()]

    unused = [(t.name, t.unused_sections) for t in matrix.targets if t.unused_sections]
    if unused:
        lines += ["", "unused profile sections (no check used them):"]
        lines += [f"  {name}: {', '.join(sections)}" for name, sections in unused]

    status = matrix.exit_status()
    meaning = _STATUS_MEANING[status]
    if status == 1 and any(r.state is State.FAIL for r in matrix.results):
        meaning += ", and a check failed"
    lines += ["", f"exit status {status}: {meaning}"]
    return "\n".join(lines) + "\n"


def _value_text(result: Result) -> str:
    """The value with its unit and the limit, for example "27.6 mT/m (limit 80 mT/m)"; empty
    when the result has neither."""
    unit = f" {result.unit}" if result.unit else ""
    parts = []
    if result.value is not None:
        parts.append(f"{result.value:.4g}{unit}")
    if result.limit is not None:
        parts.append(
            f"(limit {result.limit:.4g}{unit})" if parts else f"limit {result.limit:.4g}{unit}"
        )
    return " ".join(parts)
