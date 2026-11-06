"""Behavioral regressions and legacy call contracts of the private client."""

import inspect
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from kuma import APIError, PrivateClient
from kuma.constants import SHARED_TENANT
from tests.test_api_errors import make_response

SAVED = {"cookies": {}, "headers": {}, "xsrf_token": "test-xsrf"}


@pytest.fixture
def api():
    with PrivateClient(
        "https://example.invalid", "user", "password", SAVED, "3.4"
    ) as client:
        yield client


def responses(monkeypatch, api, method, *data):
    result = []
    for value in data:
        status, body = value if isinstance(value, tuple) else (200, value)
        response = make_response(json.dumps(body) if body is not None else "", status)
        response.close = Mock()
        result.append(response)
    handler = Mock(side_effect=result)
    monkeypatch.setattr(api.session, method, handler)
    return handler, result


def test_legacy_call_signatures_are_retained():
    manifest = json.loads(
        (Path(__file__).parent / "fixtures/private_compatibility.json").read_text()
    )
    for source, methods in manifest.items():
        for name, arguments in methods.items():
            method = getattr(PrivateClient, name)
            signature = inspect.signature(method)
            kwargs = {name: object() for name in arguments}
            if "self" in signature.parameters:
                kwargs["self"] = object()
            signature.bind(**kwargs)
            positional = [object()] * (
                len(arguments) + ("self" in signature.parameters)
            )
            signature.bind(*positional)


@pytest.mark.parametrize("wrapped", [False, True])
def test_resources_paginate_past_short_server_pages(api, monkeypatch, wrapped):
    pages = [[{"id": "first"}], [{"id": "second"}], []]
    if wrapped:
        pages = [{"result": rows} for rows in pages]
    get, replies = responses(monkeypatch, api, "get", *pages)
    assert [row["id"] for row in api.get_resources("filter", "tenant")] == [
        "first",
        "second",
    ]
    assert [call.kwargs["params"]["page"] for call in get.call_args_list] == [1, 2, 3]
    assert all(
        call.kwargs["params"]["tenantID"] == "tenant" for call in get.call_args_list
    )
    assert all(response.close.call_count == 1 for response in replies)


@pytest.mark.parametrize("version", ["3.4", "4.0", "4.2", "4.2.1.5"])
def test_empty_correlators_result_is_an_empty_list(api, monkeypatch, version):
    api.version = version
    responses(monkeypatch, api, "get", {"result": []})
    assert api.get_all_correlator() == []


def test_pagination_rejects_reordered_repeated_ids_before_yielding(api, monkeypatch):
    responses(
        monkeypatch,
        api,
        "get",
        [{"id": "a"}, {"id": "b"}],
        [{"id": "b", "changed": True}, {"id": "a"}],
    )
    rows = api.iter_resources(page_size=2)
    assert [next(rows)["id"], next(rows)["id"]] == ["a", "b"]
    with pytest.raises(APIError, match="repeated a page"):
        next(rows)


def test_legacy_list_error_and_strict_iterator_error(api, monkeypatch):
    error = {"message": "denied"}
    responses(monkeypatch, api, "get", (403, error), (403, error))
    assert json.loads(api.get_resources("filter")) == error
    with pytest.raises(APIError) as caught:
        list(api.iter_resources("filter"))
    assert caught.value.status_code == 403
    assert caught.value.response_data == error


@pytest.mark.parametrize(
    "include_share,only_shared,expected",
    [
        (True, False, ["s", "t"]),
        (False, False, ["t"]),
        (True, True, ["s"]),
        (False, True, ["s"]),
    ],
)
def test_folder_shared_flags_and_offset(
    api, monkeypatch, include_share, only_shared, expected
):
    rows = [
        {"id": "s", "tenantID": SHARED_TENANT["id"], "tenantName": ""},
        {"id": "t", "tenantID": "tenant", "tenantName": ""},
    ]
    get, _ = responses(monkeypatch, api, "get", rows, [])
    result = api.get_all_folders_by_kind(
        include_share=include_share, only_shared=only_shared
    )
    assert [row["id"] for row in result] == expected
    assert [call.kwargs["params"]["offset"] for call in get.call_args_list] == [0, 2]


def test_root_folders_use_selected_tenants_alias(api, monkeypatch):
    api.selected_tenant = [{"id": "tenant", "name": "Tenant"}]
    responses(monkeypatch, api, "get", [], [])
    assert (
        api.get_all_folders_by_kind("filter", include_root=True)[0]["id"]
        == "filter-tenant"
    )
    assert api.selected_tenant is api.selected_tenants


