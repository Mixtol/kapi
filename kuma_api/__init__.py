"""Alternative top-level imports for the kuma-api distribution."""

from typing import TYPE_CHECKING

import kuma as _kuma

if TYPE_CHECKING:
    from kuma import APIError, DownloadStream, PrivateClient, RestClient

__all__ = list(_kuma.__all__)


def __getattr__(name):
    if name in __all__:
        value = getattr(_kuma, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
