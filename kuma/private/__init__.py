"""Приватный API KUMA: авторизация, сессия и методы веб-интерфейса."""

import json
import logging
from typing import Optional
from urllib.parse import unquote, urlsplit, urlunsplit

import requests

from kuma._common.transport import Timeout, Verify
from kuma._common.versions import (
    SUPPORTED_VERSIONS,
    normalize_version,
    resolve_contract_version,
)
from kuma._logging import configure_logging
from kuma.errors import APIError
from kuma.private._base import PrivateRequests
from kuma.private._session import PrivateSession
from kuma.private.folders import PrivateFolders
from kuma.private.resources import PrivateResources
from kuma.private.rules import AVAILABLE_RULE_TYPES, PrivateRules
from kuma.private.settings import PrivateSettings
from kuma.private.transfers import PrivateTransfers

_logger = configure_logging()


class KumaPrivateAPI(
    PrivateFolders,
    PrivateResources,
    PrivateRules,
    PrivateSettings,
    PrivateTransfers,
    PrivateRequests,
):
    """Клиент приватного API с cookie/XSRF-авторизацией, порт по умолчанию 7220.

    Импорты: ``from kuma import PrivateClient`` или
    ``from kuma_api import PrivateClient``. Методы доступны на самом клиенте.
    ID конфигурации ресурса и ID запущенного сервиса различаются; нужный вид
    ID указан в документации каждого метода.

    Форматы результатов сохранены для совместимости и различаются по методам.
    Большинство старых методов возвращает тело HTTP-ошибки строкой. Итераторы,
    файловые операции и явно отмеченные методы вызывают APIError. Успешный
    JSON-метод возвращает None при HTTP 204; некорректный JSON вызывает APIError.
    Сетевые исключения requests обычно передаются вызывающему коду без замены;
    исключение — whoami(), сохраняющий исторический ConnectionError.

    Выбранные тенанты и сессия изменяемы: экземпляр предназначен для
    последовательного использования. Для независимых операций создавайте
    отдельных клиентов. Контекстный менеджер закрывает соединения, но не
    завершает серверную сессию: для этого нужен явный logout().
    """

    DEFAULT_PORT = 7220
    DEFAULT_TIMEOUT = 30
    DEFAULT_SCHEME = "https"

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        session_data: dict = None,
        version: str = "2.1.0",
        logger: Optional[logging.Logger] = None,
        *,
        verify: Verify = True,
        timeout: Timeout = DEFAULT_TIMEOUT,
        validate_session: bool = False,
    ):
        """Создать сессию, восстановить cookie либо выполнить вход в KUMA.

        Args:
            url: Адрес Core; без схемы используется HTTPS, без порта — 7220.
            username: Логин учётной записи приватного API.
            password: Пароль входа. Также служит запасным паролем архива,
                если export_content/import_content не получили свой password.
            session_data: Результат get_session_data(). При корректной структуре
                и validate_session=False восстанавливается без HTTP-запросов.
            version: Версия KUMA. Поддерживаются 2.x, 3.x, 4.0, 4.1, 4.2;
                2.1.0 оставлена по умолчанию для совместимости. Patch/build
                допустимы, исходная строка сохраняется в self.version.
                Для 4.1 используются запросы 4.0; см. contract_version.
            logger: Логгер этого клиента; настройки приложения не изменяются.
            verify: True — стандартная проверка TLS, False — без проверки TLS,
                либо путь к CA-файлу/каталогу доверенных сертификатов.
            timeout: Положительное число секунд или пара (connect, read).
                Применяется ко всем запросам, если метод не получил свой timeout.
            validate_session: Проверить восстановленные cookie через whoami().
                Повторный вход выполняется только после HTTP 401/403.
                Ошибки сети и CA не запускают повторную авторизацию.

        Свежий вход выбирает все доступные тенанты. Некорректные session_data
        приводят к новому входу. Версия из session_data не меняет version
        конструктора. Ошибка инициализации закрывает созданную HTTP-сессию.
        """
        normalized = normalize_version(version)
        major = int(normalized.split(".")[0])
        if major not in (2, 3) and normalized not in SUPPORTED_VERSIONS:
            raise ValueError(
                "Unsupported private API version; use 2.x, 3.x, 4.0, 4.1 or 4.2"
            )
        self.user = {}
        self.username = username
        self.password = password
        self.version = version
        self._contract_version = resolve_contract_version(normalized)
        self._major_version = int(self._contract_version.split(".")[0])
        self.logger = logger if logger is not None else _logger
        self.verify = verify
        self.timeout = timeout
        self.validate_session = validate_session
        self.selected_tenants = []
        self._tenants = {}
        self._configure_url(url)
        self._configure_session(session_data)

    @property
    def contract_version(self) -> str:
        """Версия формата запросов: major.minor, для KUMA 4.1 — строка '4.0'.

        Не обращается к серверу и не меняет self.version. Фактическую версию
        установленного Core возвращает get_version().
        """
        return self._contract_version

    def _configure_url(self, url: str) -> None:
        """Нормализовать адрес Core; отклонить credentials/query/fragment в URL."""
        if not isinstance(url, str) or not url.strip():
            raise ValueError("KUMA URL cannot be empty")
        url = url.strip()
        if "://" not in url:
            url = f"{self.DEFAULT_SCHEME}://{url}"
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("KUMA URL must be an HTTP(S) URL with a hostname")
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "KUMA URL must not contain credentials, a query, or a fragment"
            )
        if any(char.isspace() for char in parsed.hostname):
            raise ValueError("Invalid KUMA hostname")
        port = parsed.port if parsed.port is not None else self.DEFAULT_PORT
        if port == 0:
            raise ValueError("KUMA port must be between 1 and 65535")
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        self.url = urlunsplit(
            (parsed.scheme, f"{host}:{port}", parsed.path.rstrip("/"), "", "")
        )

    def _configure_session(self, session_data=None) -> None:
        """Восстановить или создать сессию; закрыть её при сбое инициализации."""
        self.session = PrivateSession(verify=self.verify, timeout=self.timeout)
        self.verify = self.session.verify
        try:
            if session_data:
                try:
                    self.load_session(session_data)
                except (KeyError, TypeError, ValueError):
                    self.logger.warning(
                        "Saved session data is invalid; logging in again"
                    )
                else:
                    if not self.validate_session:
                        return
                    try:
                        self._test_session()
                        return
                    except ConnectionError as exc:
                        response = getattr(exc.__cause__, "response", None)
                        if response is None or response.status_code not in (401, 403):
                            raise
                        self.logger.info("Saved session has expired; logging in again")
                self.session.cookies.clear()
                self.session.headers.pop("X-XSRF-TOKEN", None)
            self.initialize_session()
        except BaseException:
            self.session.close()
            raise

    @classmethod
    def create_session(
        cls,
        url,
        username,
        password,
        existing_session_data=None,
        cert=None,
        *,
        version="2.1.0",
        logger=None,
        verify=True,
        timeout=DEFAULT_TIMEOUT,
        validate_session=False,
    ):
        """Фабрика клиента с совместимой сигнатурой; возвращает экземпляр cls.

        existing_session_data соответствует session_data конструктора.
        cert — старое имя аргумента CA, а не клиентский сертификат mTLS.
        Передавайте cert либо verify; сочетание cert с verify, отличным от
        True, вызывает ValueError. Остальные аргументы описаны в __init__().
        Новый вход выполняется один раз; валидная сохранённая сессия при
        validate_session=False восстанавливается без обращения к серверу.
        """
        if cert is not None:
            if verify is not True:
                raise ValueError("Specify either cert or verify, not both")
            verify = cert
        return cls(
            url,
            username,
            password,
            existing_session_data,
            version,
            logger,
            verify=verify,
            timeout=timeout,
            validate_session=validate_session,
        )

    def close(self):
        """Закрыть локальные соединения requests; возвращает None.

        Серверная сессия и cookie не отзываются. Для выхода сначала вызовите
        logout(), затем close(); выход из блока with вызывает только close().
        """
        self.session.close()

    def __enter__(self):
        """Вернуть клиент без повторной авторизации."""
        return self

    def __exit__(self, *args):
        """Закрыть локальные соединения, не подавляя исключение блока with."""
        self.close()

    def load_session(self, session_data):
        """Загрузить headers, cookies и xsrf_token из get_session_data().

        Добавляет данные к текущей HTTP-сессии без запросов к серверу;
        устанавливает X-XSRF-TOKEN, игнорируя сохранённый заголовок Cookie.
        Версия клиента и выбор тенантов этим методом не меняются. Проверка
        актуальности выполняется отдельно через whoami(). Возвращает None.
        При отсутствующих/некорректных полях возможны KeyError, TypeError,
        ValueError. Содержимое session_data даёт доступ к сессии пользователя.
        """
        cookies = requests.utils.cookiejar_from_dict(session_data["cookies"])
        headers = dict(session_data["headers"])
        token = session_data["xsrf_token"]
        if not isinstance(token, str) or not token:
            raise ValueError("Saved session has no XSRF token")
        headers = {
            key: value for key, value in headers.items() if key.lower() != "cookie"
        }
        self.session.cookies.update(cookies)
        self.session.headers.update(headers)
        self.session.headers["X-XSRF-TOKEN"] = token

    def _test_session(self):
        """Проверить cookie через whoami(), не переключая тенанты на сервере."""
        return self.whoami()

    def initialize_session(self):
        """Войти с сохранёнными username/password и выбрать все тенанты.

        Возвращает None. Ответ login() закрывается при любом результате.
        HTTP 401/402/403 вызывает ConnectionError; остальные неуспешные
        статусы — APIError с исходным ответом. В частности, mustChangePassword
        означает требование смены пароля, authBlocked — блокировку входа.
        """
        response = self.login(self.username, self.password)
        try:
            if response.status_code in (200, 204):
                self.private_select_tenant(select_all=True)
            elif response.status_code in (401, 402, 403):
                raise ConnectionError(
                    f"Bad credentials {self.url} response: {response.status_code}"
                )
            else:
                raise APIError.from_response(response)
        finally:
            response.close()

    def login(self, username, password, timeout: Optional[Timeout] = None):
        """POST /api/login: войти и обновить cookie и заголовок X-XSRF-TOKEN.

        username/password — учётные данные; timeout переопределяет таймаут
        только этого запроса, None использует таймаут клиента. Тенанты здесь
        не выбираются: полный цикл входа выполняет initialize_session().

        Возвращает незакрытый requests.Response, включая HTTP-ошибки;
        вызывающий код обязан закрыть его. При успехе без cookie XSRF-TOKEN
        ответ закрывается и вызывается ConnectionError. Сетевые исключения
        requests передаются без замены. Перенаправления не выполняются.
        """
        response = self.session.post(
            self.url + "/api/login",
            data=json.dumps({"login": username, "password": password}),
            timeout=timeout,
            allow_redirects=False,
        )
        if response.status_code in (200, 204):
            token = self.session.cookies.get("XSRF-TOKEN")
            if not token:
                response.close()
                raise ConnectionError(
                    "Login response did not include an XSRF-TOKEN cookie"
                )
            self.session.headers.update({"X-XSRF-TOKEN": unquote(token)})
        return response

    def get_session_data(self) -> dict:
        """Вернуть снимок headers, cookies, xsrf_token и выбранной version.

        Запросов к серверу нет. Словарь предназначен для session_data
        конструктора или load_session(); содержит действующие данные входа
        и не должен попадать в логи. Выбор тенантов хранится на сервере,
        актуальное значение можно получить через whoami().
        """
        return {
            "headers": dict(self.session.headers),
            "cookies": requests.utils.dict_from_cookiejar(self.session.cookies),
            "xsrf_token": self.session.headers.get("X-XSRF-TOKEN"),
            "version": self.version,
        }

    def logout(self) -> int:
        """POST /api/logout: завершить серверную сессию и вернуть HTTP-статус.

        HTTP-ошибка возвращается кодом, а не APIError. Локальные соединения
        закрываются отдельно через close(); cookie здесь не очищаются.
        """
        return self._result("POST", "/api/logout", text=True)[0]

    def whoami(self):
        """GET /api/whoami: вернуть словарь текущего пользователя.

        Обновляет self.user и локальный selected_tenants, если ответ содержит
        selectedTenants. Не переключает тенанты на сервере. Ответ закрывается
        автоматически. HTTP/сетевые ошибки и ошибка разбора JSON оборачиваются
        в ConnectionError; исходное исключение доступно через __cause__.
        JSON, который не является объектом, вызывает APIError.
        """
        response = None
        try:
            response = self._send("GET", "/api/whoami")
            response.raise_for_status()
            user = response.json()
            if not isinstance(user, dict):
                raise APIError("Whoami response is not an object", response.status_code)
            self.user = user
            if isinstance(user.get("selectedTenants"), list):
                self._remember_selection(user["selectedTenants"])
            return user
        except requests.RequestException as exc:
            self.logger.error(
                "Could not retrieve the current KUMA user: %s", type(exc).__name__
            )
            raise ConnectionError("Could not retrieve the current KUMA user") from exc
        finally:
            if response is not None:
                response.close()

    def export_geo(self):
        """GET geoip/export: вернуть JSON-ответ подготовки экспорта GeoIP.

        Возвращает тело ответа сервера, а не скачанный файл. HTTP-ошибка
        возвращается строкой; некорректный успешный JSON вызывает APIError.
        """
        return self._result("GET", "geoip/export")[1]

    def get_active_list_scan(self, correlator_service_id: str, active_list_id: str):
        """Прочитать до 1000 записей активного списка через activeLists/scan.

        correlator_service_id — ID запущенного коррелятора; active_list_id —
        ID ресурса активного списка. Возвращает JSON сервера либо строку
        HTTP-ошибки. Пагинация не выполняется: результат может быть неполным
        для большого списка. Полную выгрузку делает get_active_list_content().
        """
        return self._result(
            "GET",
            f"services/id/{self._path(correlator_service_id)}/activeLists/scan/{self._path(active_list_id)}",
            params={"limit": 1000},
        )[1]

    def delete_activeList_record(
        self, correlator_service_id, active_list_id, device_key: str
    ):
        """Удалить запись с ключом device_key из активного списка сервиса.

        correlator_service_id — ID сервиса, active_list_id — ID ресурса списка.
        KUMA 2 получает key в query, KUMA 3/4 — в JSON DELETE-запроса.
        Возвращает None при HTTP 204, иначе текст ответа без APIError.
        """
        endpoint = f"services/id/{self._path(correlator_service_id)}/activeLists/del/{self._path(active_list_id)}"
        options = (
            {"params": {"key": device_key}}
            if self._major_version == 2
            else {"json": {"key": device_key}}
        )
        status, text = self._result("DELETE", endpoint, text=True, **options)
        return None if status == 204 else text

    def post_activeList_record(
        self, correlator_service_id, activeList_id, device_key: str, records: dict
    ):
        """Записать поля records для ключа device_key в активный список.

        correlator_service_id — ID сервиса коррелятора, activeList_id — ID
        ресурса списка. records — карта имён полей в значения; преобразуется
        в массив set: [{"name": имя, "value": значение}]. Ключ передаётся
        через query в KUMA 2 и через JSON в KUMA 3/4. Ответ закрывается.
        Возвращает None при HTTP 204, иначе строку 'reason text' без APIError.
        """
        endpoint = f"services/id/{self._path(correlator_service_id)}/activeLists/create/{self._path(activeList_id)}"
        body = {
            "set": [{"name": key, "value": value} for key, value in records.items()]
        }
        options = {"params": {"key": device_key}} if self._major_version == 2 else {}
        if self._major_version != 2:
            body["key"] = device_key
        response = self._send("POST", endpoint, json=body, **options)
        reason = response.reason
        status, text = self._response_result(response, text=True)
        return None if status == 204 else f"{reason} {text}"
