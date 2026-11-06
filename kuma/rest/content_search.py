"""Ограниченный поиск JSON ресурсов: общий план для sync SDK и async MCP.

План выдаёт только вызовы публичного SDK. Исполнитель обязан вернуть JSON через
send() или безопасный SearchError через throw(); HTTP принадлежит RestClient.
"""

import hashlib
import json
import re
import time
from copy import deepcopy
from uuid import UUID

KINDS = frozenset(
    (
        "correlationRule",
        "enrichmentRule",
        "aggregationRule",
        "segmentationRule",
        "dataMiningRule",
        "dictionary",
        "normalizer",
        "filter",
        "correlator",
        "collector",
    )
)
LINKS = {
    "rules": "correlationRule",
    "correlationRules": "correlationRule",
    "enrichment": "enrichmentRule",
    "enrichmentRules": "enrichmentRule",
    "filter": "filter",
    "filters": "filter",
    "normalizer": "normalizer",
    "linkedNormalizer": "normalizer",
    "dictionary": "dictionary",
}
SECRET = re.compile(
    r"password|credential|authorization|(?:api|access|private)[_-]?key|token|secret",
    re.IGNORECASE,
)
REF = re.compile(
    r"(?<![\w])(?:(?P<filter>filter)\s*=\s*'(?P<fid>[0-9a-fA-F-]{36})'"
    r"|(?P<dictionary>indictionary)\s*\(\s*'(?P<did>[0-9a-fA-F-]{36})')"
)


class SearchError(Exception):
    """Код остановки без ответа сервера и credentials."""


def uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def references_in_code(code):
    """Читать ссылки вне строковых литералов, не исполняя язык фильтра."""
    pos = 0
    while pos < len(code):
        match = REF.match(code, pos)
        if match:
            kind = "filter" if match.group("filter") else "dictionary"
            ident = uuid(match.group("fid") or match.group("did"))
            if ident:
                yield kind, ident, pos, match.end()
            pos = match.end()
        elif code[pos] in "'\"`":
            quote = code[pos]
            pos += 1
            while pos < len(code):
                if code[pos] == "\\":
                    pos += 2
                elif code[pos] == quote:
                    if pos + 1 < len(code) and code[pos + 1] == quote:
                        pos += 2
                    else:
                        pos += 1
                        break
                else:
                    pos += 1
        else:
            pos += 1


def _walk(value):
    # Итераторы держат в памяти глубину дерева, а не все строки словаря.
    stack = [iter([((), value, None)])]
    count = 0
    while stack:
        item = next(stack[-1], None)
        if item is None:
            stack.pop()
            continue
        path, node, context = item
        count += 1
        if count > 100000 or len(path) > 64:
            raise SearchError("content_complexity_limit")
        yield path, node, context
        if isinstance(node, (dict, list)):
            stack.append(_children(path, node, context))


def _children(path, node, context):
    if isinstance(node, dict):
        for key, value in node.items():
            if not SECRET.search(str(key)):
                yield path + (str(key),), value, LINKS.get(key)
    else:
        for index, value in enumerate(node):
            yield path + (str(index),), value, context


def _parts(pattern):
    if (
        not isinstance(pattern, str)
        or not pattern.startswith("/")
        or len(pattern) > 256
    ):
        raise ValueError("Путь должен быть JSON Pointer длиной до 256 символов")
    if re.search(r"~(?![01])", pattern):
        raise ValueError("Некорректное экранирование JSON Pointer")
    return tuple(
        p.replace("~1", "/").replace("~0", "~") for p in pattern[1:].split("/")
    )


def _path_matches(path, pattern, subtree=False):
    return (
        len(path) >= len(pattern) if subtree else len(path) == len(pattern)
    ) and all(
        expected == "*" or actual == expected for actual, expected in zip(path, pattern)
    )


