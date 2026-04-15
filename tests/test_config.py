from __future__ import annotations

import json

from olinkb import config


def test_settings_from_env_uses_persisted_file_as_fallback(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "OLINKB_PG_URL": "postgresql://user:pass@db.example.com:5432/olinkb",
                "OLINKB_TEAM": "example-team",
                "OLINKB_PROJECT": "olinkb",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "get_persisted_settings_path", lambda: settings_path)

    settings = config.Settings.from_env(env={"USER": "rzjulio"})

    assert settings.pg_url == "postgresql://user:pass@db.example.com:5432/olinkb"
    assert settings.team == "example-team"
    assert settings.default_project == "olinkb"
    assert settings.user == "rzjulio"


def test_settings_from_env_prefers_real_environment_over_persisted_file(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "OLINKB_PG_URL": "postgresql://persisted",
                "OLINKB_TEAM": "persisted-team",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "get_persisted_settings_path", lambda: settings_path)

    settings = config.Settings.from_env(
        env={
            "OLINKB_PG_URL": "postgresql://env",
            "OLINKB_TEAM": "env-team",
            "USER": "rzjulio",
        }
    )

    assert settings.pg_url == "postgresql://env"
    assert settings.team == "env-team"