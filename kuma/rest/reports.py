from typing import List

from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPIReports(KumaRestAPIModule):
    """Methods for Reports."""

    def search(self, tenants_ids: List[str], **kwargs) -> APIResult:
        """
        Searching reports info
        Args:
            tenants_ids (List[str]): List of tenant filter
            id (List[str]): Report UUID
            name (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            limit (int): Maximum number of entities to return
            offset (int): Number of entities to skip
            order (str): Columns for sorting ('-' is for DESC)
            column** (str): Returned columns of JSON (use several times)
        """
        params = {"tenantIDs": tenants_ids, **kwargs}
        return self._make_request("GET", "reports/", params=params)
