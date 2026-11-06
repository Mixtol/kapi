import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder

from kuma._common.transfers import (
    CHUNK_SIZE,
    DownloadStream,
    upload_source,
    validate_chunk_size,
)
from kuma._common.transport import Timeout, Verify, validate_timeout, validate_verify
from kuma._common.versions import (
    LATEST_VERSION,
    SUPPORTED_VERSIONS,
    normalize_version,
    resolve_contract_version,
    resolve_default_version,
)
from kuma.errors import APIError

APIResult = Tuple[int, Any]


class KumaRestAPIBase:
    """Public KUMA API v3 transport. Sessions are reusable, but not thread-safe."""

    DEFAULT_PORT = 7223
    DEFAULT_TIMEOUT = 30
    DEFAULT_SCHEME = "https"

    def __init__(
        self,
        url: str,
        token: str,
        verify: Verify = True,
        timeout: Timeout = DEFAULT_TIMEOUT,
        logger: Optional[logging.Logger] = None,
        version: str = LATEST_VERSION,
    ):
        self._version = normalize_version(resolve_default_version(version))
        if self._version not in SUPPORTED_VERSIONS:
            raise ValueError(
                f"Unsupported KUMA version {self._version}; supported: "
                + ", ".join(SUPPORTED_VERSIONS)
            )
        self._contract_version = resolve_contract_version(self._version)
        if not isinstance(token, str) or not token.strip():
            raise ValueError("KUMA token cannot be empty")
        self._validate_timeout(timeout)
        self.timeout = timeout
        self.logger = logger if logger is not None else logging.getLogger("kuma.rest")
        self._configure_url(url)
        self._configure_ssl(verify)
        self.session = requests.Session()
        self.session.verify = self.verify
        self.session.headers.update(
            {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        )

    @property
    def version(self) -> str:
        """Configured KUMA major.minor release; this does not query the server."""
        return self._version

    @property
    def contract_version(self) -> str:
        """KUMA release whose request contract is used (4.0 for KUMA 4.1)."""
        return self._contract_version

    def _configure_url(self, url: str) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("KUMA URL cannot be empty")
        url = url.strip()
        if "://" not in url:
            url = f"{self.DEFAULT_SCHEME}://{url}"
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("KUMA URL must be an HTTP(S) URL with a hostname")
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "KUMA URL must not contain credentials, a query, or a fragment"
            )
        hostname = parsed.hostname
        if any(char.isspace() for char in hostname):
            raise ValueError("Invalid KUMA hostname")
        host = f"[{hostname}]" if ":" in hostname else hostname
        port = parsed.port if parsed.port is not None else self.DEFAULT_PORT
        if port == 0:
            raise ValueError("KUMA port must be between 1 and 65535")
        path = parsed.path.rstrip("/")
        if path.endswith("/api/v3"):
            path = path[:-7]
        self.url = urlunsplit((parsed.scheme, f"{host}:{port}", path, "", ""))

    def _configure_ssl(self, verify: Verify) -> None:
        self.verify = validate_verify(verify)

    @staticmethod
    def _validate_timeout(timeout):
        validate_timeout(timeout)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def _query_value(value):
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (list, tuple)):
            return [KumaRestAPIBase._query_value(item) for item in value]
        return value

    def _request(self, method, endpoint, headers=None, timeout=None, **kwargs):
        timeout = self.timeout if timeout is None else timeout
        self._validate_timeout(timeout)
        params = kwargs.get("params")
        if params is not None:
            params = dict(params)
            presence_flags = {
                "activeLists/import": ("clear",),
                "contextTables/import": ("clear",),
                "alerts": ("withEvents", "withAffected"),
                "services": ("paired",),
                "tenants": ("main",),
            }
            for key in presence_flags.get(endpoint.strip("/"), ()):
                if key not in params:
                    continue
                value = params.pop(key)
                if isinstance(value, str):
                    value = value.lower()
                if value in (False, None, "false", "0"):
                    continue
                if value not in (True, "true", "1", ""):
                    raise ValueError(f"{key} must be a boolean flag")
                params[key] = ""
            for key in ("needReload", "overwriteExist"):
                if isinstance(params.get(key), bool):
                    params[key] = int(params[key])
            kwargs["params"] = {
                key: self._query_value(value) for key, value in params.items()
            }
        url = f"{self.url}/api/v3/{endpoint.lstrip('/')}"
        self.logger.debug("Request: %s %s", method, url)
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                verify=self.verify,
                timeout=timeout,
                stream=True,
                allow_redirects=False,
                **kwargs,
            )
        except requests.exceptions.SSLError as exc:
            raise APIError(
                f"TLS verification failed: {exc}. Check the CA chain and certificate hostname."
            ) from exc
        except requests.RequestException as exc:
            raise APIError(f"Request failed: {exc}") from exc
        if response.status_code >= 300:
            try:
                error = APIError.from_response(response)
                self.logger.error(str(error))
                raise error
            except requests.RequestException as exc:
                raise APIError(
                    f"Error response read failed: {exc}", response.status_code
                ) from exc
            finally:
                response.close()
        return response

    def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict] = None,
        timeout: Optional[Timeout] = None,
        **kwargs,
    ) -> APIResult:
        response = self._request(
            method, endpoint, headers=headers, timeout=timeout, **kwargs
        )
        try:
            if response.status_code in (204, 205):
                return response.status_code, b""
            content_type = (
                response.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .lower()
                .strip()
            )
            if content_type == "application/json" or content_type.endswith("+json"):
                return response.status_code, (
                    response.json() if response.content else b""
                )
            if content_type.startswith("text/") or content_type == "text":
                return response.status_code, response.text
            return response.status_code, response.content
        except (ValueError, requests.RequestException) as exc:
            raise APIError(
                f"Response parsing failed: {exc}", response.status_code
            ) from exc
        finally:
            response.close()

    def _download(
        self,
        endpoint,
        filepath=None,
        *,
        stream=True,
        chunk_size=CHUNK_SIZE,
        timeout=None,
        headers=None,
        **kwargs,
    ):
        validate_chunk_size(chunk_size)
        if filepath is not None:
            destination = Path(filepath)
            if not destination.parent.is_dir() or destination.is_dir():
                raise ValueError(
                    "Download destination must be a file in an existing directory"
                )
        headers = {"Accept": "application/octet-stream", **(headers or {})}
        if filepath is None and not stream:
            return self._make_request(
                "GET", endpoint, headers=headers, timeout=timeout, **kwargs
            )
        response = self._request(
            "GET", endpoint, headers=headers, timeout=timeout, **kwargs
        )
        download = DownloadStream(response, chunk_size)
        return response.status_code, (
            download.save(filepath) if filepath is not None else download
        )

    def _upload(
        self,
        endpoint,
        data=None,
        *,
        filepath=None,
        multipart=False,
        filename="data.csv",
        content_type="application/octet-stream",
        chunk_size=CHUNK_SIZE,
        timeout=None,
        **kwargs,
    ):
        with upload_source(data, filepath, chunk_size) as source:
            if multipart:
                body = MultipartEncoder({"file": (filename, source, content_type)})
                headers = {"Content-Type": body.content_type}
            else:
                body = source
                headers = {
                    "Content-Type": content_type,
                    "Content-Length": str(source.len),
                }
            return self._make_request(
                "POST", endpoint, data=body, headers=headers, timeout=timeout, **kwargs
            )

    @staticmethod
    def format_time(time_value):
        """Format Unix seconds or aware datetimes as RFC3339 in UTC."""
        if isinstance(time_value, bool):
            raise ValueError("A boolean is not a timestamp")
        if isinstance(time_value, (int, float)):
            time_value = datetime.fromtimestamp(time_value, tz=timezone.utc)
        if isinstance(time_value, datetime):
            if time_value.tzinfo is None or time_value.utcoffset() is None:
                raise ValueError("Datetime must include a timezone")
            return (
                time_value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        if isinstance(time_value, str):
            parsed = datetime.fromisoformat(time_value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Timestamp must include a timezone")
            return time_value
        raise TypeError(
            "Timestamp must be Unix seconds, an aware datetime, or an RFC3339 string"
        )


class KumaRestAPIModule:
    """Base class for public REST API modules."""

    def __init__(self, base: KumaRestAPIBase):
        self._base = base

    def __getattr__(self, name):
        return getattr(self._base, name)

    def _make_request(self, *args, **kwargs):
        return self._base._make_request(*args, **kwargs)

    def format_time(self, value):
        return self._base.format_time(value)

    @staticmethod
    def _path(value):
        if value is None or str(value) in ("", ".", ".."):
            raise ValueError("Path parameters cannot be empty or dot segments")
        return quote(str(value), safe="")
