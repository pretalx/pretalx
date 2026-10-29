# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from pathlib import Path
from types import SimpleNamespace

import pytest
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
def test_info_step_get_form_initial_reads_type_and_track_from_url():
    event = EventFactory()
    sub_type = event.cfp.default_type
    track = TrackFactory(event=event)

    def initial(query):
        step = InfoStep(event=event)
        step.request = make_request(
            event,
            path=f"/?{query}",
            resolver_match=make_resolver(),
            session=make_cfp_session(),
        )
        return step.get_form_initial()

    assert initial(f"submission_type={sub_type.pk}") == {"submission_type": sub_type}
    assert initial(f"submission_type={sub_type.pk}-talk") == {
        "submission_type": sub_type
    }
    assert initial(f"track={track.pk}") == {"track": track}
    assert initial("submission_type=invalid") == {}
    assert initial("submission_type=99999") == {}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("stored", "expected"),
    (
        (["a@example.com", "b@example.com"], "a@example.com,b@example.com"),
        ("a@example.com", "a@example.com"),
    ),
    ids=["list", "string"],
)
def test_info_step_get_form_data_joins_additional_speaker_list(stored, expected):
    event = EventFactory()
    step = InfoStep(event=event)
    step.request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"info": {"additional_speaker": stored, "title": "Test"}}
        ),
    )

    assert step.get_form_data() == {"additional_speaker": expected, "title": "Test"}


@pytest.mark.django_db
def test_info_step_get_form_kwargs_passes_request_access_code():
    event = EventFactory()
    with_code = InfoStep(event=event)
    with_code.request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(),
        access_code="test_code",
    )
    without_code = InfoStep(event=event)
    without_code.request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )

    assert with_code.get_form_kwargs()["access_code"] == "test_code"
    assert without_code.get_form_kwargs()["access_code"] is None


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


def test_info_step_formset_has_resources_ignores_deleted_rows():
    step = InfoStep(event=None)
    kept = SimpleNamespace(cleaned_data={"description": "Slides", "DELETE": False})
    deleted = SimpleNamespace(cleaned_data={"description": "Slides", "DELETE": True})

    assert step._formset_has_resources(SimpleNamespace(forms=[kept, deleted])) is True
    assert step._formset_has_resources(SimpleNamespace(forms=[deleted])) is False


@pytest.mark.django_db
def test_info_step_get_resource_formset_only_when_enabled():
    disabled = InfoStep(event=EventFactory())
    enabled = InfoStep(
        event=EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    )
    for step in (disabled, enabled):
        step.request = make_request(
            step.event, resolver_match=make_resolver(), session=make_cfp_session()
        )

    assert disabled.get_resource_formset(submission=None) is None
    assert enabled.get_resource_formset(submission=None).prefix == "resource"


@pytest.mark.django_db
def test_info_step_get_resource_formset_post_prefers_reupload_over_stored_file():
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    session = make_cfp_session()
    management = (
        "resource-TOTAL_FORMS=1&resource-INITIAL_FORMS=0"
        "&resource-MIN_NUM_FORMS=0&resource-MAX_NUM_FORMS=1000"
    )

    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=make_resolver(), session=session)
    step.set_files(
        {
            "resource-0-resource": SimpleUploadedFile(
                "old.pdf", b"%PDF-old", content_type="application/pdf"
            )
        }
    )

    def post_formset(files):
        step = InfoStep(event=event)
        request = make_request(
            event, method="post", resolver_match=make_resolver(), session=session
        )
        request.POST = QueryDict(management + "&resource-0-link=https://example.com")
        request._files = MultiValueDict(files)
        step.request = request
        return step.get_resource_formset(submission=None)

    assert post_formset({}).files["resource-0-resource"].name == "old.pdf"
    new_upload = SimpleUploadedFile(
        "new.pdf", b"%PDF-new", content_type="application/pdf"
    )
    assert (
        post_formset({"resource-0-resource": [new_upload]})
        .files["resource-0-resource"]
        .name
        == "new.pdf"
    )


@pytest.mark.django_db
def test_info_step_is_valid_false_when_resource_tmp_file_missing():
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
    assert list(get_messages(request)) == []
    assert step.resource_formset.forms[0].errors == {
        "resource": ["Your file upload could not be processed. Please try again."]
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("description_valid", "file_valid", "expected_name"),
    ((False, True, "slides.pdf"), (True, False, None)),
    ids=("kept_when_other_field_invalid", "dropped_when_own_field_invalid"),
)
def test_info_step_is_valid_persists_resource_unless_own_field_invalid(
    description_valid, file_valid, expected_name
):
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=make_cfp_session()
    )
    post = (
        "title=Test&abstract=An+abstract&content_locale=en"
        f"&submission_type={event.cfp.default_type.pk}"
        "&resource-TOTAL_FORMS=1&resource-INITIAL_FORMS=0"
        "&resource-MIN_NUM_FORMS=0&resource-MAX_NUM_FORMS=1000"
    )
    if description_valid:
        post += "&resource-0-description=Slides"
    request.POST = QueryDict(post)
    upload = (
        SimpleUploadedFile("slides.pdf", b"%PDF", content_type="application/pdf")
        if file_valid
        else SimpleUploadedFile("evil.exe", b"MZ", content_type="application/x-dosexec")
    )
    request._files = MultiValueDict({"resource-0-resource": [upload]})
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    stored = step.cfp_session["files"].get("info", {}).get("resource-0-resource")
    assert (stored["name"] if stored else None) == expected_name


