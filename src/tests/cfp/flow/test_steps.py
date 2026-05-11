# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.messages import constants as message_constants
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.forms import ValidationError
from django.http import QueryDict
from django.utils.datastructures import MultiValueDict

from pretalx.cfp.flow import CfPFlow, InfoStep, ProfileStep, QuestionsStep, UserStep
from pretalx.common.exceptions import SendMailException
from pretalx.submission.models import (
    QuestionTarget,
    Resource,
    Submission,
    SubmissionStates,
)
from pretalx.submission.models.submission import SubmissionInvitation
from pretalx.submission.signals import submission_state_change
from tests.cfp.flow._helpers import make_cfp_session, make_resolver
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_request

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# InfoStep
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_info_step_get_form_initial_populates_submission_type_from_url():
    event = EventFactory()
    sub_type = event.cfp.default_type
    step = InfoStep(event=event)
    request = make_request(
        event,
        path=f"/?submission_type={sub_type.pk}",
        resolver_match=make_resolver(),
        session=make_cfp_session(),
    )
    step.request = request

    result = step.get_form_initial()

    assert result["submission_type"] == sub_type


@pytest.mark.django_db
def test_info_step_get_form_initial_populates_track_from_url():
    event = EventFactory()
    track = TrackFactory(event=event)
    step = InfoStep(event=event)
    request = make_request(
        event,
        path=f"/?track={track.pk}",
        resolver_match=make_resolver(),
        session=make_cfp_session(),
    )
    step.request = request

    result = step.get_form_initial()

    assert result["track"] == track


@pytest.mark.django_db
def test_info_step_get_form_initial_handles_slug_style_id():
    """Submission type ID can be in format 'pk-slug'."""
    event = EventFactory()
    sub_type = event.cfp.default_type
    step = InfoStep(event=event)
    request = make_request(
        event,
        path=f"/?submission_type={sub_type.pk}-talk",
        resolver_match=make_resolver(),
        session=make_cfp_session(),
    )
    step.request = request

    result = step.get_form_initial()

    assert result["submission_type"] == sub_type


@pytest.mark.parametrize(
    "query_value", ("invalid", "99999"), ids=("non_numeric", "nonexistent_pk")
)
@pytest.mark.django_db
def test_info_step_get_form_initial_ignores_bad_submission_type(query_value):
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        path=f"/?submission_type={query_value}",
        resolver_match=make_resolver(),
        session=make_cfp_session(),
    )
    step.request = request

    result = step.get_form_initial()

    assert "submission_type" not in result


@pytest.mark.django_db
def test_info_step_get_form_data_joins_additional_speaker_list():
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
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
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"info": {"additional_speaker": "a@example.com"}}
        ),
    )
    step.request = request

    result = step.get_form_data()

    assert result["additional_speaker"] == "a@example.com"


@pytest.mark.django_db
def test_info_step_get_form_kwargs_includes_access_code():
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(),
        access_code="test_code",
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["access_code"] == "test_code"


@pytest.mark.django_db
def test_info_step_get_form_kwargs_access_code_none_when_absent():
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )
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
    kwargs = {}
    if visibility:
        kwargs["cfp__fields"] = {"resources": {"visibility": visibility}}
    event = EventFactory(**kwargs)
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


@pytest.mark.django_db
def test_info_step_get_resource_formset_returns_none_when_disabled():
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request

    assert step.get_resource_formset(submission=None) is None


@pytest.mark.django_db
def test_info_step_get_resource_formset_returns_formset_when_enabled():
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    step = InfoStep(event=event)
    request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request

    formset = step.get_resource_formset(submission=None)
    assert formset.prefix == "resource"


@pytest.mark.django_db
def test_info_step_get_resource_formset_post_merges_stored_files():
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    session = make_cfp_session()

    # Phase 1: store a resource file via set_files on a GET request
    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=make_resolver(), session=session)
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
        event, method="post", resolver_match=make_resolver(), session=session
    )
    request.POST = QueryDict(
        "resource-TOTAL_FORMS=1&resource-INITIAL_FORMS=0"
        "&resource-MIN_NUM_FORMS=0&resource-MAX_NUM_FORMS=1000"
        "&resource-0-link=https://example.com"
    )
    step.request = request

    formset = step.get_resource_formset(submission=None)

    assert formset.files["resource-0-resource"].name == "slides.pdf"


