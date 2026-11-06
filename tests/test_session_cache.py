import json
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from kuma.private.session_cache import PrivateSessionCache


def fake_client():
    return Mock(
        url="https://example.invalid:7220",
        username="user",
        version="3.4",
        get_session_data=Mock(return_value={"xsrf_token": "test-xsrf"}),
    )


def test_cache_is_encrypted_and_bound_to_identity(tmp_path):
    path = tmp_path / "session.bin"
    cache = PrivateSessionCache(path, Fernet.generate_key())
    client = fake_client()
    cache.save(client)
    assert b"test-xsrf" not in path.read_bytes()
    assert cache.load("https://example.invalid", "user", "3.4.1") == {
        "xsrf_token": "test-xsrf"
    }
    assert cache.load("https://other.invalid", "user", "3.4") is None
    assert cache.load(client.url, "other-user", "3.4") is None
    assert cache.load(client.url, "user", "4.2") is None


def test_expiry_uses_authenticated_time_and_invalid_ciphertext_is_a_miss(tmp_path):
    path = tmp_path / "session.bin"
    cache = PrivateSessionCache(path, Fernet.generate_key())
    client = fake_client()
    data = {
        "identity": cache._identity(client.url, client.username, client.version),
        "session": client.get_session_data(),
    }
    path.write_bytes(cache.cipher.encrypt_at_time(json.dumps(data).encode(), 1))
    assert cache.load(client.url, client.username, client.version) is None
    path.write_bytes(b"invalid")
    assert cache.load(client.url, client.username, client.version) is None


def test_cache_open_validates_session_and_closes_client_on_save_failure(
    tmp_path, monkeypatch
):
    import kuma

    cache = PrivateSessionCache(
        tmp_path / "missing" / "session.bin", Fernet.generate_key()
    )
    client = fake_client()
    create = Mock(return_value=client)
    monkeypatch.setattr(kuma, "PrivateClient", create)
    with pytest.raises(OSError):
        cache.open_client(client.url, "user", "test-password", version="3.4")
    assert create.call_args.kwargs["validate_session"] is True
    client.close.assert_called_once()