@pytest.mark.django_db
def test_info_step_is_valid_drops_stored_resource_of_deleted_row():
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    session = make_cfp_session()

    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=make_resolver(), session=session)
    step.set_files(
        {
            "resource-0-resource": SimpleUploadedFile(
                "gone.pdf", b"%PDF-gone", content_type="application/pdf"
            ),
            "resource-1-resource": SimpleUploadedFile(
                "kept.pdf", b"%PDF-kept", content_type="application/pdf"
            ),
        }
    )

    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=session
    )
    request.POST = QueryDict(
        "title=Test&abstract=An+abstract&content_locale=en"
        f"&submission_type={event.cfp.default_type.pk}"
        "&resource-TOTAL_FORMS=2&resource-INITIAL_FORMS=0"
        "&resource-MIN_NUM_FORMS=0&resource-MAX_NUM_FORMS=1000"
        "&resource-0-description=Gone&resource-0-DELETE=on"
        "&resource-1-description=Kept"
    )
    request._files = MultiValueDict()
    request._messages = FallbackStorage(request)
    step.request = request

    step.is_valid()

    assert set(step.cfp_session["files"]["info"]) == {"resource-1-resource"}


@pytest.mark.django_db
def test_info_step_keeps_held_resource_when_replacement_rejected():
    event = EventFactory(cfp__fields={"resources": {"visibility": "optional"}})
    session = make_cfp_session()

    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=make_resolver(), session=session)
    step.set_files(
        {
            "resource-0-resource": SimpleUploadedFile(
                "slides.pdf", b"%PDF", content_type="application/pdf"
            )
        }
    )

    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=session
    )
    request.POST = QueryDict(
        "title=Test&abstract=An+abstract&content_locale=en"
        f"&submission_type={event.cfp.default_type.pk}"
        "&resource-TOTAL_FORMS=1&resource-INITIAL_FORMS=0"
        "&resource-MIN_NUM_FORMS=0&resource-MAX_NUM_FORMS=1000"
        "&resource-0-description=Slides"
    )
    request._files = MultiValueDict(
        {
            "resource-0-resource": [
                SimpleUploadedFile(
                    "evil.exe", b"MZ", content_type="application/x-dosexec"
                )
            ]
        }
    )
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    form = step.get_context_data()["resource_formset"].forms[0]

    assert form.errors == {
        "resource": [
            (
                "This filetype (.exe) is not allowed, it has to be one of "
                "the following: .png, .jpg, .jpeg, .gif, .webp, .bmp, .tif, "
                ".tiff, .pdf, .txt, .csv, .zip, .doc, .docx, .rtf, .ppt, "
                ".pptx, .xls, .xlsx, .odt, .ods, .odp"
            )
        ]
    }
    assert form.fields["resource"].widget.stored_filename == "slides.pdf"
    assert step.cfp_session["files"]["info"]["resource-0-resource"]["name"] == (
        "slides.pdf"
    )


RESOURCE_MANAGEMENT = {
    "resource-TOTAL_FORMS": "1",
    "resource-INITIAL_FORMS": "0",
    "resource-MIN_NUM_FORMS": "0",
    "resource-MAX_NUM_FORMS": "1000",
}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("resources", "expected"),
    (
        ({}, False),
        (
            {
                "info__resources": RESOURCE_MANAGEMENT
                | {"resource-0-link": "https://example.com", "resource-0-DELETE": "on"}
            },
            False,
        ),
        (
            {
                "info__resources": RESOURCE_MANAGEMENT
                | {
                    "resource-0-description": "Slides",
                    "resource-0-link": "https://example.com/slides",
                }
            },
            True,
        ),
    ),
    ids=["no_formset", "all_deleted", "present"],
)
def test_info_step_is_completed_needs_required_resources(resources, expected):
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
                }
            }
            | resources
        ),
    )
    step.request = request

    assert step.is_completed(request) is expected


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
def test_info_step_done_creates_submission_despite_invitation_mail_failure(
    monkeypatch, register_signal_handler
):
    received = []

    def handler(signal, sender, submission, **kwargs):
        received.append(submission)

    def _raise(*_, **__):
        raise SendMailException("SMTP error")

    register_signal_handler(submission_state_change, handler)
    monkeypatch.setattr("pretalx.submission.domain.invitation.render_to_mail", _raise)
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=UserFactory(),
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

    submission = Submission.objects.get(pk=request.submission.pk)
    assert submission.title == "Talk with Co-Speaker"
    assert submission.state == SubmissionStates.SUBMITTED
    assert received == [submission]
    assert list(
        SubmissionInvitation.objects.filter(submission=submission).values_list(
            "email", flat=True
        )
    ) == ["cospeaker@example.com"]


