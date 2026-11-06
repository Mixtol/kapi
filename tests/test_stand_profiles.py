from pathlib import Path

import pytest

from scripts.check_stand import Checks, StandConfig, archive_password, matching_version


def values():
    return {
        "TEST_KUMA_URL": "https://old.example.invalid:7223",
        "TEST_KUMA_TOKEN": "old-token",
        "TEST_KUMA_LOGIN": "old-user",
        "TEST_KUMA_PASS": "old-password",
        "TEST_KUMA_CA": "does-not-exist.pem",
        "TEST_KUMA42_URL": "https://new.example.invalid",
        "TEST_KUMA42_TOKEN": "new-token",
        "TEST_KUMA42_USER": "new-user",
        "TEST_KUMA42_PASS": "new-password",
    }


def test_42_profile_uses_only_its_credentials_and_ca():
    config = StandConfig.from_mapping(values(), "4.2.1.100")
    assert config.version == "4.2"
    assert config.url == "https://new.example.invalid"
    assert config.private_url == "https://new.example.invalid:7220"
    assert (config.token, config.username, config.password) == (
        "new-token",
        "new-user",
        "new-password",
    )
    assert config.verify is True
    assert "new-" not in repr(config)


@pytest.mark.parametrize("suffix", ["URL", "TOKEN", "USER", "PASS"])
def test_missing_42_credentials_never_fall_back_to_34(suffix):
    env = values()
    del env["TEST_KUMA42_" + suffix]
    with pytest.raises(ValueError, match="TEST_KUMA42"):
        StandConfig.from_mapping(env, "4.2")


def test_34_profile_keeps_login_and_resolves_ca_relative_to_env(tmp_path):
    env = values()
    env["TEST_KUMA_CA"] = "ca.pem"
    ca = tmp_path / "ca.pem"
    ca.write_text("test certificate placeholder")
    config = StandConfig.from_mapping(env, "3.4", base_dir=tmp_path)
    assert config.username == "old-user"
    assert config.private_url == "https://old.example.invalid:7220"
    assert Path(config.verify) == ca


def test_public_only_does_not_require_private_credentials():
    config = StandConfig.from_mapping(
        {"TEST_KUMA42_URL": "https://example.invalid", "TEST_KUMA42_TOKEN": "token"},
        "4.2",
        public_only=True,
    )
    assert config.username is None


def test_41_profile_keeps_its_own_credentials_despite_contract_fallback():
    env = values()
    with pytest.raises(ValueError, match="TEST_KUMA41"):
        StandConfig.from_mapping(env, "4.1", public_only=True)
    env.update(
        TEST_KUMA41_URL="https://kuma41.example.invalid", TEST_KUMA41_TOKEN="41-token"
    )
    config = StandConfig.from_mapping(env, "4.1.2.100", public_only=True)
    assert config.version == "4.1"
    assert config.url == env["TEST_KUMA41_URL"]
    assert config.token == "41-token"


def test_42_login_alias_and_custom_private_url():
    env = values()
    env["TEST_KUMA42_LOGIN"] = env.pop("TEST_KUMA42_USER")
    env["TEST_KUMA42_PRIVATE_URL"] = "https://private.example.invalid:443"
    config = StandConfig.from_mapping(env, "4.2")
    assert config.username == "new-user"
    assert config.private_url == env["TEST_KUMA42_PRIVATE_URL"]


def test_failures_do_not_print_server_or_credentials(capsys):
    def failing():
        raise ConnectionError("https://private-server/ secret-token secret-password")

    checks = Checks()
    checks.run("public.connection", failing)
    output = capsys.readouterr().out
    assert "ConnectionError" in output
    assert "private-server" not in output and "secret-" not in output
    assert checks.rows[0]["passed"] is False


def test_wrong_live_version_cannot_pass_as_42():
    class OldStand:
        def get_version(self):
            return "3.4"

    with pytest.raises(ValueError, match="does not match"):
        matching_version(OldStand(), "4.2")


def test_archive_password_satisfies_42_repetition_policy():
    password = archive_password()
    assert len(password) >= 16
    assert len(set(password)) == len(password)
    assert any(c.islower() for c in password)
    assert any(c.isupper() for c in password)
    assert any(c.isdigit() for c in password)
    assert "!" in password
