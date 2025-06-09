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

    def __getattr__(self, name):
        if name in self._module_classes:
            if name not in self._modules:
                self._modules[name] = self._module_classes[name](self)
            return self._modules[name]
        raise AttributeError(name)

    # Расширенные функции
    #


KumaAPI = KumaRestAPI
__all__ = ["KumaRestAPI", "KumaAPI"]
