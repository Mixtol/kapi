from typing import List, Tuple, Union

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPISettings(KumaRestAPIModule):
    """Methods for Settings."""

    def export_extendedfields(self) -> Tuple[int, Union[dict, str]]:
        """
        The user can export a list of fields from the extended event schema.
        """
        return self._make_request("GET", f"settings/extendedFields/export")

    def import_extendedfields(self, fields: List[dict]) -> Tuple[int, Union[dict, str]]:
        """
        The user can import a list of fields from the extended event schema.
        whats examples examples\import_extended_fields.txt
        """
        return self._make_request("POST", f"settings/extendedFields/import")

    def view(self, id: str) -> Tuple[int, Union[dict, str]]:
        """
        List of custom fields added by the KUMA user in the application web interface.
        Args:
            id (str): Configuration UUID of the custom fields
        """
        return self._make_request("GET", f"settings/id/{id}")
