import json
from typing import Dict, Tuple, Union

from ._base import KumaRestAPIModule


class KumaRestAPIActiveLists(KumaRestAPIModule):
    """
    Методы для работы с активными списками
    """

    def __init__(self, base):
        super().__init__(base)

    def lists(self, correlator_id: str) -> tuple[int, list | str]:
        """
        Gets current active lists on correlator.
        Args:
            correlatorID* (str): Service ID
        """
        return self._make_request(
            "GET", "activeLists", params={"correlatorID": correlator_id}
        )

    def import_data(
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
        return self._make_request(
            "POST", "activeLists/import", params=params, data=data
        )

    def download(self, file_id: str) -> Tuple[int, bytes]:
        """
        Download AL by generated ID.
        Args:
            file_id (str): File UUID via /download operation
        """
        return self._make_request(
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
        return self._make_request(
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
        return self._make_request(
            "GET", f"services/{correlator_id}/activeLists/scan/{active_list_id}"
        )

    # Extended function

    def to_dictionary(
        self,
        correlator_id: str,
        active_list_id: str,
        dictionary_id: str,
        active_list_key: str = "key",
        need_reload: int = 0,
        clear: bool = False,
    ) -> Tuple[int, Dict | str]:
        """
        Converts active sheet data into an existing dictionary,
        with the ability to change the key column.
        correlator_id* (str): Service ID
        active_list_id* (str): Source AL resource id
        dictionary_id* (str): Destination Dict. resource id
        active_list_key: Column name of Active List which will be key column in Dictionary.
        need_reload (1|0): Will restart all dependeses resources
        clear (bool): Will clear filled dictionary
        """
        if not correlator_id:
            raise ValueError("Correlator id must be specified")
        if not active_list_id:
            raise ValueError("Active List id must be specified")
        if not dictionary_id:
            raise ValueError("Dictionary id must be specified")

        _, download_id = self.export(
            correlator_id=correlator_id, active_list_id=active_list_id
        )
        _, al_content_json = self.download(download_id.get("id", {}))
        active_list_content = [
            json.loads(line) for line in al_content_json.splitlines()
        ]
        if not al_content_json:
            return 0, "Active List is empty"

        elif active_list_key != "key" and active_list_key not in active_list_content[
            0
        ].get("record"):
            raise ValueError(
                "Active List column name for key must be "
                "equal 'key' or exist in Active List record"
            )

        _, dict_data = self._base.dictionaries.content(dictionary_id)
        dict_headers = dict_data.splitlines()[0].split(",")

        if not clear:
            dict_unique_keys = frozenset(
                row.split(",")[0] for row in dict_data.splitlines()[1:]
            )
        else:
            dict_unique_keys = frozenset()
            dict_data = ",".join(dict_headers) + "\n"

        dict_data += self._get_data_with_column(
            active_list_key, active_list_content, dict_headers, dict_unique_keys
        )

        return self._base.dictionaries.update(
            dictionary_id=dictionary_id,
            csv=dict_data,
            need_reload=need_reload,
        )

    def _get_data_with_column(self, al_key, al_content, dict_headers, dict_unique_keys):
        dict_data = ""
        for row in al_content:
            al_record = row["record"]
            al_key = row["key"]
            dict_key = al_key if al_key == "key" else al_record[al_key]
            if dict_key not in dict_unique_keys:
                dict_unique_keys.add(dict_key)
                dict_line = [dict_key]
                for header in dict_headers[1:]:
                    value = al_record.get(header, "")
                    dict_line.append(value)
                dict_data += ",".join(dict_line) + "\n"
        return dict_data
