import pytest
from django.conf import settings
from django.utils.translation import get_language

from pretalx.common.language import (
    LANGUAGE_CODES_MAPPING,
    LANGUAGE_NAMES,
    get_current_language_information,
    get_language_information,
    language,
)

pytestmark = pytest.mark.unit


def test_language_codes_mapping_contains_all_configured_languages():
    assert set(LANGUAGE_CODES_MAPPING.values()) == set(
        settings.LANGUAGES_INFORMATION.keys()
    )


def test_language_codes_mapping_lowercases_keys():
    for key in LANGUAGE_CODES_MAPPING:
        assert key == key.lower()


def test_language_names_contains_configured_languages():
    for lang_info in settings.LANGUAGES_INFORMATION.values():
        assert lang_info["code"] in LANGUAGE_NAMES
        assert LANGUAGE_NAMES[lang_info["code"]] == lang_info["natural_name"]


@pytest.mark.parametrize(
    ("input_code", "expected_code"),
    (("en", "en"), ("EN", "EN")),
    ids=("lowercase", "uppercase"),
)
def test_get_language_information_preserves_input_case(input_code, expected_code):
    info = get_language_information(input_code)

    assert info["code"] == expected_code
    assert info["natural_name"] == "English"


def test_get_language_information_unknown_language():
    with pytest.raises(KeyError):
        get_language_information("xx-nonexistent")


def test_get_language_information_does_not_mutate_settings():
    info1 = get_language_information("en")
    info1["custom_key"] = "test"

    info2 = get_language_information("en")

    assert "custom_key" not in info2


def test_get_current_language_information():
    with language("en"):
        info = get_current_language_information()

    assert info["code"] == "en"
    assert info["natural_name"] == "English"


def test_language_context_manager_activates_language():
    with language("de"):
        assert get_language() == "de"


def test_language_context_manager_restores_previous():
    with language("de"):
        with language("en"):
            assert get_language() == "en"
        assert get_language() == "de"


def test_language_context_manager_none_uses_default():
    with language(None):
        assert get_language() == settings.LANGUAGE_CODE


def test_language_context_manager_restores_on_exception():
    original = get_language()
    try:
        with language("de"):
            raise ValueError("test")
    except ValueError:
        pass

    assert get_language() == original
