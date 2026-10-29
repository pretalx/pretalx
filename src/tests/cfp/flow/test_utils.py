# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from copy import deepcopy
from types import SimpleNamespace

import pytest
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString

from pretalx.cfp.flow.utils import cfp_session, i18n_string, serialize_value
from tests.cfp.flow._helpers import make_resolver
from tests.utils import SimpleSession, make_request

pytestmark = pytest.mark.unit

EMPTY_SESSION_ENTRY = {"data": {}, "initial": {}, "files": {}}
EXISTING_SESSION_ENTRY = {
    "data": {"info": {"title": "Test"}},
    "initial": {},
    "files": {},
}


@pytest.mark.parametrize(
    ("session_contents", "expected"),
    (
        ({}, EMPTY_SESSION_ENTRY),
        ({"cfp": None}, EMPTY_SESSION_ENTRY),
        ({"cfp": {"abc123": EXISTING_SESSION_ENTRY}}, EXISTING_SESSION_ENTRY),
    ),
    ids=["new", "empty_cfp_key", "existing"],
)
def test_cfp_session_returns_entry_for_tmpid(session_contents, expected):
    request = make_request(
        event=None,
        session=SimpleSession(deepcopy(session_contents)),
        resolver_match=make_resolver(),
    )

    result = cfp_session(request)

    assert result == expected
    assert request.session["cfp"]["abc123"] is result
    assert request.session.modified is True


@pytest.mark.parametrize(
    ("data", "locales", "expected"),
    (
        ("hello", ["en"], {"en": "hello"}),
        ({"en": "hello", "de": "hallo"}, ["en"], {"en": "hello", "de": "hallo"}),
        (42, ["en"], {"en": ""}),
        (None, ["en"], {"en": ""}),
        ("hello", ["en", "de"], {"en": "hello", "de": "hello"}),
        (
            {"en": "hello", "de": "existing"},
            ["en", "de"],
            {"en": "hello", "de": "existing"},
        ),
        (_("Title"), ["en", "de"], {"en": "Title", "de": "Titel"}),
    ),
    ids=[
        "string",
        "dict",
        "integer",
        "none",
        "fills_missing_locale",
        "keeps_existing_locale",
        "translates_lazy_string",
    ],
)
def test_i18n_string_normalises_to_lazy_i18n_string(data, locales, expected):
    original = deepcopy(data)

    result = i18n_string(data, locales)

    assert isinstance(result, LazyI18nString)
    assert result.data == expected
    assert data == original


def test_i18n_string_passes_through_existing_lazy_i18n_string():
    original = LazyI18nString({"en": "hello"})

    assert i18n_string(original, ["en"]) is original


class IterableSerializable:
    serialize = staticmethod(lambda: "serialized")

    def __iter__(self):
        return iter([SimpleNamespace(pk=1)])


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (SimpleNamespace(pk=42), 42),
        ([SimpleNamespace(pk=1), SimpleNamespace(pk=2)], [1, 2]),
        (SimpleNamespace(serialize=lambda: "serialized"), "serialized"),
        (42, "42"),
        (SimpleNamespace(pk=7, serialize=lambda: "serialized"), 7),
        (IterableSerializable(), [1]),
        ([[SimpleNamespace(pk=1)], [SimpleNamespace(pk=2)]], [[1], [2]]),
        ([], []),
    ),
    ids=[
        "pk",
        "iterable",
        "serialize_method",
        "plain_value",
        "pk_over_serialize",
        "iterable_over_serialize",
        "nested_iterables",
        "empty_iterable",
    ],
)
def test_serialize_value(value, expected):
    assert serialize_value(value) == expected
