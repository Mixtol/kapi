"""Check the public wire contract against an independently captured Swagger."""

import json
import re
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import unquote, urlsplit

import pytest

from kuma import DownloadStream, RestClient
from tests.test_api_errors import make_response

SPEC_FILES = {
    "3.4": "public_api_v3.json",
    "4.0": "public_api_v3_4_0.json",
    "4.1": "public_api_v3_4_0.json",  # Explicit compatibility with the 4.0 contract.
    "4.2": "public_api_v3_4_2.json",
}
OPERATIONS = {}
for version, filename in SPEC_FILES.items():
    spec = json.loads(
        (Path(__file__).parent / "fixtures" / filename).read_text(encoding="utf-8")
    )
    OPERATIONS[version] = {(op["method"], op["path"]): op for op in spec["operations"]}
RESOURCE = {
    "name": "example",
    "kind": "correlator",
    "tenantID": "tenant",
    "payload": {},
}

# name, positional arguments, keyword arguments, HTTP method, Swagger path
CASES = [
    ("active_lists.lists", ("correlator",), {}, "GET", "/activeLists"),
    (
        "active_lists.import_data",
        ("correlator", "csv", "key,value\na,b\n"),
        {"activeListID": "list", "keyField": "key"},
        "POST",
        "/activeLists/import",
    ),
    ("alerts.search", (), {}, "GET", "/alerts"),
    ("alerts.assign", (["alert"], "user"), {}, "POST", "/alerts/assign"),
    ("alerts.close", ("alert",), {}, "POST", "/alerts/close"),
    ("alerts.comment", ("alert", "comment"), {}, "POST", "/alerts/comment"),
    ("alerts.get", ("alert",), {}, "GET", "/alerts/id/{id}"),
    (
        "alerts.link_event",
        ("alert", "cluster", "event", 1),
        {},
        "POST",
        "/alerts/link-event",
    ),
    ("alerts.unlink_event", ("alert", "event"), {}, "POST", "/alerts/unlink-event"),
    ("assets.search", (), {}, "GET", "/assets"),
    (
        "assets.delete",
        (),
        {"assets_ids": ["asset"], "tenant_id": "tenant"},
        "POST",
        "/assets/delete",
    ),
    ("assets.create", ([], "tenant"), {}, "POST", "/assets/import"),
    ("context_tables.list", ("correlator",), {}, "GET", "/contextTables"),
    (
        "context_tables.export",
        ("correlator",),
        {"context_table_id": "table"},
        "GET",
        "/contextTables/export",
    ),
    (
        "context_tables.import_data",
        ("correlator", "csv", "key,value\na,b\n"),
        {"contextTableID": "table"},
        "POST",
        "/contextTables/import",
    ),
    ("dictionaries.content", ("dictionary",), {}, "GET", "/dictionaries"),
    (
        "dictionaries.add_row",
        ("dictionary", "key", {"value": "test"}),
        {},
        "POST",
        "/dictionaries/add_row",
    ),
    (
        "dictionaries.delete_row",
        ("dictionary", "key"),
        {},
        "POST",
        "/dictionaries/delete_row",
    ),
    (
        "dictionaries.update",
        ("dictionary", "key,value\na,b\n"),
        {},
        "POST",
        "/dictionaries/update",
    ),
    ("resources.download", ("file",), {}, "GET", "/download/{id}"),
    ("events.search", (None, 0, 1, "SELECT 1"), {}, "POST", "/events"),
    ("events.get_clusters", (), {}, "GET", "/events/clusters"),
    ("folders.search", (["tenant"],), {}, "GET", "/folders/"),
    ("incidents.search", (), {}, "GET", "/incidents"),
    ("incidents.assign", (["incident"], "user"), {}, "POST", "/incidents/assign"),
    ("incidents.close", (["incident"], 0), {}, "POST", "/incidents/close"),
    ("incidents.comment", ("incident", "comment"), {}, "POST", "/incidents/comment"),
    (
        "incidents.create",
        ({"name": "incident", "tenantID": "tenant", "priority": 1},),
        {},
        "POST",
        "/incidents/create",
    ),
    ("incidents.get", ("incident",), {}, "GET", "/incidents/id/{id}"),
    ("incidents.link_alert", ("incident", ["alert"]), {}, "POST", "/incidents/link"),
    (
        "incidents.unlink_alert",
        ("incident", ["alert"]),
        {},
        "POST",
        "/incidents/unlink",
    ),
    ("reports.search", (["tenant"],), {}, "GET", "/reports/"),
    ("resources.search", (), {}, "GET", "/resources"),
    (
        "resources.download",
        ("file",),
        {"legacy": True},
        "GET",
        "/resources/download/{id}",
    ),
    (
        "resources.export",
        (["resource"], "tenant", "test-password"),
        {},
        "POST",
        "/resources/export",
    ),
    (
        "resources.import_data",
        ("file", "tenant", "test-password"),
        {},
        "POST",
        "/resources/import",
    ),
    ("resources.toc", ("file", "test-password"), {}, "POST", "/resources/toc"),
    ("resources.upload", (b"archive",), {}, "POST", "/resources/upload"),
    (
        "resources.create",
        ("correlator", RESOURCE),
        {},
        "POST",
        "/resources/{kind}/create",
    ),
    (
        "resources.validate",
        ("correlator", RESOURCE),
        {},
        "POST",
        "/resources/{kind}/validate",
    ),
    (
        "resources.get",
        ("correlator", "id"),
        {"filter_code_only": True},
        "GET",
        "/resources/{kind}/{id}",
    ),
    (
        "resources.put",
        ("correlator", "id", RESOURCE),
        {},
        "PUT",
        "/resources/{kind}/{id}",
    ),
    (
        "resources.list_history",
        ("correlator", "id"),
        {"page": 2, "size": 10, "sort": "-changeNumber", "userLogin": "user"},
        "GET",
        "/resources/{kind}/{id}/history",
    ),
    (
        "resources.get_history",
        ("correlator", "id", 1),
        {},
        "GET",
        "/resources/{kind}/{id}/history/{changeNumber}",
    ),
    (
        "resources.revert",
        ("correlator", "id", 1),
        {},
        "POST",
        "/resources/{kind}/{id}/history/{changeNumber}",
    ),
    ("services.search", (), {}, "GET", "/services"),
    ("services.create", ("resource",), {}, "POST", "/services/create"),
    (
        "active_lists.export",
        ("correlator", "list"),
        {},
        "GET",
        "/services/{id}/activeLists/export/{list}",
    ),
    (
        "active_lists.scan",
        ("correlator", "list"),
        {
            "limit": "10",
            "pattern": "test",
            "sort": "updated",
            "from": "0",
            "exclude": "1",
        },
        "GET",
        "/services/{id}/activeLists/scan/{list}",
    ),
    ("services.reload", ("service",), {}, "POST", "/services/{id}/reload"),
    ("services.restart", ("service",), {}, "POST", "/services/{id}/restart"),
    (
        "settings.export_extendedfields",
        (),
        {},
        "GET",
        "/settings/extendedFields/export",
    ),
    (
        "settings.import_extendedfields",
        ([{"kind": "SA", "name": "field", "description": "test", "disabled": False}],),
        {},
        "POST",
        "/settings/extendedFields/import",
    ),
    ("settings.view", ("id",), {}, "GET", "/settings/id/{id}"),
    ("system.backup", (), {}, "GET", "/system/backup"),
    ("system.restore", (), {"data": b"archive"}, "POST", "/system/restore"),
    (
        "tasks.create",
        ({"kind": "retroscan", "tenantIDs": ["tenant"]},),
        {},
        "POST",
        "/tasks/create",
    ),
    ("tenants.search", (), {}, "GET", "/tenants"),
    ("tenants.create", ("tenant", 100), {}, "POST", "/tenants/create"),
    ("users.search", (), {"size": 10, "excludeDisabled": False}, "GET", "/users/"),
    ("users.get", ("user",), {}, "GET", "/users/id/{id}"),
    ("users.whoami", (), {}, "GET", "/users/whoami"),
]


