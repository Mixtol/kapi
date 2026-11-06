from kuma.rest._base import APIResult, KumaRestAPIModule
from kuma.rest._pagination import iter_pages


class KumaRestAPIServices(KumaRestAPIModule):
    """Methods for Services."""

    def iter_search(self, *, page=1, **filters):
        """Выдавать метаданные сервисов до пустой страницы; отклонять повторы страниц."""
        return iter_pages(self.search, page=page, **filters)

    def reload_resource(self, resource_id):
        """Перезагрузить сервисы с указанным resourceID через публичный API.

        Возвращает (200, [{id, status}]); без совпадений список пуст.
        Останавливается при первой ошибке; предыдущие перезагрузки не отменяются.
        """
        if not isinstance(resource_id, str) or not resource_id:
            raise ValueError("resource_id должен быть непустой строкой")
        result = []
        for service in self.iter_search():
            if service.get("resourceID") == resource_id:
                status, _ = self.reload(service["id"])
                result.append({"id": service["id"], "status": status})
        return 200, result

    def search(
        self,
        **kwargs,
    ) -> APIResult:
        """
        Search services with filtering.
        Args:
            page (int): Listing page of result (250 alerts per page)
            id (List[str]): Search for specified services
            tenantID (List[str]): Tenant IDs filter
            name (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            fqdn (str): FQDN filter (regex in 3.4, substring in 4.x)
            kind (str): Service kind (collector|correlator|...)
            paired (bool): Services that executed the first start.
        """
        params = {**kwargs}
        return self._make_request("GET", "services", params=params)

    def create(self, resource_id: str) -> APIResult:
        """
        Create service from resource id.
        Args:
            resource_id (str): Resource template UUID
        """
        return self._make_request(
            "POST", "services/create", json={"resourceID": resource_id}
        )

    def reload(self, service_id: str) -> APIResult:
        """
        Reload service (Updating JSON from Core).
        Args:
            service_id (str): Service UUID
        """
        return self._make_request("POST", f"services/{self._path(service_id)}/reload")

    def restart(self, service_id: str) -> APIResult:
        """
        Restart service (systemctl restart ...)
        Args:
            service_id (str): Service UUID
        """
        return self._make_request("POST", f"services/{self._path(service_id)}/restart")
