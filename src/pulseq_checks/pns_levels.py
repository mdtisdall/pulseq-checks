"""The PNS total of a whole sequence as a stored level: the minimum and the maximum in
fixed time bins, and the summary (section 4.1, item 2, and section 4.2 of
docs/plans/diagram-lanes.md).

`pns_levels` samples the gradients block by block (`GradientSampler.block_samples`),
runs the SAFE model of the pinned pypulseq fork over them in chunks
(`_safe_gwf_to_pns_chunk`, which carries the filter state from one chunk to the next),
and keeps only the stored level and the summary. Its memory does not grow with the
duration of the sequence, except for the stored level (at most `MAX_BINS` bins).

The browser's `PnsLanes` (assets/pns_lanes.js) computes the same samples for its exact
views, so the stored level and the exact views agree to float rounding.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pypulseq as pp

# The chunk function of the pypulseq fork (TODO.md, "Move from the pypulseq fork to a
# pypulseq release"). It is private in the
# fork, so that the upstream proposal adds no public name: decision 11 of
# docs/plans/diagram-lanes.md. This is the only module that imports it.
from pypulseq.utils.safe_pns_prediction import _safe_gwf_to_pns_chunk, safe_example_hw
from pypulseq.utils.siemens.asc_to_hw import asc_to_hw

from .asc import EXAMPLE_HARDWARE, hardware_name, read_gradient_asc
from .extensions import refuse_rotations
from .sampling import GradientSampler, raster_block_lengths
from .seq_index import sequence_index

# The longest exact view of the browser (`PnsLanes.EXACT_MAX_S`), in s. The finest stored
# bin is at most half a display bin at this view (section 4.2, decision 13). Keep the two
# equal.
EXACT_MAX_S = 10.0
# The number of display bins of the diagram chart: `PLOT_W` of `assets/lane_chart.js`
# (960 - 128 - 20). Keep the two equal.
DISPLAY_BINS = 812
# The largest number of stored bins for one file (section 4.2).
MAX_BINS = 2_000_000
# The fork's chunk size (samples): smaller chunks add time, larger ones add memory
# (section 2.6, item 4). A chunk of `pns_levels` is the whole number of bins nearest
# above it.
CHUNK_SAMPLES = 30_000
NO_GRADIENTS = "no gradients"
# Samples within this fraction of the peak count as the peak. Identical TRs differ only by
# rounding, so the peak time is in the first of them.
PEAK_TOLERANCE = 1e-6


@dataclass(frozen=True)
class PnsLevels:
    reason: str | None  # why there is no prediction (NO_GRADIENTS), or None
    hardware: str  # the hardware name in the .asc file, or asc.EXAMPLE_HARDWARE
    asc_file: str | None  # the .asc file name, or None for the example hardware
    hw: dict[str, dict[str, float]]  # "x", "y", "z": tau1, tau2, tau3, a1, a2, a3,
    # stim_limit, g_scale, as pypulseq's hardware namespace has them
    dt_s: float  # the gradient raster
    num_samples: int  # the number of samples of the whole sequence
    bin_samples: int  # samples in each stored bin (section 4.2)
    level_min: np.ndarray  # float32, one for each bin: the minimum of the total
    level_max: np.ndarray  # float32, one for each bin: the maximum of the total
    peak: float  # the largest total; 1 is the stimulation limit
    peak_time_s: float | None  # the first sample time within PEAK_TOLERANCE of the peak
    axis_peaks: dict[str, float]  # "x", "y", "z": the largest value of each axis
    on_raster: bool  # every block is a whole number of samples (`raster_block_lengths`)


def bin_samples_for(num_samples: int, dt: float) -> int:
    """`max(floor(EXACT_MAX_S / (2 * DISPLAY_BINS) / dt), ceil(num_samples / MAX_BINS))`,
    and at least 1 (section 4.2). 615 at the 10 us raster for a file of up to
    1,230,000,000 samples."""
    finest = math.floor(EXACT_MAX_S / (2 * DISPLAY_BINS) / dt)
    coarsest_for_size = math.ceil(num_samples / MAX_BINS)
    return max(finest, coarsest_for_size, 1)


def pns_levels(seq: pp.Sequence, *, gradient_asc: str | Path | None = None) -> PnsLevels:
    """The stored level and the summary of the SAFE PNS total of `seq`, with the hardware
    of the gradient .asc file `gradient_asc`, or pypulseq's example hardware when it is None
    (as `pns.pns_prediction` chooses them, with `asc.read_gradient_asc`,
    `asc.hardware_name` and `asc.EXAMPLE_HARDWARE`).

    The model is `calc_pns` of the pinned fork, on other samples:

    1. `dt = seq.grad_raster_time`. The samples are `GradientSampler.block_samples` of
       each axis (Hz/m), divided by `seq.system.gamma` (T/m), as `calc_pns` divides.
       When a block is not on the raster (`on_raster` False), the samples are
       `GradientSampler.sample` at the file times `(k + 0.5) * dt`, as `calc_pns`
       samples, with `k = 0 .. ceil((end - 1e-10) / dt) - 1` and `end` the end of the
       last block (`calc_pns` stops at the last gradient point instead; the samples
       after it are the decay of the filters).
    2. The samples go through `_safe_gwf_to_pns_chunk` in chunks of
       `bin_samples * ceil(CHUNK_SAMPLES / bin_samples)` samples (the whole number of
       bins nearest at or above `CHUNK_SAMPLES`), with `state=None` for the first chunk
       and the returned state after.
    3. The axis values are `0.01 *` the returned percent, and the total of a sample is
       `sqrt(x^2 + y^2 + z^2)` of them, with the numpy operations of `calc_pns`
       (`np.sqrt((comp ** 2).sum(axis=1))`).
    4. The level: the minimum and the maximum of the total in each bin of
       `bin_samples_for(num_samples, dt)` samples (the last bin can be shorter), cast
       to float32 outward: the minimum rounds down and the maximum rounds up
       (`numpy.nextafter` when the cast value is on the wrong side), so that each
       stored bin holds every total of its samples.
    5. The summary: the peak (float64), the axis peaks, and the peak time: the time
       `(k + 0.5) * dt` of the first sample whose total is at or above
       `peak * (1 - PEAK_TOLERANCE)`, as `PnsPrediction.peak_time_s`. The peak is
       known only at the end, so `pns_levels` keeps the start state of each chunk
       (12 numbers) and the float64 maximum of each chunk, and runs again only the
       first chunk whose maximum reaches the threshold.

    The result does not depend on the chunk size (exact equality). A sequence without
    a gradient event gives `reason=NO_GRADIENTS`, no bins, peak 0 and
    `peak_time_s` None. Memory: the chunk, the longest block, the stored level and a
    few numbers for each chunk.

    Raises NotImplementedError for a sequence with the rotation extension
    (`extensions.refuse_rotations`), as the gradient cards and the functions of
    `rf_profiles.py` do.
    """
    refuse_rotations(seq)
    dt = seq.grad_raster_time

    if gradient_asc is None:
        hw_ns, hardware, asc_file = safe_example_hw(), EXAMPLE_HARDWARE, None
    else:
        asc = read_gradient_asc(gradient_asc)
        hw_ns = asc_to_hw(asc)
        hardware, asc_file = hardware_name(asc), Path(gradient_asc).name
    hw = _hw_to_dict(hw_ns)

    index = sequence_index(seq)
    block_lengths, on_raster = raster_block_lengths(index, dt)

    if not _has_gradients(index):
        empty = np.zeros(0, dtype=np.float32)
        return PnsLevels(
            reason=NO_GRADIENTS,
            hardware=hardware,
            asc_file=asc_file,
            hw=hw,
            dt_s=dt,
            num_samples=0,
            bin_samples=bin_samples_for(0, dt),
            level_min=empty,
            level_max=empty,
            peak=0.0,
            peak_time_s=None,
            axis_peaks=dict.fromkeys(_AXES3, 0.0),
            on_raster=on_raster,
        )

    sampler = GradientSampler(seq, index)
    gamma = seq.system.gamma

    # After `_has_gradients`, `num_samples >= 1`, and each chunk has one sample or more.
    if on_raster:
        cumulative = np.cumsum(block_lengths)
        num_samples = int(cumulative[-1])

        def read_range(s0: int, s1: int) -> np.ndarray:
            return _read_block_range(sampler, dt, gamma, cumulative, s0, s1)
    else:
        # The whole sequence, as the blocks give it, not `seq.get_gradients()`: that
        # builds the gradients of the whole file.
        num_samples = max(math.ceil((index.end_s - 1e-10) / dt), 0)

        def read_range(s0: int, s1: int) -> np.ndarray:
            return _read_sampled_range(sampler, dt, gamma, s0, s1)

    bin_samples = bin_samples_for(num_samples, dt)
    chunk_samples = bin_samples * math.ceil(CHUNK_SAMPLES / bin_samples)

    num_bins = math.ceil(num_samples / bin_samples)
    level_min = np.empty(num_bins, dtype=np.float32)
    level_max = np.empty(num_bins, dtype=np.float32)

    num_chunks = math.ceil(num_samples / chunk_samples)
    state = None
    peak = 0.0
    axis_peak = np.zeros(3, dtype=np.float64)
    # The start state and the float64 maximum of each chunk (item 5): enough to run
    # again only the one chunk that holds the peak, instead of keeping every sample.
    chunk_records: list[tuple[int, object, float]] = []

    bin_cursor = 0
    for chunk_index in range(num_chunks):
        s0 = chunk_index * chunk_samples
        s1 = min(s0 + chunk_samples, num_samples)
        gwf = read_range(s0, s1)
        state_before = state
        total, axis_frac, state = _chunk_total(gwf, dt, hw_ns, state_before)

        axis_peak = np.maximum(axis_peak, axis_frac.max(axis=0))
        chunk_max = float(total.max())
        peak = max(peak, chunk_max)
        chunk_records.append((s0, state_before, chunk_max))

        bin_cursor = _store_bins(level_min, level_max, bin_cursor, total, bin_samples)

    peak_time_s = None
    threshold = peak * (1 - PEAK_TOLERANCE)
    for s0, state_before, chunk_max in chunk_records:
        if chunk_max < threshold:
            continue
        s1 = min(s0 + chunk_samples, num_samples)
        gwf = read_range(s0, s1)
        total, _, _ = _chunk_total(gwf, dt, hw_ns, state_before)
        first = int(np.flatnonzero(total >= threshold)[0])
        peak_time_s = (s0 + first + 0.5) * dt
        break

    return PnsLevels(
        reason=None,
        hardware=hardware,
        asc_file=asc_file,
        hw=hw,
        dt_s=dt,
        num_samples=num_samples,
        bin_samples=bin_samples,
        level_min=level_min,
        level_max=level_max,
        peak=peak,
        peak_time_s=peak_time_s,
        axis_peaks=dict(zip(_AXES3, axis_peak.tolist(), strict=True)),
        on_raster=on_raster,
    )


# ---- Private helpers ----

_AXES3 = ("x", "y", "z")
_GRAD_COLUMNS = ("gx", "gy", "gz")
# The 8 hardware fields of one axis that the dataclass keeps (not `stim_thresh`, which
# `_safe_gwf_to_pns_chunk` does not use).
_HW_FIELDS = ("tau1", "tau2", "tau3", "a1", "a2", "a3", "stim_limit", "g_scale")


def _has_gradients(index) -> bool:
    """Whether `index` (a `SequenceIndex`) has a gradient event on any axis, from its
    `gx`/`gy`/`gz` columns. Cheaper than `seq.get_gradients()`, which builds the
    gradients of the whole file."""
    return bool(index.gx.any() or index.gy.any() or index.gz.any())


def _hw_to_dict(hw_ns) -> dict[str, dict[str, float]]:
    """`hw_ns` (pypulseq's hardware `SimpleNamespace`, with `.x`, `.y`, `.z`) as a plain
    dict of the 8 fields of `_HW_FIELDS` for each axis."""
    return {
        axis: {field: float(getattr(getattr(hw_ns, axis), field)) for field in _HW_FIELDS}
        for axis in _AXES3
    }


def _read_block_range(
    sampler: GradientSampler, dt: float, gamma: float, cumulative: np.ndarray, s0: int, s1: int
) -> np.ndarray:
    """The gwf (T/m, shape `(s1 - s0, 3)`) of the global sample range `[s0, s1)`, from
    `GradientSampler.block_samples` over the block range that covers it (found in
    `cumulative`, the cumulative sample count of each block). Memory is bounded by the
    range plus the longest block that straddles one of its ends."""
    first_block = int(np.searchsorted(cumulative, s0, side="right"))
    stop_block = int(np.searchsorted(cumulative, s1 - 1, side="right")) + 1
    offset = int(cumulative[first_block - 1]) if first_block > 0 else 0
    columns = [sampler.block_samples(axis, first_block, stop_block, dt) for axis in _GRAD_COLUMNS]
    gwf_hz = np.stack(columns, axis=1)[s0 - offset : s1 - offset]
    return gwf_hz / gamma


def _read_sampled_range(
    sampler: GradientSampler, dt: float, gamma: float, s0: int, s1: int
) -> np.ndarray:
    """The gwf (T/m, shape `(s1 - s0, 3)`) of the global sample range `[s0, s1)`, from
    `GradientSampler.sample` at the file times `(k + 0.5) * dt` (the fallback for a
    sequence with a block that is not on the raster)."""
    t = (np.arange(s0, s1, dtype=np.float64) + 0.5) * dt
    columns = [sampler.sample(axis, t) for axis in _GRAD_COLUMNS]
    return np.stack(columns, axis=1) / gamma


def _chunk_total(gwf: np.ndarray, dt: float, hw_ns, state) -> tuple[np.ndarray, np.ndarray, object]:
    """Runs `_safe_gwf_to_pns_chunk` on `gwf` (T/m) and returns the total (float64,
    `sqrt(x^2 + y^2 + z^2)`), the axis fractions (`0.01 *` the returned percent) and the
    state for the next chunk, as `calc_pns` computes them."""
    percent, new_state = _safe_gwf_to_pns_chunk(gwf, dt, hw_ns, state)
    axis_frac = 0.01 * percent
    total = np.sqrt((axis_frac**2).sum(axis=1))
    return total, axis_frac, new_state


def _store_bins(
    level_min: np.ndarray,
    level_max: np.ndarray,
    bin_cursor: int,
    total: np.ndarray,
    bin_samples: int,
) -> int:
    """Stores the minimum and the maximum of `total` (float64) in consecutive bins of
    `bin_samples` samples of `level_min`/`level_max`, starting at `bin_cursor`, cast
    outward to float32 (item 4). Only the last bin of `total` can be shorter than
    `bin_samples`: `pns_levels` builds every chunk except the last as a whole number of
    bins, so no bin crosses a chunk. Returns the new bin cursor."""
    chunk_len = total.shape[0]
    n_full = chunk_len // bin_samples
    if n_full:
        reshaped = total[: n_full * bin_samples].reshape(n_full, bin_samples)
        level_min[bin_cursor : bin_cursor + n_full] = _cast_outward(reshaped.min(axis=1), down=True)
        level_max[bin_cursor : bin_cursor + n_full] = _cast_outward(
            reshaped.max(axis=1), down=False
        )
        bin_cursor += n_full
    remainder = chunk_len - n_full * bin_samples
    if remainder:
        tail = total[n_full * bin_samples :]
        level_min[bin_cursor] = _cast_outward(np.array([tail.min()]), down=True)[0]
        level_max[bin_cursor] = _cast_outward(np.array([tail.max()]), down=False)[0]
        bin_cursor += 1
    return bin_cursor


def _cast_outward(values: np.ndarray, *, down: bool) -> np.ndarray:
    """`values` (float64) cast to float32, nudged with `numpy.nextafter` so the cast
    holds every input value: `down` moves a value that rounded the wrong way toward
    `-inf` (for a minimum), otherwise toward `+inf` (for a maximum)."""
    cast = values.astype(np.float32)
    back = cast.astype(np.float64)
    wrong_side = back > values if down else back < values
    if np.any(wrong_side):
        direction = np.float32(-np.inf) if down else np.float32(np.inf)
        cast = cast.copy()
        cast[wrong_side] = np.nextafter(cast[wrong_side], direction)
    return cast