def test_folder_snapshot_avoids_unstable_offset_pages(api, monkeypatch):
    a, b, c = ({"id": id_, "name": "same name"} for id_ in "abc")
    get, _ = responses(monkeypatch, api, "get", [a, c], [b, a, c], [])
    assert list(api.iter_folders(page_size=2)) == [b, a, c]
    assert [
        (call.kwargs["params"]["limit"], call.kwargs["params"]["offset"])
        for call in get.call_args_list
    ] == [(2, 0), (4, 0), (1, 3)]


def test_capped_folder_snapshot_fails_instead_of_returning_incomplete_data(
    api, monkeypatch
):
    responses(monkeypatch, api, "get", [{"id": "a"}, {"id": "b"}], [{"id": "c"}])
    with pytest.raises(APIError, match="capped the folder snapshot"):
        list(api.iter_folders(page_size=250))


@pytest.mark.parametrize("action", [-1, 3, True, "1", None])
def test_invalid_import_action_never_uploads(api, monkeypatch, action):
    post = Mock()
    monkeypatch.setattr(api.session, "post", post)
    with pytest.raises(ValueError, match="Import action"):
        api.import_content("not-opened.bin", "tenant", action=action)
    post.assert_not_called()


def test_folder_lookup_uses_supplied_kind_and_later_pages(api, monkeypatch):
    get, _ = responses(
        monkeypatch,
        api,
        "get",
        [
            {"id": "a", "name": "other"},
            {"id": "b", "name": "wanted", "tenantID": "tenant", "parentID": "parent"},
        ],
        [],
    )
    assert api.get_folder_id_by_name("wanted", "filter", "tenant", "parent") == "b"
    assert all(
        call.kwargs["params"]["subKind"] == "filter" for call in get.call_args_list
    )


def test_v2_restores_tenant_selection_when_folder_request_fails(api, monkeypatch):
    api._major_version = 2
    api.selected_tenants = [{"id": "original"}]
    monkeypatch.setattr(api, "whoami", Mock())
    monkeypatch.setattr(
        api, "get_all_tenants", Mock(return_value=[{"id": "temporary"}])
    )
    select = Mock(side_effect=lambda ids: api._remember_selection(ids))
    monkeypatch.setattr(api, "private_select_tenant", select)
    monkeypatch.setattr(api.session, "get", Mock(side_effect=requests.Timeout("slow")))
    with pytest.raises(requests.Timeout):
        api.get_all_folders()
    assert [call.args[0] for call in select.call_args_list] == [
        ["temporary"],
        ["original"],
    ]
    assert api.selected_tenants == [{"id": "original", "name": ""}]


@pytest.mark.parametrize("status", [200, 201, 204, 500])
def test_create_resource_preserves_input_and_handles_empty_success(
    api, monkeypatch, status
):
    resource = {
        "id": "source",
        "kind": "filter",
        "name": "old",
        "tenantName": "Old tenant",
        "payload": {"id": "source", "name": "old"},
    }
    original = deepcopy(resource)
    post, replies = responses(
        monkeypatch, api, "post", (status, None if status == 204 else {"id": "new"})
    )
    returned_status, body = api.create_resource(
        resource, "tenant", "folder", "new name"
    )
    assert returned_status == status
    assert resource == original
    sent = post.call_args.kwargs["json"]
    assert sent["tenantName"] == "" and "tanantName" not in sent
    assert sent["name"] == sent["payload"]["name"] == "new name"
    assert sent["id"] == sent["payload"]["id"] == ""
    if status == 204:
        assert body is None
    replies[0].close.assert_called_once()


@pytest.mark.parametrize("status", [200, 204, 400, 401, 403, 404, 500])
def test_upsert_creates_only_on_not_found_and_returns_status(api, monkeypatch, status):
    resource = {"id": "id", "kind": "filter", "payload": {"id": "id"}}
    original = deepcopy(resource)
    responses(monkeypatch, api, "put", (status, None if status == 204 else {}))
    post, _ = responses(monkeypatch, api, "post", (201, {"id": "created"}))
    assert api.update_or_create_resource(resource, "tenant", "") == (
        201 if status == 404 else status
    )
    assert post.call_count == (status == 404)
    assert resource == original


def test_resource_and_payload_helpers_have_distinct_shapes(api, monkeypatch):
    resource = {"id": "r", "payload": {"id": "r", "name": "rule"}}
    responses(monkeypatch, api, "get", resource, resource)
    assert api.get_rule_by_id("r", "correlationRule") == resource
    assert api.get_correlation_rule_by_id("r") == resource["payload"]
    with pytest.raises(ValueError):
        api.get_rule_by_id("r", "unknown")


