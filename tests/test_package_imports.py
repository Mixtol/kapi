import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def test_legacy_imports_reference_the_same_classes_and_version_sentinel():
    import kuma
    import kuma_api as kapi
    from kuma import APIError, DownloadStream, PrivateClient, RestClient
    from kuma._common import transfers, versions
    from kuma.errors import APIError as SharedAPIError
    from kuma.private import KumaPrivateAPI
    from kuma.rest import KumaRestAPI, _transfer, _version
    from kuma.rest.errors import APIError as RestAPIError

    assert PrivateClient is KumaPrivateAPI
    assert RestClient is KumaRestAPI
    assert APIError is SharedAPIError is RestAPIError
    assert DownloadStream is transfers.DownloadStream is _transfer.DownloadStream
    assert _version.DEFAULT_VERSION is versions.DEFAULT_VERSION
    assert kapi.__all__ == kuma.__all__
    for name in kuma.__all__:
        assert getattr(kapi, name) is getattr(kuma, name)
    assert set(kapi.__all__) <= set(dir(kapi))
    with pytest.raises(AttributeError):
        kapi.unknown_attribute


@pytest.mark.parametrize(
    "statement,blocked",
    [
        ("import kuma", "kuma.rest,kuma.private"),
        ("import kuma_api as kapi", "kuma.rest,kuma.private"),
        ("from kuma_api import PrivateClient", "kuma.rest"),
        ("from kuma_api import RestClient", "kuma.private"),
        ("import kuma.private", "kuma.rest"),
        ("from kuma import PrivateClient", "kuma.rest"),
        ("import kuma.rest", "kuma.private"),
        ("from kuma import RestClient", "kuma.private"),
    ],
)
def test_client_imports_are_independent(statement, blocked):
    script = textwrap.dedent("""
        import importlib.abc
        import sys

        blocked = sys.argv[2].split(',')

        class BlockClientImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
                    raise AssertionError('Unexpected client dependency: ' + fullname)

        sys.meta_path.insert(0, BlockClientImports())
        exec(sys.argv[1])
        import kuma
        assert set(kuma.__all__) <= set(dir(kuma))
        for name in blocked:
            assert name not in sys.modules
        """)
    result = subprocess.run(
        [sys.executable, "-c", script, statement, blocked],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
