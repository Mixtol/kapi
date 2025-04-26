from typing import Dict, List, Optional, Tuple, Union


class KumaRestAPIContextTables:
    """
    Методы для работы с контекстными таблицами (живут на корреляторах)
    """

    def __init__(self, base):
        self._base = base

    def list(
        self,
        correlator_id: str,
    ) -> tuple[int, dict | str | bytes]:
        """
        Get context tables from correlator.
        Args:
            correlator_id (str): Correlator service id
        """
        params = {
            "correlatorID": correlator_id,
        }
        return self._base._make_request("GET", "contextTables", params=params)

    def export(
        self,
        correlator_id: str,
        context_table_id: Optional[str] = None,
        context_table_name: Optional[str] = None,
    ) -> Tuple[int, bytes | str]:
        """
        Download context table data from correlator
        Args:
            correlator_id* (str): COrrelator service ID
            context_table_id** (str): Exporting CT resource id
            context_table_name** (str): Exporting CT Name
        """
        params = {
            "correlatorID": correlator_id,
        }
        if context_table_id:
            params["contextTableID"] = context_table_id
        else:
            params["contextTableName"] = context_table_name
        return self._base._make_request("GET", "contextTables/export", params=params)

    def _import(
        self, correlator_id: str, format: str, data: str, **kwargs
    ) -> tuple[int, str]:
        """
        Method for importing JSON(with out commas), CSV, TSV to Correaltor AL
        Args:
            correlator_id* (str): Service ID
            format* (str): format of represented data (csv|tsv|internal)
            contextTableID (str): CT UUID (must be ID or Name)
            contextTableName (str): CT Name
            clear (bool, optional): Is need to delete existing values. Defaults to False.
            data* (str): CT content (see examples)
        """
        params = {"correlatorID": correlator_id, "format": format, **kwargs}
        return self._base._make_request(
            "POST",
            "contextTables/import",
            params=params,
            data=data,
            # headers={"Content-Type": f"text/{format}"}
        )
