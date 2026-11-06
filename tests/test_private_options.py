import json
import logging
from unittest.mock import Mock

import pytest
import requests

from kuma import PrivateClient


def fake_session(monkeypatch):
    session = Mock()
    session.cookies = requests.cookies.cookiejar_from_dict({"XSRF-TOKEN": "test-xsrf"})
    session.headers = {}
    session.verify = True
    session.post.return_value.status_code = 200
    session.put.return_value.status_code = 204
    monkeypatch.setattr("kuma.private.PrivateSession", Mock(return_value=session))
    return session


@pytest.mark.parametrize(
    "version", ["2.1.0", "3.4", "3.4.1.53", "4.0", "4.1", "4.1.2.100", "4.2"]
)
def test_private_login_keeps_version_and_uses_its_tenant_route(monkeypatch, version):
    session = fake_session(monkeypatch)
    user = {"id": "user", "tenants": {"tenant": {}}}
    session.get.side_effect = lambda url, **kwargs: Mock(
        status_code=200,
        json=Mock(return_value=user if url.endswith("/whoami") else [{"id": "tenant"}]),
    )
    logger = Mock()
    client = PrivateClient(
        "example.invalid", "user", "password", version=version, logger=logger
    )
    assert client.version == version
    if version.startswith("4.1"):
        assert client.contract_version == "4.0"
    assert client.logger is logger
    if version.startswith("2"):
        assert session.post.call_args.args[0].endswith("/users/tenants/select")
        assert json.loads(session.post.call_args.kwargs["data"]) == {"ids": ["tenant"]}
        session.put.assert_not_called()
    else:
        assert session.put.call_args.args[0].endswith(
            "/standaloneUsers/user/selectTenants"
        )
        assert json.loads(session.put.call_args.kwargs["data"]) == {
            "tenantIDs": ["tenant"]
        }
    client.initialize_session()
    assert client.version == version


def test_private_restored_session_and_positional_arguments(monkeypatch):
    session = fake_session(monkeypatch)
    logger = Mock()
    saved = {
        "cookies": {"session": "saved"},
        "headers": {"X-Test": "saved"},
        "xsrf_token": "saved-xsrf",
    }
    client = PrivateClient("example.invalid", "user", "password", saved, "3.4", logger)
    assert client.version == "3.4"
    assert client.logger is logger
    assert session.cookies["session"] == "saved"
    assert session.headers["X-XSRF-TOKEN"] == "saved-xsrf"
    assert client.get_session_data()["version"] == "3.4"
    session.post.assert_not_called()


def test_private_loggers_are_isolated_between_clients(monkeypatch):
    fake_session(monkeypatch)
    saved = {"cookies": {}, "headers": {}, "xsrf_token": "saved-xsrf"}
    first_logger, second_logger = Mock(), Mock()
    first = PrivateClient(
        "example.invalid", "user", "password", saved, "3.4", first_logger
    )
    second = PrivateClient(
        "example.invalid", "user", "password", saved, "3.4", second_logger
    )
    first.session.get.side_effect = requests.ConnectionError("offline")
    with pytest.raises(ConnectionError):
        first.whoami()
    first_logger.error.assert_called_once()
    second_logger.error.assert_not_called()
    assert second.logger is second_logger


def test_private_default_and_legacy_factory_remain_usable(monkeypatch):
    fake_session(monkeypatch)
    monkeypatch.setattr(PrivateClient, "private_select_tenant", Mock())
    client = PrivateClient("example.invalid", "user", "password")
    assert client.version == "2.1.0"
    assert client.logger is logging.getLogger("kuma._logging")
    factory_client = PrivateClient.create_session("example.invalid", "user", "password")
    assert factory_client.version == "2.1.0"
