from typing import Any, Dict, List, Optional, Tuple, Union


class KumaRestAPIAlerts:
    """
    Методы для работы с алертами
    """

    def __init__(self, base):
        self._base = base

    def search(self, **kwargs) -> Tuple[int, bytes | str]:
        """
        Searching alerts from KUMA
        Args:
            page (int): Listing page of result (250 alerts per page)
            id (List[str]): Search for specified alerts
            tenantID (str): Tenant filter
            name (str): Case-insensetine name regex filter
            timestampField (str): lastSeen|firtsSeen for from-to order
            from (str): RFC3339 Lower limit
            to (str): RFC3339 Upper limit
            status (str): new|assigned|closed|escalated
            withEvents (str): Include normalized JSON (HEAVY)
            withAffected (str): Include assets and accounts

        """
        params = {
            **kwargs,
        }
        return self._base._make_request("GET", "alerts", params=params)

    def assign(self, alerts_ids: list, user_id: str) -> Tuple[int, bytes | str]:
        """Alert assign method
        Args:
            alerts_ids (list): Alerts UUID list
            user_id (str): User UUID
        """
        json = {"ids": alerts_ids, "userId": user_id}
        return self._base._make_request("POST", "alerts/assign", json=json)

    def close(self, alert_id: str, reason: str = "responded") -> Tuple[int, Dict]:
        """
        Close alerts with reason.
        Args:
            alert_id (str): Alert UUID
            reason (str): responded|incorrect data|incorrect correlation rule
        """
        json = {"id": alert_id, "reason": reason}
        return self._base._make_request("POST", "alerts/close", json=json)

    def comment(self, alert_id: str, comment: str) -> Tuple[int, Dict]:
        """
        Create a comment in alert.
        Args:
            alert_id (str): Alert UUID
            comment (str): Message for your SOC team
        """
        json = {"alertID": alert_id, "comment": comment}
        return self._base._make_request("POST", "alerts/comment", json=json)

    def get(self, alert_id: str) -> Tuple[int, Dict | str]:
        """Gets specified alert data
        Args:
            alert_id (str): Alert UUID
        """
        return self._base._make_request("GET", f"alerts/id/{alert_id}")

    def link_event(
        self,
        alert_id: str,
        cluster_id: str,
        event_id: str,
        event_timestamp: int,
        comment: str,
    ) -> Tuple[int, Dict | str]:
        """Linking event from storage to alert
        Args:
            alert_id (str): Alert UUID
            cluster_id (str): Event storage cluster UUID
            event_id (str): Events to link UUID
            event_timestamp (int): Event timestamp epoch
            comment (str): Comment message for alert
        """
        json = {
            "alertID": alert_id,
            "clusterID": cluster_id,
            "eventID": event_id,
            "eventTimestamp": event_timestamp,
            "comment": comment,
        }
        return self._base._make_request("POST", f"alerts/link-event", json=json)

    def unlink_event(
        self,
        alert_id: str,
        event_id: str,
    ) -> Tuple[int, Dict | str]:
        """Unlinks event from  alert
        Args:
            alert_id (str): Alert UUID
            event_id (str): Event UUID to unlink
        """
        json = {"alertID": alert_id, "eventID": event_id}
        return self._base._make_request("POST", f"alerts/unlink-event", json=json)

    ### ext

    def search(self, **kwargs) -> Tuple[int, bytes | str]:
        """
        Searching alerts from KUMA
        Args:
            page (int): Listing page of result (250 alerts per page)
            id (List[str]): Search for specified alerts
            tenantID (str): Tenant filter
            name (str): Case-insensetine name regex filter
            timestampField (str): lastSeen|firtsSeen for from-to order
            from (str): RFC3339 Lower limit
            to (str): RFC3339 Upper limit
            status (str): new|assigned|closed|escalated
            withEvents (str): Include normalized JSON (HEAVY)
            withAffected (str): Include assets and accounts
        """
        params = {
            **kwargs,
        }
        return self._base._make_request("GET", "alerts", params=params)

    # Extended

    def searchp(self, limit: int = 250, **kwargs) -> Tuple[int, list | str]:
        """
        Search with pagination, if more 250 is needed
        Args:
            limit (int): Nubmer of returner alerts
            id (List[str]): Search for specified alerts
            tenantID (str): Tenant filter
            name (str): Case-insensetine name regex filter
            timestampField (str): lastSeen|firtsSeen for from-to order
            from (str): RFC3339 Lower limit
            to (str): RFC3339 Upper limit
            status (str): new|assigned|closed|escalated
            withEvents (str): Include normalized JSON (HEAVY)
            withAffected (str): Include assets and accounts
        """
        all_alerts = []
        current_page = 1
        while True:
            params = {
                "page": current_page,
                **kwargs,
            }
            status_code, data = self._base._make_request("GET", "alerts", params=params)
            if status_code != 200:
                return status_code, data
            items = data if isinstance(data, list) else [data]
            all_alerts.extend(items)

            if len(all_alerts) >= limit or len(items) < 250:
                break
            current_page += 1
        return 200, all_alerts[:limit]