@pytest.mark.django_db
def test_info_step_get_resource_formset_post_keeps_reuploaded_file():
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    session = make_cfp_session()

    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=make_resolver(), session=session)
    step.set_files(
        {
            "resource-0-resource": SimpleUploadedFile(
                "old.pdf", b"%PDF-old", content_type="application/pdf"
            )
        }
    )

    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=session
    )
    request.POST = QueryDict(
        "resource-TOTAL_FORMS=1&resource-INITIAL_FORMS=0"
        "&resource-MIN_NUM_FORMS=0&resource-MAX_NUM_FORMS=1000"
    )
    request._files = MultiValueDict(
        {
            "resource-0-resource": [
                SimpleUploadedFile(
                    "new.pdf", b"%PDF-new", content_type="application/pdf"
                )
            ]
        }
    )
    step.request = request

    formset = step.get_resource_formset(submission=None)

    assert formset.files["resource-0-resource"].name == "new.pdf"


@pytest.mark.django_db
def test_info_step_is_valid_false_when_resource_tmp_file_missing():
    """is_valid() must surface a user-facing error and return False when
    a resource upload's temp file has disappeared, instead of crashing
    the whole submit view with a 500."""
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    step = InfoStep(event=event)

    tmp_file = TemporaryUploadedFile("slides.pdf", "application/pdf", 4, "utf-8")
    tmp_file.write(b"%PDF")
    tmp_file.seek(0)
    Path(tmp_file.temporary_file_path()).unlink()

    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=make_cfp_session()
    )
    request.POST = QueryDict(
        "title=Test&abstract=An+abstract&content_locale=en"
        f"&submission_type={event.cfp.default_type.pk}"
        "&resource-TOTAL_FORMS=1&resource-INITIAL_FORMS=0"
        "&resource-MIN_NUM_FORMS=0&resource-MAX_NUM_FORMS=1000"
        "&resource-0-description=Slides"
    )
    request._files = MultiValueDict({"resource-0-resource": [tmp_file]})
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    assert step.cfp_session["files"].get("info", {}) == {}
    error_messages = [
        m for m in get_messages(request) if m.level == message_constants.ERROR
    ]
    assert len(error_messages) == 1


@pytest.mark.django_db
def test_info_step_is_completed_false_when_resources_required_and_formset_invalid():
    event = EventFactory(cfp__fields={"resources": {"visibility": "required"}})
    step = InfoStep(event=event)
    # Valid info data so the main form passes, but no resource formset data
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
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

    assert step.is_completed(request) is False


@pytest.mark.django_db
def test_info_step_is_completed_false_when_resources_required_but_all_deleted():
    event = EventFactory(cfp__fields={"resources": {"visibility": "required"}})
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
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

    assert step.is_completed(request) is False


@pytest.mark.django_db
def test_info_step_is_completed_true_when_resources_required_and_present():
    event = EventFactory(cfp__fields={"resources": {"visibility": "required"}})
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
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

    assert step.is_completed(request) is True


@pytest.mark.django_db
def test_info_step_done_processes_resource_delete():
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    speaker = SpeakerFactory(user=user, event=event)
    submission.speakers.add(speaker)
    resource = ResourceFactory(submission=submission, link="https://example.com/old")
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=make_resolver(),
        session=make_cfp_session(
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

    step.done(request, draft=True)

    assert not Resource.objects.filter(pk=resource.pk).exists()


@pytest.mark.django_db
def test_info_step_done_skips_resources_when_formset_invalid():
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    speaker = SpeakerFactory(user=user, event=event)
    submission.speakers.add(speaker)
    step = InfoStep(event=event)
    # Intentionally no resource formset data (no management form fields)
    request = make_request(
        event,
        user=user,
        resolver_match=make_resolver(),
        session=make_cfp_session(
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

    step.done(request, draft=True)

    # No resources should have been created
    assert submission.resources.count() == 0


@pytest.mark.django_db
def test_info_step_done_catches_send_mail_exception(monkeypatch):
    """done() catches SendMailException when sending speaker invitations
    instead of crashing — the submission is still created."""
    event = EventFactory()
    user = UserFactory()

    def _raise(*_, **__):
        raise SendMailException("SMTP error")

    monkeypatch.setattr("pretalx.submission.domain.invitation.send_transient", _raise)

    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=make_resolver(),
        session=make_cfp_session(
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

    step.done(request, draft=False)

    # The submission was still created despite the mail failure
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

    event = EventFactory()
    user = UserFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=make_resolver(),
        session=make_cfp_session(
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

    step.done(request, draft=False)

    assert len(received) == 1
    assert received[0].title == "Signal Test Talk"
    assert received[0].state == SubmissionStates.SUBMITTED


# ---------------------------------------------------------------------------
# QuestionsStep
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_questions_step_is_applicable_with_submission_questions():
    event = EventFactory()
    QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    assert step.is_applicable(request) is True


@pytest.mark.django_db
def test_questions_step_is_applicable_with_speaker_questions():
    event = EventFactory()
    QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    assert step.is_applicable(request) is True


@pytest.mark.django_db
def test_questions_step_not_applicable_without_questions():
    event = EventFactory()
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    assert step.is_applicable(request) is False


@pytest.mark.django_db
def test_questions_step_not_applicable_when_question_filtered_by_type():
    event = EventFactory()
    other_type = SubmissionTypeFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    question.submission_types.add(other_type)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    assert step.is_applicable(request) is False


@pytest.mark.django_db
def test_questions_step_applicable_when_question_matches_type():
    event = EventFactory()
    default_type = event.cfp.default_type
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    question.submission_types.add(default_type)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(data={"info": {"submission_type": default_type.pk}}),
    )
    step.request = request

    assert step.is_applicable(request) is True


@pytest.mark.django_db
def test_questions_step_applicable_with_track_filtering():
    event = EventFactory()
    track = TrackFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    question.tracks.add(track)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={
                "info": {
                    "submission_type": event.cfp.default_type.pk,
                    "track": track.pk,
                }
            }
        ),
    )
    step.request = request

    assert step.is_applicable(request) is True


@pytest.mark.django_db
def test_questions_step_not_applicable_with_wrong_track():
    event = EventFactory()
    track_a = TrackFactory(event=event)
    track_b = TrackFactory(event=event)
    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    question.tracks.add(track_a)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={
                "info": {
                    "submission_type": event.cfp.default_type.pk,
                    "track": track_b.pk,
                }
            }
        ),
    )
    step.request = request

    assert step.is_applicable(request) is False


