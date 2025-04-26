

KumaAPI — это Python-клиент для работы с REST API KUMA (начиная с версии 3.2).\
Он предоставляет универсальный метод для выполнения HTTP-запросов и набор методов для работы со словарями, таблицами, сервисами, тенантами, алертами и событиями.\
Данный репозиторий использутся как централизованный источник методов для проектов взаимодействующих с API Kuma.\
Методы используют публиный RestAPI описанный по https://support.kaspersky.com/help/KUMA/3.4/en-US/217973.htm и/или Private вертки API, которые испольузются в UI системы.

## Установка пакета

`pip install kuma`

## Особенности

- Универсальный метод _make_request для выполнения HTTP-запросов с обработкой JSON, текстовых и бинарных ответов.

# Инициализация клиента

```
from kapi import kapi
kapi = kuma.kapi(
    base_url="https://kuma.example.com",
    token="YOUR_BEARER_TOKEN",
    verify='core.cert'  # (отключение проверки SSL-сертификатов не рекомендуется в продакшене)
)

code, response = kapi.events.get_clusters()
print(code, response)
# Выведет:
# 200, [{'id': 'dc4a6s88-fd81-2gae-120r-0ffe80f2sd98', 'name': 'Test_Stogare', 'tenantID': '2cvvvae3-5573-3c31-vcf9-34d3a3697e66', 'tenantName': 'Main'}]

```
