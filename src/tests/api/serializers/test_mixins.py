# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.utils import translation
from i18nfield.strings import LazyI18nString

from pretalx.api.serializers.access_code import (
    SubmitterAccessCodeSerializer,
    V1SubmitterAccessCodeSerializer,
)
from pretalx.api.serializers.mixins import DocumentedI18nField
from pretalx.api.serializers.question import QuestionSerializer
from pretalx.api.serializers.submission import (
    ResourceWriteSerializer,
    SubmissionSerializer,
)
from pretalx.api.versions import V1
from tests.factories import EventFactory, SubmissionFactory, TalkSlotFactory
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


def test_documented_i18n_field_to_representation_with_override_locale():
    field = DocumentedI18nField()
    field.parent = QuestionSerializer(context={"override_locale": "en"})

    value = LazyI18nString({"en": "English text", "de": "Deutscher Text"})

    with translation.override("en"):
        result = field.to_representation(value)

    assert result == "English text"
    assert isinstance(result, str)


def test_documented_i18n_field_to_representation_without_override_locale():
    field = DocumentedI18nField()
    field.parent = QuestionSerializer()

    value = LazyI18nString({"en": "English text", "de": "Deutscher Text"})
    result = field.to_representation(value)

    assert isinstance(result, dict)
    assert result == {"en": "English text", "de": "Deutscher Text"}


@pytest.mark.django_db
def test_pretalx_serializer_init_sets_event_from_request(rf):
    event = EventFactory()
    request = rf.get("/")
    request.event = event
    request.query_params = request.GET
    serializer = QuestionSerializer(context={"request": request})

    assert serializer.event is event


@pytest.mark.django_db
def test_pretalx_serializer_get_extra_flex_field_not_expanded():
    request = make_api_request(event=EventFactory())
    serializer = SubmissionSerializer(context={"request": request})

    assert serializer.get_extra_flex_field("slots") is None


@pytest.mark.django_db
def test_pretalx_serializer_get_extra_flex_field_with_nested_omit():
    submission = SubmissionFactory()
    slot = TalkSlotFactory(submission=submission, is_visible=True)
    request = make_api_request(
        event=submission.event, data={"expand": "slots", "omit": "slots.room"}
    )
    serializer = SubmissionSerializer(context={"request": request})

    data = serializer.get_extra_flex_field("slots").to_representation([slot])

    assert len(data) == 1
    assert data[0]["id"] == slot.pk
    assert "room" not in data[0]


@pytest.mark.django_db
def test_pretalx_serializer_get_extra_flex_field_builds_once_per_serializer():
    request = make_api_request(event=EventFactory(), data={"expand": "slots,tags"})
    serializer = SubmissionSerializer(context={"request": request})
    other = SubmissionSerializer(context={"request": request})

    slots = serializer.get_extra_flex_field("slots")

    assert serializer.get_extra_flex_field("slots") is slots
    assert serializer.get_extra_flex_field("tags") is not slots
    assert other.get_extra_flex_field("slots") is not slots


@pytest.mark.parametrize(
    ("context", "path", "expected"),
    (
        (
            {},
            "pretalx.api.serializers.access_code.SubmitterAccessCodeSerializer",
            SubmitterAccessCodeSerializer,
        ),
        (
            {"api_version": V1},
            "pretalx.api.serializers.access_code.SubmitterAccessCodeSerializer",
            V1SubmitterAccessCodeSerializer,
        ),
        (
            {"api_version": V1},
            "pretalx.api.serializers.submission.ResourceWriteSerializer",
            ResourceWriteSerializer,
        ),
    ),
    ids=["without_version", "registered_for_version", "unregistered_name"],
)
def test_pretalx_serializer_lazy_serializer_class(context, path, expected):
    serializer = SubmissionSerializer(context=context)

    assert serializer._get_serializer_class_from_lazy_string(path) is expected
