"""Peripheral nerve stimulation (PNS) prediction for a Pulseq sequence with the SAFE model.

`pns_prediction` gives the PNS summary (the peak, the peak time and the axis peaks) of a
sequence: the reason, hardware and asc-file fields, and the summary fields of
`pns_levels.pns_levels`, cached one time for each (sequence object, gradient .asc file) by
`pns_levels_for`. `pns_levels_for` is the one place that runs the SAFE model
(`pns_levels.pns_levels`, which uses the pinned pypulseq fork's chunk function), so a
page that has both the PNS summary card and the diagram's PNS lane for one sequence
computes it once (`docs/plans/diagram-lanes.md`, section 4.6).

The model needs the scanner's gradient hardware parameters, which Siemens keeps in the
gradient system's .asc file (MP_GPA_*.asc, or MP_GradSys_*.asc on newer software). The
files are confidential, so this library does not include any. Without them, the
prediction uses pypulseq's example hardware, which is not a real scanner.
"""

import math
import weakref
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pypulseq as pp

from .pns_levels import PnsLevels, pns_levels
from .seq_index import sequence_index


@dataclass(frozen=True)
class PnsPrediction:
    """The PNS summary of one sequence (`pns_prediction`). Summary-only: a caller that
    wants the samples of a short sequence can call `seq.calculate_pns` directly (the
    pinned fork's memory is near the size of its result), or use `pns_levels_for` for
    the stored level (`docs/plans/diagram-lanes.md`, section 7, question 1)."""

    reason: str | None  # why there is no prediction, or None
    hardware: str  # the hardware name in the .asc file, or asc.EXAMPLE_HARDWARE
    asc_file: str | None  # the .asc file name, or None for the example hardware
    peak: float  # the largest total (root-sum-of-squares of the axes); 1 is the limit
    peak_time_s: float | None  # the first sample within pns_levels.PEAK_TOLERANCE of the peak
    axis_peaks: dict[str, float] = field(default_factory=dict)  # "x", "y", "z"


# For each sequence object: the number of blocks, the last block id (the rule of
# `seq_index.sequence_index`) and one `PnsLevels` for each hardware, keyed by `None` (the
# example hardware) or the resolved path of the gradient .asc file.
_Kept = tuple[int, int, dict[str | None, PnsLevels]]
_LEVELS_CACHE: "weakref.WeakKeyDictionary[pp.Sequence, _Kept]" = weakref.WeakKeyDictionary()


def pns_levels_for(seq: pp.Sequence, *, gradient_asc: str | Path | None = None) -> PnsLevels:
    """The `PnsLevels` of `seq` with the hardware of the gradient .asc file `gradient_asc`
    (`pns_levels.pns_levels`), or pypulseq's example hardware when it is None.

    The result is kept for the sequence object and the hardware, so that the PNS summary
    card (`cards.pns.pns_card`) and the diagram's PNS lane (`cards.diagram.diagram_card`)
    compute it one time for each hardware of one sequence
    (`docs/plans/diagram-lanes.md`, section 4.6). A relative and an absolute spelling of
    one file are one hardware. The kept results are built again when the number of blocks
    or the last block id changed, for example after `add_block` (the rule of
    `seq_index.sequence_index`).
    """
    block_events = seq.block_events
    num_blocks = len(block_events)
    last_id = int(next(reversed(block_events))) if num_blocks else 0
    key = None if gradient_asc is None else str(Path(gradient_asc).resolve())

    kept = _LEVELS_CACHE.get(seq)
    if kept is None or kept[0] != num_blocks or kept[1] != last_id:
        kept = (num_blocks, last_id, {})
        _LEVELS_CACHE[seq] = kept
    by_hardware = kept[2]
    if key not in by_hardware:
        by_hardware[key] = pns_levels(seq, gradient_asc=gradient_asc)
    return by_hardware[key]


def pns_prediction(seq: pp.Sequence, *, gradient_asc: str | Path | None = None) -> PnsPrediction:
    """The SAFE PNS summary for `seq`, with the hardware in the .asc file `gradient_asc`, or
    pypulseq's example hardware when it is None. Built from `pns_levels_for`, so a page
    that also draws the PNS lane of the diagram for `seq` (`cards.diagram.diagram_card`)
    does not run the SAFE model twice."""
    levels = pns_levels_for(seq, gradient_asc=gradient_asc)
    return PnsPrediction(
        reason=levels.reason,
        hardware=levels.hardware,
        asc_file=levels.asc_file,
        peak=levels.peak,
        peak_time_s=levels.peak_time_s,
        axis_peaks=dict(levels.axis_peaks),
    )


def peak_tr_window(seq: pp.Sequence, peak_time_s: float | None) -> tuple[float, float] | None:
    """Start and end, in seconds, of the TR that holds `peak_time_s`, counted from the
    sequence start in steps of the TR definition. None without a TR definition, or when
    the sequence is not longer than one TR.

    `peak_time_s` is in seconds, for example `PnsPrediction.peak_time_s`. A caller adds
    this window to the diagram card's windows for a "TR with the highest PNS" button
    (`docs/plans/diagram-lanes.md`, section 4.6), without a dependency on the PNS card."""
    tr = seq.definitions.get("TR")
    if tr is None or peak_time_s is None:
        return None
    tr = float(np.atleast_1d(tr)[0])
    duration = sequence_index(seq).end_s
    if tr <= 0 or duration <= tr * (1 + 1e-9):
        return None
    start = math.floor(peak_time_s / tr + 1e-9) * tr
    return start, min(start + tr, duration)
