from typing import List, Tuple, Union

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPIUsers(KumaRestAPIModule):
    """Methods for Users."""
    def search(self, **kwargs) -> Tuple[int, Union[List, str]]:
        """
        Search tenants with filter
        Args:
            pattern (str): Search by name, login, and email case-insensitive regex
            login (str): Case-insensetine name regex filter
            email (str): Case-insensetine name regex filter
            name (str): Case-insensetine name regex filter
            sort (str): For ASC <field> or add <-field> for DESC
            excludeDisabled (bool): Exclude disabled users
            role (List[str]): Role IDs filter, see examples.
            tenant (List[str]): Tenants IDs filter
            page (int): Pagination page (1 by default)
            size (int): Page size (250 by default)
        """
        params = {**kwargs}
        return self._make_request("GET", "users", params=params)

    def get(self, id: str) -> Tuple[int, Union[List, str]]:
        """
        Get specified user by UUID
        Args:
            id (str): User UUID
        """
        return self._make_request("GET", f"users/id/{id}")

    def whoami(self) -> Tuple[int, Union[List, str]]:
        """
        Show info about token user
        """
        return self._make_request("GET", f"users/whoami")
