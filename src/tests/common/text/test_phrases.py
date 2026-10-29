# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.text.phrases import BasePhrases, PhraseBook, Phrases, _phrase_book

pytestmark = pytest.mark.unit


def test_phrase_book_returns_registered_apps_only():
    book = PhraseBook()

    assert isinstance(book.base, BasePhrases)
    assert book.base is _phrase_book["base"]
    assert book.nonexistent_app is None


def test_phrases_attributes():
    base = BasePhrases()

    assert str(base.save) == "Save"
    assert base.permission_denied_long in BasePhrases.permission_denied_long


def test_custom_phrases_class_registered():

    class TestPhrases(Phrases, app="test_custom"):
        greeting = "Hello"

    assert "test_custom" in _phrase_book
    assert _phrase_book["test_custom"].greeting == "Hello"

    # Clean up
    del _phrase_book["test_custom"]
