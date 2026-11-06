"""Постраничный обход публичного API по мере запроса данных."""

import hashlib
import json

from kuma.errors import APIError


def iter_pages(search, *, page=1, **filters):
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page должен быть положительным целым числом")
    seen = set()
    while True:
        status, rows = search(page=page, **filters)
        if not isinstance(rows, list) or any(
            not isinstance(row, dict) or not row.get("id") for row in rows
        ):
            raise APIError("Ожидался массив объектов с ID", status)
        if not rows:
            return
        signature = hashlib.sha256(
            json.dumps(sorted(row["id"] for row in rows)).encode()
        ).digest()
        if signature in seen:
            raise APIError("Публичный API вернул повторную страницу", status)
        seen.add(signature)
        yield from rows
        # Некоторые серверы возвращают меньше заявленных 250 строк на страницу.
        page += 1
