from typing import List, Tuple, Union

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPIFolders(KumaRestAPIModule):
    """Methods for Folders."""
    def search(
        self, tenants_ids: List[str], **kwargs
    ) -> Tuple[int, Union[List, str]]:  # TODO: Use tenants_ids
        """
        Searching folders info
        Args:
            tenants_ids* (int): Listing of tenants where are folders
            id (List[str]): Folder UUID
            name (str): Case-insensetine name regex filter
            limit (int): Maximum number of entities to return
            offset (int): Number of entities to skip
            order (str): Columns for sorting ('-' is for DESC)
            kind (str): resource|report|dashboard
            subkind (str): Kuma resource type name (activeList|storage|...etc)
            column** (str): Returned columns of JSON (use several times)
        """
        params = {
            **kwargs,
        }
        return self._make_request("GET", "folders", params=params)
