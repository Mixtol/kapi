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
        dictionary_key: str = "key",
        need_reload: int = 0,
    ) -> Tuple[int, Dict | str]:
        """
        Converts active sheet data into an existing dictionary,
        with the ability to change the key column.
        correlator_id* (str): Service ID
        active_list_id* (str): Source AL resource id
        dictionary_id* (str): Destination Dict. resource id
        dictionary_key: Key column name of Dictionary which will have values from key column of Active List.
        active_list_key: Column name of Active List which will be key column in Dictionary.
        """
        if not correlator_id:
            raise ValueError("Correlator id must be specified")
        if not active_list_id:
            raise ValueError("Active List id must be specified")
        if not dictionary_id:
            raise ValueError("Dictionary id must be specified")

        download_id = self.export(
            correlator_id=correlator_id, active_list_id=active_list_id
        )[1]["id"]
        al_content_json = self.download(download_id)[1]
        al_content = [json.loads(line) for line in al_content_json.splitlines()]

        if not al_content:
            return 0, "Active List is empty"

        if active_list_key != "key" and active_list_key not in al_content[0].get(
            "record"
        ):
            raise ValueError(
                "Active List column name for Dictionary key must be equal 'key' or exist in Active List"
            )

        dict_data = self._base.dictionaries.content(dictionary_id)[1]
        dict_unique_values = set(row.split(",")[0] for row in dict_data.splitlines()[1:])
        dict_headers = dict_data.splitlines()[0].split(",")
        del dict_headers[0]

        if active_list_key == "key":
            dict_data += self._get_data_with_key_column(
                dict_unique_values, al_content, dict_headers
            )
        else:
            dict_data += self._get_data_with_unique_column(
                dict_unique_values,
                al_content,
                dict_headers,
                active_list_key,
                dictionary_key,
            )

        return self._base.dictionaries.update(
            dictionary_id=dictionary_id,
            csv=dict_data,
            need_reload=need_reload,
        )

    def _get_data_with_key_column(self, dict_unique_values, al_content, dict_headers):
        dict_data = ""
        for row in al_content:
            if (key := row["key"]) not in dict_unique_values:
                record = row["record"]
                dict_unique_values.add(key)
                dict_data += f"{key},{','.join([record.get(header, '') for header in dict_headers])}\n"
        return dict_data

    def _get_data_with_unique_column(
        self,
        dict_unique_values,
        al_content,
        dict_headers,
        active_list_key,
        dictionary_key,
    ):
        index = dict_headers.index(dictionary_key)
        dict_headers[index] = "key"
        dict_data = ""
        for row in al_content:
            record = row["record"]
            if (key := record[active_list_key]) not in dict_unique_values:
                dict_unique_values.add(key)
                dict_data += f"{key},{','.join([record.get(header, '') if header != 'key' else row['key'] for header in dict_headers])}\n"
        return dict_data
