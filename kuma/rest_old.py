import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from .logging import configure_logging

_logger = configure_logging()
_api_version = "v2.1"


class APIError(Exception):
    """Exception for API errors with status code support."""

    def __init__(self, message: str, status_code: int = None):
        self.status_code = status_code
        super().__init__(message)
        _logger.error(f"APIError: {message} (status: {status_code})")


class KumaRestAPI:
    """
    Client for KUMA REST API (version 3.2+).
    Key Features:
    - Unified request handling with _make_request()
    - Content-type aware response parsing (JSON/text/binary)
    - Comprehensive error handling
    - Detailed logging
    - Type hints for better IDE support
    Example:
        >>> kapi = KumaRestAPI(base_url="https://kumacore.local", token="your_token")
        >>> status, services = kapi.get_services(kind="correlator")
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        verify: bool = False,
        timeout: int = 30,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize API client.
        Args:
            base_url: Base server URL (e.g., "https://kumacore.local")
            token: Bearer token for authentication
            verify: Verify SSL certificates (default: False)
            timeout: Request timeout in seconds (default: 30)
        """
        self.base_url = base_url.rstrip("/")
        self.verify = verify
        self.timeout = timeout
        self.session = requests.Session()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        self.logger = logger or _logger
        self.logger.info(f"Initialized KUMA API client for {self.base_url}")

    def _make_request(
        self, method: str, endpoint: str, headers: Optional[Dict] = None, **kwargs
    ) -> Tuple[int, Union[Dict, str, bytes]]:
        """
        Unified request method with error handling and logging.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., 'dictionaries/add_row')
            headers: Additional headers
            **kwargs: Request parameters
        Returns:
            Tuple of (status_code, response_data)
        Raises:
            APIError: On request failure or bad status code
        """
        url = f"{self.base_url}:7223/api/{_api_version}/{endpoint.lstrip('/')}"
        headers = {**self.headers, **(headers or {})}

        self.logger.debug(f"Request: {method} {url}")
        self.logger.debug(f"Params: {kwargs.get('params')}")
        self.logger.debug(f"Headers: {headers.keys()}")

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                verify=self.verify,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exception:
            self.logger.error(f"Request failed: {str(exception)}")
            raise APIError(f"Request failed: {exception}") from exception

        self.logger.debug(f"Response: {response.status_code}")
        self.logger.debug(f"Content-Type: {response.headers.get('Content-Type')}")

        if response.status_code >= 300:
            error_msg = f"Bad response {response.status_code}: {response.text[:500]}"
            self.logger.error(error_msg)
            raise APIError(error_msg, status_code=response.status_code)

        try:
            content_type = response.headers.get("Content-Type", "").lower()
            if "application/json" in content_type:
                return response.status_code, response.json()
            elif content_type.startswith("text/"):
                return response.status_code, response.text
            elif (
                "attachment" in response.headers.get("Content-Disposition", "").lower()
            ):
                self.logger.info(
                    f"Received binary data ({len(response.content)} bytes)"
                )

            return response.status_code, response.content
        except Exception as exception:
            self.logger.error(f"Response parsing failed: {str(exception)}")
            raise APIError(f"Response parsing failed: {exception}")

    def download_file(self, file_id: str) -> Tuple[int, bytes]:
        """
        Download file by ID.

        Args:
            file_id: File identifier

        Returns:
            Tuple of (status_code, file_content)
        """
        self.logger.info(f"Downloading file {file_id}")
        return self._make_request(
            "GET", f"download/{file_id}", headers={"Accept": "application/octet-stream"}
        )

    def get_resource(self, id: str, kind: str) -> Tuple[int, Dict]:
        """
        Get resource by ID and kind.

        Args:
            id: Resource ID.
            kind: Resource type.

        Returns:
            Tuple of (status_code, resource_data).
        """
        self.logger.debug(f"Getting resource {kind}/{id}")
        return self._make_request("GET", f"resources/{kind}/{id}")

    def get_dictionary(self, dictionary_id: str) -> Tuple[int, str]:
        """
        Get dictionary content.

        Args:
            dictionary_id: Dictionary ID.

        Returns:
            Tuple of (status_code, CSV_content).
        """
        self.logger.info(f"Getting dictionary {dictionary_id}")
        return self._make_request(
            "GET",
            "dictionaries",
            params={"dictionaryID": dictionary_id},
            headers={"Accept": "text/csv"},
        )

    def add_dictionary_row(
        self,
        data: Dict,
        dictionary_id: str,
        row_key: str,
        overwrite_exist: int = 0,
        need_reload: int = 0,
    ) -> Tuple[int, Dict]:
        """
        Add row to dictionary.

        Args:
            data: Dictionary data {"Column1": "value1", ...}.
            dictionary_id: Dictionary ID.
            row_key: Unique key value.
            overwrite_exist: Overwrite if exists (1/0).
            need_reload: Reload correlators (1/0).

        Returns:
            Tuple of (status_code, operation_result).
        """
        self.logger.info(f"Adding row to dictionary {dictionary_id}")
        params = {
            "dictionaryID": dictionary_id,
            "rowKey": row_key,
            "overwriteExist": overwrite_exist,
            "needReload": need_reload,
        }
        return self._make_request(
            "POST", "dictionaries/add_row", params=params, json=data
        )

    def update_dictionary_from_csv(
        self, dictionary_id: str, file_path_or_data: str, need_reload: int = 0
    ) -> Tuple[int, Dict]:
        """
        Update dictionary from CSV file.

        Args:
            dictionary_id: Dictionary ID.
            file_path_or_data: Path to CSV file or data in CSV format.
            need_reload: Reload correlators (1/0).

        Returns:
            Tuple of (status_code, operation_result).

        Raises:
            ValueError: If file doesn't exist.
            APIError: On file operation failure.
        """
        params = {"dictionaryID": dictionary_id, "needReload": need_reload}
        try:
            if os.path.isfile(file_path_or_data):
                self.logger.info(
                    f"Updating dictionary {dictionary_id} from {file_path_or_data}"
                )
                with open(file_path_or_data, "rb") as file:
                    files = {"file": (os.path.basename(file_path_or_data), file)}
            else:
                self.logger.info(f"Updating dictionary {dictionary_id} with CSV data")
                files = {"file": ("data.csv", file_path_or_data)}

            return self._make_request(
                "POST", "dictionaries/update", params=params, files=files
            )
        except IOError as exception:
            self.logger.error(f"File operation failed: {str(exception)}")
            raise APIError(f"File operation failed: {exception}") from exception

    def get_correlator_active_lists(
        self, correlator_id: str
    ) -> tuple[int, dict | str | bytes]:
        """
        Get active lists for correlator.

        Args:
            correlator_id: Correlator service ID.

        Returns:
            Tuple of (status_code, list_of_active_lists).
        """
        self.logger.info(f"Getting active lists for correlator {correlator_id}")
        return self._make_request(
            "GET", "activeLists", params={"correlatorID": correlator_id}
        )

    def get_active_list_scan(
        self, correlator_id: str, active_list_id: str
    ) -> Tuple[int, Dict]:
        """
        Scan active list content.

        Args:
            correlator_id: Correlator service ID.
            active_list_id: Active list ID.

        Returns:
            Tuple of (status_code, active_list_content).
        """
        self.logger.info(f"Scanning active list {active_list_id} on {correlator_id}")
        return self._make_request(
            "GET", f"services/{correlator_id}/activeLists/scan/{active_list_id}"
        )

    def export_active_list(
        self, correlator_id: str, active_list_id: str
    ) -> Tuple[int, bytes]:
        """
        Export active list content.

        Args:
            correlator_id: Correlator ID.
            active_list_id: Active list ID.

        Returns:
            Tuple of (status_code, exported_data).
        """
        self.logger.info(f"Exporting active list {active_list_id} from {correlator_id}")
        return self._make_request(
            "GET",
            f"services/{correlator_id}/activeLists/export/{active_list_id}",
            headers={"Accept": "application/octet-stream"},
        )

    def get_correlator_tables(
        self, correlator_id: str, **kwargs
    ) -> tuple[int, dict | str | bytes]:
        """
        Get context tables for correlator.

        Args:
            correlator_id: Correlator ID.
            **kwargs: Additional filters.

        Returns:
            Tuple of (status_code, list_of_tables).
        """
        self.logger.info(f"Getting tables for correlator {correlator_id}")
        params = {"correlatorID": correlator_id, **kwargs}
        return self._make_request("GET", "contextTables", params=params)

    def import_table(
        self,
        data: Union[Dict, str],
        correlator_id: str,
        table_id: str | None = None,
        table_name: str | None = None,
        format: str = "csv",
        clear: bool = False,
    ) -> Tuple[int, Dict]:
        """
        Import context table.

        Args:
            data: Table data (dict or file path).
            correlator_id: Correlator ID.
            table_id: Table ID.
            table_name: Table name.
            format: Data format (csv/tsv/internal).
            clear: Clear existing data.

        Returns:
            Tuple of (status_code, import_result).
        """
        if table_id is None and table_name is None:
            raise ValueError("Table ID or table name must be specified")
        self.logger.info(f"Importing table {table_id} to {correlator_id}")

        params = {
            "correlatorID": correlator_id,
            "format": format.lower(),
            "clear": str(clear).lower(),
        }
        if table_id is not None:
            params["contextTableID"] = table_id
        else:
            params["contextTableName"] = table_name

        if isinstance(data, str) and os.path.isfile(data):
            self.logger.debug(f"Reading table data from file {data}")
            with open(data, "r", encoding="utf-8") as f:
                data = f.read()

        return self._make_request(
            "POST",
            "contextTables/import",
            params=params,
            data=data,
            headers={"Content-Type": "text/csv"},
        )

    def get_services(
        self,
        page: int = 1,
        **kwargs,
    ) -> tuple[int, dict | str | bytes]:
        """
        Get services with filtering.
        Args:
            id:str Service UUID filter.
            tenantID:str Tenant UUID filter.
            kind:str storage|correlator... Service kind filter.
            page:int Page number from 1
            fqdn:str Service FQND filter (PCRE).
            name:str Service name (PCRE).
            paired:true|false services that executed the first start.
        """
        self.logger.info("Getting services with filters")
        params = {"page": page, **kwargs}
        return self._make_request("GET", "services", params=params)

    def create_service(self, resource_id: str) -> Tuple[int, Dict]:
        """
        Create service from resource.

        Args:
            resource_id: Resource ID.

        Returns:
            Tuple of (status_code, created_service).
        """
        self.logger.info(f"Creating service from resource {resource_id}")
        return self._make_request(
            "POST", "services/create", json={"resourceID": resource_id}
        )

    def get_tenants(
        self,
        id: Optional[str] = None,
        name: Optional[str] = None,
        main: Optional[bool] = None,
        page: int = 1,
    ) -> tuple[int, dict | str | bytes]:
        """
        Get tenants with filtering.

        Args:
            id: Tenant ID filter.
            name: Tenant name filter.
            main: Main tenant filter.
            page: Page number.

        Returns:
            Tuple of (status_code, list_of_tenants).
        """
        self.logger.info("Getting tenants with filters")
        params = {
            "id": id,
            "name": name,
            "main": str(main).lower() if main is not None else None,
            "page": page,
        }
        return self._make_request("GET", "tenants", params=params)

    def get_alerts(
        self, page: int = 1, limit: int = 250, **kwargs
    ) -> tuple[int, dict | str | bytes] | tuple[int, list[Any]]:
        """
        Get alerts with pagination.

        Args:
            page: Page number.
            limit: Items per page.
            **kwargs: Additional filters.

        Returns:
            Tuple of (status_code, list_of_alerts).
        """
        self.logger.info(f"Getting alerts page {page} (limit {limit})")
        all_alerts = []
        current_page = page

        while True:
            params = {
                "page": current_page,
                "page_size": min(limit - len(all_alerts), 250),
                **kwargs,
            }

            status_code, data = self._make_request("GET", "alerts", params=params)

            if status_code != 200:
                return status_code, data

            items = data if isinstance(data, list) else [data]
            all_alerts.extend(items)

            if len(all_alerts) >= limit or len(items) < params["page_size"]:
                break

            current_page += 1

        return 200, all_alerts[:limit]

    def assign_alerts(self, user_id: str, alert_ids: List[str]) -> Tuple[int, Dict]:
        """
        Assign alerts to user.

        Args:
            user_id: User ID
            alert_ids: List of alert IDs

        Returns:
            Tuple of (status_code, operation_result)
        """
        self.logger.info(f"Assigning {len(alert_ids)} alerts to user {user_id}")
        return self._make_request(
            "POST", "alerts/assign", json={"userId": user_id, "ids": alert_ids}
        )

    def close_alert(self, alert_id: str, reason: str = "responded") -> Tuple[int, Dict]:
        """
        Close alert with reason.

        Args:
            alert_id: Alert ID.
            reason: Close reason.

        Returns:
            Tuple of (status_code, operation_result).
        """
        self.logger.info(f"Closing alert {alert_id} (reason: {reason})")
        return self._make_request(
            "POST", "alerts/close", json={"id": alert_id, "reason": reason}
        )

    def search_events(self, body: Dict) -> Tuple[int, Union[Dict, List]]:
        """
        Search events with complex query.

        Args:
            body: Search parameters.

        Returns:
            Tuple of (status_code, search_results).
        """
        self.logger.info("Searching events with complex query")
        return self._make_request("POST", "events", json=body)

    def post_sql(
        self,
        cluster_id: str,
        start_time: Union[str, int],
        end_time: Union[str, int],
        query: str,
        empty_fields: bool = True,
        raw_timestamps: bool = True,
    ) -> Tuple[int, Union[Dict, List]]:
        """
        Execute SQL query on events.

        Args:
            cluster_id: Cluster ID.
            start_time: Start time (ISO string or timestamp).
            end_time: End time (ISO string or timestamp).
            query: SQL query.
            empty_fields: Include empty fields.
            raw_timestamps: Use raw timestamps.

        Returns:
            Tuple of (status_code, query_results).
        """

        self.logger.info(f"Executing SQL query on cluster {cluster_id}")
        data = {
            "clusterID": cluster_id,
            "period": {
                "from": self.format_time(start_time),
                "to": self.format_time(end_time),
            },
            "emptyFields": empty_fields,
            "rawTimestamps": raw_timestamps,
            "sql": query,
        }
        return self._make_request("POST", "events", json=data)

    @staticmethod
    def format_time(time_value):
        if isinstance(time_value, int):
            return datetime.fromtimestamp(time_value).isoformat()
        return time_value

    def get_clusters(
        self,
        id: Optional[List[str]] = None,
        tenant_id: Optional[List[str]] = None,
        name: Optional[str] = None,
        page: int = 1,
    ) -> tuple[int, dict | str | bytes]:
        """
        Get event clusters.

        Args:
            id: Cluster IDs filter.
            tenant_id: Tenant IDs filter.
            name: Name pattern filter.
            page: Page number.

        Returns:
            Tuple of (status_code, list_of_clusters).
        """
        self.logger.info("Getting event clusters")
        params = {"id": id, "tenantID": tenant_id, "name": name, "page": page}
        return self._make_request("GET", "events/clusters", params=params)

    def active_list_to_dictionary(
        self,
        correlator_id: str = "",
        active_list_id: str = "",
        dictionary_id: str = "",
        need_reload: int = 0,
    ) -> Tuple[int, Dict]:
        """
        Transform active list data to dictionary.

        Args:
            correlator_id: Correlator service ID.
            active_list_id: Active list ID.
            dictionary_id: Dictionary ID.
            need_reload: Reload correlators (1/0).

        Returns:
            Tuple of (status_code, operation_result).

        Raises:
            ValueError: If correlator_id or active_list_id or dictionary_id is not specified.
        """
        if not correlator_id:
            raise ValueError("Correlator id must be specified")
        if not active_list_id:
            raise ValueError("Active List id must be specified")
        if not dictionary_id:
            raise ValueError("Dictionary id must be specified")

        dictionary_data = self.get_dictionary(dictionary_id)[1]
        active_list = self.get_active_list_scan(
            correlator_id=correlator_id, active_list_id=active_list_id
        )

        for record_number, item in enumerate(active_list[1]["data"], 1):
            dictionary_data += (
                f'RecordFromActiveList_{record_number},"{item["Record"]}"\n'
            )

        return self.update_dictionary_from_csv(
            dictionary_id=dictionary_id,
            file_path_or_data=dictionary_data,
            need_reload=need_reload,
        )
