# pulseq-checks

`pulseq-checks` checks a [Pulseq](https://pulseq.github.io/) sequence against
the limits of one or more target scanners. You give a `.seq` file and a target
profile for each scanner. You get a result for each check and each target:
pass, fail, not evaluated or error. The `pulseq-check` command gives an exit
status for CI, and a Python function gives the same results as data.

The measurement modules that the checks use are in the package
[pulseq-analysis](https://github.com/mdtisdall/pulseq-analysis), a dependency
of `pulseq-checks`.

There are no default limits. A check that needs a value that the profile does
not give is "not evaluated". It is never a pass.

## Install

With uv, from the git URL and the tag:

```
uv add "pulseq-checks @ git+https://github.com/mdtisdall/pulseq-checks@v0.1.0rc2"
```

The package needs pypulseq 1.5.0.post1 with four commits that are not in a
release. `pyproject.toml` pins them from a fork in `[tool.uv.sources]`. uv
applies this pin for a project that depends on `pulseq-checks` by git URL. pip
does not.

## Example

A target profile, `prisma.toml`:

```toml
format = 1
name = "Prisma AS82"

[opts]
max_grad = 80
grad_unit = "mT/m"
max_slew = 200
slew_unit = "T/m/s"
rf_dead_time = 100e-6
rf_ringdown_time = 30e-6
adc_dead_time = 10e-6

[rasters]
GradientRasterTime = 10e-6
RadiofrequencyRasterTime = 1e-6
AdcRasterTime = 100e-9
BlockDurationRaster = 10e-6
```

Check a sequence against it, and require the slew check:

```
pulseq-check scan.seq --target prisma.toml --check gradient.slew.axis
```

The exit status is 0 when no check failed and each required check was
evaluated, 2 when a check failed, and 1 for an error. The profile has no SAFE
parameters, so `pns.safe` is "not evaluated": it does not change the status,
because the command did not name it.

## All the errors of a check

A result gives the worst value of a check. It can also have findings: one for
each problem that the check found, with a code, a message, the block and the
time, and the values. `timing.pypulseq` gives one finding for each error of
pypulseq's `check_timing`, and `timing.rasters` gives one finding for each
raster that differs from the target or that the file does not declare
correctly. The three gradient checks give one finding for each block, and
axis, that is above the limit, and `pns.safe` gives one finding for each
interval where the SAFE total is at or above 100 %. A plugin check can give its
own.

The summary on the console gives only the number of findings of each result.
To see them there, add `--show-findings`. To pass them to another tool, write
the JSON result, which has all of them:

```
pulseq-check scan.seq --target prisma.toml --json result.json
pulseq-check scan.seq --target prisma.toml --json - | next-tool
```

With `--json -` the JSON goes to the standard output and the summary to the
standard error. `--max-findings N` keeps the first `N` findings of each
result, and the result records how many it omitted.

In Python, each result has its findings:

```python
from pulseq_checks import read_profile, run_checks

matrix = run_checks("scan.seq", [read_profile("prisma.toml")])
for result in matrix.results:
    for finding in result.findings:
        print(result.check_id, finding.code, finding.location, finding.message)
```

`matrix.to_json()` gives the same JSON as the command, and
`ResultMatrix.from_json(text)` reads it again.

## Documents

- [`docs/usage.md`](docs/usage.md): the target profile, the check
  configuration, the command, the Python API, the result JSON, how to pass the
  findings to another tool, how to write a plugin check (also one that gives
  findings), and how a check uses the measurement modules of pulseq-analysis.
- [`docs/checks.md`](docs/checks.md): the specification of each check.
