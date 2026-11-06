import io
import json
from unittest.mock import Mock

import pytest
import requests

from kuma import APIError, DownloadStream, PrivateClient
from kuma.private._session import PrivateSession
from tests.test_api_errors import make_response
from tests.test_tls import FIXTURES, tls_server
from tests.test_transfers import GuardedFile, StreamingResponse

SAVED = {"cookies": {}, "headers": {}, "xsrf_token": "test-xsrf"}


@pytest.fixture
def client():
    with PrivateClient(
        "example.invalid", "user", "password", SAVED, "3.4", Mock()
    ) as api:
        yield api


@pytest.mark.parametrize("status", [200, 204])
def test_factory_logs_in_once_and_cert_is_a_ca_bundle(monkeypatch, status):
    logins = []
    observed = []

    def send(session, request, **kwargs):
        observed.append(kwargs)
        if request.url.endswith("/api/login"):
            logins.append(request)
            session.cookies.set("XSRF-TOKEN", "test-xsrf")
            return make_response("", status)
        if request.url.endswith("/api/whoami"):
            return make_response('{"id":"user"}', 200)
        if request.url.endswith("/api/private/tenants/"):
            return make_response('[{"id":"tenant"}]', 200)
        return make_response("", 204)

    monkeypatch.setattr(requests.Session, "send", send)
    ca = FIXTURES / "localhost-cert.pem"
    with PrivateClient.create_session(
        "example.invalid",
        "user",
        "password",
        cert=ca,
        version="3.4",
        timeout=(2, 7),
    ) as api:
        assert len(logins) == 1
        assert api.version == "3.4"
        assert api.verify == str(ca.resolve())
        assert all(row["timeout"] == (2, 7) for row in observed)
        assert all(row["verify"] == str(ca.resolve()) for row in observed)
        saved = api.get_session_data()
        with PrivateClient.create_session(
            "example.invalid",
            "user",
            "password",
            saved,
            cert=ca,
            version="3.4",
            timeout=(2, 7),
        ) as restored:
            assert len(logins) == 1
            assert restored.session.headers["X-XSRF-TOKEN"] == "test-xsrf"


@pytest.mark.parametrize(
    "method", ["get", "post", "put", "patch", "delete", "head", "options"]
)
def test_every_private_http_verb_inherits_timeout_and_tls(monkeypatch, method):
    send = Mock(return_value=make_response("{}", 200))
    monkeypatch.setattr(requests.Session, "send", send)
    with PrivateSession(timeout=(3, 19)) as session:
        session.trust_env = False
        getattr(session, method)("https://example.invalid/api/private/resource")
        assert send.call_args.kwargs["timeout"] == (3, 19)
        assert send.call_args.kwargs["verify"] is True
        getattr(session, method)("https://example.invalid/resource", timeout=4)
        assert send.call_args.kwargs["timeout"] == 4
        assert session.timeout == (3, 19)


@pytest.mark.parametrize("timeout", [0, -1, (1, 0), False, None])
def test_invalid_private_timeout_prevents_network(monkeypatch, timeout):
    send = Mock()
    monkeypatch.setattr(requests.Session, "send", send)
    with pytest.raises(ValueError):
        PrivateClient("example.invalid", "user", "password", timeout=timeout)
    send.assert_not_called()


def test_private_tls_uses_supplied_ca(tls_server):
    with PrivateClient(
        f"https://localhost:{tls_server}",
        "user",
        "password",
        SAVED,
        "3.4",
        verify=FIXTURES / "localhost-cert.pem",
        timeout=(2, 5),
    ) as api:
        api.session.trust_env = False
        assert api.whoami() == {}


@pytest.mark.parametrize(
    "host,verify", [("localhost", True), ("127.0.0.1", FIXTURES / "localhost-cert.pem")]
)
def test_private_tls_rejects_untrusted_ca_and_hostname(tls_server, host, verify):
    with PrivateClient(
        f"https://{host}:{tls_server}",
        "user",
        "password",
        SAVED,
        "3.4",
        verify=verify,
        timeout=(2, 5),
    ) as api:
        api.session.trust_env = False
        with pytest.raises(requests.exceptions.SSLError):
            api.session.get(api.url + "/api/whoami")


def test_export_streams_atomically_and_uses_request_timeout(
    client, monkeypatch, tmp_path
):
    metadata = make_response('{"fileID":"export"}', 200)
    download = StreamingResponse([b"abc", b"def"])
    post, get = Mock(return_value=metadata), Mock(return_value=download)
    monkeypatch.setattr(client.session, "post", post)
    monkeypatch.setattr(client.session, "get", get)
    target = tmp_path / "archive.bin"
    assert (
        client.export_content(
            ["resource"], "tenant", file_path=target, timeout=(3, 90), chunk_size=3
        )
        == 200
    )
    assert target.read_bytes() == b"abcdef"
    assert post.call_args.kwargs["timeout"] == (3, 90)
    assert get.call_args.kwargs["stream"] is True
    assert get.call_args.kwargs["timeout"] == (3, 90)
    assert download.chunk_size == 3
    download.close.assert_called_once()


