"""Chunked private exports, imports and active-list downloads."""

import json
from typing import Any, Optional, Union

from requests_toolbelt.multipart.encoder import MultipartEncoder

from kuma._common.transfers import (
    CHUNK_SIZE,
    DownloadStream,
    upload_source,
    validate_chunk_size,
)
from kuma._common.transport import Timeout
from kuma.errors import APIError


class PrivateTransfers:
    def _download_file(self, file_id, *, timeout=None, chunk_size=CHUNK_SIZE):
        """Открыть GET download/{file_id} как DownloadStream без чтения целиком.

        При ошибке ответ закрывается. При успехе владение ответом переходит
        потоку: вызывающий код должен завершить чтение, вызвать close() или
        использовать with. HTTP-ошибка вызывает APIError.
        """
        validate_chunk_size(chunk_size)
        response = self._send(
            "GET",
            f"download/{self._path(file_id)}",
            stream=True,
            timeout=timeout,
            allow_redirects=False,
        )
        try:
            if not 200 <= response.status_code < 300:
                raise APIError.from_response(response)
            return DownloadStream(response, chunk_size)
        except BaseException:
            response.close()
            raise

    def export_content(
        self,
        ids: list,
        tenant_id: str,
        password: Optional[str] = None,
        file_path: str = "exported_content",
        *,
        timeout: Optional[Timeout] = None,
        chunk_size: int = CHUNK_SIZE,
    ):
        """Экспортировать ресурсы и сохранить зашифрованный архив чанками.

        Args:
            ids: Список ID конфигураций ресурсов для export/resources.
            tenant_id: ID тенанта экспортируемых ресурсов.
            password: Пароль архива. При None/пустой строке для совместимости
                используется пароль учётной записи клиента; можно задать иной.
            file_path: Путь назначения, по умолчанию 'exported_content';
                родительский каталог должен существовать.
            timeout: Секунды либо (connect, read); применяется отдельно к
                запросам экспорта и скачивания. None использует настройку клиента.
            chunk_size: Положительный размер чанка в байтах; по умолчанию 64 КиБ.

        KUMA 4.x получает пароль в newPassword, KUMA 2/3 — в password. После
        получения fileID скачивает download/{fileID} во временный файл рядом
        с назначением, затем заменяет целевой файл. При сбое прежний файл
        сохраняется. Возвращает HTTP-статус скачивания, не путь и не кортеж.

        HTTP-ошибка/отсутствие fileID вызывает APIError. Ошибки чтения потока
        и записи файла также оборачиваются в APIError; исходная ошибка, если
        она есть, доступна через __cause__. Сбой HTTP-запроса до получения
        потока передаётся как исключение requests. Соединения закрываются.
        timeout не ограничивает общую продолжительность всего экспорта.

        Example:
            status = client.export_content(
                [resource_id], tenant_id, password=archive_password,
                file_path='resources.bin', timeout=(5, 120), chunk_size=1024 * 1024,
            )
        """
        if not password:
            password = self.password
        validate_chunk_size(chunk_size)
        try:
            password_field = "newPassword" if self._major_version >= 4 else "password"
            payload = {"ids": ids, password_field: password, "tenantID": tenant_id}
            status, exported = self._json_response(
                self._send(
                    "POST",
                    "export/resources",
                    json=payload,
                    timeout=timeout,
                )
            )
            if not isinstance(exported, dict) or not exported.get("fileID"):
                raise APIError("Resource export did not return a file ID", status)
            with self._download_file(
                exported["fileID"],
                timeout=timeout,
                chunk_size=chunk_size,
            ) as download:
                download.save(file_path)
                return download.status_code
        except Exception as exception:
            self.logger.error(f"Error occurred when exporting content: {exception}")
            raise

    def import_content(
        self,
        file_path: str,
        tenant_id: str,
        password=None,
        action=2,
        *,
        timeout: Optional[Timeout] = None,
        chunk_size: int = CHUNK_SIZE,
    ):
        """Загрузить архив чанками, прочитать его состав и импортировать ресурсы.

        Args:
            file_path: Путь существующего архива экспорта KUMA.
            tenant_id: ID целевого тенанта.
            password: Пароль архива; None/пустая строка использует пароль
                учётной записи клиента для совместимости.
            action: Одно действие для всех ресурсов архива: 0 — пропустить,
                1 — импортировать, 2 — заменить (значение по умолчанию).
            timeout: Секунды либо (connect, read) для каждого из трёх запросов;
                None использует таймаут клиента, не общий срок операции.
            chunk_size: Положительный размер читаемого чанка в байтах, 64 КиБ
                по умолчанию. Файл не загружается целиком в память.

        Последовательность: POST upload (multipart), POST import/toc,
        POST import/resources с картой ID в action. Даже action=0 выполняет
        загрузку и запрос импорта. Возвращает HTTP-статус последнего запроса.
        Состав архива и карта действий хранятся в памяти. Ответы закрываются.

        Неверный action вызывает ValueError до запросов. HTTP-ошибки,
        отсутствие ID загруженного файла или resources в составе — APIError.
        Ошибки файловой системы и requests передаются без замены. Операция
        не даёт гарантии атомарности импорта на сервере.
        """
        if (
            isinstance(action, bool)
            or not isinstance(action, int)
            or action not in (0, 1, 2)
        ):
            raise ValueError("Import action must be 0=skip, 1=create or 2=replace")
        if not password:
            password = self.password
        try:
            with upload_source(filepath=file_path, chunk_size=chunk_size) as source:
                body = MultipartEncoder(
                    {"file": ("resources.bin", source, "application/octet-stream")}
                )
                status, uploaded = self._json_response(
                    self._send(
                        "POST",
                        "upload",
                        data=body,
                        headers={"Content-Type": body.content_type},
                        timeout=timeout,
                    )
                )
            if not isinstance(uploaded, dict) or not uploaded.get("id"):
                raise APIError("Resource upload did not return a file ID", status)
            file_id = uploaded["id"]
            data = {"fileID": file_id, "password": password}
            status, toc = self._json_response(
                self._send(
                    "POST",
                    "import/toc",
                    json=data,
                    timeout=timeout,
                )
            )
            if not isinstance(toc, dict) or not isinstance(toc.get("resources"), list):
                raise APIError("Resource import TOC did not return resources", status)
            actions = {resource["id"]: action for resource in toc["resources"]}
            data = {
                "actions": actions,
                "fileID": file_id,
                "password": password,
                "tenantID": tenant_id,
            }
            response = self._send(
                "POST",
                "import/resources",
                json=data,
                timeout=timeout,
            )
            try:
                if not 200 <= response.status_code < 300:
                    raise APIError.from_response(response)
                return response.status_code
            finally:
                response.close()
        except Exception as exception:
            self.logger.error(f"Error occurred when importing content: {exception}")
            raise

    def get_active_list_content(
        self,
        correlator_service_id: str,
        active_list_id: str,
        *,
        filepath=None,
        stream=True,
        timeout=None,
        chunk_size=CHUNK_SIZE,
    ) -> Union[str, Any]:
        """Экспортировать активный список сервиса и получить его содержимое.

        Args:
            correlator_service_id: ID запущенного сервиса коррелятора.
            active_list_id: ID ресурса активного списка.
            filepath: Путь сохранения; если задан, имеет приоритет над stream.
            stream: True — вернуть DownloadStream без сборки в памяти;
                False — прочитать целиком и разобрать JSON или строки NDJSON.
            timeout: Секунды либо (connect, read) для экспорта и скачивания;
                None использует настройку клиента.
            chunk_size: Положительное число байт в чанке, по умолчанию 64 КиБ.

        Returns:
            При filepath — строка пути после сохранения файла;
            при stream=True — DownloadStream, которым владеет вызывающий код;
            при stream=False — разобранный JSON либо список объектов NDJSON.
            Метод не возвращает кортеж (status, data).

        При записи файл заменяется только после успешного скачивания;
        родительский каталог должен существовать. Ошибки потока и записи
        оборачиваются в APIError с исходной ошибкой в __cause__, если она есть.
        HTTP-ошибки и отсутствие ID экспорта вызывают APIError, некорректное
        содержимое при stream=False — ошибку разбора JSON. При потоковом
        чтении используйте with, особенно если можете прервать обход.

        Example:
            with client.get_active_list_content(service_id, list_id) as chunks:
                for chunk in chunks:
                    output.write(chunk)
        """
        validate_chunk_size(chunk_size)
        endpoint = f"services/id/{self._path(correlator_service_id)}/activeLists/export/{self._path(active_list_id)}"
        status, exported = self._result("GET", endpoint, timeout=timeout, strict=True)
        if not isinstance(exported, dict) or not exported.get("id"):
            raise APIError("Active list export did not return a file ID", status)
        download = self._download_file(
            exported["id"], timeout=timeout, chunk_size=chunk_size
        )
        if filepath is not None:
            return download.save(filepath)
        if stream:
            return download
        with download:
            data = b"".join(download)
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return [json.loads(line) for line in data.splitlines() if line.strip()]
