# KAPI - KUMA API Python Client

## Описание

KUMA API Python Client — это библиотека для взаимодействия с SIEM KUMA, предоставляющая удобный интерфейс как для публичного REST API, так и для приватных API-методов, используемых в веб-интерфейсе системы.

**Особенности:**
- Поддержка как стабильного публичного API (документированного), так и приватных методов;
- Minor&Major индексы версии идентичны официальным веткам методов;
- Унифицированный интерфейс для работы со всеми сущностями KUMA (алерты, события, тенанты и др.);
- Автоматическая обработка ответов (JSON, текст, бинарные данные);
- Поддержка аутентификации через Bearer Token.

## Установка

```bash
pip install kuma-api
```

## Инициализация клиента

### Для работы с публичным REST API

```python
import kuma

# Инициализация клиента с публичным API
client = kuma.RestClient(
    base_url="https://kuma.example.com",
    token="YOUR_BEARER_TOKEN",
    verify='core.cert'  # Путь к SSL-сертификату (рекомендуется для продакшена)
)
```

### Для работы с приватным API (только для внутреннего использования)

```python

# Инициализация клиента с приватным API
client = kuma.PrivateClient(
    url="https://kuma.example.com",
    login="USER",
    password="PASSWORD"
)
```

**Важно:** Приватный API может изменяться между версиями KUMA и поддерживает подключение только с одного разрешенного хоста.

## Примеры использования REST

### Работа с алертами

#### Поиск
```python
# Поиск алертов по фильтру
status, alerts = client.alerts.search(
    status="new",
    from="2023-01-01T00:00:00Z",
    to="2023-01-31T23:59:59Z",
    tenantID="tenant-123"
)
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
if assign_status == 200:
    print("Alert assigned successfully")

# Закрытие алерта с указанием причины
close_status, _ = client.alerts.close(
    alert_id="123e4567-e89b-12d3-a456-426614174000",
    reason="responded"
)
if close_status == 200:
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
status, response = client.alerts.get("invalid-id")
if status != 200:
    print(f"Error {status}: {response}")
    # Для 404: "Alert not found"
    # Для 403: "Access denied"
```


## Документация API

Официальная документация по публичному API доступна по адресу:
https://support.kaspersky.com/help/KUMA/3.4/en-US/217973.htm

**Примечание:** Приватные API-методы не документированы и могут изменяться вендором без предупреждения между версиями системы.
