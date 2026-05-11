# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from types import SimpleNamespace

import pytest
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString

from pretalx.cfp.flow.utils import (
    cfp_field_labels,
    cfp_session,
    i18n_string,
    serialize_value,
)
from tests.cfp.flow._helpers import make_resolver
from tests.utils import SimpleSession, make_request

pytestmark = pytest.mark.unit


def test_cfp_session_creates_new_session_data():
    request = make_request(
        event=None, session=SimpleSession(), resolver_match=make_resolver()
    )

    result = cfp_session(request)

    assert result == {"data": {}, "initial": {}, "files": {}}
    assert request.session.modified is True


def test_cfp_session_returns_existing_session_data():
    existing = {"data": {"info": {"title": "Test"}}, "initial": {}, "files": {}}
    request = make_request(
        event=None,
        session=SimpleSession({"cfp": {"abc123": existing}}),
        resolver_match=make_resolver(),
    )

    result = cfp_session(request)

    assert result == existing


def test_cfp_session_handles_empty_cfp_key():
    request = make_request(
        event=None, session=SimpleSession({"cfp": None}), resolver_match=make_resolver()
    )

    result = cfp_session(request)

    assert result == {"data": {}, "initial": {}, "files": {}}


def test_cfp_field_labels_returns_expected_keys():
    result = cfp_field_labels()

    assert set(result.keys()) == {
        "title",
        "additional_speaker",
        "availabilities",
        "resources",
    }


@pytest.mark.parametrize(
    ("data", "expected_en"),
    (
        ("hello", "hello"),
        ({"en": "hello", "de": "hallo"}, "hello"),
        (42, ""),
        (None, ""),
    ),
    ids=["string", "dict", "integer", "none"],
)
def test_i18n_string_returns_lazy_i18n_string(data, expected_en):
    result = i18n_string(data, ["en"])

    assert isinstance(result, LazyI18nString)
    assert result.data["en"] == expected_en


def test_i18n_string_passes_through_existing_lazy_i18n_string():
    original = LazyI18nString({"en": "hello"})

    result = i18n_string(original, ["en"])

    assert result is original


def test_i18n_string_fills_missing_locales():
    result = i18n_string("hello", ["en", "de"])

    assert "en" in result.data
    assert "de" in result.data


def test_i18n_string_preserves_existing_locale_values():
    data = {"en": "hello", "de": "existing"}

    result = i18n_string(data, ["en", "de"])

    assert result.data["de"] == "existing"


def test_i18n_string_converts_lazy_string():
    lazy = _("Title")

    result = i18n_string(lazy, ["en"])

    assert isinstance(result, LazyI18nString)
    assert isinstance(result.data["en"], str)


def test_i18n_string_does_not_mutate_input():
    data = {"en": "hello"}
    original = data.copy()

    i18n_string(data, ["en", "de"])

    assert data == original


def test_serialize_value_returns_pk_for_model_like_object():
    obj = SimpleNamespace(pk=42)

    assert serialize_value(obj) == 42


def test_serialize_value_returns_list_for_iterable():
    items = [SimpleNamespace(pk=1), SimpleNamespace(pk=2)]

    assert serialize_value(items) == [1, 2]


def test_serialize_value_calls_serialize_method():
    obj = SimpleNamespace(serialize=lambda: "serialized")

    assert serialize_value(obj) == "serialized"


def test_serialize_value_returns_str_for_plain_value():
    assert serialize_value(42) == "42"


def test_serialize_value_prefers_pk_over_serialize():
    obj = SimpleNamespace(pk=7, serialize=lambda: "serialized")

    assert serialize_value(obj) == 7


def test_serialize_value_prefers_iterable_over_serialize():

    class IterableSerializable:
        def __iter__(self):
            return iter([SimpleNamespace(pk=1)])

        def serialize(self):
            return "serialized"

    obj = IterableSerializable()
    assert obj.serialize() == "serialized"

    assert serialize_value(obj) == [1]


def test_serialize_value_handles_nested_iterables():
    items = [[SimpleNamespace(pk=1)], [SimpleNamespace(pk=2)]]

    assert serialize_value(items) == [[1], [2]]


def test_serialize_value_handles_empty_iterable():
    assert serialize_value([]) == []
