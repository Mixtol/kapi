from typing import Dict, List, Optional, Tuple, Union

from ._base import KumaRestAPIModule


class KumaRestAPISettings(KumaRestAPIModule):
    """
    Методы для работы с настройками Ядра
    """

    def __init__(self, base):
        super().__init__(base)

    def view(self, id: str) -> tuple[int, dict | str]:
        """
        List of custom fields added by the KUMA user in the application web interface.
        Args:
            id (str): Configuration UUID of the custom fields
        """
        return self._make_request("GET", f"settings/id/{id}")
