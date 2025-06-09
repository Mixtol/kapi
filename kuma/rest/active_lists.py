from typing import Dict, List, Optional, Tuple, Union


class KumaRestAPIActiveLists:
    """
    Методы для работы с активными списками
    """

    def __init__(self, base):
        self._base = base

    def lists(self, correlator_id: str) -> tuple[int, list | str]:
        """
        Gets current active lists on correlator.
        Args:
            correlatorID* (str): Service ID
        """
        return self._base._make_request(
            "GET", "activeLists", params={"correlatorID": correlator_id}
        )

    def _import(
        self, correlator_id: str, format: str, data: str, **kwargs
    ) -> tuple[int, Union[str, list]]:
        """
            Method for importing JSON(with out commas), CSV, TSV to Correaltor AL
        Args:
            correlator_id* (str): Service ID
            format* (str): format of represented data (csv|tsv|internal)
            activeListID (str): AL UUID (must be ID or Name)
            activeListName (str): AL Name
            keyField* (str): Name of key (uniq) column for csv and tsv
            clear (bool, optional): Is need to delete existing values. Defaults to False.
            data* (str): AL content (see examples)
        """
        params = {"correlatorID": correlator_id, "format": format, **kwargs}
        return self._base._make_request(
            "POST", "activeLists/import", params=params, data=data
        )

    def download(self, file_id: str) -> Tuple[int, bytes]:
        """
        Download AL by generated ID.
        Args:
            file_id (str): File UUID via /download operation
        """
        return self._base._make_request(
            "GET", f"download/{file_id}", headers={"Accept": "application/octet-stream"}
        )

    def export(
        self, correlator_id: str, active_list_id: str
    ) -> Tuple[int, bytes | str]:
        """
        Generatind AL file ID for download file method.
        Args:
            correlator_id* (str): Service ID
            active_list_id* (str): Exporting AL resource id
        """
        return self._base._make_request(
            "GET",
            f"services/{correlator_id}/activeLists/export/{active_list_id}",
            headers={"Accept": "application/octet-stream"},
        )

    def scan(
        self, correlator_id: str, active_list_id: str, **kwargs
    ) -> Tuple[int, Dict | str]:
        """
        Scan active list content withouts keys (For some extraordinary shit).
        Args:
            correlator_id* (str): Service ID
            active_list_id* (str): Exporting AL resource id
            from (str): Epoch in nanoseconds
            exclude (str): Epoch in nanoseconds
            pattern (str): Key search string filter
            limit (str): Yes str but actualy its limit number
            sort (str): For ASC <columnname> or add '-columnname' for DESC
        """
        return self._base._make_request(
            "GET", f"services/{correlator_id}/activeLists/scan/{active_list_id}"
        )
