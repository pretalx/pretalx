import json
from types import SimpleNamespace

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import CharField, FileField, ValidationError
from django.http import HttpResponseNotAllowed, QueryDict
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretalx.cfp.flow import (
    BaseCfPStep,
    CfPFlow,
    InfoStep,
    ProfileStep,
    QuestionsStep,
    TemplateFlowStep,
    UserStep,
    cfp_field_labels,
    cfp_session,
    i18n_string,
    serialize_value,
)
from pretalx.cfp.signals import cfp_steps
from pretalx.common.exceptions import SendMailException
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import (
    QuestionTarget,
    Resource,
    Submission,
    SubmissionStates,
)
from pretalx.submission.models.submission import SubmissionInvitation
from pretalx.submission.signals import submission_state_change
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import SimpleSession, make_request

pytestmark = pytest.mark.unit


def _cfp_session(tmpid="abc123", data=None, initial=None, files=None, **extra):
    """Build a session dict with a ready-to-use cfp sub-dict."""
    entry = {"data": data or {}, "initial": initial or {}, "files": files or {}}
    entry.update(extra)
    return SimpleSession({"cfp": {tmpid: entry}})


def _resolver(tmpid="abc123", **kwargs):
    """Build a minimal resolver_match for CfP step unit tests."""
    return SimpleNamespace(kwargs={"tmpid": tmpid, **kwargs})


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
    """Iterable check happens before serialize check."""

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


def test_cfp_session_creates_new_session_data():
    request = make_request(
        event=None, session=SimpleSession(), resolver_match=_resolver()
    )

    result = cfp_session(request)

    assert result == {"data": {}, "initial": {}, "files": {}}
    assert request.session.modified is True


def test_cfp_session_returns_existing_session_data():
    existing = {"data": {"info": {"title": "Test"}}, "initial": {}, "files": {}}
    request = make_request(
        event=None,
        session=SimpleSession({"cfp": {"abc123": existing}}),
        resolver_match=_resolver(),
    )

    result = cfp_session(request)

    assert result == existing


def test_cfp_session_handles_empty_cfp_key():
    request = make_request(
        event=None, session=SimpleSession({"cfp": None}), resolver_match=_resolver()
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


@pytest.mark.parametrize("method", ("get", "post"))
def test_base_cfp_step_get_and_post_return_not_allowed(method):
    step = BaseCfPStep(event=None)

    assert isinstance(getattr(step, method)(request=None), HttpResponseNotAllowed)


def test_base_cfp_step_identifier_raises():
    with pytest.raises(NotImplementedError):
        BaseCfPStep(event=None).identifier  # noqa: B018


def test_base_cfp_step_label_raises():
    with pytest.raises(NotImplementedError):
        BaseCfPStep(event=None).label  # noqa: B018


def test_base_cfp_step_is_completed_raises():
    with pytest.raises(NotImplementedError):
        BaseCfPStep(event=None).is_completed(request=None)


def test_base_cfp_step_get_next_applicable_returns_next():
    step_a = BaseCfPStep(event=None)
    step_b = BaseCfPStep(event=None)
    step_a._next = step_b

    assert step_a.get_next_applicable(request=None) is step_b


def test_base_cfp_step_get_next_applicable_skips_non_applicable():
    step_a = BaseCfPStep(event=None)
    step_b = BaseCfPStep(event=None)
    step_c = BaseCfPStep(event=None)
    step_b.is_applicable = lambda req: False
    step_b._next = step_c
    step_a._next = step_b

    assert step_a.get_next_applicable(request=None) is step_c


@pytest.mark.parametrize(
    "method", ("get_next_applicable", "get_prev_applicable"), ids=("next", "prev")
)
def test_base_cfp_step_get_next_prev_applicable_returns_none_without_neighbor(method):
    assert getattr(BaseCfPStep(event=None), method)(request=None) is None


def test_base_cfp_step_get_prev_applicable_returns_previous():
    step_a = BaseCfPStep(event=None)
    step_b = BaseCfPStep(event=None)
    step_b._previous = step_a

    assert step_b.get_prev_applicable(request=None) is step_a


def test_base_cfp_step_get_prev_applicable_skips_non_applicable():
    step_a = BaseCfPStep(event=None)
    step_b = BaseCfPStep(event=None)
    step_c = BaseCfPStep(event=None)
    step_b.is_applicable = lambda req: False
    step_b._previous = step_a
    step_c._previous = step_b

    assert step_c.get_prev_applicable(request=None) is step_a


@pytest.mark.django_db
def test_base_cfp_step_get_step_url_builds_correct_url():
    """get_step_url builds /event-slug/submit/tmpid/step/ URLs."""
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["info"]
    request = make_request(
        event, resolver_match=_resolver(event=event.slug, step="old")
    )

    url = step.get_step_url(request)

    assert f"/{event.slug}/submit/abc123/info/" in url


@pytest.mark.django_db
def test_base_cfp_step_get_step_url_merges_query_params():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["info"]
    request = make_request(
        event,
        path="/?access_code=XYZ",
        resolver_match=_resolver(event=event.slug, step="old"),
    )

    url = step.get_step_url(request, query={"draft": "1"})

    assert "access_code=XYZ" in url
    assert "draft=1" in url


@pytest.mark.django_db
def test_base_cfp_step_get_step_url_removes_false_query_params():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["info"]
    request = make_request(
        event,
        path="/?draft=1&access_code=XYZ",
        resolver_match=_resolver(event=event.slug, step="old"),
    )

    url = step.get_step_url(request, query={"draft": False})

    assert "draft" not in url
    assert "access_code=XYZ" in url


@pytest.mark.django_db
def test_base_cfp_step_get_next_url_returns_url_when_next_exists():
    with scopes_disabled():
        event = EventFactory()
        QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    flow = CfPFlow(event)
    info_step = flow.steps_dict["info"]
    request = make_request(
        event,
        resolver_match=_resolver(event=event.slug, step="info"),
        session=_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )

    with scopes_disabled():
        url = info_step.get_next_url(request)

    assert f"/{event.slug}/submit/abc123/questions/" in url


@pytest.mark.parametrize(
    "method", ("get_next_url", "get_prev_url"), ids=("next", "prev")
)
def test_base_cfp_step_get_next_prev_url_returns_none_without_neighbor(method):
    assert (
        getattr(BaseCfPStep(event=None), method)(request=make_request(event=None))
        is None
    )


@pytest.mark.django_db
def test_base_cfp_step_get_prev_url_returns_url_when_prev_exists():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    questions_step = flow.steps_dict["questions"]
    request = make_request(
        event, resolver_match=_resolver(event=event.slug, step="questions")
    )

    url = questions_step.get_prev_url(request)

    assert f"/{event.slug}/submit/abc123/info/" in url
    assert "draft" not in url


def test_template_flow_step_identifier_raises():
    with pytest.raises(NotImplementedError):
        TemplateFlowStep(event=None).identifier  # noqa: B018


@pytest.mark.django_db
def test_info_step_get_form_initial_populates_submission_type_from_url():
    with scopes_disabled():
        event = EventFactory()
        sub_type = event.cfp.default_type
    step = InfoStep(event=event)
    request = make_request(
        event,
        path=f"/?submission_type={sub_type.pk}",
        resolver_match=_resolver(),
        session=_cfp_session(),
    )
    step.request = request

    with scopes_disabled():
        result = step.get_form_initial()

    assert result["submission_type"] == sub_type


@pytest.mark.django_db
def test_info_step_get_form_initial_populates_track_from_url():
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
    step = InfoStep(event=event)
    request = make_request(
        event,
        path=f"/?track={track.pk}",
        resolver_match=_resolver(),
        session=_cfp_session(),
    )
    step.request = request

    with scopes_disabled():
        result = step.get_form_initial()

    assert result["track"] == track


@pytest.mark.django_db
def test_info_step_get_form_initial_handles_slug_style_id():
    """Submission type ID can be in format 'pk-slug'."""
    with scopes_disabled():
        event = EventFactory()
        sub_type = event.cfp.default_type
    step = InfoStep(event=event)
    request = make_request(
        event,
        path=f"/?submission_type={sub_type.pk}-talk",
        resolver_match=_resolver(),
        session=_cfp_session(),
    )
    step.request = request

    with scopes_disabled():
        result = step.get_form_initial()

    assert result["submission_type"] == sub_type


@pytest.mark.parametrize(
    "query_value", ("invalid", "99999"), ids=("non_numeric", "nonexistent_pk")
)
@pytest.mark.django_db
def test_info_step_get_form_initial_ignores_bad_submission_type(query_value):
    with scopes_disabled():
        event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        path=f"/?submission_type={query_value}",
        resolver_match=_resolver(),
        session=_cfp_session(),
    )
    step.request = request

    with scopes_disabled():
        result = step.get_form_initial()

    assert "submission_type" not in result


