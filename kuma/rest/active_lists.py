import csv
import json
import sqlite3
import tempfile
from collections.abc import Mapping
from contextlib import closing
from io import StringIO
from pathlib import Path
from typing import Optional

from kuma._common.transfers import CHUNK_SIZE
from kuma.errors import APIError
from kuma.rest._base import APIResult, KumaRestAPIModule, Timeout


class KumaRestAPIActiveLists(KumaRestAPIModule):
    """Methods for Active Lists."""

    def lists(self, correlator_id: str) -> APIResult:
        """
        Gets current active lists on correlator.
        Args:
            correlatorID* (str): Service ID
        """
        return self._make_request(
            "GET", "activeLists", params={"correlatorID": correlator_id}
        )

    def import_data(
        self,
        correlator_id: str,
        format: str,
        data=None,
        *,
        filepath=None,
        timeout=None,
        chunk_size=CHUNK_SIZE,
        **kwargs,
    ):
        """Stream CSV, TSV, or internal NDJSON; select an active list by ID or name."""
        if format not in ("csv", "tsv", "internal"):
            raise ValueError("format must be csv, tsv, or internal")
        if bool(kwargs.get("activeListID")) == bool(kwargs.get("activeListName")):
            raise ValueError("Specify exactly one activeListID or activeListName")
        if format in ("csv", "tsv") and not kwargs.get("keyField"):
            raise ValueError("keyField is required for CSV and TSV")
        return self._upload(
            "activeLists/import",
            data,
            filepath=filepath,
            params={"correlatorID": correlator_id, "format": format, **kwargs},
            content_type=format,
            timeout=timeout,
            chunk_size=chunk_size,
        )

    def download(
        self,
        file_id: str,
        filepath=None,
        *,
        stream=True,
        timeout=None,
        chunk_size=CHUNK_SIZE,
    ):
        """Download an exported active list to a file or a managed chunk iterator."""
        return self._download(
            f"download/{self._path(file_id)}",
            filepath,
            stream=stream,
            timeout=timeout,
            chunk_size=chunk_size,
        )

    def export(
        self,
        correlator_id: str,
        active_list_id: str,
        *,
        timeout: Optional[Timeout] = None,
    ) -> APIResult:
        """
        Generating AL file ID for download file method.
        Args:
            correlator_id* (str): Service ID
            active_list_id* (str): Active list resource ID
            timeout: Seconds or (connect, read) seconds; None uses the client timeout
        """
        return self._make_request(
            "GET",
            f"services/{self._path(correlator_id)}/activeLists/export/{self._path(active_list_id)}",
            headers={"Accept": "application/json"},
            timeout=timeout,
        )

    def scan(self, correlator_id: str, active_list_id: str, **kwargs) -> APIResult:
        """
        Scan active list records with timestamp or substring filters.
        Args:
            correlator_id* (str): Service ID
            active_list_id* (str): Active list resource ID
            from (str): Epoch in nanoseconds
            exclude (str): Epoch in nanoseconds
            pattern (str): Key search string filter
            limit (str): Maximum number of returned records
            sort (str): For ASC <columnname> or add '-columnname' for DESC
        """
        return self._make_request(
            "GET",
            f"services/{self._path(correlator_id)}/activeLists/scan/{self._path(active_list_id)}",
            params=kwargs,
        )

    @staticmethod
    def _cell(value):
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _row_error(values, max_cell_len, ascii_only):
        if not values[0]:
            return "Пустой ключ"
        for column, value in enumerate(values, 1):
            if len(value) > max_cell_len:
                return f"Столбец {column}: длина {len(value)}, максимум {max_cell_len}"
            if ascii_only and not value.isascii():
                return f"Столбец {column}: символы вне ASCII"
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                return f"Столбец {column}: некорректный Unicode"
        return None

    @staticmethod
    def _read_records(source):
        for line_number, line in enumerate(source, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Некорректный JSONL в строке {line_number}"
                    ) from error

    def _write_existing(
        self, reader, writer, headers, seen, max_cell_len, ascii_only, clean_existing
    ):
        dropped = 0
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                error = "Неверное число столбцов"
            else:
                values = [row[h] for h in headers]
                error = self._row_error(values, max_cell_len, ascii_only)
                if not error and values[0] in seen:
                    error = "Повторный ключ"
            if error:
                if not clean_existing:
                    raise ValueError(
                        f"Словарь, строка {reader.line_num}: {error}. "
                        "Для удаления некорректных строк задайте clean_existing=True"
                    )
                dropped += 1
                continue
            seen.add(values[0])
            writer.writerow(values)
        return dropped

    def _write_records(
        self,
        writer,
        al_key,
        records,
        headers,
        seen,
        *,
        max_cell_len=1024,
        ascii_only=False,
        invalid_rows="raise",
        stats=None,
        columns=None,
    ):
        if stats is None:
            stats = {"added": 0, "skipped": 0, "duplicates": 0}
        fields = [(columns or {}).get(header, header) for header in headers[1:]]
        count = 0
        for row in records:
            count += 1
            record = row.get("record") if isinstance(row, dict) else None
            if not isinstance(record, dict):
                error = "Запись и её поле record должны быть объектами"
            else:
                source = row if al_key == "key" else record
                if al_key not in source:
                    error = "Отсутствует поле ключа"
                else:
                    key = self._cell(source[al_key])
                    if key in seen:
                        stats["duplicates"] += 1
                        continue
                    values = [key] + [self._cell(record.get(field)) for field in fields]
                    error = self._row_error(values, max_cell_len, ascii_only)
            if error:
                if invalid_rows == "raise":
                    raise ValueError(f"Активный список, запись {count}: {error}")
                stats["skipped"] += 1
                continue
            writer.writerow(values)
            seen.add(key)
            stats["added"] += 1
        return count

    def _get_data_with_column(self, al_key, al_content, dict_headers, dict_unique_keys):
        output = StringIO(newline="")
        self._write_records(
            csv.writer(output, lineterminator="\n"),
            al_key,
            al_content,
            dict_headers,
            dict_unique_keys,
        )
        return output.getvalue()

    @staticmethod
    def _merge_updates(existing, incoming, target, database, stats):
        # Keep row contents on disk; only the current pair of rows is decoded.
        with closing(sqlite3.connect(database)) as db:
            db.executescript(
                "PRAGMA cache_size=-8192; PRAGMA temp_store=FILE;"
                "CREATE TABLE incoming (seq INTEGER PRIMARY KEY, key TEXT UNIQUE, cells TEXT)"
            )
            with incoming.open(encoding="utf-8", newline="") as source:
                db.executemany(
                    "INSERT INTO incoming (key, cells) VALUES (?, ?)",
                    (
                        (row[0], json.dumps(row, ensure_ascii=False))
                        for row in csv.reader(source)
                    ),
                )
            with (
                existing.open(encoding="utf-8", newline="") as source,
                target.open("w", encoding="utf-8", newline="") as output,
            ):
                reader = csv.reader(source)
                writer = csv.writer(output, lineterminator="\n")
                writer.writerow(next(reader))
                for row in reader:
                    match = db.execute(
                        "SELECT cells FROM incoming WHERE key = ?", (row[0],)
                    ).fetchone()
                    if match is not None:
                        replacement = json.loads(match[0])
                        stats["added"] -= 1
                        stats["replaced" if replacement != row else "duplicates"] += 1
                        db.execute("DELETE FROM incoming WHERE key = ?", (row[0],))
                        row = replacement
                    writer.writerow(row)
                for (cells,) in db.execute("SELECT cells FROM incoming ORDER BY seq"):
                    writer.writerow(json.loads(cells))

    def _clear_dictionary(
        self, dictionary_id, original, need_reload, *, dry_run=False, timeout=None
    ):
        # KUMA rejects header-only CSV; an empty rows array in resources.put
        # leaves the table unchanged on both 3.4 and 4.2.
        result = 200, {"message": "Dictionary is empty", "updated": False}
        with original.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            next(reader)
            keys = dict.fromkeys(row[0] for row in reader if row)
        if "" in keys:
            raise ValueError("Нельзя удалить строку с пустым ключом через delete_row")
        if not dry_run:
            request_options = {} if timeout is None else {"timeout": timeout}
            for key in keys:
                result = self._base.dictionaries.delete_row(
                    dictionary_id, key, need_reload=need_reload, **request_options
                )
        return result, bool(keys)

    def to_dictionary(
        self,
        correlator_id: str,
        active_list_id: str,
        dictionary_id: str,
        active_list_key: str = "key",
        need_reload: int = 0,
        clear: bool = False,
        *,
        max_cell_len: int = 1024,
        ascii_only: bool = False,
        clean_existing: bool = False,
        invalid_rows: str = "raise",
        return_report: bool = False,
        on_conflict: str = "keep",
        columns: Optional[Mapping[str, str]] = None,
        dry_run: bool = False,
        timeout: Optional[Timeout] = None,
    ):
        """Перенести записи активного списка в словарь через временные файлы.

        Args:
            correlator_id: ID сервиса коррелятора.
            active_list_id: ID ресурса активного списка.
            dictionary_id: ID целевого словаря типа table.
            active_list_key: key — ключ записи AL, иначе поле внутри record.
            need_reload: Флаг обновления сервисов для dictionaries.update.
            clear: Заменить содержимое словаря, иначе сохранить прежние ключи.
            max_cell_len: Максимум символов Unicode в ячейке. По умолчанию 1024,
                проверено для таблиц KUMA 3.4 и 4.2; можно задать меньший лимит.
            ascii_only: Отклонять не-ASCII ячейки; не исправляет кодировку текста.
            clean_existing: Удалять некорректные и повторные существующие строки.
                По умолчанию ошибка такой строки прекращает операцию до записи.
            invalid_rows: raise — ошибка новой записи прекращает операцию;
                skip — пропустить запись и увеличить skipped в отчёте.
            return_report: Вернуть статистику вместе с исходным ответом сервера.
            on_conflict: keep — сохранить существующую строку; update — заменить
                её целиком из AL. При повторах в AL берётся первая корректная запись.
            columns: {столбец словаря: поле record}, например {"value": "login"}.
                Остальные столбцы читаются по имени; отсутствующее поле даёт "".
                Ключ задаётся отдельно через active_list_key.
            dry_run: Проверить и вернуть отчёт без изменения словаря; счётчики
                показывают план, updated=False, would_update — нужны ли изменения.
            timeout: Секунды или (connect, read) для каждого запроса операции,
                включая удаление строк; None использует таймаут клиента.

        Returns:
            По умолчанию (status, response), как у dictionaries.update.
            При return_report=True: (status, {response, updated, added, skipped,
            dropped, duplicates, replaced}). dropped считает удалённые строки;
            duplicates — новые записи с уже сохранённым ключом. added — записи,
            добавленные из AL; replaced — изменённые существующие строки.
            dry_run=True всегда возвращает отчёт с dry_run=True и response=None.
            Если изменений нет, updated=False, POST не нужен.

        Ключ обязателен; пустые остальные ячейки разрешены. None превращается
        в пустую строку, 0 и False сохраняются. Пустые строки JSONL игнорируются.
        Синтаксические ошибки читаемых JSON/CSV прерывают операцию даже в skip.
        В режиме keep существующие значения имеют приоритет. В режиме skip вместе
        с clear непустой AL без единой корректной записи не очищает словарь:
        вызывается ValueError. Пустой AL с clear=True очищает его явно.
        clean_existing=True работает и при пустом AL. Содержимое исходных ячеек
        не включается в сообщения валидации. HTTP-ошибки передаются без повторов.
        Пустой результат нельзя загрузить CSV: вместо update строки удаляются
        через delete_row с need_reload, возвращается ответ последнего удаления.
        Такая очистка требует запроса на каждый ключ и не атомарна: при ошибке
        уже удалённые строки не восстанавливаются. Уже пустой словарь не меняется.
        Если в пустой результат попала строка с пустым ключом, вызывается
        ValueError до удаления: delete_row требует непустой rowKey.
        Чтение и перезапись словаря не защищены от параллельных изменений.
        """
        if not all((correlator_id, active_list_id, dictionary_id)):
            raise ValueError("Correlator, active list, and dictionary IDs are required")
        if (
            isinstance(max_cell_len, bool)
            or not isinstance(max_cell_len, int)
            or max_cell_len < 1
        ):
            raise ValueError("max_cell_len должен быть положительным целым числом")
        if any(
            not isinstance(flag, bool)
            for flag in (ascii_only, clean_existing, return_report, dry_run)
        ):
            raise ValueError(
                "ascii_only, clean_existing, return_report и dry_run должны быть bool"
            )
        if invalid_rows not in ("raise", "skip"):
            raise ValueError("invalid_rows должен быть raise или skip")
        if on_conflict not in ("keep", "update"):
            raise ValueError("on_conflict должен быть keep или update")
        if not isinstance(active_list_key, str) or not active_list_key:
            raise ValueError("active_list_key должен быть непустой строкой")
        if columns is not None and (
            not isinstance(columns, Mapping)
            or any(
                not isinstance(value, str) or not value
                for pair in columns.items()
                for value in pair
            )
        ):
            raise ValueError(
                "columns должен сопоставлять непустые имена столбцов и полей"
            )
        columns = dict(columns or {})
        if timeout is not None:
            self._validate_timeout(timeout)
        request_options = {} if timeout is None else {"timeout": timeout}
        stats = {"added": 0, "skipped": 0, "dropped": 0, "duplicates": 0, "replaced": 0}
        _, exported = self.export(correlator_id, active_list_id, **request_options)
        if not isinstance(exported, dict) or not exported.get("id"):
            raise APIError(
                "Active list export did not return a file ID", response_data=exported
            )
        with tempfile.TemporaryDirectory(prefix="kapi-") as directory:
            active = Path(directory) / "active-list.ndjson"
            original = Path(directory) / "dictionary.csv"
            target = Path(directory) / "result.csv"
            incoming = Path(directory) / "incoming.csv"
            merge = on_conflict == "update" and not clear
            self.download(exported["id"], filepath=active, **request_options)
            self._base.dictionaries.content(
                dictionary_id, filepath=original, **request_options
            )
            seen = set()
            with (
                original.open(encoding="utf-8-sig", newline="") as inp,
                target.open("w", encoding="utf-8", newline="") as out,
            ):
                reader = self._base.dictionaries._reader(inp)
                headers = reader.fieldnames
                if not headers:
                    raise ValueError("Dictionary CSV must have a header")
                if columns.keys() - set(headers[1:]):
                    raise ValueError(
                        "columns может содержать только существующие столбцы значений словаря"
                    )
                writer = csv.writer(out, lineterminator="\n")
                writer.writerow(headers)
                if not clear:
                    stats["dropped"] = self._write_existing(
                        reader,
                        writer,
                        headers,
                        seen,
                        max_cell_len,
                        ascii_only,
                        clean_existing,
                    )
                with (
                    active.open(encoding="utf-8-sig") as records,
                    incoming.open("w", encoding="utf-8", newline="") as new_rows,
                ):
                    count = self._write_records(
                        csv.writer(new_rows, lineterminator="\n") if merge else writer,
                        active_list_key,
                        self._read_records(records),
                        headers,
                        set() if merge else seen,
                        max_cell_len=max_cell_len,
                        ascii_only=ascii_only,
                        invalid_rows=invalid_rows,
                        stats=stats,
                        columns=columns,
                    )
            if merge and stats["added"]:
                merged = Path(directory) / "merged.csv"
                self._merge_updates(
                    target, incoming, merged, Path(directory) / "rows.sqlite", stats
                )
                target = merged
            if clear and count and not stats["added"]:
                raise ValueError("В AL нет корректных записей; словарь не очищен")
            updated = clear or bool(
                stats["added"] or stats["dropped"] or stats["replaced"]
            )
            if updated and not (seen or stats["added"]):
                (status, response), updated = self._clear_dictionary(
                    dictionary_id,
                    original,
                    need_reload,
                    dry_run=dry_run,
                    **request_options,
                )
            elif updated and not dry_run:
                status, response = self._base.dictionaries.update(
                    dictionary_id,
                    filepath=target,
                    need_reload=need_reload,
                    **request_options,
                )
            else:
                status, response = 200, {
                    "message": (
                        "Active list is empty"
                        if not count
                        else "Нет новых корректных записей"
                    ),
                    "updated": False,
                }
            if dry_run:
                return 200, {
                    "response": None,
                    "updated": False,
                    "would_update": bool(updated),
                    "dry_run": True,
                    **stats,
                }
            if return_report:
                return status, {"response": response, "updated": updated, **stats}
            return status, response
