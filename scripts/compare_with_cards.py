"""Compare the checks of pulseq-checks with the cards of pulseq-reports (plan phase 7).

The two packages have two environments, so the work runs in four sub-commands, in several
processes. `OUT_DIR` is a scratch directory outside the repository.

    prepare OUT_DIR [--exvivo PATH] [--sequences A,B] [--limit-sets A,B]
        (devShell of this repository) writes the `.seq` files, the target profiles, the
        synthetic `.asc` files and `manifest.json`. The ex-vivo file is a symlink, never a copy.
    cards OUT_DIR
        (devShell of the pulseq-reports reference worktree) runs `timing_card`,
        `gradient_limits_card` (whole file, `check_norms=True`) and `pns_card` for each
        sequence and limit set. Writes `cards.jsonl`. Imports `pulseq_reports` and pypulseq.
    checks OUT_DIR
        (devShell of this repository) runs `run_checks` for the same pairs. Writes
        `checks.jsonl`. Imports `pulseq_checks`.
    compare OUT_DIR
        (either devShell) joins the two files, writes `comparison.jsonl`, prints a table and a
        summary, and exits 1 when a pair differs.
    run OUT_DIR --reference PATH [--exvivo PATH] [...]
        runs the four steps in their environments (this command runs in the devShell of this
        repository, and starts `nix develop` in the reference worktree for `cards`).

For example, from the root of this repository:

    nix develop --command uv run python scripts/compare_with_cards.py run SCRATCH/compare \\
        --reference /path/to/pulseq-reports/.worktrees/cards-reference \\
        --exvivo /path/to/pulseq-reports/data/exvivo_gre_seg_0.seq

The units of the comparison: PNS is compared as `100 * peak` (percent): the new check gives
`100 * peak`, and the card side computes the same product from the unrounded peak of
`pulseq_reports.pns.pns_prediction` (the card rounds its displayed percent to 0.01, so its
rounded value is not used as a number). The verdict of the PNS card is its own check.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
AXES = ("x", "y", "z")
REL_TOL = 1e-12

# The limit sets of task 7.2. Values of the `gradient-fail` set: every synthetic sequence
# with gradients has a peak of at least 2.8 mT/m on some axis (`arbitrary_gradient_sequence`
# and `border_sequence`, 10 % of 28 mT/m) and a peak slew of at least 7 T/m/s
# (`border_sequence`: 2.8 mT/m in 400 µs), so 1 mT/m and 2 T/m/s are below every such
# sequence, and the |G| peak is above 1 mT/m as well. `compare` checks the claim: it reports a
# sequence with gradients that still passes in this set.
GRADIENT_FAIL_MAX_GRAD_MT_PER_M = 1.0
GRADIENT_FAIL_MAX_SLEW_T_PER_M_PER_S = 2.0
# The `pns-fail` set: the SAFE example hardware with its limits and thresholds multiplied by
# this scale. The SAFE total is linear in the gradient and in 1 / stimulation limit, so a scale
# of PNS_FAIL_SCALE raises the PNS of each sequence by 1 / scale. The value is chosen so that
# the sequence with the smallest gradients (`arbitrary_gradient_sequence`) is at 100 % or more;
# `compare` reports a sequence with gradients whose PNS still passes in this set.
PNS_FAIL_SCALE = 0.01
# The `timing-fail` set: the synthetic limits with a longer RF dead time and RF ringdown than the
# synthetic sequences use (100 µs and 20 µs), so that each sequence with an RF pulse has timing
# errors (the RF delay is shorter than the dead time, and the block is shorter than the pulse
# with its ringdown). It gives the comparison of the timing error lists a failing case.
TIMING_FAIL_RF_DEAD_TIME_S = 200e-6
TIMING_FAIL_RF_RINGDOWN_TIME_S = 30e-6


def _json_default(value: Any) -> Any:
    import numpy as np

    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def _dump(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=_json_default) + "\n")


def _load_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _attempt(fn) -> dict:
    """`{"value": fn()}`, or `{"raised": "Type: message"}` when `fn` raises."""
    try:
        return {"value": fn()}
    except Exception as e:  # noqa: BLE001 (an exception of a card or a check is its result)
        return {"raised": f"{type(e).__name__}: {e}"}


def _manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))


# ---- prepare (devShell of this repository) ----


def _write_gradient_asc(
    directory: Path, limit_scale: float = 1.0, name: str = "MP_GPA_TEST", split: bool = False
) -> Path:
    """Copied from `write_gradient_asc` of `tests/conftest.py` (a pytest fixture), less the
    `gpa` option: a gradient .asc file with the PNS parameters of pypulseq's example hardware,
    with the stimulation limits and thresholds multiplied by `limit_scale`. With `split`, the
    layout of a scanner file (an `ASCCONV` block with CRLF line ends and an included
    `_GSWD_SAFETY.asc` file)."""
    from pypulseq.utils.safe_pns_prediction import safe_example_hw

    hw = safe_example_hw()
    prefix = "GradPatSup.Phys.PNS." if split else ""
    pns_lines, scale_lines = [], []
    for axis in "xyz":
        a, suffix = getattr(hw, axis), axis.upper()
        pns_lines += [
            f"{prefix}flGSWDTau{suffix}[{i}] = {getattr(a, f'tau{i + 1}')!r}" for i in range(3)
        ]
        pns_lines += [
            f"{prefix}flGSWDA{suffix}[{i}] = {getattr(a, f'a{i + 1}')!r}" for i in range(3)
        ]
        pns_lines += [
            f"{prefix}flGSWDStimulationLimit{suffix} = {a.stim_limit * limit_scale!r}",
            f"{prefix}flGSWDStimulationThreshold{suffix} = {a.stim_thresh * limit_scale!r}",
        ]
        scale_lines.append(
            f"asGPAParameters[0].sGCParameters.flGScaleFactor{suffix} = {a.g_scale!r}"
        )
    path = directory / f"{name}_{limit_scale:g}.asc"
    if not split:
        path.write_text("\n".join([f'asCOMP.tName = "{name}"', *pns_lines, *scale_lines]) + "\n")
        return path

    def ascconv(lines):
        block = ["### ASCCONV BEGIN @Checksum=mp2:0 ###", "", *lines, "", "### ASCCONV END ###"]
        return "\r\n".join(block) + "\r\n"

    safety = path.with_name(f"{path.stem}_GSWD_SAFETY.asc")
    safety.write_bytes(ascconv(pns_lines).encode())
    main = [f'asCOMP[0].tName = "{name}"', *scale_lines, f"$INCLUDE {safety.name}"]
    path.write_bytes(ascconv(main).encode())
    return path


def _toml_value(value: Any) -> str:
    return json.dumps(value) if isinstance(value, str) else repr(value)


def _write_profile(path: Path, name: str, asc: str, opts: dict, rasters: dict) -> None:
    lines = ["format = 1", f"name = {json.dumps(name)}", f"asc = {json.dumps(asc)}", ""]
    lines += ["[opts]", *(f"{k} = {_toml_value(v)}" for k, v in opts.items()), ""]
    lines += ["[rasters]", *(f"{k} = {_toml_value(v)}" for k, v in rasters.items()), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def _synthetic_builders() -> dict:
    """Each public function of `tests/synthetic.py` that returns a sequence, with the
    variants of its arguments. Raises when a new such function has no entry here."""
    import pypulseq as pp

    sys.path.insert(0, str(REPO / "tests"))
    import synthetic

    builders = {
        "spin_echo_before": lambda: synthetic.spin_echo_sequence("before"),
        "spin_echo_after": lambda: synthetic.spin_echo_sequence("after"),
        "gre": synthetic.gre_sequence,
        "empty": synthetic.empty_sequence,
        "arbitrary_gradient": synthetic.arbitrary_gradient_sequence,
        "border": synthetic.border_sequence,
    }
    covered = {"spin_echo_sequence", "gre_sequence"} | {
        f"{n}_sequence" for n in ("empty", "arbitrary_gradient", "border")
    }
    found = {
        name
        for name, fn in vars(synthetic).items()
        if callable(fn)
        and getattr(fn, "__module__", None) == "synthetic"
        and not name.startswith("_")
        and getattr(fn, "__annotations__", {}).get("return") is pp.Sequence
    }
    if found != covered:
        raise RuntimeError(f"tests/synthetic.py changed: builders {sorted(found ^ covered)}")
    return builders


def prepare(args: argparse.Namespace) -> None:
    import pypulseq as pp

    from pulseq_checks.profile import RASTER_OPTS

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if REPO in out.resolve().parents or out.resolve() == REPO:
        raise SystemExit("OUT_DIR must be outside the repository")

    sys.path.insert(0, str(REPO / "tests"))
    import scale_sequences
    import synthetic

    builders = _synthetic_builders()
    builders["repeating_1000"] = lambda: scale_sequences.build_repeating(1000)
    builders["worst_1000"] = lambda: scale_sequences.build_worst(1000)
    wanted = args.sequences.split(",") if args.sequences else None
    if wanted:
        unknown = set(wanted) - set(builders) - {"exvivo"}
        if unknown:
            raise SystemExit(f"unknown sequences: {sorted(unknown)}")

    sequences = []
    for name, build in builders.items():
        if wanted and name not in wanted:
            continue
        path = out / f"{name}.seq"
        start = time.perf_counter()
        build().write(str(path))
        print(f"wrote {path.name} ({time.perf_counter() - start:.1f} s)")
        sequences.append({"name": name, "path": str(path), "kind": "synthetic"})
    if args.exvivo and (not wanted or "exvivo" in wanted):
        source = Path(args.exvivo).resolve()
        if not source.is_file():
            raise SystemExit(f"no ex-vivo file: {source}")
        link = out / "exvivo.seq"
        link.unlink(missing_ok=True)
        link.symlink_to(source)
        sequences.append({"name": "exvivo", "path": str(link), "kind": "exvivo"})

    # The Opts of tests/synthetic.py's SYSTEM (plan task 7.2), and the pypulseq default rasters.
    system = synthetic.SYSTEM
    opts = {
        "max_grad": 28,
        "grad_unit": "mT/m",
        "max_slew": 150,
        "slew_unit": "T/m/s",
        "rf_dead_time": 100e-6,
        "rf_ringdown_time": 20e-6,
        "adc_dead_time": 10e-6,
    }
    if (system.rf_dead_time, system.rf_ringdown_time, system.adc_dead_time) != (
        opts["rf_dead_time"],
        opts["rf_ringdown_time"],
        opts["adc_dead_time"],
    ):
        raise RuntimeError("tests/synthetic.py SYSTEM changed: update the opts of the script")
    defaults = pp.Opts()
    rasters = {name: getattr(defaults, keyword) for name, keyword in RASTER_OPTS.items()}

    asc_one = _write_gradient_asc(out, 1.0, split=False)
    asc_fail = _write_gradient_asc(out, PNS_FAIL_SCALE, split=True)
    grad_fail_opts = {
        **opts,
        "max_grad": GRADIENT_FAIL_MAX_GRAD_MT_PER_M,
        "max_slew": GRADIENT_FAIL_MAX_SLEW_T_PER_M_PER_S,
    }
    sets = [
        ("synthetic", opts, asc_one, 1.0, "SYSTEM of tests/synthetic.py; SAFE example hardware"),
        (
            "gradient-fail",
            grad_fail_opts,
            asc_one,
            1.0,
            "max_grad and max_slew below every sequence with gradients",
        ),
        (
            "pns-fail",
            opts,
            asc_fail,
            PNS_FAIL_SCALE,
            f"SAFE example hardware with limit_scale {PNS_FAIL_SCALE} (split layout)",
        ),
        (
            "timing-fail",
            {
                **opts,
                "rf_dead_time": TIMING_FAIL_RF_DEAD_TIME_S,
                "rf_ringdown_time": TIMING_FAIL_RF_RINGDOWN_TIME_S,
            },
            asc_one,
            1.0,
            "RF dead time and RF ringdown longer than the synthetic sequences use",
        ),
    ]
    wanted_sets = args.limit_sets.split(",") if args.limit_sets else None
    limit_sets = []
    for name, set_opts, asc, scale, why in sets:
        if wanted_sets and name not in wanted_sets:
            continue
        profile = out / f"{name}.toml"
        _write_profile(profile, name, asc.name, set_opts, rasters)
        keywords = dict(set_opts)
        keywords.update({RASTER_OPTS[n]: v for n, v in rasters.items()})
        limit_sets.append(
            {
                "name": name,
                "profile": str(profile),
                "asc": str(asc),
                "opts_keywords": keywords,
                "max_grad_mt_per_m": float(set_opts["max_grad"]),
                "max_slew_t_per_m_per_s": float(set_opts["max_slew"]),
                "pns_limit_scale": scale,
                "description": why,
            }
        )
    manifest = {"sequences": sequences, "limit_sets": limit_sets}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"{len(sequences)} sequences x {len(limit_sets)} limit sets: {out / 'manifest.json'}")


# ---- cards (devShell of the pulseq-reports reference worktree) ----


def _cards_pair(seq_path: str, limit_set: dict) -> dict:
    import pypulseq as pp
    from pulseq_reports.cards.gradient_limits import _excesses, gradient_limits_card
    from pulseq_reports.cards.pns import pns_card
    from pulseq_reports.cards.timing import _timing_errors, timing_card
    from pulseq_reports.grad_limits import HardwareLimits, gradient_limits
    from pulseq_reports.pns import pns_prediction

    def read():
        seq = pp.Sequence(system=pp.Opts(**limit_set["opts_keywords"]))
        seq.read(seq_path)
        return seq

    def timing(seq):
        card = timing_card(seq)
        return {"passed": card.checks[0].passed, "errors": _error_rows(_timing_errors(seq))}

    def gradient(seq):
        limits = HardwareLimits(
            max_grad_mt_per_m=limit_set["max_grad_mt_per_m"],
            max_slew_t_per_m_per_s=limit_set["max_slew_t_per_m_per_s"],
            label=limit_set["name"],
        )
        card = gradient_limits_card(seq, limits=limits, check_norms=True)
        # The numbers of the card's table (the card calls gradient_limits the same way), and
        # the card's own excess messages, which say which quantity is above its limit.
        measured = gradient_limits(seq, window=None, limits=limits)
        messages = _excesses(measured, "the whole file", True)
        return {
            "passed": card.checks[0].passed,
            "message": card.checks[0].message,
            "excesses": messages,
            "amplitude_axis_passed": not any(
                m.startswith(("Gx peak", "Gy peak", "Gz peak")) for m in messages
            ),
            "slew_axis_passed": not any(
                m.startswith(("Gx slew", "Gy slew", "Gz slew")) for m in messages
            ),
            "norm_passed": not any(m.startswith("|G| peak") for m in messages),
            "reason": measured.reason,
            "peak_mt_per_m": {a: measured.axes[a].peak_mt_per_m for a in AXES},
            "slew_t_per_m_per_s": {a: measured.axes[a].max_slew_t_per_m_per_s for a in AXES},
            "vector_peak_mt_per_m": measured.vector_peak_mt_per_m,
        }

    def pns(seq):
        card = pns_card(seq, gradient_asc=limit_set["asc"])
        prediction = pns_prediction(seq, gradient_asc=limit_set["asc"])
        return {
            "passed": card.checks[0].passed,
            "reason": prediction.reason,
            "peak_percent": 100 * prediction.peak,
            "axis_peaks_percent": {a: 100 * v for a, v in prediction.axis_peaks.items()},
        }

    row: dict = {}
    seq = _attempt(read)
    if "raised" in seq:
        return {"read": seq, "timing": seq, "gradient": seq, "pns": seq}
    row["read"] = {"value": "ok"}
    # Each card gets its own copy of the sequence, so a block cache of one does not reach
    # the others (the cards of the reference do not depend on it; this is only care).
    for name, fn in (("timing", timing), ("gradient", gradient), ("pns", pns)):
        row[name] = _attempt(lambda fn=fn: fn(read()))
    return row


def _error_rows(errors: list[dict]) -> list[dict]:
    """The timing errors as comparable data: the block ID, the event, the field, the error
    type and the value of each."""
    return [
        {
            "block": e.get("block"),
            "event": e.get("event"),
            "field": e.get("field"),
            "error_type": e.get("error_type", e.get("message")),
            "value": e.get("value"),
        }
        for e in errors
    ]


def cards(args: argparse.Namespace) -> None:
    out = Path(args.out_dir)
    manifest = _manifest(out)
    rows = []
    for sequence in manifest["sequences"]:
        for limit_set in manifest["limit_sets"]:
            start = time.perf_counter()
            row = _cards_pair(sequence["path"], limit_set)
            row.update(sequence=sequence["name"], limit_set=limit_set["name"])
            rows.append(row)
            print(
                f"cards {sequence['name']} x {limit_set['name']}: {time.perf_counter() - start:.1f} s"
            )
    _dump(out / "cards.jsonl", rows)


# ---- checks (devShell of this repository) ----


def _checks_pair(seq_path: str, limit_set: dict) -> dict:
    import pypulseq as pp
    from pulseq_analysis.grad_limits import gradient_limits

    from pulseq_checks.profile import read_profile
    from pulseq_checks.run import run_checks

    profile = read_profile(limit_set["profile"])
    matrix = _attempt(lambda: run_checks(seq_path, [profile]))
    if "raised" in matrix:
        return {"run": matrix}
    results = {}
    for r in matrix["value"].results:
        results[r.check_id] = {
            "state": r.state.value,
            "value": r.value,
            "limit": r.limit,
            "unit": r.unit,
            "reason": r.reason,
            "location": None if r.location is None else [r.location.block, r.location.time_s],
        }

    def read():
        seq = pp.Sequence(system=profile.make_opts())
        seq.read(seq_path)
        return seq

    def timing_errors():
        _, errors = read().check_timing()
        return _error_rows([dict(vars(e)) for e in errors])

    def axes():
        # gradient_limits gives Hz/m and Hz/m/s, with no gamma. Convert with the magnitude of
        # the gamma of the profile, as the checks do.
        measured = gradient_limits(read())
        g = abs(profile.make_opts().gamma)
        return {
            "reason": measured.reason,
            "peak_mt_per_m": {a: measured.axes[a].peak_hz_per_m / g * 1e3 for a in AXES},
            "slew_t_per_m_per_s": {a: measured.axes[a].max_slew_hz_per_m_per_s / g for a in AXES},
            "vector_peak_mt_per_m": measured.vector_peak_hz_per_m / g * 1e3,
        }

    return {
        "run": {"value": "ok"},
        "results": results,
        "timing_errors": _attempt(timing_errors),
        "gradient_values": _attempt(axes),
    }


def checks(args: argparse.Namespace) -> None:
    out = Path(args.out_dir)
    manifest = _manifest(out)
    rows = []
    for sequence in manifest["sequences"]:
        for limit_set in manifest["limit_sets"]:
            start = time.perf_counter()
            row = _checks_pair(sequence["path"], limit_set)
            row.update(sequence=sequence["name"], limit_set=limit_set["name"])
            rows.append(row)
            print(
                f"checks {sequence['name']} x {limit_set['name']}: {time.perf_counter() - start:.1f} s"
            )
    _dump(out / "checks.jsonl", rows)


# ---- compare (plain Python) ----


def _close(a: float, b: float) -> bool:
    if a == b:
        return True
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    return abs(a - b) <= REL_TOL * max(abs(a), abs(b))


def _side_verdict(passed: bool) -> str:
    return "pass" if passed else "fail"


def _raised_type(message: str) -> str:
    return message.split(":", 1)[0]


def _new_result(checks_row: dict, check_id: str) -> dict:
    """The result of a check as `{"raised": ...}` for an error, a run error or a state that
    is not pass or fail, else `{"value": result}`."""
    if "raised" in checks_row["run"]:
        return {"raised": checks_row["run"]["raised"]}
    result = checks_row["results"][check_id]
    if result["state"] == "error":
        return {"raised": result["reason"]}
    if result["state"] not in ("pass", "fail"):
        return {"other": f"{result['state']}: {result['reason']}"}
    return {"value": result}


def _compare_raises(card: dict, new: dict, diffs: list[str]) -> bool:
    """True when at least one side raised or is not evaluated (then the pair is decided here):
    both raised with the same exception type is agreement."""
    if "other" in new:
        diffs.append(f"the new check is {new['other']}")
        return True
    if "raised" in card or "raised" in new:
        if "raised" in card and "raised" in new:
            if _raised_type(card["raised"]) != _raised_type(new["raised"]):
                diffs.append(f"both raised, different types: {card['raised']} | {new['raised']}")
        else:
            diffs.append(
                "only one side raised: "
                f"card {card.get('raised', 'no exception')} | check {new.get('raised', 'no exception')}"
            )
        return True
    return False


def _pair(seq: str, limit_set: str, name: str, card: dict, new: dict, compare_fn) -> dict:
    diffs: list[str] = []
    if not _compare_raises(card, new, diffs):
        compare_fn(card["value"], new["value"], diffs)
    return {
        "sequence": seq,
        "limit_set": limit_set,
        "pair": name,
        "match": not diffs,
        "differences": diffs,
        "card": card,
        "check": new,
    }


def _verdict_diff(card_passed: bool, result: dict, diffs: list[str]) -> None:
    if _side_verdict(card_passed) != result["state"]:
        diffs.append(f"verdict: card {_side_verdict(card_passed)} | check {result['state']}")


def _value_diff(label: str, card_value: float, new_value: float, diffs: list[str]) -> None:
    if not _close(card_value, new_value):
        diffs.append(f"{label}: card {card_value!r} | check {new_value!r}")


def _compare_timing(card: dict, new: dict, diffs: list[str]) -> None:
    _verdict_diff(card["passed"], new["result"], diffs)
    errors = new["errors"]
    if "raised" in errors:
        diffs.append(f"the error list of the check raised: {errors['raised']}")
    elif card["errors"] != errors["value"]:
        diffs.append(f"error list: card {card['errors']!r} | check {errors['value']!r}")


_GRADIENT_KINDS = {
    # kind: (card verdict key, card values key, gradient_limits values key)
    "amplitude": ("amplitude_axis_passed", "peak_mt_per_m", "peak_mt_per_m"),
    "slew": ("slew_axis_passed", "slew_t_per_m_per_s", "slew_t_per_m_per_s"),
    "norm": ("norm_passed", None, None),
}


def _compare_gradient(kind: str, card: dict, new: dict, diffs: list[str]) -> None:
    result, own = new["result"], new["values"]
    passed_key, card_key, own_key = _GRADIENT_KINDS[kind]
    _verdict_diff(card[passed_key], result, diffs)
    if card_key is None:
        card_max = card["vector_peak_mt_per_m"]
        _value_diff("|G| peak (check result)", card_max, result["value"], diffs)
        _value_diff("|G| peak (gradient_limits)", card_max, own["vector_peak_mt_per_m"], diffs)
        return
    _value_diff(
        "largest axis value (check result)", max(card[card_key].values()), result["value"], diffs
    )
    for axis in AXES:
        _value_diff(
            f"axis {axis} (gradient_limits)", card[card_key][axis], own[own_key][axis], diffs
        )


def _compare_pns(card: dict, result: dict, diffs: list[str]) -> None:
    _verdict_diff(card["passed"], result, diffs)
    if card["peak_percent"] != result["value"]:
        diffs.append(
            f"peak in percent (exact): card {card['peak_percent']!r} | check {result['value']!r}"
        )


def _coverage_notes(key: tuple, card: dict, notes: list[str]) -> None:
    """Notes for a limit set that does not do its job: a sequence with gradients that passes
    in `gradient-fail` or in `pns-fail`, or a sequence that passes the timing check in
    `timing-fail` (the comparison then has no failing case for it)."""
    sequence, limit_set = key
    gradient, pns, timing = card["gradient"], card["pns"], card["timing"]
    if limit_set == "timing-fail" and "value" in timing and timing["value"]["passed"]:
        notes.append(f"{sequence} x {limit_set}: the timing check passes (card)")
    if limit_set == "gradient-fail" and "value" in gradient and gradient["value"]["reason"] is None:
        value = gradient["value"]
        for label, passed in (
            ("amplitude", value["amplitude_axis_passed"]),
            ("slew", value["slew_axis_passed"]),
            ("|G|", value["norm_passed"]),
        ):
            if passed and max(value["peak_mt_per_m"].values()) > 0:
                notes.append(f"{sequence} x {limit_set}: the {label} check passes (card)")
    if (
        limit_set == "pns-fail"
        and "value" in pns
        and pns["value"]["reason"] is None
        and pns["value"]["passed"]
    ):
        notes.append(f"{sequence} x {limit_set}: the PNS check passes (card)")


def compare(args: argparse.Namespace) -> int:
    out = Path(args.out_dir)
    manifest = _manifest(out)
    card_rows = {(r["sequence"], r["limit_set"]): r for r in _load_lines(out / "cards.jsonl")}
    check_rows = {(r["sequence"], r["limit_set"]): r for r in _load_lines(out / "checks.jsonl")}
    rows: list[dict] = []
    notes: list[str] = []
    for sequence in manifest["sequences"]:
        for limit_set in manifest["limit_sets"]:
            key = (sequence["name"], limit_set["name"])
            c, n = card_rows[key], check_rows[key]
            new = {i: _new_result(n, i) for i in _IDS}
            if "raised" in n["run"]:
                errors = values = n["run"]
            else:
                errors, values = n["timing_errors"], n["gradient_values"]

            def add(name, card, new_side, fn, key=key):
                rows.append(_pair(*key, name, card, new_side, fn))

            timing = new["timing.pypulseq"]
            add(
                "timing.pypulseq",
                c["timing"],
                {"value": {"result": timing["value"], "errors": errors}}
                if "value" in timing
                else timing,
                _compare_timing,
            )
            for check_id, kind in (
                ("gradient.amplitude.axis", "amplitude"),
                ("gradient.slew.axis", "slew"),
                ("gradient.amplitude.any-orientation", "norm"),
            ):
                res = new[check_id]
                if "value" in res and "raised" in values:
                    res = {"raised": values["raised"]}
                add(
                    check_id,
                    c["gradient"],
                    {"value": {"result": res["value"], "values": values["value"]}}
                    if "value" in res
                    else res,
                    lambda cv, nv, diffs, kind=kind: _compare_gradient(kind, cv, nv, diffs),
                )
            pns = new["pns.safe"]
            add(
                "pns.safe",
                c["pns"],
                pns,
                _compare_pns,
            )
            _coverage_notes(key, c, notes)
    _dump(out / "comparison.jsonl", rows)
    return _report(rows, notes)


_IDS = (
    "timing.pypulseq",
    "gradient.amplitude.axis",
    "gradient.slew.axis",
    "gradient.amplitude.any-orientation",
    "pns.safe",
)


def _report(rows: list[dict], notes: list[str]) -> int:
    """Print one line for each pair (a table), each difference with both sides, the notes and
    the summary. The status is 1 when any pair differs."""
    width = max(len(r["sequence"]) for r in rows)
    sets = max(len(r["limit_set"]) for r in rows)
    print(f"{'sequence':<{width}}  {'limit set':<{sets}}  {'pair':<36}  result")
    for r in rows:
        card, new = r["card"], r["check"]
        if "value" in card and "value" in new:
            how = "same"
        else:
            how = "both raised" if "raised" in card and "raised" in new else "raised/other"
        result = f"ok ({how})" if r["match"] else "DIFFERENT"
        print(f"{r['sequence']:<{width}}  {r['limit_set']:<{sets}}  {r['pair']:<36}  {result}")
    different = [r for r in rows if not r["match"]]
    for r in different:
        print(f"\nDIFFERENCE {r['sequence']} x {r['limit_set']} x {r['pair']}")
        for d in r["differences"]:
            print(f"  {d}")
    if notes:
        print("\nnotes (a limit set that does not fail a sequence with gradients):")
        for note in notes:
            print(f"  {note}")
    raised = sum(1 for r in rows if "raised" in r["card"] or "raised" in r["check"])
    print(
        f"\n{len(rows)} pairs, {len(rows) - len(different)} equal, {len(different)} different, "
        f"{raised} with an exception on a side"
    )
    return 1 if different else 0


# ---- run and main ----


def run(args: argparse.Namespace) -> int:
    script = str(Path(__file__).resolve())
    out = str(Path(args.out_dir))
    prepare_args = []
    for flag, value in (
        ("--exvivo", args.exvivo),
        ("--sequences", args.sequences),
        ("--limit-sets", args.limit_sets),
    ):
        if value:
            prepare_args += [flag, value]
    reference = Path(args.reference).resolve()
    steps = [
        ("prepare", [sys.executable, script, "prepare", out, *prepare_args], REPO),
        (
            "cards",
            ["nix", "develop", "--command", "uv", "run", "python", script, "cards", out],
            reference,
        ),
        ("checks", [sys.executable, script, "checks", out], REPO),
    ]
    for name, command, cwd in steps:
        start = time.perf_counter()
        status = subprocess.run(command, cwd=cwd, check=False).returncode
        print(f"== {name}: {time.perf_counter() - start:.1f} s, status {status}")
        if status != 0:
            return status
    return compare(args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "cards", "checks", "compare", "run"):
        p = sub.add_parser(name)
        p.add_argument("out_dir", help="a scratch directory outside the repository")
        if name in ("prepare", "run"):
            p.add_argument("--exvivo", help="the ex-vivo .seq file (a symlink, never a copy)")
            p.add_argument("--sequences", help="comma-separated names (default: all)")
            p.add_argument("--limit-sets", help="comma-separated names (default: all three)")
        if name == "run":
            p.add_argument("--reference", required=True, help="the pulseq-reports worktree")
    args = parser.parse_args()
    start = time.perf_counter()
    status = {
        "prepare": prepare,
        "cards": cards,
        "checks": checks,
        "compare": compare,
        "run": run,
    }[args.command](args)
    print(f"{args.command}: {time.perf_counter() - start:.1f} s")
    return status or 0


if __name__ == "__main__":
    sys.exit(main())
