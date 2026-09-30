# TODO

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