@pytest.mark.django_db
def test_questions_step_get_form_kwargs_includes_track_and_type():
    event = EventFactory()
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(data={"info": {"track": 5, "submission_type": 3}}),
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["track"] == 5
    assert result["submission_type"] == 3
    assert result["target"] == ""


@pytest.mark.django_db
def test_questions_step_get_form_kwargs_uses_access_code_type():
    event = EventFactory()
    access_type = SubmissionTypeFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(access_type)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"info": {"track": None, "submission_type": event.cfp.default_type.pk}}
        ),
        access_code=access_code,
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["submission_type"] == access_type


@pytest.mark.django_db
def test_questions_step_get_form_kwargs_includes_speaker_for_authenticated():
    event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(user=user, event=event)
    step = QuestionsStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"info": {"track": None, "submission_type": event.cfp.default_type.pk}}
        ),
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["speaker"] == speaker


# ---------------------------------------------------------------------------
# UserStep
# ---------------------------------------------------------------------------


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
    event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["user"]
    request = make_request(
        event,
        resolver_match=make_resolver(event=event.slug, step="user"),
        session=make_cfp_session(),
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["request"] is request
    assert result["no_buttons"] is True
    assert f"/{event.slug}/submit/abc123/profile/" in result["success_url"]


@pytest.mark.django_db
def test_user_step_done_raises_for_inactive_user():
    event = EventFactory()
    user = UserFactory(is_active=False)
    step = UserStep(event=event)
    request = make_request(
        event, user=user, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request

    with pytest.raises(ValidationError):
        step.done(request)


# ---------------------------------------------------------------------------
# ProfileStep
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_profile_step_set_data_stores_avatar_action():
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=make_cfp_session()
    )
    request.POST = QueryDict("avatar_action=remove")
    step.request = request

    step.set_data({"name": "Alice"})

    assert step.cfp_session["data"]["profile"]["avatar_action"] == "remove"


@pytest.mark.django_db
def test_profile_step_set_data_ignores_keep_avatar_action():
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=make_cfp_session()
    )
    request.POST = QueryDict("avatar_action=keep")
    step.request = request

    step.set_data({"name": "Alice"})

    assert "avatar_action" not in step.cfp_session["data"]["profile"]


@pytest.mark.django_db
def test_profile_step_set_data_ignores_avatar_action_on_get():
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request

    step.set_data({"name": "Alice"})

    assert "avatar_action" not in step.cfp_session["data"]["profile"]


@pytest.mark.django_db
def test_profile_step_get_form_kwargs_uses_authenticated_user():
    event = EventFactory()
    user = UserFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, user=user, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["user"] == user
    assert result["name"] == user.name
    assert result["read_only"] is False
    assert result["essential_only"] is True


@pytest.mark.django_db
def test_profile_step_get_form_kwargs_uses_session_user_data():
    event = EventFactory()
    user = UserFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"user": {"user_id": user.pk, "register_name": "From Session"}}
        ),
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result["user"] == user
    assert result["name"] == user.name


@pytest.mark.django_db
def test_profile_step_get_form_kwargs_uses_register_name_without_user():
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(data={"user": {"register_name": "New Person"}}),
    )
    step.request = request

    result = step.get_form_kwargs()

    assert result.get("user") is None
    assert result["name"] == "New Person"
