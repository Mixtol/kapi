"""Отчёт по правилам через публичный API с группировкой на диске и атомарной записью."""

import csv
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from kuma.rest.resource_workflows import tenant_filter


def export_rules_csv(
    resources,
    filepath,
    *,
    tenant_ids=None,
    include_shared=True,
    name_contains="#",
    strip_tenant_prefix=True,
    delimiter=",",
):
    """Вернуть (200, {path, rules, rows, bindings}); хранить одну конфигурацию в памяти.

    SQLite хранит метаданные и выполняет объединение на диске с кешем 8 МиБ.
    Одновременно собирается одна группа CSV. Подсчитываются уникальные ID тенантов,
    а не копии правил. tenant_ids фильтрует владельцев правил; связи учитываются
    во всех доступных корреляторах, включая межтенантные связи с правилами Shared.
    Пустые имена тенантов дополняются из публичного списка. Префикс удаляется
    до первого '#' включительно; False сохраняет полное имя для группировки.
    """
    if not isinstance(name_contains, str):
        raise ValueError("name_contains должен быть строкой")
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in "\r\n\x00":
        raise ValueError(
            "delimiter должен быть одним допустимым символом разделителя CSV"
        )
    filters = tenant_filter(tenant_ids)
    allowed = set(filters.get("tenantID", []))
    if name_contains:
        filters["name"] = (
            re.escape(name_contains)
            if resources.contract_version == "3.4"
            else name_contains
        )
    destination = Path(filepath)
    temporary = None
    counts = {"path": os.fspath(filepath), "rules": 0, "rows": 0, "bindings": 0}
    try:
        with tempfile.TemporaryDirectory(prefix="kapi-report-") as directory:
            with closing(sqlite3.connect(str(Path(directory) / "index.sqlite"))) as db:
                db.executescript("""
                    PRAGMA cache_size=-8192;
                    PRAGMA temp_store=FILE;
                    CREATE TABLE tenants(id TEXT PRIMARY KEY, name TEXT NOT NULL);
                    CREATE TABLE rules(id TEXT PRIMARY KEY, name TEXT NOT NULL,
                                       tenant TEXT NOT NULL, tenant_name TEXT NOT NULL);
                    CREATE INDEX rules_name ON rules(name);
                    CREATE TABLE bindings(rule TEXT NOT NULL, correlator TEXT NOT NULL,
                                          name TEXT NOT NULL, PRIMARY KEY(rule,correlator));
                """)
                from kuma.rest._pagination import iter_pages

                for tenant in iter_pages(resources._base.tenants.search):
                    db.execute(
                        "INSERT OR REPLACE INTO tenants VALUES (?,?)",
                        (tenant["id"], tenant.get("name") or tenant["id"]),
                    )
                for rule in resources.iter_search(kind="correlationRule", **filters):
                    if allowed and rule.get("tenantID") not in allowed:
                        continue
                    name = rule["name"]
                    if name_contains.casefold() not in name.casefold():
                        continue
                    tenant_id = rule["tenantID"]
                    tenant = db.execute(
                        "SELECT name FROM tenants WHERE id=?", (tenant_id,)
                    ).fetchone()
                    tenant_name = (
                        tenant[0] if tenant else rule.get("tenantName")
                    ) or tenant_id
                    if not include_shared and tenant_name.casefold() == "shared":
                        continue
                    if strip_tenant_prefix and "#" in name:
                        name = name.split("#", 1)[1]
                    db.execute(
                        "INSERT OR REPLACE INTO rules VALUES (?,?,?,?)",
                        (rule["id"], name, tenant_id, tenant_name),
                    )
                counts["rules"] = db.execute("SELECT count(*) FROM rules").fetchone()[0]
                # Нет запросов по каждому правилу; пустая выборка не запускает обход.
                if counts["rules"]:
                    for binding in resources.iter_rule_bindings():
                        db.execute(
                            "INSERT OR IGNORE INTO bindings SELECT ?,?,? WHERE EXISTS "
                            "(SELECT 1 FROM rules WHERE id=?)",
                            (
                                binding["ruleID"],
                                binding["correlatorID"],
                                binding["correlatorName"],
                                binding["ruleID"],
                            ),
                        )
                db.commit()
                counts["bindings"] = db.execute(
                    "SELECT count(*) FROM bindings"
                ).fetchone()[0]
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8-sig",
                    newline="",
                    dir=destination.parent,
                    prefix="." + destination.name + ".",
                    suffix=".part",
                    delete=False,
                ) as output:
                    temporary = Path(output.name)
                    writer = csv.writer(output, delimiter=delimiter)
                    writer.writerow(
                        ["Название", "Количество тенантов", "Тенанты", "Корреляторы"]
                    )
                    for (name,) in db.execute(
                        "SELECT DISTINCT name FROM rules ORDER BY name"
                    ):
                        tenants = db.execute(
                            "SELECT DISTINCT tenant,tenant_name FROM rules WHERE name=? "
                            "ORDER BY tenant_name,tenant",
                            (name,),
                        ).fetchall()
                        correlators = db.execute(
                            "SELECT DISTINCT b.correlator,b.name FROM bindings b "
                            "JOIN rules r ON r.id=b.rule WHERE r.name=? ORDER BY b.name,b.correlator",
                            (name,),
                        )
                        writer.writerow(
                            [
                                name,
                                len(tenants),
                                ", ".join(t[1] for t in tenants),
                                ", ".join(row[1] for row in correlators),
                            ]
                        )
                        counts["rows"] += 1
            os.replace(temporary, destination)
            temporary = None
        return 200, counts
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
