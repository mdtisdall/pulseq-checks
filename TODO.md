# TODO

- **Unequal rasters (R6 of `docs/plans/pulseq-checks.md`).** Version 1 of
  `timing.rasters` passes only when the rasters of the file equal the
  rasters of the target. A file with a coarser raster (F = k x T) has its
  block durations, ADC dwell times and event edges on the target raster,
  but its gradient and RF shapes are samples at the cell centres of F, and
  the Pulseq specification does not say how an interpreter plays them on T.
  Study how specific interpreters (for example the Siemens interpreter)
  handle a file raster that differs from the system raster, and add a rule
  for unequal rasters only where that behavior is known. A check that is
  not based on the behavior of an interpreter does not assert anything of
  value.

- **Worst-case slew and PNS under rotation.** `gradient.slew.axis` and
  `pns.safe` measure the logical axes of the file, so what they promise holds
  only for a scan with no rotation: a rotation can put the slews of two or
  three logical axes on one physical axis, and the SAFE parameters differ for
  each physical axis. Study whether the data that the checks already have (the
  gradient waveforms of the three axes) can give the worst case over all
  rotations, as `gradient.amplitude.any-orientation` does for the amplitude.
  For the slew, the magnitude of the slew vector bounds each physical axis. For
  PNS, the SAFE model filters each axis with its own parameters, so the worst
  case is not a simple bound and needs its own study. This would be a separate
  output (a new check or a new value), not a replacement for the checks of
  today.

- **The convention declaration (decision 10 of
  `docs/plans/pulseq-checks.md`).** Where does a sequence declare its
  coordinate and sign conventions (section 6.2), until the Pulseq community
  has a convention? Version 1 has no convention checks. A later proposal of
  `[DEFINITIONS]` keys to pypulseq and MATLAB Pulseq can include the keys for
  the system limits (section 5.11).
- **Move from the pypulseq fork to a pypulseq release (decision 2 of
  `docs/plans/pulseq-checks-v1.md`, section 2.4).** This package pins
  pypulseq from the fork `mdtisdall/pypulseq` in `[tool.uv.sources]` of
  `pyproject.toml`: the tag `pulseq-reports-pin-1`, commit `a74ab06`. That is
  the release 1.5.0.post1 with four commits: the SAFE PNS filter as a
  recursion, `calc_pns` in chunks (with the private
  `_safe_gwf_to_pns_chunk`), the `get_block` fix for oversampled arbitrary
  gradients (upstream PR #424), and the read fix of upstream #359. The item
  "Move from the pypulseq fork to a pypulseq release" in the `TODO.md` of
  pulseq-reports gives each commit and how to change the pin. pulseq-checks,
  pulseq-analysis and pulseq-reports all pin the same commit (decision T12 of
  `docs/plans/pulseq-analysis.md`). When a pypulseq release has
  all four changes: pin that release in `[project] dependencies`, remove
  `[tool.uv.sources]`, and change `pns_levels.py` of pulseq-analysis to the
  released name of the chunk function. Do this in the three repositories at
  the same time.
