"""The check rule `acoustic.resonance-energy` (plan acoustic-resonance-check, section 3): the
percent of the energy of the gradient spectrum that is in the acoustic resonance bands of the
target, all the bands together. A fail gives one finding for all the bands.

The spectrum comes from the analysis `gradient.spectrum` of pulseq-analysis, with the defaults
of pypulseq (decision D9). It is in Hz/m/sqrt(Hz), but a fraction of energy has no unit, so the
check does not need the gamma of the target."""

import numpy as np
from pulseq_analysis.grad_spectrum import NO_GRADIENTS, GradientSpectrum

from ..results import Finding, Result, State
from ..rules import CheckPromise, CheckSpec, RunContext

# The limit, in percent of the energy of the spectrum, for all the bands together (decisions D2
# and D7). It is a rule of this package, the decision of the user, not a limit of a vendor.
ACOUSTIC_BAND_ENERGY_LIMIT = 30.0


def _bands(n: int) -> str:
    """The number of bands as words, for the reason and the message."""
    if n == 0:
        return "no resonance band"
    return f"{n} resonance band" + ("" if n == 1 else "s")


class _ResonanceEnergy:
    spec = CheckSpec(
        id="acoustic.resonance-energy",
        version=1,
        title="Gradient energy in the acoustic resonance bands",
        quantity=(
            "The percent of the energy of the gradient spectrum that is in the acoustic "
            "resonance bands of the target, all the bands together. The spectrum is the RSS of "
            "the axes x, y and z from 0 Hz to 2000 Hz, by the method of "
            "`calculate_gradient_spectrum` of pypulseq with its defaults (the analysis "
            "gradient.spectrum of pulseq-analysis). The energy at a frequency is the square of "
            "the RSS spectrum. The band of a resonance (frequency f, bandwidth bw) is the closed "
            "interval [f - bw/2, f + bw/2]. A frequency in two bands counts one time."
        ),
        inputs=("acoustic.resonances",),
        models=(),
        limit=(
            f"{ACOUSTIC_BAND_ENERGY_LIMIT:g} % of the energy of the spectrum, for all the bands "
            "together. There is no limit for one band. The limit is a rule of this package, not "
            "a limit of a vendor."
        ),
        tolerance="None.",
        pass_condition=(
            f"The percent is at or below {ACOUSTIC_BAND_ENERGY_LIMIT:g} %. A sequence with no "
            "gradient event, a spectrum with no energy, and a target with an empty list of "
            'resonances give a pass with 0 %. The check is "not evaluated" when a band reaches '
            "above the highest frequency of the spectrum (2000 Hz), because the check cannot "
            'measure the energy there. The check is also "not evaluated" when the file does not '
            "declare GradientRasterTime or BlockDurationRaster and the target does not give "
            "that raster (rasters.GradientRasterTime or rasters.BlockDurationRaster). The check "
            "does not use a default of pypulseq for a raster."
        ),
        cost="slow",
        pypulseq=(
            "`calculate_gradient_spectrum` of pypulseq (the method), through "
            "`grad_spectrum.gradient_spectrum_for` of pulseq-analysis"
        ),
        url=None,
        rasters=("GradientRasterTime", "BlockDurationRaster"),
        analyses=("gradient.spectrum",),
        findings=(
            "A fail has one finding, for all the bands together, and a pass has none. The "
            "result gives no share for one band. The code is ACOUSTIC_BAND_ENERGY. The location "
            "is none, because a spectrum has no block and no time. The data are energy_percent "
            "(the percent of the energy in all the bands together, the value of the result), "
            "limit_percent (the limit), num_bands (the number of resonance bands of the target) "
            "and max_frequency_hz, window_s and frequency_oversampling (the arguments of the "
            "spectrum). The message is the percent, with up to 4 significant digits, the "
            'number of bands and the limit, for example "42.1 % of the gradient energy is in '
            'the 2 resonance bands (limit 30 %)".'
        ),
        promise=CheckPromise(
            on_pass=(
                f"At most {ACOUSTIC_BAND_ENERGY_LIMIT:g} % of the energy of the gradient spectrum "
                "of the file, from 0 Hz to 2000 Hz, is in the acoustic resonance bands of the "
                "target, all the bands together. The value does not change when the scan "
                "rotates the logical axes, because the RSS of the three axes does not."
            ),
            on_fail=(
                f"More than {ACOUSTIC_BAND_ENERGY_LIMIT:g} % of that energy is in the resonance "
                "bands, all the bands together. A fail does not need one band above "
                f"{ACOUSTIC_BAND_ENERGY_LIMIT:g} %."
            ),
            not_promised=(
                "That the scanner accepts the sequence, that the scan is quiet, or that the "
                f"gradient coil is safe: {ACOUSTIC_BAND_ENERGY_LIMIT:g} % is a rule of this "
                "package, not a limit of a vendor, and the scanner can have its own rules (for "
                "example the forbidden echo spacings of an EPI readout). The energy above "
                "2000 Hz. A short, strong burst at a resonance: the spectrum is the maximum over "
                "windows of 50 ms, so the sum of its squares is not the energy of the whole "
                "sequence, and a short burst can have a small share. The waveform that the "
                "scanner plays, when its interpreter makes it in another way than the check: "
                "when the GradientRasterTime or the BlockDurationRaster of the file differs from "
                "the raster of the target (timing.rasters fails), the value describes the "
                "waveform of the file only."
            ),
        ),
    )

    def run(self, ctx: RunContext) -> Result:
        spectrum: GradientSpectrum = ctx.analysis("gradient.spectrum")
        resonances = ctx.profile.acoustic_resonances or ()
        bands = [(f - bw / 2, f + bw / 2) for f, bw in resonances]
        for (f, bw), (_, high) in zip(resonances, bands, strict=True):
            if high > spectrum.max_frequency_hz:
                return ctx.result(
                    self.spec,
                    State.NOT_EVALUATED,
                    reason=(
                        f"the band {f:g} Hz, {bw:g} Hz wide reaches {high:g} Hz, above the "
                        f"spectrum (0 Hz to {spectrum.max_frequency_hz:g} Hz)"
                    ),
                )
        fields = {"limit": ACOUSTIC_BAND_ENERGY_LIMIT, "unit": "%", "location": None}
        if spectrum.reason == NO_GRADIENTS:
            return ctx.result(
                self.spec, State.PASS, value=0.0, reason="no gradient event", **fields
            )
        energy = np.asarray(spectrum.rss, dtype=np.float64) ** 2
        total = float(energy.sum())
        in_bands = np.zeros(energy.shape, dtype=bool)
        for low, high in bands:
            in_bands |= (spectrum.frequency_hz >= low) & (spectrum.frequency_hz <= high)
        value = 0.0 if total == 0 else 100 * float(energy[in_bands].sum()) / total
        state = State.FAIL if value > ACOUSTIC_BAND_ENERGY_LIMIT else State.PASS
        findings = ()
        if state is State.FAIL:
            findings = (self._finding(spectrum, value, len(bands)),)
        return ctx.result(
            self.spec, state, value=value, reason=_bands(len(bands)), findings=findings, **fields
        )

    @staticmethod
    def _finding(spectrum: GradientSpectrum, value: float, num_bands: int) -> Finding:
        return Finding(
            "ACOUSTIC_BAND_ENERGY",
            f"{value:.4g} % of the gradient energy is in the {_bands(num_bands)} "
            f"(limit {ACOUSTIC_BAND_ENERGY_LIMIT:g} %)",
            None,
            {
                "energy_percent": value,
                "limit_percent": ACOUSTIC_BAND_ENERGY_LIMIT,
                "num_bands": num_bands,
                "max_frequency_hz": spectrum.max_frequency_hz,
                "window_s": spectrum.window_s,
                "frequency_oversampling": spectrum.frequency_oversampling,
            },
        )


RESONANCE_ENERGY = _ResonanceEnergy()
