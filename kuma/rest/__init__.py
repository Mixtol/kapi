from ._base import KumaRestAPIBase
from .active_lists import KumaRestAPIActiveLists
from .alerts import KumaRestAPIAlerts
from .assets import KumaRestAPIAssets
from .context_tables import KumaRestAPIContextTables
from .dictionaries import KumaRestAPIDictionaries
from .events import KumaRestAPIEvents
from .folders import KumaRestAPIFolders
from .incidents import KumaRestAPIIncidents
from .reports import KumaRestAPIReports
from .resources import KumaRestAPIResources
from .services import KumaRestAPIServices
from .settings import KumaRestAPISettings
from .system import KumaRestAPISystem
from .tasks import KumaRestAPITasks
from .tenants import KumaRestAPITenants
from .users import KumaRestAPIUsers


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
        verify,
        timeout: int = KumaRestAPIBase.DEFAULT_TIMEOUT,
    ):
        super().__init__(url, token, verify, timeout)
        self._modules = {}

    def _get_module(self, name):
        if name in self._module_classes:
            if name not in self._modules:
                self._modules[name] = self._module_classes[name](self)
            return self._modules[name]
        raise AttributeError(name)

    def __getattr__(self, name):
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
