import csv
import io
import json
from pathlib import Path
from unittest.mock import Mock, call
from urllib.parse import urlsplit

import pytest

from kuma import APIError, RestClient
from tests.test_api_errors import make_response


@pytest.fixture
def conversion(monkeypatch):
    with RestClient("example.invalid", "test-token", version="4.2") as client:
        data = {"csv": "key,value\nold,keep\n", "ndjson": "", "uploads": []}

        def download(file_id, *, filepath):
            Path(filepath).write_text(data["ndjson"], encoding="utf-8")
            return 200, str(filepath)

        def content(dictionary_id, *, filepath):
            Path(filepath).write_text(data["csv"], encoding="utf-8")
            return 200, str(filepath)

        def update(dictionary_id, *, filepath, need_reload):
            with Path(filepath).open(encoding="utf-8", newline="") as source:
                data["uploads"].append(list(csv.reader(source)))
            data["upload_path"] = Path(filepath)
            return 200, {"message": "server response"}

        monkeypatch.setattr(
            client.active_lists, "export", Mock(return_value=(200, {"id": "export"}))
        )
        monkeypatch.setattr(client.active_lists, "download", download)
        monkeypatch.setattr(client.dictionaries, "content", content)
        monkeypatch.setattr(client.dictionaries, "update", Mock(side_effect=update))
        monkeypatch.setattr(
            client.dictionaries,
            "delete_row",
            Mock(return_value=(200, {"deleted": True})),
        )
        yield client, data


def ndjson(*rows):
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)


def record(key="new", value="value", **fields):
    return {"key": key, "record": {"value": value, **fields}}


def convert(client, **options):
    return client.active_lists.to_dictionary(
        "correlator", "list", "dictionary", **options
    )


@pytest.mark.parametrize("version", ["3.4", "4.0", "4.1", "4.2"])
def test_cell_conversion_keeps_csv_and_scalar_values(version):
    with RestClient("example.invalid", "test-token", version=version) as client:
        result = client.active_lists._get_data_with_column(
            "key",
            [
                record(0, False),
                record("null-value", None),
                record("quoted", 'comma,"quote"\nline'),
                record("кириллица", "я" * 1024),
            ],
            ["key", "value"],
            set(),
        )
    assert list(csv.reader(io.StringIO(result, newline=""))) == [
        ["0", "False"],
        ["null-value", ""],
        ["quoted", 'comma,"quote"\nline'],
        ["кириллица", "я" * 1024],
    ]


@pytest.mark.parametrize("size", [255, 256, 1024])
def test_server_supported_cell_lengths_are_kept(conversion, size):
    client, data = conversion
    data["ndjson"] = ndjson(record("я" * size, "я" * size))
    assert convert(client) == (200, {"message": "server response"})
    assert data["uploads"][0][-1] == ["я" * size, "я" * size]
    assert not data["upload_path"].exists()


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        "text",
        42,
        {},
        {"key": "a", "record": None},
        {"record": {}},
        record(None),
        record(""),
        record("x" * 1025),
        record("oversized-value", "x" * 1161),
        record("unicode", "\ud800"),
    ],
)
def test_invalid_new_records_abort_before_any_upload(conversion, bad):
    client, data = conversion
    # ASCII-экранирование позволяет проверить недопустимый суррогат в JSON.
    data["ndjson"] = json.dumps(record()) + "\n" + json.dumps(bad)
    with pytest.raises(ValueError):
        convert(client)
    client.dictionaries.update.assert_not_called()


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        "text",
        42,
        {},
        {"key": "a", "record": None},
        {"record": {}},
        record(None),
        record(""),
        record("x" * 1025),
        record("oversized-value", "x" * 1161),
        record("unicode", "\ud800"),
    ],
)
def test_skip_invalid_new_records_reports_counts(conversion, bad):
    client, data = conversion
    data["ndjson"] = json.dumps(bad) + "\n" + json.dumps(record())
    status, report = convert(client, invalid_rows="skip", return_report=True)
    assert status == 200
    assert report == {
        "response": {"message": "server response"},
        "updated": True,
        "added": 1,
        "skipped": 1,
        "dropped": 0,
        "duplicates": 0,
        "replaced": 0,
    }
    assert data["uploads"] == [[["key", "value"], ["old", "keep"], ["new", "value"]]]


