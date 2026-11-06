"""Поиск правил и привязка к конфигурациям корреляторов."""

from copy import deepcopy

from kuma.errors import APIError

AVAILABLE_RULE_TYPES = frozenset({"correlationRule", "enrichmentRule"})


class PrivateRules:
    def get_rule_by_id(self, rule_id: str, rule_type: str):
        """Вернуть полный ресурс правила rule_id указанного типа rule_type.

        Допустимы correlationRule и enrichmentRule; другой тип вызывает
        ValueError до запроса. Возвращает объект с payload либо текст
        HTTP-ошибки, как get_resource().
        """
        if rule_type not in AVAILABLE_RULE_TYPES:
            raise ValueError(f"Unsupported rule type: {rule_type}")
        return self.get_resource(rule_id, rule_type)

    def _check_rule_binding(self):
        if self._major_version < 3:
            raise ConnectionAbortedError("This function is not supported in KUMA v2")

    def bind_rules(self, rules_ids: list, correlator_ids: list, tenant_id: str):
        """Привязать правила к корреляторам через серверный batch-метод KUMA 3/4.

        rules_ids — ID ресурсов правил, correlator_ids — ID ресурсов
        корреляторов, tenant_id — тенант в query. Это ID конфигураций,
        не запущенных сервисов. Повторы удаляются, порядок сохраняется.
        POST resources/correlation_rule/bind возвращает HTTP-статус, включая
        ошибки. KUMA 2 вызывает ConnectionAbortedError до запроса. Метод
        самостоятельно не вызывает reload сервисов.
        """
        self._check_rule_binding()
        return self._result(
            "POST",
            "resources/correlation_rule/bind",
            params={"tenantID": tenant_id},
            json={
                "ids": list(dict.fromkeys(rules_ids)),
                "correlatorIDs": list(dict.fromkeys(correlator_ids)),
                "searchType": "ids",
            },
            text=True,
        )[0]

    def link_rules(self, rules_IDs: list, correlator_IDs: list):
        """Привязать правила batch-запросом без явного фильтра tenantID.

        rules_IDs и correlator_IDs — списки ID ресурсов правил и корреляторов;
        написание аргументов сохранено для существующих вызовов. Повторы
        удаляются с сохранением порядка. Возвращает (status, text), включая
        HTTP-ошибки. Для явного тенанта используйте bind_rules(). KUMA 2
        вызывает ConnectionAbortedError. Reload сервисов не выполняется.
        """
        self._check_rule_binding()
        return self._result(
            "POST",
            "resources/correlation_rule/bind",
            json={
                "ids": list(dict.fromkeys(rules_IDs)),
                "correlatorIDs": list(dict.fromkeys(correlator_IDs)),
                "searchType": "ids",
            },
            text=True,
        )

    def unbind_rule(self, rule_id: str, correlators_ids: list, tenant_id: str):
        """Отвязать одно правило от списка конфигураций корреляторов KUMA 3/4.

        rule_id — ID ресурса правила, correlators_ids — ID ресурсов
        корреляторов, tenant_id — тенант в JSON-теле. Выполняет POST
        resources/correlation_rule/{rule_id}/unbind и возвращает HTTP-статус,
        включая ошибки. KUMA 2 вызывает ConnectionAbortedError. Повторы
        корреляторов исключаются; reload сервисов не выполняется.
        """
        self._check_rule_binding()
        return self._result(
            "POST",
            f"resources/correlation_rule/{self._path(rule_id)}/unbind",
            json={
                "correlatorIDs": list(dict.fromkeys(correlators_ids)),
                "tenantID": tenant_id,
            },
            text=True,
        )[0]

    def _attach_rules(self, correlator_id, rules_ids):
        """Прочитать коррелятор, добавить недостающие payload правил и записать.

        Возвращает (attempted, (status, data)): attempted=True означает попытку
        PUT, а не успешную запись. Локальные результаты используют строковые
        статусы '200'/'500', HTTP-ответ PUT — целочисленный статус.
        """
        original = self.get_correlator_by_id(correlator_id)
        if not isinstance(original, dict):
            return False, (
                "500",
                f"Failed to get correlator data {correlator_id}: {original}",
            )
        rules = original["payload"].get("rules", [])
        existing = {rule["id"] for rule in rules}
        missing = [id_ for id_ in dict.fromkeys(rules_ids) if id_ not in existing]
        if not missing:
            return False, (
                "200",
                f"Correlation rules are already linked to '{correlator_id}'",
            )
        body = deepcopy(original)
        updated = body["payload"].setdefault("rules", [])
        for id_ in missing:
            rule = self.get_correlation_rule_by_id(id_)
            if not isinstance(rule, dict):
                return False, ("500", f"Failed to get correlation rule {id_}: {rule}")
            updated.append(rule)
        return True, self._result(
            "PUT", f"resources/correlator/{self._path(correlator_id)}", json=body
        )

    def link_rules_to_correlator(self, correlator_id: str, rules_ids: list):
        """Добавить правила в payload.rules конфигурации коррелятора через PUT.

        correlator_id — ID ресурса коррелятора; rules_ids — ID ресурсов правил.
        Сначала читает конфигурацию и недостающие payload правил, затем пишет
        копию полного объекта. Существующие правила и порядок сохраняются,
        дубликаты не добавляются. Если всё уже привязано, PUT не выполняется.

        Returns:
            После PUT — (int status, JSON/None либо текст HTTP-ошибки).
            Если изменений нет — ('200', сообщение). Если конфигурация или
            правило не прочитаны как объект — ('500', сообщение).

        Чтение и запись не атомарны; параллельные изменения согласует приложение.
        Метод не перечитывает работающие сервисы: при необходимости отдельно
        вызовите reload_services(correlator_id).
        """
        return self._attach_rules(correlator_id, rules_ids)[1]

    def link_rule_to_correlator(self, correlator_id: str, rule_id: str):
        """Добавить одно правило по ID ресурса, используя чтение/PUT коррелятора.

        Аргументы — ID ресурсов, не сервисов. Поведение записи и конкурентного
        доступа описано в link_rules_to_correlator(). Возвращает JSON/None
        успешного PUT; строку 'Rule already exist on correlator', если правило
        уже есть; строку '<status>:<data>' при ошибке. Reload не выполняется.
        """
        changed, (status, data) = self._attach_rules(correlator_id, [rule_id])
        if not changed and status == "200":
            return "Rule already exist on correlator"
        return data if 200 <= int(status) < 300 else f"{status}:{data}"

    def unlink_rules_from_correlator(self, correlator_id: str, rules_ids: list[str]):
        """Удалить правила из payload.rules конфигурации коррелятора через PUT.

        correlator_id — ID ресурса коррелятора; rules_ids — список ID ресурсов
        правил. Остальные поля и порядок правил сохраняются в копии объекта.
        Чтение/изменение/запись не атомарны; reload сервисов не выполняется.

        Returns:
            После PUT — (int status, JSON/None либо текст HTTP-ошибки).
            Если коррелятор не прочитан — ('500', сообщение).
            Если список правил пуст — ('200', сообщение).
            Если указанные правила отсутствуют — {'response': сообщение}.
            В двух последних случаях запрос записи не отправляется.
        """
        original = self.get_correlator_by_id(correlator_id)
        if not isinstance(original, dict):
            return "500", f"Failed to get correlator data {correlator_id}: {original}"
        rules = original.get("payload", {}).get("rules", [])
        if not rules:
            return (
                "200",
                f"Correlator {original.get('name')} has no linked rules at all",
            )
        removed = set(rules_ids)
        remaining = [rule for rule in rules if rule["id"] not in removed]
        if remaining == rules:
            return {"response": "Correlator didn't have these rules in linked list"}
        body = deepcopy(original)
        body["payload"]["rules"] = remaining
        return self._result(
            "PUT", f"resources/correlator/{self._path(correlator_id)}", json=body
        )

    def get_resource_id_by_name(
        self, name: str, tenant_id: str, shared: bool = False, shared_prefixes=None
    ):
        """Найти ID правила корреляции по точному имени name и тенанту.

        tenant_id — тенант поиска. shared=True выбирает Shared вместо него.
        shared_prefixes — список префиксов имён; совпадение начала name также
        выбирает Shared. Список префиксов не изменяет искомое имя. Поиск идёт
        через resources/all с kind=correlationRule, preview=True и страницами
        по 64 записи; имя и tenantID дополнительно проверяются локально.

        Returns:
            (200, id) первого точного совпадения; (0, сообщение), если его нет;
            (status, text) при HTTP-ошибке. Ошибки формата/пагинации и отсутствие
            Shared вызывают APIError, сетевые исключения не подавляются.

        Example:
            status, rule_id = client.get_resource_id_by_name('Rule name', tenant_id)
            if status == 200:
                rule = client.get_correlation_rule(rule_id)
        """
        use_shared = shared or bool(
            shared_prefixes and name.startswith(tuple(shared_prefixes))
        )
        query = {
            "preview": True,
            "excludeKinds": ["eventPreset", "search"],
            "name": name,
            "kind": "correlationRule",
        }
        try:
            shared_id = self.get_tenant_shared() if use_shared else None
            for resource in self._iter_rows(
                "resources/all", params=query, page_size=64
            ):
                matches_tenant = resource.get("tenantID") == (
                    shared_id if use_shared else tenant_id
                )
                if resource.get("name") == name and matches_tenant:
                    return 200, resource["id"]
        except APIError as exc:
            if exc.response_text is not None:
                return exc.status_code, exc.response_text
            raise
        return 0, f"Could not find resource with name {name}"
