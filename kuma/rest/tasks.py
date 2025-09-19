from typing import List, Tuple, Union

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPITasks(KumaRestAPIModule):
    """Methods for Tasks."""
    def create(self, task: dict) -> Tuple[int, Union[List, str]]:
        """
        Search tenants with filter
        Args:
            task (dict): PTask body JSON, see examples.
        """
        return self._make_request("POST", "tasks/create", json=task)
