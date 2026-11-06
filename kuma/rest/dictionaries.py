import csv
import os
import tempfile
from io import StringIO
from pathlib import Path
from typing import Dict

from kuma._common.transfers import CHUNK_SIZE
from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPIDictionaries(KumaRestAPIModule):
    """Methods for Dictionaries and Tables."""

    def content(
        self,
        dictionary_id: str,
        filepath=None,
        *,
        stream=True,
        chunk_size=CHUNK_SIZE,
        timeout=None,
    ):
        """Download UTF-8 CSV. Use stream=False to return a string in memory."""
        status, downloaded = self._download(
            "dictionaries",
            filepath,
            stream=True,
            chunk_size=chunk_size,
            timeout=timeout,
            params={"dictionaryID": dictionary_id},
            headers={"Accept": "text/plain; charset=utf-8"},
        )
        if filepath is None and not stream:
            # KUMA 4.2 sends text/csv without a charset; requests assumes Latin-1.
            with downloaded:
                return status, b"".join(downloaded).decode("utf-8-sig")
        return status, downloaded

    def add_row(
        self,
        dictionary_id: str,
        row_key: str,
        data: Dict,
        overwrite_exist: int = 0,
        need_reload: int = 0,
    ) -> APIResult:
        """
        Add row to dictionary.
        Args:
            dictionary_id* (str):
            row_key* (str): Key column field value
            overwrite_exist (int): 0|1 Delete existing data
            need_reload (int): 0|1 Reload services thats using resource
            data (Dict): Json where the key is the row field name,
                the value is the row field value. see example
        """
        params = {
            "dictionaryID": dictionary_id,
            "rowKey": row_key,
            "overwriteExist": overwrite_exist,
            "needReload": need_reload,
        }
        return self._make_request(
            "POST", "dictionaries/add_row", params=params, json=data
        )

    def delete_row(
        self, dictionary_id: str, row_key: str, need_reload: int = 0, *, timeout=None
    ) -> APIResult:
        """
        Delete row from dictionary by key.
        Args:
            dictionary_id* (str): Dictionary UUID
            row_key* (str): Key column field value
            need_reload (int): 0|1 Reload services thats using resource
            timeout: Seconds or (connect, read); None uses the client timeout.
        """
        params = {
            "dictionaryID": dictionary_id,
            "rowKey": row_key,
            "needReload": need_reload,
        }
        return self._make_request(
            "POST", "dictionaries/delete_row", params=params, timeout=timeout
        )

    def update(
        self,
        dictionary_id: str,
        csv=None,
        need_reload: int = 0,
        *,
        filepath=None,
        timeout=None,
        chunk_size=CHUNK_SIZE,
    ):
        """Stream CSV text, bytes, a binary stream, or a file as multipart data.

        Existing string paths remain supported; filepath is unambiguous for files.
        """
        if isinstance(csv, os.PathLike) or (
            isinstance(csv, str) and os.path.isfile(csv)
        ):
            if filepath is not None:
                raise ValueError("Specify either filepath or csv, not both")
            filepath, csv = csv, None
        return self._upload(
            "dictionaries/update",
            csv,
            filepath=filepath,
            multipart=True,
            filename=Path(filepath).name if filepath is not None else "data.csv",
            content_type="text/csv; charset=utf-8",
            timeout=timeout,
            chunk_size=chunk_size,
            params={"dictionaryID": dictionary_id, "needReload": need_reload},
        )

    @staticmethod
    def _reader(source):
        reader = csv.DictReader(source, strict=True)
        headers = reader.fieldnames
        if headers and (
            any(not h for h in headers) or len(set(headers)) != len(headers)
        ):
            raise ValueError("CSV column names must be non-empty and unique")
        return reader

    @staticmethod
    def _rows(reader):
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(
                    f"CSV row {reader.line_num} has an incorrect number of columns"
                )
            yield row

    def csv_to_json(self, csv_data: str) -> list:
        """Parse CSV with quoted commas, embedded newlines, and UTF-8 BOM support."""
        return list(
            self._rows(self._reader(StringIO(csv_data.lstrip("\ufeff"), newline="")))
        )

    def _write_with_key(self, source, output, new_key_column):
        reader = self._reader(source)
        headers = reader.fieldnames or []
        if new_key_column not in headers:
            raise ValueError(f"CSV key column does not exist: {new_key_column}")

        # Swap names instead of overwriting an existing 'value' column.
        def rename(name):
            if name == new_key_column:
                return "key"
            if name == "key":
                return new_key_column
            return name

        writer = csv.DictWriter(
            output, fieldnames=[rename(h) for h in headers], lineterminator="\n"
        )
        writer.writeheader()
        seen = set()
        for row in self._rows(reader):
            key = row[new_key_column]
            if not key or key in seen:
                raise ValueError(
                    f"CSV key must be non-empty and unique (row {reader.line_num})"
                )
            seen.add(key)
            writer.writerow({rename(name): value for name, value in row.items()})

    def _swap_key_column(self, csv_data, new_key_column):
        output = StringIO(newline="")
        self._write_with_key(
            StringIO(csv_data.lstrip("\ufeff"), newline=""), output, new_key_column
        )
        return output.getvalue()

    def to_active_list(
        self,
        dictionary_id: str,
        correlator_id: str,
        active_list_id: str,
        dictionary_key: str = "key",
        clear: bool = False,
    ):
        """Convert CSV on disk and upload it after validating every key."""
        with tempfile.TemporaryDirectory(prefix="kapi-") as directory:
            source = Path(directory) / "dictionary.csv"
            target = Path(directory) / "active-list.csv"
            self.content(dictionary_id, filepath=source)
            with (
                source.open(encoding="utf-8-sig", newline="") as inp,
                target.open("w", encoding="utf-8", newline="") as out,
            ):
                self._write_with_key(inp, out, dictionary_key)
            return self._base.active_lists.import_data(
                correlator_id,
                "csv",
                filepath=target,
                activeListID=active_list_id,
                keyField="key",
                clear=clear,
            )
