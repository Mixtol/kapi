from typing import Dict, List, Optional, Tuple, Union

from ._base import KumaRestAPIModule


class KumaRestAPISystem(KumaRestAPIModule):
    """
    Методы для работы с ядром
    """

    def __init__(self, base):
        super().__init__(base)

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
