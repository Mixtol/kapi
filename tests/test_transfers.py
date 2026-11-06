import hashlib
import io
import json
import threading
import tracemalloc
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from kuma import APIError, DownloadStream, RestClient
from kuma.rest._transfer import CHUNK_SIZE
from tests.test_api_errors import make_response


class StreamingResponse:
    status_code = 200
    headers = {"Content-Type": "application/octet-stream"}

    def __init__(self, chunks):
        self.chunks = chunks
        self.close = Mock()

    @property
    def content(self):
        raise AssertionError("A streaming download must not access response.content")

    @property
    def text(self):
        raise AssertionError("A streaming download must not access response.text")

    def iter_content(self, chunk_size):
        self.chunk_size = chunk_size
        yield from self.chunks


@pytest.mark.parametrize(
    "method,args",
    [
        ("system.backup", ()),
        ("resources.download", ("file",)),
        ("active_lists.download", ("file",)),
        ("dictionaries.content", ("dictionary",)),
        ("context_tables.export", ("correlator", "table")),
    ],
)
def test_file_downloads_stream_and_close(monkeypatch, tmp_path, method, args):
    response = StreamingResponse([b"abc", b"", b"def"])
    path = tmp_path / "download.bin"
    with RestClient("example.invalid", "test-token") as client:
        request = Mock(return_value=response)
        monkeypatch.setattr(client.session, "request", request)
        module, member = method.split(".")
        assert getattr(getattr(client, module), member)(
            *args, filepath=path, chunk_size=3
        ) == (200, str(path))
        assert request.call_args.kwargs["stream"] is True
    assert path.read_bytes() == b"abcdef"
    assert response.chunk_size == 3
    response.close.assert_called_once()
    assert not list(tmp_path.glob("*.part"))


def test_backup_defaults_to_a_closeable_stream(monkeypatch):
    response = StreamingResponse([b"one", b"two"])
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(client.session, "request", Mock(return_value=response))
        status, stream = client.system.backup()
        assert status == 200 and isinstance(stream, DownloadStream)
        with stream:
            assert next(stream) == b"one"
        assert list(stream) == []
    response.close.assert_called_once()


def test_stream_exhaustion_closes_response(monkeypatch):
    response = StreamingResponse([b"one", b"two"])
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(client.session, "request", Mock(return_value=response))
        _, stream = client.system.backup()
        assert list(stream) == [b"one", b"two"]
    assert stream.closed
    response.close.assert_called_once()


def test_interrupted_download_preserves_existing_file(monkeypatch, tmp_path):
    def broken():
        yield b"partial"
        raise requests.exceptions.ChunkedEncodingError("truncated download")

    response = StreamingResponse(broken())
    path = tmp_path / "backup.tar.gz"
    path.write_bytes(b"old valid backup")
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(client.session, "request", Mock(return_value=response))
        with pytest.raises(APIError, match="Download failed") as caught:
            client.system.backup(path)
    assert isinstance(caught.value.__cause__, requests.RequestException)
    assert path.read_bytes() == b"old valid backup"
    assert list(tmp_path.iterdir()) == [path]
    response.close.assert_called_once()


def test_download_memory_is_independent_of_total_size(monkeypatch, tmp_path):
    chunk = b"x" * CHUNK_SIZE
    response = StreamingResponse((chunk for _ in range(1024)))  # 64 MiB on disk.
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(client.session, "request", Mock(return_value=response))
        tracemalloc.start()
        try:
            client.system.backup(tmp_path / "backup.bin")
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    assert (tmp_path / "backup.bin").stat().st_size == 64 * 1024 * 1024
    assert peak < 2 * 1024 * 1024


def test_short_response_does_not_replace_target(monkeypatch, tmp_path):
    response = StreamingResponse([b"short"])
    response.headers = {"Content-Length": "100"}
    path = tmp_path / "backup.bin"
    path.write_bytes(b"previous")
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(client.session, "request", Mock(return_value=response))
        with pytest.raises(APIError, match="Incomplete download"):
            client.system.backup(path)
    assert path.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [path]


def test_decoded_response_length_is_not_compared_with_compressed_length():
    response = StreamingResponse([b"decoded data"])
    response.headers = {"Content-Length": "4", "Content-Encoding": "gzip"}
    assert list(DownloadStream(response)) == [b"decoded data"]


@pytest.mark.parametrize("state", ["partial", "closed", "exhausted", "saved"])
def test_reused_stream_cannot_overwrite_an_existing_file(tmp_path, state):
    response = StreamingResponse([b"abc", b"def"])
    stream = DownloadStream(response)
    destination = tmp_path / "existing-backup.bin"
    destination.write_bytes(b"previous complete backup")
    if state == "partial":
        next(stream)
    elif state == "closed":
        stream.close()
    elif state == "exhausted":
        list(stream)
    else:
        stream.save(tmp_path / "first.bin")
    with pytest.raises(APIError, match="closed or partially consumed"):
        stream.save(destination)
    assert destination.read_bytes() == b"previous complete backup"
    assert not list(tmp_path.glob("*.part"))
    assert stream.closed


