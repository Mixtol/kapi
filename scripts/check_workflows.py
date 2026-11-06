"""Проверки на стенде; изменения ограничены ресурсами текущего запуска."""

import argparse
import csv
import json
import logging
import os
import sys
import tempfile
import uuid
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kuma import APIError, PrivateClient, RestClient
from kuma.rest._pagination import iter_pages
from scripts.check_stand import (
    Checks,
    StandConfig,
    archive_password,
    matching_version,
    successful,
)


def require(value):
    if not value:
        raise AssertionError("Результат операции не соответствует ожидаемому состоянию")


def read_checks(client, checks, directory):
    def report():
        path = Path(directory) / "rules.csv"
        result = successful(client.resources.export_rules_csv(path))
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            require(
                reader.fieldnames
                == ["Название", "Количество тенантов", "Тенанты", "Корреляторы"]
            )
            require(sum(1 for _ in reader) == result["rows"])
        return result

    result = checks.run("public.csv_report", report)
    if result:
        print(
            json.dumps(
                {
                    "report_counts": {
                        key: result[key] for key in ("rules", "rows", "bindings")
                    }
                }
            ),
            flush=True,
        )

    def bindings():
        first = next(client.resources.iter_rule_bindings(), None)
        require(first)
        rows = successful(client.resources.get_bound_correlators(first["ruleID"]))
        require(first["correlatorID"] in {row["id"] for row in rows})

    checks.run("public.bound_correlators", bindings)


def mutation_checks(client, private, checks, directory, prefix, ledger):
    tenants = [
        row
        for row in iter_pages(client.tenants.search)
        if row.get("name", "").lower() != "shared"
    ]
    require(len(tenants) >= 2)
    source_tenant, target_tenant = tenants[0]["id"], tenants[1]["id"]

    def remember(row):
        require(isinstance(row, dict) and row.get("id"))
        ledger.append(
            {"kind": row["kind"], "id": row["id"], "tenantID": row["tenantID"]}
        )
        return row

    def create(kind, payload, tenant, suffix):
        payload = deepcopy(payload)
        payload.update(id="", name=prefix + suffix)
        return remember(
            successful(
                client.resources.create(
                    kind,
                    {
                        "kind": kind,
                        "name": prefix + suffix,
                        "tenantID": tenant,
                        "payload": payload,
                    },
                )
            )
        )

    def dictionary(value):
        return {
            "kind": "table",
            "tableDict": {
                "columnsByName": {"key": 0, "value": 1},
                "rows": [["kapi", value]],
            },
        }

    source = checks.run(
        "public.create_source_fixture",
        lambda: create(
            "dictionary", dictionary("source"), source_tenant, "-dictionary"
        ),
    )
    target = checks.run(
        "public.create_target_fixture",
        lambda: create("dictionary", dictionary("local"), target_tenant, "-dictionary"),
    )
    if source and target:

        def cross_tenant():
            before = {
                r["id"]
                for r in client.resources.iter_search(
                    kind="dictionary", name=prefix, tenantID=target_tenant
                )
            }
            rows = list(
                client.resources.iter_copy_to(
                    client,
                    [source["id"]],
                    source_tenant,
                    target_tenant,
                    password=archive_password(),
                    batch_size=1,
                )
            )
            after = {
                r["id"]
                for r in client.resources.iter_search(
                    kind="dictionary", name=prefix, tenantID=target_tenant
                )
            }
            require(len(rows) == 1 and len(after - before) == 1)

        checks.run("public.copy_cross_tenant", cross_tenant)
        for policy in ("preserve", "replace"):

            def transfer(policy=policy):
                original_export = client.resources.export
                current = successful(client.resources.get("dictionary", source["id"]))
                current["description"] = "source"
                successful(client.resources.put("dictionary", source["id"], current))

                def export_then_local_change(*args, **kwargs):
                    result = original_export(*args, **kwargs)
                    client.resources.export = original_export
                    current = successful(
                        client.resources.get("dictionary", source["id"])
                    )
                    current["description"] = "local"
                    successful(
                        client.resources.put("dictionary", source["id"], current)
                    )
                    return result

                client.resources.export = export_then_local_change
                try:
                    rows = list(
                        client.resources.iter_copy_to(
                            client,
                            [source["id"]],
                            source_tenant,
                            source_tenant,
                            password=archive_password(),
                            on_conflict=policy,
                            backup_directory=directory,
                            batch_size=1,
                        )
                    )
                finally:
                    client.resources.export = original_export
                require(len(rows) == 1 and rows[0]["backup_path"])
                current = successful(client.resources.get("dictionary", source["id"]))
                value = current["description"]
                require(value == ("local" if policy == "preserve" else "source"))

            checks.run("public.copy_conflicts_" + policy, transfer)

    def rule_and_correlator():
        sample = next(client.resources.iter_search(kind="correlationRule"))
        rule_template = successful(
            client.resources.get("correlationRule", sample["id"])
        )
        # Старые встроенные правила содержат пустые фильтры обогащения, недопустимые
        # в 3.4. Тестовый ресурс не обрабатывает события и не требует обогащения.
        for action in rule_template["payload"].get("actions", {}).values():
            action["enrichment"] = []
        rule = create(
            "correlationRule", rule_template["payload"], source_tenant, "-rule"
        )
        # Создаётся только конфигурация; сервисы не создаются и не запускаются.
        corr_template = next(client.resources.iter_correlators())
        payload = deepcopy(corr_template["payload"])
        payload.update(
            rules=[], destinations=[], activeLists=[], enrichment=[], responses=[]
        )
        if "contextTables" in payload:
            payload["contextTables"] = []
        corr = create("correlator", payload, source_tenant, "-correlator")
        rows = list(
            client.resources.iter_update_correlators([corr["id"]], [rule["id"]])
        )
        require(rows[0]["status"] < 300)
        bound = successful(
            client.resources.get_bound_correlators(rule["id"], [source_tenant])
        )
        require(corr["id"] in {row["id"] for row in bound})
        list(
            client.resources.iter_update_correlators(
                [corr["id"]], [rule["id"]], action="unlink"
            )
        )
        require(
            not successful(
                client.resources.get_bound_correlators(rule["id"], [source_tenant])
            )
        )
        template = deepcopy(rule)
        template["name"] = prefix + "-synced"
        successful(client.resources.sync_correlation_rule(rule["id"], template))
        updated = successful(client.resources.get("correlationRule", rule["id"]))
        require(updated["name"] == template["name"] and updated["id"] == rule["id"])
        variables_template = deepcopy(corr)
        variables_template["payload"]["variables"] = []
        successful(
            client.resources.copy_correlator_variables(corr["id"], variables_template)
        )
        require(
            successful(client.resources.get("correlator", corr["id"]))["payload"].get(
                "variables"
            )
            in ([], None)
        )
        require(successful(client.services.reload_resource(corr["id"])) == [])

    checks.run("public.rule_sync_variables_bind_unbind", rule_and_correlator)

    def alerting_noop():
        settings = private._rows(successful(private.get_settings()))
        for setting in settings:
            details = successful(private.get_settings_by_id(setting["id"]))
            for rule in details.get("segmentationRules") or []:
                if rule.get("correlationRuleIDs"):
                    # Уже связанные ID позволяют выполнить проверку без записи.
                    original_send = private._send

                    def readonly(method, endpoint, **kwargs):
                        require(method == "GET")
                        return original_send(method, endpoint, **kwargs)

                    private._send = readonly
                    try:
                        rows = list(
                            private.iter_update_alerting(
                                [setting["tenantID"]],
                                [rule["correlationRuleIDs"][0]],
                                rule_name=rule["name"],
                            )
                        )
                        require(rows and all(row["status"] == 200 for row in rows))
                    finally:
                        private._send = original_send
                    return True
        return False

    if checks.run("private.alerting_existing_link_noop", alerting_noop) is False:
        checks.skip(
            "private.alerting_noop: нет правила сегментации с существующими связями"
        )

    def cached_session():
        from cryptography.fernet import Fernet

        from kuma.private.session_cache import PrivateSessionCache

        cache = PrivateSessionCache(
            Path(directory) / "session.bin", Fernet.generate_key()
        )
        cache.save(private)
        with cache.open_client(
            private.url,
            private.username,
            private.password,
            version=private.version,
            verify=private.verify,
            timeout=private.timeout,
            logger=private.logger,
        ) as restored:
            require(restored.whoami()["id"] == private.whoami()["id"])

    checks.run("private.encrypted_session_restore", cached_session)


