import math

import numpy as np
import pypulseq as pp
import pytest
from oracles import grad_limits as oracle
from synthetic import (
    SYSTEM,
    arbitrary_gradient_sequence,
    empty_sequence,
    gre_sequence,
    spin_echo_sequence,
)

from pulseq_checks.grad_limits import GradientLimits, gradient_limits
from pulseq_checks.seq_index import grad_events, sequence_index
from pulseq_checks.seq_utils import GAMMA, gradient_offsets


def test_trapezoid_peak_slew_and_rms_match_hand_computed_values():
    """A single x trapezoid: the peak amplitude, the peak slew and the RMS amplitude
    equal values computed by hand from the trapezoid's own rise time, flat time and
    amplitude."""
    amplitude = 0.5 * SYSTEM.max_grad  # Hz/m
    gx = pp.make_trapezoid(
        channel="x", amplitude=amplitude, rise_time=200e-6, flat_time=1e-3, system=SYSTEM
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    (block_id,) = seq.block_events

    result = gradient_limits(seq)

    peak_mt_per_m = amplitude / GAMMA * 1e3
    slew_t_per_m_per_s = amplitude / gx.rise_time / GAMMA
    # RMS^2 * duration is the integral of amplitude^2 dt: the rising ramp contributes
    # amplitude^2 * rise_time / 3 (the integral of (amplitude * t / rise_time)^2 from 0
    # to rise_time), the falling ramp contributes the same by symmetry, and the flat
    # top contributes amplitude^2 * flat_time.
    duration = sum(seq.block_durations.values())
    energy = 2 * (gx.rise_time * amplitude**2 / 3) + gx.flat_time * amplitude**2
    rms_mt_per_m = math.sqrt(energy / duration) / GAMMA * 1e3

    axis = result.axes["x"]
    assert result.reason is None
    assert axis.peak_mt_per_m == pytest.approx(peak_mt_per_m)
    assert axis.peak_block == block_id
    assert axis.max_slew_t_per_m_per_s == pytest.approx(slew_t_per_m_per_s)
    assert axis.slew_block == block_id
    assert axis.rms_mt_per_m == pytest.approx(rms_mt_per_m)


def test_same_trapezoid_on_x_and_y_gives_vector_peak_root_2_times_axis_peak():
    """The same trapezoid, played on x and on y at the same time: the vector peak is
    the axis peak times sqrt(2), because at every point Gx == Gy, so
    |G| = sqrt(Gx^2 + Gy^2) = sqrt(2) * |Gx|."""
    gx = pp.make_trapezoid(
        channel="x",
        amplitude=0.5 * SYSTEM.max_grad,
        rise_time=200e-6,
        flat_time=1e-3,
        system=SYSTEM,
    )
    gy = pp.make_trapezoid(
        channel="y",
        amplitude=0.5 * SYSTEM.max_grad,
        rise_time=200e-6,
        flat_time=1e-3,
        system=SYSTEM,
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx, gy)

    result = gradient_limits(seq)

    assert result.vector_peak_mt_per_m == pytest.approx(
        result.axes["x"].peak_mt_per_m * math.sqrt(2)
    )
    assert result.axes["x"].peak_mt_per_m == pytest.approx(result.axes["y"].peak_mt_per_m)


def test_window_that_cuts_a_ramp_gives_hand_computed_rms():
    """A window that ends halfway up the rising ramp of a trapezoid: the RMS amplitude
    over the window equals the value computed by hand from the piece that the window
    keeps, cut at the window edge."""
    amplitude = 0.5 * SYSTEM.max_grad
    rise_time = 200e-6
    gx = pp.make_trapezoid(
        channel="x", amplitude=amplitude, rise_time=rise_time, flat_time=1e-3, system=SYSTEM
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    window = (0.0, gx.delay + rise_time / 2)

    result = gradient_limits(seq, window=window)

    # The window keeps the ramp from (0, 0) to (rise_time / 2, amplitude / 2), a
    # straight line, so Delta t * (a^2 + a*b + b^2) / 3 with a = 0, b = amplitude / 2.
    mid_amplitude = amplitude / 2
    length = window[1] - window[0]
    energy = (rise_time / 2) * (mid_amplitude**2) / 3
    rms_mt_per_m = math.sqrt(energy / length) / GAMMA * 1e3

    assert result.range_s == window
    assert result.axes["x"].rms_mt_per_m == pytest.approx(rms_mt_per_m)


def test_arbitrary_gradient_peak_is_the_largest_of_first_last_and_waveform():
    """An arbitrary gradient: the peak amplitude is the largest absolute value among
    the shape's `first`, `last` and interior waveform samples, since `gradient_points`
    (seq_utils) adds `first` and `last` as extra points at the shape's ends."""
    n = 40
    dt = SYSTEM.grad_raster_time
    t = (np.arange(n) + 0.5) * dt
    # A waveform that is not symmetric, so its largest magnitude is not at the center.
    waveform = 0.3 * SYSTEM.max_grad * np.sin(np.pi * t / (1.5 * n * dt))
    gx = pp.make_arbitrary_grad(channel="x", waveform=waveform, system=SYSTEM)
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)

    result = gradient_limits(seq)

    block = seq.get_block(1)
    peak_hz_per_m = max(abs(block.gx.first), abs(block.gx.last), np.max(np.abs(waveform)))
    assert result.axes["x"].peak_mt_per_m == pytest.approx(peak_hz_per_m / GAMMA * 1e3)


def test_no_gradients_sets_reason():
    """A sequence with no gradient events at all: `reason` is set, and every numeric
    field is its zero value (0.0, or None for a block field)."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_delay(2e-3))

    result = gradient_limits(seq)

    assert result.reason == "no gradient events in the sequence"
    assert result.vector_peak_mt_per_m == 0.0
    assert result.vector_peak_time_s == 0.0
    for axis in ("x", "y", "z"):
        a = result.axes[axis]
        assert a.peak_mt_per_m == 0.0
        assert a.peak_block is None
        assert a.max_slew_t_per_m_per_s == 0.0
        assert a.slew_block is None
        assert a.rms_mt_per_m == 0.0


def test_arbitrary_gradient_max_slew_is_the_largest_neighbouring_slope():
    """The largest slew of an arbitrary gradient is the largest `|delta g / delta t|`
    between its neighbouring corner points (the shape's `first`, its waveform samples,
    and its `last`), computed by hand from the event's own fields, not by calling
    `gradient_limits` for the expected value."""
    n = 40
    dt = SYSTEM.grad_raster_time
    t = (np.arange(n) + 0.5) * dt
    # An asymmetric waveform, so the largest slope is not obviously at one place.
    waveform = 0.3 * SYSTEM.max_grad * np.sin(2 * np.pi * t / (1.3 * n * dt))
    gx = pp.make_arbitrary_grad(channel="x", waveform=waveform, system=SYSTEM)
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    block = seq.get_block(1)

    result = gradient_limits(seq)

    times = np.concatenate(([0.0], block.gx.tt, [block.gx.shape_dur]))
    amps = np.concatenate(([block.gx.first], block.gx.waveform, [block.gx.last]))
    expected_slew_t_per_m_per_s = float(np.max(np.abs(np.diff(amps) / np.diff(times)))) / GAMMA

    assert result.axes["x"].max_slew_t_per_m_per_s == pytest.approx(expected_slew_t_per_m_per_s)


def test_extended_trapezoid_max_slew_is_the_largest_segment_slope():
    """The largest slew of an extended trapezoid is the largest `|delta g / delta t|`
    between its neighbouring control points, computed by hand from the times and the
    amplitudes given to `make_extended_trapezoid`."""
    mg = SYSTEM.max_grad
    times = [0.0, 200e-6, 400e-6, 900e-6, 1100e-6]
    amplitudes = [0.0, 0.1 * mg, 0.15 * mg, 0.15 * mg, 0.0]
    gx = pp.make_extended_trapezoid(channel="x", times=times, amplitudes=amplitudes, system=SYSTEM)
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)

    result = gradient_limits(seq)

    expected_slew_t_per_m_per_s = (
        float(np.max(np.abs(np.diff(amplitudes) / np.diff(times)))) / GAMMA
    )

    assert result.axes["x"].max_slew_t_per_m_per_s == pytest.approx(expected_slew_t_per_m_per_s)


def test_largest_over_several_blocks_and_axes_credits_the_first_block_with_that_value():
    """With several blocks on several axes, the peak amplitude and the peak slew of
    each axis are the largest over every block that has an event on that axis, and the
    credited block is the first block, in play order, whose event reaches that value
    (a later block with the very same event does not move the credit)."""
    gx_small = pp.make_trapezoid(
        channel="x",
        amplitude=0.2 * SYSTEM.max_grad,
        rise_time=100e-6,
        flat_time=200e-6,
        system=SYSTEM,
    )
    gx_big = pp.make_trapezoid(
        channel="x",
        amplitude=0.8 * SYSTEM.max_grad,
        rise_time=250e-6,
        flat_time=200e-6,
        system=SYSTEM,
    )
    gy = pp.make_trapezoid(
        channel="y",
        amplitude=0.5 * SYSTEM.max_grad,
        rise_time=200e-6,
        flat_time=100e-6,
        system=SYSTEM,
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx_small)
    seq.add_block(gy)
    seq.add_block(gx_big)
    seq.add_block(gx_big)  # the same event again: the credit must stay on the first block
    block_ids = list(seq.block_events)

    result = gradient_limits(seq)

    assert result.axes["x"].peak_mt_per_m == pytest.approx(0.8 * SYSTEM.max_grad / GAMMA * 1e3)
    assert result.axes["x"].peak_block == block_ids[2]
    assert result.axes["x"].max_slew_t_per_m_per_s == pytest.approx(
        0.8 * SYSTEM.max_grad / gx_big.rise_time / GAMMA
    )
    assert result.axes["x"].slew_block == block_ids[2]
    assert result.axes["y"].peak_mt_per_m == pytest.approx(0.5 * SYSTEM.max_grad / GAMMA * 1e3)
    assert result.axes["y"].peak_block == block_ids[1]


def test_window_that_cuts_a_ramp_gives_the_slew_of_the_part_inside_the_window():
    """A window that includes only part of an extended trapezoid, over a segment with a
    smaller slope than another segment outside the window: the slew over the window is
    the slope of the part inside the window, not the largest slope of the whole event, and its
    time is the window start, where the window cuts that segment."""
    mg = SYSTEM.max_grad
    times = [0.0, 200e-6, 400e-6, 900e-6, 1100e-6]
    amplitudes = [0.0, 0.1 * mg, 0.15 * mg, 0.15 * mg, 0.0]
    gx = pp.make_extended_trapezoid(channel="x", times=times, amplitudes=amplitudes, system=SYSTEM)
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    window = (100e-6, 300e-6)  # inside the first two segments; the steepest segment
    # (900 to 1100 us, 750 * mg) is outside the window.

    result = gradient_limits(seq, window=window)

    expected_slew_t_per_m_per_s = (500 * mg) / GAMMA  # the slope of the 0-200 us segment

    assert result.axes["x"].max_slew_t_per_m_per_s == pytest.approx(expected_slew_t_per_m_per_s)
    assert result.axes["x"].slew_time_s == pytest.approx(100e-6)


def test_slew_time_is_the_start_of_the_steepest_segment():
    """An extended trapezoid whose steepest segment is its last one (900 to 1100 us): the
    slew time is the start of that segment, 900 us."""
    mg = SYSTEM.max_grad
    times = [0.0, 200e-6, 400e-6, 900e-6, 1100e-6]
    amplitudes = [0.0, 0.1 * mg, 0.15 * mg, 0.15 * mg, 0.0]
    gx = pp.make_extended_trapezoid(channel="x", times=times, amplitudes=amplitudes, system=SYSTEM)
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)

    result = gradient_limits(seq)

    assert result.axes["x"].max_slew_t_per_m_per_s == pytest.approx(750 * mg / GAMMA)
    assert result.axes["x"].slew_time_s == pytest.approx(900e-6)


def test_vector_peak_of_g_compares_different_triples_across_blocks():
    """Two blocks with different triples of active gradients: the vector peak of `|G|`
    is the largest magnitude found across the two different triples, not just the
    largest single-axis peak, and its block and time are those of block B (the end of its
    rise, after the 0.8 ms of block A)."""
    amp_a = 0.9 * SYSTEM.max_grad
    gx_a = pp.make_trapezoid(
        channel="x", amplitude=amp_a, rise_time=300e-6, flat_time=200e-6, system=SYSTEM
    )
    amp_b = 0.7 * SYSTEM.max_grad
    gx_b = pp.make_trapezoid(
        channel="x", amplitude=amp_b, rise_time=200e-6, flat_time=200e-6, system=SYSTEM
    )
    gy_b = pp.make_trapezoid(
        channel="y", amplitude=amp_b, rise_time=200e-6, flat_time=200e-6, system=SYSTEM
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx_a)
    seq.add_block(gx_b, gy_b)

    result = gradient_limits(seq)

    expected_vector_peak_mt_per_m = math.sqrt(2) * amp_b / GAMMA * 1e3
    assert expected_vector_peak_mt_per_m > amp_a / GAMMA * 1e3  # block B's triple wins
    assert result.vector_peak_mt_per_m == pytest.approx(expected_vector_peak_mt_per_m)
    _block_a_id, block_b_id = seq.block_events
    assert result.vector_peak_block == block_b_id
    assert result.vector_peak_time_s == pytest.approx(1.0e-3)


def test_default_limits_come_from_seq_system():
    """With `limits=None`, the limits are `seq.system.max_grad` and
    `seq.system.max_slew`, converted from Hz/m (respectively Hz/m/s) to mT/m
    (respectively T/m/s), with the label "pypulseq system limits"."""
    gx = pp.make_trapezoid(channel="x", area=1000, system=SYSTEM)
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)

    result = gradient_limits(seq)

    assert result.limits.label == "pypulseq system limits"
    assert result.limits.max_grad_mt_per_m == pytest.approx(seq.system.max_grad / GAMMA * 1e3)
    assert result.limits.max_slew_t_per_m_per_s == pytest.approx(seq.system.max_slew / GAMMA)


# ---- Junction steps (decision 6 of section 2.5 of docs/plans/cards-at-scale.md, task 4.3) ----
#
# `add_block` checks the step at every block junction against `max_slew * grad_raster_time`
# (`docs/notes/slew-definitions.md`, section 1.1). The gradient limits card now reports that
# step, divided by `grad_raster_time`, as part of the axis's slew, whenever it is the largest
# value found (segment or junction). These sequences are built so that the junction step is
# larger than every segment's own slope, so the tests show the junction is really included.

_RASTER = SYSTEM.grad_raster_time
_MAX_STEP = SYSTEM.max_slew * _RASTER  # the largest step add_block accepts


def test_junction_step_between_extended_trapezoids_is_reported_as_the_slew():
    """A step at the junction between two extended trapezoids, within the tolerance that
    `add_block` accepts (`max_slew * grad_raster_time`, section 1.1 of
    `docs/notes/slew-definitions.md`) and larger than any segment's own slope: the
    reported slew is the step divided by `grad_raster_time`, credited to the block after
    the junction, and its time is the junction (0.2 ms)."""
    step = 0.9 * _MAX_STEP
    x = 0.3 * SYSTEM.max_grad
    y = x - step
    gx_a = pp.make_extended_trapezoid(
        channel="x", times=[0.0, 100e-6, 200e-6], amplitudes=[0.0, x, x], system=SYSTEM
    )
    gx_b = pp.make_extended_trapezoid(
        channel="x", times=[0.0, 100e-6, 200e-6], amplitudes=[y, y, 0.0], system=SYSTEM
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx_a)
    seq.add_block(gx_b)
    _block_a_id, block_b_id = seq.block_events

    result = gradient_limits(seq)

    expected_slew_t_per_m_per_s = step / _RASTER / GAMMA
    assert result.axes["x"].max_slew_t_per_m_per_s == pytest.approx(expected_slew_t_per_m_per_s)
    assert result.axes["x"].slew_block == block_b_id
    assert result.axes["x"].slew_time_s == pytest.approx(200e-6)


def test_gradient_ending_non_zero_before_a_block_with_no_gradient_is_a_junction_step():
    """A gradient that ends at a non-zero value (within the tolerance `add_block`
    accepts) right before a block with no gradient on that axis: the junction step
    uses 0 for the block with no event, and is credited to that block (the block after
    the junction)."""
    last_value = 0.9 * _MAX_STEP
    gx = pp.make_extended_trapezoid(
        channel="x",
        times=[0.0, 100e-6, 200e-6],
        amplitudes=[0.0, last_value, last_value],
        system=SYSTEM,
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    seq.add_block(pp.make_delay(1e-3))
    _block_a_id, block_b_id = seq.block_events

    result = gradient_limits(seq)

    expected_slew_t_per_m_per_s = last_value / _RASTER / GAMMA
    assert result.axes["x"].max_slew_t_per_m_per_s == pytest.approx(expected_slew_t_per_m_per_s)
    assert result.axes["x"].slew_block == block_b_id


def test_first_block_not_starting_at_zero_is_a_junction_step_before_the_first_block():
    """A first block whose gradient starts at a non-zero value within the tolerance
    `add_block` accepts: the junction before the first block uses 0 for "the block
    before" (there is none), and is credited to the first block."""
    start_value = 0.9 * _MAX_STEP
    gx = pp.make_extended_trapezoid(
        channel="x",
        times=[0.0, 100e-6, 200e-6],
        amplitudes=[start_value, start_value, 0.0],
        system=SYSTEM,
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    (block_id,) = seq.block_events

    result = gradient_limits(seq)

    expected_slew_t_per_m_per_s = start_value / _RASTER / GAMMA
    assert result.axes["x"].max_slew_t_per_m_per_s == pytest.approx(expected_slew_t_per_m_per_s)
    assert result.axes["x"].slew_block == block_id


def test_window_inside_a_block_with_no_gradient_ignores_the_junction_before_it():
    """A window entirely inside a block with no gradient, after a gradient event that
    ends at a non-zero value (within the tolerance `add_block` accepts) in the block
    before: the junction between the two blocks is before the window start, so it is
    not used, and the window has no gradient event and 0 slew. A window that starts
    exactly at that junction still uses it."""
    step = 0.9 * _MAX_STEP
    gx = pp.make_extended_trapezoid(
        channel="x", times=[0.0, 100e-6, 200e-6], amplitudes=[0.0, step, step], system=SYSTEM
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    seq.add_block(pp.make_delay(1e-3))
    _block_a_id, block_b_id = seq.block_events

    inside_result = gradient_limits(seq, window=(0.5e-3, 1.0e-3))
    assert inside_result.reason == "no gradient events in the window"
    assert inside_result.axes["x"].max_slew_t_per_m_per_s == 0.0
    assert inside_result.axes["x"].slew_block is None

    junction_result = gradient_limits(seq, window=(0.2e-3, 1.0e-3))
    expected_slew_t_per_m_per_s = step / _RASTER / GAMMA
    assert junction_result.reason is None
    assert junction_result.axes["x"].max_slew_t_per_m_per_s == pytest.approx(
        expected_slew_t_per_m_per_s
    )
    assert junction_result.axes["x"].slew_block == block_b_id


def _tie_trapezoid(channel: str):
    """A trapezoid of 0.8 ms: rise 0 to 0.2 ms, flat to 0.6 ms, fall to 0.8 ms."""
    return pp.make_trapezoid(
        channel=channel,
        amplitude=0.5 * SYSTEM.max_grad,
        rise_time=200e-6,
        flat_time=400e-6,
        system=SYSTEM,
    )


def test_window_that_cuts_a_block_credits_it_on_a_tie_with_a_later_block():
    """A window that starts in the flat top of block 1, then block 2 with the same trapezoid
    fully inside the window: the two blocks reach the same peak and the same slew (the fall
    ramp of block 1 is fully inside the window), so both are credited to block 1, the first in
    play order, and the peak time is the window start, the first time block 1 reaches the
    peak."""
    g = _tie_trapezoid("x")
    seq = pp.Sequence(SYSTEM)
    seq.add_block(g)
    seq.add_block(g)
    seq.add_block(pp.make_delay(1e-3))
    block_1_id = next(iter(seq.block_events))

    result = gradient_limits(seq, window=(0.4e-3, 2.0e-3))

    axis = result.axes["x"]
    assert axis.peak_block == block_1_id
    assert axis.peak_time_s == pytest.approx(0.4e-3)
    assert axis.slew_block == block_1_id
    assert result.vector_peak_time_s == pytest.approx(0.4e-3)


def test_vector_peak_time_on_a_tie_is_the_first_time_in_play_order():
    """The same trapezoid on x in block 1 and on y in block 2: |G| reaches the same peak in
    both blocks, from two different triples of events, and the vector peak time is the first
    time that block 1 reaches it (the end of its rise, 0.2 ms), not a time in block 2, and the
    vector peak block is block 1."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(_tie_trapezoid("x"))
    seq.add_block(_tie_trapezoid("y"))

    result = gradient_limits(seq)

    assert result.vector_peak_time_s == pytest.approx(200e-6)
    assert result.vector_peak_block == next(iter(seq.block_events))


def test_axis_whose_only_event_is_zero_credits_no_block():
    """A y event scaled to amplitude 0 (as a phase encode loop makes for the centre line of
    k-space), with an x trapezoid in the same block: the y axis has a peak and a slew of 0, and
    no block is credited for either."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(_tie_trapezoid("x"), pp.scale_grad(_tie_trapezoid("y"), 0.0))

    result = gradient_limits(seq)

    axis = result.axes["y"]
    assert axis.peak_mt_per_m == 0.0
    assert axis.max_slew_t_per_m_per_s == 0.0
    assert axis.peak_block is None
    assert axis.slew_block is None


# ---- Comparisons with the oracle (task 4.4) ----
#
# `tests/oracles/grad_limits.py` is the implementation from before phase 4 of
# docs/plans/cards-at-scale.md. It reads every block with `get_block` and has no junction
# steps. The random sequences below build every gradient event so that it starts and ends at
# 0, so every block junction step is 0 (the junction tests above cover the junction steps on
# their own, against hand-computed values, as docs/plans/cards-at-scale.md section 4.6 item 6
# says to). With no junction contribution, the new code's slew is the segment part only, so
# the whole result can be compared with the oracle's.
#
# The new code sums and maxes per unique event; the oracle sums and maxes per block, after
# adding that block's own start time to the event's corner points before differencing them
# for a slope. When a sequence plays one event in several blocks at different start times
# (for example `tests/synthetic.gre_sequence`'s readout, once each TR), the oracle gets a
# very slightly different slope for the same event at each occurrence: each corner time
# `start + offset` is rounded to about machine eps times the start time, and a slope divides
# the difference of two such times by the segment's duration. The tolerance is therefore
# derived from each sequence (the user, 2026-09-28): `1e-12 + 4 * eps * duration / shortest
# segment` (`_rounding_tol`), relative to the value or to the limit of the same kind. The
# oracle can also credit a peak or a slew of a repeated event to a later block, from the
# same rounding, so these general comparisons check only whether a block is credited; the
# dedicated block-attribution tests above use events that are not repeated and check the
# block exactly.


def _rounding_tol(seq: pp.Sequence) -> float:
    """`1e-12 + 4 * eps * duration / shortest segment`: the rounding of the oracle's
    absolute corner times (`block start + offset`, about eps times the duration), divided
    by the shortest time between two corner points of any gradient event of `seq`."""
    duration = float(sum(seq.block_durations.values()))
    index = sequence_index(seq)
    shortest = math.inf
    for _, g in grad_events(seq, index):
        _, offsets, _ = gradient_offsets(g)
        steps = np.diff(np.asarray(offsets, dtype=float))
        steps = steps[steps > 0]
        if steps.size:
            shortest = min(shortest, float(steps.min()))
    if not math.isfinite(shortest):
        return 1e-12
    return 1e-12 + 4 * np.finfo(float).eps * duration / shortest


def _assert_close(actual: float, expected: float, scale: float, tol: float, label: str) -> None:
    bound = max(abs(expected) * tol, scale * tol)
    assert abs(actual - expected) <= bound, (
        f"{label}: {actual!r} != {expected!r} (tolerance {bound!r})"
    )


def _assert_matches_oracle(ours: GradientLimits, theirs, tol: float) -> None:
    assert ours.reason == theirs.reason
    assert ours.range_s == pytest.approx(theirs.range_s, abs=1e-9)
    grad_scale = ours.limits.max_grad_mt_per_m
    slew_scale = ours.limits.max_slew_t_per_m_per_s
    for axis in ("x", "y", "z"):
        a, b = ours.axes[axis], theirs.axes[axis]
        _assert_close(a.peak_mt_per_m, b.peak_mt_per_m, grad_scale, tol, f"{axis} peak")
        _assert_close(
            a.max_slew_t_per_m_per_s, b.max_slew_t_per_m_per_s, slew_scale, tol, f"{axis} slew"
        )
        _assert_close(a.rms_mt_per_m, b.rms_mt_per_m, grad_scale, tol, f"{axis} rms")
        assert (a.peak_block is None) == (b.peak_block is None), f"{axis} peak_block presence"
        assert (a.slew_block is None) == (b.slew_block is None), f"{axis} slew_block presence"
    _assert_close(
        ours.vector_peak_mt_per_m, theirs.vector_peak_mt_per_m, grad_scale, tol, "vector peak"
    )


@pytest.mark.parametrize(
    "make_seq",
    [spin_echo_sequence, gre_sequence, empty_sequence, arbitrary_gradient_sequence],
    ids=["spin_echo", "gre", "empty", "arbitrary_gradient"],
)
def test_matches_oracle_on_synthetic_sequences(make_seq):
    """`gradient_limits` matches the oracle on the whole file, and on a window that
    covers the first half of the sequence, for each of `tests/synthetic.py`'s
    sequences."""
    seq = make_seq()
    total = sum(seq.block_durations.values())

    assert_ours = gradient_limits(seq)
    assert_theirs = oracle.gradient_limits(seq)
    tol = _rounding_tol(seq)
    _assert_matches_oracle(assert_ours, assert_theirs, tol)

    if total > 0:
        window = (0.0, total / 2)
        _assert_matches_oracle(
            gradient_limits(seq, window=window), oracle.gradient_limits(seq, window=window), tol
        )


def _zero_ended_trapezoid(rng: np.random.Generator, channel: str):
    amplitude = rng.uniform(0.05, 0.8) * SYSTEM.max_grad * rng.choice([-1.0, 1.0])
    min_rise = abs(amplitude) / (0.7 * SYSTEM.max_slew)
    rise_time = math.ceil(max(min_rise, 50e-6) / _RASTER) * _RASTER
    flat_time = round(rng.uniform(0.0, 500e-6) / _RASTER) * _RASTER
    return pp.make_trapezoid(
        channel=channel,
        amplitude=amplitude,
        rise_time=rise_time,
        flat_time=flat_time,
        system=SYSTEM,
    )


def _zero_ended_extended_trapezoid(rng: np.random.Generator, channel: str):
    peak = rng.uniform(0.05, 0.6) * SYSTEM.max_grad * rng.choice([-1.0, 1.0])
    min_ramp = abs(peak) / (0.7 * SYSTEM.max_slew)
    ramp = math.ceil(max(min_ramp, 50e-6) / _RASTER) * _RASTER
    flat = round(rng.uniform(_RASTER, 300e-6) / _RASTER) * _RASTER
    times = [0.0, ramp, ramp + flat, 2 * ramp + flat]
    amplitudes = [0.0, peak, peak, 0.0]
    return pp.make_extended_trapezoid(
        channel=channel, times=times, amplitudes=amplitudes, system=SYSTEM
    )


_ARB_N = 50
_ARB_SHAPE = np.sin(np.pi * np.arange(1, _ARB_N + 1) / (_ARB_N + 1))


def _zero_ended_arbitrary(rng: np.random.Generator, channel: str):
    amplitude = rng.uniform(0.05, 0.3) * SYSTEM.max_grad * rng.choice([-1.0, 1.0])
    # first and last default to a linear extrapolation of the waveform's own edge
    # samples (pypulseq's make_arbitrary_grad), not to 0: pass them explicitly so this
    # event, like the other two builders, starts and ends at 0.
    return pp.make_arbitrary_grad(
        channel=channel, waveform=_ARB_SHAPE * amplitude, first=0.0, last=0.0, system=SYSTEM
    )


_RANDOM_EVENT_BUILDERS = [
    _zero_ended_trapezoid,
    _zero_ended_extended_trapezoid,
    _zero_ended_arbitrary,
]


def _random_gradient_sequence(rng: np.random.Generator) -> pp.Sequence:
    """A sequence of 2 to 6 blocks, each with 0 to 3 random gradient axes, each a
    trapezoid, an extended trapezoid or an arbitrary gradient (`make_*` functions, so
    pypulseq's own checks apply) that starts and ends at 0, so every block junction
    step is 0."""
    seq = pp.Sequence(SYSTEM)
    n_blocks = int(rng.integers(2, 7))
    for _ in range(n_blocks):
        n_axes = int(rng.integers(0, 4))
        axes = rng.choice(["x", "y", "z"], size=n_axes, replace=False) if n_axes else []
        events = []
        for axis in axes:
            builder = _RANDOM_EVENT_BUILDERS[int(rng.integers(0, len(_RANDOM_EVENT_BUILDERS)))]
            events.append(builder(rng, str(axis)))
        if events:
            seq.add_block(*events)
        else:
            delay = round(rng.uniform(1e-4, 1e-3) / _RASTER) * _RASTER
            seq.add_block(pp.make_delay(delay))
    return seq


@pytest.mark.parametrize("seed", range(200))
def test_matches_oracle_on_random_gradient_sequences(seed):
    """200 random sequences of trapezoids, extended trapezoids and arbitrary gradients
    on random axes, each event starting and ending at 0 (so no block junction has a
    step, and the result is only the per-event, non-junction part that
    `docs/plans/cards-at-scale.md` section 4.6 item 6 says to compare with the
    oracle): `gradient_limits` matches the oracle, on the whole file and on a random
    window, within the tolerance of section 3.5, item 2 (see the comment above)."""
    rng = np.random.default_rng(seed)
    seq = _random_gradient_sequence(rng)
    total = sum(seq.block_durations.values())

    ours_whole = gradient_limits(seq)
    theirs_whole = oracle.gradient_limits(seq)
    tol = _rounding_tol(seq)
    _assert_matches_oracle(ours_whole, theirs_whole, tol)

    start = rng.uniform(0.0, total * 0.6)
    end = rng.uniform(start + _RASTER, total)
    window = (start, end)
    ours_window = gradient_limits(seq, window=window)
    theirs_window = oracle.gradient_limits(seq, window=window)
    _assert_matches_oracle(ours_window, theirs_window, tol)

    # The whole-file RMS that gradient_limits computes in the same call, for the card's
    # "RMS over whole file" column, matches the oracle's own whole-file RMS.
    for axis in ("x", "y", "z"):
        _assert_close(
            ours_window.whole_rms_mt_per_m[axis],
            theirs_whole.axes[axis].rms_mt_per_m,
            ours_window.limits.max_grad_mt_per_m,
            tol,
            f"whole_rms_mt_per_m[{axis}]",
        )
