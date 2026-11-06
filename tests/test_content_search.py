"""Поиск ресурсов без сети: полнота, курсор, пределы и структура JSON."""

from unittest.mock import Mock
from uuid import UUID

import pytest

from kuma import RestClient
from kuma.rest.content_search import SearchError, content_search_plan, inspect_content

T = str(UUID(int=1))
A, B, C = (str(UUID(int=i)) for i in (2, 3, 4))


def resource(ident=A, kind="filter", **payload):
    return {
        "id": ident,
        "tenantID": T,
        "kind": kind,
        "name": "Example",
        "payload": payload,
    }


def execute(handler, **kwargs):
    calls = []
    plan = content_search_plan(kind="filter", tenant_ids=[T], query="needle", **kwargs)
    try:
        request = next(plan)
        while True:
            calls.append(request)
            try:
                reply = handler(*request)
            except SearchError as error:
                request = plan.throw(error)
            else:
                request = plan.send(reply)
    except StopIteration as result:
        return result.value, calls


def test_deep_arrays_dictionary_keys_and_escaped_pointer():
    value = resource(data=[{"a/b~c": "none"}] * 1100 + [{"a/b~c": "NeedLE"}])
    result = inspect_content(value, "needle")
    assert result["matched"] and result["complete"]
    assert result["matches"][0]["path"] == "/payload/data/1100/a~1b~0c"
    assert inspect_content(resource(mapping={"DeviceVendor": "x"}), "devicevendor")[
        "matched"
    ]
    assert not inspect_content(resource(code="abc"), ".*")["matched"]


def test_secret_fields_and_quoted_fake_references_are_excluded():
    value = resource(
        password="needle",
        credentials={"nested": "needle"},
        code=f"Name=\"filter='{B}'\"",
    )
    result = inspect_content(value, "needle")
    assert not result["matched"] and not result["references"]


def test_paths_conditions_false_zero_and_same_document():
    value = resource(rules=[{"enabled": False, "count": 0, "code": "needle"}])
    assert inspect_content(value, "needle", paths=["/payload/rules/*/code"])["matched"]
    assert not inspect_content(value, "needle", paths=["/name"])["matched"]
    checks = [
        {"path": "/payload/rules/*/enabled", "op": "equals", "value": False},
        {"path": "/payload/rules/*/count", "op": "equals", "value": 0},
    ]
    assert inspect_content(value, None, conditions=checks)["matched"]
    checks[0]["value"] = 0
    assert not inspect_content(value, None, conditions=checks)["matched"]
    assert inspect_content(value, None, conditions=checks, condition_mode="any")[
        "matched"
    ]


def test_short_catalog_pages_require_empty_page_and_budget_resumes():
    docs = {A: resource(A, code="nothing"), B: resource(B, code="needle")}

    def handler(method, args):
        if method == "resources.search":
            assert args["tenantID"] == [T] and args["kind"] == "filter"
            return {1: [docs[A]], 2: [docs[B]]}.get(args["page"], [])
        assert args["filter_code_only"] is True
        return docs[args["id"]]

    first, calls = execute(handler, max_queries=1)
    assert len(calls) == 1 and first["state"]["root"]["pending"]
    second, calls = execute(handler, max_queries=1, state=first["state"])
    assert len(calls) == 1 and calls[0][0] == "resources.get" and second["checked"] == 1
    third, calls = execute(handler, state=second["state"])
    assert third["complete"] and third["rows"][0]["id"] == B and third["checked"] == 2


def test_reference_continuation_does_not_reload_root_and_deduplicates_cycle():
    docs = {
        A: resource(A, code=f"filter='{B}'"),
        B: resource(B, code=f"filter='{A}' AND needle"),
    }

    def handler(method, args):
        return (
            ([docs[A]] if args["page"] == 1 else [])
            if method.endswith("search")
            else docs[args["id"]]
        )

    first, _ = execute(
        handler, max_queries=2, include_references=True, reference_depth=2
    )
    second, calls = execute(
        handler, state=first["state"], include_references=True, reference_depth=2
    )
    assert calls[0][1]["id"] == B
    assert second["complete"] and second["rows"][0]["matched_resource"]["id"] == B
    assert second["rows"][0]["via"] == [A]


