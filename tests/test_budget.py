import time

from scale_sequences import TR_BLOCKS, build_repeating

from pulseq_checks.profile import read_profile
from pulseq_checks.results import State
from pulseq_checks.run import run_checks

# The time in seconds that the fast checks have for 10^5 blocks, with the read of the file.
# Task 8.3 of the plan: three times the largest time. Locally (Apple M1 Max) the timed part
# takes 0.44 s; CI ran the whole test suite 2.5 times slower than this machine (3.15 s and
# 1.25 s), so about 1.1 s in CI, and 3 x 1.1 s = 3.3 s.
CI_BUDGET_S = 3.3
BLOCKS = 100_000

# The synthetic limits of `synthetic.SYSTEM`, the pypulseq default rasters, as in
# `scripts/budget.py`.
PROFILE = """\
format = 1
name = "budget"

[opts]
max_grad = 28
grad_unit = "mT/m"
max_slew = 150
slew_unit = "T/m/s"
rf_dead_time = 100e-6
rf_ringdown_time = 20e-6
adc_dead_time = 10e-6

[rasters]
GradientRasterTime = 10e-6
RadiofrequencyRasterTime = 1e-6
AdcRasterTime = 100e-9
BlockDurationRaster = 10e-6
"""


def test_the_fast_checks_of_100000_blocks_are_within_the_ci_budget(tmp_path):
    seq_path = tmp_path / "budget.seq"
    build_repeating(BLOCKS // TR_BLOCKS).write(str(seq_path))
    profile_path = tmp_path / "budget.toml"
    profile_path.write_text(PROFILE)
    profile = read_profile(profile_path)

    start = time.perf_counter()
    matrix = run_checks(seq_path, [profile], fast_only=True)
    seconds = time.perf_counter() - start

    assert matrix.results, "no fast check ran"
    assert not [r for r in matrix.results if r.state in (State.ERROR, State.NOT_EVALUATED)]
    assert seconds <= CI_BUDGET_S, f"{seconds:.1f} s for the fast checks, budget {CI_BUDGET_S} s"
