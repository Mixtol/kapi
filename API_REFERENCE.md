# Публичный API v3 — KUMA 3.4, 4.0, 4.1 и 4.2

Источники: официальные Swagger [3.4](https://support.kaspersky.com/help/KUMA/RestAPI/3.0/openapi3_0.json), [4.0](https://support.kaspersky.com/help/KUMA/4.0/common/RestAPI/3/kuma-public-openapi.json), [4.2](https://support.kaspersky.com/help/KUMA/4.2/common/RestAPI/3/kuma-public-openapi.json). Контракты получены 2026-11-05. В каждой версии 62 операции, включая устаревший маршрут скачивания ресурса. Тела сложных ресурсов передаются как JSON без изменения схемы.

`RestClient(..., version="3.4")` выбирает контракт KUMA; по умолчанию используется `4.2`. При пропуске `version` или передаче `""` конструктор выдаёт `UserWarning` с выбранной версией. Patch/build отбрасываются: `3.4.1.53` → `3.4`. Неизвестные версии отклоняются до сетевых запросов. Все поддерживаемые версии используют путь `/api/v3`, который не следует путать с версией KUMA.

`client.version` возвращает выбранную версию. `client.get_version()` отдельно читает все страницы списка сервисов и возвращает major.minor узлов Core; версия клиента от этого не меняется. Фильтрация `kind=core` выполняется локально. Нет доступного Core, некорректная версия или разные major.minor узлов — `APIError`; различия patch/build допустимы. Метод может сообщить версию, ещё не поддерживаемую клиентом.

Для `version="4.1"` используется контракт 4.0: `client.version == "4.1"`, `client.contract_version == "4.0"`. Это явно заданная совместимость; отдельный Swagger 4.1 не используется. Все 62 операции 4.1 проверяются по контракту 4.0 локально; проверка на отдельном стенде 4.1 не выполнялась.

## Примеры вызовов

```python
import kuma_api as kapi  # Также поддерживается import kuma

client = kapi.RestClient(
    "https://kuma.example.com", "YOUR_BEARER_TOKEN",
    verify="ca-bundle.pem", version="4.1", timeout=(5, 60),
)
# Выполните нужный вызов из таблицы, затем client.close().
```

Каждая строка таблицы — самостоятельный вызов, а не шаг общего сценария. Замените ID и пути на свои; тела `assets`, `incident`, `resource`, `resource_update`, `task`, `fields` приведены ниже. Методы записи изменяют выбранные объекты. Все вызовы возвращают `(status, result)`; при HTTP 204 результат равен `None`.

`*` у параметра означает обязательность в Swagger. Параметры query передаются через именованные аргументы; `from` — через словарь. В `resources.get` параметру `filterCodeOnly` соответствует `filter_code_only`; в методах с `tenants_ids` список передаётся как `tenantIDs`.

| Метод клиента | HTTP | Маршрут | Query-параметры | Успешные коды | Пример вызова |
|---|---|---|---|---|---|
| `active_lists.lists` | GET | `/activeLists` | `correlatorID`* | 200 | `client.active_lists.lists(correlator_id)` |
| `active_lists.import_data` | POST | `/activeLists/import` | `correlatorID`*, `format`*, `activeListID`, `activeListName`, `keyField`, `clear` | 204 | `client.active_lists.import_data(correlator_id, "csv", csv_data, activeListID=active_list_id, keyField="key", clear=False)` |
| `alerts.search` | GET | `/alerts` | `page`, `id`, `tenantID`, `name`, `timestampField`, `from`, `to`, `status`, `withEvents`, `withAffected` | 200 | `client.alerts.search(tenantID=[tenant_id], status=["new"], page=1)` |
| `alerts.assign` | POST | `/alerts/assign` | — | 204 | `client.alerts.assign([alert_id], user_id)` |
| `alerts.close` | POST | `/alerts/close` | — | 204 | `client.alerts.close(alert_id)` |
| `alerts.comment` | POST | `/alerts/comment` | — | 204 | `client.alerts.comment(alert_id, "Investigating")` |
| `alerts.get` | GET | `/alerts/id/{id}` | — | 200 | `client.alerts.get(alert_id)` |
| `alerts.link_event` | POST | `/alerts/link-event` | — | 204 | `client.alerts.link_event(alert_id, cluster_id, event_id, 1767225600000000000)` |
| `alerts.unlink_event` | POST | `/alerts/unlink-event` | — | 204 | `client.alerts.unlink_event(alert_id, event_id)` |
| `assets.search` | GET | `/assets` | `page`, `id`, `tenantID`, `name`, `fqdn`, `ip`, `mac` | 200 | `client.assets.search(tenantID=[tenant_id], fqdn="host.example.com")` |
| `assets.delete` | POST | `/assets/delete` | — | 200 | `client.assets.delete(assets_ids=[asset_id], tenant_id=tenant_id)` |
| `assets.create` | POST | `/assets/import` | — | 200 | `client.assets.create(assets, tenant_id)` |
| `context_tables.list` | GET | `/contextTables` | `correlatorID`* | 200 | `client.context_tables.list(correlator_id)` |
| `context_tables.export` | GET | `/contextTables/export` | `correlatorID`*, `contextTableID`, `contextTableName`, `format` (4.x) | 200 | `client.context_tables.export(correlator_id, table_id, filepath="context.ndjson")` |
| `context_tables.import_data` | POST | `/contextTables/import` | `correlatorID`*, `format`*, `contextTableID`, `contextTableName`, `clear` | 204 | `client.context_tables.import_data(correlator_id, "csv", csv_data, contextTableID=table_id, clear=False)` |
| `dictionaries.content` | GET | `/dictionaries` | `dictionaryID`* | 200 | `client.dictionaries.content(dictionary_id)` |
| `dictionaries.add_row` | POST | `/dictionaries/add_row` | `dictionaryID`*, `rowKey`*, `overwriteExist`, `needReload` | 200 | `client.dictionaries.add_row(dictionary_id, "alpha", {"value": "beta"})` |
| `dictionaries.delete_row` | POST | `/dictionaries/delete_row` | `dictionaryID`*, `rowKey`*, `needReload` | 200 | `client.dictionaries.delete_row(dictionary_id, "alpha")` |
| `dictionaries.update` | POST | `/dictionaries/update` | `dictionaryID`*, `needReload` | 200 | `client.dictionaries.update(dictionary_id, csv_data)` |
| `resources.download` | GET | `/download/{id}` | — | 200 | `client.resources.download(file_id, filepath="download.bin", chunk_size=1024*1024)` |
| `events.search` | POST | `/events` | — | 200 | `client.events.search(cluster_id, start_time, end_time, "SELECT * FROM events LIMIT 100")` |
| `events.get_clusters` | GET | `/events/clusters` | `page`, `id`, `tenantID`, `name` | 200 | `client.events.get_clusters(tenantID=[tenant_id])` |
| `folders.search` | GET | `/folders/` | `id`, `name`, `limit`, `offset`, `order`, `kind`, `subKind`, `column`, `tenantIDs`* | 200 | `client.folders.search([tenant_id], limit=100, offset=0)` |
| `incidents.search` | GET | `/incidents` | `page`, `id`, `tenantID`, `name`, `from`, `to`, `timestampField`, `status`, `search` | 200 | `client.incidents.search(tenantID=[tenant_id], status="open")` |
| `incidents.assign` | POST | `/incidents/assign` | — | 204 | `client.incidents.assign([incident_id], user_id)` |
| `incidents.close` | POST | `/incidents/close` | — | 204 | `client.incidents.close([incident_id], resolution=1)` |
| `incidents.comment` | POST | `/incidents/comment` | — | 204 | `client.incidents.comment(incident_id, "Investigating")` |
| `incidents.create` | POST | `/incidents/create` | `calcPriority` | 200 | `client.incidents.create(incident, calc_priority=False)` |
| `incidents.get` | GET | `/incidents/id/{id}` | — | 200 | `client.incidents.get(incident_id)` |
| `incidents.link_alert` | POST | `/incidents/link` | — | 204 | `client.incidents.link_alert(incident_id, [alert_id])` |
| `incidents.unlink_alert` | POST | `/incidents/unlink` | — | 204 | `client.incidents.unlink_alert(incident_id, [alert_id])` |
| `reports.search` | GET | `/reports/` | `id`, `name`, `limit`, `offset`, `order`, `tenantIDs`* | 200 | `client.reports.search([tenant_id], limit=100, offset=0)` |
| `resources.search` | GET | `/resources` | `page`, `id`, `tenantID`, `name`, `kind`, `userID` | 200 | `client.resources.search(tenantID=[tenant_id], kind=["filter"])` |
| `resources.download(legacy=True)` | GET | `/resources/download/{id}` | — | 200 | `client.resources.download(file_id, filepath="download-legacy.bin", legacy=True)` |
| `resources.export` | POST | `/resources/export` | — | 200 | `client.resources.export([resource_id], tenant_id, password=password, timeout=(5, 120))` |
| `resources.import_data` | POST | `/resources/import` | — | 204 | `client.resources.import_data(file_id, tenant_id, password=password, actions={resource_id: 1})` |
| `resources.toc` | POST | `/resources/toc` | — | 200 | `client.resources.toc(file_id, password=password)` |
| `resources.upload` | POST | `/resources/upload` | — | 200 | `client.resources.upload(filepath="resources.bin", chunk_size=1024*1024)` |
| `resources.create` | POST | `/resources/{kind}/create` | — | 200 | `client.resources.create("filter", resource)` |
| `resources.validate` | POST | `/resources/{kind}/validate` | — | 204 | `client.resources.validate("filter", resource)` |
| `resources.get` | GET | `/resources/{kind}/{id}` | `filterCodeOnly` | 200 | `client.resources.get("filter", resource_id)` |
| `resources.put` | PUT | `/resources/{kind}/{id}` | — | 200 | `client.resources.put("filter", resource_id, resource_update)` |
| `resources.list_history` | GET | `/resources/{kind}/{id}/history` | `page`, `size`, `sort`, `userLogin` | 200 | `client.resources.list_history("filter", resource_id, page=1, size=100)` |
| `resources.get_history` | GET | `/resources/{kind}/{id}/history/{changeNumber}` | — | 200 | `client.resources.get_history("filter", resource_id, 1)` |
| `resources.revert` | POST | `/resources/{kind}/{id}/history/{changeNumber}` | — | 204 | `client.resources.revert("filter", resource_id, 1)` |
| `services.search` | GET | `/services` | `page`, `id`, `tenantID`, `name`, `fqdn`, `kind`, `paired` | 200 | `client.services.search(tenantID=[tenant_id], kind="correlator")` |
| `services.create` | POST | `/services/create` | — | 200 | `client.services.create(resource_id)` |
| `active_lists.export` | GET | `/services/{id}/activeLists/export/{list}` | — | 200 | `client.active_lists.export(correlator_id, active_list_id, timeout=(5, 120))` |
| `active_lists.scan` | GET | `/services/{id}/activeLists/scan/{list}` | `from`, `exclude`, `pattern`, `limit`, `sort` | 200 | `client.active_lists.scan(correlator_id, active_list_id, limit=100)` |
| `services.reload` | POST | `/services/{id}/reload` | — | 204 | `client.services.reload(service_id)` |
| `services.restart` | POST | `/services/{id}/restart` | — | 202 | `client.services.restart(service_id)` |
| `settings.export_extendedfields` | GET | `/settings/extendedFields/export` | — | 200 | `client.settings.export_extendedfields(timeout=(5, 120))` |
| `settings.import_extendedfields` | POST | `/settings/extendedFields/import` | — | 204 | `client.settings.import_extendedfields(fields)` |
| `settings.view` | GET | `/settings/id/{id}` | — | 200 | `client.settings.view(settings_id)` |
| `system.backup` | GET | `/system/backup` | — | 200 | `client.system.backup(filepath="backup.tar.gz", chunk_size=1024*1024, timeout=(5, 300))` |
| `system.restore` | POST | `/system/restore` | — | 204 | `client.system.restore(filepath="backup.tar.gz", chunk_size=1024*1024, timeout=(5, 300))` |
| `tasks.create` | POST | `/tasks/create` | — | 200 | `client.tasks.create(task)` |
| `tenants.search` | GET | `/tenants` | `page`, `id`, `name`, `main` | 200 | `client.tenants.search(name="Example tenant")` |
| `tenants.create` | POST | `/tenants/create` | — | 200 | `client.tenants.create("Example tenant", 100)` |
| `users.search` | GET | `/users/` | `pattern`, `login`, `email`, `name`, `sort`, `excludeDisabled`, `role`, `tenant`, `page`, `size` | 200 | `client.users.search(size=100, excludeDisabled=True)` |
| `users.get` | GET | `/users/id/{id}` | — | 200 | `client.users.get(user_id)` |
| `users.whoami` | GET | `/users/whoami` | — | 200 | `client.users.whoami()` |

## Передача файлов

Общие параметры файловых методов: `filepath`, `chunk_size`, `timeout`. Скачивание дополнительно принимает `stream`: по умолчанию возвращается `DownloadStream`, `stream=False` явно включает чтение целиком. JSON-ответы экспортирующих операций содержат ID файла, который передаётся в метод скачивания.

С `filepath` скачивание возвращает `(status, path)` и заменяет файл только после успешной записи всех чанков; загрузка читает файл частями. Без пути скачивание возвращает `(status, DownloadStream)`: полностью прочитайте поток или закройте через `with`. `DownloadStream.save(path)` допустим только до чтения первого чанка.

`resources.export`, `active_lists.export`, `context_tables.export` и `settings.export_extendedfields` принимают отдельный `timeout=`: число секунд или `(connect, read)`. Например: `client.resources.export(ids, tenant_id, password=password, timeout=(5, 120))`. `None` использует таймаут клиента; переопределение действует только на этот запрос. Для последующего `download` таймаут задаётся отдельно. Это таймаут подключения/ожидания данных, а не общий предел длительности экспорта.

Для `active_lists.import_data` выберите `activeListID` или `activeListName`, для `context_tables.import_data` — `contextTableID` или `contextTableName`. CSV/TSV активного списка требуют `keyField`. `context_tables.export` принимает `context_table_id` или `context_table_name`. В 3.4 доступен только внутренний формат NDJSON; в 4.0/4.1/4.2 можно выбрать `format="internal"` (по умолчанию), `"csv"` или `"tsv"`. Неподдерживаемый формат для 3.4 отклоняется до запроса.

## Особенности схемы

`resources.export` передаёт пароль как `password` для 3.4 и `newPassword` для 4.0/4.1/4.2. В Python параметр во всех случаях называется `password`. Для `resources.import_data` параметр `actions` — карта ID ресурса в 0 (пропустить), 1 (импортировать), 2 (заменить). В Swagger enum для этих значений размещён на объекте карты; тесты трактуют его согласно описанию значений.

`clear`, `withEvents`, `withAffected`, `paired` и `main` являются флагами наличия. Ложный флаг исключается из query. Фильтры имён в 3.4 используют регулярные выражения без учёта регистра, в 4.0/4.1/4.2 — подстроки. Клиент передаёт выражение без преобразования. Для сортировки отчётов используется `createdAt` в 3.4 и `finishedAt` в 4.0/4.1/4.2. Сложные JSON-схемы ресурсов, задач и ответы остаются в формате выбранной версии сервера; клиент не преобразует их между выпусками.

Дополнительные методы `alerts.searchp`, `alerts.iter_search`, преобразования CSV и привязка правил описаны в [EXTENTIONS.md](EXTENTIONS.md).

`alerts.iter_search()` вызывает `APIError`, если сервер повторяет страницу; записи этой страницы повторно не выдаются.

В `APIError` доступны `details`, `errors`, `params`, `response_data` и `response_text`; параметры из `params` подставляются в текст ошибки. KUMA 3.4 может возвращать `entity`/`errors` вместо `message`/`details`; поддерживаются оба формата. Без `params` сохраняется исходное сообщение.

## Данные для примеров

ID ниже — обозначения соответствующих объектов. `file_id` берётся из результата загрузки или экспорта, `correlator_id` и `service_id` — ID запущенных сервисов, `resource_id` — ID конфигурации ресурса. Для импорта и восстановления нужны существующие архивы KUMA. Пароль архива задаётся приложением.

```python
tenant_id = "TENANT_UUID"
user_id = "USER_UUID"
alert_id = "ALERT_UUID"
event_id = "EVENT_UUID"
incident_id = "INCIDENT_ID"
asset_id = "ASSET_UUID"
correlator_id = "CORRELATOR_SERVICE_UUID"
cluster_id = "STORAGE_CLUSTER_UUID"
active_list_id = "ACTIVE_LIST_RESOURCE_UUID"
table_id = "CONTEXT_TABLE_RESOURCE_UUID"
dictionary_id = "DICTIONARY_RESOURCE_UUID"
resource_id = "RESOURCE_UUID"
file_id = "EXPORTED_OR_UPLOADED_FILE_UUID"
service_id = "SERVICE_UUID"
settings_id = "SETTINGS_UUID"
rule_id = "CORRELATION_RULE_UUID"
password = "ARCHIVE_PASSWORD"
start_time = "2026-01-01T00:00:00Z"
end_time = "2026-01-01T01:00:00Z"
csv_data = "key,value\nalpha,beta\n"

assets = [{"name": "Example host", "fqdn": ["host.example.com"], "ipAddresses": ["192.0.2.10"]}]
incident = {
    "name": "Example incident", "tenantID": tenant_id, "priority": 1,
    "description": "Investigation", "alerts": [{"id": alert_id}],
    "assets": [{"id": asset_id}], "assigneeId": user_id,
}
resource = {
    "name": "Example filter", "kind": "filter", "tenantID": tenant_id,
    "payload": {"code": "DeviceVendor = 'Example'"},
}
resource_update = dict(resource, version="VERSION_FROM_GET")
task = {
    "name": "Example retrospective scan", "kind": "retroscan",
    "tenantIDs": [tenant_id], "correlatorID": correlator_id,
    "search": {
        "kind": "event", "clusterID": cluster_id, "tenantIDs": [tenant_id],
        "period": {"from": start_time, "to": end_time},
        "sql": "SELECT * FROM events ORDER BY Timestamp DESC LIMIT 100",
    },
    "replay": {"id": "", "ruleIDs": {rule_id: True}, "responses": False, "alerts": True},
}
fields = [{"kind": "SA", "name": "ExampleField", "description": "Example field", "disabled": False}]
```

Для обновления ресурса получите его через `resources.get`, измените нужные поля и передайте результат в `resources.put`, сохранив `version` из GET. `VERSION_FROM_GET` выше показывает место этого значения, а не готовую версию. `payload` зависит от `kind`: пример фильтра нельзя использовать как конфигурацию коллектора или хранилища. Схемы сложных ресурсов и задач передаются серверу без преобразования между версиями.
