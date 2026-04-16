from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class SettingsError(ValueError):
    pass


ALLOWED_STORAGE_BACKENDS = {"postgres", "sqlite"}


def _get_windows_roaming_path() -> Path:
    appdata = (os.environ.get("APPDATA") or "").strip()
    if appdata:
        return Path(appdata)

    userprofile = (os.environ.get("USERPROFILE") or "").strip()
    if userprofile:
        return Path(userprofile) / "AppData" / "Roaming"

    return Path.home() / "AppData" / "Roaming"


def get_global_config_dir() -> Path:
    if os.name == "nt":
        return _get_windows_roaming_path() / "olinkb"
    return Path.home() / ".config" / "olinkb"


def get_persisted_settings_path() -> Path:
    return get_global_config_dir() / "settings.json"


def load_persisted_environment() -> dict[str, str]:
    path = get_persisted_settings_path()
    if not path.exists():
        return {}

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(document, dict):
        return {}

    return {
        key: value
        for key, value in document.items()
        if isinstance(key, str) and isinstance(value, str) and value
    }


def _get_required_env(name: str, env: dict[str, str]) -> str:
    value = env.get(name)
    if value:
        return value
    raise SettingsError(f"Missing required environment variable: {name}")


def _get_storage_backend(env: dict[str, str]) -> str:
    raw_value = (env.get("OLINKB_STORAGE_BACKEND") or "postgres").strip().lower()
    if raw_value == "postgresql":
        raw_value = "postgres"
    if raw_value not in ALLOWED_STORAGE_BACKENDS:
        raise SettingsError(
            f"Unsupported storage backend: {raw_value!r}. "
            f"Valid values: {', '.join(sorted(ALLOWED_STORAGE_BACKENDS))}"
        )
    return raw_value


def _get_optional_path(name: str, env: dict[str, str]) -> Path | None:
    value = (env.get(name) or "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def _get_int(name: str, default: int, env: dict[str, str]) -> int:
    value = env.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SettingsError(f"Environment variable {name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    pg_url: str | None
    user: str
    team: str
    default_project: str | None
    cache_ttl_seconds: int
    cache_max_entries: int
    pg_pool_max_size: int = 5
    storage_backend: str = "postgres"
    sqlite_path: Path | None = None
    server_name: str = "OlinKB"

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        require_user: bool = True,
        require_team: bool = True,
    ) -> "Settings":
        values = {**load_persisted_environment(), **(env or dict(os.environ))}
        user = values.get("OLINKB_USER") or values.get("USER") or values.get("USERNAME")
        if require_user and not user:
            raise SettingsError(
                "Missing OLINKB_USER and no OS user fallback was found. "
                "Set OLINKB_USER in your environment or run 'olinkb --init' to configure."
            )
        team = values.get("OLINKB_TEAM") or ""
        if require_team and not team:
            raise SettingsError(
                "Missing required environment variable: OLINKB_TEAM. "
                "Set OLINKB_TEAM to your team identifier or run 'olinkb --init' to configure."
            )
        storage_backend = _get_storage_backend(values)

        pg_url: str | None = None
        sqlite_path: Path | None = None
        if storage_backend == "postgres":
            pg_url = _get_required_env("OLINKB_PG_URL", values)
        else:
            sqlite_path = _get_optional_path("OLINKB_SQLITE_PATH", values)
            if sqlite_path is None:
                raise SettingsError(
                    "Missing required environment variable: OLINKB_SQLITE_PATH. "
                    "Set it to the path where OlinKB should store its SQLite database, "
                    "e.g. OLINKB_SQLITE_PATH=~/.olinkb/olinkb.db"
                )

        return cls(
            pg_url=pg_url,
            user=user or "",
            team=team,
            default_project=values.get("OLINKB_PROJECT"),
            cache_ttl_seconds=_get_int("OLINKB_CACHE_TTL_SECONDS", 300, values),
            cache_max_entries=_get_int("OLINKB_CACHE_MAX_ENTRIES", 256, values),
            pg_pool_max_size=_get_int("OLINKB_PG_POOL_MAX_SIZE", 5, values),
            storage_backend=storage_backend,
            sqlite_path=sqlite_path,
            server_name=values.get("OLINKB_SERVER_NAME", "OlinKB"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


@lru_cache(maxsize=1)
def get_viewer_settings() -> Settings:
    return Settings.from_env(require_user=False, require_team=False)


def clear_settings_cache() -> None:
    get_settings.cache_clear()
    get_viewer_settings.cache_clear()
