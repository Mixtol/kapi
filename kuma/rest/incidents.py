from typing import List

from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPIIncidents(KumaRestAPIModule):
    """Methods for Incidents."""

    def search(self, **kwargs) -> APIResult:
        """
        Searching alerts from KUMA
        Args:
            page (int): Listing page of result (250 alerts per page)
            id (List[str]): Search for specified id
            tenantID (str): Tenant filter
            name (str): Case-insensitive filter (regex in 3.4, substring in 4.x)
            from (str): RFC3339 Lower limit
            to (str): RFC3339 Upper limit
            timestampField (str): lastSeen|firstSeen for from-to order
            status (str): open|assigned|closed
            search (str): case-insensitive filter (regex in 3.4, substring in 4.x) search in most used fields
        """
        params = {
            **kwargs,
        }
        return self._make_request("GET", "incidents", params=params)

    def assign(self, incidents_ids: list, user_id: str) -> APIResult:
        """Alert assign method
        Args:
            incidents_ids (list): Incidents INC names list
            user_id (str): User UUID
        """
        json = {"incidentIDs": incidents_ids, "assignee": user_id}
        return self._make_request("POST", "incidents/assign", json=json)

    def close(self, incidents_ids: List[str], resolution: int) -> APIResult:
        """
        Close alerts with reason.
        Args:
            incidents_ids (list): Incidents INC names list
            resolution (int): 1 Confirmed|0 Not confirmed
        """
        if isinstance(incidents_ids, str):
            incidents_ids = [incidents_ids]
        if (
            isinstance(resolution, bool)
            or not isinstance(resolution, int)
            or resolution not in (0, 1)
        ):
            raise ValueError("resolution must be 0 (not confirmed) or 1 (confirmed)")
        json = {"incidentIDs": incidents_ids, "resolution": resolution}
        return self._make_request("POST", "incidents/close", json=json)

    def comment(self, incident_id: str, comment: str) -> APIResult:
        """
        Create a comment in alert.
        Args:
            incident_id (str): Incident INC id
            comment (str): Message for your SOC team
        """
        json = {"id": incident_id, "comment": comment}
        return self._make_request("POST", "incidents/comment", json=json)

    def create(self, incident: dict, calc_priority: bool = False) -> APIResult:
        """
        Creating new incident from JSON data
        Args:
            incident (dict): Incident JSON data, see examples
            calc_priority (str): Copy priority from alert
        """
        params = {"calcPriority": calc_priority}
        return self._make_request(
            "POST", f"incidents/create", json=incident, params=params
        )

    def get(self, incident_id: str) -> APIResult:
        """Gets specified alert data
        Args:
            incident_id (str): Incident INC id
        """
        return self._make_request("GET", f"incidents/id/{self._path(incident_id)}")

    def link_alert(self, incident_id: str, alerts_ids: List[str]) -> APIResult:
        """Linking event from storage to alert
        Args:
            incident_id (str): Incident INC id
            alerts_ids (str): List of alert UUID to link
        """
        json = {"incidentID": incident_id, "alertIDs": alerts_ids}
        return self._make_request("POST", f"incidents/link", json=json)

    def unlink_alert(self, incident_id: str, alerts_ids: List[str]) -> APIResult:
        """Linking event from storage to alert
        Args:
            incident_id (str): Incident INC id
            alerts_ids (str): List of alert UUID to unlink
        """
        json = {"incidentID": incident_id, "alertIDs": alerts_ids}
        return self._make_request("POST", f"incidents/unlink", json=json)
