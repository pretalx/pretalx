import pytest

from pretalx.common.cache import NamespacedCache, ObjectRelatedCache
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("locmem_cache")]


def test_namespaced_cache_set_and_get():
    cache = NamespacedCache("test-ns")

    cache.set("key1", "value1")

    assert cache.get("key1") == "value1"


def test_namespaced_cache_get_missing_key():
    cache = NamespacedCache("test-ns")

    assert cache.get("nonexistent") is None


def test_namespaced_cache_clear_on_fresh_cache():
    """Clearing a cache that has never been written to sets the prefix
    via the ValueError fallback in incr()."""
    cache = NamespacedCache("fresh-ns")

    cache.clear()
    cache.set("key1", "value1")

    assert cache.get("key1") == "value1"


def test_namespaced_cache_clear_invalidates_keys():
    cache = NamespacedCache("test-ns")
    cache.set("key1", "value1")

    cache.clear()

    assert cache.get("key1") is None


def test_namespaced_cache_clear_does_not_affect_other_namespaces():
    cache_a = NamespacedCache("ns-a")
    cache_b = NamespacedCache("ns-b")
    cache_a.set("shared_key", "from_a")
    cache_b.set("shared_key", "from_b")

    cache_a.clear()

    assert cache_a.get("shared_key") is None
    assert cache_b.get("shared_key") == "from_b"


def test_namespaced_cache_delete():
    cache = NamespacedCache("test-ns")
    cache.set("key1", "value1")

    cache.delete("key1")

    assert cache.get("key1") is None


def test_namespaced_cache_get_or_set_returns_existing():
    cache = NamespacedCache("test-ns")
    cache.set("key1", "existing")

    result = cache.get_or_set("key1", lambda: "new_value")

    assert result == "existing"


def test_namespaced_cache_get_or_set_stores_default():
    cache = NamespacedCache("test-ns")

    result = cache.get_or_set("key1", lambda: "default_value")

    assert result == "default_value"
    assert cache.get("key1") == "default_value"


def test_namespaced_cache_set_many_and_get_many():
    cache = NamespacedCache("test-ns")

    cache.set_many({"a": "1", "b": "2", "c": "3"})
    result = cache.get_many(["a", "b", "c"])

    assert result == {"a": "1", "b": "2", "c": "3"}


def test_namespaced_cache_get_many_missing_keys():
    cache = NamespacedCache("test-ns")
    cache.set("a", "1")

    result = cache.get_many(["a", "missing"])

    assert result == {"a": "1"}


def test_namespaced_cache_delete_many():
    cache = NamespacedCache("test-ns")
    cache.set_many({"a": "1", "b": "2", "c": "3"})

    cache.delete_many(["a", "c"])

    assert cache.get("a") is None
    assert cache.get("b") == "2"
    assert cache.get("c") is None


def test_namespaced_cache_incr():
    cache = NamespacedCache("test-ns")
    cache.set("counter", 10)

    result = cache.incr("counter")

    assert result == 11
    assert cache.get("counter") == 11


def test_namespaced_cache_incr_by_amount():
    cache = NamespacedCache("test-ns")
    cache.set("counter", 10)

    result = cache.incr("counter", 5)

    assert result == 15


def test_namespaced_cache_decr():
    cache = NamespacedCache("test-ns")
    cache.set("counter", 10)

    result = cache.decr("counter")

    assert result == 9
    assert cache.get("counter") == 9


def test_namespaced_cache_decr_by_amount():
    cache = NamespacedCache("test-ns")
    cache.set("counter", 10)

    result = cache.decr("counter", 3)

    assert result == 7


def test_namespaced_cache_close_is_noop():
    """close() exists for interface compatibility but does nothing."""
    cache = NamespacedCache("test-ns")
    cache.close()


def test_namespaced_cache_prefix_key_hashes_long_keys():
    """Keys longer than 200 characters are hashed to stay under memcached limits."""
    cache = NamespacedCache("test-ns")
    long_key = "k" * 300

    cache.set(long_key, "value")

    assert cache.get(long_key) == "value"
    internal_key = cache._prefix_key(long_key)
    assert len(internal_key) == 64  # SHA-256 hex digest length


def test_namespaced_cache_prefix_key_short_keys_not_hashed():
    cache = NamespacedCache("test-ns")

    internal_key = cache._prefix_key("short")

    assert "short" in internal_key
    assert len(internal_key) < 200


def test_namespaced_cache_strip_prefix_roundtrips():
    cache = NamespacedCache("test-ns")
    prefixed = cache._prefix_key("mykey")

    stripped = cache._strip_prefix(prefixed)

    assert stripped == "mykey"


def test_namespaced_cache_strip_prefix_with_colons_in_prefixkey():
    cache = NamespacedCache("Event:42")
    prefixed = cache._prefix_key("mykey")

    stripped = cache._strip_prefix(prefixed)

    assert stripped == "mykey"


@pytest.mark.django_db
def test_object_related_cache_set_and_get():
    event = EventFactory()
    cache = ObjectRelatedCache(event)

    cache.set("key1", "value1")

    assert cache.get("key1") == "value1"


@pytest.mark.django_db
def test_object_related_cache_clear_isolates_objects():
    event1 = EventFactory()
    event2 = EventFactory()
    cache1 = ObjectRelatedCache(event1)
    cache2 = ObjectRelatedCache(event2)
    cache1.set("data", "event1-data")
    cache2.set("data", "event2-data")

    cache1.clear()

    assert cache1.get("data") is None
    assert cache2.get("data") == "event2-data"


@pytest.mark.django_db
def test_object_related_cache_uses_model_name_and_pk():
    event = EventFactory()
    cache = ObjectRelatedCache(event)

    assert cache.prefixkey == f"Event:{event.pk}"


@pytest.mark.django_db
def test_object_related_cache_custom_field():
    event = EventFactory()
    cache = ObjectRelatedCache(event, field="slug")

    assert cache.prefixkey == f"Event:{event.slug}"


def test_object_related_cache_rejects_non_model():
    with pytest.raises(TypeError, match="not a Model"):
        ObjectRelatedCache("not-a-model")
