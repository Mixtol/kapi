from unittest.mock import Mock

import pytest

from kuma import RestClient
from tests.test_api_errors import make_response

EXPORTS = [
    ("resources.export", (["resource"], "tenant", "chosen-password")),
    ("active_lists.export", ("correlator", "list")),
    ("context_tables.export", ("correlator", "table")),
    ("settings.export_extendedfields", ()),
]


def resolve(client, method):
    module, name = method.split(".")
    return getattr(getattr(client, module), name)


@pytest.mark.parametrize("method,args", EXPORTS)
@pytest.mark.parametrize("timeout", [None, 90, (5, 120)])
def test_export_timeout_overrides_one_request_only(monkeypatch, method, args, timeout):
    with RestClient(
        "example.invalid", "test-token", timeout=(2, 30), version="3.4"
    ) as client:
        send = Mock(side_effect=lambda **kwargs: make_response("{}", 200))
        monkeypatch.setattr(client.session, "request", send)
        _, result = resolve(client, method)(*args, timeout=timeout)
        if hasattr(result, "close"):
            result.close()
        options = send.call_args.kwargs
        assert options["timeout"] == ((2, 30) if timeout is None else timeout)
        assert "timeout" not in options.get("params", {})
        assert "timeout" not in options.get("json", {})
        assert client.timeout == (2, 30)
        client.users.whoami()
        assert send.call_args.kwargs["timeout"] == (2, 30)


@pytest.mark.parametrize("method,args", EXPORTS)
@pytest.mark.parametrize("timeout", [0, -1, (5, 0)])
def test_invalid_export_timeout_fails_before_network(
    monkeypatch, method, args, timeout
):
    with RestClient("example.invalid", "test-token", version="3.4") as client:
        send = Mock()
        monkeypatch.setattr(client.session, "request", send)
        with pytest.raises(ValueError, match="Timeouts"):
            resolve(client, method)(*args, timeout=timeout)
        send.assert_not_called()