@pytest.mark.parametrize("version", ["2.1.0", "3.4", "4.2"])
def test_move_and_delete_use_explicit_ids_and_keep_result_shapes(monkeypatch, version):
    with PrivateClient("example.invalid", "user", "password", SAVED, version) as client:
        post, replies = responses(monkeypatch, client, "post", (204, None))
        response = client.move_content(folderID="folder", resourceIDs=["r"])
        assert response is replies[0]
        response.close.assert_not_called()
        response.close()
        expected = (
            {"folderID": "folder", "resourceIDs": ["r"]}
            if version.startswith("2")
            else {"folderID": "folder", "ids": ["r"], "searchType": "ids"}
        )
        assert post.call_args.kwargs["json"] == expected
        delete, replies = responses(monkeypatch, client, "delete", (204, None))
        assert client.delete_resource("r", "filter") == ("", 204)
        if version.startswith("2"):
            assert delete.call_args.kwargs["json"] == {"ids": ["r"]}
        else:
            assert delete.call_args.args[0].endswith("/resources/filter/r")
            assert "json" not in delete.call_args.kwargs
        replies[0].close.assert_called_once()
        with pytest.raises(ValueError):
            client.move_content("folder", [])


def test_legacy_service_aliases_match_corrected_names(api, monkeypatch):
    monkeypatch.setattr(
        api,
        "get_all_services",
        Mock(
            return_value=[
                {"id": "a", "resourceID": "r"},
                {"id": "b", "resourceID": "r"},
                {"id": "c", "resourceID": "other"},
            ]
        ),
    )
    assert (
        api.get_service_id_by_resouce_id("r")
        == api.get_service_id_by_resource_id("r")
        == "a"
    )
    assert (
        api.get_services_id_by_resouce_id("r")
        == api.get_services_ids_by_resource_id("r")
        == ["a", "b"]
    )


def test_search_encodes_special_name_once_and_reads_next_page(api, monkeypatch):
    name = "Rule #1 + A&B/тест"
    calls = []

    def send(session, request, **kwargs):
        query = parse_qs(urlsplit(request.url).query)
        calls.append(query)
        assert query["name"] == [name]
        page = int(query["page"][0])
        return make_response(
            json.dumps(
                [
                    {
                        "id": str(page),
                        "name": "other" if page == 1 else name,
                        "tenantID": "tenant",
                    }
                ]
            ),
            200,
        )

    monkeypatch.setattr(requests.Session, "send", send)
    assert api.get_resource_id_by_name(name, "tenant") == (200, "2")
    assert len(calls) == 2


def test_shared_search_uses_tenant_id_not_empty_name(api, monkeypatch):
    monkeypatch.setattr(
        api, "get_tenant_shared", Mock(return_value=SHARED_TENANT["id"])
    )
    responses(
        monkeypatch,
        api,
        "get",
        [
            {
                "id": "wrong",
                "name": "Shared_rule",
                "tenantName": "",
                "tenantID": "regular",
            },
            {
                "id": "right",
                "name": "Shared_rule",
                "tenantName": "",
                "tenantID": SHARED_TENANT["id"],
            },
        ],
    )
    assert api.get_resource_id_by_name(
        "Shared_rule", "regular", shared_prefixes=["Shared_"]
    ) == (200, "right")


def test_batch_binding_retains_tuple_and_status_results(api, monkeypatch):
    post, _ = responses(monkeypatch, api, "post", (204, None), (204, None))
    assert api.link_rules(rules_IDs=["a", "a", "b"], correlator_IDs=["c", "c"]) == (
        204,
        "",
    )
    assert api.bind_rules(["a"], ["c"], "tenant") == 204
    assert post.call_args_list[0].kwargs["json"] == {
        "ids": ["a", "b"],
        "correlatorIDs": ["c"],
        "searchType": "ids",
    }
    assert post.call_args_list[1].kwargs["params"] == {"tenantID": "tenant"}


def test_rule_link_is_ordered_idempotent_and_does_not_mutate_input(api, monkeypatch):
    correlator = {"id": "c", "payload": {"rules": [{"id": "already"}]}}
    original = deepcopy(correlator)
    monkeypatch.setattr(api, "get_correlator_by_id", Mock(return_value=correlator))
    getter = Mock(side_effect=lambda id_: {"id": id_})
    monkeypatch.setattr(api, "get_correlation_rule_by_id", getter)
    put, _ = responses(monkeypatch, api, "put", {"updated": True})
    assert api.link_rules_to_correlator("c", ["b", "a", "b", "already"]) == (
        200,
        {"updated": True},
    )
    assert [row["id"] for row in put.call_args.kwargs["json"]["payload"]["rules"]] == [
        "already",
        "b",
        "a",
    ]
    assert getter.call_count == 2 and correlator == original
    assert (
        api.link_rule_to_correlator("c", "already")
        == "Rule already exist on correlator"
    )
    assert put.call_count == 1


