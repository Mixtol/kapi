from kuma.rest._base import KumaRestAPIModule


class KumaRestAPICorrelators(KumaRestAPIModule):
    """Methods for Correlators."""

    def link_rule_to_correlator(self, correlator_id: str, rule_id: str):
        """Привязывает правило к коррелятору.
        self,
                Args:
                    correlator_id (str): ID коррелятора
                    rules_id (str): ID корреляционного правила

                Raises:
                    Exception: Если не удалось получить коррелятор
                    Exception: Если не удалось получить корреляционное правило
        """
        status, correlator = self._base.resources.get(
            kind="correlator", id=correlator_id
        )
        if status != 200:
            raise Exception("Could not get correlator. Status code:", correlator)

        status, rule = self._base.resources.get(kind="correlationRule", id=rule_id)
        if status != 200:
            raise Exception("Could not get correlation rule. Status code:", status)

        if "rules" not in correlator["payload"]:
            correlator["payload"]["rules"] = [rule["payload"]]
        else:
            rules_on_correlator_ids = [
                rule["id"] for rule in correlator["payload"]["rules"]
            ]
            if rule_id in rules_on_correlator_ids:
                return {
                    "response": f"Correlation rule '{rule_id}' is already linked to '{correlator_id}'"
                }

            correlator["payload"]["rules"].append(rule["payload"])
        return self._base.resources.put(
            kind="correlator", id=correlator_id, resource=correlator
        )

    def link_rules_to_correlator(self, correlator_id: str, rules_ids: set[str]):
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

    def unlink_rule_from_correlator(self, correlator_id: str, rule_id: str):
        """Отвязывает правило от коррелятора.

        Args:
            correlator_id (str): ID коррелятора
            rules_id (str): ID корреляционного правила

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

        rules_on_correlator_ids = [
            rule["id"] for rule in correlator["payload"]["rules"]
        ]
        if rule_id not in rules_on_correlator_ids:
            return {
                "response": f"Rule id '{rule_id}' is not linked to correlator '{correlator_id}'"
            }

        rule_index = rules_on_correlator_ids.index(rule_id)
        del correlator["payload"]["rules"][rule_index]
        return self._base.resources.put(
            kind="correlator", id=correlator_id, resource=correlator
        )

    def unlink_rules_from_correlator(
        self, correlator_id: str, rules_ids: set[str] = set(), unlink_all: bool = False
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
