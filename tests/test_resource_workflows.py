import csv
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

from kuma import APIError, RestClient


@pytest.fixture(params=["3.4", "4.2"])
def client(request):
    with RestClient(
        "https://example.invalid", "test-token", version=request.param
    ) as api:
        yield api


def resource(id_, kind="correlator", **payload):
    return {"id": id_, "kind": kind, "name": id_, "tenantID": "t", "payload": payload}


def test_pagination_is_lazy_and_rejects_reordered_repeated_pages(client, monkeypatch):
    search = Mock(
        side_effect=[
            (200, [{"id": "a"}, {"id": "b"}]),
            (200, [{"id": "b"}, {"id": "a"}]),
        ]
    )
    monkeypatch.setattr(client.resources, "search", search)
    iterator = client.resources.iter_search(kind="filter")
    assert search.call_count == 0
    assert next(iterator)["id"] == "a"
    assert next(iterator)["id"] == "b"
    with pytest.raises(APIError, match="повторную страницу"):
        next(iterator)
    assert search.call_args.kwargs == {"page": 2, "kind": "filter"}


@pytest.mark.parametrize("value", [{}, [{"name": "missing-id"}], [None]])
def test_pagination_rejects_invalid_collection(client, monkeypatch, value):
    monkeypatch.setattr(client.resources, "search", Mock(return_value=(200, value)))
    with pytest.raises(APIError):
        list(client.resources.iter_search())


def report_transport(client, monkeypatch, *, failure=False):
    rules = [
        {"id": "r1", "name": 'a#Правило,"в кавычках"\nстрока', "tenantID": "a"},
        {"id": "r2", "name": 'b#Правило,"в кавычках"\nстрока', "tenantID": "b"},
        {"id": "r3", "name": "s#Свободное правило", "tenantID": "s", "tenantName": ""},
    ]
    requests = []

    def send(method, endpoint, **kwargs):
        requests.append((method, endpoint, kwargs))
        assert method == "GET" and "private" not in endpoint
        page = kwargs.get("params", {}).get("page", 1)
        if endpoint == "tenants":
            return 200, (
                [
                    {"id": "a", "name": "Alpha"},
                    {"id": "b", "name": "Beta"},
                    {"id": "s", "name": "Shared"},
                ]
                if page == 1
                else []
            )
        if endpoint == "resources":
            if kwargs["params"]["kind"] == "correlationRule":
                return 200, rules[page - 1 : page]
            return 200, ([{"id": "c1"}, {"id": "c2"}] if page == 1 else [])
        if endpoint == "resources/correlator/c1":
            return 200, resource("c1", rules=[{"id": "r1"}, {"id": "r1"}, {"id": "r2"}])
        if endpoint == "resources/correlator/c2":
            if failure:
                raise APIError("denied", 403)
            return 200, resource("c2", rules=[{"id": "r2"}, {"id": "unknown"}])
        raise AssertionError("Unexpected route")

    monkeypatch.setattr(client, "_make_request", send)
    return requests


def test_csv_groups_on_disk_and_reads_each_correlator_once(
    client, monkeypatch, tmp_path
):
    calls = report_transport(client, monkeypatch)
    path = tmp_path / "rules.csv"
    status, summary = client.resources.export_rules_csv(path)
    assert status == 200
    assert summary == {"path": str(path), "rules": 3, "rows": 2, "bindings": 3}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows == [
        {
            "Название": 'Правило,"в кавычках"\nстрока',
            "Количество тенантов": "2",
            "Тенанты": "Alpha, Beta",
            "Корреляторы": "c1, c2",
        },
        {
            "Название": "Свободное правило",
            "Количество тенантов": "1",
            "Тенанты": "Shared",
            "Корреляторы": "",
        },
    ]
    assert sum(path.startswith("resources/correlator/") for _, path, _ in calls) == 2
    assert not any("correlationRule/" in path for _, path, _ in calls)


def test_csv_filters_shared_by_resolved_tenant_and_preserves_full_name(
    client, monkeypatch, tmp_path
):
    report_transport(client, monkeypatch)
    path = tmp_path / "rules.csv"
    _, summary = client.resources.export_rules_csv(
        path, include_shared=False, strip_tenant_prefix=False
    )
    assert summary["rules"] == 2 and summary["rows"] == 2
    assert "Shared" not in path.read_text(encoding="utf-8-sig")


def test_failed_csv_keeps_destination_and_leaves_no_partial_file(
    client, monkeypatch, tmp_path
):
    report_transport(client, monkeypatch, failure=True)
    path = tmp_path / "report.csv"
    path.write_text("previous", encoding="utf-8")
    with pytest.raises(APIError):
        client.resources.export_rules_csv(path)
    assert path.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [path]


def test_bound_lookup_is_public_and_deduplicates(client, monkeypatch):
    calls = report_transport(client, monkeypatch)
    assert client.resources.get_bound_correlators("r1") == (
        200,
        [{"id": "c1", "name": "c1", "tenantID": "t"}],
    )
    assert sum(path.startswith("resources/correlator/") for _, path, _ in calls) == 2
    with pytest.raises(ValueError):
        client.resources.get_bound_correlators("r1", tenant_ids=[])


