# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.submission.models import Submission, SubmissionStates
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.cfp.views.conftest import get_response_and_url, info_data, start_wizard
from tests.factories import (
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


def _post_info(
    client, url, event, submission_type=None, title="Submission title", **extra
):
    """Post the info step with standard defaults, returning (response, next_url)."""
    data = info_data(event, submission_type=submission_type, title=title, **extra)
    return get_response_and_url(client, url, data=data)


def _post_questions(client, url, question_data):
    """Post the questions step."""
    return get_response_and_url(client, url, data=question_data)


def _register_user(client, url, email="testuser@example.com", password="testpassw0rd!"):
    """Register a new user on the user step."""
    data = {
        "register_name": email,
        "register_email": email,
        "register_password": password,
        "register_password_repeat": password,
    }
    return get_response_and_url(client, url, data=data)


def _login_user(client, url, email, password="testpassw0rd!"):
    """Login an existing user on the user step."""
    data = {"login_email": email, "login_password": password}
    return get_response_and_url(client, url, data=data)


def _post_profile(client, url, name="Jane Doe", biography="l337 hax0r"):
    """Post the profile step."""
    data = {"name": name, "biography": biography}
    return get_response_and_url(client, url, data=data)


def _assert_submission(
    event,
    title="Submission title",
    content_locale="en",
    description="Description",
    abstract="Abstract",
    notes="Notes",
    question=None,
    answer="42",
    track=None,
    tags=None,
):
    """Verify the created submission matches expectations."""
    with scope(event=event):
        sub = Submission.objects.last()
        assert sub.title == title
        assert sub.submission_type is not None
        assert sub.content_locale == content_locale
        assert sub.description == description
        assert sub.abstract == abstract
        assert sub.notes == notes
        assert sub.slot_count == 1
        if question:
            answ = sub.answers.first()
            assert answ is not None
            assert answ.question == question
            assert answ.answer == answer
        else:
            assert sub.answers.count() == 0
        if track:
            assert sub.track == track
        else:
            assert sub.track is None
        if tags:
            assert set(sub.tags.all()) == set(tags)
    return sub


def _assert_speaker(
    submission, email="testuser@example.com", name="Jane Doe", biography="l337 hax0r"
):
    """Verify the speaker profile on the submission."""
    with scope(event=submission.event):
        profile = submission.speakers.get(user__email=email)
        assert profile.name == name
        assert profile.biography == biography
    return profile.user


@pytest.fixture
def multiple_choice_question(cfp_event):
    """A speaker-targeted multiple choice question with three options."""
    with scopes_disabled():
        question = QuestionFactory(
            event=cfp_event,
            question="Which colors other than green do you like?",
            variant=QuestionVariant.MULTIPLE,
            target="speaker",
            question_required=QuestionRequired.OPTIONAL,
            position=10,
        )
        for answer in ("yellow", "blue", "black"):
            AnswerOptionFactory(question=question, answer=answer)
    return question


def test_e2e_new_user_submission_with_questions(cfp_event, client):
    """Complete submission flow: new user registers, answers questions, fills profile.

    Verifies:
    - Submission created with correct field values
    - Question answer saved
    - Speaker profile created
    - Confirmation email sent
    """
    djmail.outbox = []
    with scopes_disabled():
        submission_question = QuestionFactory(
            event=cfp_event,
            question="How much do you like green, on a scale from 1-10?",
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            position=1,
        )
        sub_type = cfp_event.cfp.default_type
        sub_type.deadline = cfp_event.cfp.deadline
        sub_type.save(update_fields=["deadline"])

    _, info_url = start_wizard(client, cfp_event)
    _, q_url = _post_info(client, info_url, cfp_event)
    assert "/questions/" in q_url

    answer_data = {f"question_{submission_question.pk}": "42"}
    _, user_url = _post_questions(client, q_url, answer_data)
    assert "/user/" in user_url

    # Try wrong credentials first, then register
    _, stay_url = _login_user(client, user_url, email="wrong@example.org")
    assert "/user/" in stay_url

    _, profile_url = _register_user(client, user_url)
    assert "/profile/" in profile_url

    response, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    sub = _assert_submission(cfp_event, question=submission_question)
    _assert_speaker(sub)
    assert len(djmail.outbox) == 1
    assert sub.title in djmail.outbox[0].subject
    assert sub.title in djmail.outbox[0].body
    assert "testuser@example.com" in djmail.outbox[0].to
    assert sub.state == SubmissionStates.SUBMITTED


def test_e2e_new_user_with_mail_on_new_submission(client):
    """New user submission with mail_on_new_submission sends 2 emails (user + orga)."""
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        mail_settings={"mail_on_new_submission": True},
    )
    djmail.outbox = []

    _, info_url = start_wizard(client, event)
    _, user_url = _post_info(client, info_url, event)
    _, profile_url = _register_user(client, user_url)
    _post_profile(client, profile_url)

    assert len(djmail.outbox) == 2


