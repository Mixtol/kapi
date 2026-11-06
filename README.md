# KAPI - KUMA API Python Client

[![PyPI](https://img.shields.io/pypi/v/kuma-api?logo=pypi&logoColor=white)](https://pypi.org/project/kuma-api)
[![GitHub](https://img.shields.io/badge/GitHub-repo-181717?logo=github&logoColor=white)](https://github.com/Mixtol/kapi)
![Python Version](https://img.shields.io/badge/python-3.10%2B-green)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Описание

KUMA API Python Client — это библиотека для взаимодействия с SIEM KUMA, предоставляющая удобный интерфейс как для публичного REST API, так и для приватных API-методов, используемых в веб-интерфейсе системы.

**Особенности:**

- Поддержка как стабильного публичного API (документированного), так и приватных методов;
- Minor&Major индексы версии идентичны официальным веткам методов;
- Унифицированный интерфейс для работы со всеми сущностями KUMA (алерты, события, тенанты и др.);
- Автоматическая обработка ответов (JSON, текст, бинарные данные);
- Поддержка аутентификации через Bearer Token.

## Установка

Требуется Python 3.10 или новее.

```bash
pip install kuma-api
```

Версия пакета `4.2.0` поддерживает выбор KUMA `3.4`, `4.0`, `4.1` и `4.2` через `version=`; версия пакета не переключает версию уже настроенного клиента. Для `4.1` используется контракт `4.0`.

Поддерживаются оба импорта: `import kuma` и `import kuma_api as kapi`. Во втором случае доступны те же `kapi.RestClient`, `kapi.PrivateClient`, `kapi.APIError`, `kapi.DownloadStream`; классы и настройки логирования общие.

## Quickstart Инициализация клиента

### Для работы с публичным REST API

```python
import kuma

# Инициализация клиента с публичным API
client = kuma.RestClient(
    url="https://kuma.example.com",
    token="YOUR_BEARER_TOKEN",
    verify='ca-bundle.pem',  # Цепочка доверенных CA; имя в URL должно совпадать с SAN сертификата
    version="3.4"
)
code, response = client.users.whoami()
print(client.version)       # Выбранная версия: "3.4"
print(client.get_version()) # Версия Core на сервере, например "3.4"
```

`version` задаёт версию KUMA: поддерживаются `3.4`, `4.0`, `4.1`, `4.2`; по умолчанию используется последняя поддерживаемая — `4.2`. Если `version` не передана или равна `""`, при создании клиента выдаётся `UserWarning` с выбранной версией. Учитываются только major.minor: `3.4.1.53` приводится к `3.4`. При `version="4.1"` свойство `client.version` равно `"4.1"`, а `client.contract_version` — `"4.0"`. Сохранён позиционный порядок `RestClient(url, token, verify, timeout, logger, version)`. `get_version()` получает версию Core через публичный API и не меняет выбранную версию клиента. Если Core недоступен в списке сервисов или его узлы сообщают разные major.minor, метод вызывает `APIError`.

Логирование настраивает приложение через стандартный `logging.basicConfig()` или собственные обработчики. Импорты библиотеки не меняют root-логгер и уровни `requests`/`urllib3`; логи `kuma.*` наследуют настройки приложения. В `RestClient` также можно передать свой `logger=`. Добавлять `force=True` из-за KAPI не требуется.

### Для работы с приватным API (только для внутреннего использования)

```python
import kuma

# Инициализация клиента с приватным API
client = kuma.PrivateClient(
    url="https://kuma.example.com",
    username="USER",
    password="PASSWORD",
    version="3.4",
    verify="ca-bundle.pem",
    timeout=(5, 30)
)
response = client.whoami()
```

**Важно:** Приватный API может изменяться между версиями KUMA и поддерживает подключение только с одного разрешенного хоста.

`PrivateClient(url, username, password, session_data=None, version="3.4", logger=logger)` сохраняет выбранную версию после логина и использует переданный логгер для сообщений этого экземпляра. Для обратной совместимости его версия по умолчанию остаётся `2.1.0`. Учтены ветки 2.x/3.x и формат коллекций `{"result": [...]}` для 4.2; для 4.0/4.1/4.2 используются современные маршруты. Для 4.1 `client.contract_version` равна `"4.0"`, выбранная версия сохраняется в данных сессии. На живых стендах 3.4 и 4.2 проверены чтение, сессии, пагинация и файловые операции; 4.0 и 4.1 проверены локальными тестами. `get_version()` читает версию Core и не меняет настройку клиента.

У приватного клиента TLS проверяется по умолчанию; `verify` принимает `True`, `False` или путь к CA. `timeout` задаёт конечный таймаут всех запросов (по умолчанию 30 секунд), также допустима пара `(connect, read)`. `create_session(..., cert=ca, version="3.4")` использует `cert` как CA и выполняет один логин; при восстановлении сохранённой сессии повторного логина нет. Клиент поддерживает `with` и `close()` для закрытия соединений; завершение серверной сессии выполняется через `logout()`.

`PrivateClient` включает настройки алертов, поиск правил по имени, массовую и одиночную привязку правил, поиск Shared и сервисов. Исторические имена `get_service_id_by_resouce_id` и `get_services_id_by_resouce_id` сохранены как алиасы. `validate_session=True` при создании клиента проверяет сохранённую сессию и повторяет вход только после HTTP 401/403; ошибки сети и CA не запускают повторную авторизацию. Аргументы, форматы результатов, ошибки и различия версий описаны в строках документации методов: например, `help(kuma.PrivateClient.export_content)`.

`export_content(..., file_path=path, timeout=120, chunk_size=1024*1024)` скачивает архив чанками и возвращает статус. `import_content(..., timeout=120, chunk_size=1024*1024)` отправляет файл частями. `get_active_list_content(..., filepath=path)` возвращает путь, без `filepath` — `DownloadStream`; `stream=False` явно собирает JSON/NDJSON в памяти. Ошибки HTTP, чтения потока и записи скачиваемого файла вызывают `APIError`; сбои сетевого запроса до получения потока передаются как исключения `requests`. Существующий файл сохраняется при неудачном скачивании.

## Примеры использования REST

Вызовы всех 62 операций Swagger и примеры JSON для активов, инцидентов, ресурсов, задач и расширенных полей собраны в [API_REFERENCE.md](API_REFERENCE.md).

### Расширенные функции

Помимо стандартных REST-методов в клиенте есть ряд более комплексных методов, которые используют дополнительную логику или сразу несколько публичных методов, например преобразование Активного листа в Словарь и наоборот. Подробное описание и примеры функций — в [EXTENTIONS.md](EXTENTIONS.md).

Через публичный API доступны поиск корреляторов по правилу, CSV-отчёт с группировкой на диске, пакетный перенос ресурсов с резервированием конфликтов, синхронизация правил с эталоном и массовая привязка правил. Массовое изменение настроек алертинга использует приватный API. Необязательный `kuma-api[session-cache]` добавляет зашифрованный кеш приватной сессии. Контракты и проверки на стендах — в [EXTENTIONS.md](EXTENTIONS.md).

### Работа с алертами

#### Поиск
```python
# Поиск алертов по фильтру
status, alerts = client.alerts.search(**{
    "status": "new",
    "from": "2023-01-01T00:00:00Z",
    "to": "2023-01-31T23:59:59Z",
    "tenantID": "tenant-123",
})
if status == 200:
    for alert in alerts:
        print(f"Found alert: {alert['id']}")

# Поиск с пагинацией (автоматическая загрузка всех страниц)
status, all_alerts = client.alerts.searchp(limit=500, status="assigned")
if status == 200:
    print(f"Total alerts found: {len(all_alerts)}")
```

#### Управление алертами
```python
# Назначение алерта на пользователя
assign_status, _ = client.alerts.assign(
    alerts_ids=["123e4567-e89b-12d3-a456-426614174000"],
    user_id="user-123"
)
if assign_status == 204:
    print("Alert assigned successfully")

# Закрытие алерта с указанием причины
close_status, _ = client.alerts.close(
    alert_id="123e4567-e89b-12d3-a456-426614174000",
    reason="responded"
)
if close_status == 204:
    print("Alert closed")

# Добавление комментария к алерту
comment_status, _ = client.alerts.comment(
    alert_id="123e4567-e89b-12d3-a456-426614174000",
    comment="False positive, ignoring"
)
if comment_status == 200:
    print("Comment added")
```

#### Работа с связанными событиями
```python
# Связывание события с алертом
link_status, _ = client.alerts.link_event(
    alert_id="alert-123",
    cluster_id="cluster-456",
    event_id="event-789",
    event_timestamp=1672531200,
    comment="Related event found"
)
if link_status == 200:
    print("Event linked")

# Отвязывание события от алерта
unlink_status, _ = client.alerts.unlink_event(
    alert_id="alert-123",
    event_id="event-789"
)
if unlink_status == 200:
    print("Event unlinked")

```

#### Обработка ошибок
```python
from kuma import APIError

try:
    status, response = client.alerts.get("invalid-id")
except APIError as error:
    print(error.status_code, error)
    print(error.details, error.params)
```


## Файлы и совместимость обновления

```python
# Архив записывается чанками по 1 МиБ без накопления целиком в памяти.
status, path = client.system.backup(filepath="backup.tar.gz", chunk_size=1024 * 1024)
```

Файловые методы с `filepath` возвращают `(status, path)` и заменяют целевой файл только после успешного скачивания. Без пути возвращается `(status, DownloadStream)`; итератор нужно полностью прочитать или закрыть через `with`. Для прежнего результата целиком в памяти передайте `stream=False`. Загрузка файлов также поддерживает `filepath` и читает файл частями.

`DownloadStream.save(path)` вызывается до чтения первого чанка. Сохранение частично прочитанного или закрытого потока отклоняется, существующий файл не меняется. `alerts.iter_search()` прекращает обход с `APIError`, если сервер повторяет страницу; повторные записи этой страницы не выдаются.

TLS проверяется по умолчанию; `verify` принимает `True`, `False` или путь к цепочке CA. Пароль экспорта, импорта и просмотра архива теперь передаётся явно. Привязка и отвязка правил возвращают `(status, resource)` также при отсутствии изменений. Проверки дат, таймаутов и CSV стали строже: даты должны содержать часовой пояс, ключи CSV — быть непустыми и уникальными.

В `APIError` доступны `details`, `errors`, `params`, `response_data` и `response_text`; присланные сервером параметры ошибки подставляются в текст сообщения. Перечень методов публичного API и параметры — в [API_REFERENCE.md](API_REFERENCE.md).

## Документация API

### Ограниченный поиск содержимого ресурсов

`client.resources.find_content(kind=..., tenant_ids=[...], query="powershell")` возвращает `(200, result)` с найденными корневыми ресурсами, путями/фрагментами совпадений, `complete`, `scan_exhausted`, накопительными `checked`/`unreadable` и `state` для следующей порции с теми же условиями. HTTP 200 здесь означает результат workflow; полноту и ошибки чтения проверяют отдельно. Тип и непустой список UUID тенантов обязательны. Параметры: `ids`, `paths` (поддеревья JSON Pointer с `*` на один сегмент), `conditions` (`path`, `op=contains|equals|exists`, `value`), `condition_mode=all|any`, `include_references=False`, `reference_depth=1` (до 2), `limit=10`, `max_queries=12` (до 20), `deadline=15`, `min_interval=1.0` секунды.

Поиск буквальный, без регистра, по ключам и значениям JSON до сокращения представления; секретные поля исключены. `resources.get(filter_code_only=True)` возвращает код фильтров вместо AST. Значения словарей ищутся независимо от количества строк. При включённых ссылках до 8 уникальных ресурсов на root; встроенные конфигурации не загружаются повторно. Root ограничен tenant_ids; ссылки могут принадлежать другим доступным токену тенантам. Условия проверяются в одном JSON, wildcard-условия могут совпасть в разных элементах массива. Достаточно первого доказательства совпадения root, примеров не больше трёх. Путь может иметь path_truncated=true. Глубина JSON до 64 и до 100000 узлов; превышение явно делает результат неполным.

SDK не делает retry и параллельных запросов. Между запросами одной порции минимум секунда; deadline запрещает новые запросы после бюджета, но уже отправленный HTTP ограничен timeout клиента. Общий лимит между клиентами, размер входящего HTTP и защита state принадлежат приложению. `state` не содержит содержимого ресурсов, но не подписан: не принимайте его от недоверенного клиента напрямую. Для async-адаптера доступен `kuma.rest.content_search.content_search_plan`: выдаёт вызовы публичного SDK, принимает ответы через send или безопасные SearchError через throw. MCP использует этот план с общими rate/concurrency, лимитами байтов и подписанным курсором, привязанным к токену.

Официальная документация по публичному API: [KUMA 3.4](https://support.kaspersky.com/help/KUMA/3.4/common/RestAPI/3/swagger_dist/dist/index.html), [KUMA 4.0](https://support.kaspersky.com/help/KUMA/4.0/common/RestAPI/3/swagger_dist/dist/index.html), [KUMA 4.2](https://support.kaspersky.com/help/KUMA/4.2/common/RestAPI/3/swagger_dist/dist/index.html).

**Примечание:** Приватные API-методы не задокументированы и могут изменяться вендором без предупреждения между версиями системы.