@pytest.mark.django_db
def test_info_step_get_form_data_joins_additional_speaker_list():
    with scopes_disabled():
        event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "additional_speaker": ["a@example.com", "b@example.com"],
                    "title": "Test",
                }
            }
        ),
    )
    step.request = request

    result = step.get_form_data()

    assert result["additional_speaker"] == "a@example.com,b@example.com"


@pytest.mark.django_db
def test_info_step_get_form_data_preserves_string_additional_speaker():
    with scopes_disabled():
        event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(data={"info": {"additional_speaker": "a@example.com"}}),
    )
    step.request = request

    result = step.get_form_data()

    assert result["additional_speaker"] == "a@example.com"


@pytest.mark.django_db
def test_info_step_get_form_kwargs_includes_access_code():
    with scopes_disabled():
        event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(),
        access_code="test_code",
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["access_code"] == "test_code"


@pytest.mark.django_db
def test_info_step_get_form_kwargs_access_code_none_when_absent():
    with scopes_disabled():
        event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(event, resolver_match=_resolver(), session=_cfp_session())
    # make_request doesn't set access_code, so getattr returns None
    step.request = request

    result = step.get_form_kwargs()

    assert result["access_code"] is None


@pytest.mark.parametrize(
    ("visibility", "expected_enabled", "expected_required"),
    ((None, False, False), ("optional", True, False), ("required", True, True)),
    ids=("disabled", "optional", "required"),
)
@pytest.mark.django_db
def test_info_step_resources_visibility(
    visibility, expected_enabled, expected_required
):
    with scopes_disabled():
        event = EventFactory()
        if visibility:
            event.cfp.fields["resources"]["visibility"] = visibility
            event.cfp.save()
    step = InfoStep(event=event)

    assert step._resources_enabled is expected_enabled
    assert step._resources_required is expected_required


def test_info_step_formset_has_resources_true_when_non_deleted():
    step = InfoStep(event=None)
    form = SimpleNamespace(cleaned_data={"description": "Slides", "DELETE": False})
    formset = SimpleNamespace(forms=[form])

    assert step._formset_has_resources(formset) is True


def test_info_step_formset_has_resources_false_when_all_deleted():
    step = InfoStep(event=None)
    form = SimpleNamespace(cleaned_data={"description": "Slides", "DELETE": True})
    formset = SimpleNamespace(forms=[form])

    assert step._formset_has_resources(formset) is False


def test_info_step_formset_has_resources_false_when_no_cleaned_data():
    step = InfoStep(event=None)
    form = SimpleNamespace(cleaned_data={})
    formset = SimpleNamespace(forms=[form])

    assert step._formset_has_resources(formset) is False


@pytest.mark.django_db
def test_info_step_get_resource_formset_returns_none_when_disabled():
    with scopes_disabled():
        event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(event, resolver_match=_resolver(), session=_cfp_session())
    step.request = request

    assert step.get_resource_formset() is None


