from kuma.rest._base import KumaRestAPIModule


class KumaRestAPICorrelators(KumaRestAPIModule):
    """Methods for Correlators."""
    
    def add_corr_rule_on_correlator(self, correlator_id: str, rule_id: str):
        status, correlator = self._base.resources.get(kind="correlator", id=correlator_id)
        if status != 200:
            raise Exception("Could not get correlator. Status code:", correlator)
    
        status, rule = self._base.resources.get(kind="correlationRule", id=rule_id)
        if status != 200:
            raise Exception("Could not get correlation rule. Status code:", status)
    
        correlator["payload"]["rules"].append(rule["payload"])
        self._base.resources.put(kind="correlator", id=correlator_id, resource=correlator)
    
    def remove_corr_rule_from_correlator(self, correlator_id: str, rule_id: str):
        status, correlator = self._base.resources.get(kind="correlator", id=correlator_id)
        if status != 200:
            raise Exception("Could not get correlator. Status code:", correlator)
    
        rules_on_correlator_ids = [rule["id"] for rule in correlator["payload"]["rules"]]
        try:
            rule_index = rules_on_correlator_ids.index(rule_id)
        except ValueError:
            raise Exception(f"Rule id '{rule_id}' is not linked to correlator '{correlator_id}'")
    
        del correlator["payload"]["rules"][rule_index]
        self._base.resources.put(kind="correlator", id=correlator_id, resource=correlator)
    
    def remove_all_rules_from_correlator(self, correlator_id: str):
        status, correlator = self._base.resources.get(kind="correlator", id=correlator_id)
        if status != 200:
            raise Exception("Could not get correlator. Status code:", correlator)
    
        correlator["payload"]["rules"].clear()
        self._base.resources.put(kind="correlator", id=correlator_id, resource=correlator)
    
    def remove_multiple_rules_from_correlator(self, correlator_id: str, rules_ids: set[str], ignore: bool = False):
        status, correlator = self._base.resources.get(kind="correlator", id=correlator_id)
        if status != 200:
            raise Exception("Could not get correlator. Status code:", correlator)
    
        rules_on_correlator_ids = [rule["id"] for rule in correlator["payload"]["rules"]]
        indexes_to_delete = []
        for rule_id in rules_ids:
            try:
                rule_index = rules_on_correlator_ids.index(rule_id)
            except ValueError:
                if not ignore:
                    raise Exception(f"Rule id '{rule_id}' is not linked to correlator '{correlator_id}'")
                continue
            indexes_to_delete.append(rule_index)
    
        for rule_index in sorted(indexes_to_delete, reverse=True):
            del correlator["payload"]["rules"][rule_index]
    
        self._base.resources.put(kind="correlator", id=correlator_id, resource=correlator)
    
    def add_multiple_rules_on_correlator(self, correlator_id: str, rules_ids: set[str]):
        status, correlator = self._base.resources.get(kind="correlator", id=correlator_id)
        if status != 200:
            raise Exception("Could not get correlator. Status code:", correlator)
    
        rules_on_correlator = correlator["payload"].get("rules", [])
        rules_on_correlator_ids = [rule["id"] for rule in rules_on_correlator]
        for rule_id in rules_ids:
            if not rule_id in rules_on_correlator_ids:
                status, rule = self._base.resources.get(kind="correlationRule", id=rule_id)
                if status != 200:
                    raise Exception("Could not get correlation rule. Status code:", status)
    
                rules_on_correlator.append(rule["payload"])
    
        correlator["payload"]["rules"] = rules_on_correlator
        self._base.resources.put(kind="correlator", id=correlator_id, resource=correlator)