def test_rule_sync_preserves_custom_and_target_identity(client, monkeypatch):
    original = resource(
        "target",
        "correlationRule",
        name="target",
        selectors=[
            {
                "filter": "target-condition",
                "variables": [
                    {"name": "CustomX", "value": "local"},
                    {"name": "old", "value": "old"},
                ],
            }
        ],
        actions={"onEvent": {"noAlert": False, "local": "keep"}},
        keepPolicy=0,
    )
    template = resource(
        "source",
        "correlationRule",
        selectors=[
            {
                "filter": "other-condition",
                "variables": [
                    {"name": "CustomX", "value": "upstream"},
                    {"name": "new", "value": "new"},
                ],
            }
        ],
        actions={"onEvent": {"noAlert": True}},
        keepPolicy=1,
    )
    before = deepcopy((original, template))
    monkeypatch.setattr(client.resources, "get", Mock(return_value=(200, original)))
    put = Mock(return_value=(200, None))
    monkeypatch.setattr(client.resources, "put", put)
    client.resources.sync_correlation_rule("target", template)
    body = put.call_args.args[2]
    assert body["id"] == "target" and body["tenantID"] == "t"
    assert body["payload"]["selectors"][0] == {
        "filter": "target-condition",
        "variables": [
            {"name": "new", "value": "new"},
            {"name": "CustomX", "value": "local"},
        ],
    }
    assert body["payload"]["actions"]["onEvent"] == {"noAlert": True, "local": "keep"}
    assert (original, template) == before
    template["payload"]["selectors"] = []
    with pytest.raises(ValueError, match="Количество селекторов"):
        client.resources.sync_correlation_rule("target", template)
    assert put.call_count == 1


def test_variable_copy_and_idempotence(client, monkeypatch):
    original = resource("target", variables=[{"name": "old"}], workers=4)
    template = resource("source", variables=[{"name": "new"}])
    monkeypatch.setattr(client.resources, "get", Mock(return_value=(200, original)))
    put = Mock(return_value=(200, None))
    monkeypatch.setattr(client.resources, "put", put)
    client.resources.copy_correlator_variables("target", template)
    assert put.call_args.args[2]["payload"] == {
        "variables": [{"name": "new"}],
        "workers": 4,
    }
    assert original["payload"]["variables"] == [{"name": "old"}]
    assert client.resources.copy_correlator_variables("target", original) == (
        200,
        original,
    )
    assert put.call_count == 1


def test_bulk_binding_is_incremental_and_reload_uses_service_id(client, monkeypatch):
    link = Mock(return_value=(200, {}))
    monkeypatch.setattr(client.resources, "link_rules_to_correlator", link)
    monkeypatch.setattr(
        client.services,
        "search",
        Mock(
            side_effect=[
                (
                    200,
                    [
                        {"id": "service", "resourceID": "corr"},
                        {"id": "unrelated", "resourceID": "other"},
                    ],
                ),
                (200, []),
            ]
        ),
    )
    reload = Mock(return_value=(204, None))
    monkeypatch.setattr(client.services, "reload", reload)
    rows = client.resources.iter_update_correlators(
        ["corr", "later"], ["r", "r"], reload=True
    )
    assert next(rows) == {
        "correlatorID": "corr",
        "status": 200,
        "services": [{"id": "service", "status": 204}],
    }
    link.assert_called_once_with("corr", ["r"])
    reload.assert_called_once_with("service")
    rows.close()


def transfer_clients(
    client, monkeypatch, tmp_path, *, conflict=True, broken_retry=False
):
    source = client.resources
    target = Mock()
    destination = target.resources
    monkeypatch.setattr(
        source, "export", Mock(return_value=(200, {"fileID": "export"}))
    )
    monkeypatch.setattr(
        source,
        "download",
        Mock(
            side_effect=lambda id_, filepath, **kw: Path(filepath).write_bytes(
                b"archive"
            )
        ),
    )
    destination.upload.return_value = (200, {"id": "uploaded"})
    destination.toc.side_effect = (
        [
            (200, {"folders": [{"resources": [{"id": "candidate"}]}]}),
            (
                200,
                {
                    "folders": [
                        {
                            "resources": [
                                {"id": "stored"},
                                {"id": "unrelated-dependency"},
                            ]
                        }
                    ]
                },
            ),
        ]
        if conflict
        else [(200, {"folders": [{"resources": [{"id": "candidate"}]}]})] * 5
    )
    error = APIError(
        "conflict",
        409,
        response_data={
            "details": json.dumps(
                {
                    "conflicts": [
                        {
                            "candidateID": "candidate",
                            "storedResourceID": "stored",
                            "storedResourceTenantID": "original-tenant",
                        }
                    ]
                }
            )
        },
    )
    destination.import_data.side_effect = (
        [error, APIError("retry failed", 500) if broken_retry else (200, {}), (200, {})]
        if conflict
        else [(200, {})] * 5
    )
    destination.export.return_value = (200, {"fileID": "backup"})
    destination.download.side_effect = lambda id_, filepath, **kw: Path(
        filepath
    ).write_bytes(b"encrypted-backup")
    return target


