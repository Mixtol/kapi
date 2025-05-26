import json
import urllib
import urllib.parse
import uuid
from typing import Any, Tuple

import requests

from .consants import SHARED_TENANT
from .logging import configure_logging

_logger = configure_logging()
_api_version = "v2.1"


class KumaPrivateAPI:
    """
    Class for working with the API via port 7220.

    This library describes methods for interacting with SIEM KUMA using the installed session and received session
     objects on port 7220 of the system core.
    """

    def __init__(
        self,
        url,
        username,
        password,
        existing_session_data=None,
        version="2.1.0",
    ):
        self.url = url + ":7220"
        self.user = {}
        self.username = username
        self.password = password
        self.version = version
        self.session = requests.Session()
        self.session.verify = False
        self.selected_tenants = []

        if existing_session_data:
            try:
                self.load_session(existing_session_data)
            except Exception as exception:
                _logger.error(f"Error occurred when loading session: {exception}")
                self.initialize_session()

        else:
            self.initialize_session()

    # TODO: session = PrivateKumaSession.create_session(url, username, password)
    @classmethod
    def create_session(
        cls, url, username, password, existing_session_data=None, cert=None
    ):
        session = cls(url, username, password, existing_session_data, cert)
        if existing_session_data:
            session.load_session(existing_session_data)
        else:
            session.initialize_session()

        return session

    def load_session(self, session_data):
        self.session.cookies.update(
            requests.utils.cookiejar_from_dict(session_data["cookies"])
        )
        self.session.headers.update(session_data["headers"])
        self.session.headers.update({"X-XSRF-TOKEN": session_data["xsrf_token"]})

    def initialize_session(self):
        response = self.login(self.username, self.password)
        if response.status_code == 200:
            self.version = "2.1.0"
            self.private_select_tenant(select_all=True)
        elif response.status_code in (401, 402, 403):
            raise ConnectionError(
                f"Bad credentials {self.url} response: {response.status_code} {response.text}"
            )

        raise ConnectionError(
            f"Cannot connect to {self.url} response: {response.status_code} {response.text}"
        )

    def login(self, username, password, timeout: int = 10):
        payload = json.dumps({"login": username, "password": password})
        response = self.session.post(
            f"{self.url}/api/login", data=payload, timeout=timeout
        )
        self.session.headers.update(
            {"X-XSRF-TOKEN": urllib.parse.unquote(self.session.cookies["XSRF-TOKEN"])}
        )
        return response

    def get_session_data(self) -> dict:
        return {
            "headers": dict(self.session.headers),
            "cookies": requests.utils.dict_from_cookiejar(self.session.cookies),
            "xsrf_token": self.session.headers.get("X-XSRF-TOKEN"),
            "version": self.version,
        }

    def logout(self) -> int:
        return self.session.post(f"{self.url}/api/logout").status_code

    def whoami(self):
        """Getting information about the current user."""
        try:
            response = self.session.get(f"{self.url}/api/whoami")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exception:
            _logger.error(
                f"Error occurred when getting information about the current user: {exception}"
            )
            raise ConnectionError

    def private_select_tenant(
        self, tenant_ids: list = [], select_all: bool = False
    ) -> str:
        """
        Функция получает на вход Json с массивом IDs тенантов, с которыми можно производить манипуляции
        (То самое окно слева в куме)
        payload = {
            'ids': []
            }
        """
        user = self.whoami()
        if select_all:
            if self.version.startswith("2"):
                tenant_ids = list(user["tenants"].keys())

            elif self.version.startswith("3"):
                tenant_ids = []
                all_tenants = self.session.get(f"{self.url}/api/private/tenants/")
                if all_tenants.status_code != 200:
                    return all_tenants.text

                for tenant in all_tenants.json():
                    tenant_ids.append(tenant["id"])

        if self.version.startswith("2"):
            payload = {"ids": []}
            for tenant_id in tenant_ids:
                payload["ids"].append(tenant_id)

            _ = self.session.post(
                f"{self.url}/api/private/users/tenants/select", data=json.dumps(payload)
            )

        elif self.version.startswith("3"):
            payload = {"tenantIDs": []}
            for tenant_id in tenant_ids:
                payload["tenantIDs"].append(tenant_id)

            _ = self.session.put(
                f"{self.url}/api/private/standaloneUsers/{user['id']}/selectTenants",
                data=json.dumps(payload),
            )

    def get_all_tenants(self):
        all_tenants = self.session.get(f"{self.url}/api/private/tenants/").json()
        if self.version.startswith("2"):
            all_tenants.append(SHARED_TENANT)

        return all_tenants

    def get_all_tenant_content(self, tenant_id: str, kind: str = "") -> Any:
        """Функция для получения всего контента из тенанта
        Args:
            tenant_id: ID of tenant.
            kind (str, optional): Опция контента, correlationRule и тп,
                можно получить только конкретный контент если указать. Defaults to ''.
        """
        self.private_select_tenant([tenant_id])

        if kind:
            kind += "/"

        if self.version.startswith("2"):
            url = f"{self.url}/api/private/resources/{kind}?tenantID={tenant_id}"
        elif self.version.startswith("3"):
            filter_expression = '{"tenantID":["' + tenant_id + '"]}'
            url = f"{self.url}/api/private/resources/{kind}?filter={urllib.parse.quote(filter_expression)}"
        else:
            url = ""

        response = self.session.get(url)
        return response.json() if response.status_code == 200 else response.text

    def get_tenant_id_by_name(self, name):
        response_json = self.session.get(f"{self.url}/api/private/tenants/").json()
        for tenant in response_json:
            if tenant["name"] == name:
                return tenant["id"]

    def get_correlation_rule_id_by_name(self, tenant_id) -> list:
        response = self.session.get(
            f"{self.url}/api/private/resources/correlationRule?size=999999",
            params={"filter": {"tenantID": tenant_id}},
        )

        return response.json() if response.status_code == 200 else response.text

    def get_all_correlator(self, tenant_id) -> Any:
        return self.session.get(
            f"{self.url}/api/private/resources/correlator?tenantID={tenant_id}"
        ).json()

    def get_tenant_services(self, tenant_id: str, kind: str) -> list | None:
        """Функция возвращающая сервисы заданного типа по тенанту
        Args:
            tenant_id (str): tenantID
            kind (str): storage|agent|correlator|collector
        Returns:
            list: ...
        """
        response = self.session.get(
            f"{self.url}/api/private/resources/{kind}?tenantID={tenant_id}"
        )
        if response.status_code in (200, 204):
            return response.json()

    def get_resource(self, id: str = None, kind: str | None = None) -> dict:
        response = self.session.get(f"{self.url}/api/private/resources/{kind}/{id}")
        return response.json() if response.status_code == 200 else response.text

    def get_resources(self, kind: str | None = None, tenant_id: str = "") -> list:
        response = self.session.get(
            f"{self.url}/api/private/resources/{kind}?tenantID={tenant_id}"
        )
        return response.json() if response.status_code == 200 else response.text

    def get_correlation_rule_by_id(self, correlation_rule_id):
        return self.session.get(
            f"{self.url}/api/private/resources/correlationRule/{correlation_rule_id}"
        ).json()["payload"]

    def get_correlation_rule(self, rule_id):
        """
        New function for getting full rule.

        Returns:
            dict: Rule dictionary with payload in it.
        """
        response = self.session.get(
            f"{self.url}/api/private/resources/correlationRule/{rule_id}"
        )
        return response.json() if response.status_code == 200 else response.text

    def get_content_by_folder_id(self, folder_id, sub_kind):
        """
        Method for getting content from folder.

        Args:
            folder_id: ID of folder.
            sub_kind: Resource type (correlationRule, filter, aggregationRule, normalizer, secret, activList,
            dictionary, connector, segmentationRule, collector, correlator, etc...)
        Returns:
            list: List of resources.
        """
        return self.session.get(
            f"{self.url}/api/private/resources/{sub_kind}?folderID={folder_id}"
        ).json()

    def get_destination_by_id(self, content_id: str):
        return self.session.get(
            f"{self.url}/api/private/resources/destination/{content_id}"
        ).json()["payload"]

    def get_dependences(self, resource_id: str):
        return self.session.get(
            f"{self.url}/api/private/resources/dependencies/{resource_id}"
        ).json()

    def get_correlator_by_id(self, content_id: str):
        response = self.session.get(
            f"{self.url}/api/private/resources/correlator/{content_id}"
        )
        return response.json() if response.status_code == 200 else response.text

    def get_all_services(self, kind: str | None = None):
        """The function for receiving all instance services"""
        if kind:
            url = f"{self.url}/api/private/services/?pattern=&size=1000&kind={kind}"
        else:
            url = f"{self.url}/api/private/services/?pattern=&size=10000"

        response = self.session.get(url)
        return response.json() if response.status_code == 200 else response.text

    def get_service_id_by_resouce_id(self, resource_id) -> str | None:
        response = self.session.get(f"{self.url}/api/private/services/")
        for service in response.json():
            if service["resourceID"] == resource_id:
                return service["id"]
        return None

    def get_content_by_id(self, content_id, sub_kind):
        """Функция для возвращения всего обьекта по его ID
        Args:
            sub_kind: Тип контента, который нужно вернуть (correlationRule, filter, aggregationRule, normalizer, secret,
            activList, dictionary, connector, segmentationRule, collector, correlator, etc...)
        Returns:
            duct: KUMA full object ##### АККУРАТНЕЕ C ВЫБРАННЫМИ ТЕНАНТАМИ
        """
        if self.version.startswith("2") and sub_kind == "dictionary":
            content_id += "?size=5001"
        response = self.session.get(
            f"{self.url}/api/private/resources/{sub_kind}/{content_id}"
        )

        return response.json() if response.status_code == 200 else response.text

    def get_all_folders_by_kind(
        self,
        sub_kind="correlationRule",
        include_share: bool = True,
        only_shared: bool = False,
        include_root: bool = False,
    ):
        """
        Функция для возвращения всех папок.

        Поскольку нет возможности возвращать более 250 папок во 2 версии, мы
        по очереди выбираем тенанты и их папки, так что если в 1 тенанте более 250 папкок
        будет ошибка. Далее мы возвращаем выбранные тенанты, как было и выходим с папками.

        Args:
            sub_kind: Тип папок, которые нужно вернуть (correlationRule, filter, aggregationRule, normalizer, secret,
            activList, dictionary, connector, segmentationRule, collector, correlator, etc...)
            include_share: Включать ли папки общего доступа
            only_shared: Выводить только папки общего доступа
            include_root: ...
        Returns:
            list: KUMA folders
        """
        all_folders = []
        tenant_ids = []

        if self.version.startswith("2"):
            url = f"{self.url}/api/private/folders/?subKind={sub_kind}&size=1000"

            folders_set = set()
            for tenant in self.selected_tenants:
                tenant_ids.append(tenant["id"])
                self.private_select_tenant([tenant["id"]])
                response = self.session.get(url).json()
                folders_set.update(map(json.dumps, response))
            self.private_select_tenant(tenant_ids)

            all_folders = list(map(json.loads, folders_set))
        elif self.version.startswith("3"):
            url = f"{self.url}/api/private/folders/?limit=10000&subKind={sub_kind}"
            all_folders = self.session.get(url).json()

        if include_root:
            for tenant in self.selected_tenants:
                root_folder = {
                    "name": "",
                    "id": f"{sub_kind}-{tenant['id']}",
                    "tenantID": tenant["id"],
                    "tenantName": "",
                    "kind": "resource",
                    "subKind": sub_kind,
                    "parentID": "",
                }
                all_folders.append(root_folder)

        if only_shared:
            all_folders = [
                folder for folder in all_folders if folder["tenantName"] == "Shared"
            ]
        if include_share:
            all_folders = [
                folder for folder in all_folders if folder["tenantName"] != "Shared"
            ]
        return all_folders

    def get_all_folders(self, include_share=True, only_shared=False):
        """
        returns list: KUMA folders
        """
        all_folders = []
        tenant_ids = []
        try:
            if self.version.startswith("2"):
                folders_set = set()

                for tenant in self.get_all_tenants():
                    tenant_ids.append(tenant["id"])
                    self.private_select_tenant([tenant["id"]])

                    response = self.session.get(
                        f"{self.url}/api/private/folders/?limit=10000"
                    )
                    if response.status_code == 200:
                        response = response.json()
                    else:
                        return response.text
                    folders_set.update(map(json.dumps, response))

                self.private_select_tenant(tenant_ids)
                all_folders = list(map(json.loads, folders_set))
            elif self.version.startswith("3"):
                response = self.session.get(
                    f"{self.url}/api/private/folders/?limit=10000"
                )
                all_folders = response.json()
        except Exception as exception:
            _logger.error(f"Error occurred when getting all folders: {exception}")
            return response.text

        if only_shared:
            all_folders = [
                folder for folder in all_folders if folder["tenantName"] == "Shared"
            ]
        if not include_share:
            all_folders = [
                folder for folder in all_folders if folder["tenantName"] != "Shared"
            ]
        return all_folders

    def get_all_folders_content(self, sub_kind: str):
        """
        Функция для возвращения всего контента в папках.

        Args:
            sub_kind: Тип контента, который нужно вернуть (correlationRule, filter, aggregationRule, normalizer, secret,
            activList, dictionary, connector, segmentationRule, collector, correlator, etc...)
        Returns:
            list: KUMA folders content
        """
        return self.session.get(
            f"{self.url}/api/private/resources/{sub_kind}?size=999999"
        ).json()

    def get_folder_content(self, folder_id, sub_kind: str):
        """Функция для возвращения всего контента в папках
        Args:
            folder_id: ID папки, в которой нужно найти контент
            sub_kind: Тип контента, который нужно вернуть
            (correlationRule, filter, aggregationRule, normalizer,
            secret, activList, dictionary, connector, segmentationRule,
            collector, correlator, etc...)
        Returns:
            list: KUMA folders content
        """
        response = self.session.get(
            f"{self.url}/api/private/resources/{sub_kind}?folderID={folder_id}&size=999999"
        )
        return response.json() if response.status_code == 200 else response.text

    def get_folder_id_by_name(
        self, folder_name, sub_kind, tenant_id, parent_id
    ) -> str | None:
        response_json = self.session.get(
            f"{self.url}/api/private/folders/?subKind={sub_kind}"
        ).json()
        for folder in response_json:
            if (
                folder["name"] == folder_name
                and folder["tenantID"] == tenant_id
                and folder["parentID"] == parent_id
            ):
                return folder["id"]
        return None

    def reload_service(self, service_id) -> None:
        _ = self.session.post(
            f"{self.url}/api/private/services/id/{service_id}/reload",
            data=json.dumps({}),
        )

    def create_folder(
        self,
        name: str,
        tenant_id: str,
        parent_id: str = "",
        sub_kind: str = "correlationRule",
    ):
        payload = {
            "id": "",
            "kind": "resource",
            "name": name,
            "parentID": parent_id,
            "subKind": sub_kind,
            "tenantID": tenant_id,
            "tenantName": "",
            "userID": "",
        }
        if self.version.startswith("2"):
            payload["createdAt"] = 0000000000000
            payload["description"] = ""
            payload["userID"] = self.user["id"]

        response = self.session.post(
            f"{self.url}/api/private/folders/", data=json.dumps(payload)
        )
        return (
            response.status_code,
            response.json() if response.status_code == 200 else response.status_code,
            response.text,
        )

    def update_resource(self, resource: dict, new_name: str = None):
        """Функция получает обновленный обект ресурса
        и по его ID пытает обновить существуеющий
        Args:
            resource (dict): Обьект ресурса внутри которого есть payload
            new_name (str, optional): новое имя
        Returns:
            _type_: Обновленный ресурс
        """
        if new_name:
            resource["name"] = new_name
            resource["payload"]["name"] = new_name

        payload = json.dumps(resource)
        response = self.session.put(
            f'{self.url}/api/private/resources/{resource["kind"]}/{resource["id"]}',
            data=payload,
        )
        return response.json() if response.status_code == 200 else response.text

    def create_resource(
        self, resource: dict, tenant_id: str, folder_id: str, new_name: str = None
    ):
        resource["id"] = ""
        resource["payload"]["id"] = ""
        resource["tanantName"] = ""
        resource["tenantID"] = tenant_id
        resource["folderID"] = folder_id
        if new_name:
            resource["name"] = new_name
            resource["payload"]["name"] = new_name

        payload = json.dumps(resource)
        response = self.session.post(
            f'{self.url}/api/private/resources/{resource["kind"]}', data=payload
        )
        if response.status_code in (200, 201, 204, 500):
            return response.status_code, response.json()
        return response.status_code, response.text

    def update_or_create_resource(
        self,
        resource: dict,
        tenant_id: str = "",
        folder_id: str = "",
        new_name: str = None,
    ) -> int:
        """
        Функция для обновления или создания ресурсов KUMA.

        Returns:
            int: Статус ответа.
        """
        resource["exportID"] = ""
        resource["repositoryPackageID"] = ""
        resource["userID"] = ""
        resource["userName"] = ""
        resource["folderID"] = folder_id
        response = self.update_resource(resource, new_name)
        if response.status_code not in (200, 204) and tenant_id and folder_id:
            response = self.create_resource(resource, tenant_id, folder_id, new_name)

        if isinstance(response, dict):
            return response.json()
        else:
            return response

    def create_corrRule(
        self, rule: dict, folder_id: str, tenant_id: str, new_name: str = None
    ):
        """OLD LEGACY
        Функция создает корреляционное правило
        # если айди фолдера пустое создает просто в тенанте
        rule - само правило в куме с payload внутри
        """
        # Исправляем исходный массив
        old_name = rule["name"]
        url = self.url + "/api/private/resources/correlationRule"
        rule["folderID"] = folder_id
        rule["tenantID"] = tenant_id
        rule["id"] = str(uuid.uuid4())
        rule["exportID"] = str(uuid.uuid4())
        rule["payload"]["id"] = str(uuid.uuid4())
        if new_name:
            rule["name"] = new_name
            rule["payload"]["name"] = new_name
        else:
            rule["payload"]["name"] = rule["name"]
        payload = json.dumps(rule)
        response = self.session.post(url, data=payload)
        rule["name"] = old_name
        rule["payload"]["name"] = old_name
        if response.status_code == 200:
            return response.json()
        else:
            # 400 Возвращает если правило уже есть
            return []

    def link_rules(self, rules_IDs: list, correlator_IDs: list, rules_tenant_id: str):
        if self.version < 3:
            raise ConnectionAbortedError("This function is not supported in KUMA v2")

        response = self.session.post(
            f"{self.url}/api/private/resources/correlation_rule/bind",
            data=json.dumps(
                {
                    "correlationRuleIDs": rules_IDs,
                    "correlatorIDs": correlator_IDs,
                    "tenantID": rules_tenant_id,
                }
            ),
        )
        return response.status_code

    def link_rule_to_correlator(self, correlator_id, correlation_rule_id):
        try:
            url = f"{self.url}/api/private/resources/correlator/{correlator_id}"
            correlation_rule_payload = self.get_correlation_rule_by_id(
                correlation_rule_id
            )
            correlator_data = self.get_correlator_by_id(correlator_id)
            if "rules" not in correlator_data["payload"]:
                correlator_data["payload"]["rules"] = []

        except KeyError:
            return correlator_data

        for cor_rul in correlator_data["payload"]["rules"]:
            if cor_rul["id"] == correlation_rule_id:
                return "Rule already exist on correlator"

        correlator_data["payload"]["rules"].append(correlation_rule_payload)
        response = self.session.put(url, data=json.dumps(correlator_data))

        return (
            response.json()
            if response.status_code == 200
            else f"{response.status_code}:{response.text}"
        )

    def link_rules_to_correlator(self, correlator_id, rules_list):
        """Функция линковки правил к корреялтору
        Args:
            correlator_id (_type_): ID корреялтора
            rules_list (_type_): Передается лист с полноценными обектами правила
                с нагрузкой и всеми делами, но в самом корреляторе испоьзуется payload
        """
        url = self.url + "/api/private/resources/correlator/" + correlator_id
        correlator_data = self.get_correlator_by_id(correlator_id)
        if "rules" not in correlator_data["payload"]:
            # Обработка если коррелятор пустой
            correlator_data["payload"]["rules"] = []
            linked_rules_id = []
        else:
            # Быстро получаем список ID уже прилинкованных правил
            linked_rules_id = [
                rule["id"] for rule in correlator_data["payload"]["rules"]
            ]
        for new_rule in rules_list:
            if new_rule["id"] not in linked_rules_id:
                # Если правило не прилинковано добавляем в коррелятор
                correlator_data["payload"]["rules"].append(new_rule["payload"])
        response = self.session.put(url, data=json.dumps(correlator_data))
        if response.status_code != 200:
            return f"{response.status_code}:{response.text}"
        return response.json()

    def unlink_rules_from_correlator(self, correlator_id: str, rules_id: list):
        """Отлинковка правил, по факту презаливание корреялтора без правил
        Args:
            correlator_id (str): id UUID РЕСУРСА коррелятора
            rules_id (list): Список UUID правил
        Returns:
            dict|str: Ответ API или сообщение об ошибке/статусе
        """
        correlator_data = self.get_correlator_by_id(correlator_id)
        if not isinstance(correlator_data, dict):
            return f"Failed to get correlator data {correlator_id}: {correlator_data}"

        linked_rules = correlator_data.get("payload", {}).get("rules", [])
        if not linked_rules:
            return (
                f'Correlator {correlator_data.get("name")} has no linked rules at all'
            )

        rules_to_unlink = set(rules_id)
        updated_rules = []
        change_check = False
        for rule in linked_rules:
            if rule["id"] not in rules_to_unlink:
                updated_rules.append(rule)
            else:
                change_check = True

        if not change_check:
            return {"response": "Correlator didnt have these rules in linked list"}

        correlator_data["payload"]["rules"] = updated_rules
        return self.update_resource(correlator_data)

    def move_content(self, folderID, resourceIDs: list | str):
        """Функция перемещения из папки в папку контента"""
        url = self.url + "/api/private/misc/resource/move"
        payload = {
            "folderID": folderID,
            "resourceIDs": (
                resourceIDs if isinstance(resourceIDs, list) else [resourceIDs]
            ),
        }
        return self.session.post(url, data=payload)

    def export_geo(self):
        return self.session.get(self.url + "/api/private/geoip/export").json()

    def export_content(
        self,
        ids: list,
        tenant_id: str,
        password: str | None = None,
        file_path: str = "exported_content",
    ):
        """
        Функция скачивания ресурсов в файл с паролем
        """
        if not password:
            password = self.password
        try:
            payload = {"ids": ids, "password": password, "tenantID": tenant_id}
            response = self.session.post(
                f"{self.url}/api/private/export/resources", json=payload
            )
            response = self.session.get(
                f"{self.url}/api/private/download/{response.json()['fileID']}"
            )
            with open(file_path, "wb") as file:
                file.write(response.content)

            return response.status_code
        except Exception as exception:
            _logger.error(f"Error occurred when exporting content: {exception}")
            return f"{response.text} error:{exception}"

    def import_content(self, file_path: str, tenant_id: str, password=None, action=2):
        """
        Функция для загруки и установки с ЗАМЕНОЙ контента из файла экспорта.

        action:int - Это условие импорта контента
        2-принудительная замена
        1-создание если нет
        0-игнорирование
        """
        if not password:
            password = self.password
        try:
            with open(file_path, "rb") as file:
                files = {"file": file}
                file_id = self.session.post(
                    f"{self.url}/api/private/upload", files=files
                ).json()["id"]

            data = {"fileID": file_id, "password": password}
            response = self.session.post(
                f"{self.url}/api/private/import/toc", json=data
            ).json()

            actions = {}
            for resource in response["resources"]:
                actions[resource["id"]] = action

            data = {
                "actions": actions,
                "fileID": file_id,
                "password": password,
                "tenantID": tenant_id,
            }
            response = self.session.post(
                f"{self.url}/api/private/import/resources", json=data
            )
            return response.status_code
        except Exception as exception:
            _logger.error(f"Error occurred when importing content: {exception}")
            return response.status_code

    def delete_resource(self, resource_id: str, kind: str) -> Tuple[str, int]:
        payload = json.dumps({"ids": [resource_id]})
        response = self.session.delete(
            f"{self.url}/api/private/resources/{kind}", data=payload
        )
        return response.text, response.status_code

    def get_active_list_scan(
        self, correlator_service_id: str, active_list_id: str
    ) -> list:
        """Скан листа для приватного API
        Args:
            correlator_service_id (str): id СЕРВИСА отличается от ID ресурса
            active_list_id (str): id листа
        """
        response = self.session.get(
            f"{self.url}/api/private/services/id/{correlator_service_id}/activeLists/scan/{active_list_id}?limit=1000"
        )
        return response.json() if response.status_code == 200 else response.text

    def get_active_list_content(
        self, correlator_service_id: str, active_list_id: str
    ) -> str | Any:
        """
        Старая функция скачивает файл, потом разшифровывает его и возвращает словарь.

        correlator_service_id - id именно СЕРВИСА коррелятора, а не ресурса
        activeList_id - id активного листа, где TTL настраивается

        """
        url = f"{self.url}/api/private/services/id/{correlator_service_id}"
        url += "/activeLists/export/" + active_list_id
        response = self.session.get(url, verify=False)
        if response.status_code != 200:
            return response.text

        file_id = response.json()["id"]
        url = f"{self.url}/api/private/download/{file_id}"
        response = self.session.get(url, verify=False)
        if response.status_code == 200:
            with open("test_file1", "w") as file:
                file.write(response.content)
            with open("test_file2", "w") as file:
                file.write(response.content.decode("utf-8"))
            return response.json()
        else:
            return response.text

    def delete_activeList_record(
        self, correlator_service_id, active_list_id, device_key: str
    ):
        """Метод для удаления 1 записи в листе на корреляторе
            Ключ записи преобразуется в url-Like
        Args:
            correlator_service_id (str): id СЕРВИСА отличается от ID ресурса
            active_list_id (str): id листа
        """
        url = f"{self.url}/api/private/services/id/{correlator_service_id}"
        data = None
        if self.version.startswith("2"):
            url += f"/activeLists/del/{active_list_id}?key={urllib.parse.quote(device_key)}"
        elif self.version.startswith("3"):
            url += f"/activeLists/del/{active_list_id}"
            data = {"key": device_key}

        response = self.session.delete(url, json=data)
        if response.status_code != 204:
            return response.text

    def post_activeList_record(
        self, correlator_service_id, activeList_id, device_key: str, records: dict
    ):
        """Метод для создания 1 записи в листе на корреляторе
            Ключ записи преобразуется в url-Like
        Args:
            correlator_service_id (str): id СЕРВИСА отличается от ID ресурса
            activeList_id (str): id листа
            records (dict): Словарь со значениями и их наименованиями который должен быть в куме.]
            set - это значит  создать
        """
        url = self.url + "/api/private/services/id/" + correlator_service_id
        data = []
        for kname, value in records.items():
            data.append({"name": kname, "value": value})
        data = {"set": data}
        if self.version.startswith("2"):
            url += f"/activeLists/create/{activeList_id}?key={urllib.parse.quote(device_key)}"
        elif self.version.startswith("3"):
            url += f"/activeLists/create/{activeList_id}"
            data["key"] = device_key
        response = self.session.post(url, json=data)
        if response.status_code != 204:
            return f"{response.reason} {response.text}"