@pytest.mark.parametrize(
    "version,field",
    [
        ("2.1.0", "password"),
        ("3.4", "password"),
        ("4.0", "newPassword"),
        ("4.1", "newPassword"),
        ("4.1.2.100", "newPassword"),
        ("4.2", "newPassword"),
        ("4.2.1.100", "newPassword"),
    ],
)
def test_private_export_password_field_matches_release(
    monkeypatch, tmp_path, version, field
):
    with PrivateClient("example.invalid", "user", "password", SAVED, version) as api:
        post = Mock(return_value=make_response('{"fileID":"export"}', 200))
        monkeypatch.setattr(api.session, "post", post)
        monkeypatch.setattr(
            api.session, "get", Mock(return_value=StreamingResponse([b"archive"]))
        )
        api.export_content(
            ["resource"],
            "tenant",
            password="archive-password",
            file_path=tmp_path / "export.bin",
        )
        assert post.call_args.kwargs["json"] == {
            "ids": ["resource"],
            "tenantID": "tenant",
            field: "archive-password",
        }


@pytest.mark.parametrize("phase", ["export", "download"])
def test_export_preserves_original_network_error_and_existing_file(
    client, monkeypatch, tmp_path, phase
):
    error = requests.Timeout("simulated timeout")
    target = tmp_path / "archive.bin"
    target.write_bytes(b"previous backup")
    monkeypatch.setattr(
        client.session,
        "post",
        Mock(return_value=make_response('{"fileID":"export"}', 200)),
    )
    monkeypatch.setattr(client.session, "get", Mock(side_effect=error))
    if phase == "export":
        monkeypatch.setattr(client.session, "post", Mock(side_effect=error))
    with pytest.raises(requests.Timeout) as caught:
        client.export_content(["resource"], "tenant", file_path=target)
    assert caught.value is error
    assert target.read_bytes() == b"previous backup"


def test_private_download_http_error_does_not_replace_file(
    client, monkeypatch, tmp_path
):
    target = tmp_path / "archive.bin"
    target.write_bytes(b"previous backup")
    monkeypatch.setattr(
        client.session,
        "post",
        Mock(return_value=make_response('{"fileID":"export"}', 200)),
    )
    response = make_response('{"message":"not found"}', 404)
    response.close = Mock()
    monkeypatch.setattr(client.session, "get", Mock(return_value=response))
    with pytest.raises(APIError) as caught:
        client.export_content(["resource"], "tenant", file_path=target)
    assert caught.value.status_code == 404
    assert target.read_bytes() == b"previous backup"
    response.close.assert_called_once()


def test_import_uses_bounded_upload_reads_and_closes_file(
    client, monkeypatch, tmp_path
):
    payload = b"archive" * 10000
    source = io.BytesIO(payload)
    guarded = GuardedFile(source, 1024)
    guarded.close = source.close
    monkeypatch.setattr(
        "kuma._common.transfers.open", lambda *args: guarded, raising=False
    )
    uploaded = []

    def post(url, **kwargs):
        assert kwargs["timeout"] == (2, 40)
        if url.endswith("/upload"):
            body = kwargs["data"]
            chunks = []
            while chunk := body.read(8192):
                chunks.append(chunk)
            uploaded.append(b"".join(chunks))
            return make_response('{"id":"file"}', 200)
        if url.endswith("/toc"):
            return make_response('{"resources":[{"id":"resource"}]}', 200)
        assert kwargs["json"]["actions"] == {"resource": 0}
        return make_response("", 204)

    monkeypatch.setattr(client.session, "post", post)
    assert (
        client.import_content(
            tmp_path / "archive.bin",
            "tenant",
            action=0,
            timeout=(2, 40),
            chunk_size=1024,
        )
        == 204
    )
    assert payload in uploaded[0]
    assert len(guarded.read_sizes) > 2
    assert source.closed


def test_import_first_request_timeout_is_not_masked(client, monkeypatch, tmp_path):
    path = tmp_path / "archive.bin"
    path.write_bytes(b"archive")
    error = requests.ReadTimeout("simulated")
    monkeypatch.setattr(client.session, "post", Mock(side_effect=error))
    with pytest.raises(requests.ReadTimeout) as caught:
        client.import_content(path, "tenant")
    assert caught.value is error


@pytest.mark.parametrize(
    "data,expected",
    [(b'{"key":"a"}\n{"key":"b"}\n', [{"key": "a"}, {"key": "b"}]), (b"", [])],
)
def test_explicit_buffered_active_list_accepts_ndjson(
    client, monkeypatch, data, expected
):
    get = Mock(
        side_effect=[make_response('{"id":"file"}', 200), StreamingResponse([data])]
    )
    monkeypatch.setattr(client.session, "get", get)
    assert (
        client.get_active_list_content("correlator", "list", stream=False) == expected
    )


@pytest.mark.parametrize("mode", ["stream", "file", "buffered"])
def test_active_list_download_modes_do_not_disable_tls_or_create_debug_files(
    client, monkeypatch, tmp_path, mode
):
    monkeypatch.chdir(tmp_path)
    response = StreamingResponse([b'[{"id":1}]'])
    get = Mock(side_effect=[make_response('{"id":"file"}', 200), response])
    monkeypatch.setattr(client.session, "get", get)
    options = (
        {"filepath": tmp_path / "active.json"}
        if mode == "file"
        else {"stream": mode != "buffered"}
    )
    result = client.get_active_list_content("correlator", "list", **options)
    if mode == "stream":
        assert isinstance(result, DownloadStream)
        with result:
            assert b"".join(result) == b'[{"id":1}]'
    elif mode == "file":
        assert (tmp_path / "active.json").read_bytes() == b'[{"id":1}]'
    else:
        assert result == [{"id": 1}]
    assert all("verify" not in call.kwargs for call in get.call_args_list)
    assert not (tmp_path / "test_file1").exists()
    assert not (tmp_path / "test_file2").exists()
