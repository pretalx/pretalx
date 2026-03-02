# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.utils import translation
from i18nfield.strings import LazyI18nString

from pretalx.api.serializers.mixins import DocumentedI18nField
from pretalx.api.serializers.question import QuestionSerializer
from pretalx.api.serializers.submission import SubmissionSerializer
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
def test_pretalx_serializer_get_extra_flex_field_with_nested_omit():
    """When expanding with nested omit (e.g. ?expand=slots&omit=slots.submission),
    the nested omit config is forwarded to the child serializer."""
    submission = SubmissionFactory()
    slot = TalkSlotFactory(submission=submission, is_visible=True)
    request = make_api_request(
        event=submission.event, data={"expand": "slots", "omit": "slots.submission"}
    )
    serializer = SubmissionSerializer(
        submission, context={"request": request, "schedule": slot.schedule}
    )
    data = serializer.data

    assert len(data["slots"]) == 1
    assert data["slots"][0]["id"] == slot.pk
    assert "submission" not in data["slots"][0]
