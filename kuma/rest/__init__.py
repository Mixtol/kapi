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

    def __init__(
        self,
        url: str,
        token: str,
        verify,
        timeout: int = KumaRestAPIBase.DEFAULT_TIMEOUT,
    ):
        # Инициализируем родительский класс
        super().__init__(url, token, verify, timeout)

        # Основные модули
        self.active_lists = KumaRestAPIActiveLists(self)
        self.alerts = KumaRestAPIAlerts(self)
        self.assets = KumaRestAPIAssets(self)
        self.context_tables = KumaRestAPIContextTables(self)
        self.dictionaries = KumaRestAPIDictionaries(self)
        self.events = KumaRestAPIEvents(self)
        self.folders = KumaRestAPIFolders(self)
        self.incidents = KumaRestAPIIncidents(self)
        self.reports = KumaRestAPIReports(self)
        self.resources = KumaRestAPIResources(self)
        self.services = KumaRestAPIServices(self)
        self.settings = KumaRestAPISettings(self)
        self.system = KumaRestAPISystem(self)
        self.tasks = KumaRestAPITasks(self)
        self.tenants = KumaRestAPITenants(self)
        self.users = KumaRestAPIUsers(self)

        # Расширенные функции
        #


__all__ = ["KumaAPI"]
