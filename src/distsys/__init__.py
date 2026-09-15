"""Advanced Distributed System."""

from importlib.metadata import PackageNotFoundError, version

_DISTRIBUTION_NAME = "advanced-distributed-system"

try:
    __version__ = version(_DISTRIBUTION_NAME)
except PackageNotFoundError:
    __version__ = "0+unknown"
