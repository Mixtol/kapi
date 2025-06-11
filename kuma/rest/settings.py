from kuma.rest._base import KumaRestAPIModule


class KumaRestAPISettings(KumaRestAPIModule):
    """Methods for Settings."""
    def view(self, id: str) -> tuple[int, dict | str]:
        """
        List of custom fields added by the KUMA user in the application web interface.
        Args:
            id (str): Configuration UUID of the custom fields
        """
        return self._make_request("GET", f"settings/id/{id}")
