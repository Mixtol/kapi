import json
from unittest.mock import Mock

import pytest
import requests

from kuma import RestClient
from kuma.rest.errors import APIError


def make_response(body, status=400, content_type="application/json"):
    response = requests.Response()
    response.status_code = status
    response.encoding = "utf-8"
    response.headers["Content-Type"] = content_type
    response._content = body.encode("utf-8") if isinstance(body, str) else body
    response._content_consumed = True
    return response


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"mustChangePassword": True, "authBlocked": False}, "password change"),
        (
            {"mustChangePassword": False, "authBlocked": True},
            "authentication is blocked",
        ),
        (
            {"mustChangePassword": True, "authBlocked": True},
            "authentication is blocked",
        ),
    ],
)
def test_private_42_login_policy_error_is_readable(payload, message):
    body = json.dumps(payload)
    error = APIError.from_response(make_response(body))
    assert message in str(error)
    assert error.status_code == 400
    assert error.response_data == payload
    assert error.response_text == body


def test_42_error_string_is_readable_and_preserved():
    payload = {"error": "read file info: failed to lookup: ent: kfs_file not found"}
    body = json.dumps(payload)
    error = APIError.from_response(make_response(body, status=500))
    assert str(error) == "Bad response 500: " + payload["error"]
    assert error.response_data == payload
    assert error.response_text == body


@pytest.fixture
def client():
    with RestClient("https://example.invalid", "test-token", verify=True) as api:
        api.logger = Mock()
        yield api


def test_validation_error_is_readable_and_preserves_server_data(client, monkeypatch):
    payload = {
        "message": "validation error",
        "details": {
            "rows.229.0": "the number of characters must be between",
            "rows.5550.0": "the number of characters must be between",
        },
        "params": {
            "rows.229.0": {"from": "1", "to": "1024"},
            "rows.5550.0": {"from": "1", "to": "1024"},
        },
        "requestID": "server-request-id",
    }
    body = json.dumps(payload)
    monkeypatch.setattr(
        client.session, "request", Mock(return_value=make_response(body))
    )

    with pytest.raises(APIError) as caught:
        client.dictionaries.update("dictionary-id", "key,value\n,value\n")

    error = caught.value
    assert str(error) == (
        "Bad response 400: validation error\n"
        "rows.229.0: the number of characters must be between 1 and 1024\n"
        "rows.5550.0: the number of characters must be between 1 and 1024"
    )
    assert error.status_code == 400
    assert error.details == payload["details"]
    assert error.params == payload["params"]
    assert error.response_data == payload
    assert error.response_text == body
    client.logger.error.assert_called_once_with(str(error))


@pytest.mark.parametrize(
    "message, params, expected",
    [
        (
            "the number of characters must be between",
            {"from": 0, "to": 1024, "unit": "characters"},
            "the number of characters must be between 0 and 1024 (unit=characters)",
        ),
        (
            "the number of characters must be between",
            {"from": "1"},
            "the number of characters must be between (from=1)",
        ),
        ("must exceed limit", {"limit": 0}, "must exceed limit (limit=0)"),
        ("required", {}, "required"),
        ("required", None, "required"),
        ("required", "extra context", "required (params=extra context)"),
        ("required", [1, 2], "required (params=[1, 2])"),
        ("required", False, "required (params=false)"),
        (
            "Недопустимое значение",
            {"value": "текст"},
            "Недопустимое значение (value=текст)",
        ),
        ("invalid", {"allowed": ["a", "b"]}, 'invalid (allowed=["a", "b"])'),
        (["required", "invalid"], None, '["required", "invalid"]'),
        ({"child": "required"}, None, '{"child": "required"}'),
        (None, None, "null"),
    ],
)
def test_field_errors_keep_available_parameters(message, params, expected):
    payload = {
        "message": "validation error",
        "details": {"field": message},
        "params": {"field": params},
    }
    error = APIError.from_response(make_response(json.dumps(payload)))
    assert str(error) == f"Bad response 400: validation error\nfield: {expected}"
    assert error.response_data == payload


@pytest.mark.parametrize(
    "extra, expected_lines",
    [
        ({}, []),
        ({"details": None, "params": None}, []),
        ({"details": ["required", "invalid"]}, ['details: ["required", "invalid"]']),
        ({"details": "required"}, ["details: required"]),
        ({"details": False}, ["details: false"]),
        ({"params": {"limit": 1}}, ['params: {"limit": 1}']),
        (
            {"details": {"field": "required"}, "params": [1, 2]},
            ["field: required", "params: [1, 2]"],
        ),
        (
            {"details": {"field": "required"}, "params": {"other": {"limit": 1}}},
            ["field: required", 'params: {"other": {"limit": 1}}'],
        ),
    ],
)
def test_partial_or_unusual_error_shapes_do_not_hide_details(extra, expected_lines):
    payload = {"message": "validation error", **extra}
    error = APIError.from_response(make_response(json.dumps(payload)))
    assert str(error).splitlines() == [
        "Bad response 400: validation error",
        *expected_lines,
    ]
    assert error.details == payload.get("details")
    assert error.params == payload.get("params")