@pytest.mark.parametrize(
    "action,ids,expected",
    [("add", ["b", "c", "c"], ["a", "b", "c"]), ("delete", ["a"], ["b"])],
)
def test_settings_update_preserves_payload_and_order(
    api, monkeypatch, action, ids, expected
):
    payload = {
        "disabled": True,
        "segmentationRules": [
            {"name": "ALL_EventOutcome", "correlationRuleIDs": ["a", "b"]},
            {"name": "other", "correlationRuleIDs": ["z"]},
        ],
    }
    original = deepcopy(payload)
    put, _ = responses(monkeypatch, api, "put", (204, None))
    assert api.update_settings_by_id("settings", ids, action, payload) == (204, None)
    sent = put.call_args.kwargs["json"]
    assert sent["segmentationRules"][0]["correlationRuleIDs"] == expected
    assert (
        sent["disabled"] is True
        and sent["segmentationRules"][1] == payload["segmentationRules"][1]
    )
    assert payload == original


def test_settings_fetch_when_payload_omitted_and_noop_skips_write(api, monkeypatch):
    payload = {
        "segmentationRules": [{"name": "ALL_EventOutcome", "correlationRuleIDs": ["a"]}]
    }
    responses(monkeypatch, api, "get", payload)
    put = Mock()
    monkeypatch.setattr(api.session, "put", put)
    assert api.update_settings_by_id("settings", ["a"]) == (200, payload)
    with pytest.raises(ValueError, match="not found"):
        api.update_settings_by_id(
            "settings", ["b"], payload=payload, rule_name="missing"
        )
    assert api.update_settings_by_id("settings", []) == (
        0,
        "ERROR: argument 'correlation_rules' is empty list",
    )
    put.assert_not_called()


def test_settings_repeated_columns_and_http_error_tuple(api, monkeypatch):
    captured = []

    def send(session, request, **kwargs):
        captured.append(parse_qs(urlsplit(request.url).query))
        return make_response("denied", 403)

    monkeypatch.setattr(requests.Session, "send", send)
    assert api.get_settings(columns=["tenantID", "disabled"]) == (403, "denied")
    assert captured[0]["column"] == ["tenantID", "disabled"]


@pytest.mark.parametrize("version", ["2.1.0", "3.4", "4.0", "4.1", "4.2"])
def test_active_list_version_routes_and_encoded_key(monkeypatch, version):
    captured = []

    def send(session, request, **kwargs):
        captured.append(request)
        return make_response("", 204)

    monkeypatch.setattr(requests.Session, "send", send)
    with PrivateClient("example.invalid", "user", "password", SAVED, version) as client:
        assert (
            client.post_activeList_record(
                "service", "list", "a#&/+", {"field": "value"}
            )
            is None
        )
        assert client.delete_activeList_record("service", "list", "a#&/+") is None
    assert urlsplit(captured[0].url).path.endswith("/activeLists/create/list")
    assert urlsplit(captured[1].url).path.endswith("/activeLists/del/list")
    for request in captured:
        if version.startswith("2"):
            assert parse_qs(urlsplit(request.url).query)["key"] == ["a#&/+"]
        else:
            assert json.loads(request.body)["key"] == "a#&/+"


@pytest.mark.parametrize("version", ["5.0", "4.9", "bad", None])
def test_unknown_version_fails_before_login(monkeypatch, version):
    send = Mock()
    monkeypatch.setattr(requests.Session, "send", send)
    with pytest.raises((ValueError, TypeError)):
        PrivateClient("example.invalid", "user", "password", version=version)
    send.assert_not_called()


def test_saved_session_validation_refreshes_expired_cookie_once(monkeypatch):
    calls = []

    def send(session, request, **kwargs):
        path = urlsplit(request.url).path
        calls.append(path)
        if path == "/api/whoami":
            status = 200 if "/api/login" in calls else 401
            return make_response('{"id":"user","selectedTenants":[]}', status)
        if path == "/api/login":
            session.cookies.set("XSRF-TOKEN", "fresh-token")
            return make_response("", 204)
        if path == "/api/private/tenants/":
            return make_response('[{"id":"tenant"}]', 200)
        return make_response("", 204)

    monkeypatch.setattr(requests.Session, "send", send)
    with PrivateClient(
        "example.invalid", "user", "password", SAVED, "3.4", validate_session=True
    ) as client:
        assert client.session.headers["X-XSRF-TOKEN"] == "fresh-token"
        assert client.selected_tenants == [{"id": "tenant"}]
    assert calls.count("/api/login") == 1


def test_session_check_preserves_network_error_and_does_not_relogin(monkeypatch):
    send = Mock(side_effect=requests.exceptions.SSLError("wrong CA"))
    monkeypatch.setattr(requests.Session, "send", send)
    with pytest.raises(ConnectionError) as caught:
        PrivateClient(
            "example.invalid", "user", "password", SAVED, "3.4", validate_session=True
        )
    assert isinstance(caught.value.__cause__, requests.exceptions.SSLError)
    assert send.call_count == 1
