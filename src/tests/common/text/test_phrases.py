import pytest

from pretalx.common.text.phrases import BasePhrases, PhraseBook, Phrases, _phrase_book

pytestmark = pytest.mark.unit


def test_phrase_book_returns_registered_app():
    book = PhraseBook()

    result = book.base

    assert isinstance(result, BasePhrases)


def test_phrase_book_returns_none_for_unknown_app():
    book = PhraseBook()

    result = book.nonexistent_app

    assert result is None


def test_phrases_metaclass_registers_in_phrase_book():
    assert "base" in _phrase_book
    assert isinstance(_phrase_book["base"], BasePhrases)


def test_phrases_returns_scalar_attribute_directly():
    """Scalar (non-list/tuple) attributes are returned as-is."""
    base = BasePhrases()

    result = base.save

    assert str(result) == "Save"


@pytest.mark.parametrize("attr", ("not_found_long", "permission_denied_long"))
def test_phrases_returns_random_choice_from_collection(attr):
    """List and tuple attributes return a random element, not the collection."""
    base = BasePhrases()

    result = getattr(base, attr)

    assert not isinstance(result, (list, tuple))


def test_custom_phrases_class_registered():
    """Creating a new Phrases subclass registers it in the phrase book."""

    class TestPhrases(Phrases, app="test_custom"):
        greeting = "Hello"

    assert "test_custom" in _phrase_book
    assert _phrase_book["test_custom"].greeting == "Hello"

    # Clean up
    del _phrase_book["test_custom"]