# ---------------------------------------------------------------------------
# QuestionsStep
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_questions_step_is_applicable_when_a_question_matches_type_and_track():
    event = EventFactory()
    default_type = event.cfp.default_type
    other_type = SubmissionTypeFactory(event=event)
    track_a = TrackFactory(event=event)
    track_b = TrackFactory(event=event)

    def applicable(**info):
        step = QuestionsStep(event=event)
        request = make_request(
            event,
            resolver_match=make_resolver(),
            session=make_cfp_session(
                data={"info": {"submission_type": default_type.pk, **info}}
            ),
        )
        step.request = request
        return step.is_applicable(request)

    assert applicable() is False

    question = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    assert applicable() is True

    question.submission_types.add(other_type)
    assert applicable() is False
    question.submission_types.set([default_type])
    assert applicable() is True

    question.tracks.add(track_a)
    assert applicable(track=track_a.pk) is True
    assert applicable(track=track_b.pk) is False

    QuestionFactory(event=event, target=QuestionTarget.SPEAKER)
    assert applicable(track=track_b.pk) is True


@pytest.mark.django_db
def test_questions_step_get_form_kwargs_resolves_type_track_and_speaker():
    event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(user=user, event=event)
    access_type = SubmissionTypeFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(access_type)

    def form_kwargs(info, **request_attrs):
        step = QuestionsStep(event=event)
        step.request = make_request(
            event,
            resolver_match=make_resolver(),
            session=make_cfp_session(data={"info": info}),
            **request_attrs,
        )
        return step.get_form_kwargs()

    plain = form_kwargs({"track": 5, "submission_type": 3})
    assert plain["track"] == 5
    assert plain["submission_type"] == 3
    assert plain["target"] == ""
    assert "speaker" not in plain

    info = {"track": None, "submission_type": event.cfp.default_type.pk}
    assert form_kwargs(info, access_code=access_code)["submission_type"] == access_type
    assert form_kwargs(info, user=user)["speaker"] == speaker


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
def test_profile_step_keeps_avatar_upload_when_name_missing(make_image):
    event = EventFactory()
    user = UserFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        user=user,
        method="post",
        resolver_match=make_resolver(),
        session=make_cfp_session(),
    )
    request.POST = QueryDict("name=&avatar_action=upload")
    request._files = MultiValueDict({"avatar": [make_image("face.png")]})
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    assert step.cfp_session["files"]["profile"]["avatar"]["name"] == "face.png"


@pytest.mark.django_db
def test_profile_step_set_data_stores_posted_avatar_action_unless_keep():
    event = EventFactory()

    def stored_data(method, post):
        step = ProfileStep(event=event)
        step.request = make_request(
            event,
            method=method,
            resolver_match=make_resolver(),
            session=make_cfp_session(),
        )
        step.request.POST = QueryDict(post)
        step.set_data({"name": "Alice"})
        return step.cfp_session["data"]["profile"]

    assert stored_data("post", "avatar_action=remove") == {
        "name": "Alice",
        "avatar_action": "remove",
    }
    assert stored_data("post", "avatar_action=keep") == {"name": "Alice"}
    assert stored_data("get", "avatar_action=remove") == {"name": "Alice"}


@pytest.mark.django_db
def test_profile_step_get_form_kwargs_resolves_user_from_request_or_session():
    event = EventFactory()
    user = UserFactory()

    def form_kwargs(**request_attrs):
        step = ProfileStep(event=event)
        step.request = make_request(
            event, resolver_match=make_resolver(), **request_attrs
        )
        return step.get_form_kwargs()

    authenticated = form_kwargs(user=user, session=make_cfp_session())
    assert authenticated["instance"] == user.get_speaker(event)
    assert authenticated["name"] == user.name
    assert authenticated["read_only"] is False
    assert authenticated["essential_only"] is True

    from_session = form_kwargs(
        session=make_cfp_session(
            data={"user": {"user_id": user.pk, "register_name": "From Session"}}
        )
    )
    assert from_session["instance"] == user.get_speaker(event)
    assert from_session["name"] == user.name

    registering = form_kwargs(
        session=make_cfp_session(data={"user": {"register_name": "New Person"}})
    )
    assert registering["instance"] is None
    assert registering["name"] == "New Person"
