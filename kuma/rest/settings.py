from typing import Dict, List, Optional, Tuple, Union


class KumaRestAPISettings:
    """
    Методы для работы с настройками Ядра
    """

    def __init__(self, base):
        self._base = base

    def view(self, id: str) -> tuple[int, dict | str]:
        """
        List of custom fields added by the KUMA user in the application web interface.
        Args:
            id (str): Configuration UUID of the custom fields
        """
        return self._base._make_request("GET", f"settings/id/{id}")
