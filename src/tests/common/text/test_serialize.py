# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from i18nfield.strings import LazyI18nString

from pretalx.common.text.serialize import (
    I18nStrJSONEncoder,
    humanize_duration,
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


@pytest.mark.parametrize(
    ("minutes", "expected"),
    (
        (0, "0\xa0minutes"),
        (30, "30\xa0minutes"),
        (100, "1\xa0hour, 40\xa0minutes"),
        (60 * 36, "1\xa0day, 12\xa0hours"),
    ),
)
def test_humanize_duration(minutes, expected):
    assert humanize_duration(minutes) == expected


def test_i18n_str_json_encoder_with_lazy_i18n_string():
    encoder = I18nStrJSONEncoder()
    i18n_str = LazyI18nString({"en": "hello", "de": "hallo"})

    result = encoder.default(i18n_str)

    assert result == "hello"


@pytest.mark.django_db
def test_i18n_str_json_encoder_falls_back_to_parent(event):
    encoder = I18nStrJSONEncoder()

    result = encoder.default(event)

    assert result == {"id": event.pk, "type": "Event"}


def test_json_roundtrip_serializes_i18n_strings():
    data = {
        "key": "value",
        "number": 42,
        "nested": {"a": [1, 2, 3]},
        "title": LazyI18nString({"en": "Talk", "de": "Vortrag"}),
    }

    result = json_roundtrip(data)

    assert result == {**data, "title": {"en": "Talk", "de": "Vortrag"}}


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (LazyI18nString({"en": "hello"}), {"en": "hello"}),
        ("plain string", "plain string"),
        (42, 42),
        (None, None),
    ),
)
def test_serialize_i18n(value, expected):
    assert serialize_i18n(value) == expected
