from typing import Dict, List, Optional, Tuple, Union


class KumaRestAPITasks:
    """
    Методы для работы с отложенными задачами
    """

    def __init__(self, base):
        self._base = base

    def create(self, task: dict) -> Tuple[int, List | str]:
        """
        Search tenants with filter
        Args:
            task (dict): PTask body JSON, see examples.
        """
        return self._base._make_request("POST", "tasks/create", json=task)