@pytest.mark.django_db
def test_info_step_get_resource_formset_returns_formset_when_enabled():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["resources"]["visibility"] = "optional"
        event.cfp.save()
    step = InfoStep(event=event)
    request = make_request(event, resolver_match=_resolver(), session=_cfp_session())
    step.request = request

    formset = step.get_resource_formset()
    assert formset.prefix == "resource"


@pytest.mark.django_db
def test_questions_step_is_applicable_with_submission_questions():
    with scopes_disabled():
        event = EventFactory()
        QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_applicable(request) is True


@pytest.mark.django_db
def test_questions_step_is_applicable_with_speaker_questions():
    with scopes_disabled():
        event = EventFactory()
        QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_applicable(request) is True


@pytest.mark.django_db
def test_questions_step_not_applicable_without_questions():
    with scopes_disabled():
        event = EventFactory()
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_applicable(request) is False


@pytest.mark.django_db
def test_questions_step_not_applicable_when_question_filtered_by_type():
    """A submission question restricted to a different type is excluded."""
    with scopes_disabled():
        event = EventFactory()
        other_type = SubmissionTypeFactory(event=event)
        question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        question.submission_types.add(other_type)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_applicable(request) is False


@pytest.mark.django_db
def test_questions_step_applicable_when_question_matches_type():
    with scopes_disabled():
        event = EventFactory()
        default_type = event.cfp.default_type
        question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        question.submission_types.add(default_type)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(data={"info": {"submission_type": default_type.pk}}),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_applicable(request) is True


@pytest.mark.django_db
def test_questions_step_applicable_with_track_filtering():
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        question.tracks.add(track)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "submission_type": event.cfp.default_type.pk,
                    "track": track.pk,
                }
            }
        ),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_applicable(request) is True


@pytest.mark.django_db
def test_questions_step_not_applicable_with_wrong_track():
    with scopes_disabled():
        event = EventFactory()
        track_a = TrackFactory(event=event)
        track_b = TrackFactory(event=event)
        question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
        question.tracks.add(track_a)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "submission_type": event.cfp.default_type.pk,
                    "track": track_b.pk,
                }
            }
        ),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_applicable(request) is False


@pytest.mark.django_db
def test_questions_step_get_form_kwargs_includes_track_and_type():
    with scopes_disabled():
        event = EventFactory()
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(data={"info": {"track": 5, "submission_type": 3}}),
    )
    step.request = request

    with scopes_disabled():
        result = step.get_form_kwargs()

    assert result["track"] == 5
    assert result["submission_type"] == 3
    assert result["target"] == ""


@pytest.mark.django_db
def test_questions_step_get_form_kwargs_uses_access_code_type():
    with scopes_disabled():
        event = EventFactory()
        access_type = SubmissionTypeFactory(event=event)
        access_code = SubmitterAccessCodeFactory(event=event)
        access_code.submission_types.add(access_type)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={"info": {"track": None, "submission_type": event.cfp.default_type.pk}}
        ),
        access_code=access_code,
    )
    step.request = request

    with scopes_disabled():
        result = step.get_form_kwargs()

    assert result["submission_type"] == access_type


@pytest.mark.django_db
def test_questions_step_get_form_kwargs_includes_speaker_for_authenticated():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        speaker, _ = SpeakerProfile.objects.get_or_create(user=user, event=event)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={"info": {"track": None, "submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    with scopes_disabled():
        result = step.get_form_kwargs()

    assert result["speaker"] == speaker


@pytest.mark.parametrize(
    ("is_authenticated", "expected"),
    ((False, True), (True, False)),
    ids=("anonymous", "authenticated"),
)
def test_user_step_is_applicable(is_authenticated, expected):
    request = make_request(
        event=None, user=SimpleNamespace(is_authenticated=is_authenticated)
    )

    assert UserStep(event=None).is_applicable(request) is expected


@pytest.mark.django_db
def test_user_step_get_form_kwargs_includes_request():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["user"]
    request = make_request(
        event,
        resolver_match=_resolver(event=event.slug, step="user"),
        session=_cfp_session(),
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["request"] is request
    assert result["no_buttons"] is True
    assert f"/{event.slug}/submit/abc123/profile/" in result["success_url"]


@pytest.mark.django_db
def test_profile_step_set_data_stores_avatar_action():
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, method="post", resolver_match=_resolver(), session=_cfp_session()
    )
    request.POST = QueryDict("avatar_action=remove")
    step.request = request

    step.set_data({"name": "Alice"})

    assert step.cfp_session["data"]["profile"]["avatar_action"] == "remove"


@pytest.mark.django_db
def test_profile_step_set_data_ignores_keep_avatar_action():
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, method="post", resolver_match=_resolver(), session=_cfp_session()
    )
    request.POST = QueryDict("avatar_action=keep")
    step.request = request

    step.set_data({"name": "Alice"})

    assert "avatar_action" not in step.cfp_session["data"]["profile"]


@pytest.mark.django_db
def test_profile_step_set_data_ignores_avatar_action_on_get():
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(event, resolver_match=_resolver(), session=_cfp_session())
    step.request = request

    step.set_data({"name": "Alice"})

    assert "avatar_action" not in step.cfp_session["data"]["profile"]


@pytest.mark.django_db
def test_profile_step_get_form_kwargs_uses_authenticated_user():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, user=user, resolver_match=_resolver(), session=_cfp_session()
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["user"] == user
    assert result["name"] == user.name
    assert result["read_only"] is False
    assert result["essential_only"] is True


@pytest.mark.django_db
def test_profile_step_get_form_kwargs_uses_session_user_data():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={"user": {"user_id": user.pk, "register_name": "From Session"}}
        ),
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["user"] == user
    assert result["name"] == user.name


