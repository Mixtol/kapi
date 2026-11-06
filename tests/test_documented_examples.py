"""Execute the documented calls against the captured Swagger, without a server."""

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from requests import Request

from kuma_api import DownloadStream, RestClient
from tests.test_api_errors import make_response
from tests.test_public_contracts import OPERATIONS, check_schema

REFERENCE = (Path(__file__).resolve().parents[1] / "API_REFERENCE.md").read_text(
    encoding="utf-8"
)
EXAMPLES = re.findall(
    r"^\| `([^`]+)` \| (GET|POST|PUT) \| `([^`]+)` \|.*\| `(client\.[^`]+)` \|$",
    REFERENCE,
    re.MULTILINE,
)
EXAMPLE_DATA = next(
    block
    for block in re.findall(r"```python\n(.*?)\n```", REFERENCE, re.DOTALL)
    if block.startswith("tenant_id =")
)


def query_value(value, schema):
    """Decode query strings according to Swagger before checking their types."""
    kind = schema.get("type")
    if kind == "boolean":
        assert value in ("true", "false")
        return value == "true"
    if kind == "integer":
        return int(value)
    if kind == "number":
        return float(value)
    return value


@pytest.mark.parametrize("version", OPERATIONS)
def test_every_swagger_operation_has_a_documented_example(version):
    assert len(EXAMPLES) == len(OPERATIONS[version])
    assert {(method, path) for _, method, path, _ in EXAMPLES} == set(
        OPERATIONS[version]
    )


@pytest.mark.parametrize("version", OPERATIONS)
@pytest.mark.parametrize(
    "name,method,path,code", EXAMPLES, ids=[row[0] for row in EXAMPLES]
)
def test_documented_call_matches_swagger(
    monkeypatch, tmp_path, version, name, method, path, code
):
    monkeypatch.chdir(tmp_path)
    for filename in ("resources.bin", "backup.tar.gz"):
        (tmp_path / filename).write_bytes(b"test archive body")
    contract = OPERATIONS[version][method, path]
    requests = []

    def send(**request):
        requests.append(request)
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
        prepared = Request("GET", request["url"], params=params).prepare()
        for key, values in parse_qs(
            urlsplit(prepared.url).query, keep_blank_values=True
        ).items():
            schema = parameters[key].get("schema", {})
            if schema.get("type") == "array":
                value = [query_value(item, schema.get("items", {})) for item in values]
            else:
                assert len(values) == 1
                value = query_value(values[0], schema)
            check_schema(value, schema)
        if "application/json" in contract["body"]:
            check_schema(request["json"], contract["body"]["application/json"])
        elif contract["body"]:
            assert request["data"].read(1024)
        return make_response("{}", status=contract["response_codes"][0])

    with RestClient("example.invalid", "test-token", version=version) as client:
        monkeypatch.setattr(client.session, "request", send)
        namespace = {"client": client}
        exec(EXAMPLE_DATA, namespace)
        status, result = eval(code, namespace)
        assert status in contract["response_codes"]
        if isinstance(result, DownloadStream):
            result.close()
        assert len(requests) == 1