def test_e2e_existing_user_login_with_questions(
    cfp_event, client, cfp_user, choice_question, multiple_choice_question
):
    """Existing user logs in and submits with various question types.

    Tests choice, multiple choice, file, and speaker questions.
    """
    with scopes_disabled():
        submission_question = QuestionFactory(
            event=cfp_event,
            question="How much do you like green, on a scale from 1-10?",
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            position=1,
        )
        speaker_question = QuestionFactory(
            event=cfp_event,
            question="What is your favourite color?",
            variant=QuestionVariant.STRING,
            target="speaker",
            question_required=QuestionRequired.OPTIONAL,
            position=3,
        )
        file_question = QuestionFactory(
            event=cfp_event,
            question="Please submit your paper.",
            variant=QuestionVariant.FILE,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            position=7,
        )
        sub_type = cfp_event.cfp.default_type_id
        answer_data = {
            f"question_{submission_question.pk}": "42",
            f"question_{speaker_question.pk}": "green",
            f"question_{choice_question.pk}": choice_question.options.first().pk,
            f"question_{multiple_choice_question.pk}": multiple_choice_question.options.first().pk,
            f"question_{file_question.pk}": SimpleUploadedFile(
                "testfile.txt", b"file_content"
            ),
        }

    _, info_url = start_wizard(client, cfp_event)
    _, q_url = _post_info(client, info_url, cfp_event, submission_type=sub_type)
    assert "/questions/" in q_url

    _, user_url = _post_questions(client, q_url, answer_data)
    assert "/user/" in user_url

    _, profile_url = _login_user(client, user_url, email=cfp_user.email)
    assert "/profile/" in profile_url

    _, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    sub = _assert_submission(cfp_event, question=submission_question)
    _assert_speaker(sub, email=cfp_user.email)
    with scope(event=cfp_event):
        assert file_question.answers.first().answer_file.read() == b"file_content"
        # Verify speaker question answer is on the profile, not the submission
        profile = sub.speakers.get(user__email=cfp_user.email)
        speaker_answer = profile.answers.filter(question=speaker_question).first()
        assert speaker_answer is not None
        assert speaker_answer.answer == "green"
        assert speaker_answer.submission is None


def test_e2e_logged_in_user_skips_user_step(cfp_event, client, cfp_user):
    djmail.outbox = []
    with scopes_disabled():
        submission_question = QuestionFactory(
            event=cfp_event,
            question="How much do you like green, on a scale from 1-10?",
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            position=1,
        )
    client.force_login(cfp_user)

    _, info_url = start_wizard(client, cfp_event)
    _, q_url = _post_info(client, info_url, cfp_event)
    assert "/questions/" in q_url

    answer_data = {f"question_{submission_question.pk}": "42"}
    _, profile_url = _post_questions(client, q_url, answer_data)
    assert "/profile/" in profile_url

    _, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    sub = _assert_submission(cfp_event, question=submission_question)
    _assert_speaker(sub, email=cfp_user.email)
    assert len(djmail.outbox) == 1


def test_e2e_logged_in_user_no_questions(cfp_event, client, cfp_user):
    """When no questions exist, logged-in user goes info → profile → done."""
    client.force_login(cfp_user)

    _, info_url = start_wizard(client, cfp_event)
    _, profile_url = _post_info(client, info_url, cfp_event)
    assert "/profile/" in profile_url

    _, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    sub = _assert_submission(cfp_event)
    _assert_speaker(sub, email=cfp_user.email)


