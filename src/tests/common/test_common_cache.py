# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import random

import pytest
from django.core.cache import cache as django_cache
from django.test import TestCase, override_settings
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.cache import ObjectRelatedCache
from pretalx.event.models import Event, Organiser


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "tralala",
        }
    }
)
class CacheTest(TestCase):
    """This test case tests the invalidation of the event related cache."""

    @classmethod
    def setUpTestData(cls):
        with scopes_disabled():
            o = Organiser.objects.create(name="Dummy", slug="dummy")
            cls.event = Event.objects.create(
                organiser=o,
                name="Dummy",
                slug="dummy",
                date_from=now().date(),
                date_to=now().date(),
            )

    def setUp(self):
        self.cache = self.event.cache
        randint = random.random()
        self.testkey = "test" + str(randint)

    def test_interference(self):
        django_cache.clear()
        self.cache.set(self.testkey, "foo")
        assert django_cache.get(self.testkey) is None
        assert self.cache.get(self.testkey) in (None, "foo")

    def test_longkey(self):
        self.cache.set(self.testkey * 100, "foo")
        assert self.cache.get(self.testkey * 100) == "foo"

    def test_get_or_set(self):
        assert self.cache.get_or_set(self.testkey, "foo") == "foo"
        assert self.cache.get_or_set(self.testkey, "foo") == "foo"

    def test_invalidation(self):
        self.cache.set(self.testkey, "foo")
        self.cache.clear()
        assert self.cache.get(self.testkey) is None

    def test_many(self):
        inp = {
            "a": "foo",
            "b": "bar",
        }
        self.cache.set_many(inp)
        assert inp == self.cache.get_many(inp.keys())


def test_incorrect_cache_creation():
    with pytest.raises(Exception):  # noqa: B017, PT011
        ObjectRelatedCache(1)
