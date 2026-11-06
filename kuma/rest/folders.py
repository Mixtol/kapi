from typing import List

from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPIFolders(KumaRestAPIModule):
    """Methods for Folders."""

    def search(self, tenants_ids: List[str], **kwargs) -> APIResult:
        """
        Searching folders info
        Args:
            tenants_ids (List[str]): Target tenant IDs (required).
            id (List[str]): Folder UUID
            name (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            limit (int): Maximum number of entities to return
            offset (int): Number of entities to skip
            order (str): Columns for sorting ('-' is for DESC)
            kind (str): resource|report|dashboard
            subKind (str): KUMA resource type name (activeList|storage|...).
            column** (str): Returned columns of JSON (use several times)
        """
        params = {
            "tenantIDs": tenants_ids,
            **kwargs,
        }
        return self._make_request("GET", "folders/", params=params)