def test_e2e_single_non_english_content_locale_do_not_ask(client):
    """When an event has a single non-English content locale and the field is
    set to do_not_ask, submissions should still get the event's content locale."""
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"content_locale": {"visibility": "do_not_ask"}},
        locale="de",
        locale_array="de",
        content_locale_array="de",
    )
    user = UserFactory()
    client.force_login(user)

    _, info_url = start_wizard(client, event)
    _, profile_url = _post_info(client, info_url, event)
    assert "/profile/" in profile_url

    _, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    with scope(event=event):
        sub = Submission.objects.last()
        assert sub.content_locale == "de"


def test_e2e_tracks_with_access_code_and_questions(client):
    """Track requiring access code: no code fails, code succeeds with track-specific questions."""
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={
            "track": {"visibility": "required"},
            "abstract": {"visibility": "do_not_ask"},
        },
    )
    track = TrackFactory(event=event, name="Test Track", requires_access_code=True)
    TrackFactory(event=event, name="Second Track", requires_access_code=True)
    submission_question = QuestionFactory(
        event=event,
        question="How much do you like green, on a scale from 1-10?",
        variant=QuestionVariant.NUMBER,
        target="submission",
        question_required=QuestionRequired.OPTIONAL,
        position=1,
    )
    submission_question.tracks.add(track)
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(track)
    access_code.submission_types.add(event.cfp.default_type)
    sub_type = event.cfp.default_type_id

    _, info_url = start_wizard(client, event)

    # Without code — stays on info
    _, stay_url = _post_info(
        client, info_url, event, submission_type=sub_type, track=track.pk
    )
    assert "/info/" in stay_url

    # With code — proceeds
    code_url = info_url + "?access_code=" + access_code.code
    _, q_url = _post_info(
        client, code_url, event, submission_type=sub_type, track=track.pk
    )
    assert "/questions/" in q_url

    answer_data = {f"question_{submission_question.pk}": "42"}
    _, user_url = _post_questions(client, q_url, answer_data)
    _, profile_url = _register_user(client, user_url)
    _, final_url = _post_profile(client, profile_url)

    assert "/me/submissions/" in final_url
    _assert_submission(event, track=track, question=submission_question, abstract=None)


def test_e2e_access_code_bypasses_deadline(client):
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=1))
    access_code = SubmitterAccessCodeFactory(event=event)

    _, info_url = start_wizard(client, event, access_code=access_code)
    assert "/info/" in info_url

    _, user_url = _post_info(client, info_url, event)
    _, profile_url = _register_user(client, user_url)
    _, final_url = _post_profile(client, profile_url)

    assert "/me/submissions/" in final_url
    with scope(event=event):
        sub = Submission.objects.last()
        assert sub.access_code == access_code


def test_e2e_additional_speakers_send_invitations(cfp_event, client, cfp_user):
    djmail.outbox = []
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    _, profile_url = _post_info(
        client,
        info_url,
        cfp_event,
        additional_speaker="speaker2@example.com,speaker3@example.com",
    )
    _, final_url = _post_profile(client, profile_url)

    assert "/me/submissions/" in final_url
    # 1 confirmation + 2 invitation emails
    assert len(djmail.outbox) == 3
    all_recipients = {mail.to[0] for mail in djmail.outbox}
    assert "speaker2@example.com" in all_recipients
    assert "speaker3@example.com" in all_recipients


