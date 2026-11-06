"""Opt-in live checks. Reports contain no URLs, credentials or response bodies."""

import argparse
import json
import logging
import os
import secrets
import string
import sys
import tempfile
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kuma import PrivateClient, RestClient
from kuma._common.versions import LATEST_VERSION, normalize_version

PROFILES = {
    "3.4": "TEST_KUMA",
    "4.0": "TEST_KUMA40",
    "4.1": "TEST_KUMA41",
    "4.2": "TEST_KUMA42",
}


@dataclass(repr=False)
class StandConfig:
    version: str
    url: str
    private_url: str
    token: str
    username: str
    password: str
    verify: object

    @classmethod
    def from_mapping(cls, values, version, *, base_dir=ROOT, public_only=False):
        version = normalize_version(version)
        if version not in PROFILES:
            raise ValueError("Unsupported stand version")
        prefix = PROFILES[version]

        def required(suffix):
            name = prefix + suffix
            value = values.get(name)
            if not value:
                raise ValueError("Missing " + name)
            return value

        url = required("_URL")
        token = required("_TOKEN")
        username = values.get(prefix + "_USER") or values.get(prefix + "_LOGIN")
        password = values.get(prefix + "_PASS")
        if not public_only and (not username or not password):
            raise ValueError("Missing " + prefix + "_USER/_LOGIN or _PASS")
        ca = values.get(prefix + "_CA")
        verify = True
        if ca:
            path = Path(ca).expanduser()
            if not path.is_absolute():
                path = Path(base_dir) / path
            if not path.exists():
                raise ValueError("CA path in " + prefix + "_CA does not exist")
            verify = str(path.resolve())
        parsed = urlsplit(url if "://" in url else "https://" + url)
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Invalid stand URL")
        host = parsed.hostname
        host = f"[{host}]" if ":" in host else host
        private_url = values.get(prefix + "_PRIVATE_URL") or urlunsplit(
            (parsed.scheme, host + ":7220", "", "", "")
        )
        return cls(version, url, private_url, token, username, password, verify)


class Checks:
    def __init__(self):
        self.rows = []

    def run(self, name, operation):
        row = {"check": name, "passed": False}
        try:
            result = operation()
            row["passed"] = True
            return result
        except Exception as exc:
            row["error"] = type(exc).__name__
            row["status"] = getattr(exc, "status_code", None)
            row["causes"] = []
            seen = set()
            while exc and id(exc) not in seen:
                seen.add(id(exc))
                row["causes"].append(type(exc).__name__)
                exc = exc.__cause__ or exc.__context__
        finally:
            self.rows.append(row)
            print(json.dumps(row), flush=True)

    def skip(self, name):
        self.rows.append({"check": name, "skipped": True})


def successful(result):
    status, body = result
    if not 200 <= status < 300:
        from kuma import APIError

        raise APIError("Unexpected response status", status)
    return body


def matching_version(client, expected):
    actual = client.get_version()
    if actual != expected:
        raise ValueError("Core version does not match the selected stand profile")
    return actual


def check_public(config, checks, logger, transfers):
    with RestClient(
        config.url, config.token, config.verify, (5, 60), logger, config.version
    ) as client:
        # A mismatched or unreachable stand must not be reported as compatible.
        matching_version(client, config.version)
        for name, call in [
            ("users.whoami", client.users.whoami),
            ("users.search", lambda: client.users.search(size=2)),
            ("tenants.search", client.tenants.search),
            ("services.search", client.services.search),
            ("events.clusters", client.events.get_clusters),
            ("alerts.search", lambda: client.alerts.search(page=1)),
            ("incidents.search", client.incidents.search),
        ]:
            checks.run("public." + name, lambda call=call: successful(call()))
        resources = checks.run(
            "public.resources.search",
            lambda: successful(client.resources.search(kind=["filter"], size=2)),
        )
        if resources:
            resource = resources[0]
            for name, call in [
                (
                    "resources.get",
                    lambda: client.resources.get("filter", resource["id"]),
                ),
                (
                    "resources.history",
                    lambda: client.resources.list_history(
                        "filter", resource["id"], size=1
                    ),
                ),
                (
                    "folders.search",
                    lambda: client.folders.search([resource["tenantID"]], limit=2),
                ),
                (
                    "reports.search",
                    lambda: client.reports.search([resource["tenantID"]], limit=2),
                ),
            ]:
                checks.run("public." + name, lambda call=call: successful(call()))
            if transfers:
                checks.run(
                    "public.export_download_upload_toc",
                    lambda: check_public_transfer(client, resource),
                )
        else:
            checks.skip("public.resource_details_and_transfers: no filters")


