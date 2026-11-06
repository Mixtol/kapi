import json
import logging
import subprocess
import sys
import warnings
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import requests

from kuma import APIError, RestClient
from tests.test_api_errors import make_response


@pytest.mark.parametrize(
    "url,expected",
    [
        ("example.invalid", "https://example.invalid:7223"),
        (" https://example.invalid/ ", "https://example.invalid:7223"),
        ("http://example.invalid:8080/proxy/", "http://example.invalid:8080/proxy"),
        ("https://example.invalid/api/v3/", "https://example.invalid:7223"),
        ("https://example.invalid/proxy/api/v3", "https://example.invalid:7223/proxy"),
        ("https://[::1]", "https://[::1]:7223"),
        ("https://[::1]:8443/", "https://[::1]:8443"),
    ],
)
def test_url_normalization(url, expected):
    with RestClient(url, "test-token") as client:
        assert client.url == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        " ",
        "https://",
        "ftp://example.invalid",
        "https://user:pass@example.invalid",
        "https://example.invalid?q=1",
        "https://example.invalid/#x",
        "https://example.invalid:70000",
        "https://example.invalid:0",
        "https://bad host",
    ],
)
def test_bad_urls_fail_before_network(url):
    with pytest.raises(ValueError):
        RestClient(url, "test-token")


@pytest.mark.parametrize(
    "timeout", [0, -1, False, (1,), (1, 0), float("nan"), float("inf"), "30", None]
)
def test_invalid_timeouts(timeout):
    with pytest.raises(ValueError):
        RestClient("example.invalid", "test-token", timeout=timeout)


def test_tls_configuration_is_used_and_warnings_are_not_disabled(tmp_path, monkeypatch):
    ca = tmp_path / "ca.pem"
    ca.write_text("test fixture")
    before = list(warnings.filters)
    for verify in [True, False, ca]:
        with RestClient(
            "example.invalid", "test-token", verify=verify, timeout=(2, 7)
        ) as client:
            request = Mock(return_value=make_response("{}", 200))
            monkeypatch.setattr(client.session, "request", request)
            client.users.whoami()
            expected = str(ca) if verify == ca else verify
            assert request.call_args.kwargs["verify"] == expected
            assert client.session.verify == expected
            assert request.call_args.kwargs["timeout"] == (2, 7)
            assert request.call_args.kwargs["allow_redirects"] is False
    assert warnings.filters == before
    with pytest.raises(ValueError, match="CA"):
        RestClient("example.invalid", "test-token", verify=tmp_path / "missing.pem")


@pytest.mark.parametrize(
    "endpoint,flag",
    [
        ("activeLists/import", "clear"),
        ("contextTables/import", "clear"),
        ("alerts", "withEvents"),
        ("alerts", "withAffected"),
        ("services", "paired"),
        ("tenants", "main"),
    ],
)
@pytest.mark.parametrize("value", [False, True, "false", "true", 0, 1, None])
def test_presence_flags_do_not_turn_false_into_true(monkeypatch, endpoint, flag, value):
    with RestClient("example.invalid", "test-token") as client:
        request = Mock(return_value=make_response("{}", 200))
        monkeypatch.setattr(client.session, "request", request)
        client._make_request("GET", endpoint, params={flag: value})
        actual = request.call_args.kwargs["params"]
        if value in (True, "true", 1):
            assert actual == {flag: ""}
        else:
            assert actual == {}


def test_parameter_encoding_and_headers(monkeypatch):
    with RestClient("example.invalid", "test-token") as client:
        request = Mock(return_value=make_response("{}", 200))
        monkeypatch.setattr(client.session, "request", request)
        client.users.search(excludeDisabled=False, tenant=["a", "b"])
        assert request.call_args.kwargs["params"] == {
            "excludeDisabled": "false",
            "tenant": ["a", "b"],
        }
        assert client.session.headers["Authorization"] == "Bearer test-token"
        client.users.get("a/b ?#")
        assert request.call_args.kwargs["url"].endswith("users/id/a%2Fb%20%3F%23")


def test_relative_ca_path_survives_working_directory_change(tmp_path, monkeypatch):
    ca = tmp_path / "ca.pem"
    ca.write_text("test fixture")
    monkeypatch.chdir(tmp_path)
    with RestClient("example.invalid", "test-token", verify="ca.pem") as client:
        monkeypatch.chdir(tmp_path.parent)
        request = Mock(return_value=make_response("{}", 200))
        monkeypatch.setattr(client.session, "request", request)
        client.users.whoami()
        assert request.call_args.kwargs["verify"] == str(ca)


@pytest.mark.parametrize(
    "body,ctype,status,expected",
    [
        ("", "application/json", 204, b""),
        ("", "application/json", 202, b""),
        ('{"ok":true}', "application/problem+json", 200, {"ok": True}),
    ],
)
def test_empty_and_json_suffix_responses_are_closed(
    monkeypatch, body, ctype, status, expected
):
    response = make_response(body, status, ctype)
    response.close = Mock()
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(client.session, "request", Mock(return_value=response))
        assert client.users.whoami() == (status, expected)
    response.close.assert_called_once()


def test_invalid_success_json_preserves_cause_and_closes(monkeypatch):
    response = make_response("{", 200)
    response.close = Mock()
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(client.session, "request", Mock(return_value=response))
        with pytest.raises(APIError) as caught:
            client.users.whoami()
    assert caught.value.status_code == 200
    assert isinstance(caught.value.__cause__, ValueError)
    response.close.assert_called_once()


def test_public_import_does_not_configure_root_logging_or_load_private():
    code = "import logging, sys, requests; before=list(logging.getLogger().handlers); import kuma; assert logging.getLogger().handlers == before; assert 'kuma.private' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True, timeout=15)


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "1970-01-01T00:00:00Z"),
        (0.5, "1970-01-01T00:00:00.500000Z"),
        (
            datetime(2026, 11, 5, 3, tzinfo=timezone(timedelta(hours=3))),
            "2026-11-05T00:00:00Z",
        ),
        ("2026-11-05T03:00:00+03:00", "2026-11-05T03:00:00+03:00"),
    ],
)
def test_time_is_timezone_aware(value, expected):
    assert RestClient.format_time(value) == expected


@pytest.mark.parametrize("value", [True, datetime(2026, 11, 5), "2026-11-05T12:00:00"])
def test_ambiguous_timestamps_are_rejected(value):
    with pytest.raises(ValueError):
        RestClient.format_time(value)