def test_e2e_draft_save_and_resume(cfp_event, client, cfp_user):
    """Save as draft, then resume and complete the submission.

    Verifies:
    - Draft is saved with correct data
    - Resume loads draft values
    - Final submission transitions from DRAFT to SUBMITTED
    """
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(
        cfp_event,
        title="My Draft Talk",
        description="Draft desc",
        abstract="Draft abstract",
        notes="Draft notes",
        action="draft",
    )
    _, final_url = get_response_and_url(client, info_url, data=data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        draft = Submission.all_objects.filter(state=SubmissionStates.DRAFT).last()
        assert draft is not None
        assert draft.title == "My Draft Talk"
        code = draft.code

    # Resume the draft
    restart_url = f"/{cfp_event.slug}/submit/restart-{code}/"
    response, resume_url = get_response_and_url(client, restart_url, method="GET")
    assert "/info/" in resume_url
    assert "My Draft Talk" in response.content.decode()

    # Complete the submission
    _, profile_url = _post_info(client, resume_url, cfp_event, title="My Draft Talk")
    assert "/profile/" in profile_url
    _, done_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in done_url

    with scope(event=cfp_event):
        draft.refresh_from_db()
        assert draft.state == SubmissionStates.SUBMITTED


def test_e2e_draft_invalid_info_stays_on_step(cfp_event, client, cfp_user):
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, title="", action="draft")
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/info/" in url
    with scope(event=cfp_event):
        assert Submission.all_objects.filter(state=SubmissionStates.DRAFT).count() == 0


def test_e2e_draft_anonymous_login_then_save(cfp_event, client, cfp_user):
    """Anonymous user: draft on info → redirected to user step → login → draft saved."""
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event, title="Anonymous Draft", action="draft")
    _, user_url = get_response_and_url(client, info_url, data=data)
    assert "/user/" in user_url
    assert "draft=1" in user_url

    _, final_url = _login_user(client, user_url, email=cfp_user.email)
    assert "/me/submissions/" in final_url

    with scope(event=cfp_event):
        draft = Submission.all_objects.filter(state=SubmissionStates.DRAFT).last()
        assert draft is not None
        assert draft.title == "Anonymous Draft"


@pytest.mark.parametrize(
    ("resource_data", "expect_link"),
    (
        (
            {
                "description": "My slides",
                "link": "https://example.com/slides.pdf",
                "is_public": "on",
            },
            True,
        ),
        ({"description": "My slides", "is_public": "on"}, False),
    ),
    ids=["link", "file_upload"],
)
def test_e2e_wizard_with_resource(client, resource_data, expect_link):
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"resources": {"visibility": "optional"}},
    )
    user = UserFactory()
    sub_type = event.cfp.default_type_id

    if not expect_link:
        resource_data["resource"] = SimpleUploadedFile(
            "slides.pdf", b"fake pdf content", content_type="application/pdf"
        )

    client.force_login(user)
    _, info_url = start_wizard(client, event)
    data = info_data(event, title="Talk with resources", submission_type=sub_type)
    data["resource-TOTAL_FORMS"] = "1"
    for key, value in resource_data.items():
        data[f"resource-0-{key}"] = value
    _, profile_url = get_response_and_url(client, info_url, data=data)
    assert "/profile/" in profile_url

    _, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    with scope(event=event):
        sub = Submission.objects.last()
        assert sub.title == "Talk with resources"
        assert sub.resources.count() == 1
        resource = sub.resources.first()
        assert resource.description == "My slides"
        assert resource.is_public is True
        if expect_link:
            assert resource.link == "https://example.com/slides.pdf"
        else:
            assert resource.resource
            assert not resource.link


def test_e2e_wizard_resource_deleted_unsaved_form_ignored(client):
    """A resource form marked for deletion that was never saved is silently ignored."""
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"resources": {"visibility": "optional"}},
    )
    user = UserFactory()
    client.force_login(user)
    _, info_url = start_wizard(client, event)
    data = info_data(event, title="Talk with deleted unsaved resource")
    data.update(
        {
            "resource-TOTAL_FORMS": "2",
            # Form 0: valid resource
            "resource-0-description": "Real resource",
            "resource-0-link": "https://example.com/real",
            "resource-0-is_public": "on",
            # Form 1: filled but marked for deletion, never saved (no pk)
            "resource-1-description": "Discarded resource",
            "resource-1-link": "https://example.com/discard",
            "resource-1-DELETE": "on",
        }
    )
    _, profile_url = get_response_and_url(client, info_url, data=data)
    assert "/profile/" in profile_url

    _, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    with scope(event=event):
        sub = Submission.objects.last()
        assert sub.title == "Talk with deleted unsaved resource"
        assert sub.resources.count() == 1
        resource = sub.resources.first()
        assert resource.description == "Real resource"
        assert resource.link == "https://example.com/real"


