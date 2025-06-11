from typing import List, Tuple

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPITenants(KumaRestAPIModule):
    """Methods for Tenants."""
    def search(self, **kwargs) -> Tuple[int, List | str]:
        """
        Search tenants with filter
        Args:
            page (int): Pagination page (1 by default)
            id (List[str]): Tenants UUID filter
            name (str): Case-insensetine name regex filter
            main (bool): Only display 'Main' tenant
        """
        return self._make_request("GET", "tenants", params=kwargs)

    def create(
        self,
        name: str,
        eps_limit: int,
        description: str = "",
    ) -> Tuple[int, List | str]:
        """
        Create tenant
        Args:
            name (str): New tenant name
            eps_limit (int): New tenant EPS limit value
            description (str): New tenant description
        """
        json = {"name": name, "description": description, "epsLimit": eps_limit}
        return self._make_request("POST", "tenants/create", json=json)