@pytest.mark.parametrize(
    "row",
    [
        ",empty\n",
        "old,second\n",
        "x" * 1161 + ",long\n",
        "large," + "x" * 1025 + "\n",
        "missing-column\n",
        "extra,column,unexpected\n",
    ],
)
def test_existing_invalid_rows_require_explicit_cleanup(conversion, row):
    client, data = conversion
    data["csv"] += row
    data["ndjson"] = ndjson(record())
    with pytest.raises(ValueError, match="clean_existing=True"):
        convert(client)
    client.dictionaries.update.assert_not_called()
    status, report = convert(client, clean_existing=True, return_report=True)
    assert status == 200 and report["dropped"] == 1 and report["added"] == 1
    assert data["uploads"] == [[["key", "value"], ["old", "keep"], ["new", "value"]]]


def test_cleanup_releases_invalid_key_and_preserves_first_valid_duplicate(conversion):
    client, data = conversion
    data["csv"] = "key,value\nrepair," + "x" * 1161 + "\nold,first\nold,second\n"
    data["ndjson"] = ndjson(record("repair", "fixed"), record("old", "new"))
    _, report = convert(client, clean_existing=True, return_report=True)
    assert (report["dropped"], report["added"], report["duplicates"]) == (2, 1, 1)
    assert data["uploads"] == [
        [["key", "value"], ["old", "first"], ["repair", "fixed"]]
    ]


def test_skipped_record_does_not_reserve_its_key(conversion):
    client, data = conversion
    data["ndjson"] = ndjson(
        record("new", "x" * 1025), record("new", "fixed"), record("new", "last")
    )
    _, report = convert(client, invalid_rows="skip", return_report=True)
    assert (report["skipped"], report["added"], report["duplicates"]) == (1, 1, 1)
    assert data["uploads"][0][-1] == ["new", "fixed"]


@pytest.mark.parametrize("source", ["", "\ufeff\n \n\t\n"])
def test_empty_al_and_cleanup_without_new_records(conversion, source):
    client, data = conversion
    data["ndjson"] = source
    assert convert(client) == (
        200,
        {"message": "Active list is empty", "updated": False},
    )
    client.dictionaries.update.assert_not_called()
    data["csv"] += "x" * 1161 + ",bad\n"
    _, report = convert(client, clean_existing=True, return_report=True)
    assert report["updated"] is True and report["added"] == 0 and report["dropped"] == 1
    assert data["uploads"] == [[["key", "value"], ["old", "keep"]]]


def test_blank_jsonl_and_custom_key_in_every_record(conversion):
    client, data = conversion
    data["ndjson"] = (
        "\ufeff\n"
        + ndjson(
            record("a", None, login=0), record("b"), record("c", "good", login="user")
        )
        + "\n \n"
    )
    with pytest.raises(ValueError):
        convert(client, active_list_key="login")
    _, report = convert(
        client, active_list_key="login", invalid_rows="skip", return_report=True
    )
    assert report["skipped"] == 1 and report["added"] == 2
    assert data["uploads"][0][1:] == [["old", "keep"], ["0", ""], ["user", "good"]]


def test_clear_ignores_old_rows_and_keeps_only_valid_new_rows(conversion):
    client, data = conversion
    data["csv"] += "x" * 1161 + ",bad\n"
    data["ndjson"] = ndjson(None, record())
    _, report = convert(client, clear=True, invalid_rows="skip", return_report=True)
    assert report["updated"] and report["skipped"] == 1 and report["dropped"] == 0
    assert data["uploads"] == [[["key", "value"], ["new", "value"]]]


