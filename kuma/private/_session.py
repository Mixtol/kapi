"""Private API session with validated TLS settings and finite request timeouts."""

import requests

from kuma._common.transport import validate_timeout, validate_verify


class PrivateSession(requests.Session):
    def __init__(self, *, verify=True, timeout=30):
        """Создать requests.Session с общей проверкой CA и конечным таймаутом.

        verify — bool либо путь к существующему CA-файлу/каталогу;
        timeout — положительные секунды или пара (connect, read).
        Настройки проверяются до создания сессии; сетевых запросов здесь нет.
        """
        validate_timeout(timeout)
        verify = validate_verify(verify)
        super().__init__()
        self.verify = verify
        self.timeout = timeout

    def request(self, method, url, **kwargs):
        """Применить таймаут клиента, если запрос не передал собственный.

        Отсутствующий timeout и timeout=None используют self.timeout.
        Неположительные/нечисловые значения отклоняются до сети. Остальные
        параметры и формат результата соответствуют requests.Session.request.
        """
        timeout = kwargs.get("timeout")
        kwargs["timeout"] = self.timeout if timeout is None else timeout
        validate_timeout(kwargs["timeout"])
        return super().request(method, url, **kwargs)
