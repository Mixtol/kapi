import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

IMPORTS = [
    "import kuma",
    "from kuma import RestClient",
    "from kuma import PrivateClient",
    "from kuma import *",
    "import kuma.private",
    "import kuma_api as kapi",
    "from kuma_api import *",
]


def run_isolated(script, *args):
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script), *map(str, args)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not result.stderr, result.stderr


@pytest.mark.parametrize("statement", IMPORTS)
def test_import_allows_application_to_configure_logging_later(statement):
    run_isolated(
        """
        import io
        import logging
        import sys
        import requests

        root = logging.getLogger()
        assert not root.handlers
        for name in ('requests', 'urllib3'):
            logging.getLogger(name).setLevel(logging.DEBUG)
        exec(sys.argv[1])
        assert not root.handlers
        assert root.level == logging.WARNING
        assert logging.getLogger('requests').level == logging.DEBUG
        assert logging.getLogger('urllib3').level == logging.DEBUG

        output = io.StringIO()
        logging.basicConfig(
            level=logging.INFO, stream=output,
            format='APP|%(levelname)s|%(message)s',
        )
        logging.getLogger('application').info('Starting')
        logging.getLogger('kuma.rest').info('public')
        logging.getLogger('kuma._logging').info('legacy')
        assert output.getvalue().splitlines() == [
            'APP|INFO|Starting', 'APP|INFO|public', 'APP|INFO|legacy',
        ]
        """,
        statement,
    )


@pytest.mark.parametrize("statement", IMPORTS)
def test_import_preserves_existing_application_and_dependency_logging(statement):
    run_isolated(
        """
        import io
        import logging
        import sys
        import requests

        output = io.StringIO()
        logging.basicConfig(
            level=logging.DEBUG, stream=output,
            format='APP|%(name)s|%(levelname)s|%(message)s',
        )
        names = ('', 'application', 'requests', 'urllib3', 'kuma._logging', 'kuma.rest')
        loggers = [logging.getLogger(name) for name in names]
        for logger in loggers[1:]:
            logger.setLevel(logging.DEBUG)

        def state(logger):
            return (
                logger.level, logger.disabled, logger.propagate,
                tuple(logger.filters),
                tuple((h, h.level, h.formatter, tuple(h.filters)) for h in logger.handlers),
            )

        before = [state(logger) for logger in loggers]
        exec(sys.argv[1])
        assert [state(logger) for logger in loggers] == before
        for logger in loggers[1:]:
            logger.debug('visible')
        assert output.getvalue().splitlines() == [
            f'APP|{name}|DEBUG|visible' for name in names[1:]
        ]
        """,
        statement,
    )


def test_legacy_file_logging_is_opt_in_local_and_not_duplicated(tmp_path):
    run_isolated(
        """
        import io
        import logging
        import sys
        from pathlib import Path
        from kuma._logging import configure_logging

        output = io.StringIO()
        logging.basicConfig(level=logging.INFO, stream=output, format='APP|%(message)s')
        root = logging.getLogger()
        before = (root.level, tuple(root.handlers), root.handlers[0].formatter)
        path = Path(sys.argv[1])
        logger = configure_logging(logging.DEBUG, str(path), 'KUMA|%(message)s')
        assert configure_logging(logging.DEBUG, str(path), 'KUMA|%(message)s') is logger
        from kuma import PrivateClient
        assert configure_logging() is logger
        assert logger.level == logging.DEBUG
        assert (root.level, tuple(root.handlers), root.handlers[0].formatter) == before

        logging.getLogger('application').info('application')
        logger.info('library')
        handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(handlers) == 1
        for handler in handlers:
            handler.flush()
        assert path.read_text(encoding='utf-8').splitlines() == ['KUMA|library']
        assert output.getvalue().splitlines() == ['APP|application', 'APP|library']
        """,
        tmp_path / "library.log",
    )


def test_public_client_uses_injected_logger_without_reconfiguring_it():
    run_isolated("""
        import io
        import logging
        from unittest.mock import patch
        import requests
        from kuma import RestClient

        app_output = io.StringIO()
        logging.basicConfig(level=logging.INFO, stream=app_output, format='APP|%(message)s')
        client_output = io.StringIO()
        logger = logging.getLogger('application.kuma')
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = logging.StreamHandler(client_output)
        handler.setFormatter(logging.Formatter('CLIENT|%(message)s'))
        logger.addHandler(handler)
        response = requests.Response()
        response.status_code = 200
        response.headers['Content-Type'] = 'application/json'
        response._content = b'{}'
        response._content_consumed = True
        with RestClient('example.invalid', 'test-token', logger=logger, version='3.4') as client:
            with patch.object(client.session, 'request', return_value=response):
                client.users.whoami()
        logging.getLogger('application').info('still visible')
        assert logger.handlers == [handler]
        assert logger.level == logging.DEBUG and not logger.propagate
        assert client_output.getvalue().splitlines() == [
            'CLIENT|Request: GET https://example.invalid:7223/api/v3/users/whoami',
        ]
        assert app_output.getvalue().splitlines() == ['APP|still visible']
        """)
