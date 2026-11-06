from typing import List, Optional

from kuma.rest._base import APIResult, KumaRestAPIModule, Timeout


class KumaRestAPISettings(KumaRestAPIModule):
    """Methods for Settings."""

    def export_extendedfields(self, *, timeout: Optional[Timeout] = None) -> APIResult:
        """
        The user can export a list of fields from the extended event schema.
        """
        return self._make_request(
            "GET", "settings/extendedFields/export", timeout=timeout
        )

    def import_extendedfields(self, fields: List[dict]) -> APIResult:
        """
        The user can import a list of fields from the extended event schema.
        See the fields payload in API_REFERENCE.md.
        """
        return self._make_request("POST", "settings/extendedFields/import", json=fields)

    def view(self, id: str) -> APIResult:
        """
        List of custom fields added by the KUMA user in the application web interface.
        Args:
            id (str): Configuration UUID of the custom fields
        """
        return self._make_request("GET", f"settings/id/{self._path(id)}")