def test_e2e_draft_with_resources_then_resume_and_submit(client):
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"resources": {"visibility": "optional"}},
    )
    user = UserFactory()
    client.force_login(user)
    _, info_url = start_wizard(client, event)
    data = info_data(event, title="Draft with resources", action="draft")
    data.update(
        {
            "resource-TOTAL_FORMS": "1",
            "resource-0-description": "Draft slides",
            "resource-0-link": "https://example.com/draft-slides",
            "resource-0-is_public": "on",
        }
    )
    get_response_and_url(client, info_url, data=data)

    with scope(event=event):
        sub = Submission.all_objects.filter(state=SubmissionStates.DRAFT).last()
        assert sub.resources.count() == 1
        code = sub.code
        resource_pk = sub.resources.first().pk

    # Resume the draft
    restart_url = f"/{event.slug}/submit/restart-{code}/"
    response, resume_url = get_response_and_url(client, restart_url, method="GET")
    content = response.content.decode()
    assert "Draft slides" in content
    assert "https://example.com/draft-slides" in content

    # Resubmit with existing resource
    data = info_data(event, title="Draft with resources")
    data.update(
        {
            "resource-TOTAL_FORMS": "1",
            "resource-INITIAL_FORMS": "1",
            "resource-0-description": "Draft slides",
            "resource-0-link": "https://example.com/draft-slides",
            "resource-0-is_public": "on",
            "resource-0-id": str(resource_pk),
        }
    )
    _, profile_url = get_response_and_url(client, resume_url, data=data)
    assert "/profile/" in profile_url

    _, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    with scope(event=event):
        sub.refresh_from_db()
        assert sub.state == SubmissionStates.SUBMITTED
        assert sub.resources.count() == 1
        resource = sub.resources.first()
        assert resource.description == "Draft slides"
        assert resource.link == "https://example.com/draft-slides"


def test_e2e_submission_type_access_code(cfp_event, client, cfp_access_code):
    with scopes_disabled():
        sub_type = cfp_event.cfp.default_type
        sub_type.requires_access_code = True
        sub_type.save(update_fields=["requires_access_code"])
        cfp_access_code.submission_types.add(sub_type)

    _, info_url = start_wizard(client, cfp_event)

    # Without code — stays on info (pass model instance to exercise conftest branch)
    _, stay_url = _post_info(client, info_url, cfp_event, submission_type=sub_type)
    assert "/info/" in stay_url

    # With code — full flow
    code_url = info_url + "?access_code=" + cfp_access_code.code
    _, user_url = _post_info(client, code_url, cfp_event, submission_type=sub_type.pk)
    assert "/user/" in user_url

    _, profile_url = _register_user(client, user_url)
    _, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    _assert_submission(cfp_event)


def test_e2e_wizard_with_tags(client):
    """Full wizard flow with public tags – private tags excluded."""
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"tags": {"visibility": "optional"}},
    )
    tag1 = TagFactory(event=event, tag="Python", is_public=True)
    tag2 = TagFactory(event=event, tag="Web", is_public=True)
    TagFactory(event=event, tag="Private", is_public=False)

    _, info_url = start_wizard(client, event)
    _, user_url = _post_info(client, info_url, event, tags=[tag1.pk, tag2.pk])
    _, profile_url = _register_user(client, user_url)
    _, final_url = _post_profile(client, profile_url)

    assert "/me/submissions/" in final_url
    sub = _assert_submission(event, tags=[tag1, tag2])
    _assert_speaker(sub)


def test_e2e_broken_template_no_email(cfp_event, client, cfp_user):
    """When the submission confirmation template has invalid variables, no email is sent
    but the submission still succeeds."""
    djmail.outbox = []
    with scopes_disabled():
        ack_template = cfp_event.get_mail_template("submission.new")
        ack_template.text = str(ack_template.text) + "{name} and {nonexistent}"
        ack_template.save()

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    _, profile_url = _post_info(client, info_url, cfp_event)
    _, final_url = _post_profile(client, profile_url)

    assert "/me/submissions/" in final_url
    _assert_submission(cfp_event)
    assert len(djmail.outbox) == 0
