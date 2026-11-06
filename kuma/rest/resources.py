import os
from copy import deepcopy
from typing import Dict, List, Optional

from kuma._common.transfers import CHUNK_SIZE
from kuma.rest._base import APIResult, KumaRestAPIModule, Timeout
from kuma.rest.content_search import ResourceContentSearch
from kuma.rest.resource_workflows import PublicResourceWorkflows


class KumaRestAPIResources(
    ResourceContentSearch, PublicResourceWorkflows, KumaRestAPIModule
):
    """Methods for Resources."""

    def search(self, **kwargs) -> APIResult:
        """
        Search resources
        Args:
            page (int): Pagination page (1 by default)
            id (List[str]): Resources UUID filter
            tenantID (List[str]): Tenants UUID filter
            name (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            kind (List[str]): Resource kind filter (filter|correlationRule|...)
            userID (List[str]): Creator filter
        """
        params = {
            **kwargs,
        }
        return self._make_request("GET", "resources", params=params)

    def download(
        self,
        id: str,
        filepath=None,
        *,
        stream=True,
        chunk_size=CHUNK_SIZE,
        timeout=None,
        legacy=False,
    ):
        """
        Download export file data
        Args:
            id (str): File ID as a result of resource export request.
        """
        endpoint = (
            f"resources/download/{self._path(id)}"
            if legacy
            else f"download/{self._path(id)}"
        )
        return self._download(
            endpoint, filepath, stream=stream, chunk_size=chunk_size, timeout=timeout
        )

    def export(
        self,
        resources_ids: List[str],
        tenant_id: str,
        password: Optional[str] = None,
        *,
        timeout: Optional[Timeout] = None,
    ) -> APIResult:
        """
        Generating export file ID for download
        Args:
            resources_ids (List[str]): Resources UUID list to download
            tenant_id (str): Resources tenant UUID
            password (str): Future file open password
            timeout: Seconds or (connect, read) seconds; None uses the client timeout
        """
        if not password:
            raise ValueError("An explicit export password is required")
        password_field = "password" if self.contract_version == "3.4" else "newPassword"
        body = {"ids": resources_ids, password_field: password, "tenantID": tenant_id}
        return self._make_request(
            "POST", "resources/export", json=body, timeout=timeout
        )

    def import_data(
        self,
        file_id: str,
        tenant_id: str,
        password: Optional[str] = None,
        actions: Optional[Dict] = None,
    ) -> APIResult:
        """
        Import content file uploaded earlier from /upload method
        Args:
            file_id (str): Uploaded file UUID returned by Core
            tenant_id (str): Destination resource tenant UUID
            password (str): File open password
            actions (dict): Conflict resolve rules, see examples
                0=ignore, 1=import, 2=replace
        """
        if not password:
            raise ValueError("An explicit import password is required")
        json = {
            "actions": {} if actions is None else actions,
            "fileID": file_id,
            "password": password,
            "tenantID": tenant_id,
        }
        return self._make_request("POST", "resources/import", json=json)

    def toc(
        self,
        file_id: str,
        password: Optional[str] = None,
    ) -> APIResult:
        """
        View content of uploaded resource file, recommended to use before import_data
        Args:
            file_id (str): Uploaded file UUID returned by Core
            password (str): File open password
        """
        if not password:
            raise ValueError("An explicit resource file password is required")
        json = {
            "fileID": file_id,
            "password": password,
        }
        return self._make_request("POST", f"resources/toc", json=json)

    def upload(self, data=None, *, filepath=None, timeout=None, chunk_size=CHUNK_SIZE):
        """
        Upload a resource archive from a path, bytes, or a binary stream.
        Args:
            data (binary): File data or file path
        """
        if isinstance(data, (str, os.PathLike)):
            if filepath is not None:
                raise ValueError("Specify either filepath or data, not both")
            filepath, data = data, None
        return self._upload(
            "resources/upload",
            data,
            filepath=filepath,
            timeout=timeout,
            chunk_size=chunk_size,
        )

    def create(
        self,
        kind: str,
        resource: dict,
    ) -> APIResult:
        """
        Create resource from JSON
        Args:
            kind (str): Resource kind (correlationRule|dictionary|...)
            resource (dict): Resource JSON object, see examples.
        """
        return self._make_request(
            "POST", f"resources/{self._path(kind)}/create", json=resource
        )

    def validate(
        self,
        kind: str,
        resource: dict,
    ) -> APIResult:
        """
        Validate resource JSON
        Args:
            kind (str): Resource kind (correlationRule|dictionary|...)
            resource (dict): Resource JSON object, see /create method.
        """
        return self._make_request(
            "POST", f"resources/{self._path(kind)}/validate", json=resource
        )

    def get(self, kind: str, id: str, *, filter_code_only=None, **kwargs) -> APIResult:
        """
        Get resource JSON
        Args:
            id (str): Resource UUID
            kind (str): Resource kind (correlationRule|dictionary|...)
        """
        if filter_code_only is not None:
            kwargs["filterCodeOnly"] = filter_code_only
        return self._make_request(
            "GET", f"resources/{self._path(kind)}/{self._path(id)}", params=kwargs
        )

    def put(self, kind: str, id: str, resource: dict) -> APIResult:
        """
        Modify|Update resource with JSON
        Args:
            id (str): Resource UUID
            kind (str): Resource kind (correlationRule|dictionary|...)
            resource (dict): Resource JSON object, see /create method.
        """
        return self._make_request(
            "PUT", f"resources/{self._path(kind)}/{self._path(id)}", json=resource
        )

    def list_history(self, kind: str, id: str, **kwargs) -> APIResult:
        """Getting all resource history versions
        id (str): Resource UUID
        kind (str): Resource kind (correlationRule|dictionary|...)
        """
        return self._make_request(
            "GET",
            f"resources/{self._path(kind)}/{self._path(id)}/history",
            params=kwargs,
        )

    def get_history(self, kind: str, id: str, history_id: int) -> APIResult:
        """Getting resource history version with specified kind, ID and version number
        id (str): Resource UUID
        kind (str): Resource kind (correlationRule|dictionary|...)
        history_id (int): Number of version
        """
        return self._make_request(
            "GET",
            f"resources/{self._path(kind)}/{self._path(id)}/history/{self._path(history_id)}",
        )

    def revert(self, kind: str, id: str, history_id: int) -> APIResult:
        """Reverting resource history version with specified kind, ID and version number
        id (str): Resource UUID
        kind (str): Resource kind (correlationRule|dictionary|...)
        history_id (int): Number of version
        """
        return self._make_request(
            "POST",
            f"resources/{self._path(kind)}/{self._path(id)}/history/{self._path(history_id)}",
        )

    def link_rules_to_correlator(self, correlator_id: str, rules_ids: list[str]):
        """Attach missing rules once, preserving input order and existing rules."""
        status, original = self.get("correlator", correlator_id)
        correlator = deepcopy(original)
        rules = correlator["payload"].setdefault("rules", [])
        existing = {rule["id"] for rule in rules}
        changed = False
        for rule_id in dict.fromkeys(rules_ids):
            if rule_id not in existing:
                _, rule = self.get("correlationRule", rule_id)
                rules.append(rule["payload"])
                existing.add(rule_id)
                changed = True
        if not changed:
            return status, original
        return self.put("correlator", correlator_id, correlator)

    def unlink_rules_from_correlator(
        self, correlator_id: str, rules_ids=None, unlink_all: bool = False
    ):
        """Detach rules in linear time; return the unchanged resource for a no-op."""
        status, original = self.get("correlator", correlator_id)
        rules = original["payload"].get("rules", [])
        removed = set(rules_ids or ())
        remaining = (
            [] if unlink_all else [rule for rule in rules if rule["id"] not in removed]
        )
        if remaining == rules:
            return status, original
        correlator = deepcopy(original)
        if unlink_all:
            correlator["payload"].pop("rules", None)
        else:
            correlator["payload"]["rules"] = remaining
        return self.put("correlator", correlator_id, correlator)