def test_clear_with_all_invalid_records_cannot_erase_dictionary(conversion):
    client, data = conversion
    data["ndjson"] = ndjson(None, record(""))
    with pytest.raises(ValueError):
        convert(client, clear=True, invalid_rows="skip")
    client.dictionaries.update.assert_not_called()


def test_explicit_clear_of_empty_al_deletes_rows(conversion):
    client, data = conversion
    data["csv"] += "second,value\nold,duplicate\n"
    _, report = convert(client, clear=True, need_reload=1, return_report=True)
    assert report["updated"] and report["added"] == 0
    assert report["response"] == {"deleted": True}
    client.dictionaries.update.assert_not_called()
    assert client.dictionaries.delete_row.call_args_list == [
        call("dictionary", "old", need_reload=1),
        call("dictionary", "second", need_reload=1),
    ]


def test_cleanup_can_remove_all_existing_rows_with_empty_al(conversion):
    client, data = conversion
    data["csv"] = "key,value\nlong," + "x" * 1161 + "\n"
    _, report = convert(client, clean_existing=True, return_report=True)
    assert report["updated"] and report["dropped"] == 1
    client.dictionaries.update.assert_not_called()
    client.dictionaries.delete_row.assert_called_once_with(
        "dictionary", "long", need_reload=0
    )


def test_clearing_already_empty_dictionary_is_noop(conversion):
    client, data = conversion
    data["csv"] = "key,value\n"
    _, report = convert(client, clear=True, return_report=True)
    assert report["updated"] is False
    client.dictionaries.update.assert_not_called()
    client.dictionaries.delete_row.assert_not_called()


@pytest.mark.parametrize("bad", [",empty\n", 'bad,"unterminated'])
def test_clear_validates_entire_csv_before_deleting_rows(conversion, bad):
    client, data = conversion
    data["csv"] += bad
    with pytest.raises((ValueError, csv.Error)):
        convert(client, clear=True)
    client.dictionaries.delete_row.assert_not_called()


def test_clear_failure_stops_without_retry(conversion):
    client, data = conversion
    data["csv"] += "second,value\nthird,value\n"
    failure = APIError("delete failed", 403)
    client.dictionaries.delete_row.side_effect = [(200, {}), failure]
    with pytest.raises(APIError) as caught:
        convert(client, clear=True)
    assert caught.value is failure
    assert client.dictionaries.delete_row.call_count == 2


@pytest.mark.parametrize(
    "source", [ndjson(record("old", "ignored")), ndjson(None, record(""))]
)
def test_no_changes_avoid_upload(conversion, source):
    client, data = conversion
    data["ndjson"] = source
    _, report = convert(client, invalid_rows="skip", return_report=True)
    assert report["updated"] is False and report["added"] == 0
    client.dictionaries.update.assert_not_called()


def test_explicit_ascii_policy_and_lower_limit(conversion):
    client, data = conversion
    data["csv"] += "unicode,кириллица\n"
    data["ndjson"] = ndjson(
        record("unicode", "ASCII"),
        record("кириллица"),
        record("long", "a" * 256),
        record("boundary", "a" * 255),
    )
    _, report = convert(
        client,
        ascii_only=True,
        max_cell_len=255,
        clean_existing=True,
        invalid_rows="skip",
        return_report=True,
    )
    assert (report["dropped"], report["skipped"], report["added"]) == (1, 2, 2)
    assert data["uploads"][0][1:] == [
        ["old", "keep"],
        ["unicode", "ASCII"],
        ["boundary", "a" * 255],
    ]


