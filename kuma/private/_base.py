"""Response handling and pagination shared by private API modules."""

import hashlib
import json
from urllib.parse import quote

from kuma.errors import APIError


class PrivateRequests:
    @staticmethod
    def _path(value):
        """Закодировать ID как один сегмент URL, включая '/' и спецсимволы."""
        return quote(str(value), safe="")

    def _send(self, method, endpoint, **kwargs):
        """Отправить запрос и вернуть незакрытый Response без проверки статуса.

        endpoint без ведущего '/' дополняется префиксом /api/private/;
        с '/' используется относительно Core, например /api/whoami.
        kwargs передаются requests, перенаправления по умолчанию запрещены.
        Response закрывает вызывающий метод или владеющий им поток.
        """
        path = endpoint if endpoint.startswith("/") else "/api/private/" + endpoint
        kwargs.setdefault("allow_redirects", False)
        return getattr(self.session, method.lower())(self.url + path, **kwargs)

    @staticmethod
    def _response_result(response, *, strict=False, text=False):
        """Разобрать Response в (status, data) и закрыть его даже при ошибке.

        strict=True превращает не-2xx в APIError с полями исходного ответа.
        Иначе HTTP-ошибка возвращается текстом. text=True всегда возвращает
        текст, включая пустую строку HTTP 204. Без text успешный HTTP 204
        даёт None, остальные успешные ответы разбираются как JSON;
        некорректный JSON вызывает APIError.
        """
        try:
            status = response.status_code
            if strict and not 200 <= status < 300:
                raise APIError.from_response(response)
            if text or not 200 <= status < 300:
                return status, response.text
            if status == 204:
                return status, None
            try:
                return status, response.json()
            except ValueError as exc:
                raise APIError("Invalid JSON response", status) from exc
        finally:
            response.close()

    @classmethod
    def _json_response(cls, response):
        """Разобрать и закрыть ответ; HTTP-ошибка вызывает APIError."""
        return cls._response_result(response, strict=True)

    def _result(self, method, endpoint, *, strict=False, text=False, **kwargs):
        """Отправить запрос через _send() и закрыть его через _response_result().

        strict/text задают правила результата и ошибок; прочие kwargs идут
        в requests. Возвращает (status, data), сетевые ошибки не перехватывает.
        """
        return self._response_result(
            self._send(method, endpoint, **kwargs), strict=strict, text=text
        )

    @staticmethod
    def _rows(data, status=200):
        """Извлечь список объектов из массива либо обёртки {"result": [...]}.

        Пустой result — корректная пустая коллекция. Другой формат или
        не-объекты внутри списка вызывают APIError с переданным status.
        """
        rows = data.get("result") if isinstance(data, dict) else data
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise APIError(
                "Expected a collection of objects from the private API", status
            )
        return rows

    def _iter_rows(self, endpoint, *, params=None, page_size=250, offset=False):
        """Читать коллекцию до пустой страницы с проверкой повторов.

        По умолчанию использует page/size с page=1; offset=True — offset/limit
        с offset=0 и сдвигом на фактическое число записей. Исходные params
        не изменяются. Короткая страница не завершает обход: сервер может
        ограничить size. Отпечатки отсортированных ID выявляют повтор страницы
        до повторной выдачи объектов. В памяти — страница и набор отпечатков.
        Неверный page_size вызывает ValueError, HTTP/формат/повтор — APIError.
        """
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or page_size < 1
        ):
            raise ValueError("page_size must be a positive integer")
        query = dict(params or {})
        cursor = 0 if offset else 1
        seen_pages = set()
        while True:
            query.update({"limit" if offset else "size": page_size})
            query["offset" if offset else "page"] = cursor
            status, data = self._result(
                "GET", endpoint, params=query.copy(), strict=True
            )
            rows = self._rows(data, status)
            if not rows:
                return
            identities = sorted(
                json.dumps(row.get("id", row), sort_keys=True, ensure_ascii=False)
                for row in rows
            )
            fingerprint = hashlib.sha256(json.dumps(identities).encode()).digest()
            if fingerprint in seen_pages:
                raise APIError(
                    "Private API repeated a page; pagination did not advance", status
                )
            seen_pages.add(fingerprint)
            yield from rows
            # Continue to an empty page: a server may cap the requested page size.
            cursor += len(rows) if offset else 1

    def _collect_rows(self, endpoint, **kwargs):
        """Собрать _iter_rows() в список с совместимым возвратом HTTP-ошибок.

        APIError с response_text превращается в эту строку; ошибки формата
        и пагинации без тела ответа остаются исключениями. При HTTP-ошибке
        после нескольких страниц частичный список не возвращается.
        """
        try:
            return list(self._iter_rows(endpoint, **kwargs))
        except APIError as exc:
            if exc.response_text is not None:
                return exc.response_text
            raise
