"""Private resource and service operations; legacy return shapes are retained."""

from copy import deepcopy

from kuma.errors import APIError


class PrivateResources:
    def iter_resources(self, kind=None, tenant_id="", *, page_size=250, **filters):
        """Выдавать объекты ресурсов из GET resources/{kind или all}.

        kind — тип конфигурации, например filter/correlationRule/correlator;
        None выбирает all. Непустой tenant_id задаёт фильтр tenantID, не меняя
        выбор тенантов сессии. filters — дополнительные query-параметры API;
        page/size управляются итератором, page_size должен быть положительным.

        Читает страницы до пустой, даже если сервер уменьшил размер страницы;
        поддерживает список и {"result": [...]}. Хранит текущую страницу и
        отпечатки уже прочитанных страниц. HTTP-ошибка, неожиданный формат
        или повтор страницы вызывают APIError до повторной выдачи записей.
        Сетевые исключения requests не перехватываются.
        """
        if tenant_id:
            filters["tenantID"] = tenant_id
        return self._iter_rows(
            f"resources/{self._path(kind or 'all')}",
            params=filters,
            page_size=page_size,
        )

    def get_resources(self, kind=None, tenant_id=""):
        """Собрать все страницы ресурсов в список; kind=None означает all.

        tenant_id — необязательный фильтр по тенанту, без смены выбора сессии.
        Весь результат хранится в памяти. HTTP-ошибка возвращается её текстом;
        ошибки формата/пагинации вызывают APIError. Для постраничной обработки
        и единообразных HTTP-исключений используйте iter_resources().
        """
        return self._collect_rows(
            f"resources/{self._path(kind or 'all')}",
            params={"tenantID": tenant_id} if tenant_id else None,
        )

    def get_resource(self, id=None, kind=None):
        """GET resources/{kind}/{id}: получить полную конфигурацию ресурса.

        id — ID конфигурации, kind — её тип; оба обязательны, иначе ValueError.
        Возвращает JSON с внешними полями и payload; при HTTP-ошибке — текст.
        ID работающего сервиса здесь не подходит. Ответ закрывается внутри.
        """
        if not id or not kind:
            raise ValueError("Resource id and kind are required")
        return self._result("GET", f"resources/{self._path(kind)}/{self._path(id)}")[1]

    def get_content_by_id(self, content_id, sub_kind):
        """Получить полную конфигурацию content_id типа sub_kind.

        Эквивалент чтения resources/{sub_kind}/{content_id}; для словарей
        KUMA 2 добавляет size=5001. Возвращает JSON либо текст HTTP-ошибки;
        не выполняет дополнительной пагинации содержимого словаря.
        """
        params = (
            {"size": 5001}
            if self._major_version == 2 and sub_kind == "dictionary"
            else None
        )
        return self._result(
            "GET",
            f"resources/{self._path(sub_kind)}/{self._path(content_id)}",
            params=params,
        )[1]

    def get_all_tenant_content(self, tenant_id: str, kind: str = ""):
        """Вернуть конфигурации tenant_id, при kind='' — всех типов.

        Применяет фильтр tenantID без переключения выбранных тенантов.
        Возвращает список всех страниц либо текст HTTP-ошибки, как get_resources().
        """
        # The explicit filter avoids changing the caller's selected tenants.
        return self.get_resources(kind, tenant_id)

    def get_correlation_rule_id_by_name(self, tenant_id):
        """Вернуть список полных объектов правил корреляции тенанта tenant_id.

        Историческое имя сохранено: метод не принимает имя и не возвращает
        отдельный ID. Для поиска по имени нужен get_resource_id_by_name().
        HTTP-ошибка возвращается строкой, как в get_resources().
        """
        return self.get_resources("correlationRule", tenant_id)

    def get_all_correlator(self, tenant_id: str = ""):
        """Вернуть конфигурации корреляторов; tenant_id='' не задаёт фильтр.

        Результат — список ресурсов либо текст HTTP-ошибки. Для работающих
        экземпляров сервисов используйте get_all_services(kind='correlator').
        """
        return self.get_resources("correlator", tenant_id)

    def get_tenant_services(self, tenant_id: str, kind: str):
        """Вернуть конфигурации ресурсов kind в тенанте tenant_id.

        Название сохранено для совместимости: запрос идёт к resources,
        результат не является списком запущенных сервисов. Возвращает список
        либо строку HTTP-ошибки; см. get_resources() и get_all_services().
        """
        return self.get_resources(kind, tenant_id)

    def get_correlation_rule(self, rule_id: str):
        """Вернуть полный объект correlationRule по ID ресурса rule_id.

        Включает внешние поля id/name/tenantID и payload; HTTP-ошибка — строка.
        Только payload возвращает get_correlation_rule_by_id().
        """
        return self.get_resource(rule_id, "correlationRule")

    def get_correlation_rule_by_id(self, rule_id: str):
        """Вернуть только payload правила correlationRule с ID rule_id.

        Текст HTTP-ошибки передаётся как строка. Если успешный объект не
        содержит payload, возникает KeyError. Полный объект — get_correlation_rule().
        """
        data = self.get_correlation_rule(rule_id)
        return data["payload"] if isinstance(data, dict) else data

    def get_destination_by_id(self, content_id: str):
        """Вернуть payload ресурса destination по content_id либо текст ошибки.

        При отсутствии payload в объекте возникает KeyError. Для внешних
        полей конфигурации используйте get_resource(content_id, 'destination').
        """
        data = self.get_resource(content_id, "destination")
        return data["payload"] if isinstance(data, dict) else data

    def get_correlator_by_id(self, content_id: str):
        """Вернуть полную конфигурацию correlator по ID ресурса content_id.

        Возвращает объект с payload либо текст HTTP-ошибки; это не ID сервиса.
        Вложенный payload.rules используется методами привязки правил через PUT.
        """
        return self.get_resource(content_id, "correlator")

    def get_dependences(self, resource_id: str):
        """GET resources/dependencies/{resource_id}: получить зависимости ресурса.

        Возвращает JSON сервера либо текст HTTP-ошибки. Написание сохранено
        для совместимости; get_dependencies() вызывает этот же метод.
        """
        return self._result("GET", f"resources/dependencies/{self._path(resource_id)}")[
            1
        ]

    def get_dependencies(self, resource_id: str):
        """Алиас get_dependences(resource_id) с исправленным написанием."""
        return self.get_dependences(resource_id)

    def get_content_by_folder_id(self, folder_id: str, sub_kind: str):
        """Алиас get_folder_content(folder_id, sub_kind); результат не меняется."""
        return self.get_folder_content(folder_id, sub_kind)

    def get_folder_content(self, folder_id, sub_kind: str):
        """Вернуть все ресурсы типа sub_kind с фильтром folderID=folder_id.

        Собирает страницы в список, не обходит вложенные папки рекурсивно.
        HTTP-ошибка возвращается текстом, ошибка формата/пагинации — APIError.
        """
        return self._collect_rows(
            f"resources/{self._path(sub_kind)}", params={"folderID": folder_id}
        )

    def get_all_folders_content(self, sub_kind: str):
        """Вернуть все доступные ресурсы sub_kind, без фильтра по папке.

        Это общий список из get_resources(), а не дерево папок. HTTP-ошибка
        возвращается строкой; весь успешный результат собирается в памяти.
        """
        return self.get_resources(sub_kind)

    @staticmethod
    def _resource_body(resource, new_name=None):
        body = deepcopy(resource)
        if new_name is not None:
            body["name"] = new_name
            body["payload"]["name"] = new_name
        return body

    def _update_resource(self, resource, new_name=None):
        body = self._resource_body(resource, new_name)
        return self._result(
            "PUT",
            f"resources/{self._path(body['kind'])}/{self._path(body['id'])}",
            json=body,
        )

    def update_resource(self, resource: dict, new_name: str = None):
        """PUT resources/{kind}/{id}: записать полную конфигурацию resource.

        Передавайте объект из get_resource(), сохраняя version и остальные
        поля серверной схемы. kind и id берутся из объекта. new_name, если
        указан, заменяет name снаружи и внутри payload. Входной словарь
        копируется и не изменяется. Возвращает JSON/None либо текст HTTP-ошибки,
        без статуса. Конкурентные изменения согласует вызывающий код.
        """
        return self._update_resource(resource, new_name)[1]

    def create_resource(
        self, resource: dict, tenant_id: str, folder_id: str, new_name: str = None
    ):
        """POST resources/{kind}: создать конфигурацию по образцу resource.

        resource — полный объект с kind и payload; tenant_id — целевой тенант,
        folder_id — целевая папка, '' для корня. new_name меняет оба поля name.
        В копии сбрасываются внешний id и payload.id, задаются tenantID,
        tenantName и folderID. Входной объект остаётся неизменным.
        Возвращает (status, JSON/None), при HTTP-ошибке — (status, text).
        """
        body = self._resource_body(resource, new_name)
        body.update(id="", tenantID=tenant_id, tenantName="", folderID=folder_id)
        body.pop("tanantName", None)
        body["payload"]["id"] = ""
        return self._result("POST", f"resources/{self._path(body['kind'])}", json=body)

    def update_or_create_resource(
        self,
        resource: dict,
        tenant_id: str = "",
        folder_id: str = "",
        new_name: str = None,
    ) -> int:
        """Обновить resource; создать только после HTTP 404 и при tenant_id.

        resource должен содержать kind, id, payload. Копия очищается от exportID,
        repositoryPackageID, userID/userName; folderID заменяется на folder_id
        даже при значении ''. new_name обрабатывается как в update_resource().
        tenant_id используется только при создании, не переносит существующий
        ресурс в другой тенант. Возвращает итоговый HTTP-статус. Ошибки 403,
        409 и другие не запускают создание. Последовательность PUT/POST
        не является атомарной операцией; повторные записи согласует приложение.
        """
        body = self._resource_body(resource)
        body.update(
            exportID="",
            repositoryPackageID="",
            userID="",
            userName="",
            folderID=folder_id,
        )
        status, _ = self._update_resource(body, new_name)
        if status == 404 and tenant_id:
            status, _ = self.create_resource(body, tenant_id, folder_id, new_name)
        return status

    def create_corrRule(
        self, rule: dict, folder_id: str, tenant_id: str, new_name: str = None
    ):
        """Создать правило из полного объекта rule через create_resource().

        Порядок аргументов: rule, folder_id, tenant_id, new_name. kind берётся
        из rule и должен соответствовать правилу корреляции. При успехе
        возвращает JSON/None, при HTTP-ошибке — [] вместо текста и статуса.
        """
        status, data = self.create_resource(rule, tenant_id, folder_id, new_name)
        return data if 200 <= status < 300 else []

    def delete_resource(self, resource_id: str, kind: str):
        """Удалить один ресурс по ID; вернуть (text, status).

        KUMA 3/4: DELETE resources/{kind}/{id}, как в веб-консоли.
        Для KUMA 2 сохранён DELETE коллекции с ids. HTTP-ошибка также
        возвращается этой парой; ответ закрывается внутри.
        """
        if self._major_version >= 3:
            endpoint = f"resources/{self._path(kind)}/{self._path(resource_id)}"
            kwargs = {}
        else:
            endpoint = f"resources/{self._path(kind)}"
            kwargs = {"json": {"ids": [resource_id]}}
        status, text = self._result(
            "DELETE",
            endpoint,
            text=True,
            **kwargs,
        )
        return text, status

    def move_content(self, folderID, resourceIDs):
        """POST misc/resource/move: переместить ресурсы в папку folderID.

        resourceIDs — непустой ID либо список непустых строк ID ресурсов;
        пустые/нестроковые значения вызывают ValueError. Для KUMA 3/4 ID
        передаются как ids с searchType='ids', повторы удаляются с сохранением
        порядка; KUMA 2 получает resourceIDs. Возвращает requests.Response
        без проверки HTTP-статуса: вызывающий код обязан закрыть ответ.

        Example:
            with client.move_content(folder_id, [resource_id]) as response:
                response.raise_for_status()
        """
        ids = resourceIDs if isinstance(resourceIDs, list) else [resourceIDs]
        if not ids or any(not isinstance(id_, str) or not id_ for id_ in ids):
            raise ValueError("At least one nonempty resource ID is required")
        body = {"folderID": folderID}
        if self._major_version >= 3:
            body.update(ids=list(dict.fromkeys(ids)), searchType="ids")
        else:
            body["resourceIDs"] = ids
        return self._send(
            "POST",
            "misc/resource/move",
            json=body,
        )

    def iter_services(self, kind=None, *, page_size=250):
        """Выдавать объекты запущенных сервисов из GET services/ по страницам.

        kind — необязательный тип сервиса; page_size — положительный размер
        запроса. Читает до пустой страницы, поддерживает обёртку result.
        HTTP-ошибка, неверный формат или повтор страницы вызывают APIError.
        Полный список не накапливается; хранится текущая страница и отпечатки.
        """
        return self._iter_rows(
            "services/", params={"kind": kind} if kind else None, page_size=page_size
        )

    def get_all_services(self, kind=None):
        """Собрать все сервисы в список; kind=None не ограничивает тип.

        Возвращает список либо текст HTTP-ошибки. Для обработки без накопления
        полного списка используйте iter_services(). Это работающие сервисы,
        а не конфигурации из resources; связь с конфигурацией — поле resourceID.
        """
        return self._collect_rows("services/", params={"kind": kind} if kind else None)

    def get_services_ids_by_resource_id(self, resource_id: str):
        """Вернуть ID всех сервисов с resourceID, равным resource_id.

        Загружает get_all_services() и фильтрует локально. При отсутствии
        совпадений возвращает [], при HTTP-ошибке получения сервисов — её текст.
        """
        services = self.get_all_services()
        if isinstance(services, str):
            return services
        return [
            service["id"]
            for service in services
            if service.get("resourceID") == resource_id
        ]

    def get_service_id_by_resource_id(self, resource_id):
        """Вернуть первый ID сервиса для resource_id, None либо текст ошибки.

        Порядок определяется ответом сервера; при нескольких экземплярах
        используйте get_services_ids_by_resource_id().
        """
        ids = self.get_services_ids_by_resource_id(resource_id)
        return ids if isinstance(ids, str) else next(iter(ids), None)

    # Historical misspellings remain available for existing callers.
    def get_service_id_by_resouce_id(self, resource_id):
        """Совместимый алиас get_service_id_by_resource_id(), включая результат."""
        return self.get_service_id_by_resource_id(resource_id)

    def get_services_id_by_resouce_id(self, resource_id: str):
        """Совместимый алиас get_services_ids_by_resource_id(), включая результат."""
        return self.get_services_ids_by_resource_id(resource_id)

    def reload_service(self, service_id) -> None:
        """Перечитать конфигурацию одного запущенного сервиса service_id.

        POST services/id/{service_id}/reload; нужен ID сервиса, не ресурса.
        Возвращает None, HTTP-ошибка вызывает APIError. Не является restart.
        """
        self._result(
            "POST",
            f"services/id/{self._path(service_id)}/reload",
            json={},
            strict=True,
            text=True,
        )

    def reload_services(self, resource_id: str):
        """Последовательно перечитать все сервисы конфигурации resource_id.

        Возвращает список пар [HTTP-статус, ID сервиса], [] при отсутствии
        сервисов либо текст ошибки получения их списка. HTTP-ошибка отдельного
        reload сохраняется кодом и не прерывает остальные вызовы. Сетевая
        ошибка прерывает обход; уже выполненные reload не отменяются.
        """
        ids = self.get_services_ids_by_resource_id(resource_id)
        if isinstance(ids, str):
            return ids
        return [
            [
                self._result(
                    "POST", f"services/id/{self._path(id_)}/reload", text=True
                )[0],
                id_,
            ]
            for id_ in ids
        ]

    def get_version(self):
        """Прочитать сервисы Core и вернуть фактическую версию major.minor.

        Использует iter_services(), игнорирует остальные виды сервисов и Core
        без заполненного version. Различия patch/build допустимы. Если не
        найдено ни одной версии или major.minor различаются, вызывает APIError;
        некорректная заполненная версия — ValueError/TypeError. HTTP-ошибки
        итератора передаются наружу. self.version и contract_version не меняются;
        фактическая версия 4.1 возвращается как '4.1', несмотря на контракт 4.0.
        """
        from kuma._common.versions import normalize_version

        versions = {
            normalize_version(row["version"])
            for row in self.iter_services()
            if row.get("kind") == "core" and row.get("version")
        }
        if len(versions) != 1:
            raise APIError("Core version is missing or differs between Core services")
        return versions.pop()
