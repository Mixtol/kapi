from typing import Any, Dict, List, Optional, Tuple, Union


class KumaRestAPIAssets:
    """
    Методы для работы с активами
    """

    def __init__(self, base):
        self._base = base

    def search(self, **kwargs) -> Tuple[int, List | str]:
        """Searchin assets by provided filter
        Args:
            page (int): Assets page number
            id (str): Asset UUID
            tenantID (str): Tenant UUID filter
            name (str): Case-insensitive regex filter for Name
            fqdn (str): Asset FQDN filter
            ip (str): Case-insensitive regex filter for IP
            mac (str): Case-insensitive regex filter for MAC
        """
        return self._base._make_request("GET", "assets", params=kwargs)

    def delete(
        self,
        assets_fqdns: List[str],
        assets_ids: List[str],
        assets_ips: List[str],
        tenant_id: str,
    ) -> Tuple[int, Dict | str]:
        """Method for deleting tenant assets
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
        return self._base._make_request("POST", "assets/delete", json=json)

    def create(self, assets: List[Dict], tenant_id: str) -> Tuple[int, Dict | str]:
        """Import\Create assets fron JSON, see examples
        Args:
            assets (list): List of assets JSON
            tenant_id (str): Assets tenantID
        """
        json = {"assets": assets, "tenantID": tenant_id}
        return self._base._make_request("POST", "assets/import", json=json)