@pytest.mark.django_db
def test_profile_step_get_form_kwargs_uses_register_name_without_user():
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(data={"user": {"register_name": "New Person"}}),
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result.get("user") is None
    assert result["name"] == "New Person"


@pytest.mark.django_db
def test_dedraft_mixin_returns_draft_for_authenticated_speaker():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        speaker, _ = SpeakerProfile.objects.get_or_create(user=user, event=event)
        submission.speakers.add(speaker)
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=_resolver(),
        session=_cfp_session(code=submission.code),
    )
    step.request = request

    with scopes_disabled():
        assert step.dedraft_submission == submission


@pytest.mark.django_db
def test_dedraft_mixin_returns_none_for_anonymous():
    with scopes_disabled():
        event = EventFactory()
        submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    step = InfoStep(event=event)
    request = make_request(
        event, resolver_match=_resolver(), session=_cfp_session(code=submission.code)
    )
    step.request = request

    assert step.dedraft_submission is None


@pytest.mark.django_db
def test_dedraft_mixin_returns_none_without_code():
    with scopes_disabled():
        event = EventFactory()
        UserFactory()
    step = InfoStep(event=event)
    request = make_request(
        event, user=UserFactory(), resolver_match=_resolver(), session=_cfp_session()
    )
    step.request = request

    assert step.dedraft_submission is None


@pytest.mark.django_db
def test_dedraft_mixin_returns_none_for_non_draft():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker, _ = SpeakerProfile.objects.get_or_create(user=user, event=event)
        submission.speakers.add(speaker)
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=_resolver(),
        session=_cfp_session(code=submission.code),
    )
    step.request = request

    with scopes_disabled():
        assert step.dedraft_submission is None


@pytest.mark.django_db
def test_dedraft_mixin_returns_none_for_wrong_speaker():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        other_user = UserFactory()
        submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        other_speaker, _ = SpeakerProfile.objects.get_or_create(
            user=other_user, event=event
        )
        submission.speakers.add(other_speaker)
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=_resolver(),
        session=_cfp_session(code=submission.code),
    )
    step.request = request

    with scopes_disabled():
        assert step.dedraft_submission is None


@pytest.mark.django_db
def test_cfp_flow_has_default_steps():
    with scopes_disabled():
        event = EventFactory()

    flow = CfPFlow(event)

    assert [s.identifier for s in flow.steps] == [
        "info",
        "questions",
        "user",
        "profile",
    ]


@pytest.mark.django_db
def test_cfp_flow_steps_sorted_by_priority():
    with scopes_disabled():
        event = EventFactory()

    flow = CfPFlow(event)

    priorities = [s.priority for s in flow.steps]
    assert priorities == sorted(priorities)


@pytest.mark.django_db
def test_cfp_flow_steps_linked_list():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    steps = flow.steps

    assert steps[0]._previous is None
    assert steps[0]._next is steps[1]
    assert steps[1]._previous is steps[0]
    assert steps[1]._next is steps[2]
    assert not hasattr(steps[-1], "_next")


@pytest.mark.django_db
def test_cfp_flow_steps_dict_is_ordered():
    with scopes_disabled():
        event = EventFactory()

    flow = CfPFlow(event)

    assert list(flow.steps_dict.keys()) == ["info", "questions", "user", "profile"]


@pytest.mark.django_db
def test_cfp_flow_default_config_is_empty():
    with scopes_disabled():
        event = EventFactory()

    assert CfPFlow(event).config == {"steps": {}}


@pytest.mark.django_db
def test_cfp_flow_steps_property_returns_list():
    with scopes_disabled():
        event = EventFactory()

    flow = CfPFlow(event)

    assert isinstance(flow.steps, list)
    assert len(flow.steps) == 4


