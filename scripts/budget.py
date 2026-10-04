"""Time and memory of each check on a large synthetic sequence (plan decision 8, part 1).

Builds `build_repeating` of `tests/scale_sequences.py` with about 10^6 blocks, writes it
to a scratch `.seq` file, and runs each installed check alone in a fresh process, with the
synthetic limits, the SAFE example hardware and the acoustic resonances of
`tests/profiles/prisma.toml` as the profile. Run it in the devShell:

    nix develop --command uv run python scripts/budget.py [--blocks N] [--work-dir DIR] \
[--json OUT]

The time of a check is the wall time of `run_checks(path, [profile], select=[check_id])`,
which includes the one read of the `.seq` file. The line "read only" is the time of the
read alone, in its own process, so that a reader can subtract it. The build and the write
of the sequence are timed and printed, but they are not part of the budget. A child stops
at 5 minutes or at 8 GB of RSS. The script is also the child: `_one MODE SEQ PROFILE`
(a hidden sub-command) prints one JSON line.

The mode "@analysis" runs all the checks and keeps the analysis `pns.safe.levels` in the
result (`analyses=["pns.safe.levels"]`). For each run of the checks, the record also gives
the size of `ResultMatrix.to_json()` in UTF-8 bytes and the time of `to_json`, which is not
part of the time of the run.
"""

import argparse
import json
import platform
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

TIME_LIMIT_S = 300.0
RSS_LIMIT_BYTES = 8 * 1024**3
POLL_S = 1.0
ALL = "@all"  # the mode of the child that runs all checks together
FAST = "@fast"  # the mode of the child that runs with `fast_only=True`
ANALYSIS = "@analysis"  # the mode of the child that runs all checks and keeps pns.safe.levels
READ = "@read"  # the mode of the child that only reads the file

# The synthetic limits of `tests/synthetic.SYSTEM` and the four pypulseq default rasters.
PROFILE_HEAD = """\
format = 1
name = "budget"

[opts]
max_grad = 28
grad_unit = "mT/m"
max_slew = 150
slew_unit = "T/m/s"
rf_dead_time = 100e-6
rf_ringdown_time = 20e-6
adc_dead_time = 10e-6

[rasters]
GradientRasterTime = 10e-6
RadiofrequencyRasterTime = 1e-6
AdcRasterTime = 100e-9
BlockDurationRaster = 10e-6

# The resonances of tests/profiles/prisma.toml, so that acoustic.resonance-energy is evaluated.
[acoustic]
resonances = [[590, 100], [1140, 220]]

# The SAFE parameters of pypulseq's example hardware, not of a real scanner.
[models.pns.safe]
name = "pypulseq example hardware (not a real scanner)"
"""
SAFE_FIELDS = ("tau1", "tau2", "tau3", "a1", "a2", "a3", "stim_limit", "stim_thresh", "g_scale")


def profile_text() -> str:
    from pypulseq.utils.safe_pns_prediction import safe_example_hw

    hw = safe_example_hw()
    lines = [PROFILE_HEAD]
    for axis in "xyz":
        lines.append(f"[models.pns.safe.{axis}]")
        lines += [f"{f} = {float(getattr(getattr(hw, axis), f))!r}" for f in SAFE_FIELDS]
        lines.append("")
    return "\n".join(lines)


