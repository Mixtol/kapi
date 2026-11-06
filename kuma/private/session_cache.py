"""Необязательный зашифрованный кеш сессии приватного API."""

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from kuma._common.versions import normalize_version


class PrivateSessionCache:
    """Кеш Fernet, привязанный к адресу Core, пользователю и версии KUMA.

    Требует kuma-api[session-cache]. Ключ Fernet передаёт приложение из своего
    хранилища секретов; библиотека не создаёт и не сохраняет ключ. Срок действия
    проверяется по аутентифицированной метке времени Fernet. Повреждённый или
    просроченный кеш считается отсутствующим; ошибки TLS и входа передаются выше.
    """

    def __init__(self, path, key, *, max_age=8 * 3600):
        from cryptography.fernet import Fernet

        if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age <= 0:
            raise ValueError("max_age должен быть положительным числом секунд")
        self.path = Path(path)
        self.cipher = Fernet(key)
        self.max_age = max_age

    @staticmethod
    def _identity(url, username, version):
        parsed = urlsplit(url if "://" in url else "https://" + url)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Некорректный адрес Core")
        host = parsed.hostname
        if ":" in host:
            host = "[" + host + "]"
        canonical = urlunsplit(
            (
                parsed.scheme,
                host + ":" + str(parsed.port or 7220),
                parsed.path.rstrip("/"),
                "",
                "",
            )
        )
        return [canonical, username, normalize_version(version)]

    def load(self, url, username, version):
        """Вернуть session_data или None, если кеш отсутствует либо недействителен."""
        from cryptography.fernet import InvalidToken

        identity = self._identity(url, username, version)
        try:
            encrypted = self.path.read_bytes()
        except FileNotFoundError:
            return None
        try:
            data = json.loads(self.cipher.decrypt(encrypted, ttl=self.max_age))
        except (InvalidToken, ValueError, UnicodeError):
            return None
        if not isinstance(data, dict) or data.get("identity") != identity:
            return None
        return data.get("session") if isinstance(data.get("session"), dict) else None

    def save(self, client):
        """Атомарно заменить шифротекст; при ошибке записи сохранить прежний кеш."""
        data = {
            "identity": self._identity(client.url, client.username, client.version),
            "session": client.get_session_data(),
        }
        encrypted = self.cipher.encrypt(json.dumps(data).encode("utf-8"))
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.path.parent,
                prefix="." + self.path.name + ".",
                delete=False,
            ) as output:
                temporary = Path(output.name)
                output.write(encrypted)
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def open_client(self, url, username, password, *, version, **options):
        """Восстановить и проверить сессию либо войти и сохранить новую.

        Повторный вход выполняет PrivateClient только после HTTP 401/403.
        Изменяющие запросы автоматически не повторяются. Вызывающий код закрывает
        клиент; после logout кешированная сессия не пройдёт следующую проверку.
        """
        from kuma import PrivateClient

        if "session_data" in options or "validate_session" in options:
            raise ValueError(
                "Кеш самостоятельно задаёт session_data и validate_session"
            )
        client = PrivateClient(
            url,
            username,
            password,
            self.load(url, username, version),
            version,
            validate_session=True,
            **options,
        )
        try:
            self.save(client)
        except BaseException:
            client.close()
            raise
        return client