def test_fresh_empty_stream_can_be_saved(tmp_path):
    destination = tmp_path / "empty.bin"
    stream = DownloadStream(StreamingResponse([]))
    assert stream.save(destination) == str(destination)
    assert destination.read_bytes() == b""


def test_explicit_buffered_backup_is_available(monkeypatch):
    with RestClient("example.invalid", "test-token") as client:
        monkeypatch.setattr(
            client.session,
            "request",
            Mock(
                return_value=make_response(b"archive", 200, "application/octet-stream")
            ),
        )
        assert client.system.backup(stream=False) == (200, b"archive")


@pytest.fixture(scope="module")
def http_server():
    state = {"uploads": [], "download": b"test-archive-" * 10000}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(state["download"])))
            self.end_headers()
            for offset in range(0, len(state["download"]), 4096):
                self.wfile.write(state["download"][offset : offset + 4096])

        def do_POST(self):
            count = int(self.headers["Content-Length"])
            chunks = []
            while count:
                data = self.rfile.read(min(count, 8192))
                if not data:
                    break
                chunks.append(data)
                count -= len(data)
            state["uploads"].append((self.path, self.headers, b"".join(chunks)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


class GuardedFile:
    def __init__(self, wrapped, limit):
        self.wrapped = wrapped
        self.limit = limit
        self.read_sizes = []

    def read(self, size=-1):
        assert 0 <= size <= self.limit, "unbounded upload read"
        self.read_sizes.append(size)
        return self.wrapped.read(size)

    def tell(self):
        return self.wrapped.tell()

    def seek(self, *args):
        return self.wrapped.seek(*args)


@pytest.mark.parametrize(
    "method", ["restore", "resource", "dictionary", "active_list", "context_table"]
)
def test_real_http_uploads_use_bounded_reads_and_correct_body(http_server, method):
    url, state = http_server
    payload = ("key,value\na,текст\n" * 10000).encode()
    with (
        io.BytesIO(b"skip" + payload) as source,
        RestClient(url, "test-token", timeout=(2, 5)) as client,
    ):
        source.seek(4)
        guarded = GuardedFile(source, 1024)
        if method == "restore":
            client.system.restore(data=guarded, chunk_size=1024)
        elif method == "resource":
            client.resources.upload(guarded, chunk_size=1024)
        elif method == "dictionary":
            client.dictionaries.update("dictionary", guarded, chunk_size=1024)
        elif method == "active_list":
            client.active_lists.import_data(
                "correlator",
                "csv",
                guarded,
                activeListID="list",
                keyField="key",
                clear=False,
                chunk_size=1024,
            )
        else:
            client.context_tables.import_data(
                "correlator",
                "csv",
                guarded,
                contextTableID="table",
                clear=False,
                chunk_size=1024,
            )
        assert not source.closed
        assert len(guarded.read_sizes) > 2
    path, headers, body = state["uploads"][-1]
    assert "clear" not in path
    assert int(headers["Content-Length"]) == len(body)
    assert headers["Authorization"] == "Bearer test-token"
    if method == "dictionary":
        message = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: "
            + headers["Content-Type"].encode()
            + b"\r\nMIME-Version: 1.0\r\n\r\n"
            + body
        )
        parts = list(message.iter_parts())
        assert len(parts) == 1
        assert parts[0].get_param("name", header="content-disposition") == "file"
        body = parts[0].get_payload(decode=True)
    assert hashlib.sha256(body).digest() == hashlib.sha256(payload).digest()


def test_real_file_paths_and_download(http_server, tmp_path):
    url, state = http_server
    source = tmp_path / "input.bin"
    source.write_bytes(b"test archive" * 1000)
    with RestClient(url, "test-token", timeout=5) as client:
        client.system.restore(filepath=source)
        assert state["uploads"][-1][2] == source.read_bytes()
        client.resources.upload(str(source))
        assert state["uploads"][-1][2] == source.read_bytes()
        csv = tmp_path / "dictionary.csv"
        csv.write_text("key,value\na,b\n")
        client.dictionaries.update("dictionary", filepath=csv)
        client.system.backup(tmp_path / "backup.tar.gz")
        assert (tmp_path / "backup.tar.gz").read_bytes() == state["download"]


@pytest.mark.parametrize("chunk_size", [0, -1, True, 1.5])
def test_invalid_chunk_sizes_fail_before_network(monkeypatch, chunk_size):
    with RestClient("example.invalid", "test-token") as client:
        request = Mock()
        monkeypatch.setattr(client.session, "request", request)
        with pytest.raises(ValueError):
            client.system.backup(chunk_size=chunk_size)
        with pytest.raises(ValueError):
            client.system.restore(data=b"test", chunk_size=chunk_size)
        request.assert_not_called()