def inspect_content(resource, query, *, paths=(), conditions=(), condition_mode="all"):
    """Литеральный поиск в ключах и значениях; conditions применяются к одному JSON.

    Возвращаются максимум три примера. Секретные поля не ищутся. paths выбирает
    поддеревья, '*' — один сегмент; условия используют точный путь с wildcard.
    """
    scopes = [_parts(p) for p in paths]
    checks = [(_parts(c["path"]), c) for c in conditions]
    hits = [False] * len(checks)
    evidence, references = [], []
    term = query.casefold() if query else None
    text_hit = term is None
    complete = True
    try:
        for path, value, context in _walk(resource):
            pointer = "/" + "/".join(
                p.replace("~", "~0").replace("/", "~1") for p in path
            )
            scalar = not isinstance(value, (dict, list))
            text = str(value) if scalar else ""
            key = path[-1] if path else ""
            selected = not scopes or any(_path_matches(path, p, True) for p in scopes)
            hit_kind = None
            if (
                term is not None
                and selected
                and (term in text.casefold() or term in key.casefold())
            ):
                text_hit = True
                hit_kind = "value" if term in text.casefold() else "key"
            for i, (pattern, check) in enumerate(checks):
                if not _path_matches(path, pattern):
                    continue
                expected = check.get("value")
                matched = (
                    check["op"] == "exists"
                    or (
                        check["op"] == "equals"
                        and type(value) is type(expected)
                        and value == expected
                    )
                    or (
                        check["op"] == "contains"
                        and isinstance(value, str)
                        and str(expected).casefold() in value.casefold()
                    )
                )
                if matched:
                    hits[i] = True
                    hit_kind = hit_kind or "condition"
            if hit_kind and len(evidence) < 3:
                source = key if hit_kind == "key" else text
                offset = max(0, source.casefold().find(term) - 50) if term else 0
                evidence.append(
                    {
                        "path": pointer[:256],
                        "path_truncated": len(pointer) > 256,
                        "match_type": hit_kind,
                        "snippet": source[offset : offset + 180],
                    }
                )
            if any(p in {"data", "tableDict", "samples"} for p in path):
                continue
            if context:
                ident = (
                    uuid(value.get("id")) if isinstance(value, dict) else uuid(value)
                )
                # Конфигурация уже вложена в JSON; отдельно читать её не требуется.
                embedded = isinstance(value, dict) and bool(
                    set(value)
                    - {
                        "id",
                        "name",
                        "kind",
                        "tenantID",
                        "tenantName",
                        "tags",
                        "description",
                    }
                )
                if ident and not embedded:
                    references.append((context, ident))
            if key == "code" and isinstance(value, str):
                references.extend(
                    (kind, ident) for kind, ident, _, _ in references_in_code(value)
                )
    except SearchError:
        complete = False
    predicate = not checks or (all(hits) if condition_mode == "all" else any(hits))
    return {
        "matched": text_hit and predicate,
        "matches": evidence,
        "complete": complete,
        "references": list(dict.fromkeys(references)),
    }


