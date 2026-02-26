import datetime as dt

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.submission.models import Submission, SubmissionStates, SubmissionType
from tests.cfp.views.conftest import get_response_and_url, info_data, start_wizard
from tests.factories import TagFactory

pytestmark = pytest.mark.e2e


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


@pytest.mark.django_db
def test_e2e_new_user_submission_with_questions(cfp_event, client, submission_question):
    """Complete submission flow: new user registers, answers questions, fills profile.

    Verifies:
    - Submission created with correct field values
    - Question answer saved
    - Speaker profile created
    - Confirmation email sent
    """
    djmail.outbox = []
    with scopes_disabled():
        sub_type = SubmissionType.objects.filter(event=cfp_event).first()
        sub_type.deadline = cfp_event.cfp.deadline
        sub_type.save()

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


@pytest.mark.django_db
def test_e2e_new_user_with_mail_on_new_submission(cfp_event, client):
    """New user submission with mail_on_new_submission sends 2 emails (user + orga)."""
    djmail.outbox = []
    with scopes_disabled():
        cfp_event.mail_settings["mail_on_new_submission"] = True
        cfp_event.save()

    _, info_url = start_wizard(client, cfp_event)
    _, user_url = _post_info(client, info_url, cfp_event)
    _, profile_url = _register_user(client, user_url)
    _post_profile(client, profile_url)

    assert len(djmail.outbox) == 2


@pytest.mark.django_db
def test_e2e_existing_user_login_with_questions(
    cfp_event,
    client,
    cfp_user,
    submission_question,
    speaker_question,
    choice_question,
    multiple_choice_question,
    file_question,
):
    """Existing user logs in and submits with various question types.

    Tests choice, multiple choice, file, and speaker questions.
    """
    with scopes_disabled():
        sub_type = SubmissionType.objects.filter(event=cfp_event).first().pk
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


@pytest.mark.django_db
def test_e2e_logged_in_user_skips_user_step(
    cfp_event, client, cfp_user, submission_question
):
    """A logged-in user skips the user step and goes directly to questions/profile."""
    djmail.outbox = []
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_e2e_tracks_with_access_code_and_questions(
    cfp_event, client, cfp_access_code, cfp_track, cfp_other_track, submission_question
):
    """Track requiring access code: no code fails, code succeeds with track-specific questions."""
    with scopes_disabled():
        sub_type = SubmissionType.objects.filter(event=cfp_event).first().pk
        cfp_event.cfp.fields["track"]["visibility"] = "required"
        cfp_event.cfp.fields["abstract"]["visibility"] = "do_not_ask"
        cfp_event.cfp.save()
        cfp_track.requires_access_code = True
        cfp_track.save()
        cfp_other_track.requires_access_code = True
        cfp_other_track.save()
        cfp_access_code.tracks.add(cfp_track)
        cfp_access_code.submission_types.add(cfp_event.cfp.default_type)
        submission_question.tracks.add(cfp_track)

    _, info_url = start_wizard(client, cfp_event)

    # Without code — stays on info
    _, stay_url = _post_info(
        client, info_url, cfp_event, submission_type=sub_type, track=cfp_track.pk
    )
    assert "/info/" in stay_url

    # With code — proceeds
    code_url = info_url + "?access_code=" + cfp_access_code.code
    _, q_url = _post_info(
        client, code_url, cfp_event, submission_type=sub_type, track=cfp_track.pk
    )
    assert "/questions/" in q_url

    answer_data = {f"question_{submission_question.pk}": "42"}
    _, user_url = _post_questions(client, q_url, answer_data)
    _, profile_url = _register_user(client, user_url)
    _, final_url = _post_profile(client, profile_url)

    assert "/me/submissions/" in final_url
    _assert_submission(
        cfp_event, track=cfp_track, question=submission_question, abstract=None
    )


@pytest.mark.django_db
def test_e2e_access_code_bypasses_deadline(cfp_event, client, cfp_access_code):
    """With CfP closed, access code allows full submission flow."""
    with scopes_disabled():
        cfp_event.cfp.deadline = now() - dt.timedelta(days=1)
        cfp_event.cfp.save()

    _, info_url = start_wizard(client, cfp_event, access_code=cfp_access_code)
    assert "/info/" in info_url

    _, user_url = _post_info(client, info_url, cfp_event)
    _, profile_url = _register_user(client, user_url)
    _, final_url = _post_profile(client, profile_url)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        sub = Submission.objects.last()
        assert sub.access_code == cfp_access_code


