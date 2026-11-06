from copy import deepcopy
from unittest.mock import Mock

import pytest

from kuma import APIError, PrivateClient


@pytest.mark.parametrize("version,wrapped", [("3.4", False), ("4.2", True)])
def test_bulk_alerting_updates_only_requested_tenant_and_keeps_original(
    version, wrapped, monkeypatch
):
    with PrivateClient(
        "example.invalid",
        "user",
        "password",
        {"cookies": {}, "headers": {}, "xsrf_token": "test-xsrf"},
        version,
    ) as client:
        rows = [
            {"id": "settings-a", "tenantID": "a"},
            {"id": "settings-b", "tenantID": "b"},
        ]
        payload = {
            "segmentationRules": [
                {"name": "chosen", "correlationRuleIDs": ["old"]},
                {"name": "untouched", "correlationRuleIDs": []},
            ]
        }
        before = deepcopy(payload)
        calls = []

        def result(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if endpoint == "settings/":
                return 200, {"result": rows} if wrapped else rows
            if method == "GET":
                return 200, payload
            assert endpoint == "settings/id/settings-b"
            assert kwargs["json"]["segmentationRules"] == [
                {"name": "chosen", "correlationRuleIDs": ["old", "new"]},
                {"name": "untouched", "correlationRuleIDs": []},
            ]
            return 200, {}

        monkeypatch.setattr(client, "_result", result)
        assert list(
            client.iter_update_alerting(["b"], ["new"], rule_name="chosen")
        ) == [{"tenantID": "b", "settingsID": "settings-b", "status": 200}]
        assert payload == before
        assert len(calls) == 3
        with pytest.raises(ValueError, match="доступны не для всех"):
            list(client.iter_update_alerting(["missing"], ["new"]))
        assert len(calls) == 4
