import os
from typing import Dict, List, Optional, Tuple, Union

from ._base import APIError, KumaRestAPIBase


class KumaRestAPIDictionaries(KumaRestAPIBase):
    """
    Методы для работы со словарями и таблицами
    """

    def __init__(self, base):
        self._base = base

    def content(self, dictionary_id: str) -> Tuple[int, str]:
        """
        Get dictionary content.
        """
        return self._base._make_request(
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
        return self._base._make_request(
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
        return self._base._make_request("POST", "dictionaries/add_row", params=params)

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
            return self._base._make_request(
                "POST", "dictionaries/update", params=params, files=files
            )
        except IOError as exception:
            raise APIError(f"File operation failed: {exception}") from exception

    # Extended

    def csv_to_json(self, csv_data: str) -> Dict:
        """
        Преобразует CSV словаря в список JSON объектов с обработкой ошибок.
        Args:
            csv_data: CSV строка с заголовками из контента dictionaries
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
            self._client.logger.exception(f"Unknown exeption: {e}")
            return None
