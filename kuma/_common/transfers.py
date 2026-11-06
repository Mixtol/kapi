"""Bounded-memory file transfers shared by the public and private clients."""

import io
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator, Union

import requests

from kuma.errors import APIError

CHUNK_SIZE = 64 * 1024
FilePath = Union[str, os.PathLike]
UploadData = Union[str, bytes, BinaryIO, os.PathLike]


def validate_chunk_size(chunk_size: int) -> None:
    if (
        isinstance(chunk_size, bool)
        or not isinstance(chunk_size, int)
        or chunk_size <= 0
    ):
        raise ValueError("chunk_size must be a positive integer")


class DownloadStream(Iterator[bytes]):
    """Single-use chunk iterator. Use as a context manager when stopping early."""

    def __init__(self, response: requests.Response, chunk_size: int = CHUNK_SIZE):
        validate_chunk_size(chunk_size)
        self.status_code = response.status_code
        self.headers = response.headers.copy()
        self._response = response
        self._chunks = response.iter_content(chunk_size=chunk_size)
        self.closed = False
        self.received_bytes = 0
        length = response.headers.get("Content-Length", "")
        encoding = response.headers.get("Content-Encoding", "identity").lower()
        self._expected_length = (
            int(length) if length.isdigit() and encoding == "identity" else None
        )

    def __iter__(self):
        return self

    def __next__(self) -> bytes:
        if self.closed:
            raise StopIteration
        try:
            while True:
                chunk = next(self._chunks)
                if chunk:
                    self.received_bytes += len(chunk)
                    return chunk
        except StopIteration:
            self.close()
            if (
                self._expected_length is not None
                and self.received_bytes != self._expected_length
            ):
                raise APIError(
                    f"Incomplete download: expected {self._expected_length} bytes, received {self.received_bytes}",
                    self.status_code,
                ) from None
            raise
        except requests.RequestException as exc:
            self.close()
            raise APIError(f"Download failed: {exc}", self.status_code) from exc
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._response.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def save(self, filepath: FilePath) -> str:
        """Replace the target only after the complete response has been written."""
        destination = Path(filepath)
        temporary = None
        try:
            if self.closed or self.received_bytes:
                raise APIError(
                    "Cannot save a closed or partially consumed download",
                    self.status_code,
                )
            with (
                self,
                tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=destination.parent,
                    prefix=f".{destination.name}.",
                    suffix=".part",
                    delete=False,
                ) as output,
            ):
                temporary = Path(output.name)
                for chunk in self:
                    output.write(chunk)
            os.replace(temporary, destination)
            temporary = None
            return os.fspath(filepath)
        except OSError as exc:
            raise APIError(f"File operation failed: {exc}", self.status_code) from exc
        finally:
            self.close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class UploadReader:
    """Seekable binary source that never performs an unbounded read."""

    def __init__(self, source: BinaryIO, chunk_size: int = CHUNK_SIZE):
        validate_chunk_size(chunk_size)
        self.source = source
        self.chunk_size = chunk_size
        if isinstance(source, io.TextIOBase):
            raise ValueError("Upload streams must be opened in binary mode")
        try:
            position = source.tell()
            source.seek(0, os.SEEK_END)
            self._end = source.tell()
            source.seek(position)
        except (AttributeError, OSError) as exc:
            raise ValueError("Upload streams must support seek() and tell()") from exc

    @property
    def len(self):
        return max(0, self._end - self.source.tell())

    def read(self, size=-1):
        size = (
            self.chunk_size if size is None or size < 0 else min(size, self.chunk_size)
        )
        size = min(size, self.len)
        chunk = self.source.read(size)
        if not isinstance(chunk, bytes):
            raise TypeError("Upload streams must return bytes")
        if size and not chunk:
            raise OSError("Upload source ended before its advertised length")
        return chunk


@contextmanager
def upload_source(data=None, filepath=None, chunk_size=CHUNK_SIZE):
    """Close owned files; leave caller-owned streams open."""
    validate_chunk_size(chunk_size)
    if filepath is not None and data is not None:
        raise ValueError("Specify either filepath or data, not both")
    if isinstance(data, os.PathLike):
        filepath, data = data, None
    owned = False
    source = None
    try:
        if filepath is not None:
            source = open(filepath, "rb")
            owned = True
        elif isinstance(data, (str, bytes)):
            source = io.BytesIO(data.encode("utf-8") if isinstance(data, str) else data)
            owned = True
        elif hasattr(data, "read"):
            source = data
        else:
            raise ValueError(
                "Supply a file path, bytes, text, or a seekable binary stream"
            )
        yield UploadReader(source, chunk_size)
    except requests.RequestException:
        # RequestException also inherits OSError; keep network failures intact.
        raise
    except OSError as exc:
        raise APIError(f"File operation failed: {exc}") from exc
    finally:
        if owned and source is not None:
            source.close()