@pytest.mark.parametrize("content_type", ["application/json", "text/plain", ""])
def test_error_json_is_parsed_even_without_json_content_type(content_type):
    error = APIError.from_response(
        make_response('{"message": "forbidden"}', status=403, content_type=content_type)
    )
    assert str(error) == "Bad response 403: forbidden"
    assert error.status_code == 403


@pytest.mark.parametrize(
    "body, decoded",
    [
        ("proxy unavailable", None),
        ("<html>Bad Gateway</html>", None),
        ('{"message":', None),
        ("", None),
        ("null", None),
        ("false", False),
        ("[]", []),
        ('"server failure"', "server failure"),
        (
            '{"error": {"message": "unavailable"}}',
            {"error": {"message": "unavailable"}},
        ),
        ('{"message": null}', {"message": None}),
        ('{"message": {"unexpected": true}}', {"message": {"unexpected": True}}),
    ],
)
def test_unrecognized_errors_fall_back_to_original_body(
    client, monkeypatch, body, decoded
):
    monkeypatch.setattr(
        client.session, "request", Mock(return_value=make_response(body, status=502))
    )
    with pytest.raises(APIError) as caught:
        client.users.whoami()
    error = caught.value
    assert str(error) == f"Bad response 502: {body}"
    assert error.status_code == 502
    assert error.response_text == body
    assert error.response_data == decoded


@pytest.mark.parametrize(
    "status, body, content_type, expected",
    [
        (200, '{"message": "ok"}', "application/json", {"message": "ok"}),
        (200, '[{"id": "a"}]', "application/json", [{"id": "a"}]),
        (200, "key,value\na,b\n", "text/csv", "key,value\na,b\n"),
        (200, b"\x00\xff", "application/octet-stream", b"\x00\xff"),
        (204, b"", "", b""),
    ],
)
def test_successful_response_contract_is_unchanged(
    client, monkeypatch, status, body, content_type, expected
):
    monkeypatch.setattr(
        client.session,
        "request",
        Mock(return_value=make_response(body, status, content_type)),
    )
    assert client.users.whoami() == (status, expected)
    client.logger.error.assert_not_called()


def test_network_failure_preserves_original_cause(client, monkeypatch):
    timeout = requests.Timeout("request timed out")
    monkeypatch.setattr(client.session, "request", Mock(side_effect=timeout))
    with pytest.raises(APIError) as caught:
        client.users.whoami()
    error = caught.value
    assert str(error) == "Request failed: request timed out"
    assert error.__cause__ is timeout
    assert error.status_code is None
    assert error.response_data is None
    assert error.response_text is None
    assert error.details is None
    assert error.params is None


def test_direct_api_error_construction_is_backward_compatible():
    error = APIError("custom error", 409)
    assert str(error) == "custom error"
    assert error.args == ("custom error",)
    assert error.status_code == 409
    assert error.details is None
    assert error.params is None


def test_kuma_34_entity_errors_include_the_password_limit():
    payload = {
        "entity": "export",
        "errors": {"password": "must be greater than or equal to"},
        "params": {"password": {"greater": 16}},
    }
    body = json.dumps(payload)
    error = APIError.from_response(make_response(body))
    assert str(error) == (
        "Bad response 400: export\npassword: must be greater than or equal to 16"
    )
    assert error.errors == payload["errors"]
    assert error.entity == "export"
    assert error.details is None
    assert error.params == payload["params"]
    assert error.response_data == payload
    assert error.response_text == body


def test_kuma_34_dictionary_error_does_not_invent_missing_parameters():
    payload = {
        "message": "validation error",
        "details": {
            "tableDict.rows.0.0": "the number of characters must be between",
            "tableDict.rows.1.0": "the number of characters must be between",
        },
    }
    error = APIError.from_response(make_response(json.dumps(payload)))
    assert error.params is None
    assert error.details == payload["details"]
    assert str(error) == (
        "Bad response 400: validation error\n"
        "tableDict.rows.0.0: the number of characters must be between\n"
        "tableDict.rows.1.0: the number of characters must be between"
    )


@pytest.mark.parametrize("title", [{}, {"message": "invalid"}, {"entity": "input"}])
def test_errors_field_is_supported_without_losing_server_data(title):
    payload = {**title, "errors": {"field": "required"}}
    error = APIError.from_response(make_response(json.dumps(payload)))
    assert "field: required" in str(error)
    assert error.errors == payload["errors"]
    assert error.response_data == payload


def test_both_details_and_errors_are_retained():
    payload = {
        "message": "invalid",
        "details": {"first": "required"},
        "errors": {"second": "invalid"},
    }
    error = APIError.from_response(make_response(json.dumps(payload)))
    assert "first: required" in str(error)
    assert 'errors: {"second": "invalid"}' in str(error)
    assert error.details == payload["details"]
    assert error.errors == payload["errors"]


def test_kuma_34_decryption_error_preserves_the_server_status():
    payload = {
        "reason": "Decryption error",
        "details": "cipher: message authentication failed",
    }
    error = APIError.from_response(make_response(json.dumps(payload), status=500))
    assert str(error) == (
        "Bad response 500: Decryption error\n"
        "details: cipher: message authentication failed"
    )
    assert error.status_code == 500
    assert error.details == payload["details"]
    assert error.response_data == payload
