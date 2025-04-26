from typing import Dict, List, Optional, Tuple, Union


class KumaRestAPISystem:
    """
    Методы для работы с ядром
    """

    def __init__(self, base):
        self._base = base

    def backup(
        self,
    ) -> Tuple[int, str]:
        """
        Creating binary Core backup file
        """
        return self._base._make_request("POST", "system/backup")

    def restore(self, data: str) -> Tuple[int, str]:
        """
        Restoring core from archive with the backup copy
        """
        return self._base._make_request("POST", "system/backup", data=data)
