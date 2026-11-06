from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPITenants(KumaRestAPIModule):
    """Methods for Tenants."""

    def search(self, **kwargs) -> APIResult:
        """
        Search tenants with filters
        Args:
            page (int): Pagination page (1 by default)
            id (List[str]): Tenants UUID filter
            name (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            main (bool): Only display 'Main' tenant
        """
        return self._make_request("GET", "tenants", params=kwargs)

    def create(
        self,
        name: str,
        eps_limit: int,
        description: str = "",
    ) -> APIResult:
        """
        Create tenant
        Args:
            name (str): New tenant name
            eps_limit (int): New tenant EPS limit value
            description (str): New tenant description
        """
        json = {"name": name, "description": description, "epsLimit": eps_limit}
        return self._make_request("POST", "tenants/create", json=json)
