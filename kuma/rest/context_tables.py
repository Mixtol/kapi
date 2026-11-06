from typing import Optional

from kuma._common.transfers import CHUNK_SIZE
from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPIContextTables(KumaRestAPIModule):
    """Methods for Context Tables (live on correlators)."""

    def list(
        self,
        correlator_id: str,
    ) -> APIResult:
        """
        Get context tables from correlator.
        Args:
            correlator_id (str): Correlator service id
        """
        params = {
            "correlatorID": correlator_id,
        }
        return self._make_request("GET", "contextTables", params=params)

    def export(
        self,
        correlator_id: str,
        context_table_id: Optional[str] = None,
        context_table_name: Optional[str] = None,
        *,
        format: str = "internal",
        filepath=None,
        stream=True,
        chunk_size=CHUNK_SIZE,
        timeout=None,
    ) -> APIResult:
        """
        Download context table data from correlator
        Args:
            correlator_id* (str): Correlator service ID
            context_table_id** (str): Exporting CT resource id
            context_table_name** (str): Exporting CT Name
        """
        params = {
            "correlatorID": correlator_id,
        }
        if format not in ("internal", "csv", "tsv"):
            raise ValueError("format must be internal, csv, or tsv")
        if self.contract_version == "3.4":
            if format != "internal":
                raise ValueError("KUMA 3.4 supports only internal context table export")
        else:
            params["format"] = format
        if bool(context_table_id) == bool(context_table_name):
            raise ValueError("Specify exactly one context table ID or name")
        if context_table_id:
            params["contextTableID"] = context_table_id
        else:
            params["contextTableName"] = context_table_name
        return self._download(
            "contextTables/export",
            filepath,
            stream=stream,
            chunk_size=chunk_size,
            timeout=timeout,
            params=params,
        )

    def import_data(
        self,
        correlator_id: str,
        format: str,
        data=None,
        *,
        filepath=None,
        chunk_size=CHUNK_SIZE,
        timeout=None,
        **kwargs,
    ) -> APIResult:
        """
        Import NDJSON, CSV, or TSV into a context table
        Args:
            correlator_id* (str): Service ID
            format* (str): format of represented data (csv|tsv|internal)
            contextTableID (str): CT UUID (must be ID or Name)
            contextTableName (str): CT Name
            clear (bool, optional): Is need to delete existing values. Defaults to False.
            data* (str): CT content (see examples)
        """
        if format not in ("internal", "csv", "tsv"):
            raise ValueError("format must be internal, csv, or tsv")
        if bool(kwargs.get("contextTableID")) == bool(kwargs.get("contextTableName")):
            raise ValueError("Specify exactly one contextTableID or contextTableName")
        params = {"correlatorID": correlator_id, "format": format, **kwargs}
        return self._upload(
            "contextTables/import",
            data,
            filepath=filepath,
            params=params,
            content_type=format,
            timeout=timeout,
            chunk_size=chunk_size,
        )
