from olinkb.storage.cache import ReadCache


def test_read_cache_returns_value_before_expiration() -> None:
    cache = ReadCache(max_size=2, ttl_seconds=60)

    cache.set("boot:rzjulio", {"loaded": 3})

    assert cache.get("boot:rzjulio") == {"loaded": 3}


def test_read_cache_invalidates_prefix() -> None:
    cache = ReadCache(max_size=3, ttl_seconds=60)

    cache.set("boot:rzjulio:project-a", {"loaded": 1})
    cache.set("boot:rzjulio:project-b", {"loaded": 2})
    cache.set("remember:query", {"loaded": 3})

    cache.invalidate_prefix("boot:rzjulio:")

    assert cache.get("boot:rzjulio:project-a") is None
    assert cache.get("boot:rzjulio:project-b") is None
    assert cache.get("remember:query") == {"loaded": 3}