@pytest.mark.parametrize(
    "option,value",
    [
        ("max_cell_len", 0),
        ("max_cell_len", -1),
        ("max_cell_len", True),
        ("max_cell_len", 1.5),
        ("max_cell_len", None),
        ("max_cell_len", "1024"),
        ("invalid_rows", "ignore"),
        ("invalid_rows", None),
        ("ascii_only", 1),
        ("clean_existing", "yes"),
        ("return_report", 1),
        ("on_conflict", "replace"),
        ("on_conflict", None),
        ("dry_run", 1),
        ("active_list_key", ""),
        ("active_list_key", None),
        ("columns", []),
        ("columns", {"": "source"}),
        ("columns", {"value": ""}),
        ("columns", {"value": None}),
        ("columns", {1: "source"}),
        ("timeout", 0),
        ("timeout", True),
        ("timeout", (1, -2)),
        ("timeout", float("inf")),
    ],
)
def test_invalid_options_fail_before_network(conversion, option, value):
    client, _ = conversion
    with pytest.raises(ValueError):
        convert(client, **{option: value})
    client.active_lists.export.assert_not_called()


@pytest.mark.parametrize("source", ['{"broken":', 'NaN\n{"broken":'])
def test_invalid_json_never_partially_updates_even_in_skip_mode(conversion, source):
    client, data = conversion
    data["ndjson"] = ndjson(record()) + "\n" + source
    with pytest.raises(ValueError, match="JSONL"):
        convert(client, invalid_rows="skip")
    client.dictionaries.update.assert_not_called()


@pytest.mark.parametrize("source", ["", "key,key\n", 'key,value\nold,"broken'])
def test_invalid_csv_is_not_repaired_by_guessing(conversion, source):
    client, data = conversion
    data["csv"] = source
    data["ndjson"] = ndjson(record())
    with pytest.raises((ValueError, csv.Error)):
        convert(client, clean_existing=True, invalid_rows="skip")
    client.dictionaries.update.assert_not_called()


@pytest.mark.parametrize(
    "response", [None, "text response", [], {"skipped": "server field"}]
)
def test_original_server_response_preserved(conversion, response):
    client, data = conversion
    data["ndjson"] = ndjson(record())
    client.dictionaries.update.side_effect = None
    client.dictionaries.update.return_value = (200, response)
    assert convert(client) == (200, response)
    _, report = convert(client, return_report=True)
    assert report["response"] is response and report["skipped"] == 0


def test_server_error_is_not_swallowed_or_retried(conversion):
    client, data = conversion
    data["ndjson"] = ndjson(record())
    failure = APIError("server rejected update", 400)
    client.dictionaries.update.side_effect = failure
    with pytest.raises(APIError) as caught:
        convert(client, invalid_rows="skip", clean_existing=True, return_report=True)
    assert caught.value is failure
    client.dictionaries.update.assert_called_once()


def test_validation_error_does_not_expose_contents(conversion):
    client, data = conversion
    marker = "sensitive-example-value"
    data["ndjson"] = ndjson(record("new", marker * 100))
    with pytest.raises(ValueError) as caught:
        convert(client)
    assert marker not in str(caught.value)


@pytest.mark.parametrize("version", ["3.4", "4.0", "4.1", "4.2"])
def test_update_replaces_matching_rows_and_preserves_other_rows(conversion, version):
    client, data = conversion
    client._version = version
    data["csv"] += 'unchanged,keep\n"quoted,key",before\n'
    data["ndjson"] = ndjson(
        record("old", "changed"),
        record("new", "added"),
        record("quoted,key", 'кириллица,"quote"\nline'),
        record("old", "ignored"),
    )
    _, report = convert(client, on_conflict="update", return_report=True)
    assert (report["added"], report["replaced"], report["duplicates"]) == (1, 2, 1)
    assert data["uploads"] == [
        [
            ["key", "value"],
            ["old", "changed"],
            ["unchanged", "keep"],
            ["quoted,key", 'кириллица,"quote"\nline'],
            ["new", "added"],
        ]
    ]
    assert not data["upload_path"].parent.exists()


def test_identical_updates_do_not_upload(conversion):
    client, data = conversion
    data["ndjson"] = ndjson(record("old", "keep"), record("old", "later"))
    _, report = convert(client, on_conflict="update", return_report=True)
    assert not report["updated"] and report["replaced"] == report["added"] == 0
    assert report["duplicates"] == 2
    client.dictionaries.update.assert_not_called()