@pytest.mark.django_db
def test_cfp_flow_get_config_parses_json_string():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    result = flow.get_config(json.dumps({"steps": {"info": {"icon": "star"}}}))

    assert result["steps"]["info"]["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_get_config_handles_dict():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    result = flow.get_config({"steps": {"info": {"icon": "star"}}})

    assert result["steps"]["info"]["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_get_config_returns_empty_for_non_dict():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    assert flow.get_config(42) == {}
    assert flow.get_config(None) == {}
    assert flow.get_config("") == {}
    assert flow.get_config([]) == {}


@pytest.mark.django_db
def test_cfp_flow_get_config_processes_i18n_fields():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    result = flow.get_config({"steps": {"info": {"title": "Hello", "text": "World"}}})

    assert isinstance(result["steps"]["info"]["title"], LazyI18nString)
    assert result["steps"]["info"]["title"].data["en"] == "Hello"
    assert isinstance(result["steps"]["info"]["text"], LazyI18nString)
    assert result["steps"]["info"]["text"].data["en"] == "World"


@pytest.mark.django_db
def test_cfp_flow_get_config_processes_field_configs():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    data = {
        "steps": {
            "info": {
                "fields": [
                    {
                        "key": "title",
                        "label": "Custom Title",
                        "help_text": "Enter title",
                    }
                ]
            }
        }
    }

    result = flow.get_config(data)

    field = result["steps"]["info"]["fields"][0]
    assert field["key"] == "title"
    assert field["label"].data["en"] == "Custom Title"
    assert field["help_text"].data["en"] == "Enter title"


@pytest.mark.django_db
def test_cfp_flow_get_config_preserves_non_i18n_field_keys():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    data = {
        "steps": {
            "info": {"fields": [{"key": "title", "required": True, "request": True}]}
        }
    }

    result = flow.get_config(data)

    field = result["steps"]["info"]["fields"][0]
    assert field["required"] is True
    assert field["request"] is True


@pytest.mark.django_db
def test_cfp_flow_get_config_ignores_unknown_field_keys():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    data = {"steps": {"info": {"fields": [{"key": "title", "widget": "fancy"}]}}}

    result = flow.get_config(data)

    assert "widget" not in result["steps"]["info"]["fields"][0]


@pytest.mark.django_db
def test_cfp_flow_get_config_json_compat_mode():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    result = flow.get_config({"steps": {"info": {"title": "Hello"}}}, json_compat=True)

    assert isinstance(result["steps"]["info"]["title"], dict)


@pytest.mark.django_db
def test_cfp_flow_save_config_stores_in_settings():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.save_config({"steps": {"info": {"icon": "star"}}})
        event.cfp.refresh_from_db()

    assert event.cfp.settings["flow"]["steps"]["info"]["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_save_config_normalises_list_input():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.save_config([{"title": "test"}])
        event.cfp.refresh_from_db()

    assert "steps" in event.cfp.settings["flow"]


@pytest.mark.django_db
def test_cfp_flow_save_config_normalises_bare_dict():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.save_config({"info": {"icon": "star"}})
        event.cfp.refresh_from_db()

    assert "steps" in event.cfp.settings["flow"]


@pytest.mark.django_db
def test_cfp_flow_reset_clears_config():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    with scopes_disabled():
        flow.save_config({"steps": {"info": {"icon": "star"}}})

        flow.reset()

        event.cfp.refresh_from_db()
    assert event.cfp.settings["flow"] == {}


@pytest.mark.django_db
def test_cfp_flow_get_config_json_returns_valid_json():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    with scopes_disabled():
        flow.save_config({"steps": {"info": {"title": "Hello"}}})
    flow = CfPFlow(event)

    result = flow.get_config_json()

    assert "steps" in json.loads(result)


@pytest.mark.django_db
def test_cfp_flow_get_config_json_empty_config():
    with scopes_disabled():
        event = EventFactory()

    assert json.loads(CfPFlow(event).get_config_json()) == {"steps": {}}


@pytest.mark.django_db
def test_cfp_flow_get_step_config_returns_config():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    with scopes_disabled():
        flow.save_config({"steps": {"info": {"icon": "star"}}})
    flow = CfPFlow(event)

    assert flow.get_step_config("info")["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_get_step_config_returns_empty_for_missing():
    with scopes_disabled():
        event = EventFactory()

    assert CfPFlow(event).get_step_config("nonexistent") == {}


@pytest.mark.django_db
def test_cfp_flow_get_field_config_returns_field():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    with scopes_disabled():
        flow.save_config(
            {
                "steps": {
                    "info": {
                        "fields": [
                            {"key": "title", "label": "Custom Title"},
                            {"key": "abstract"},
                        ]
                    }
                }
            }
        )
    flow = CfPFlow(event)

    result = flow.get_field_config("info", "title")

    assert result["key"] == "title"
    assert result["label"].data["en"] == "Custom Title"


@pytest.mark.django_db
def test_cfp_flow_get_field_config_returns_empty_for_missing_field():
    with scopes_disabled():
        event = EventFactory()

    assert CfPFlow(event).get_field_config("info", "nonexistent") == {}


@pytest.mark.django_db
def test_cfp_flow_get_field_config_returns_empty_for_missing_step():
    with scopes_disabled():
        event = EventFactory()

    assert CfPFlow(event).get_field_config("nonexistent", "title") == {}


@pytest.mark.django_db
def test_cfp_flow_update_step_header():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_step_header("info", title="New Title", text="New Text")

    flow = CfPFlow(event)
    step_config = flow.get_step_config("info")
    assert step_config["title"].data["en"] == "New Title"
    assert step_config["text"].data["en"] == "New Text"


@pytest.mark.django_db
def test_cfp_flow_update_step_header_creates_step_if_missing():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_step_header("new_step", title="Title", text="Text")

    assert CfPFlow(event).get_step_config("new_step") != {}


@pytest.mark.django_db
def test_cfp_flow_update_field_config_creates_new_field():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_field_config("info", "title", label="Custom Title")

    flow = CfPFlow(event)
    field = flow.get_field_config("info", "title")
    assert field["key"] == "title"
    assert field["label"].data["en"] == "Custom Title"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_updates_existing_field():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    with scopes_disabled():
        flow.update_field_config("info", "title", label="Original", help_text="Help")
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_field_config("info", "title", label="Updated")

    flow = CfPFlow(event)
    field = flow.get_field_config("info", "title")
    assert field["label"].data["en"] == "Updated"
    # help_text is preserved from original save
    assert field["help_text"].data["en"] == "Help"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_creates_step_if_missing():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_field_config("new_step", "new_field", label="Label")

    field = CfPFlow(event).get_field_config("new_step", "new_field")
    assert field["key"] == "new_field"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_with_help_text_only():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_field_config("info", "title", help_text="Some help")

    field = CfPFlow(event).get_field_config("info", "title")
    assert field["help_text"].data["en"] == "Some help"
    assert "label" not in field


@pytest.mark.django_db
def test_cfp_flow_update_field_order_reorders_fields():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    with scopes_disabled():
        flow.save_config(
            {
                "steps": {
                    "info": {
                        "fields": [
                            {"key": "title", "label": "Title"},
                            {"key": "abstract", "label": "Abstract"},
                            {"key": "description"},
                        ]
                    }
                }
            }
        )
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_field_order("info", ["description", "title", "abstract"])

    fields = CfPFlow(event).get_step_config("info")["fields"]
    assert [f["key"] for f in fields] == ["description", "title", "abstract"]


@pytest.mark.django_db
def test_cfp_flow_update_field_order_preserves_metadata():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    with scopes_disabled():
        flow.save_config(
            {"steps": {"info": {"fields": [{"key": "title", "label": "Custom Title"}]}}}
        )
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_field_order("info", ["title"])

    field = CfPFlow(event).get_field_config("info", "title")
    assert field["label"].data["en"] == "Custom Title"


@pytest.mark.django_db
def test_cfp_flow_update_field_order_creates_new_field_stubs():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_field_order("info", ["title", "new_field"])

    assert CfPFlow(event).get_field_config("info", "new_field") == {"key": "new_field"}


@pytest.mark.django_db
def test_cfp_flow_update_field_order_creates_step_if_missing():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_field_order("new_step", ["field_a", "field_b"])

    fields = CfPFlow(event).get_step_config("new_step")["fields"]
    assert [f["key"] for f in fields] == ["field_a", "field_b"]


@pytest.mark.django_db
def test_cfp_flow_ensure_step_config_creates_structure():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    config = {}

    flow._ensure_step_config(config, "info")

    assert config == {"steps": {"info": {"fields": []}}}


@pytest.mark.django_db
def test_cfp_flow_ensure_step_config_preserves_existing():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    config = {"steps": {"info": {"fields": [{"key": "title"}], "icon": "star"}}}

    flow._ensure_step_config(config, "info")

    assert config["steps"]["info"]["icon"] == "star"
    assert len(config["steps"]["info"]["fields"]) == 1


@pytest.mark.django_db
def test_cfp_flow_ensure_step_config_adds_missing_fields_key():
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    config = {"steps": {"info": {"icon": "star"}}}

    flow._ensure_step_config(config, "info")

    assert config["steps"]["info"]["fields"] == []
    assert config["steps"]["info"]["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_handles_exception_from_signal(register_signal_handler):
    with scopes_disabled():
        event = EventFactory()

    def bad_handler(signal, sender, **kwargs):
        raise RuntimeError("Plugin broke")

    register_signal_handler(cfp_steps, bad_handler)

    flow = CfPFlow(event)

    assert len(flow.steps) == 4


@pytest.mark.django_db
def test_cfp_flow_integrates_plugin_steps(register_signal_handler):
    with scopes_disabled():
        event = EventFactory()

    class PluginStep(BaseCfPStep):
        identifier = "plugin_step"
        label = "Plugin"
        priority = 50

        def is_completed(self, request):
            return True

    def handler(signal, sender, **kwargs):
        return [PluginStep]

    register_signal_handler(cfp_steps, handler)

    flow = CfPFlow(event)

    assert len(flow.steps) == 5
    identifiers = [s.identifier for s in flow.steps]
    assert "plugin_step" in identifiers
    plugin_idx = identifiers.index("plugin_step")
    assert identifiers[plugin_idx - 1] == "user"
    assert identifiers[plugin_idx + 1] == "profile"
    assert flow.steps_dict["plugin_step"].is_completed(request=None) is True


@pytest.mark.django_db
def test_form_flow_step_set_data_serializes_to_session():
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(event, resolver_match=_resolver(), session=_cfp_session())
    step.request = request

    step.set_data({"name": "Alice", "biography": "A speaker"})

    assert step.cfp_session["data"]["profile"]["name"] == "Alice"
    assert step.cfp_session["data"]["profile"]["biography"] == "A speaker"


@pytest.mark.django_db
def test_form_flow_step_set_data_skips_file_fields():
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(event, resolver_match=_resolver(), session=_cfp_session())
    step.request = request
    file_obj = SimpleNamespace(file=True)

    step.set_data({"name": "Alice", "avatar": file_obj})

    assert "avatar" not in step.cfp_session["data"]["profile"]
    assert step.cfp_session["data"]["profile"]["name"] == "Alice"


@pytest.mark.django_db
def test_form_flow_step_get_form_data_returns_session_data():
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(data={"profile": {"name": "Alice"}}),
    )
    step.request = request

    assert step.get_form_data() == {"name": "Alice"}


@pytest.mark.django_db
def test_form_flow_step_get_form_data_returns_empty_when_no_data():
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(event, resolver_match=_resolver(), session=_cfp_session())
    step.request = request

    assert step.get_form_data() == {}


@pytest.mark.django_db
def test_form_flow_step_get_form_initial_returns_session_initial():
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(initial={"profile": {"name": "Default"}}),
    )
    step.request = request

    assert step.get_form_initial() == {"name": "Default"}


@pytest.mark.django_db
def test_form_flow_step_get_form_data_deep_copies():
    """Modifying returned data does not affect session."""
    with scopes_disabled():
        event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(data={"profile": {"name": "Alice"}}),
    )
    step.request = request

    result = step.get_form_data()
    result["name"] = "Bob"

    assert step.cfp_session["data"]["profile"]["name"] == "Alice"


def test_form_flow_step_annotate_stored_filenames_noop_without_files():
    step = ProfileStep(event=None)
    file_field = FileField()
    file_field.help_text = "Original help"
    form = SimpleNamespace(fields={"avatar": file_field})

    step._annotate_stored_filenames(form, None)

    assert file_field.help_text == "Original help"


def test_form_flow_step_annotate_stored_filenames_adds_help_text():
    step = ProfileStep(event=None)
    file_field = FileField()
    file_field.help_text = ""
    form = SimpleNamespace(fields={"avatar": file_field})

    stored_file = SimpleNamespace(name="photo.jpg")

    step._annotate_stored_filenames(form, {"avatar": stored_file})

    assert "photo.jpg" in file_field.help_text
    assert "stored-file-indicator" in file_field.help_text


def test_form_flow_step_annotate_stored_filenames_preserves_help_text():
    step = ProfileStep(event=None)
    file_field = FileField()
    file_field.help_text = "Max 5MB"
    form = SimpleNamespace(fields={"avatar": file_field})

    stored_file = SimpleNamespace(name="photo.jpg")

    step._annotate_stored_filenames(form, {"avatar": stored_file})

    assert "Max 5MB" in file_field.help_text
    assert "photo.jpg" in file_field.help_text


def test_form_flow_step_annotate_stored_filenames_skips_non_file_fields():

    step = ProfileStep(event=None)
    char_field = CharField()
    char_field.help_text = ""
    form = SimpleNamespace(fields={"name": char_field})

    stored_file = SimpleNamespace(name="file.txt")

    step._annotate_stored_filenames(form, {"name": stored_file})

    assert "file.txt" not in char_field.help_text


@pytest.mark.django_db
def test_form_flow_step_config_reads_from_event():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.settings["flow"] = json.dumps(
            {"steps": {"info": {"icon": "rocket", "fields": []}}}
        )
        event.cfp.save()

    step = InfoStep(event=event)

    assert step.config.get("icon") == "rocket"


@pytest.mark.django_db
def test_form_flow_step_config_returns_empty_without_config():
    with scopes_disabled():
        event = EventFactory()

    assert InfoStep(event=event).config == {}


@pytest.mark.django_db
def test_form_flow_step_title_uses_config():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.settings["flow"] = json.dumps(
            {"steps": {"info": {"title": "Custom Title", "fields": []}}}
        )
        event.cfp.save()

    assert InfoStep(event=event).title.data["en"] == "Custom Title"


@pytest.mark.django_db
def test_form_flow_step_title_falls_back_to_default():
    with scopes_disabled():
        event = EventFactory()

    title = InfoStep(event=event).title
    assert isinstance(title, LazyI18nString)
    assert title.data["en"]  # has a non-empty default


@pytest.mark.django_db
def test_form_flow_step_text_uses_config():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.settings["flow"] = json.dumps(
            {"steps": {"info": {"text": "Custom Text", "fields": []}}}
        )
        event.cfp.save()

    assert InfoStep(event=event).text.data["en"] == "Custom Text"


@pytest.mark.django_db
def test_form_flow_step_get_form_kwargs_includes_event():
    with scopes_disabled():
        event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(event, resolver_match=_resolver(), session=_cfp_session())
    step.request = request

    assert step.get_form_kwargs()["event"] == event


@pytest.mark.django_db
def test_form_flow_step_get_form_kwargs_includes_field_configuration():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.settings["flow"] = json.dumps(
            {"steps": {"info": {"fields": [{"key": "title"}]}}}
        )
        event.cfp.save()
    step = InfoStep(event=event)
    request = make_request(event, resolver_match=_resolver(), session=_cfp_session())
    step.request = request

    config = step.get_form_kwargs()["field_configuration"]
    assert len(config) == 1
    assert config[0]["key"] == "title"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_updates_help_text_on_existing():
    """Updating only help_text on an existing field preserves the label."""
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    with scopes_disabled():
        flow.update_field_config("info", "title", label="Custom")
    flow = CfPFlow(event)

    with scopes_disabled():
        flow.update_field_config("info", "title", help_text="Updated help")

    field = CfPFlow(event).get_field_config("info", "title")
    assert field["help_text"].data["en"] == "Updated help"
    assert field["label"].data["en"] == "Custom"


@pytest.mark.django_db
def test_base_cfp_step_get_step_url_no_query_string_when_all_removed():
    """When all GET params are removed via False, no query string is appended."""
    with scopes_disabled():
        event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["info"]
    request = make_request(
        event, path="/?draft=1", resolver_match=_resolver(event=event.slug, step="old")
    )

    url = step.get_step_url(request, query={"draft": False})

    assert "?" not in url


@pytest.mark.django_db
def test_user_step_done_raises_for_inactive_user():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        user.is_active = False
        user.save()
    step = UserStep(event=event)
    request = make_request(
        event, user=user, resolver_match=_resolver(), session=_cfp_session()
    )
    step.request = request

    with pytest.raises(ValidationError):
        step.done(request)


@pytest.mark.django_db
def test_form_flow_step_get_form_post_merges_stored_files():
    """On POST, stored session files fill in for missing request.FILES entries."""
    with scopes_disabled():
        event = EventFactory()
    session = _cfp_session()

    # Phase 1: store a file via set_files on a GET request
    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=_resolver(), session=session)
    step.set_files(
        {"image": SimpleUploadedFile("image.png", b"\x89PNG", content_type="image/png")}
    )

    # Phase 2: fresh step (clears cached_property), POST request reusing same session
    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=_resolver(), session=session
    )
    request.POST = QueryDict(
        "title=Test&submission_type=" + str(event.cfp.default_type.pk)
    )
    step.request = request

    with scopes_disabled():
        form = step.get_form()

    assert form.files["image"].name == "image.png"


