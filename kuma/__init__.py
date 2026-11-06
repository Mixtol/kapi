import logging
from typing import TYPE_CHECKING

from kuma._common.transfers import DownloadStream
from kuma.errors import APIError

if TYPE_CHECKING:
    from kuma.private import KumaPrivateAPI as PrivateClient
    from kuma.rest import KumaRestAPI as RestClient

__all__ = ["PrivateClient", "RestClient", "APIError", "DownloadStream"]

logging.getLogger(__name__).addHandler(logging.NullHandler())


def __getattr__(name):
    if name == "PrivateClient":
        from kuma.private import KumaPrivateAPI

        globals()[name] = KumaPrivateAPI
        return KumaPrivateAPI
    if name == "RestClient":
        from kuma.rest import KumaRestAPI

        globals()[name] = KumaRestAPI
        return KumaRestAPI
    raise AttributeError(name)


def __dir__():
    return sorted(set(globals()) | set(__all__))
