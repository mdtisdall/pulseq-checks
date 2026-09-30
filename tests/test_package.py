import importlib.metadata
import tomllib
from pathlib import Path

import pulseq_checks

ROOT = Path(__file__).resolve().parent.parent


def test_the_package_imports_and_has_the_version_of_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert Path(pulseq_checks.__file__).resolve().parent == ROOT / "src" / "pulseq_checks"
    assert importlib.metadata.version("pulseq-checks") == pyproject["project"]["version"]
