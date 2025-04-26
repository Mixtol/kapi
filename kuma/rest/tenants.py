from typing import Dict, List, Optional, Tuple, Union


class KumaRestAPITenants:
    """
    Методы для работы с тенантами
    """

    def __init__(self, base):
        self._base = base

    def search(self, **kwargs) -> Tuple[int, List | str]:
        """
        Search tenants with filter
        Args:
            page (int): Pagination page (1 by default)
            id (List[str]): Tenants UUID filter
            name (str): Case-insensetine name regex filter
            main (bool): Only display 'Main' tenant
        """
        return self._base._make_request("GET", "tenants", params=kwargs)

    def create(
        self,
        name: str,
        eps_limit: int,
        desciption: str = "",
    ) -> Tuple[int, List | str]:
        """
        Create tenant
        Args:
            name (str): New tenant name
            eps_limit (int): New tenant EPS limit value
            description (str): New tenant description
        """
        json = {"name": name, "description": desciption, "epsLimit": eps_limit}
        return self._base._make_request("POST", "tenants/create", json=json)
