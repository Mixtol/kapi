import csv
import os
from io import StringIO
from typing import Dict, List, Optional, Tuple, Union

from ._base import APIError, KumaRestAPIModule


class KumaRestAPIDictionaries(KumaRestAPIModule):
    """
    Методы для работы со словарями и таблицами
    """

    def __init__(self, base):
        super().__init__(base)

    def content(self, dictionary_id: str) -> Tuple[int, str]:
        """
        Get dictionary content.
        """
        return self._make_request(
            "GET",
            "dictionaries",
            params={"dictionaryID": dictionary_id},
            headers={"Accept": "text/plain; charset=utf-8"},
        )

    def add_row(
        self,
        dictionary_id: str,
        row_key: str,
        data: Dict,
        overwrite_exist: int = 0,
        need_reload: int = 0,
    ) -> Tuple[int, Dict]:
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
        self, dictionary_id: str, row_key: str, need_reload: int = 0
    ) -> Tuple[int, Dict]:
        """
        Delete row from dictionary by key.
        Args:
            dictionary_id* (str): Dictionary UUID
            row_key* (str): Key column field value
            need_reload (int): 0|1 Reload services thats using resource
        """
        params = {
            "dictionaryID": dictionary_id,
            "rowKey": row_key,
            "needReload": need_reload,
        }
        return self._make_request("POST", "dictionaries/add_row", params=params)

    def update(
        self, dictionary_id: str, csv: str, need_reload: int = 0
    ) -> Tuple[int, Dict]:
        """
        Rewrite dictionary from CSV file or data.
        Args:
            dictionary_id (str): Dictionary UUID
            need_reload (int): 0|1 Reload services thats using resource
            csv (str): Dictionary CSV Text OR Path to existing CSV File, see examples
        """
        params = {"dictionaryID": dictionary_id, "needReload": need_reload}
        try:
            if os.path.isfile(csv):
                with open(csv, "rb") as file:
                    files = {"file": (os.path.basename(csv), file)}
            else:
                files = {"file": ("data.csv", csv)}
            return self._make_request(
                "POST", "dictionaries/update", params=params, files=files
            )
        except IOError as exception:
            raise APIError(f"File operation failed: {exception}") from exception

    # Extended

    def csv_to_json(self, csv_data: str) -> Dict:
        """
        Transform CSV in JSON list.
        Args:
            csv_data: CSV string rows from dictionary content.
        """
        try:
            lines = [line.strip() for line in csv_data.split("\n") if line.strip()]
            if not lines:
                return []
            headers = [header.strip() for header in lines[0].split(",")]
            result = []
            for line in lines[1:]:
                values = [value.strip() for value in line.split(",")]

                # Обрезаем или дополняем значения, если не strict
                row_values = values[: len(headers)]
                row_dict = dict(zip(headers, row_values))
                result.append(row_dict)

            return result

        except Exception as e:
            self.logger.exception(f"Unknown exeption: {e}")
            return None

    def to_active_list(
        self,
        dictionary_id: str,
        correlator_id: str,
        active_list_id: str,
        dictionary_key: str = "key",
        clear: bool = False,
    ) -> Tuple[int, Dict | str]:
        """
        Converts dictionary data to an existing active list,
            with the ability to change the key column.
        dictionary_id* (str): Destination Dict. resource id
        correlator_id* (str): Service ID
        active_list_id* (str): Source AL resource id
        dictionary_key (str): Key column name of Dictionary which will have values from key column of Active List.
        clear (bool, optional): Is need to delete existing values. Defaults to False.
        """
        dictionary_data = self._swap_key_column(
            self.content(dictionary_id)[1], dictionary_key
        )

        return self._base.active_lists.import_data(
            correlator_id,
            "csv",
            activeListID=active_list_id,
            keyField=dictionary_key,
            data=dictionary_data,
            clear=clear,
        )

        pass

    def _swap_key_column(self, csv_data, new_key_column):
        """Function for replacing key field in CSV
        with uniqueness validation and renaming

        Args:
            csv_data (str): Data
            new_key_column (str): Which CSV column should be taken
        """
        reader = csv.DictReader(StringIO(csv_data.strip()))
        rows = list(reader)
        fieldnames = reader.fieldnames
        if new_key_column == "key" or new_key_column not in fieldnames:
            return csv_data
        new_fieldnames = ["key", "value"] + [
            f for f in fieldnames if f not in ["key", new_key_column]
        ]
        new_rows = []
        for row in rows:
            if not row.get(new_key_column):
                continue
            new_row = {
                "key": row[new_key_column],  # Новая колонка -> key
                "value": row.get("key", ""),  # Старый key -> value
            }
            # Добавляем остальные поля (кроме key и new_key_column)
            for field in row:
                if field not in ["key", new_key_column, "", None]:
                    new_row[field] = row[field]
            new_rows.append(new_row)
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=new_fieldnames)
        writer.writeheader()
        writer.writerows(new_rows)

        return output.getvalue()