def content_search_plan(
    *,
    kind,
    tenant_ids,
    query=None,
    paths=(),
    conditions=(),
    condition_mode="all",
    ids=(),
    include_references=False,
    reference_depth=1,
    limit=10,
    max_queries=12,
    deadline=15,
    state=None,
):
    """Порция поиска с возобновляемым состоянием без содержимого ресурсов.

    Root tenant обязателен. Ссылки могут вести в другой доступный токену tenant.
    filterCodeOnly=True: поиск охватывает код фильтров вместо их AST.
    Состояние нужно защищать от подмены и привязывать к запросу/токену в адаптере.
    """
    if kind not in KINDS or not tenant_ids or any(not uuid(t) for t in tenant_ids):
        raise ValueError("Нужны поддерживаемый kind и tenant_ids с UUID")
    if (query is None and not conditions) or (
        query is not None
        and (not isinstance(query, str) or not query.strip() or len(query) > 256)
    ):
        raise ValueError("Нужен query до 256 символов либо conditions")
    if not 1 <= limit <= 10 or not 1 <= max_queries <= 20 or not 0 < deadline <= 15:
        raise ValueError("Превышены пределы порции поиска")
    if not 1 <= reference_depth <= 2 or condition_mode not in {"all", "any"}:
        raise ValueError("Некорректная глубина или режим условий")
    if (
        len(paths) > 20
        or len(conditions) > 10
        or len(ids) > 100
        or any(not uuid(i) for i in ids)
    ):
        raise ValueError("Некорректные ограничения поиска")
    for path in paths:
        _parts(path)
    for check in conditions:
        _parts(check["path"])
        if check["op"] not in {"contains", "equals", "exists"}:
            raise ValueError("Неизвестный оператор")
        value = check.get("value")
        if isinstance(value, (dict, list)) or len(str(value)) > 256:
            raise ValueError("Условие принимает скаляр до 256 символов")
        if check["op"] == "contains" and (not isinstance(value, str) or not value):
            raise ValueError("contains требует непустую строку")
    state = (
        deepcopy(state)
        if state
        else {"page": 1, "offset": 0, "checked": 0, "unreadable": 0}
    )
    start = time.monotonic()
    requests = 0
    output, failures = [], []
    cache = {}  # Только результаты проверки; полные конфигурации не сохраняются.
    stopped, exhausted = "complete", False
    allowed = {uuid(t) for t in tenant_ids}
    requested = {uuid(i) for i in ids}

    def fetch(method, **kwargs):
        nonlocal requests
        if requests >= max_queries:
            raise SearchError("query_budget")
        if time.monotonic() - start >= deadline:
            raise SearchError("time_budget")
        requests += 1
        return (yield method, kwargs)

    try:
        while len(output) < limit:
            if "root" in state:
                # Продолжение детали не перечитывает каталог: max_queries=1 тоже
                # продвигается вперёд. В state нет кода, значений и фрагментов.
                batch = [{}] * state["offset"] + [state["root"]["row"]]
                signature = state["page_signature"]
                page_end = state["root"]["page_end"]
            else:
                batch = yield from fetch(
                    "resources.search",
                    kind=kind,
                    tenantID=sorted(allowed),
                    **({"id": sorted(requested)} if requested else {}),
                    page=state["page"],
                )
                if (
                    not isinstance(batch, list)
                    or len(batch) > 250
                    or any(not isinstance(r, dict) for r in batch)
                ):
                    raise SearchError("unexpected_upstream_shape")
                identities = [r.get("id") for r in batch]
                if any(not uuid(i) for i in identities) or len(set(identities)) != len(
                    identities
                ):
                    raise SearchError("invalid_catalog_identities")
                signature = hashlib.sha256(json.dumps(identities).encode()).hexdigest()
                if state.get("page_signature") and state["page_signature"] != signature:
                    raise SearchError("catalog_changed_restart_search")
                membership = hashlib.sha256(
                    json.dumps(sorted(identities)).encode()
                ).hexdigest()
                if batch and membership == state.get("previous_page"):
                    raise SearchError("repeated_upstream_page")
                if state["offset"] > len(batch):
                    raise SearchError("catalog_changed_restart_search")
                if not batch:
                    exhausted = True
                    break
                state["page_signature"] = signature
                state["page_membership"] = membership
                page_end = True
            while state["offset"] < len(batch) and len(output) < limit:
                row = batch[state["offset"]]
                ident = uuid(row.get("id"))
                if (
                    not ident
                    or row.get("kind") != kind
                    or row.get("tenantID") not in allowed
                    or (requested and ident not in requested)
                ):
                    raise SearchError("upstream_scope_mismatch")
                root = state.setdefault(
                    "root",
                    {
                        "pending": [[kind, ident, 0, []]],
                        "seen": [],
                        "row": {k: row[k] for k in ("id", "kind", "tenantID")},
                        "page_end": state["offset"] + 1 == len(batch),
                    },
                )
                while root["pending"]:
                    target_kind, target_id, depth, via = root["pending"][0]
                    cache_key = (target_kind, target_id)
                    try:
                        if cache_key in cache and "error" in cache[cache_key]:
                            raise SearchError(cache[cache_key]["error"])
                        if cache_key not in cache:
                            value = yield from fetch(
                                "resources.get",
                                kind=target_kind,
                                id=target_id,
                                filter_code_only=True,
                            )
                            if (
                                not isinstance(value, dict)
                                or value.get("id") != target_id
                                or value.get("kind") != target_kind
                            ):
                                raise SearchError("upstream_resource_identity_mismatch")
                            if depth == 0 and value.get("tenantID") not in allowed:
                                raise SearchError("upstream_scope_mismatch")
                            cache[cache_key] = inspect_content(
                                value,
                                query,
                                paths=paths,
                                conditions=conditions,
                                condition_mode=condition_mode,
                            )
                            cache[cache_key]["tenant_id"] = value.get("tenantID")
                        found = cache[cache_key]
                        if depth == 0 and found["tenant_id"] not in allowed:
                            raise SearchError("upstream_scope_mismatch")
                    except SearchError as error:
                        if str(error) not in {
                            "upstream_http_403",
                            "upstream_http_404",
                            "upstream_response_too_large",
                        }:
                            raise
                        cache[cache_key] = {"error": str(error)}
                        state["unreadable"] += 1
                        failures.append(
                            {"id": target_id, "kind": target_kind, "error": str(error)}
                        )
                        root["pending"].pop(0)
                        root["seen"].append([target_kind, target_id])
                        continue
                    root["pending"].pop(0)
                    root["seen"].append([target_kind, target_id])
                    if not found["complete"]:
                        state["unreadable"] += 1
                        failures.append(
                            {"id": target_id, "error": "content_complexity_limit"}
                        )
                    if found["matched"]:
                        output.append(
                            {
                                "id": ident,
                                "kind": kind,
                                "tenantID": row["tenantID"],
                                "name": str(row.get("name", ""))[:128],
                                "matched_resource": {
                                    "id": target_id,
                                    "kind": target_kind,
                                },
                                "via": via,
                                "matches": found["matches"],
                            }
                        )
                        root[
                            "pending"
                        ].clear()  # Достаточно одного доказательства совпадения root.
                        break
                    if include_references and depth < reference_depth:
                        known = {tuple(p[:2]) for p in root["pending"]} | {
                            tuple(p) for p in root["seen"]
                        }
                        for ref_kind, ref_id in found["references"]:
                            if (ref_kind, ref_id) in known:
                                continue
                            if len(known) >= 8:
                                state["unreadable"] += 1
                                failures.append(
                                    {"id": ident, "error": "reference_limit"}
                                )
                                break
                            known.add((ref_kind, ref_id))
                            root["pending"].append(
                                [ref_kind, ref_id, depth + 1, via + [target_id]]
                            )
                state["offset"] += 1
                state["checked"] += 1
                state.pop("root", None)
            if state["offset"] == len(batch) and page_end:
                state.update(
                    page=state["page"] + 1,
                    offset=0,
                    previous_page=state["page_membership"],
                )
                state.pop("page_signature", None)
            if len(output) >= limit:
                stopped = "result_limit"
                break
    except SearchError as error:
        stopped = str(error)
    complete = exhausted and state["unreadable"] == 0
    return {
        "rows": output,
        "returned": len(output),
        "complete": complete,
        "scan_exhausted": exhausted,
        "stop_reason": (
            "unreadable_resources" if exhausted and not complete else stopped
        ),
        "checked": state["checked"],
        "unreadable": state["unreadable"],
        "failures": failures[:10],
        "requests": requests,
        "state": None if exhausted else state,
        "scope": {
            "filter_code_only": True,
            "secret_fields_excluded": True,
            "include_references": include_references,
            "reference_depth": reference_depth if include_references else 0,
        },
    }


