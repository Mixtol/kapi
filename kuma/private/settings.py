"""Чтение настроек и изменение привязок правил сегментации алертов."""

from copy import deepcopy


class PrivateSettings:
    def iter_update_alerting(
        self,
        tenant_ids,
        correlation_rules,
        *,
        action="add",
        rule_name="ALL_EventOutcome",
    ):
        """Изменить правило сегментации и выдать статус для каждого тенанта.

        Использует приватный API: публичный API не предоставляет запись настроек.
        Останавливается при первой HTTP-ошибке; предыдущие изменения сохраняются.
        Запросы и копирование выполняют get_settings и update_settings_by_id.
        """
        from kuma.errors import APIError

        if isinstance(tenant_ids, str) or isinstance(correlation_rules, str):
            raise ValueError(
                "ID тенантов и правил должны передаваться последовательностями"
            )
        tenants = set(tenant_ids)
        rules = list(dict.fromkeys(correlation_rules))
        if not tenants or not rules:
            raise ValueError("Требуются явные непустые наборы ID тенантов и правил")
        if action not in ("add", "delete"):
            raise ValueError("action должен быть add или delete")
        status, data = self.get_settings()
        if not 200 <= status < 300:
            raise APIError("Не удалось прочитать настройки алертинга", status)
        settings = [row for row in self._rows(data) if row.get("tenantID") in tenants]
        if tenants - {row["tenantID"] for row in settings}:
            raise ValueError(
                "Настройки алертинга доступны не для всех запрошенных тенантов"
            )
        for setting in settings:
            status, _ = self.update_settings_by_id(
                setting["id"], rules, action=action, rule_name=rule_name
            )
            if not 200 <= status < 300:
                raise APIError("Не удалось обновить настройки алертинга", status)
            yield {
                "tenantID": setting["tenantID"],
                "settingsID": setting["id"],
                "status": status,
            }

    def get_settings(
        self,
        kind: str = "alerts",
        columns=("tenantID", "tenantName", "updatedAt", "disabled"),
    ):
        """GET settings/: получить настройки указанного kind, обычно alerts.

        columns — имена полей для query column; пустая последовательность
        или None не задаёт этот параметр. Возвращает (status, JSON/None), при
        HTTP-ошибке — (status, text). Формат коллекции сервера сохраняется,
        дополнительная пагинация не выполняется.
        """
        params = {"kind": kind}
        if columns:
            params["column"] = list(columns)
        return self._result("GET", "settings/", params=params)

    def get_settings_by_id(
        self, id_: str, column: str = "segmentationRules", order: str = "name"
    ):
        """GET settings/id/{id_}: прочитать объект настроек по его ID.

        id_ — ID конфигурации настроек, не ID тенанта. column запрашивает
        поле (по умолчанию segmentationRules), order задаёт сортировку
        (по умолчанию name). Возвращает (status, JSON/None) либо (status, text)
        при HTTP-ошибке; ответ закрывается. Результат можно передать как payload
        в update_settings_by_id(), если он содержит segmentationRules.
        """
        return self._result(
            "GET",
            f"settings/id/{self._path(id_)}",
            params={"column": column, "order": order},
        )

    def update_settings_by_id(
        self,
        id_: str,
        correlation_rules=None,
        action: str = "add",
        payload: dict = None,
        rule_name: str = "ALL_EventOutcome",
    ):
        """Добавить или удалить привязки correlationRuleIDs в одном правиле.

        Args:
            id_: ID изменяемой конфигурации настроек.
            correlation_rules: Список ID ресурсов правил корреляции.
            action: 'add' или 'delete', без учёта регистра.
            payload: Объект настроек с массивом segmentationRules; если None,
                запрашивается через get_settings_by_id(id_). Объект копируется.
            rule_name: Точное имя элемента segmentationRules; по умолчанию
                ALL_EventOutcome. Меняется только его correlationRuleIDs.

        add сохраняет порядок и исключает дубликаты, delete удаляет только
        перечисленные ID. Остальные поля сохраняются. При отсутствии изменений
        PUT не отправляется. Конкурентное чтение/изменение/запись не атомарно;
        переданный payload должен соответствовать актуальным настройкам.

        Returns:
            (status, JSON/None) либо (status, text) при HTTP-ошибке GET/PUT.
            Если изменений нет — (200, копия payload). Пустой список ID
            возвращает (0, сообщение) до проверки action и сетевых запросов.

        Raises:
            ValueError: Неизвестный action, payload без массива segmentationRules
                или отсутствующее rule_name. Некорректный JSON успешного
                ответа вызывает APIError; сетевые ошибки передаются без замены.

        Example:
            status, result = client.update_settings_by_id(
                settings_id, [rule_id], action='add', rule_name='ALL_EventOutcome'
            )
        """
        if not correlation_rules:
            return 0, "ERROR: argument 'correlation_rules' is empty list"
        mode = action.lower()
        if mode not in ("add", "delete"):
            raise ValueError("Only actions 'add' and 'delete' are available")
        if payload is None:
            status, payload = self.get_settings_by_id(id_)
            if not 200 <= status < 300:
                return status, payload
        if not isinstance(payload, dict) or not isinstance(
            payload.get("segmentationRules"), list
        ):
            raise ValueError("Settings payload must contain segmentationRules")
        body = deepcopy(payload)
        rule = next(
            (
                rule
                for rule in body["segmentationRules"]
                if rule.get("name") == rule_name
            ),
            None,
        )
        if rule is None:
            raise ValueError(f"Segmentation rule not found: {rule_name}")
        current = rule.get("correlationRuleIDs", [])
        requested = set(correlation_rules)
        updated = (
            list(dict.fromkeys([*current, *correlation_rules]))
            if mode == "add"
            else [id_ for id_ in current if id_ not in requested]
        )
        if updated == current:
            return 200, body
        rule["correlationRuleIDs"] = updated
        return self._result("PUT", f"settings/id/{self._path(id_)}", json=body)
