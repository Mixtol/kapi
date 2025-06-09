from typing import Dict, List, Optional, Tuple, Union

from ._base import KumaRestAPIModule


class KumaRestAPITasks(KumaRestAPIModule):
    """
    Методы для работы с отложенными задачами
    """

    def __init__(self, base):
        super().__init__(base)

    def create(self, task: dict) -> Tuple[int, List | str]:
        """
        Search tenants with filter
        Args:
            task (dict): PTask body JSON, see examples.
        """
        return self._base._make_request("POST", "tasks/create", json=task)
