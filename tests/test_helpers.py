import csv
import io
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

from kuma import APIError, RestClient


@pytest.fixture
def client():
    with RestClient("example.invalid", "test-token") as api:
        yield api


def test_pagination_starts_at_requested_page_without_repeating(client, monkeypatch):
    request = Mock(
        side_effect=[(200, [{"id": i} for i in range(250)]), (200, [{"id": 250}])]
    )
    monkeypatch.setattr(client, "_make_request", request)
    status, items = client.alerts.searchp(limit=500, page=2)
    assert status == 200 and len(items) == 251
    assert [call.kwargs["params"]["page"] for call in request.call_args_list] == [2, 3]


def test_pagination_stops_at_limit_and_propagates_errors(client, monkeypatch):
    request = Mock(return_value=(200, list(range(250))))
    monkeypatch.setattr(client, "_make_request", request)
    assert client.alerts.searchp(limit=2) == (200, [0, 1])
    request.assert_called_once()
    request.reset_mock()
    assert client.alerts.searchp(limit=0) == (200, [])
    request.assert_not_called()
    request.side_effect = APIError("denied", 403)
    with pytest.raises(APIError):
        client.alerts.searchp(limit=2)


@pytest.mark.parametrize("cycle", [False, True])
def test_alert_pagination_stops_before_yielding_a_repeated_page(
    client, monkeypatch, cycle
):
    first = [{"id": str(i), "status": "new"} for i in range(250)]
    second = [{"id": str(i + 250)} for i in range(250)]
    repeated = [{"id": item["id"], "status": "closed"} for item in reversed(first)]
    pages = [first, second, repeated] if cycle else [first, repeated]
    search = Mock(side_effect=[(200, items) for items in pages])
    monkeypatch.setattr(client.alerts, "search", search)
    received = []
    with pytest.raises(APIError, match="repeated a page"):
        for alert in client.alerts.iter_search():
            received.append(alert)
    assert len(received) == (500 if cycle else 250)
    assert len({item["id"] for item in received}) == len(received)
    assert search.call_count == len(pages)


def test_pagination_does_not_accept_non_array_response(client, monkeypatch):
    monkeypatch.setattr(
        client, "_make_request", Mock(return_value=(200, {"unexpected": []}))
    )
    with pytest.raises(APIError, match="array"):
        client.alerts.searchp()


def test_csv_quoted_fields_and_newlines(client):
    source = '\ufeffkey,value\r\na,"b,c"\r\nd,"line1\nline2"\r\n'
    assert client.dictionaries.csv_to_json(source) == [
        {"key": "a", "value": "b,c"},
        {"key": "d", "value": "line1\nline2"},
    ]
    converted = client.active_lists._get_data_with_column(
        "key",
        [
            {"key": 1, "record": {"value": "x,y\nz"}},
            {"key": 2, "record": {"value": 42}},
        ],
        ["key", "value"],
        set(),
    )
    assert list(csv.reader(io.StringIO(converted))) == [["1", "x,y\nz"], ["2", "42"]]


@pytest.mark.parametrize(
    "text",
    ["key,key\na,b\n", "key,value\na,b,c\n", "key,value\na\n", 'key,value\na,"broken'],
)
def test_malformed_csv_is_rejected(client, text):
    with pytest.raises((ValueError, csv.Error)):
        client.dictionaries.csv_to_json(text)


def test_switching_csv_key_preserves_all_columns(client):
    result = client.dictionaries._swap_key_column(
        "key,value,host\nold,preserved,new\n", "host"
    )
    assert list(csv.DictReader(io.StringIO(result))) == [
        {"host": "old", "value": "preserved", "key": "new"}
    ]


@pytest.mark.parametrize(
    "text,column",
    [
        ("key,value\na,b\n", "missing"),
        ("key,value\na,one\nb,one\n", "value"),
        ("key,value\na,\n", "value"),
    ],
)
def test_invalid_new_keys_are_rejected(client, text, column):
    with pytest.raises(ValueError):
        client.dictionaries._swap_key_column(text, column)


def test_dictionary_conversion_uploads_an_existing_key_column(client, monkeypatch):
    def content(dictionary_id, filepath):
        Path(filepath).write_text("key,value,host\na,keep,new\n", encoding="utf-8")
        return 200, str(filepath)

    def upload(correlator, format, *, filepath, **kwargs):
        with Path(filepath).open(encoding="utf-8") as source:
            rows = list(csv.DictReader(source))
        assert kwargs["keyField"] == "key"
        assert rows == [{"host": "a", "value": "keep", "key": "new"}]
        assert kwargs["clear"] is False
        return 204, b""

    monkeypatch.setattr(client.dictionaries, "content", content)
    monkeypatch.setattr(client.active_lists, "import_data", upload)
    assert client.dictionaries.to_active_list("d", "c", "a", dictionary_key="host") == (
        204,
        b"",
    )


def test_active_list_conversion_preserves_existing_csv_and_deduplicates(
    client, monkeypatch
):
    monkeypatch.setattr(
        client.active_lists, "export", Mock(return_value=(200, {"id": "exported"}))
    )

    def download(file_id, filepath):
        records = [
            {"key": "old", "record": {"value": "replace?"}},
            {"key": "new", "record": {"value": "comma,and\nnewline"}},
            {"key": "new", "record": {"value": "duplicate"}},
        ]
        Path(filepath).write_text("\n".join(map(json.dumps, records)), encoding="utf-8")
        return 200, str(filepath)

    def content(dictionary_id, filepath):
        Path(filepath).write_text('key,value\nold,"keep,me"', encoding="utf-8")
        return 200, str(filepath)

    def update(dictionary_id, *, filepath, need_reload):
        with Path(filepath).open(encoding="utf-8", newline="") as source:
            assert list(csv.reader(source)) == [
                ["key", "value"],
                ["old", "keep,me"],
                ["new", "comma,and\nnewline"],
            ]
        return 200, {}

    monkeypatch.setattr(client.active_lists, "download", download)
    monkeypatch.setattr(client.dictionaries, "content", content)
    monkeypatch.setattr(client.dictionaries, "update", update)
    assert client.active_lists.to_dictionary("c", "a", "d") == (200, {})


def test_link_unlink_rules_are_linear_and_do_not_mutate_input(client, monkeypatch):
    resource = {"payload": {"rules": [{"id": "a"}, {"id": "b"}]}}
    original = deepcopy(resource)
    get = Mock(
        side_effect=lambda kind, id: (
            200,
            resource if kind == "correlator" else {"payload": {"id": id}},
        )
    )
    put = Mock(return_value=(200, {}))
    monkeypatch.setattr(client.resources, "get", get)
    monkeypatch.setattr(client.resources, "put", put)
    assert client.resources.link_rules_to_correlator("c", ["a"]) == (200, resource)
    put.assert_not_called()
    client.resources.link_rules_to_correlator("c", ["c", "c", "d"])
    assert put.call_args.args[2]["payload"]["rules"] == [
        {"id": k} for k in ["a", "b", "c", "d"]
    ]
    assert resource == original
    client.resources.unlink_rules_from_correlator("c", ["a", "a"])
    assert put.call_args.args[2]["payload"]["rules"] == [{"id": "b"}]
    assert resource == original
