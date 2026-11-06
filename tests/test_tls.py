"""TLS over loopback; the committed key belongs only to this test fixture."""

import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests
from urllib3.exceptions import InsecureRequestWarning

from kuma import APIError, RestClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def tls_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(
        FIXTURES / "localhost-cert.pem", FIXTURES / "localhost-key.pem"
    )
    server.socket = context.wrap_socket(server.socket, server_side=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield server.server_port
    server.shutdown()
    server.server_close()
    worker.join(timeout=5)


def test_ca_file_allows_trusted_hostname(tls_server):
    with RestClient(
        f"https://localhost:{tls_server}",
        "test-token",
        verify=FIXTURES / "localhost-cert.pem",
        timeout=(2, 5),
    ) as client:
        client.session.trust_env = False
        assert client.users.whoami() == (200, {})


@pytest.mark.parametrize(
    "host,verify", [("localhost", True), ("127.0.0.1", FIXTURES / "localhost-cert.pem")]
)
def test_untrusted_ca_or_wrong_hostname_is_rejected(tls_server, host, verify):
    with RestClient(
        f"https://{host}:{tls_server}", "test-token", verify=verify, timeout=(2, 5)
    ) as client:
        client.session.trust_env = False
        with pytest.raises(APIError) as caught:
            client.users.whoami()
    assert isinstance(caught.value.__cause__, requests.exceptions.SSLError)


def test_explicit_insecure_mode_keeps_warning(tls_server):
    with RestClient(
        f"https://localhost:{tls_server}", "test-token", verify=False, timeout=(2, 5)
    ) as client:
        client.session.trust_env = False
        with pytest.warns(InsecureRequestWarning):
            assert client.users.whoami() == (200, {})
