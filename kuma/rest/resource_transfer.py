"""Пакетный перенос через публичный API с явным выбором обработки конфликтов."""

import json
import tempfile
import uuid
from itertools import islice
from pathlib import Path

from kuma._common.transfers import CHUNK_SIZE, validate_chunk_size
from kuma.errors import APIError
from kuma.rest._pagination import iter_pages


def toc_ids(toc):
    if not isinstance(toc, dict) or not isinstance(toc.get("folders"), list):
        raise APIError("Некорректное оглавление архива ресурсов")
    ids = []
    for folder in toc["folders"]:
        for resource in folder.get("resources") or []:
            if not isinstance(resource, dict) or not resource.get("id"):
                raise APIError("У записи архива ресурсов отсутствует ID")
            ids.append(resource["id"])
    if not ids:
        raise APIError("Архив ресурсов пуст")
    return list(dict.fromkeys(ids))


def conflicts_from(error, candidates):
    details = error.details
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except ValueError:
            return None
    conflicts = details.get("conflicts") if isinstance(details, dict) else None
    if not isinstance(conflicts, list) or not conflicts:
        return None
    if any(
        not isinstance(row, dict)
        or not row.get("storedResourceID")
        or row.get("candidateID") not in candidates
        for row in conflicts
    ):
        return None
    return conflicts


def export_file(resources, ids, tenant_id, password, path, chunk_size, timeout):
    _, result = resources.export(ids, tenant_id, password, timeout=timeout)
    resources.download(
        result["fileID"], filepath=path, chunk_size=chunk_size, timeout=timeout
    )


def upload_file(resources, path, password, chunk_size, timeout):
    _, uploaded = resources.upload(
        filepath=path, chunk_size=chunk_size, timeout=timeout
    )
    _, toc = resources.toc(uploaded["id"], password)
    return uploaded["id"], toc_ids(toc)


def conflict_tenants(target, conflicts):
    """Определить исходные тенанты конфликтов, включая Shared, для восстановления."""
    missing = [
        row["storedResourceID"]
        for row in conflicts
        if not row.get("storedResourceTenantID")
    ]
    owners = {}
    if missing:
        owners = {
            row["id"]: row.get("tenantID")
            for row in iter_pages(target.search, id=missing)
        }
    groups = {}
    for row in conflicts:
        tenant = row.get("storedResourceTenantID") or owners.get(
            row["storedResourceID"]
        )
        if not tenant:
            raise APIError(
                "Не удалось определить исходный тенант конфликтующего ресурса"
            )
        groups.setdefault(tenant, set()).add(row["storedResourceID"])
    return groups


def copy_batch(
    source,
    target,
    ids,
    source_tenant,
    target_tenant,
    password,
    policy,
    backup_directory,
    chunk_size,
    timeout,
):
    backups = []
    restored = False
    with tempfile.TemporaryDirectory(prefix="kapi-transfer-") as directory:
        archive = Path(directory) / "resources.bin"
        export_file(source, ids, source_tenant, password, archive, chunk_size, timeout)
        file_id, candidates = upload_file(
            target, archive, password, chunk_size, timeout
        )
        actions = dict.fromkeys(candidates, 1)
        try:
            status, result = target.import_data(
                file_id, target_tenant, password, actions
            )
        except APIError as error:
            conflicts = (
                conflicts_from(error, actions) if error.status_code == 409 else None
            )
            if policy == "error" or not conflicts:
                raise
            # Замена допустима только после сохранения всех резервных архивов.
            for tenant, stored_ids in conflict_tenants(target, conflicts).items():
                backup = Path(backup_directory) / (
                    "kapi-conflicts-" + uuid.uuid4().hex + ".bin"
                )
                export_file(
                    target,
                    sorted(stored_ids),
                    tenant,
                    password,
                    backup,
                    chunk_size,
                    timeout,
                )
                backups.append(
                    {
                        "tenantID": tenant,
                        "path": str(backup),
                        "resourceIDs": sorted(stored_ids),
                    }
                )
            for conflict in conflicts:
                actions[conflict["candidateID"]] = 2
            try:
                try:
                    status, result = target.import_data(
                        file_id, target_tenant, password, actions
                    )
                finally:
                    if policy == "preserve":
                        failures = []
                        for backup in backups:
                            try:
                                restore_id, restore_ids = upload_file(
                                    target,
                                    backup["path"],
                                    password,
                                    chunk_size,
                                    timeout,
                                )
                                if not set(backup["resourceIDs"]) <= set(restore_ids):
                                    raise APIError(
                                        "В резервном архиве отсутствует сохранённый ресурс"
                                    )
                                target.import_data(
                                    restore_id,
                                    backup["tenantID"],
                                    password,
                                    dict.fromkeys(backup["resourceIDs"], 2),
                                )
                            except Exception as failure:
                                failures.append(failure)
                        restored = not failures
                        if failures:
                            raise failures[0]
            except Exception as failure:
                wrapped = APIError(
                    "Перенос ресурсов завершился ошибкой; резервные архивы сохранены",
                    getattr(failure, "status_code", None),
                )
                wrapped.backup_path = backups[0]["path"]
                wrapped.backups = backups
                wrapped.conflicts_restored = restored
                raise wrapped from failure
    return {
        "status": status,
        "resourceIDs": ids,
        "result": result,
        "backup_path": backups[0]["path"] if backups else None,
        "backups": backups,
        "conflicts_restored": restored,
    }


def iter_copy_to(
    source,
    target_client,
    resource_ids,
    source_tenant_id,
    target_tenant_id,
    *,
    password,
    on_conflict="error",
    backup_directory=None,
    batch_size=100,
    chunk_size=CHUNK_SIZE,
    timeout=None,
):
    """Выдавать результат каждого пакета переноса, сохраняя резервные архивы.

    error: передать ошибку 409 без замен. replace: создать резервные копии
    конфликтующих ресурсов и заменить их. preserve: дополнительно восстановить
    сохранённые ресурсы после повторного импорта, в том числе при его ошибке.
    Последний режим сохраняет локальные зависимости при импорте новых ресурсов.
    Для replace и preserve нужны постоянный каталог копий и явный пароль архива.
    Архивы остаются зашифрованными этим паролем. Общей транзакции нет: предыдущие
    импорты могут сохраниться после последующей ошибки.
    """
    if not password:
        raise ValueError("Требуется явно указать пароль архива")
    if on_conflict not in ("error", "replace", "preserve"):
        raise ValueError("on_conflict должен быть error, replace или preserve")
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size < 1
    ):
        raise ValueError("batch_size должен быть положительным целым числом")
    validate_chunk_size(chunk_size)
    if on_conflict != "error" and (
        backup_directory is None or not Path(backup_directory).is_dir()
    ):
        raise ValueError("Для обработки конфликтов нужен существующий backup_directory")
    if isinstance(resource_ids, str):
        raise ValueError("resource_ids должен быть перебираемой коллекцией ID")
    if not source_tenant_id or not target_tenant_id:
        raise ValueError("Требуется явно указать ID исходного и целевого тенантов")
    iterator = iter(resource_ids)
    while True:
        ids = list(dict.fromkeys(islice(iterator, batch_size)))
        if not ids:
            return
        if any(not isinstance(id_, str) or not id_ for id_ in ids):
            raise ValueError("ID ресурсов должны быть непустыми строками")
        yield copy_batch(
            source,
            target_client.resources,
            ids,
            source_tenant_id,
            target_tenant_id,
            password,
            on_conflict,
            backup_directory,
            chunk_size,
            timeout,
        )
