from typing import Dict, List, Optional, Tuple, Union


class KumaRestAPIUsers:
    """
    Методы для работы с пользователями
    """

    def __init__(self, base):
        self._base = base

    def search(self, **kwargs) -> Tuple[int, List | str]:
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
        return self._base._make_request("GET", "users", params=params)

    def get(
        self,
        id: str,
    ) -> Tuple[int, List | str]:
        """
        Get specified user by UUID
        Args:
            id (str): User UUID
        """
        return self._base._make_request("GET", f"users/id/{id}")

    def whoami(
        self,
    ) -> Tuple[int, List | str]:
        """
        Show info about token user
        """
        return self._base._make_request("GET", f"users/whoami")
