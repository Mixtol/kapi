from typing import Optional

from kuma._common.transfers import CHUNK_SIZE
from kuma.rest._base import APIResult, KumaRestAPIModule


class KumaRestAPISystem(KumaRestAPIModule):
    """Methods for System."""

    def backup(
        self,
        filepath: Optional[str] = None,
        timeout=900,
        *,
        stream=True,
        chunk_size=CHUNK_SIZE,
    ):
        """
        Download a Core backup to a file or a managed chunk iterator.
        Use stream=False explicitly to return the complete body in memory.
        timeout is seconds or (connect, read) seconds, not an overall deadline.
        """
        return self._download(
            "system/backup",
            filepath,
            stream=stream,
            timeout=timeout,
            chunk_size=chunk_size,
        )

    def restore(
        self,
        filepath: Optional[str] = None,
        data=None,
        *,
        timeout=900,
        chunk_size=CHUNK_SIZE,
    ) -> APIResult:
        """
        Restoring core from .tar.gz with the backup copy
        filepath: str - Relative path to bak file
        data: bytes - Bin backup data
        """
        return self._upload(
            "system/restore",
            data,
            filepath=filepath,
            timeout=timeout,
            chunk_size=chunk_size,
        )