def cleanup(client, private, checks, prefix, ledger):
    # ID созданных ресурсов и уникальный префикс импорта относятся к текущему запуску.
    known = {(row["kind"], row["id"]) for row in ledger}
    for kind in ("correlator", "correlationRule", "dictionary"):

        def remove(kind=kind):
            rows = list(client.resources.iter_search(kind=kind, name=prefix))
            ids = {row["id"] for row in rows if row["name"].startswith(prefix)}
            ids.update(id_ for type_, id_ in known if type_ == kind)
            for id_ in ids:
                _, status = private.delete_resource(id_, kind)
                require(200 <= status < 300 or status == 404)
            remaining = [
                row
                for row in client.resources.iter_search(kind=kind, name=prefix)
                if row["name"].startswith(prefix)
            ]
            require(not remaining)

        checks.run("cleanup." + kind, remove)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, choices=["3.4", "4.2"])
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument(
        "--mutations",
        action="store_true",
        help="Создать временные ресурсы и удалить их через приватный API",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    from dotenv import dotenv_values

    config = StandConfig.from_mapping(
        {**dotenv_values(args.env_file), **os.environ},
        args.version,
        base_dir=args.env_file.resolve().parent,
        public_only=not args.mutations,
    )
    logger = logging.Logger("kapi.workflow-check")
    logger.addHandler(logging.NullHandler())
    checks = Checks()
    prefix = "kapi-workflows-" + uuid.uuid4().hex[:12]
    ledger = []
    with RestClient(
        config.url, config.token, config.verify, (5, 120), logger, config.version
    ) as client:
        matching_version(client, config.version)
        with tempfile.TemporaryDirectory(prefix=prefix) as directory:
            read_checks(client, checks, directory)
            if args.mutations:
                with PrivateClient(
                    config.private_url,
                    config.username,
                    config.password,
                    version=config.version,
                    verify=config.verify,
                    timeout=(5, 120),
                    logger=logger,
                ) as private:
                    try:
                        matching_version(private, config.version)
                        checks.run(
                            "mutations",
                            lambda: mutation_checks(
                                client, private, checks, directory, prefix, ledger
                            ),
                        )
                    finally:
                        cleanup(client, private, checks, prefix, ledger)
                        checks.run("private.logout", private.logout)
    result = {
        "version": config.version,
        "tls_verified": True,
        "prefix": prefix,
        "created": len(ledger),
        "checks": checks.rows,
        "failed": sum(row.get("passed") is False for row in checks.rows),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps({"version": config.version, "failed": result["failed"]}), flush=True
    )
    return int(bool(result["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
