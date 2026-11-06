from datetime import datetime, timedelta, timezone

from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPIEvents(KumaRestAPIModule):
    """Methods for Events."""

    def search(
        self,
        cluster_id=None,
        start_time=None,
        end_time=None,
        sql=None,
        empty_fields: bool = True,
        raw_timestamps: bool = True,
    ) -> APIResult:
        """Execute SQL query on events, see .get_time()
        Args:
            cluster_id* (str): Storage cluster UUID
            start_time* (Union[str, int]): Start of event
            end_time* (Union[str, int]): End time of events
            sql* (str): SQL query to search
            empty_fields (bool, optional): Display null fields
            raw_timestamps (bool, optional): Display raw event timestamp
        """
        if (
            start_time is None
            or end_time is None
            or not isinstance(sql, str)
            or not sql.strip()
        ):
            raise ValueError("start_time, end_time, and SQL are required")
        json = {
            "period": {
                "from": self._base.format_time(start_time),
                "to": self._base.format_time(end_time),
            },
            "emptyFields": empty_fields,
            "rawTimestamps": raw_timestamps,
            "sql": sql,
        }
        if cluster_id is not None:
            json["clusterID"] = cluster_id
        return self._make_request("POST", "events", json=json)

    def get_clusters(self, **kwargs) -> APIResult:
        """
        List storages clusters for events.
        Args:
            id (List[str], optional): Storage cluster UUID filter
            tenantID (List[str], optional): Tenant UUID filter
            name (str, optional): Name filter (regex in 3.4, substring in 4.x)
            page (int, optional): Pagination page number

        Returns:
            Tuple[int, Union[dict, str, bytes]]: _description_
        """
        params = {**kwargs}
        for alias, name in (("cluster_id", "id"), ("tenant_id", "tenantID")):
            if alias in params:
                if name in params:
                    raise ValueError(f"Specify either {alias} or {name}")
                params[name] = params.pop(alias)
        return self._make_request("GET", "events/clusters", params=params)

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

    @staticmethod
    def epoch_to_iso8601(epoch_time: int) -> str:
        """
        Convert epoch timestamp to ISO 8601 format
        Examples:
            >>> epoch_to_iso8601(1630894200)
            '2021-09-06T02:10:00Z'
        """
        return datetime.fromtimestamp(epoch_time, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
