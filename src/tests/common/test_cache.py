# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from unittest.mock import ANY, patch

import pytest

from pretalx.common.cache import NamespacedCache, ObjectRelatedCache
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit]


def test_namespaced_cache_set_get_delete():
    cache = NamespacedCache("test-ns")

    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    assert cache.get("nonexistent") is None

    cache.delete("key1")
    assert cache.get("key1") is None


def test_namespaced_cache_clear_invalidates_only_its_namespace():
    cache_a = NamespacedCache("ns-a")
    cache_b = NamespacedCache("ns-b")
    cache_a.clear()
    cache_a.set("shared_key", "from_a")
    cache_b.set("shared_key", "from_b")
    assert cache_a.get("shared_key") == "from_a"

    cache_a.clear()

    assert cache_a.get("shared_key") is None
    assert cache_b.get("shared_key") == "from_b"


def test_namespaced_cache_get_or_set_stores_then_returns_existing():
    cache = NamespacedCache("test-ns")

    assert cache.get_or_set("key1", lambda: "default_value") == "default_value"
    assert cache.get("key1") == "default_value"
    assert cache.get_or_set("key1", lambda: "new_value") == "default_value"


def test_namespaced_cache_many_operations():
    cache = NamespacedCache("test-ns")

    cache.set_many({"a": "1", "b": "2", "c": "3"})
    assert cache.get_many(["a", "b", "c", "missing"]) == {"a": "1", "b": "2", "c": "3"}

    cache.delete_many(["a", "c"])
    assert cache.get_many(["a", "b", "c"]) == {"b": "2"}


def test_namespaced_cache_incr_and_decr():
    cache = NamespacedCache("test-ns")
    cache.set("counter", 10)

    assert cache.incr("counter") == 11
    assert cache.incr("counter", 5) == 16
    assert cache.decr("counter") == 15
    assert cache.decr("counter", 3) == 12
    assert cache.get("counter") == 12


def test_namespaced_cache_close_is_noop():
    cache = NamespacedCache("test-ns")
    cache.close()


def test_namespaced_cache_prefix_key_hashes_long_keys():
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


def test_namespaced_cache_prefix_keys_looks_up_the_prefix_once():
    cache = NamespacedCache("test-ns")
    cache.set("a", "1")

    with patch.object(cache.cache, "get", wraps=cache.cache.get) as mocked_get:
        keys = cache._prefix_keys(["a", "b", "c"])

    assert mocked_get.call_count == 1
    assert keys == [cache._prefix_key(key) for key in ("a", "b", "c")]


@pytest.mark.parametrize("namespace", ("test-ns", "Event:42"), ids=("plain", "colons"))
def test_namespaced_cache_strip_prefix_roundtrips(namespace):
    cache = NamespacedCache(namespace)
    prefixed = cache._prefix_key("mykey")

    assert cache._strip_prefix(prefixed) == "mykey"


@pytest.mark.django_db
def test_object_related_cache_set_and_get_under_model_and_pk_prefix():
    event = EventFactory()
    cache = ObjectRelatedCache(event)

    cache.set("key1", "value1")

    assert cache.get("key1") == "value1"
    assert cache.prefixkey == f"Event:{event.pk}"


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
def test_object_related_cache_custom_field():
    event = EventFactory()
    cache = ObjectRelatedCache(event, field="slug")

    assert cache.prefixkey == f"Event:{event.slug}"


def test_object_related_cache_rejects_non_model():
    with pytest.raises(TypeError, match="not a Model"):
        ObjectRelatedCache("not-a-model")


@pytest.mark.parametrize(
    "call",
    (lambda cache: cache._prefix_key("key1"), lambda cache: cache.clear()),
    ids=("_prefix_key", "clear"),
)
def test_namespaced_cache_stores_prefix_with_capped_timeout(call):
    cache = NamespacedCache("fresh-ns")

    with patch.object(cache.cache, "set", wraps=cache.cache.set) as mocked_set:
        call(cache)

    mocked_set.assert_called_once_with(cache.prefixkey, ANY, 86400 * 30)


@pytest.mark.parametrize(
    ("method", "call", "expected"),
    (
        ("set", lambda cache: cache.set("key1", "value1", timeout=None), 86400 * 30),
        (
            "set_many",
            lambda cache: cache.set_many({"key1": "value1"}, timeout=None),
            86400 * 30,
        ),
        (
            "get_or_set",
            lambda cache: cache.get_or_set("key1", lambda: "value1", timeout=None),
            86400 * 30,
        ),
        (
            "set",
            lambda cache: cache.set("key1", "value1", timeout=86400 * 800),
            86400 * 30,
        ),
        ("set", lambda cache: cache.set("key1", "value1"), 300),
    ),
    ids=("set", "set_many", "get_or_set", "set-above-cap", "set-default"),
)
def test_namespaced_cache_timeout_capping(method, call, expected):
    cache = NamespacedCache("test-ns")
    cache._prefix_key("warm-up-the-prefix")

    with patch.object(cache.cache, method, wraps=getattr(cache.cache, method)) as mock:
        call(cache)

    assert expected in (mock.call_args.args + tuple(mock.call_args.kwargs.values()))
