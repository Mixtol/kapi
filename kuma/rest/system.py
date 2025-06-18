from typing import Tuple

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPISystem(KumaRestAPIModule):
    """Methods for System."""
    def backup(
        self,
    ) -> Tuple[int, str]:
        """
        Creating binary Core backup file
        """
        return self._make_request("POST", "system/backup")

    def restore(self, data: str) -> Tuple[int, str]:
        """
        Restoring core from archive with the backup copy
        """
        return self._make_request("POST", "system/backup", data=data)
