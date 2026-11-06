# KAPI — клиент KUMA API для Python

[![PyPI](https://img.shields.io/pypi/v/kuma-api?logo=pypi&logoColor=white)](https://pypi.org/project/kuma-api)
[![GitHub](https://img.shields.io/badge/GitHub-repo-181717?logo=github&logoColor=white)](https://github.com/Mixtol/kapi)
![Python Version](https://img.shields.io/badge/python-3.10%2B-green)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Библиотека для публичного REST API и приватного API KUMA. Поддерживаются KUMA 3.4, 4.0, 4.1 и 4.2; для 4.1 используется контракт 4.0.

## Установка

Требуется Python 3.10 или новее.

```bash
pip install kuma-api
```

## Быстрый старт

```python
import kuma_api as kapi  # Также можно import kuma as kapi

with kapi.RestClient(
    url="https://kuma.example.com",
    token="YOUR_BEARER_TOKEN",
    version="4.2",
    verify="ca-bundle.pem",
) as client:
    status, user = client.users.whoami()
    print(user)
```

В `version` укажите версию своего сервера, в `verify` — путь к доверенному CA либо `True` для стандартной проверки TLS. Без `version` публичный клиент выбирает 4.2 и выдаёт предупреждение.

Для приватного API:

```python
from kuma import PrivateClient

with PrivateClient(
    url="https://kuma.example.com",
    username="USER",
    password="PASSWORD",
    version="4.2",
    verify="ca-bundle.pem",
) as private:
    print(private.whoami())
```

## Описание методов

Назначение, параметры и использование описаны в комментариях и docstring методов. Их можно посмотреть в IDE или через `help(client.resources.export)`, `help(PrivateClient.export_content)`.

- [API_REFERENCE.md](API_REFERENCE.md) — методы публичного API и примеры вызовов.
- [EXTENTIONS.md](EXTENTIONS.md) — кастомные методы, построенные на публичном API.

## Официальная документация

- KUMA 3.4: [документация](https://support.kaspersky.ru/kuma/3.4), [Swagger](https://support.kaspersky.com/help/KUMA/3.4/common/RestAPI/3/swagger_dist/dist/index.html).
- KUMA 4.0: [документация](https://support.kaspersky.ru/kuma/4.0), [Swagger](https://support.kaspersky.com/help/KUMA/4.0/common/RestAPI/3/swagger_dist/dist/index.html).
- KUMA 4.2: [документация](https://support.kaspersky.ru/kuma/4.2), [Swagger](https://support.kaspersky.com/help/KUMA/4.2/common/RestAPI/3/swagger_dist/dist/index.html).