@pytest.mark.parametrize("policy", ["error", "replace", "preserve"])
def test_copy_conflict_policy_and_persistent_backup(
    client, monkeypatch, tmp_path, policy
):
    target = transfer_clients(client, monkeypatch, tmp_path)
    run = client.resources.iter_copy_to(
        target,
        ["source"],
        "source-tenant",
        "target-tenant",
        password="test-password",
        on_conflict=policy,
        backup_directory=tmp_path,
    )
    if policy == "error":
        with pytest.raises(APIError):
            list(run)
        target.resources.export.assert_not_called()
        assert list(tmp_path.iterdir()) == []
    else:
        result = next(run)
        assert Path(result["backup_path"]).read_bytes() == b"encrypted-backup"
        assert result["conflicts_restored"] is (policy == "preserve")
        assert target.resources.import_data.call_count == (
            3 if policy == "preserve" else 2
        )
        assert target.resources.import_data.call_args_list[1].args[3] == {
            "candidate": 2
        }
        assert target.resources.export.call_args.args[1] == "original-tenant"
        if policy == "preserve":
            assert target.resources.import_data.call_args.args[1] == "original-tenant"
            assert target.resources.import_data.call_args.args[3] == {"stored": 2}


def test_preserve_restores_after_failed_retry_and_reports_recovery_path(
    client, monkeypatch, tmp_path
):
    target = transfer_clients(client, monkeypatch, tmp_path, broken_retry=True)
    with pytest.raises(APIError) as caught:
        list(
            client.resources.iter_copy_to(
                target,
                ["source"],
                "s",
                "t",
                password="test",
                on_conflict="preserve",
                backup_directory=tmp_path,
            )
        )
    assert caught.value.conflicts_restored
    assert Path(caught.value.backup_path).exists()
    assert target.resources.import_data.call_count == 3


def test_copy_consumes_only_one_batch_before_yield(client, monkeypatch, tmp_path):
    target = transfer_clients(client, monkeypatch, tmp_path, conflict=False)
    consumed = []

    def ids():
        for i in range(5):
            consumed.append(i)
            yield str(i)

    iterator = client.resources.iter_copy_to(
        target, ids(), "s", "t", password="test", batch_size=2
    )
    assert next(iterator)["resourceIDs"] == ["0", "1"]
    assert consumed == [0, 1]
    iterator.close()


def test_report_memory_does_not_scale_with_all_rule_metadata(
    client, monkeypatch, tmp_path
):
    import tracemalloc

    monkeypatch.setattr(
        client.tenants,
        "search",
        Mock(
            side_effect=[
                (200, [{"id": "t", "name": "Tenant"}]),
                (200, []),
            ]
        ),
    )

    def rules(**filters):
        for index in range(20000):
            yield {
                "id": str(index),
                "name": "t#" + str(index).zfill(6) + "x" * 100,
                "tenantID": "t",
                "description": "large metadata " + "z" * 300,
            }

    monkeypatch.setattr(client.resources, "iter_search", rules)
    monkeypatch.setattr(client.resources, "iter_rule_bindings", lambda: iter(()))
    tracemalloc.start()
    try:
        _, result = client.resources.export_rules_csv(tmp_path / "large.csv")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result["rules"] == result["rows"] == 20000
    # Хранение всех строк превысило бы лимит в несколько раз. Нативный кеш SQLite
    # ограничен отдельно: параметр cache_size задаёт размер 8 МиБ.
    assert peak < 3 * 1024 * 1024


def test_preserve_attempts_every_tenant_restore_and_retains_backups(
    client, monkeypatch, tmp_path
):
    target = transfer_clients(client, monkeypatch, tmp_path)
    target.resources.toc.side_effect = [
        (200, {"folders": [{"resources": [{"id": "a"}, {"id": "b"}]}]}),
        (200, {"folders": [{"resources": [{"id": "stored-a"}]}]}),
        (200, {"folders": [{"resources": [{"id": "stored-b"}]}]}),
    ]
    error = APIError(
        "conflict",
        409,
        response_data={
            "details": {
                "conflicts": [
                    {
                        "candidateID": "a",
                        "storedResourceID": "stored-a",
                        "storedResourceTenantID": "tenant-a",
                    },
                    {
                        "candidateID": "b",
                        "storedResourceID": "stored-b",
                        "storedResourceTenantID": "tenant-b",
                    },
                ]
            }
        },
    )
    target.resources.import_data.side_effect = [
        error,
        (200, {}),
        APIError("denied", 403),
        (200, {}),
    ]
    with pytest.raises(APIError) as caught:
        list(
            client.resources.iter_copy_to(
                target,
                ["source"],
                "s",
                "t",
                password="test",
                on_conflict="preserve",
                backup_directory=tmp_path,
            )
        )
    assert not caught.value.conflicts_restored
    assert len(caught.value.backups) == 2
    assert all(Path(row["path"]).exists() for row in caught.value.backups)
    assert [
        call.args[1] for call in target.resources.import_data.call_args_list[-2:]
    ] == ["tenant-a", "tenant-b"]
