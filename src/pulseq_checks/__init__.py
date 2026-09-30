"""Check a Pulseq sequence against the limits of one or more target scanners."""

from .config import CheckConfig, ConfigError, read_check_config
from .grad_limits import HardwareLimits
from .profile import ProfileError, TargetProfile, read_profile
from .results import CheckRunError, Location, Result, ResultMatrix, State, TargetInfo
from .rules import CheckRule, CheckSpec, RunContext
from .run import RunError, run_checks

__all__ = [
    "CheckConfig",
    "CheckRule",
    "CheckRunError",
    "CheckSpec",
    "ConfigError",
    "HardwareLimits",
    "Location",
    "ProfileError",
    "Result",
    "ResultMatrix",
    "RunContext",
    "RunError",
    "State",
    "TargetInfo",
    "TargetProfile",
    "read_check_config",
    "read_profile",
    "run_checks",
]
