import hashlib
import json
from itertools import islice

from kuma.errors import APIError
from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPIAlerts(KumaRestAPIModule):
    """Methods for Alerts."""

    def search(self, **kwargs) -> APIResult:
        """
        Searching alerts from KUMA
        Args:
            page (int): Listing page of result (250 alerts per page)
            id (List[str]): Search for specified alerts
            tenantID (str): Tenant filter
            name (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            timestampField (str): lastSeen|firstSeen for from-to order
            from (str): RFC3339 Lower limit
            to (str): RFC3339 Upper limit
            status (str): new|assigned|closed|escalated
            withEvents (str): Include normalized JSON (HEAVY)
            withAffected (str): Include assets and accounts

        """
        params = {
            **kwargs,
        }
        return self._make_request("GET", "alerts", params=params)

    def assign(self, alerts_ids: list, user_id: str) -> APIResult:
        """Alert assign method
        Args:
            alerts_ids (list): Alerts UUID list
            user_id (str): User UUID
        """
        json = {"ids": alerts_ids, "userId": user_id}
        return self._make_request("POST", "alerts/assign", json=json)

    def close(self, alert_id: str, reason: str = "responded") -> APIResult:
        """
        Close alerts with reason.
        Args:
            alert_id (str): Alert UUID
            reason (str): responded|incorrect data|incorrect correlation rule
        """
        json = {"id": alert_id, "reason": reason}
        return self._make_request("POST", "alerts/close", json=json)

    def comment(self, alert_id: str, comment: str) -> APIResult:
        """
        Create a comment in alert.
        Args:
            alert_id (str): Alert UUID
            comment (str): Message for your SOC team
        """
        json = {"alertID": alert_id, "comment": comment}
        return self._make_request("POST", "alerts/comment", json=json)

    def get(self, alert_id: str) -> APIResult:
        """Gets specified alert data
        Args:
            alert_id (str): Alert UUID
        """
        return self._make_request("GET", f"alerts/id/{self._path(alert_id)}")

    def link_event(
        self,
        alert_id: str,
        cluster_id: str,
        event_id: str,
        event_timestamp: int,
        comment: str = "",
    ) -> APIResult:
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
        return self._make_request("POST", f"alerts/link-event", json=json)

    def unlink_event(
        self,
        alert_id: str,
        event_id: str,
    ) -> APIResult:
        """Unlinks an event from an alert
        Args:
            alert_id (str): Alert UUID
            event_id (str): Event UUID to unlink
        """
        json = {"alertID": alert_id, "eventID": event_id}
        return self._make_request("POST", f"alerts/unlink-event", json=json)

    # Extended

    def iter_search(self, *, page: int = 1, **kwargs):
        """Yield alerts page by page without retaining previous pages."""
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        seen_pages = set()
        while True:
            status, items = self.search(page=page, **kwargs)
            if not isinstance(items, list):
                raise APIError(
                    "Expected an array of alerts",
                    status_code=status,
                    response_data=items,
                )
            if items:
                identities = sorted(
                    json.dumps(
                        item.get("id", item) if isinstance(item, dict) else item,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for item in items
                )
                signature = hashlib.sha256("\n".join(identities).encode()).digest()
                if signature in seen_pages:
                    raise APIError(
                        "Alerts pagination repeated a page", status_code=status
                    )
                seen_pages.add(signature)
            yield from items
            if len(items) < 250:
                break
            page += 1

    def searchp(self, limit: int = 250, **kwargs):
        """Collect up to limit alerts, starting at the requested page (default 1)."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        page = kwargs.pop("page", 1)
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        return 200, list(islice(self.iter_search(page=page, **kwargs), limit))