@pytest.mark.parametrize("version", SPEC_FILES)
def test_all_swagger_operations_have_a_client_contract(version):
    assert {(method, path) for _, _, _, method, path in CASES} == set(
        OPERATIONS[version]
    )


def check_schema(value, schema):
    kind = schema.get("type")
    if kind == "array":
        assert isinstance(value, list)
        for item in value:
            check_schema(item, schema.get("items", {}))
    elif kind == "string":
        assert isinstance(value, str)
    elif kind == "integer":
        assert isinstance(value, int) and not isinstance(value, bool)
    elif kind == "boolean":
        assert isinstance(value, bool)
    elif kind == "object":
        assert isinstance(value, dict)
    if "enum" in schema:
        # KUMA's actions schema puts the enum on the map, not its values.
        if kind == "object":
            assert all(item in schema["enum"] for item in value.values())
        else:
            assert value in schema["enum"]
    if isinstance(value, dict):
        assert set(schema.get("required", [])) <= value.keys()
        if schema.get("additionalProperties") is False:
            assert value.keys() <= schema.get("properties", {}).keys()
        for name, definition in schema.get("properties", {}).items():
            if name in value:
                check_schema(value[name], definition)


@pytest.mark.parametrize(
    "name,args,kwargs,method,path", CASES, ids=[f"{c[3]} {c[4]}" for c in CASES]
)
@pytest.mark.parametrize("version", SPEC_FILES)
def test_swagger_wire_contract(monkeypatch, name, args, kwargs, method, path, version):
    contract = OPERATIONS[version][method, path]
    recorded = []

    def send(**request):
        recorded.append(request)
        assert request["method"] == method
        actual_path = unquote(urlsplit(request["url"]).path).removeprefix("/api/v3")
        assert re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", path), actual_path)
        parameters = {
            p["name"]: p for p in contract["parameters"] if p["in"] == "query"
        }
        params = request.get("params", {})
        assert params.keys() <= parameters.keys()
        assert {
            name for name, p in parameters.items() if p.get("required")
        } <= params.keys()
        if "application/json" in contract["body"]:
            assert "json" in request
            check_schema(request["json"], contract["body"]["application/json"])
        elif contract["body"]:
            body = request["data"]
            chunks = []
            while True:
                chunk = body.read(1024)
                if not chunk:
                    break
                chunks.append(chunk)
            assert b"".join(chunks)
            if "multipart/form-data" in contract["body"]:
                assert 'name="file"' in b"".join(chunks).decode()
                assert request["headers"]["Content-Type"].startswith(
                    "multipart/form-data; boundary="
                )
        return make_response("{}", status=contract["response_codes"][0])

    with RestClient("https://example.invalid", "test-token", version=version) as client:
        monkeypatch.setattr(client.session, "request", send)
        module, member = name.split(".")
        status, body = getattr(getattr(client, module), member)(*args, **kwargs)
        assert status in contract["response_codes"]
        if isinstance(body, DownloadStream):
            body.close()
    assert len(recorded) == 1
