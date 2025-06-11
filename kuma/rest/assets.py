from typing import Dict, List, Tuple

from kuma.rest._base import KumaRestAPIModule


class KumaRestAPIAssets(KumaRestAPIModule):
    """Methods for Assets."""
    def search(self, **kwargs) -> Tuple[int, List | str]:
        """
        Searching assets by provided filter.

        Args:
            page (int): Assets page number
            id (str): Asset UUID
            tenantID (str): Tenant UUID filter
            name (str): Case-insensitive regex filter for Name
            fqdn (str): Asset FQDN filter
            ip (str): Case-insensitive regex filter for IP
            mac (str): Case-insensitive regex filter for MAC
        """
        return self._make_request("GET", "assets", params=kwargs)

    def delete(
        self,
        assets_fqdns: List[str],
        assets_ids: List[str],
        assets_ips: List[str],
        tenant_id: str,
    ) -> Tuple[int, Dict | str]:
        """
        Method for deleting tenant assets.

        Args:
            assets_fqdns (List[str]): FQDNs list
            assets_ids (List[str]): Assets IDs list
            assets_ips (List[str]): Assets IPAddreses list
            tenant_id (str): Assets tenantID
        """
        json = {
            "fqdns": assets_fqdns,
            "ids": assets_ids,
            "ipAddresses": assets_ips,
            "tenantID": tenant_id,
        }
        return self._make_request("POST", "assets/delete", json=json)

    def create(self, assets: List[Dict], tenant_id: str) -> Tuple[int, Dict | str]:
        """
        Import/create assets from JSON, see examples.

        Args:
            assets (list): List of assets JSON
            tenant_id (str): Assets tenantID
        """
        json = {"assets": assets, "tenantID": tenant_id}
        return self._make_request("POST", "assets/import", json=json)
