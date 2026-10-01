# TODO

- **Findings of more checks (section 8 of `docs/plans/check-findings.md`).**
  Only `timing.pypulseq` and `timing.rasters` give findings. These checks can
  give them later: `gradient.amplitude.axis` and `gradient.slew.axis` (one
  finding for each block above the limit, by axis),
  `gradient.amplitude.any-orientation` (one finding for each block where |G|
  is above the limit) and `pns.safe` (one finding for each interval where the
  PNS total is at or above 100 %). Each check is its own task. In the release
  candidates, the specification of each check stays version 1 (design
  section 5.4): its findings go into `CHANGELOG.md` only. From the first
  final release (0.1.0) on, decide for each check whether its version
  changes. For `timing.pypulseq` it did not, because the findings do not
  change the verdict (decision D6 of the plan).

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
  pulseq-reports gives each commit and how to change the pin. pulseq-checks
  and pulseq-reports must pin the same commit. When a pypulseq release has
  all four changes: pin that release in `[project] dependencies`, remove
  `[tool.uv.sources]`, and change `pns_levels.py` to the released name of the
  chunk function. Do this in the two repositories at the same time.