class ResourceContentSearch:
    def find_content(self, *, min_interval=1.0, **kwargs):
        """Выполнить одну порцию через SDK: <=20 запросов, без retry и параллелизма.

        state из результата передаётся следующему вызову с теми же фильтрами.
        Лимиты байтов, общий rate limit нескольких клиентов и подпись state —
        ответственность вызывающего приложения. min_interval не менее секунды.
        """
        if not isinstance(min_interval, (int, float)) or not 1 <= min_interval <= 60:
            raise ValueError("min_interval должен быть от 1 до 60 секунд")
        from kuma.errors import APIError

        plan = content_search_plan(**kwargs)
        last = 0.0
        started = time.monotonic()
        deadline = kwargs.get("deadline", 15)
        try:
            request = next(plan)
            while True:
                wait = max(0, last + min_interval - time.monotonic())
                if time.monotonic() + wait - started >= deadline:
                    request = plan.throw(SearchError("time_budget"))
                    continue
                time.sleep(wait)
                last = time.monotonic()
                method, arguments = request
                try:
                    status, value = getattr(self, method.split(".")[1])(**arguments)
                    if status != 200:
                        raise SearchError("upstream_http_" + str(status))
                except APIError as error:
                    request = plan.throw(
                        SearchError(
                            "upstream_http_" + str(error.status_code)
                            if error.status_code
                            else "upstream_transport_error"
                        )
                    )
                except SearchError as error:
                    request = plan.throw(error)
                else:
                    request = plan.send(value)
        except StopIteration as result:
            return 200, result.value
