"""TLS and timeout settings shared by both HTTP clients."""

import math
import os
from pathlib import Path
from typing import Tuple, Union

Timeout = Union[float, Tuple[float, float]]
Verify = Union[bool, str, os.PathLike]


def validate_verify(verify: Verify) -> Union[bool, str]:
    if isinstance(verify, bool):
        return verify
    if isinstance(verify, (str, os.PathLike)):
        path = Path(verify).expanduser().resolve()
        if not str(verify) or not path.exists():
            raise ValueError("CA bundle file or CA directory does not exist")
        return str(path)
    raise TypeError("verify must be True, False, or a CA bundle path")


def validate_timeout(timeout: Timeout) -> None:
    values = timeout if isinstance(timeout, tuple) else (timeout,)
    if isinstance(timeout, tuple) and len(timeout) != 2:
        raise ValueError("timeout must be seconds or (connect, read) seconds")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        for value in values
    ):
        raise ValueError("Timeouts must be positive numbers")
