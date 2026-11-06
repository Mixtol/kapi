import json
import warnings
from unittest.mock import Mock

import pytest

from kuma import APIError, RestClient
from tests.test_api_errors import make_response


def test_default_is_latest_supported_version_without_network(monkeypatch):
    request = Mock()
    monkeypatch.setattr("requests.Session.request", request)
    with pytest.warns(UserWarning, match=r"version was not specified.*4\.2") as caught:
        with RestClient("example.invalid", "test-token") as client:
            assert client.version == "4.2"
    assert len(caught) == 1
    assert caught[0].filename == __file__
    request.assert_not_called()


@pytest.mark.parametrize("version", ["3.4", "4.0", "4.1", "4.2"])
def test_explicit_release_does_not_warn(version):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with RestClient("example.invalid", "test-token", version=version):
            pass
    assert not caught


def test_warning_as_error_does_not_leave_an_open_session(monkeypatch):
    session = Mock()
    monkeypatch.setattr("requests.Session", session)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        with pytest.raises(UserWarning, match="version was not specified"):
            RestClient("example.invalid", "test-token")
    session.assert_not_called()


@pytest.mark.parametrize(
    "version,normalized,password_field",
    [
        ("3.4", "3.4", "password"),
        ("3.4.1.53", "3.4", "password"),
        ("4.0.1.100", "4.0", "newPassword"),
        ("4.1", "4.1", "newPassword"),
        ("4.1.2.100", "4.1", "newPassword"),
        ("4.2", "4.2", "newPassword"),
        (" 4.2.0.999 ", "4.2", "newPassword"),
    ],
)
def test_selected_release_controls_requests(
    monkeypatch, version, normalized, password_field
):
    with RestClient("example.invalid", "test-token", version=version) as client:
        send = Mock(return_value=make_response('{"fileID":"export"}', 200))
        monkeypatch.setattr(client.session, "request", send)
        assert client.version == normalized
        assert client.contract_version == ("4.0" if normalized == "4.1" else normalized)
        assert client.resources.export(
            ["resource"], "tenant", password="chosen-password"
        ) == (200, {"fileID": "export"})
        assert send.call_args.kwargs["json"] == {
            "ids": ["resource"],
            password_field: "chosen-password",
            "tenantID": "tenant",
        }


@pytest.mark.parametrize(
    "version", ["3", "3.4.", "v3.4", "3.4-rc1", "3.3", "4.3", "9.0"]
)
def test_invalid_or_unsupported_release_fails_before_session_creation(
    monkeypatch, version
):
    session = Mock()
    monkeypatch.setattr("requests.Session", session)
    with pytest.raises(ValueError):
        RestClient("example.invalid", "test-token", version=version)
    session.assert_not_called()


@pytest.mark.parametrize("version", [None, 3.4, 4, True])
def test_release_must_be_a_string(version):
    with pytest.raises(TypeError):
        RestClient("example.invalid", "test-token", version=version)


def test_original_positional_constructor_arguments_are_preserved():
    logger = Mock()
    with RestClient(
        "example.invalid", "test-token", False, (2, 7), logger, version="3.4"
    ) as client:
        assert client.logger is logger
        assert client.timeout == (2, 7)
        assert client.verify is False
        assert client.version == "3.4"


@pytest.mark.parametrize("private", [False, True])
def test_41_fallback_preserves_selected_and_detected_versions(monkeypatch, private):
    from kuma import PrivateClient

    services = [{"kind": "core", "version": "4.1.2.100"}]
    if private:
        from tests.test_private_transport import SAVED

        client = PrivateClient(
            "example.invalid", "user", "password", SAVED, "4.1.2.100"
        )
        monkeypatch.setattr(client, "iter_services", lambda: iter(services))
        selected = "4.1.2.100"
        assert client.get_session_data()["version"] == selected
    else:
        client = RestClient("example.invalid", "test-token", version="4.1.2.100")
        monkeypatch.setattr(
            client.services, "search", Mock(return_value=(200, services))
        )
        selected = "4.1"
    with client:
        assert client.get_version() == "4.1"
        assert client.version == selected
        assert client.contract_version == "4.0"


@pytest.mark.parametrize("use_base", [False, True])
@pytest.mark.parametrize("version,expected", [("3.4.1.53", "3.4"), ("", "4.2")])
def test_legacy_positional_version_and_logger(use_base, version, expected):
    from kuma.rest._base import KumaRestAPIBase

    cls = KumaRestAPIBase if use_base else RestClient
    logger = Mock()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with cls(
            "example.invalid", "test-token", True, (5, 60), logger, version
        ) as client:
            assert client.version == expected
            assert client.logger is logger
            assert client.timeout == (5, 60)
    assert len(caught) == (1 if version == "" else 0)
    if caught:
        assert caught[0].category is UserWarning


