"""meshcli - A CLI tool for mesh operations."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("meshctl")
except PackageNotFoundError:
    # Package is not installed, so we can't determine the version this way.
    # This can happen during development.
    __version__ = "unknown"