def peak_rss_bytes() -> int:
    """The peak RSS of this process: `ru_maxrss` is in bytes on macOS and in KiB on Linux."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def child_main(mode: str, seq_path: str, profile_path: str) -> None:
    """Run one mode, and print one JSON line: the mode, the state, the time, the peak RSS,
    and for a run of the checks the size and the time of the JSON result."""
    import pypulseq as pp

    from pulseq_checks.profile import read_profile
    from pulseq_checks.run import run_checks

    if mode == READ:
        start = time.perf_counter()
        pp.Sequence().read(seq_path)
        seconds = time.perf_counter() - start
        state = "read"
        json_record = {}
    else:
        profile = read_profile(profile_path)
        kwargs = {
            FAST: {"fast_only": True},
            ALL: {},
            ANALYSIS: {"analyses": ["pns.safe.levels"]},
        }.get(mode, {"select": [mode]})
        start = time.perf_counter()
        matrix = run_checks(seq_path, [profile], **kwargs)
        seconds = time.perf_counter() - start
        states = sorted({r.state.value for r in matrix.results})
        states += sorted({f"analysis {a.state.value}" for a in matrix.analyses})
        state = "+".join(states) if states else "no check ran"
        start = time.perf_counter()
        text = matrix.to_json()
        json_record = {
            "json_seconds": time.perf_counter() - start,
            "json_bytes": len(text.encode("utf-8")),
        }
    record = {
        "check": mode,
        "state": state,
        "seconds": seconds,
        "peak_rss_bytes": peak_rss_bytes(),
        **json_record,
    }
    print(json.dumps(record))


def rss_bytes(pid: int) -> int | None:
    """The current RSS of a process from `ps`, or None when it is gone."""
    out = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return int(out) * 1024 if out else None


def run_child(mode: str, seq_path: Path, profile_path: Path) -> dict:
    """Run `_one` for `mode` in a fresh process. Stops it at `TIME_LIMIT_S` or at
    `RSS_LIMIT_BYTES`, and then gives a record with a `stopped` reason and no time."""
    cmd = [sys.executable, __file__, "_one", mode, str(seq_path), str(profile_path)]
    start = time.perf_counter()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stopped, seen = None, 0
    while True:
        try:
            out, err = proc.communicate(timeout=POLL_S)
            break
        except subprocess.TimeoutExpired:
            seen = max(seen, rss_bytes(proc.pid) or 0)
            if time.perf_counter() - start > TIME_LIMIT_S:
                stopped = f"stopped at the time limit of {TIME_LIMIT_S:.0f} s"
            elif seen > RSS_LIMIT_BYTES:
                stopped = f"stopped at the RSS limit of {RSS_LIMIT_BYTES / 1024**3:.0f} GB"
            if stopped:
                proc.kill()
                proc.communicate()
                return {
                    "check": mode,
                    "state": None,
                    "seconds": None,
                    "peak_rss_bytes": seen,
                    "stopped": stopped,
                }
    if proc.returncode != 0 or not out.strip():
        tail = err.strip().splitlines()[-1:] or ["no output"]
        return {
            "check": mode,
            "state": None,
            "seconds": None,
            "peak_rss_bytes": seen,
            "stopped": f"child failed ({proc.returncode}): {tail[0]}",
        }
    return json.loads(out.strip().splitlines()[-1])


def machine() -> dict:
    cpu = platform.processor()
    if sys.platform == "darwin":
        brand = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        cpu = brand or cpu
    return {
        "platform": platform.platform(),
        "cpu": cpu,
        "python": platform.python_version(),
        "pypulseq": version("pypulseq"),
        "pulseq_checks": version("pulseq-checks"),
    }


def label(record: dict) -> str:
    return {
        ALL: "all checks together",
        ANALYSIS: "all checks, pns.safe.levels kept",
        FAST: "fast_only=True",
        READ: "read only",
    }.get(record["check"], record["check"])


def table(records: list[dict]) -> str:
    width = max(len(label(r)) for r in records)
    header = (
        f"{'check':<{width}}  {'time (s)':>9}  {'peak RSS (MB)':>13}  {'JSON (MB)':>9}  "
        f"{'JSON (s)':>8}  state"
    )
    lines = [header]
    for r in records:
        rss = f"{r['peak_rss_bytes'] / 1e6:13.0f}"
        size = f"{r['json_bytes'] / 1e6:9.3f}" if "json_bytes" in r else f"{'-':>9}"
        json_s = f"{r['json_seconds']:8.2f}" if "json_seconds" in r else f"{'-':>8}"
        if r.get("stopped"):
            lines.append(f"{label(r):<{width}}  {'-':>9}  {rss}  {size}  {json_s}  {r['stopped']}")
        else:
            lines.append(
                f"{label(r):<{width}}  {r['seconds']:9.2f}  {rss}  {size}  {json_s}  {r['state']}"
            )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--blocks", type=int, default=1_000_000, help="blocks of the sequence")
    parser.add_argument("--work-dir", type=Path, help="scratch directory (default: temporary)")
    parser.add_argument("--json", type=Path, metavar="OUT", help="write the results as JSON")
    args = parser.parse_args()

    from scale_sequences import TR_BLOCKS, build_repeating

    from pulseq_checks import registry

    temporary = None
    if args.work_dir is None:
        temporary = tempfile.mkdtemp(prefix="pulseq-budget-")
        work = Path(temporary)
    else:
        work = args.work_dir
        work.mkdir(parents=True, exist_ok=True)
    try:
        n_trs = args.blocks // TR_BLOCKS
        print(f"building {n_trs * TR_BLOCKS} blocks", file=sys.stderr)
        start = time.perf_counter()
        seq = build_repeating(n_trs)
        build_s = time.perf_counter() - start
        seq_path = work / "budget.seq"
        start = time.perf_counter()
        seq.write(str(seq_path))
        write_s = time.perf_counter() - start
        del seq
        profile_path = work / "budget.toml"
        profile_path.write_text(profile_text())
        print(f"build {build_s:.1f} s, write {write_s:.1f} s (not part of the budget)")

        modes = [READ, *sorted(registry.check_rules()), ALL, ANALYSIS, FAST]
        records = []
        for mode in modes:
            print(f"running {mode}", file=sys.stderr)
            records.append(run_child(mode, seq_path, profile_path))
        info = machine()
        print()
        print(f"blocks: {n_trs * TR_BLOCKS}; " + "; ".join(f"{k}: {v}" for k, v in info.items()))
        print(table(records))
        print(
            "\nEach time includes the one read of the .seq file (see 'read only'). "
            "'fast_only=True' runs the checks of the cost class 'fast'; the budget of "
            "decision 7 is for them together. 'JSON' is the size and the time of "
            "ResultMatrix.to_json(), which is not part of the time of the run."
        )
        if args.json:
            report = {
                "blocks": n_trs * TR_BLOCKS,
                "build_seconds": build_s,
                "write_seconds": write_s,
                "machine": info,
                "results": records,
            }
            args.json.write_text(json.dumps(report, indent=2) + "\n")
    finally:
        if temporary:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "_one":
        child_main(*sys.argv[2:])
    else:
        main()
