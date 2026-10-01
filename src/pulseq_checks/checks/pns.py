"""The check rule `pns.safe` (plan section 4.7): the peak of the SAFE PNS total of the
whole sequence, with the SAFE parameters of the target profile."""

import numpy as np

from ..pns import pns_levels_for
from ..pns_levels import NO_GRADIENTS, SAFE_MODEL, hw_from_dict
from ..results import Location, Result, State
from ..rules import CheckSpec, RunContext
from ..seq_index import sequence_index


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
            "`calc_pns`) and the SAFE parameters of the target. The gradient is divided by "
            "the gamma of seq.system. For a file, that is the gamma of the target (opts.gamma, "
            "or 42.576 MHz/T, the value of pypulseq, when the profile does not give it)."
        ),
        inputs=(),
        models=("pns.safe",),
        limit="100 % of the stimulation limit.",
        tolerance=(
            "None: the rule of pypulseq, `pns_norm < 1` (decision 5 of the plan), with no "
            "added tolerance."
        ),
        pass_condition=(
            "The peak is below 100 % of the stimulation limit. "
            'The check is "not evaluated" when the file does not declare GradientRasterTime or '
            "BlockDurationRaster and the target does not give that raster "
            "(rasters.GradientRasterTime or rasters.BlockDurationRaster). The check does not "
            "use a default of pypulseq for a raster."
        ),
        cost="slow",
        pypulseq=(
            "`_safe_gwf_to_pns_chunk` and `calc_pns` of pypulseq.utils.safe_pns_prediction "
            "(the pinned fork)"
        ),
        url=None,
        rasters=("GradientRasterTime", "BlockDurationRaster"),
    )

    def run(self, ctx: RunContext) -> Result:
        params = ctx.profile.models["pns.safe"]
        hw = hw_from_dict(params)
        label = params.get("name") or ctx.profile.sources["models.pns.safe"]
        levels = ctx.measure("pns_levels", lambda seq: pns_levels_for(seq, hardware=(hw, label)))
        model = {"model": "pns.safe", "model_version": SAFE_MODEL.version}
        if levels.reason == NO_GRADIENTS:
            return ctx.result(
                self.spec, State.PASS, value=0.0, limit=100.0, unit="%", location=None, **model
            )
        state = State.PASS if levels.peak < 1 else State.FAIL
        return ctx.result(
            self.spec,
            state,
            value=100 * levels.peak,
            limit=100.0,
            unit="%",
            location=self._location(ctx, levels.peak_time_s),
            **model,
        )

    @staticmethod
    def _location(ctx: RunContext, time_s: float | None) -> Location | None:
        """The block that holds `time_s`: the last block that starts at or before it."""
        if time_s is None:
            return None
        index = ctx.measure("index", sequence_index)
        i = max(int(np.searchsorted(index.start_s, time_s, side="right")) - 1, 0)
        return Location(block=int(index.block_id[i]), time_s=time_s)


SAFE = _SafePns()
