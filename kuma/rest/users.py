from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPIUsers(KumaRestAPIModule):
    """Methods for Users."""

    def search(self, **kwargs) -> APIResult:
        """
        Search users with filters
        Args:
            pattern (str): Search by name, login, and email case-insensitive filter (regex in 3.4, substring in 4.x)
            login (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            email (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            name (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            sort (str): For ASC <field> or add <-field> for DESC
            excludeDisabled (bool): Exclude disabled users
            role (List[str]): Role IDs filter, see examples.
            tenant (List[str]): Tenants IDs filter
            page (int): Pagination page (1 by default)
            size (int): Page size (250 by default)
        """
        params = {**kwargs}
        return self._make_request("GET", "users/", params=params)

    def get(self, id: str) -> APIResult:
        """
        Get specified user by UUID
        Args:
            id (str): User UUID
        """
        return self._make_request("GET", f"users/id/{self._path(id)}")

    def whoami(self) -> APIResult:
        """
        Show info about token user
        """
        return self._make_request("GET", f"users/whoami")
