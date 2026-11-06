"""Tenants and folders, including restoration of KUMA 2 tenant selection."""

import json
from contextlib import contextmanager
from copy import deepcopy

from kuma.constants import SHARED_TENANT
from kuma.errors import APIError


class PrivateFolders:
    @property
    def selected_tenant(self):
        """Совместимое имя selected_tenants: тот же список, без копирования.

        Присваивание меняет только локальный список. Выбор на сервере меняет
        private_select_tenant(), текущее состояние считывает whoami().
        """
        return self.selected_tenants

    @selected_tenant.setter
    def selected_tenant(self, value):
        self.selected_tenants = value

    @staticmethod
    def _is_shared(row):
        return (
            row.get("tenantID") == SHARED_TENANT["id"]
            or row.get("tenantName") == "Shared"
        )

    def _remember_selection(self, selected):
        self.selected_tenants = [
            (
                deepcopy(row)
                if isinstance(row, dict)
                else deepcopy(self._tenants.get(row, {"id": row, "name": ""}))
            )
            for row in selected
        ]

    def private_select_tenant(self, tenant_ids=None, select_all: bool = False):
        """Изменить выбранные тенанты текущей серверной сессии; вернуть None.

        tenant_ids — список ID; None/[] снимает выбор. select_all=True имеет
        приоритет и выбирает все доступные тенанты. Сначала выполняется whoami().
        KUMA 2 использует POST users/tenants/select, KUMA 3/4 —
        PUT standaloneUsers/{user_id}/selectTenants. После успешной записи
        обновляется selected_tenants; HTTP-ошибка записи вызывает APIError.
        Этот выбор влияет на видимость данных в последующих запросах клиента.
        """
        user = self.whoami()
        if select_all:
            if self._major_version == 2:
                tenant_ids = list(user["tenants"])
            else:
                tenant_ids = [tenant["id"] for tenant in self.get_all_tenants()]
        tenant_ids = list(tenant_ids or ())
        if self._major_version == 2:
            self._result(
                "POST",
                "users/tenants/select",
                data=json.dumps({"ids": tenant_ids}),
                strict=True,
                text=True,
            )
        else:
            self._result(
                "PUT",
                f"standaloneUsers/{self._path(user['id'])}/selectTenants",
                data=json.dumps({"tenantIDs": tenant_ids}),
                strict=True,
                text=True,
            )
        self._remember_selection(tenant_ids)

    def get_all_tenants(self):
        """GET tenants/: получить список объектов доступных тенантов.

        Принимает ответы в виде списка или {"result": [...]}, обновляет
        локальный справочник ID/имён. Для KUMA 2 добавляет Shared, если сервер
        его не вернул. Выбор тенантов не меняет. HTTP-ошибки и неожиданный
        формат коллекции вызывают APIError.
        """
        status, data = self._result("GET", "tenants/", strict=True)
        tenants = self._rows(data, status)
        if self._major_version == 2 and not any(
            t.get("id") == SHARED_TENANT["id"] for t in tenants
        ):
            tenants = tenants + [deepcopy(SHARED_TENANT)]
        self._tenants = {tenant["id"]: deepcopy(tenant) for tenant in tenants}
        return tenants

    def get_tenant_id_by_name(self, name):
        """Найти тенант по точному имени name; вернуть первый ID либо None.

        Каждый вызов обновляет список через get_all_tenants(); регистр имени
        учитывается. Ошибки получения списка не подавляются.
        """
        return next(
            (
                tenant["id"]
                for tenant in self.get_all_tenants()
                if tenant.get("name") == name
            ),
            None,
        )

    def get_tenant_shared(self):
        """Вернуть ID доступного тенанта с точным именем Shared.

        Использует get_all_tenants() и вызывает APIError, если Shared не найден.
        """
        tenant_id = self.get_tenant_id_by_name("Shared")
        if tenant_id is None:
            raise APIError("Could not find tenant 'Shared'")
        return tenant_id

    @contextmanager
    def _temporary_tenants(self, tenant_ids):
        """Временно выбрать tenant_ids и восстановить прежние после блока.

        При ошибке блока сбой восстановления логируется, исходное исключение
        сохраняется. При успешном блоке ошибка восстановления передаётся наружу.
        """
        previous = [tenant["id"] for tenant in self.selected_tenants]
        self.private_select_tenant(tenant_ids)
        try:
            yield
        except BaseException:
            try:
                self.private_select_tenant(previous)
            except Exception:
                self.logger.error(
                    "Could not restore selected tenants after a failed request"
                )
            raise
        else:
            self.private_select_tenant(previous)

    def iter_folders(self, sub_kind=None, *, page_size=250):
        """Выдавать объекты папок, предварительно получив полный снимок.

        Args:
            sub_kind: Тип содержимого, например correlationRule или filter;
                None не ограничивает тип папок.
            page_size: Положительный начальный limit, а не предел числа папок.

        KUMA 3.4 нестабильно сортирует одинаковые имена: обычные страницы
        offset/limit могут терять записи. Поэтому снимок читается с offset=0
        и растущим limit, затем проверяется отсутствие остатка. Снимок
        буферизуется в памяти; это не потоковая загрузка папок с сервера.

        KUMA 2 обходится по тенантам: с sub_kind — выбранным, без него — всем
        доступным. Прежний выбор восстанавливается после каждого запроса,
        включая ошибку; дубликаты (tenantID, id) исключаются.
        Неверный page_size вызывает ValueError. HTTP-ошибка, ограничение
        сервера, мешающее получить полный снимок, или превышение предельного
        limit в 1 000 000 вызывают APIError вместо выдачи неполного списка.
        """
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or page_size < 1
        ):
            raise ValueError("page_size must be a positive integer")
        params = {"subKind": sub_kind} if sub_kind else None
        if self._major_version != 2:
            yield from self._folder_snapshot(params, page_size)
            return
        # KUMA 2 limits visibility to the current selection; always restore it.
        self.whoami()
        tenants = (
            deepcopy(self.selected_tenants) if sub_kind else self.get_all_tenants()
        )
        seen = set()
        for tenant in tenants:
            with self._temporary_tenants([tenant["id"]]):
                rows = self._folder_snapshot(params, page_size)
            for row in rows:
                identity = (row.get("tenantID"), row["id"])
                if identity not in seen:
                    seen.add(identity)
                    yield row

    def _folder_snapshot(self, params, limit):
        # KUMA 3.4 sorts folders by non-unique names and has no stable ID order.
        # Fetch one complete prefix instead of merging inconsistent offset pages.
        while True:
            query = {**(params or {}), "limit": limit, "offset": 0}
            status, data = self._result("GET", "folders/", params=query, strict=True)
            rows = self._rows(data, status)
            if len(rows) < limit:
                query = {**query, "limit": 1, "offset": len(rows)}
                status, tail = self._result(
                    "GET", "folders/", params=query, strict=True
                )
                if self._rows(tail, status):
                    raise APIError(
                        "Server capped the folder snapshot; complete folder enumeration is unavailable",
                        status,
                    )
                return rows
            limit *= 2
            if limit > 1000000:
                raise APIError(
                    "Folder snapshot exceeds one million entries; narrow sub_kind or tenant selection",
                    status,
                )

    def _folder_list(self, sub_kind, include_share, only_shared, include_root=False):
        folders = list(self.iter_folders(sub_kind))
        if include_root:
            if not self.selected_tenants:
                self.whoami()
            for tenant in self.selected_tenants:
                folders.append(
                    {
                        "name": "",
                        "id": f"{sub_kind}-{tenant['id']}",
                        "tenantID": tenant["id"],
                        "tenantName": tenant.get("name", ""),
                        "kind": "resource",
                        "subKind": sub_kind,
                        "parentID": "",
                    }
                )
        if only_shared:
            return [folder for folder in folders if self._is_shared(folder)]
        if not include_share:
            return [folder for folder in folders if not self._is_shared(folder)]
        return folders

    def get_all_folders_by_kind(
        self,
        sub_kind="correlationRule",
        include_share: bool = True,
        only_shared: bool = False,
        include_root: bool = False,
    ):
        """Вернуть список папок для sub_kind с фильтрацией Shared и корней.

        sub_kind — тип ресурса; по умолчанию correlationRule.
        include_share=False исключает Shared. only_shared=True оставляет
        только Shared и имеет приоритет над include_share. Shared определяется
        по tenantID либо имени Shared; пустое tenantName не является признаком.
        include_root=True добавляет виртуальную корневую папку для каждого
        выбранного тенанта: ID '<sub_kind>-<tenant_id>', parentID='', name=''.
        Эти записи не создаются на сервере. Особенности памяти, выбора тенантов
        и ошибки чтения описаны в iter_folders().
        """
        return self._folder_list(sub_kind, include_share, only_shared, include_root)

    def get_all_folders(self, include_share=True, only_shared=False):
        """Вернуть список папок всех типов без добавления виртуальных корней.

        include_share=False исключает Shared; only_shared=True оставляет
        только Shared независимо от include_share. Использует iter_folders(),
        собирает снимок в памяти и передаёт его ошибки вызывающему коду.
        """
        return self._folder_list(None, include_share, only_shared)

    def get_folder_id_by_name(self, folder_name, sub_kind, tenant_id, parent_id):
        """Найти папку по точному имени, типу, тенанту и родительской папке.

        Все четыре условия должны совпасть. parent_id='' обозначает верхний
        уровень, не произвольного родителя. Возвращает первый ID либо None;
        поиск идёт по iter_folders(sub_kind), с его правилами выбора и ошибок.
        """
        return next(
            (
                folder["id"]
                for folder in self.iter_folders(sub_kind)
                if folder.get("name") == folder_name
                and folder.get("tenantID") == tenant_id
                and folder.get("parentID") == parent_id
            ),
            None,
        )

    def create_folder(
        self,
        name: str,
        tenant_id: str,
        parent_id: str = "",
        sub_kind: str = "correlationRule",
    ):
        """POST folders/: создать папку ресурсов и вернуть историческую тройку.

        name — имя папки; tenant_id — ID тенанта; parent_id — ID родителя
        либо '' для верхнего уровня; sub_kind — тип ресурсов в папке.
        В KUMA 2 дополнительно передаётся ID пользователя из self.user/whoami().

        Returns:
            При успехе (status, JSON, text), при HTTP-ошибке (status, status,
            text). Третье значение — исходный текст ответа, а не сообщение
            клиента. Ответ закрывается автоматически; HTTP-ошибки не вызывают
            APIError, но некорректный JSON успешного ответа вызывает его.
        """
        body = {
            "id": "",
            "kind": "resource",
            "name": name,
            "parentID": parent_id,
            "subKind": sub_kind,
            "tenantID": tenant_id,
            "tenantName": "",
            "userID": "",
        }
        if self._major_version == 2:
            body.update(
                createdAt=0, description="", userID=(self.user or self.whoami())["id"]
            )
        response = self._send("POST", "folders/", json=body)
        text = response.text
        status, data = self._response_result(response)
        return status, data if 200 <= status < 300 else status, text
