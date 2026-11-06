from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPITasks(KumaRestAPIModule):
    """Methods for Tasks."""

    def create(self, task: dict) -> APIResult:
        """
        Create a task from its JSON configuration
        Args:
            task (dict): PTask body JSON, see examples.
        """
        return self._make_request("POST", "tasks/create", json=task)
