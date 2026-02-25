import pytest
from django.utils import translation
from django_scopes import scopes_disabled
from i18nfield.fields import I18nCharField, I18nTextField
from i18nfield.strings import LazyI18nString

from pretalx.api.serializers.mixins import DocumentedI18nField, PretalxSerializer
from pretalx.api.serializers.question import QuestionSerializer
from pretalx.api.serializers.submission import SubmissionSerializer
from pretalx.submission.models import QuestionTarget
from tests.factories import (
    EventFactory,
    QuestionFactory,
    SubmissionFactory,
    TalkSlotFactory,
)
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


def test_documented_i18n_field_to_representation_with_override_locale():
    """With override_locale set, the field returns a plain string instead of a dict."""
    field = DocumentedI18nField()
    field.parent = QuestionSerializer(context={"override_locale": "en"})

    value = LazyI18nString({"en": "English text", "de": "Deutscher Text"})

    with translation.override("en"):
        result = field.to_representation(value)

    assert result == "English text"
    assert isinstance(result, str)


def test_documented_i18n_field_to_representation_without_override_locale():
    """Without override_locale, the field returns a dict of translations."""
    field = DocumentedI18nField()
    field.parent = QuestionSerializer()

    value = LazyI18nString({"en": "English text", "de": "Deutscher Text"})
    result = field.to_representation(value)

    assert isinstance(result, dict)
    assert result == {"en": "English text", "de": "Deutscher Text"}


def test_pretalx_serializer_init_sets_override_locale():
    serializer = QuestionSerializer(context={"override_locale": "de"})

    assert serializer.override_locale == "de"


@pytest.mark.django_db
def test_pretalx_serializer_init_sets_event_from_request(rf):
    event = EventFactory()
    request = rf.get("/")
    request.event = event
    request.query_params = request.GET
    serializer = QuestionSerializer(context={"request": request})

    assert serializer.event is event


def test_pretalx_serializer_init_defaults_without_context():
    serializer = QuestionSerializer()

    assert serializer.override_locale is None
    assert serializer.event is None


def test_pretalx_serializer_get_with_fallback_from_data():
    serializer = QuestionSerializer()
    serializer.instance = None

    result = serializer.get_with_fallback({"target": "submission"}, "target")

    assert result == "submission"


@pytest.mark.django_db
def test_pretalx_serializer_get_with_fallback_from_instance():
    with scopes_disabled():
        question = QuestionFactory(target=QuestionTarget.SPEAKER)

    serializer = QuestionSerializer()
    serializer.instance = question

    result = serializer.get_with_fallback({}, "target")

    assert result == QuestionTarget.SPEAKER


def test_pretalx_serializer_get_with_fallback_returns_none_without_instance():
    serializer = QuestionSerializer()
    serializer.instance = None

    result = serializer.get_with_fallback({}, "target")

    assert result is None


@pytest.mark.django_db
def test_pretalx_serializer_get_extra_flex_field_with_nested_omit():
    """When expanding with nested omit (e.g. ?expand=slots&omit=slots.submission),
    the nested omit config is forwarded to the child serializer."""
    with scopes_disabled():
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


def test_pretalx_serializer_field_mapping_i18n():
    """PretalxSerializer maps I18nCharField and I18nTextField to DocumentedI18nField."""
    assert (
        PretalxSerializer.serializer_field_mapping[I18nCharField] is DocumentedI18nField
    )
    assert (
        PretalxSerializer.serializer_field_mapping[I18nTextField] is DocumentedI18nField
    )
