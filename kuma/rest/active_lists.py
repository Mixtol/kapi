import csv
import json
import tempfile
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

    def _write_records(self, writer, al_key, records, headers, seen):
        count = 0
        for row in records:
            record = row.get("record")
            if not isinstance(record, dict):
                raise ValueError("Active list record must be an object")
            source = row if al_key == "key" else record
            if al_key not in source:
                raise ValueError(f"Active list key column is missing: {al_key}")
            key = self._cell(source[al_key])
            if not key:
                raise ValueError("Active list key cannot be empty")
            if key not in seen:
                seen.add(key)
                writer.writerow(
                    [key] + [self._cell(record.get(h)) for h in headers[1:]]
                )
            count += 1
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

    def to_dictionary(
        self,
        correlator_id: str,
        active_list_id: str,
        dictionary_id: str,
        active_list_key: str = "key",
        need_reload: int = 0,
        clear: bool = False,
    ):
        """Convert NDJSON and CSV on disk, preserving quoting and existing keys."""
        if not all((correlator_id, active_list_id, dictionary_id)):
            raise ValueError("Correlator, active list, and dictionary IDs are required")
        _, exported = self.export(correlator_id, active_list_id)
        if not isinstance(exported, dict) or not exported.get("id"):
            raise APIError(
                "Active list export did not return a file ID", response_data=exported
            )
        with tempfile.TemporaryDirectory(prefix="kapi-") as directory:
            active = Path(directory) / "active-list.ndjson"
            original = Path(directory) / "dictionary.csv"
            target = Path(directory) / "result.csv"
            self.download(exported["id"], filepath=active)
            self._base.dictionaries.content(dictionary_id, filepath=original)
            seen = set()
            with (
                original.open(encoding="utf-8-sig", newline="") as inp,
                target.open("w", encoding="utf-8", newline="") as out,
            ):
                reader = self._base.dictionaries._reader(inp)
                headers = reader.fieldnames
                if not headers:
                    raise ValueError("Dictionary CSV must have a header")
                writer = csv.writer(out, lineterminator="\n")
                writer.writerow(headers)
                if not clear:
                    for row in self._base.dictionaries._rows(reader):
                        seen.add(row[headers[0]])
                        writer.writerow([row[h] for h in headers])
                with active.open(encoding="utf-8-sig") as records:
                    count = self._write_records(
                        writer,
                        active_list_key,
                        (json.loads(line) for line in records if line.strip()),
                        headers,
                        seen,
                    )
            if not count and not clear:
                return 200, {"message": "Active list is empty", "updated": False}
            return self._base.dictionaries.update(
                dictionary_id, filepath=target, need_reload=need_reload
            )
