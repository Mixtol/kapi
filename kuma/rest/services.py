from typing import Dict, List, Optional, Tuple, Union


class KumaRestAPIServices:
    """
    Методы для работы с сервисами
    """

    def __init__(self, base):
        self._base = base

    def search(
        self,
        **kwargs,
    ) -> tuple[int, dict | str]:
        """
        Search services with filtering.
        Args:
            page (int): Listing page of result (250 alerts per page)
            id (List[str]): Search for specified services
            tenantID (List[str]): Tenant IDs filter
            name (str): Case-insensetine name regex filter
            fqnd (str): Case-insensetine FQDN regex filter
            kind (str): Service kind (collector|correlator|...)
            paired (bool): Services that executed the first start.
        """
        params = {**kwargs}
        return self._base._make_request("GET", "services", params=params)

    def create(self, resource_id: str) -> Tuple[int, Dict]:
        """
        Create service from resource id.
        Args:
            resource_id (str): Resource template UUID
        """
        return self._base._make_request(
            "POST", "services/create", json={"resourceID": resource_id}
        )

    def reload(self, service_id: str) -> Tuple[int, Dict]:
        """
        Reload service (Updatin JSON from Core).
        Args:
            service_id (str): Service UUID
        """
        return self._base._make_request("POST", f"services/{service_id}/reload")

    def restart(self, service_id: str) -> Tuple[int, Dict]:
        """
        Restart service (systemctl restart ...)
        Args:
            service_id (str): Service UUID
        """
        return self._base._make_request("POST", f"services/{service_id}/restart")
