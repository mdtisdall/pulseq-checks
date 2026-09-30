# pulseq-checks

`pulseq-checks` checks a [Pulseq](https://pulseq.github.io/) sequence against
the limits of one or more target scanners. You give a `.seq` file and a target
profile for each scanner. You get a result for each check and each target:
pass, fail, not evaluated or error. The `pulseq-check` command gives an exit
status for CI, and a Python function gives the same results as data.

There are no default limits. A check that needs a value that the profile does
not give is "not evaluated". It is never a pass.

## Install

With uv, from the git URL and the tag:

```
uv add "pulseq-checks @ git+https://github.com/mdtisdall/pulseq-checks@v0.1.0rc1"
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

## Documents

- [`docs/usage.md`](docs/usage.md): the target profile, the check
  configuration, the command, the Python API, the result JSON and how to write
  a plugin check.
- [`docs/checks.md`](docs/checks.md): the specification of each check.
