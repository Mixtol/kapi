"""Compatibility imports; implementation lives in kuma._common.versions."""

from kuma._common.versions import (
    DEFAULT_VERSION,
    LATEST_VERSION,
    SUPPORTED_VERSIONS,
    _DefaultVersion,
    normalize_version,
    resolve_default_version,
)

__all__ = [
    "DEFAULT_VERSION",
    "LATEST_VERSION",
    "SUPPORTED_VERSIONS",
    "normalize_version",
    "resolve_default_version",
]
