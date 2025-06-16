import logging
from datetime import datetime
from typing import Dict, Optional, Tuple, Union, Any

import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from kuma._logging import configure_logging
from kuma.rest.errors import APIError

_logger = configure_logging()
_api_version = "v2.1"


class KumaRestAPIBase:
    """Base client for Kaspersky Unified Monitoring and Analytics (KUMA) REST API.

    Handles core functionality including:
    - Session management
    - Authentication
    - Request/response processing
    - Error handling
    """

    DEFAULT_PORT = 7223
    DEFAULT_TIMEOUT = 30
    DEFAULT_SCHEME = "https"

    def __init__(
        self,
        url: str,
        token: str,
        verify: bool | str = False,
        timeout: int = DEFAULT_TIMEOUT,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize the API client.

        Args:
            url: Base server URL (e.g., "kumacore.local" or "https://kumacore.local:7223")
            token: Bearer token for authentication
            verify: SSL certificate verification. Set False to disable warnings.
            timeout: Request timeout in seconds (default: 30)
            logger: Custom logger instance (optional)

        Raises:
            ValueError: If URL is malformed
        """
        self.timeout = timeout
        self.logger = logger or self._create_default_logger()

        self._configure_url(url)
        self._configure_session(token)
        self._configure_ssl(verify)

        self.logger.debug(f"Initialized KUMA API client for {self.url}")

    def _configure_url(self, url: str) -> None:
        """Normalize and validate the base URL."""
        url = url.strip().rstrip("/")

        if not url:
            raise ValueError("URL cannot be empty")

        # Add scheme if missing
        if not url.startswith(("http://", "https://")):
            url = f"{self.DEFAULT_SCHEME}://{url}"

        # Add default port if not specified
        if ":" not in url.split("//")[-1]:
            url = f"{url}:{self.DEFAULT_PORT}"

        self.url = url

    def _configure_session(self, token: str) -> None:
        """Configure the requests session with default headers."""
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        )

    def _configure_ssl(self, verify: bool | str) -> None:
        """Configure SSL verification settings."""
        self.verify = verify
        if not self.verify:
            disable_warnings(InsecureRequestWarning)
            self.logger.warning(
                "SSL verification is disabled - security warnings suppressed"
            )

    def _create_default_logger(self) -> logging.Logger:
        """Create and configure a default logger instance."""
        logger = logging.getLogger("kapi")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s|%(name)s|%(levelname)s|%(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def __enter__(self):
        """Support context manager protocol."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context."""
        self.session.close()

    def _make_request(
        self, method: str, endpoint: str, headers: Optional[Dict] = None, **kwargs
    ) -> Tuple[int, Union[Dict, str, bytes]]:
        """
        Unified request method with error handling and logging.
        """
        url = f"{self.url}/api/{_api_version}/{endpoint.lstrip('/')}"
        headers = {**self.session.headers, **(headers or {})}

        self.logger.debug(f"Request: {method} {url}")
        self.logger.debug(f"Params: {kwargs.get('params')}")
        self.logger.debug(f"Headers: {headers.keys()}")

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                verify=self.verify,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exception:
            self.logger.error(f"Request failed: {exception}")
            raise APIError(f"Request failed: {exception}") from exception

        self.logger.debug(f"Response: {response.status_code}")
        self.logger.debug(f"Content-Type: {response.headers.get('Content-Type')}")

        if response.status_code >= 300:
            error_msg = f"Bad response {response.status_code}: {response.text}"
            self.logger.error(error_msg)
            raise APIError(error_msg, status_code=response.status_code)

        try:
            content_type = response.headers.get("Content-Type", "").lower()
            if "application/json" in content_type:
                return response.status_code, response.json()
            elif content_type.startswith("text/"):
                return response.status_code, response.text
            elif (
                "attachment" in response.headers.get("Content-Disposition", "").lower()
            ):
                self.logger.info(
                    f"Received binary data ({len(response.content)} bytes)"
                )
            return response.status_code, response.content
        except Exception as exception:
            self.logger.error(f"Response parsing failed: {exception}")
            raise APIError(f"Response parsing failed: {exception}")

    @staticmethod
    def format_time(time_value: int | Any) -> int | Any:
        if isinstance(time_value, int):
            return datetime.fromtimestamp(time_value).isoformat()
        return time_value


class KumaRestAPIModule:
    """Base class for REST API modules."""
    def __init__(self, base: KumaRestAPIBase) -> None:
        self._base = base

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the parent client."""
        return getattr(self._base, name)

    def _make_request(self, *args, **kwargs):
        """Proxy request call to the parent client."""
        return self._base._make_request(*args, **kwargs)

    def format_time(self, time_value: int | Any) -> int | Any:
        """Proxy ``format_time`` to the parent client."""
        return self._base.format_time(time_value)