@pytest.mark.django_db
def test_e2e_additional_speakers_send_invitations(cfp_event, client, cfp_user):
    """Additional speakers receive invitation emails alongside the confirmation."""
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_e2e_draft_invalid_info_stays_on_step(cfp_event, client, cfp_user):
    """Draft save with invalid info data stays on info step without creating a draft."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, title="", action="draft")
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/info/" in url
    with scope(event=cfp_event):
        assert Submission.all_objects.filter(state=SubmissionStates.DRAFT).count() == 0


@pytest.mark.django_db
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


@pytest.mark.django_db
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
def test_e2e_wizard_with_resource(
    cfp_event, client, cfp_user, resource_data, expect_link
):
    """Full wizard flow with a resource (link or file upload)."""
    with scopes_disabled():
        cfp_event.cfp.fields["resources"] = {"visibility": "optional"}
        cfp_event.cfp.save()
        sub_type = SubmissionType.objects.filter(event=cfp_event).first().pk

    if not expect_link:
        resource_data["resource"] = SimpleUploadedFile(
            "slides.pdf", b"fake pdf content", content_type="application/pdf"
        )

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event, title="Talk with resources", submission_type=sub_type)
    data["resource-TOTAL_FORMS"] = "1"
    for key, value in resource_data.items():
        data[f"resource-0-{key}"] = value
    _, profile_url = get_response_and_url(client, info_url, data=data)
    assert "/profile/" in profile_url

    _, final_url = _post_profile(client, profile_url)
    assert "/me/submissions/" in final_url

    with scope(event=cfp_event):
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


@pytest.mark.django_db
def test_e2e_wizard_resource_deleted_unsaved_form_ignored(cfp_event, client, cfp_user):
    """A resource form marked for deletion that was never saved is silently ignored."""
    with scopes_disabled():
        cfp_event.cfp.fields["resources"] = {"visibility": "optional"}
        cfp_event.cfp.save()

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event, title="Talk with deleted unsaved resource")
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

    with scope(event=cfp_event):
        sub = Submission.objects.last()
        assert sub.title == "Talk with deleted unsaved resource"
        assert sub.resources.count() == 1
        resource = sub.resources.first()
        assert resource.description == "Real resource"
        assert resource.link == "https://example.com/real"


@pytest.mark.django_db
def test_e2e_draft_with_resources_then_resume_and_submit(cfp_event, client, cfp_user):
    """Save draft with resources, resume, and complete – resources preserved."""
    with scopes_disabled():
        cfp_event.cfp.fields["resources"] = {"visibility": "optional"}
        cfp_event.cfp.save()

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event, title="Draft with resources", action="draft")
    data.update(
        {
            "resource-TOTAL_FORMS": "1",
            "resource-0-description": "Draft slides",
            "resource-0-link": "https://example.com/draft-slides",
            "resource-0-is_public": "on",
        }
    )
    get_response_and_url(client, info_url, data=data)

    with scope(event=cfp_event):
        sub = Submission.all_objects.filter(state=SubmissionStates.DRAFT).last()
        assert sub.resources.count() == 1
        code = sub.code
        resource_pk = sub.resources.first().pk

    # Resume the draft
    restart_url = f"/{cfp_event.slug}/submit/restart-{code}/"
    response, resume_url = get_response_and_url(client, restart_url, method="GET")
    content = response.content.decode()
    assert "Draft slides" in content
    assert "https://example.com/draft-slides" in content

    # Resubmit with existing resource
    data = info_data(cfp_event, title="Draft with resources")
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

    with scope(event=cfp_event):
        sub.refresh_from_db()
        assert sub.state == SubmissionStates.SUBMITTED
        assert sub.resources.count() == 1
        resource = sub.resources.first()
        assert resource.description == "Draft slides"
        assert resource.link == "https://example.com/draft-slides"


@pytest.mark.django_db
def test_e2e_submission_type_access_code(cfp_event, client, cfp_access_code):
    """Full flow with submission type requiring access code."""
    with scopes_disabled():
        sub_type = SubmissionType.objects.filter(event=cfp_event).first()
        sub_type.requires_access_code = True
        sub_type.save()
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


@pytest.mark.django_db
def test_e2e_wizard_with_tags(cfp_event, client):
    """Full wizard flow with public tags – private tags excluded."""
    with scopes_disabled():
        tag1 = TagFactory(event=cfp_event, tag="Python", is_public=True)
        tag2 = TagFactory(event=cfp_event, tag="Web", is_public=True)
        TagFactory(event=cfp_event, tag="Private", is_public=False)
        cfp_event.cfp.fields["tags"]["visibility"] = "optional"
        cfp_event.cfp.save()

    _, info_url = start_wizard(client, cfp_event)
    _, user_url = _post_info(client, info_url, cfp_event, tags=[tag1.pk, tag2.pk])
    _, profile_url = _register_user(client, user_url)
    _, final_url = _post_profile(client, profile_url)

    assert "/me/submissions/" in final_url
    sub = _assert_submission(cfp_event, tags=[tag1, tag2])
    _assert_speaker(sub)


@pytest.mark.django_db
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