@pytest.mark.django_db
def test_info_step_get_resource_formset_post_merges_stored_files():
    """On POST, stored resource session files fill in for missing request.FILES."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["resources"]["visibility"] = "optional"
        event.cfp.save()
    session = _cfp_session()

    # Phase 1: store a resource file via set_files on a GET request
    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=_resolver(), session=session)
    step.set_files(
        {
            "resource-0-resource": SimpleUploadedFile(
                "slides.pdf", b"%PDF", content_type="application/pdf"
            )
        }
    )

    # Phase 2: fresh step (clears cached_property), POST request reusing same session
    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=_resolver(), session=session
    )
    request.POST = QueryDict(
        "resource-TOTAL_FORMS=1&resource-INITIAL_FORMS=0"
        "&resource-MIN_NUM_FORMS=0&resource-MAX_NUM_FORMS=1000"
        "&resource-0-link=https://example.com"
    )
    step.request = request

    with scopes_disabled():
        formset = step.get_resource_formset()

    assert formset.files["resource-0-resource"].name == "slides.pdf"


@pytest.mark.django_db
def test_info_step_is_completed_false_when_resources_required_and_formset_invalid():
    """is_completed returns False when resources are required but the formset is invalid."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["resources"]["visibility"] = "required"
        event.cfp.save()
    step = InfoStep(event=event)
    # Valid info data so the main form passes, but no resource formset data
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "title": "Test",
                    "abstract": "An abstract",
                    "submission_type": event.cfp.default_type.pk,
                    "content_locale": "en",
                }
            }
        ),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_completed(request) is False


