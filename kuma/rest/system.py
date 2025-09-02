from typing import Optional, Tuple

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPISystem(KumaRestAPIModule):
    """Methods for System."""

    def backup(
        self, filepath: Optional[str] = None, timeout: int = 900
    ) -> Tuple[int, str]:
        """
        Creating binary Core backup data.
        savepath: str - Where you want to save file.
        timeout: int - Seconds, increse for big instances.
        """
        status_code, response = self._make_request(
            "GET", "system/backup", timeout=timeout
        )
        if filepath and status_code == 200:
            with open(filepath, "wb") as f:
                f.write(response)
            return status_code, filepath
        return status_code, response

    def restore(
        self, filepath: Optional[str] = None, data: Optional[bytes] = None
    ) -> Tuple[int, str]:
        """
        Restoring core from archive with the backup copy
        filepath: str - Relative path to bak file
        data: bytes - Bin backup data
        """
        if filepath:
            with open(filepath, "wb") as f:
                data = f.read()
        return self._make_request("POST", "system/backup", data=data)