def check_public_transfer(client, resource):
    password = archive_password()
    exported = successful(
        client.resources.export(
            [resource["id"]], resource["tenantID"], password, timeout=(5, 120)
        )
    )
    with tempfile.TemporaryDirectory(prefix="kapi-check-") as directory:
        path = Path(directory) / "resources.bin"
        successful(
            client.resources.download(
                exported["fileID"], filepath=path, chunk_size=1024 * 1024
            )
        )
        if not path.stat().st_size:
            raise ValueError("Empty resource export")
        uploaded = successful(client.resources.upload(filepath=path, chunk_size=65536))
        toc = successful(client.resources.toc(uploaded["id"], password=password))
        ids = {
            row["id"]
            for folder in toc.get("folders") or []
            for row in folder.get("resources") or []
        }
        if resource["id"] not in ids:
            raise ValueError("Exported resource missing from TOC")


def archive_password():
    # KUMA 4.2 limits repeated characters, including nonadjacent repetitions.
    alphabet = "".join(
        c for c in string.ascii_letters + string.digits if c not in "Aa1"
    )
    return "Aa1!" + "".join(secrets.SystemRandom().sample(alphabet, 24))


def check_private(config, checks, logger, transfers):
    with PrivateClient(
        config.private_url,
        config.username,
        config.password,
        version=config.version,
        logger=logger,
        verify=config.verify,
        timeout=(5, 60),
    ) as client:
        try:
            matching_version(client, config.version)
            for name, call in [
                ("whoami", client.whoami),
                ("tenants", client.get_all_tenants),
                ("services", lambda: list(client.iter_services(page_size=5))),
                ("folders", lambda: list(client.iter_folders(page_size=50))),
                ("correlators", lambda: client._rows(client.get_all_correlator())),
                ("settings", lambda: successful(client.get_settings())),
            ]:
                checks.run("private." + name, call)
            resources = checks.run(
                "private.resources.pagination",
                lambda: list(islice(client.iter_resources("filter", page_size=2), 6)),
            )

            def restored_session():
                with PrivateClient(
                    config.private_url,
                    config.username,
                    config.password,
                    client.get_session_data(),
                    config.version,
                    logger,
                    verify=config.verify,
                    timeout=(5, 60),
                    validate_session=True,
                ) as restored:
                    if restored.whoami()["id"] != client.whoami()["id"]:
                        raise ValueError("Restored session has a different identity")

            checks.run("private.saved_session", restored_session)
            if resources and transfers:

                def export():
                    with tempfile.TemporaryDirectory(prefix="kapi-check-") as folder:
                        path = Path(folder) / "resources.bin"
                        status = client.export_content(
                            [resources[0]["id"]],
                            resources[0]["tenantID"],
                            password=archive_password(),
                            file_path=path,
                            timeout=(5, 120),
                            chunk_size=1024 * 1024,
                        )
                        successful((status, None))
                        if not path.stat().st_size:
                            raise ValueError("Empty resource export")

                checks.run("private.export_download", export)
        finally:
            checks.run("private.logout", client.logout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=LATEST_VERSION)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--public-only", action="store_true")
    parser.add_argument(
        "--transfers",
        action="store_true",
        help="Export/upload temporary files; never import resources",
    )
    args = parser.parse_args(argv)
    from dotenv import dotenv_values

    config = StandConfig.from_mapping(
        {**dotenv_values(args.env_file), **os.environ},
        args.version,
        base_dir=args.env_file.resolve().parent,
        public_only=args.public_only,
    )
    logger = logging.Logger("kapi.stand-check")
    logger.addHandler(logging.NullHandler())
    checks = Checks()
    checks.run(
        "public.core_version_and_checks",
        lambda: check_public(config, checks, logger, args.transfers),
    )
    if not args.public_only:
        checks.run(
            "private.core_version_and_checks",
            lambda: check_private(config, checks, logger, args.transfers),
        )
    report = {
        "configured_version": config.version,
        "profile": PROFILES[config.version],
        "tls_verified": config.verify is not False,
        "resource_mutations": 0,
        "checks": checks.rows,
        "passed": sum(row.get("passed") is True for row in checks.rows),
        "failed": sum(row.get("passed") is False for row in checks.rows),
        "skipped": sum(row.get("skipped", False) for row in checks.rows),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "checks"}))
    return int(bool(report["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