def test_shared_dependency_loaded_once_and_embedded_rule_never_fetched():
    docs = {
        A: resource(A, code=f"filter='{C}'"),
        B: resource(B, code=f"filter='{C}'"),
        C: resource(C, code="nothing"),
    }

    def handler(method, args):
        return (
            ([docs[A], docs[B]] if args["page"] == 1 else [])
            if method.endswith("search")
            else docs[args["id"]]
        )

    result, calls = execute(handler, include_references=True)
    assert result["complete"] and not result["rows"]
    assert sum(args.get("id") == C for _, args in calls) == 1
    embedded = resource(
        rules=[{"id": B, "selectors": [{"filter": {"code": "needle"}}]}]
    )
    inspected = inspect_content(embedded, "needle")
    assert (
        inspected["matched"] and ("correlationRule", B) not in inspected["references"]
    )


@pytest.mark.parametrize("code", ["upstream_http_403", "upstream_response_too_large"])
def test_unreadable_is_not_a_negative_match(code):
    def handler(method, args):
        if method.endswith("search"):
            return [resource()] if args["page"] == 1 else []
        raise SearchError(code)

    result, _ = execute(handler)
    assert not result["complete"] and result["scan_exhausted"]
    assert result["unreadable"] == 1 and result["state"] is None


def test_no_retry_after_overload():
    def handler(*args):
        raise SearchError("upstream_http_429")

    result, calls = execute(handler)
    assert len(calls) == 1 and result["stop_reason"] == "upstream_http_429"


def test_cross_tenant_does_not_fetch_detail():
    result, calls = execute(lambda *_: [{**resource(), "tenantID": B}])
    assert len(calls) == 1 and result["stop_reason"] == "upstream_scope_mismatch"


def test_catalog_change_requires_restart():
    first, _ = execute(
        lambda method, args: (
            [resource(A), resource(B)]
            if method.endswith("search")
            else resource(args["id"], code="needle")
        ),
        limit=1,
    )
    result, _ = execute(lambda *_: [resource(B), resource(A)], state=first["state"])
    assert (
        result["stop_reason"] == "catalog_changed_restart_search" and not result["rows"]
    )


def test_reordered_duplicate_page_stops():
    def handler(method, args):
        if method.endswith("search"):
            return (
                [resource(A), resource(B)]
                if args["page"] == 1
                else [resource(B), resource(A)]
            )
        return resource(args["id"], code="nothing")

    result, calls = execute(handler)
    assert result["stop_reason"] == "repeated_upstream_page" and len(calls) == 4


def test_reference_cap_remains_incomplete_and_state_fits_cursor():
    import json
    from base64 import urlsafe_b64encode

    refs = [str(UUID(int=i)) for i in range(10, 30)]
    root = resource(code=" AND ".join(f"filter='{i}'" for i in refs))

    def handler(method, args):
        if method.endswith("search"):
            return [root] if args["page"] == 1 else []
        return root if args["id"] == A else resource(args["id"], code="no match")

    first, _ = execute(handler, include_references=True, max_queries=2)
    assert first["unreadable"] == 1 and not first["complete"]
    assert len(urlsafe_b64encode(json.dumps(first["state"]).encode())) < 3500
    second, _ = execute(handler, include_references=True, state=first["state"])
    assert second["scan_exhausted"] and not second["complete"]


def test_sdk_method_uses_public_resource_methods(monkeypatch):
    with RestClient("https://example.invalid", "test-token", version="3.4") as client:
        get = Mock(return_value=(200, resource(code="needle")))
        search = Mock(return_value=(200, [resource()]))
        monkeypatch.setattr(client.resources, "get", get)
        monkeypatch.setattr(client.resources, "search", search)
        # Один вызов на порцию: реальная пауза не нужна.
        _, first = client.resources.find_content(
            kind="filter", tenant_ids=[T], query="needle", max_queries=1
        )
        _, second = client.resources.find_content(
            kind="filter",
            tenant_ids=[T],
            query="needle",
            max_queries=1,
            state=first["state"],
        )
        assert second["rows"][0]["id"] == A and search.call_count == get.call_count == 1


@pytest.mark.parametrize(
    "options",
    [
        {"tenant_ids": []},
        {"query": " "},
        {"max_queries": 21},
        {"paths": ["/a~2"]},
        {"conditions": [{"path": "/a", "op": "contains", "value": ""}]},
    ],
)
def test_invalid_search_never_yields_request(options):
    args = {"kind": "filter", "tenant_ids": [T], "query": "needle", **options}
    with pytest.raises(ValueError):
        next(content_search_plan(**args))
