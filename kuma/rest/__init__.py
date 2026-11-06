import logging
from typing import Optional

from kuma._common.versions import (
    DEFAULT_VERSION,
    normalize_version,
    resolve_default_version,
)
from kuma.errors import APIError
from kuma.rest._base import KumaRestAPIBase, Timeout, Verify
from kuma.rest.active_lists import KumaRestAPIActiveLists
from kuma.rest.alerts import KumaRestAPIAlerts
from kuma.rest.assets import KumaRestAPIAssets
from kuma.rest.context_tables import KumaRestAPIContextTables
from kuma.rest.dictionaries import KumaRestAPIDictionaries
from kuma.rest.events import KumaRestAPIEvents
from kuma.rest.folders import KumaRestAPIFolders
from kuma.rest.incidents import KumaRestAPIIncidents
from kuma.rest.reports import KumaRestAPIReports
from kuma.rest.resources import KumaRestAPIResources
from kuma.rest.services import KumaRestAPIServices
from kuma.rest.settings import KumaRestAPISettings
from kuma.rest.system import KumaRestAPISystem
from kuma.rest.tasks import KumaRestAPITasks
from kuma.rest.tenants import KumaRestAPITenants
from kuma.rest.users import KumaRestAPIUsers


class KumaRestAPI(KumaRestAPIBase):
    """Kaspersky Unified Monitoring and Analytics REST API"""

    _module_classes = {
        "active_lists": KumaRestAPIActiveLists,
        "alerts": KumaRestAPIAlerts,
        "assets": KumaRestAPIAssets,
        "context_tables": KumaRestAPIContextTables,
        "dictionaries": KumaRestAPIDictionaries,
        "events": KumaRestAPIEvents,
        "folders": KumaRestAPIFolders,
        "incidents": KumaRestAPIIncidents,
        "reports": KumaRestAPIReports,
        "resources": KumaRestAPIResources,
        "services": KumaRestAPIServices,
        "settings": KumaRestAPISettings,
        "system": KumaRestAPISystem,
        "tasks": KumaRestAPITasks,
        "tenants": KumaRestAPITenants,
        "users": KumaRestAPIUsers,
    }

    def __init__(
        self,
        url: str,
        token: str,
        verify: Verify = True,
        timeout: Timeout = KumaRestAPIBase.DEFAULT_TIMEOUT,
        logger: Optional[logging.Logger] = None,
        version: str = DEFAULT_VERSION,
    ):
        version = resolve_default_version(version)
        super().__init__(url, token, verify, timeout, logger, version=version)
        self._modules = {}

    def get_version(self) -> str:
        """Read Core's major.minor release without changing the configured version.

        Uses public services listing; the server rejects a kind=core filter.
        Different patch/build versions in a Core cluster are treated as one release.
        Missing, malformed or conflicting Core versions raise APIError.
        """
        versions = set()
        seen_pages = set()
        page = 1
        while True:
            status, services = self.services.search(page=page)
            if not isinstance(services, list) or any(
                not isinstance(service, dict) for service in services
            ):
                raise APIError(
                    "Unexpected services response while reading Core version", status
                )
            for service in services:
                if service.get("kind") != "core":
                    continue
                try:
                    versions.add(normalize_version(service.get("version")))
                except (TypeError, ValueError) as exc:
                    raise APIError(
                        "Core returned an empty or invalid version", status
                    ) from exc
            if len(services) < 250:
                break
            signature = tuple(str(service.get("id")) for service in services)
            if signature in seen_pages:
                raise APIError(
                    "Services pagination repeated a page while reading Core version",
                    status,
                )
            seen_pages.add(signature)
            page += 1
        if not versions:
            raise APIError(
                "Core version is not visible in the public services list", status
            )
        if len(versions) != 1:
            raise APIError(
                "Core nodes report different major.minor versions: "
                + ", ".join(sorted(versions)),
                status,
            )
        return versions.pop()

    def _get_module(self, name: str):
        if name in self._module_classes:
            modules = self.__dict__.setdefault("_modules", {})
            if name not in modules:
                modules[name] = self._module_classes[name](self)
            return modules[name]
        raise AttributeError(name)

    def __getattr__(self, name: str):
        return self._get_module(name)

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(self._module_classes.keys()))

    # Explicit module properties for IDE autocompletion
    @property
    def active_lists(self) -> KumaRestAPIActiveLists:
        return self._get_module("active_lists")

    @property
    def alerts(self) -> KumaRestAPIAlerts:
        return self._get_module("alerts")

    @property
    def assets(self) -> KumaRestAPIAssets:
        return self._get_module("assets")

    @property
    def context_tables(self) -> KumaRestAPIContextTables:
        return self._get_module("context_tables")

    @property
    def dictionaries(self) -> KumaRestAPIDictionaries:
        return self._get_module("dictionaries")

    @property
    def events(self) -> KumaRestAPIEvents:
        return self._get_module("events")

    @property
    def folders(self) -> KumaRestAPIFolders:
        return self._get_module("folders")

    @property
    def incidents(self) -> KumaRestAPIIncidents:
        return self._get_module("incidents")

    @property
    def reports(self) -> KumaRestAPIReports:
        return self._get_module("reports")

    @property
    def resources(self) -> KumaRestAPIResources:
        return self._get_module("resources")

    @property
    def services(self) -> KumaRestAPIServices:
        return self._get_module("services")

    @property
    def settings(self) -> KumaRestAPISettings:
        return self._get_module("settings")

    @property
    def system(self) -> KumaRestAPISystem:
        return self._get_module("system")

    @property
    def tasks(self) -> KumaRestAPITasks:
        return self._get_module("tasks")

    @property
    def tenants(self) -> KumaRestAPITenants:
        return self._get_module("tenants")

    @property
    def users(self) -> KumaRestAPIUsers:
        return self._get_module("users")


KumaAPI = KumaRestAPI
__all__ = ["KumaRestAPI", "KumaAPI"]
