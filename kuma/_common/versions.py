"""KUMA release parsing and supported public API versions."""

import re
import warnings

SUPPORTED_VERSIONS = ("3.4", "4.0", "4.1", "4.2")
LATEST_VERSION = SUPPORTED_VERSIONS[-1]
VERSION_FALLBACKS = {"4.1": "4.0"}


class _DefaultVersion(str):
    """Distinguish omission from an explicitly selected latest release."""


DEFAULT_VERSION = _DefaultVersion(LATEST_VERSION)


def resolve_contract_version(version: str) -> str:
    """Select a wire contract without replacing the requested KUMA release."""
    normalized = normalize_version(version)
    return VERSION_FALLBACKS.get(normalized, normalized)


def resolve_default_version(version: str) -> str:
    """Accept an empty legacy version argument as an omitted selection."""
    if version is DEFAULT_VERSION or version == "":
        warnings.warn(
            "KUMA version was not specified; using the latest supported "
            f"version ({LATEST_VERSION}). Pass version explicitly, "
            "for example version='3.4'.",
            UserWarning,
            stacklevel=3,
        )
        return LATEST_VERSION
    return version


def normalize_version(version: str) -> str:
    """Keep major.minor, accepting numeric patch/build components when present."""
    if not isinstance(version, str):
        raise TypeError("KUMA version must be a string such as '3.4'")
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)(?:\.[0-9]+)*", version.strip())
    if match is None:
        raise ValueError("KUMA version must have the form '3.4' or '3.4.1.53'")
    return f"{int(match[1])}.{int(match[2])}"
