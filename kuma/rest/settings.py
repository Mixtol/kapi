from typing import List

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPISettings(KumaRestAPIModule):
    """Methods for Settings."""

    def export_extendedfields(self) -> tuple[int, dict | str]:
        """
        The user can export a list of fields from the extended event schema.
        """
        return self._make_request("GET", f"settings/extendedFields/export")

    def import_extendedfields(self, fields: List[dict]) -> tuple[int, dict | str]:
        """
        The user can import a list of fields from the extended event schema.
        whats examples examples\import_extended_fields.txt
        """
        return self._make_request("POST", f"settings/extendedFields/import")

    def view(self, id: str) -> tuple[int, dict | str]:
        """
        List of custom fields added by the KUMA user in the application web interface.
        Args:
            id (str): Configuration UUID of the custom fields
        """
        return self._make_request("GET", f"settings/id/{id}")