@pytest.mark.django_db
def test_info_step_is_completed_false_when_resources_required_but_all_deleted():
    """is_completed returns False when resources are required but all forms are deleted."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["resources"]["visibility"] = "required"
        event.cfp.save()
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "title": "Test",
                    "abstract": "An abstract",
                    "submission_type": event.cfp.default_type.pk,
                    "content_locale": "en",
                },
                "info__resources": {
                    "resource-TOTAL_FORMS": "1",
                    "resource-INITIAL_FORMS": "0",
                    "resource-MIN_NUM_FORMS": "0",
                    "resource-MAX_NUM_FORMS": "1000",
                    "resource-0-link": "https://example.com",
                    "resource-0-DELETE": "on",
                },
            }
        ),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_completed(request) is False


@pytest.mark.django_db
def test_info_step_is_completed_true_when_resources_required_and_present():
    """is_completed returns True when resources are required and valid resources exist."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["resources"]["visibility"] = "required"
        event.cfp.save()
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "title": "Test",
                    "abstract": "An abstract",
                    "submission_type": event.cfp.default_type.pk,
                    "content_locale": "en",
                },
                "info__resources": {
                    "resource-TOTAL_FORMS": "1",
                    "resource-INITIAL_FORMS": "0",
                    "resource-MIN_NUM_FORMS": "0",
                    "resource-MAX_NUM_FORMS": "1000",
                    "resource-0-description": "Slides",
                    "resource-0-link": "https://example.com/slides",
                },
            }
        ),
    )
    step.request = request

    with scopes_disabled():
        assert step.is_completed(request) is True


