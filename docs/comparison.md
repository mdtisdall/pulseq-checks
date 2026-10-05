# The new checks against the pulseq-reports cards

This is the comparison of phase 7 of `docs/plans/pulseq-checks-v1.md` (design
step 2.4, decision R7). It compares the check rules of this package with the
checks of the pulseq-reports cards, before pulseq-reports removes those checks
(its step 1).

Result: **the new checks and the cards agree on all 180 pairs** (9 sequences, 4
limit sets, 5 pairs of a check and a card). One difference of rule cannot show
in this set; the user accepted it (see [An accepted difference](#an-accepted-difference)).

This is a record of a comparison that was done one time, in #16. It was the
gate for the step 1 of pulseq-reports, which removed the checks of its cards
(pulseq-reports #111) and now uses this package (pulseq-reports #112). The
script `scripts/compare_with_cards.py` is removed from this repository: the
reference worktree that it needs does not exist now, and no later work needs
the comparison. The last version of the script is in the commit `778999b`
(`git show 778999b:scripts/compare_with_cards.py`). The numbers below are from
the run of #16.

## The reference

- pulseq-reports at commit `475a1eb` ("docs: the pulseq-checks order of work
  and its reference document (#104)"), in a detached worktree
  (`.worktrees/cards-reference` of the pulseq-reports checkout), synced with
  `uv sync --frozen`. Plan section 3.6.
- This package at the commit of this change (phase 5 merged, `f320963`).
- Both use pypulseq 1.5.0.post1 from the fork commit `a74ab06`.

## The set

**Sequences** (9):

| Name | Source |
|---|---|
| `spin_echo_before`, `spin_echo_after`, `gre`, `empty`, `arbitrary_gradient`, `border` | the builders of `tests/synthetic.py` |
| `repeating_1000`, `worst_1000` | `build_repeating(1000)` and `build_worst(1000)` of `tests/scale_sequences.py` (5000 blocks each) |
| `exvivo` | `exvivo_gre_seg_0.seq` (plan section 2.1; not in this repository) |

**Limit sets** (4). Each is a target profile for the new checks, and the same
values for the cards: the same `pp.Opts` keywords for the read of the `.seq`
file (plan section 2.3, fact 5), `HardwareLimits` in mT/m and T/m/s for the
gradient limits card, and the same `.asc` file for the PNS card.

| Name | Values | Purpose |
|---|---|---|
| `synthetic` | 28 mT/m, 150 T/m/s, RF dead time 100 µs, RF ringdown 20 µs, ADC dead time 10 µs (the `SYSTEM` of `tests/synthetic.py`), the pypulseq default rasters; the SAFE example hardware (`.asc`, `limit_scale` 1) | the sequences pass |
| `gradient-fail` | as `synthetic`, with 1 mT/m and 2 T/m/s | each gradient check fails on each sequence with gradients (the smallest peak is 2.8 mT/m, the smallest peak slew 7 T/m/s) |
| `pns-fail` | as `synthetic`, with the SAFE example hardware at `limit_scale` 0.01 (split `.asc` layout with `$INCLUDE`) | the PNS check fails on each sequence with gradients (the PNS total is linear in 1 / limit) |
| `timing-fail` | as `synthetic`, with RF dead time 200 µs and RF ringdown 30 µs | the timing check fails on each sequence with an RF pulse |

The plan gives the first three sets. The `timing-fail` set is added so that
the timing error lists are compared on failures, not only on empty lists.

**Pairs** (plan task 7.2):

| New check | Card | Expected |
|---|---|---|
| `timing.pypulseq` | timing card | The same pass or fail, and the same error list (block, event, field, error type, value) |
| `gradient.amplitude.axis`, `gradient.slew.axis` | gradient limits card, whole file | The same pass or fail; the same values of each axis to 1e-12 relative |
| `gradient.amplitude.any-orientation` | gradient limits card, `check_norms=True`, its \|G\| part | The same pass or fail and value, to 1e-12 relative |
| `pns.safe` | PNS card, the same `.asc` | The same peak (exact) and the same pass or fail |
| `timing.rasters` | none | Not compared |

The card side takes the per-part verdicts of the gradient limits card from its
private `_excesses` and the timing error list from the private
`_timing_errors` of the timing card at `475a1eb`, and the unrounded PNS peak
from `pns.pns_prediction`.

## The commands

These are the commands of the run of #16. The script is not in the repository
now (see the top of this document). In this repository at `778999b`, with the
reference worktree (see above):

```bash
nix develop --command uv run python scripts/compare_with_cards.py run OUT_DIR \
  --reference /path/to/pulseq-reports/.worktrees/cards-reference \
  --exvivo /path/to/exvivo_gre_seg_0.seq
```

`run` does the four steps of the script: `prepare` (the `.seq` files, the
profiles and the synthetic `.asc` files, in this repository's environment),
`cards` (in the reference worktree's environment, through `nix develop` there),
`checks` (here) and `compare`. `OUT_DIR` must be outside the repository; the
ex-vivo file is linked, not copied. `compare` exits 1 when a pair differs. The
run took about 55 s.

## The results

180 pairs, 180 equal, 0 different, 0 with an exception on a side. The states
of the new checks (the cards give the same verdicts):

| Check | `synthetic` | `gradient-fail` | `pns-fail` | `timing-fail` |
|---|---|---|---|---|
| `timing.pypulseq` | 9 pass | 9 pass | 9 pass | 6 fail, 3 pass |
| `gradient.amplitude.axis` | 9 pass | 8 fail, 1 pass | 9 pass | 9 pass |
| `gradient.slew.axis` | 9 pass | 8 fail, 1 pass | 9 pass | 9 pass |
| `gradient.amplitude.any-orientation` | 9 pass | 8 fail, 1 pass | 9 pass | 9 pass |
| `pns.safe` | 9 pass | 9 pass | 8 fail, 1 pass | 9 pass |

- The one pass in `gradient-fail` and `pns-fail` is `empty`, which has no
  gradients (value 0 on both sides).
- The three passes in `timing-fail` are the sequences without an RF pulse
  (`empty`, `arbitrary_gradient`, `border`). The six that fail have 6 to
  13 872 timing errors each, and both sides give the same list.
- The values: the ex-vivo file with the `synthetic` set has 15.47 mT/m, 9.98
  T/m/s and a PNS peak of 13.78 % on both sides.

## An accepted difference

The PNS card fails when its percent, **rounded to 0.01**, is at or above 100,
so from a peak of 99.995 %. `pns.safe` fails when the peak is at or above
100 % (the rule of pypulseq, `pns_norm < 1`, decision 5 of the plan). The two
differ for a peak in [99.995 %, 100 %). No sequence of the set is near that
range, so the comparison cannot show it. The user accepted this difference on
2026-09-30: `pns.safe` keeps the rule of pypulseq.

## Other notes

- The gradient limits are given to the card in mT/m and T/m/s; the new checks
  convert them from the `pp.Opts` values of the profile with its gamma. Only a
  verdict at the limit could depend on this, and the tolerance of 1e-9 of the
  gradient checks covers the rounding.
- After this comparison, pulseq-reports can start its step 1 (decision R7):
  remove the checks of its cards and use this package.