def test_invalid_update_preserves_original_and_allows_later_valid_record(conversion):
    client, data = conversion
    data["ndjson"] = ndjson(record("old", "x" * 1025))
    _, report = convert(
        client, on_conflict="update", invalid_rows="skip", return_report=True
    )
    assert not report["updated"] and report["skipped"] == 1
    client.dictionaries.update.assert_not_called()
    data["ndjson"] += "\n" + ndjson(record("old", "fixed"))
    _, report = convert(
        client, on_conflict="update", invalid_rows="skip", return_report=True
    )
    assert report["replaced"] == 1 and report["skipped"] == 1
    assert data["uploads"][0][-1] == ["old", "fixed"]


@pytest.mark.parametrize(
    "csv_data", ["key,value\n", "key,value\nbad," + "x" * 1161 + "\n"]
)
def test_update_can_populate_empty_or_fully_cleaned_dictionary(conversion, csv_data):
    client, data = conversion
    data["csv"] = csv_data
    data["ndjson"] = ndjson(record())
    _, report = convert(
        client, on_conflict="update", clean_existing=True, return_report=True
    )
    assert report["added"] == 1 and report["replaced"] == 0 and report["updated"]
    assert data["uploads"] == [[["key", "value"], ["new", "value"]]]
    client.dictionaries.delete_row.assert_not_called()


def test_update_and_clear_replaces_all_rows(conversion):
    client, data = conversion
    data["csv"] += "removed,value\n"
    data["ndjson"] = ndjson(record("old", "changed"))
    _, report = convert(client, clear=True, on_conflict="update", return_report=True)
    assert report["added"] == 1 and report["replaced"] == 0
    assert data["uploads"] == [[["key", "value"], ["old", "changed"]]]


def test_column_mapping_uses_destination_names_and_preserves_key_selection(conversion):
    client, data = conversion
    data["csv"] = "host,описание,score,missing\n"
    data["ndjson"] = ndjson(
        record("outer", "unused", login="alice", title='слово,"цитата"', score=0)
    )
    columns = {"описание": "title"}
    convert(client, active_list_key="login", columns=columns)
    assert data["uploads"] == [
        [["host", "описание", "score", "missing"], ["alice", 'слово,"цитата"', "0", ""]]
    ]
    assert columns == {"описание": "title"}


@pytest.mark.parametrize("value,expected", [(None, ""), (False, "False"), (0, "0")])
def test_mapped_update_handles_empty_and_scalar_values(conversion, value, expected):
    client, data = conversion
    data["ndjson"] = ndjson(record("old", "ignored", source=value))
    _, report = convert(
        client, on_conflict="update", columns={"value": "source"}, return_report=True
    )
    assert report["replaced"] == 1
    assert data["uploads"][0][-1] == ["old", expected]


@pytest.mark.parametrize("columns", [{"missing": "value"}, {"key": "login"}])
def test_mapping_rejects_unknown_columns_and_key_column(conversion, columns):
    client, data = conversion
    data["ndjson"] = ndjson(record())
    with pytest.raises(ValueError, match="columns"):
        convert(client, columns=columns)
    client.dictionaries.update.assert_not_called()
    client.dictionaries.delete_row.assert_not_called()


def test_mapping_validates_selected_value(conversion):
    client, data = conversion
    data["ndjson"] = ndjson(record("old", "short", source="x" * 1025))
    with pytest.raises(ValueError):
        convert(client, on_conflict="update", columns={"value": "source"})
    client.dictionaries.update.assert_not_called()


