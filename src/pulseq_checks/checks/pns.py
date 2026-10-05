"""The check rule `pns.safe` (plan section 4.7): the peak of the SAFE PNS total of the
whole sequence, with the SAFE parameters of the target profile. A fail also gives each interval
of samples at or above 100 % as a finding (`PnsLevels.above`).

The levels come from the analysis `pns.safe.levels` and the block index from `seq.index`, both
of pulseq-analysis. `ctx.analysis` calculates each one time for each target, with the SAFE
hardware of the target from the binding (`bindings.BINDINGS`). The PNS values of the analysis
are in Hz/T, with no gamma: the check divides them by `gamma_magnitude(ctx)`. `PnsLevels.above`
is keyed by the Hz/T threshold of the binding, `pns_threshold_hz_per_t(ctx)`."""

import numpy as np
from pulseq_analysis.pns_levels import NO_GRADIENTS, PnsInterval

from ..bindings import gamma_magnitude, pns_threshold_hz_per_t
from ..results import Finding, Location, Result, State
from ..rules import CheckPromise, CheckSpec, RunContext
from ..safe_model import SAFE_MODEL


class _SafePns:
    spec = CheckSpec(
        id="pns.safe",
        version=1,
        title="Peripheral nerve stimulation, SAFE model",
        quantity=(
            "The peak over the whole sequence of the SAFE PNS total, in percent of the "
            "stimulation limit. The total of a sample is sqrt(x^2 + y^2 + z^2) of the "
            "values of the three axes, each as a fraction of the stimulation limit of "
            "that axis. `pns_levels` calculates it with the SAFE model of the pinned "
            "pypulseq fork (`_safe_gwf_to_pns_chunk`, the chunk form of the model of "
            "`calc_pns`) and the SAFE parameters of the target. pulseq-analysis gives the "
            "total in Hz/T, with no gamma (the model runs on the gradient in Hz/m), and the "
            "check divides it by the magnitude of the gamma of the target: |opts.gamma|, or "
            "42.576 MHz/T, the value of pypulseq, when the profile does not give it, or "
            "|seq.system.gamma| when the limits come from the sequence object. For a Sequence "
            "object with the limits from the profile, it is the gamma of the profile, not that "
            "of seq.system. The gradient checks use the same gamma. A negative gamma is valid, "
            "and the check uses its magnitude."
        ),
        inputs=(),
        models=("pns.safe",),
        limit="100 % of the stimulation limit.",
        tolerance=(
            "None: the rule of pypulseq, `pns_norm < 1` (decision 5 of the plan), with no "
            "added tolerance. The check compares in Hz/T: it fails when the peak is at or "
            "above the limit, 1 times the magnitude of gamma. That is the rule of pypulseq "
            "without its division by gamma, and the rule of an interval of the findings."
        ),
        pass_condition=(
            "The peak is below 100 % of the stimulation limit. "
            'The check is "not evaluated" when the file does not declare GradientRasterTime or '
            "BlockDurationRaster and the target does not give that raster "
            "(rasters.GradientRasterTime or rasters.BlockDurationRaster). The check does not "
            "use a default of pypulseq for a raster. "
            "The result also gives each interval at or above 100 % as a finding (see Findings)."
        ),
        cost="slow",
        pypulseq=(
            "`_safe_gwf_to_pns_chunk` and `calc_pns` of pypulseq.utils.safe_pns_prediction "
            "(the pinned fork)"
        ),
        url=None,
        rasters=("GradientRasterTime", "BlockDurationRaster"),
        analyses=("pns.safe.levels", "seq.index"),
        findings=(
            "One finding for each interval of consecutive samples where the SAFE total is at "
            "or above 100 % of the stimulation limit, in time order. A fail has at least one "
            "finding, and a pass has none. The code is PNS_ABOVE_LIMIT. The location is the "
            "block ID of the block that holds the first sample of the interval (the last "
            "block that starts at or before it) and the time of that sample, in seconds from "
            "the start of the sequence. The data are start_s and end_s (the times of the "
            "first and the last sample of the interval, in seconds from the start of the "
            "sequence), peak_percent (the largest total in the interval, in percent of the "
            "stimulation limit), peak_time_s (the time of the first sample with that total, "
            "in seconds from the start of the sequence) and num_samples (the number of "
            "samples of the interval). The message is the start and the end, with up to 6 "
            "significant digits, and the peak, with up to 4, for example "
            '"PNS at or above 100 % from 0.0123 s to 0.0125 s, peak 104.2 %". The largest '
            "peak_percent of the findings is the value of the result."
        ),
        promise=CheckPromise(
            on_pass=(
                "The SAFE model of pypulseq, with the SAFE parameters of the target, predicts a "
                "peak PNS below 100 % of the stimulation limit for the gradient waveform of the "
                "file, with the logical axes x, y and z of the file as the physical axes of the "
                "coil."
            ),
            on_fail=(
                "The model predicts a PNS at or above 100 % of the stimulation limit at some time."
                " The findings give each interval at or above 100 %."
            ),
            not_promised=(
                "That a subject feels no stimulation: SAFE is a model, and its prediction is only "
                "as good as the SAFE parameters of the target. The PNS when the scan rotates the "
                "logical axes: the SAFE parameters are different for each physical axis, so a "
                "rotation changes the PNS. The waveform that the scanner plays, when its "
                "interpreter makes it in another way than the check: the check gives the SAFE "
                "model the gradient waveform of the file, sampled at the gradient raster of the "
                "file. When the GradientRasterTime or the BlockDurationRaster of the file differs "
                "from the raster of the target (timing.rasters fails), the interpreter makes the "
                "waveform on the scanner in a way that the check does not know, and the value "
                "describes the waveform of the file only."
            ),
        ),
    )

    def run(self, ctx: RunContext) -> Result:
        levels = ctx.analysis("pns.safe.levels")
        model = {"model": "pns.safe", "model_version": SAFE_MODEL.version}
        if levels.reason == NO_GRADIENTS:
            return ctx.result(
                self.spec, State.PASS, value=0.0, limit=100.0, unit="%", location=None, **model
            )
        # The state is decided in Hz/T, by the rule of `PnsLevels.above`: thus a fail has at
        # least one finding, and a pass has none.
        threshold = pns_threshold_hz_per_t(ctx)
        g = gamma_magnitude(ctx)
        state = State.FAIL if levels.peak_hz_per_t >= threshold else State.PASS
        return ctx.result(
            self.spec,
            state,
            value=100 * levels.peak_hz_per_t / g,
            limit=100.0,
            unit="%",
            location=self._location(ctx, levels.peak_time_s),
            findings=self._findings(ctx, levels.above[threshold], g),
            **model,
        )

    @staticmethod
    def _findings(
        ctx: RunContext, intervals: tuple[PnsInterval, ...], g: float
    ) -> tuple[Finding, ...]:
        """One finding for each interval, in time order, with its peak divided by `g`, the
        magnitude of gamma, in Hz/T. The block of an interval is found by the rule of
        `_location`, for all intervals in one call of `np.searchsorted`."""
        if not intervals:
            return ()
        index = ctx.analysis("seq.index")
        starts = np.array([interval.start_s for interval in intervals])
        blocks = np.maximum(np.searchsorted(index.start_s, starts, side="right") - 1, 0)
        block_ids = index.block_id[blocks].tolist()
        findings = []
        for interval, block in zip(intervals, block_ids, strict=True):
            start_s, end_s = float(interval.start_s), float(interval.end_s)
            peak_percent = float(100 * interval.peak_hz_per_t / g)
            findings.append(
                Finding(
                    code="PNS_ABOVE_LIMIT",
                    message=(
                        f"PNS at or above 100 % from {start_s:.6g} s to {end_s:.6g} s, "
                        f"peak {peak_percent:.4g} %"
                    ),
                    location=Location(block=int(block), time_s=start_s),
                    data={
                        "start_s": start_s,
                        "end_s": end_s,
                        "peak_percent": peak_percent,
                        "peak_time_s": float(interval.peak_time_s),
                        "num_samples": int(interval.num_samples),
                    },
                )
            )
        return tuple(findings)

    @staticmethod
    def _location(ctx: RunContext, time_s: float | None) -> Location | None:
        """The block that holds `time_s`: the last block that starts at or before it."""
        if time_s is None:
            return None
        index = ctx.analysis("seq.index")
        i = max(int(np.searchsorted(index.start_s, time_s, side="right")) - 1, 0)
        return Location(block=int(index.block_id[i]), time_s=time_s)


SAFE = _SafePns()
