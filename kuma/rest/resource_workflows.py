"""Расширенные операции с ресурсами через публичный REST API."""

from copy import deepcopy

from kuma.errors import APIError
from kuma.rest._pagination import iter_pages


def tenant_filter(tenant_ids):
    if tenant_ids is None:
        return {}
    if isinstance(tenant_ids, str):
        raise ValueError("tenant_ids должен быть последовательностью, а не строкой")
    ids = list(dict.fromkeys(tenant_ids))
    if not ids or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("tenant_ids должен содержать непустые ID")
    return {"tenantID": ids}


def resource_payload(resource, kind):
    if not isinstance(resource, dict) or resource.get("kind") != kind:
        raise ValueError("Ожидался ресурс типа " + kind)
    payload = resource.get("payload")
    if not isinstance(payload, dict):
        raise APIError("Поле payload ресурса должно быть объектом")
    return payload


class PublicResourceWorkflows:
    def iter_search(self, *, page=1, **filters):
        """Выдавать метаданные ресурсов постранично; отклонять повторные страницы."""
        return iter_pages(self.search, page=page, **filters)

    def iter_correlators(self, tenant_ids=None):
        """Выдавать полные конфигурации корреляторов по одной через публичный API.

        tenant_ids ограничивает тенанты корреляторов, а не вложенных правил.
        None означает все доступные тенанты; пустой список отклоняется.
        """
        filters = tenant_filter(tenant_ids)
        allowed = set(filters.get("tenantID", []))
        for row in self.iter_search(kind="correlator", **filters):
            if allowed and row.get("tenantID") not in allowed:
                continue
            _, resource = self.get("correlator", row["id"])
            resource_payload(resource, "correlator")
            yield resource

    def iter_rule_bindings(self, tenant_ids=None, *, rule_ids=None):
        """Выдавать {ruleID, correlatorID, correlatorName, tenantID} для каждой связи.

        Каждый коррелятор читается один раз. В памяти остаётся одна полная
        конфигурация, которая сама может быть большой. Отдельных HTTP-запросов
        по каждому правилу нет. rule_ids фильтрует выдачу, а не HTTP-запросы.
        """
        if isinstance(rule_ids, str):
            raise ValueError("rule_ids должен быть последовательностью, а не строкой")
        requested = None if rule_ids is None else set(rule_ids)
        if requested == set():
            return
        for resource in self.iter_correlators(tenant_ids):
            rules = resource["payload"].get("rules") or []
            if not isinstance(rules, list):
                raise APIError("Правила коррелятора должны быть массивом")
            seen = set()
            for rule in rules:
                if not isinstance(rule, dict) or not rule.get("id"):
                    raise APIError("У вложенного правила корреляции отсутствует ID")
                id_ = rule["id"]
                if id_ in seen or (requested is not None and id_ not in requested):
                    continue
                seen.add(id_)
                yield {
                    "ruleID": id_,
                    "correlatorID": resource["id"],
                    "correlatorName": resource["name"],
                    "tenantID": resource["tenantID"],
                }

    def get_bound_correlators(self, rule_id, tenant_ids=None):
        """Вернуть (200, список корреляторов) для правила через публичный API.

        Учитываются конфигурации без запущенного сервиса. Для множества правил
        используйте один обход iter_rule_bindings(). Пустой результат означает,
        что в пределах прав токена и выбранных тенантов связи не найдены.
        """
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("rule_id должен быть непустой строкой")
        return 200, [
            {
                "id": row["correlatorID"],
                "name": row["correlatorName"],
                "tenantID": row["tenantID"],
            }
            for row in self.iter_rule_bindings(tenant_ids, rule_ids=[rule_id])
        ]

    def export_rules_csv(self, filepath, **options):
        """Сформировать CSV через публичный API с временным индексом на диске.

        Фильтры, группировка, расход памяти и результат описаны в EXTENTIONS.md.
        Целевой файл заменяется атомарно только после полного завершения.
        """
        from kuma.rest.rules_report import export_rules_csv

        return export_rules_csv(self, filepath, **options)

    def copy_correlator_variables(self, correlator_id, template):
        """Перенести переменные из полного эталона, сохранив ID и остальные поля.

        Сервисы не перезагружаются. Чтение и запись не защищены от параллельных
        изменений другими авторами.
        """
        source = resource_payload(template, "correlator")
        variables = source.get("variables")
        if not isinstance(variables, list):
            raise ValueError("Переменные эталона должны быть массивом")
        status, original = self.get("correlator", correlator_id)
        resource_payload(original, "correlator")
        if original["payload"].get("variables") == variables:
            return status, original
        body = deepcopy(original)
        body["payload"]["variables"] = deepcopy(variables)
        return self.put("correlator", correlator_id, body)

    def sync_correlation_rule(self, rule_id, template, *, preserve_custom=True):
        """Перенести поля эталона, переменные селекторов и настройки общих действий.

        ID, тенант, условия селекторов и прочие поля цели сохраняются. Переменные
        цели с 'custom' в имени без учёта регистра заменяют одноимённые переменные
        эталона. Число селекторов должно совпадать. Ссылки в действиях эталона
        должны быть действительны на целевой KUMA. Сервисы не перезагружаются.
        """
        source = resource_payload(template, "correlationRule")
        status, original = self.get("correlationRule", rule_id)
        target = resource_payload(original, "correlationRule")
        source_selectors = source.get("selectors", [])
        if len(source_selectors) != len(target.get("selectors", [])):
            raise ValueError("Количество селекторов эталона и цели различается")
        body = deepcopy(original)
        payload = body["payload"]
        body["name"] = template["name"]
        payload["name"] = template["name"]
        for field in (
            "identicalFields",
            "uniqueFields",
            "rateLimit",
            "keepPolicy",
            "uniqueFieldsMapping",
        ):
            if field in source:
                payload[field] = deepcopy(source[field])
        for src, dst in zip(source_selectors, payload.get("selectors", [])):
            variables = deepcopy(src.get("variables") or [])
            if preserve_custom:
                custom = [
                    value
                    for value in dst.get("variables") or []
                    if "custom" in value.get("name", "").lower()
                ]
                names = {value["name"] for value in custom}
                variables = [v for v in variables if v.get("name") not in names]
                variables.extend(custom)
            dst["variables"] = variables
        for name, action in payload.get("actions", {}).items():
            if name in source.get("actions", {}):
                for field in ("output", "loop", "noAlert", "enrichment"):
                    if field in source["actions"][name]:
                        action[field] = deepcopy(source["actions"][name][field])
        if body == original:
            return status, original
        return self.put("correlationRule", rule_id, body)

    def iter_update_correlators(
        self, correlator_ids, rule_ids, *, action="link", reload=False
    ):
        """Выдавать результат для каждого указанного коррелятора до первой ошибки.

        Предыдущие изменения сохраняются. reload=True перезагружает сервисы,
        у которых resourceID совпадает с ID коррелятора. По умолчанию меняется
        только конфигурация.
        """
        if action not in ("link", "unlink"):
            raise ValueError("action должен быть link или unlink")
        if isinstance(correlator_ids, str) or isinstance(rule_ids, str):
            raise ValueError("ID должны передаваться последовательностями")
        rules = list(dict.fromkeys(rule_ids))
        operation = (
            self.link_rules_to_correlator
            if action == "link"
            else self.unlink_rules_from_correlator
        )
        for id_ in dict.fromkeys(correlator_ids):
            status, _ = operation(id_, rules)
            services = self._base.services.reload_resource(id_)[1] if reload else []
            yield {"correlatorID": id_, "status": status, "services": services}

    def iter_copy_to(
        self, target, resource_ids, source_tenant_id, target_tenant_id, **options
    ):
        """Переносить ресурсы ограниченными пакетами через другой RestClient.

        Пароль архива, обработка конфликтов и резервирование — в EXTENTIONS.md.
        Выдаёт результат каждого пакета; при ошибке предыдущие импорты сохраняются.
        """
        from kuma.rest.resource_transfer import iter_copy_to

        return iter_copy_to(
            self, target, resource_ids, source_tenant_id, target_tenant_id, **options
        )