@pytest.mark.parametrize("policy", ["keep", "update"])
@pytest.mark.parametrize("clear", [False, True])
def test_dry_run_reports_same_plan_as_real_conversion_without_writes(
    conversion, policy, clear
):
    client, data = conversion
    data["csv"] += "long," + "x" * 1161 + "\n"
    data["ndjson"] = ndjson(record("old", "changed"), record("new", "new"), None)
    options = dict(
        on_conflict=policy, clear=clear, clean_existing=True, invalid_rows="skip"
    )
    status, plan = convert(client, dry_run=True, **options)
    assert status == 200 and plan["dry_run"] and plan["would_update"]
    assert plan["updated"] is False and plan["response"] is None
    client.dictionaries.update.assert_not_called()
    client.dictionaries.delete_row.assert_not_called()
    _, applied = convert(client, return_report=True, **options)
    for key in ["added", "replaced", "skipped", "dropped", "duplicates"]:
        assert plan[key] == applied[key]


@pytest.mark.parametrize("clear", [False, True])
@pytest.mark.parametrize("source", ["key,value\n", "key,value\nold,keep\n"])
def test_dry_run_of_empty_al_and_clear_never_deletes(conversion, clear, source):
    client, data = conversion
    data["csv"] = source
    _, report = convert(client, clear=clear, dry_run=True)
    assert report["would_update"] is (clear and "old" in source)
    assert report["updated"] is False
    client.dictionaries.delete_row.assert_not_called()
    client.dictionaries.update.assert_not_called()


def test_dry_run_of_cleanup_predicts_deletion(conversion):
    client, data = conversion
    data["csv"] = "key,value\nlong," + "x" * 1161 + "\n"
    _, report = convert(client, dry_run=True, clean_existing=True, on_conflict="update")
    assert report["would_update"] and report["dropped"] == 1
    client.dictionaries.delete_row.assert_not_called()


@pytest.mark.parametrize("options", [{}, {"clear": True, "invalid_rows": "skip"}])
def test_dry_run_enforces_same_validation_as_write(conversion, options):
    client, data = conversion
    data["ndjson"] = ndjson(None)
    with pytest.raises(ValueError):
        convert(client, dry_run=True, **options)
    client.dictionaries.update.assert_not_called()
    client.dictionaries.delete_row.assert_not_called()


@pytest.mark.parametrize("mode", ["update", "clear", "dry_run"])
@pytest.mark.parametrize("timeout", [None, 120, (3, 120)])
def test_timeout_reaches_every_http_request(monkeypatch, mode, timeout):
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        path = urlsplit(kwargs["url"]).path
        if "/activeLists/export/" in path:
            body, content_type = '{"id":"export"}', "application/json"
        elif path.endswith("/download/export"):
            body = "" if mode == "clear" else ndjson(record("old", "changed"))
            content_type = "application/octet-stream"
        elif path.endswith("/dictionaries"):
            body, content_type = "key,value\nold,keep\nsecond,value\n", "text/csv"
        else:
            assert path.endswith(("/dictionaries/update", "/dictionaries/delete_row"))
            body, content_type = "{}", "application/json"
        return make_response(body, 200, content_type)

    with RestClient(
        "example.invalid", "test-token", version="4.2", timeout=11
    ) as client:
        monkeypatch.setattr(client.session, "request", request)
        convert(
            client,
            on_conflict="update",
            timeout=timeout,
            clear=mode == "clear",
            dry_run=mode == "dry_run",
        )
        assert client.timeout == 11
    assert all(
        call["timeout"] == (11 if timeout is None else timeout) for call in calls
    )
    assert len(calls) == {"update": 4, "clear": 5, "dry_run": 3}[mode]
    if mode == "dry_run":
        assert all(call["method"] == "GET" for call in calls)


def test_legacy_positional_arguments_still_work(conversion):
    client, data = conversion
    data["ndjson"] = ndjson(record("outer", login="custom"))
    result = client.active_lists.to_dictionary(
        "correlator", "list", "dictionary", "login", 1, False
    )
    assert result == (200, {"message": "server response"})
    assert data["uploads"][0][-1] == ["custom", "value"]
    assert client.dictionaries.update.call_args.kwargs["need_reload"] == 1
