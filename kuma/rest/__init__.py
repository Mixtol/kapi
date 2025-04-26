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

    def __init__(self, url: str, token: str, verify):
        self.base = KumaRestAPIBase(url, token, verify)

        # Основные модули
        self.active_lists = KumaRestAPIActiveLists(self.base)
        self.alerts = KumaRestAPIAlerts(self.base)
        self.assets = KumaRestAPIAssets(self.base)
        self.context_tables = KumaRestAPIContextTables(self.base)
        self.dictionaries = KumaRestAPIDictionaries(self.base)
        self.events = KumaRestAPIEvents(self.base)
        self.folders = KumaRestAPIFolders(self.base)
        self.incidents = KumaRestAPIIncidents(self.base)
        self.reports = KumaRestAPIReports(self.base)
        self.resources = KumaRestAPIResources(self.base)
        self.services = KumaRestAPIServices(self.base)
        self.settings = KumaRestAPISettings(self.base)
        self.system = KumaRestAPISystem(self.base)
        self.tasks = KumaRestAPITasks(self.base)
        self.tenants = KumaRestAPITenants(self.base)
        self.users = KumaRestAPIUsers(self.base)

        # Расширенные функции
        #


__all__ = ["KumaAPI"]
