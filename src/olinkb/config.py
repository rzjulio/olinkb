from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


class SettingsError(ValueError):
    pass


def _get_required_env(name: str, env: dict[str, str]) -> str:
    value = env.get(name)
    if value:
        return value
    raise SettingsError(f"Missing required environment variable: {name}")


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
    pg_url: str
    user: str
    team: str
    default_project: str | None
    cache_ttl_seconds: int
    cache_max_entries: int
    pg_pool_max_size: int = 5
    server_name: str = "OlinKB"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        values = env or dict(os.environ)
        user = values.get("OLINKB_USER") or values.get("USER") or values.get("USERNAME")
        if not user:
            raise SettingsError("Missing OLINKB_USER and no OS user fallback was found")

        return cls(
            pg_url=_get_required_env("OLINKB_PG_URL", values),
            user=user,
            team=_get_required_env("OLINKB_TEAM", values),
            default_project=values.get("OLINKB_PROJECT"),
            cache_ttl_seconds=_get_int("OLINKB_CACHE_TTL_SECONDS", 300, values),
            cache_max_entries=_get_int("OLINKB_CACHE_MAX_ENTRIES", 256, values),
            pg_pool_max_size=_get_int("OLINKB_PG_POOL_MAX_SIZE", 5, values),
            server_name=values.get("OLINKB_SERVER_NAME", "OlinKB"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
