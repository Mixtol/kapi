from typing import Dict, List, Optional, Tuple, Union

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPIResources(KumaRestAPIModule):
    """Methods for Resources."""

    def search(self, **kwargs) -> Tuple[int, List | str]:
        """
        Search resources
        Args:
            page (int): Pagination page (1 by default)
            id (List[str]): Resources UUID filter
            tenantID (List[str]): Tenants UUID filter
            name (str): Case-insensetine name regex filter
            kind (List[str]): Resource kind filter (filter|correlationRule|...)
            userID (List[str]): Creator filter
        """
        params = {
            **kwargs,
        }
        return self._make_request("GET", "resources", params=params)

    def download(self, id: str) -> Tuple[int, List | str]:
        """
        Download export file data
        Args:
            id (str): File ID as a result of resource export request.
        """
        return self._make_request("GET", f"download/{id}")

    def export(
        self,
        resources_ids: List[str],
        tenant_id: str,
        password: str = "Kuma_secret_p@$$w0rd",
    ) -> Tuple[int, List | str]:
        """
        Generating export file ID for download
        Args:
            resources_ids (List[str]): Resources UUID list to download
            tenant_id (str): Resources tenant UUID
            password (str): Future file open password
        """
        json = {"ids": resources_ids, "password": password, "tenantID": tenant_id}
        return self._make_request("POST", "resources/export", json=json)

    def import_data(
        self,
        file_id: str,
        tenant_id: str,
        password: str = "Kuma_secret_p@$$w0rd",
        actions: Optional[Dict] = None,
    ) -> Tuple[int, List | str]:
        """
        Import content file uploded early from /upload method
        Args:
            file_id (str): Uploaded file UUID returned by Core
            tenant_id (str): Destination resource tenant UUID
            password (str): File open password
            actions (dict): Conflict resolve rules, see examples
                0=ignore, 1=import, 2=replace
        """
        json = {
            "actions": actions,
            "fileID": file_id,
            "password": password,
            "tenantID": tenant_id,
        }
        return self._make_request("POST", "resources/import", json=json)

    def toc(
        self,
        file_id: str,
        password: str = "Kuma_secret_p@$$w0rd",
    ) -> Tuple[int, List | str]:
        """
        View content of uploaded resource file, recommended to use before import_data
        Args:
            file_id (str): Uploaded file UUID returned by Core
            password (str): File open password
        """
        json = {
            "fileID": file_id,
            "password": password,
        }
        return self._make_request("POST", f"resources/toc", json=json)

    def upload(self, data: Union[bytes, str]) -> Tuple[int, List | str]:
        """
        Download export file data
        Args:
            data (binary): File data or file path
        """
        if isinstance(data, str):
            with open(data, "rb") as f:
                data = f.read()
        return self._make_request("POST", "resources/upload", data=data)

    def create(
        self,
        kind: str,
        resource: dict,
    ) -> Tuple[int, List | str]:
        """
        Create resource from JSON
        Args:
            kind (str): Resource kind (correlationRule|dictionary|...)
            resource (dict): Resource JSON object, see examples.
        """
        return self._make_request("POST", f"resources/{kind}/create", json=resource)

    def validate(
        self,
        kind: str,
        resource: dict,
    ) -> Tuple[int, List | str]:
        """
        Validate resource JSON
        Args:
            kind (str): Resource kind (correlationRule|dictionary|...)
            resource (dict): Resource JSON object, see /create method.
        """
        return self._make_request("POST", f"resources/{kind}/validate", json=resource)

    def get(self, kind: str, id: str) -> Tuple[int, List | str]:
        """
        Get resource JSON
        Args:
            id (str): Resource UUID
            kind (str): Resource kind (correlationRule|dictionary|...)
        """
        return self._make_request("GET", f"resources/{kind}/{id}")

    def put(self, kind: str, id: str, resource: dict) -> Tuple[int, List | str]:
        """
        Modify|Update resource with JSON
        Args:
            id (str): Resource UUID
            kind (str): Resource kind (correlationRule|dictionary|...)
            resource (dict): Resource JSON object, see /create method.
        """
        return self._make_request("PUT", f"resources/{kind}/{id}", json=resource)

    def list_history(self, kind: str, id: str) -> Tuple[int, List | str]:
        """Getting all resource history versions
        id (str): Resource UUID
        kind (str): Resource kind (correlationRule|dictionary|...)
        """
        return self._make_request("GET", f"resources/{kind}/{id}/history")

    def get_history(
        self, kind: str, id: str, history_id: int
    ) -> Tuple[int, List | str]:
        """Getting resource history version with specified kind, ID and version number
        id (str): Resource UUID
        kind (str): Resource kind (correlationRule|dictionary|...)
        history_id (int): Number of version
        """
        return self._make_request("GET", f"resources/{kind}/{id}/history/{history_id}")

    def revert(self, kind: str, id: str, history_id: int) -> Tuple[int, List | str]:
        """Reverting resource history version with specified kind, ID and version number
        id (str): Resource UUID
        kind (str): Resource kind (correlationRule|dictionary|...)
        history_id (int): Number of version
        """
        return self._make_request("POST", f"resources/{kind}/{id}/history/{history_id}")