@pytest.mark.django_db
def test_info_step_done_processes_resource_delete():
    """done() deletes existing resources marked for deletion in the formset."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["resources"]["visibility"] = "optional"
        event.cfp.save()
        user = UserFactory()
        submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        speaker, _ = SpeakerProfile.objects.get_or_create(user=user, event=event)
        submission.speakers.add(speaker)
        resource = ResourceFactory(
            submission=submission, link="https://example.com/old"
        )
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "title": submission.title,
                    "abstract": submission.abstract or "An abstract",
                    "submission_type": submission.submission_type_id,
                    "content_locale": "en",
                },
                "info__resources": {
                    "resource-TOTAL_FORMS": "1",
                    "resource-INITIAL_FORMS": "1",
                    "resource-MIN_NUM_FORMS": "0",
                    "resource-MAX_NUM_FORMS": "1000",
                    "resource-0-id": str(resource.pk),
                    "resource-0-description": "Slides",
                    "resource-0-link": resource.link,
                    "resource-0-DELETE": "on",
                },
            },
            code=submission.code,
        ),
        access_code=None,
    )
    request._messages = FallbackStorage(request)
    step.request = request

    with scopes_disabled():
        step.done(request, draft=True)

        assert not Resource.objects.filter(pk=resource.pk).exists()


@pytest.mark.django_db
def test_info_step_done_skips_resources_when_formset_invalid():
    """done() skips resource processing when the formset is invalid."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["resources"]["visibility"] = "optional"
        event.cfp.save()
        user = UserFactory()
        submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        speaker, _ = SpeakerProfile.objects.get_or_create(user=user, event=event)
        submission.speakers.add(speaker)
    step = InfoStep(event=event)
    # Intentionally no resource formset data (no management form fields)
    request = make_request(
        event,
        user=user,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "title": submission.title,
                    "abstract": submission.abstract or "An abstract",
                    "submission_type": submission.submission_type_id,
                    "content_locale": "en",
                }
            },
            code=submission.code,
        ),
        access_code=None,
    )
    request._messages = FallbackStorage(request)
    step.request = request

    with scopes_disabled():
        step.done(request, draft=True)

        # No resources should have been created
        assert submission.resources.count() == 0


@pytest.mark.django_db
def test_info_step_done_catches_send_mail_exception(monkeypatch):
    """done() catches SendMailException when sending speaker invitations
    instead of crashing — the submission is still created."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()

    def _send_raises(self, _from=None, **kwargs):
        raise SendMailException("SMTP error")

    monkeypatch.setattr(SubmissionInvitation, "send", _send_raises)

    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "title": "Talk with Co-Speaker",
                    "abstract": "An abstract",
                    "submission_type": event.cfp.default_type.pk,
                    "content_locale": "en",
                    "additional_speaker": ["cospeaker@example.com"],
                }
            }
        ),
        access_code=None,
    )
    request._messages = FallbackStorage(request)
    step.request = request

    with scopes_disabled():
        step.done(request, draft=False)

    # The submission was still created despite the mail failure
    with scopes_disabled():
        assert Submission.objects.filter(pk=request.submission.pk).exists()
        # The invitation was created in the DB before send() raised
        assert SubmissionInvitation.objects.filter(
            submission=request.submission, email="cospeaker@example.com"
        ).exists()


@pytest.mark.django_db
def test_info_step_done_fires_submission_state_change_signal(register_signal_handler):
    """When a non-draft submission is created through the CfP flow,
    the submission_state_change signal fires so plugins can react."""
    received = []

    def handler(signal, sender, submission, **kwargs):
        received.append(submission)

    register_signal_handler(submission_state_change, handler)

    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=_resolver(),
        session=_cfp_session(
            data={
                "info": {
                    "title": "Signal Test Talk",
                    "abstract": "Testing signals",
                    "submission_type": event.cfp.default_type.pk,
                    "content_locale": "en",
                }
            }
        ),
        access_code=None,
    )
    request._messages = FallbackStorage(request)
    step.request = request

    with scopes_disabled():
        step.done(request, draft=False)

    assert len(received) == 1
    assert received[0].title == "Signal Test Talk"
    assert received[0].state == SubmissionStates.SUBMITTED
