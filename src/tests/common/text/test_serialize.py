import pytest
from i18nfield.strings import LazyI18nString

from pretalx.common.text.serialize import (
    I18nStrJSONEncoder,
    json_roundtrip,
    serialize_duration,
    serialize_i18n,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("minutes", "expected"),
    (
        (0, "00:00"),
        (1, "00:01"),
        (10, "00:10"),
        (30, "00:30"),
        (60, "01:00"),
        (90, "01:30"),
        (120, "02:00"),
        (150, "02:30"),
        (720, "12:00"),
        (1440, "1:00:00"),
        (1530, "1:01:30"),
    ),
)
def test_serialize_duration(minutes, expected):
    assert serialize_duration(minutes=minutes) == expected


def test_i18n_str_json_encoder_with_lazy_i18n_string():
    encoder = I18nStrJSONEncoder()
    i18n_str = LazyI18nString({"en": "hello", "de": "hallo"})

    result = encoder.default(i18n_str)

    assert result == "hello"


@pytest.mark.django_db
def test_i18n_str_json_encoder_falls_back_to_parent(event):
    """Non-LazyI18nString objects are handled by the parent I18nJSONEncoder."""
    encoder = I18nStrJSONEncoder()

    result = encoder.default(event)

    assert result == {"id": event.pk, "type": "Event"}


def test_json_roundtrip_preserves_data():
    data = {"key": "value", "number": 42, "nested": {"a": [1, 2, 3]}}

    result = json_roundtrip(data)

    assert result == data


def test_json_roundtrip_with_i18n_string():
    """LazyI18nString objects survive the round-trip via I18nJSONEncoder."""
    data = {"title": LazyI18nString({"en": "Talk", "de": "Vortrag"})}

    result = json_roundtrip(data)

    assert result == {"title": {"en": "Talk", "de": "Vortrag"}}


def test_serialize_i18n_with_data_attribute():
    """Objects with a .data attribute (like LazyI18nString) return .data."""
    i18n_str = LazyI18nString({"en": "hello"})

    result = serialize_i18n(i18n_str)

    assert result == {"en": "hello"}


@pytest.mark.parametrize("value", ("plain string", 42, None))
def test_serialize_i18n_without_data_attribute(value):
    """Plain values without .data are returned as-is."""
    assert serialize_i18n(value) == value
