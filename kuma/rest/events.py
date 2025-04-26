from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Union


class KumaRestAPIEvents:
    """
    Методы для работы с событиями
    """

    def __init__(self, base):
        self._base = base

    def search(
        self,
        cluster_id: str,
        start_time: Union[str, int],
        end_time: Union[str, int],
        sql: str,
        empty_fields: bool = True,
        raw_timestamps: bool = True,
    ) -> Tuple[int, Union[Dict, List, str]]:
        """Execute SQL query on events, see .get_time()
        Args:
            cluster_id* (str): Storage cluster UUID
            start_time* (Union[str, int]): Start of event
            end_time* (Union[str, int]): End time of events
            sql* (str): SQL query to search
            empty_fields (bool, optional): Display null fields
            raw_timestamps (bool, optional): Display raw event timestamp
        """
        json = {
            "clusterID": cluster_id,
            "period": {
                "from": self.format_time(start_time),
                "to": self.format_time(end_time),
            },
            "emptyFields": empty_fields,
            "rawTimestamps": raw_timestamps,
            "sql": sql,
        }
        return self._base._make_request("POST", "events", json=json)

    def get_clusters(self, **kwargs) -> tuple[int, dict | str | bytes]:
        """
        List storages clusters for events.
        Args:
            cluster_id ([List[str]], optional): Storage cluster UUID filter
            tenant_id ([List[str]], optional): Tenant UUID filter
            name (str, optional): Name regex filter
            page (int, optional): Pagination page number

        Returns:
            tuple[int, dict | str | bytes]: _description_
        """
        params = {**kwargs}
        return self._base._make_request("GET", "events/clusters", params=params)

    def get_time(self, offset_m: int = 0, offset_h: int = 0) -> str:
        """
        Get time for event search method
        Args:
            offset_m: Minutes to add/subtract from current time
            offset_h: Hours to add/subtract from current time
        Returns:
            str: Time in format 'YYYY-MM-DDTHH:MM:SSZ'
        Examples:
            >>> get_time()  # Current time
            '2023-05-15T14:30:00Z'
            >>> get_time(offset_m=15)  # 15 minutes later
            '2023-05-15T14:45:00Z'
            >>> get_time(offset_h=-2)  # 2 hours earlier
            '2023-05-15T12:30:00Z'
        """
        now = datetime.now(timezone.utc)
        offset = timedelta(hours=offset_h, minutes=offset_m)
        adjusted_time = now + offset
        return adjusted_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def epoch_to_iso8601(epoch_time: int) -> str:
        """
        Convert epoch timestamp to ISO 8601 format
        Examples:
            >>> epoch_to_iso8601(1630894200)
            '2021-09-06T00:10:00Z'
        """
        return datetime.fromtimestamp(epoch_time, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