@pytest.mark.parametrize("version", ["3.4", "4.0", "4.1", "4.2"])
def test_get_version_reads_core_and_does_not_change_selected_release(
    monkeypatch, version
):
    with RestClient("example.invalid", "test-token", version=version) as client:
        send = Mock(
            return_value=make_response(
                json.dumps(
                    [
                        {"kind": "collector", "version": "4.2.0.9"},
                        {"kind": "core", "version": "3.4.1.53"},
                        {"kind": "core", "version": "3.4.0.551"},
                    ]
                ),
                200,
            )
        )
        monkeypatch.setattr(client.session, "request", send)
        assert client.get_version() == "3.4"
        assert client.version == version
        assert send.call_args.kwargs["method"] == "GET"
        assert send.call_args.kwargs["url"].endswith("/api/v3/services")
        assert send.call_args.kwargs["params"] == {"page": 1}


def test_get_version_reads_later_pages(monkeypatch):
    with RestClient("example.invalid", "test-token") as client:
        pages = [
            [
                {"id": str(i), "kind": "agent", "version": "3.0.3.19"}
                for i in range(250)
            ],
            [{"id": "core", "kind": "core", "version": "4.0.1.100"}],
        ]
        search = Mock(side_effect=[(200, page) for page in pages])
        monkeypatch.setattr(client.services, "search", search)
        assert client.get_version() == "4.0"
        assert [call.kwargs for call in search.call_args_list] == [
            {"page": 1},
            {"page": 2},
        ]


@pytest.mark.parametrize(
    "services,message",
    [
        ([], "not visible"),
        ([{"kind": "collector", "version": "3.4.1.53"}], "not visible"),
        ([{"kind": "core"}], "invalid version"),
        ([{"kind": "core", "version": ""}], "invalid version"),
        ([{"kind": "core", "version": "unknown"}], "invalid version"),
        (
            [{"kind": "core", "version": "3.4"}, {"kind": "core", "version": "4.2"}],
            "different",
        ),
        ({"services": []}, "Unexpected"),
        ([None], "Unexpected"),
    ],
)
def test_get_version_does_not_guess(monkeypatch, services, message):
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(
            client.services, "search", Mock(return_value=(200, services))
        )
        with pytest.raises(APIError, match=message):
            client.get_version()


def test_get_version_can_report_a_new_unsupported_release(monkeypatch):
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(
            client.services,
            "search",
            Mock(return_value=(200, [{"kind": "core", "version": "9.9.1.100"}])),
        )
        assert client.get_version() == "9.9"
        assert client.version == "4.2"


def test_get_version_propagates_access_denied(monkeypatch):
    error = APIError("forbidden", 403)
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(client.services, "search", Mock(side_effect=error))
        with pytest.raises(APIError) as caught:
            client.get_version()
        assert caught.value is error


def test_get_version_stops_if_server_ignores_pagination(monkeypatch):
    services = [{"id": str(i), "kind": "agent"} for i in range(250)]
    with RestClient("example.invalid", "test-token") as client:
        search = Mock(return_value=(200, services))
        monkeypatch.setattr(client.services, "search", search)
        with pytest.raises(APIError, match="repeated a page"):
            client.get_version()
        assert search.call_count == 2


@pytest.mark.parametrize(
    "version,format",
    [("3.4", "internal"), ("4.0", "csv"), ("4.1", "csv"), ("4.2", "tsv")],
)
def test_context_export_format_depends_on_release(monkeypatch, version, format):
    with RestClient("example.invalid", "test-token", version=version) as client:
        send = Mock(return_value=make_response(b"", 200))
        monkeypatch.setattr(client.session, "request", send)
        _, stream = client.context_tables.export("correlator", "table", format=format)
        stream.close()
        params = send.call_args.kwargs["params"]
        if version == "3.4":
            assert "format" not in params
        else:
            assert params["format"] == format


@pytest.mark.parametrize("format", ["csv", "tsv"])
def test_unsupported_context_format_fails_before_network(monkeypatch, format):
    with RestClient("example.invalid", "test-token", version="3.4") as client:
        send = Mock()
        monkeypatch.setattr(client.session, "request", send)
        with pytest.raises(ValueError, match="3.4"):
            client.context_tables.export("correlator", "table", format=format)
        send.assert_not_called()
