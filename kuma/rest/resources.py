from typing import Dict, List, Optional, Tuple, Union

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPIResources(KumaRestAPIModule):
    """Methods for Resources."""

    def search(self, **kwargs) -> Tuple[int, Union[List, str]]:
        """
        Search resources
        Args:
            page (int): Pagination page (1 by default)
            id (List[str]): Resources UUID filter
            tenantID (List[str]): Tenants UUID filter
            name (str): Case-insensetine name regex filter
            kind (List[str]): Resource kind filter (filter|correlationRule|...)
            userID (List[str]): Creator filter
        """
        params = {
            **kwargs,
        }
        return self._make_request("GET", "resources", params=params)

    def download(self, id: str) -> Tuple[int, Union[List, str]]:
        """
        Download export file data
        Args:
            id (str): File ID as a result of resource export request.
        """
        return self._make_request("GET", f"download/{id}")

    def export(
        self,
        resources_ids: List[str],
        tenant_id: str,
        password: str = "Kuma_secret_p@$$w0rd",
    ) -> Tuple[int, Union[List, str]]:
        """
        Generating export file ID for download
        Args:
            resources_ids (List[str]): Resources UUID list to download
            tenant_id (str): Resources tenant UUID
            password (str): Future file open password
        """
        json = {"ids": resources_ids, "password": password, "tenantID": tenant_id}
        return self._make_request("POST", "resources/export", json=json)

    def import_data(
        self,
        file_id: str,
        tenant_id: str,
        password: str = "Kuma_secret_p@$$w0rd",
        actions: Optional[Dict] = None,
    ) -> Tuple[int, Union[List, str]]:
        """
        Import content file uploded early from /upload method
        Args:
            file_id (str): Uploaded file UUID returned by Core
            tenant_id (str): Destination resource tenant UUID
            password (str): File open password
            actions (dict): Conflict resolve rules, see examples
                0=ignore, 1=import, 2=replace
        """
        json = {
            "actions": actions,
            "fileID": file_id,
            "password": password,
            "tenantID": tenant_id,
        }
        return self._make_request("POST", "resources/import", json=json)

    def toc(
        self,
        file_id: str,
        password: str = "Kuma_secret_p@$$w0rd",
    ) -> Tuple[int, Union[List, str]]:
        """
        View content of uploaded resource file, recommended to use before import_data
        Args:
            file_id (str): Uploaded file UUID returned by Core
            password (str): File open password
        """
        json = {
            "fileID": file_id,
            "password": password,
        }
        return self._make_request("POST", f"resources/toc", json=json)

    def upload(self, data: Union[bytes, str]) -> Tuple[int, Union[List, str]]:
        """
        Download export file data
        Args:
            data (binary): File data or file path
        """
        if isinstance(data, str):
            with open(data, "rb") as f:
                data = f.read()
        return self._make_request("POST", "resources/upload", data=data)

    def create(
        self,
        kind: str,
        resource: dict,
    ) -> Tuple[int, Union[List, str]]:
        """
        Create resource from JSON
        Args:
            kind (str): Resource kind (correlationRule|dictionary|...)
            resource (dict): Resource JSON object, see examples.
        """
        return self._make_request("POST", f"resources/{kind}/create", json=resource)

    def validate(
        self,
        kind: str,
        resource: dict,
    ) -> Tuple[int, Union[List, str]]:
        """
        Validate resource JSON
        Args:
            kind (str): Resource kind (correlationRule|dictionary|...)
            resource (dict): Resource JSON object, see /create method.
        """
        return self._make_request("POST", f"resources/{kind}/validate", json=resource)

    def get(self, kind: str, id: str) -> Tuple[int, Union[List, str]]:
        """
        Get resource JSON
        Args:
            id (str): Resource UUID
            kind (str): Resource kind (correlationRule|dictionary|...)
        """
        return self._make_request("GET", f"resources/{kind}/{id}")

    def put(self, kind: str, id: str, resource: dict) -> Tuple[int, Union[List, str]]:
        """
        Modify|Update resource with JSON
        Args:
            id (str): Resource UUID
            kind (str): Resource kind (correlationRule|dictionary|...)
            resource (dict): Resource JSON object, see /create method.
        """
        return self._make_request("PUT", f"resources/{kind}/{id}", json=resource)

    def list_history(self, kind: str, id: str) -> Tuple[int, Union[List, str]]:
        """Getting all resource history versions
        id (str): Resource UUID
        kind (str): Resource kind (correlationRule|dictionary|...)
        """
        return self._make_request("GET", f"resources/{kind}/{id}/history")

    def get_history(
        self, kind: str, id: str, history_id: int
    ) -> Tuple[int, Union[List, str]]:
        """Getting resource history version with specified kind, ID and version number
        id (str): Resource UUID
        kind (str): Resource kind (correlationRule|dictionary|...)
        history_id (int): Number of version
        """
        return self._make_request("GET", f"resources/{kind}/{id}/history/{history_id}")

    def revert(self, kind: str, id: str, history_id: int) -> Tuple[int, Union[List, str]]:
        """Reverting resource history version with specified kind, ID and version number
        id (str): Resource UUID
        kind (str): Resource kind (correlationRule|dictionary|...)
        history_id (int): Number of version
        """
        return self._make_request("POST", f"resources/{kind}/{id}/history/{history_id}")
    
    def link_rules_to_correlator(self, correlator_id: str, rules_ids: list[str]):
        """Привязывает правила к коррелятору.

        Args:
            correlator_id (str): ID коррелятора
            rules_ids (set[str]): Множество IDs корреляционных правил

        Raises:
            Exception: Если не удалось получить коррелятор
            Exception: Если не удалось получить корреляционное правило
        """
        status, correlator = self._base.resources.get(
            kind="correlator", id=correlator_id
        )
        if status != 200:
            raise Exception("Could not get correlator. Status code:", correlator)

        add_new_rules = False
        rules_on_correlator = correlator["payload"].get("rules", [])
        rules_on_correlator_ids = [rule["id"] for rule in rules_on_correlator]
        rules_ids = set(rules_ids)
        for rule_id in rules_ids:
            if not rule_id in rules_on_correlator_ids:
                status, rule = self._base.resources.get(
                    kind="correlationRule", id=rule_id
                )
                if status != 200:
                    raise Exception(
                        "Could not get correlation rule. Status code:", status
                    )

                rules_on_correlator.append(rule["payload"])
                if not add_new_rules:
                    add_new_rules = True

        if not add_new_rules:
            return {
                "response": f"Correlation rules are already linked to '{correlator_id}'"
            }

        correlator["payload"]["rules"] = rules_on_correlator
        return self._base.resources.put(
            kind="correlator", id=correlator_id, resource=correlator
        )

    def unlink_rules_from_correlator(
        self, correlator_id: str, rules_ids: list[str] = [], unlink_all: bool = False
    ):
        """Отвязывает правила от коррелятора.

        Args:
            correlator_id (str): ID коррелятора
            rules_ids (set[str]): Множество IDs правил
            unlink_all (bool, optional): Отвязать все правила

        Raises:
            Exception: Если не удалось получить коррелятор
            Exception: Если корреляционное правило отсутствует на корреляторе
        """
        status, correlator = self._base.resources.get(
            kind="correlator", id=correlator_id
        )
        if status != 200:
            raise Exception("Could not get correlator. Status code:", correlator)

        if "rules" not in correlator["payload"]:
            return {
                "response": f"Correlator '{correlator_id}' does not have linked rules"
            }

        if unlink_all:
            del correlator["payload"]["rules"]
            return self._base.resources.put(
                kind="correlator", id=correlator_id, resource=correlator
            )

        rules_on_correlator_ids = [
            rule["id"] for rule in correlator["payload"]["rules"]
        ]
        rules_ids = set(rules_ids)
        indexes_to_delete = []
        for rule_id in rules_ids:
            if rule_id not in rules_on_correlator_ids:
                continue

            rule_index = rules_on_correlator_ids.index(rule_id)
            indexes_to_delete.append(rule_index)

        if not indexes_to_delete:
            return {
                "response": f"Rules ids are not linked to correlator '{correlator_id}'"
            }

        for rule_index in sorted(indexes_to_delete, reverse=True):
            del correlator["payload"]["rules"][rule_index]

        return self._base.resources.put(
            kind="correlator", id=correlator_id, resource=correlator
        )
