import datetime as dt
import json
from urllib.parse import urlparse

import pytest
from django.core import mail as djmail
from django.http.request import QueryDict
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.submission.models import Submission, SubmissionStates, SubmissionType
from tests.cfp.views.conftest import get_response_and_url, info_data, start_wizard
from tests.factories import TagFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_submit_start_redirects_to_info_step(client, cfp_event):
    """GET /submit/ generates a tmpid and redirects to the info step."""
    response, url = start_wizard(client, cfp_event)

    assert response.status_code == 200
    assert "/info/" in url


@pytest.mark.django_db
def test_submit_start_preserves_query_params(client, cfp_event, cfp_track):
    """GET /submit/?track=X preserves query parameters through the redirect."""
    with scopes_disabled():
        sub_type = SubmissionType.objects.filter(event=cfp_event).first()
    params = QueryDict(f"track={cfp_track.pk}&submission_type={sub_type.pk}-slug")
    url = f"/{cfp_event.slug}/submit/?{params.urlencode()}"

    response, current_url = get_response_and_url(client, url, method="GET")

    parsed = urlparse(current_url)
    q = QueryDict(parsed.query)
    assert parsed.path.endswith("/info/")
    assert q["track"] == str(cfp_track.pk)
    assert q["submission_type"] == f"{sub_type.pk}-slug"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("cfp_attrs"),
    ({"deadline": "past"}, {"deadline": None, "opening": "future"}),
    ids=["after_deadline", "before_opening"],
)
def test_wizard_cfp_closed_redirects(client, cfp_event, cfp_user, cfp_attrs):
    """When CfP is not open (past deadline or before opening), wizard redirects away."""
    sentinels = {
        "past": lambda: now() - dt.timedelta(days=1),
        "future": lambda: now() + dt.timedelta(days=1),
    }
    with scopes_disabled():
        for attr, value in cfp_attrs.items():
            setattr(
                cfp_event.cfp, attr, sentinels[value]() if value in sentinels else value
            )
        cfp_event.cfp.save()
    client.force_login(cfp_user)

    response, url = start_wizard(client, cfp_event)

    assert "/info/" not in url


@pytest.mark.django_db
def test_wizard_access_code_bypasses_closed_cfp(client, cfp_event, cfp_access_code):
    """A valid access code allows submission even when CfP deadline has passed."""
    with scopes_disabled():
        cfp_event.cfp.deadline = now() - dt.timedelta(days=1)
        cfp_event.cfp.save()

    response, url = start_wizard(client, cfp_event, access_code=cfp_access_code)

    assert "/info/" in url


@pytest.mark.django_db
def test_wizard_expired_access_code_rejected(client, cfp_event, cfp_access_code):
    """An expired access code does not bypass the closed CfP."""
    with scopes_disabled():
        cfp_event.cfp.deadline = now() - dt.timedelta(days=1)
        cfp_event.cfp.save()
        cfp_access_code.valid_until = now() - dt.timedelta(hours=1)
        cfp_access_code.save()

    response, url = start_wizard(client, cfp_event, access_code=cfp_access_code)

    assert "/info/" not in url


@pytest.mark.django_db
def test_wizard_missing_step_returns_404(client, cfp_event):
    """Requesting a non-existent step identifier returns 404."""
    _, info_url = start_wizard(client, cfp_event)

    response = client.get(info_url.replace("info", "wrooooong"))

    assert response.status_code == 404


@pytest.mark.django_db
def test_wizard_info_step_get_renders_form(client, cfp_event):
    """GET on the info step renders the submission form."""
    _, info_url = start_wizard(client, cfp_event)

    response = client.get(info_url)

    assert response.status_code == 200
    assert "form" in response.context


@pytest.mark.django_db
def test_wizard_info_step_post_valid_advances(client, cfp_event, cfp_user):
    """Posting valid data on the info step advances to the next step."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    response, url = get_response_and_url(client, info_url, data=data)

    # Authenticated user: should skip user step, go to questions or profile
    assert "/info/" not in url


@pytest.mark.django_db
def test_wizard_info_step_post_invalid_stays(client, cfp_event, cfp_user):
    """Posting invalid data (missing title) keeps user on info step."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, title="")
    response, url = get_response_and_url(client, info_url, data=data)

    assert "/info/" in url


@pytest.mark.django_db
def test_wizard_questions_step_shown_when_questions_exist(
    client, cfp_event, cfp_user, submission_question
):
    """Questions step is shown when the event has submission questions."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/questions/" in url


@pytest.mark.django_db
def test_wizard_questions_step_skipped_without_questions(client, cfp_event, cfp_user):
    """Questions step is skipped when no questions exist."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/questions/" not in url
    assert "/profile/" in url


@pytest.mark.django_db
def test_wizard_review_questions_not_shown(
    client, cfp_event, cfp_user, review_question
):
    """Reviewer-only questions do not cause the questions step to appear."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/questions/" not in url
    assert "/profile/" in url


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("logged_in", "expected_step"),
    ((False, "user"), (True, "profile")),
    ids=["anonymous_sees_user_step", "authenticated_skips_user_step"],
)
def test_wizard_user_step_visibility(
    client, cfp_event, cfp_user, logged_in, expected_step
):
    """User step shown for anonymous, skipped for authenticated users."""
    if logged_in:
        client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    _, url = get_response_and_url(client, info_url, data=data)

    assert f"/{expected_step}/" in url


@pytest.mark.django_db
def test_wizard_logged_in_user_creates_submission(client, cfp_event, cfp_user):
    """A logged-in user can complete the wizard, creating a submission and sending confirmation."""
    djmail.outbox = []
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    _, profile_url = get_response_and_url(client, info_url, data=data)
    assert "/profile/" in profile_url

    profile_data = {"name": "Jane Doe", "biography": "l337 hax0r"}
    response, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        sub = Submission.objects.last()
        assert sub.title == "Submission title"
        assert sub.submission_type is not None
        assert sub.content_locale == "en"
        assert sub.description == "Description"
        assert sub.abstract == "Abstract"
        assert sub.notes == "Notes"
        assert sub.state == SubmissionStates.SUBMITTED
        speaker = sub.speakers.first()
        assert speaker.user == cfp_user
        assert speaker.name == "Jane Doe"
        assert speaker.biography == "l337 hax0r"
    assert len(djmail.outbox) == 1
    assert sub.title in djmail.outbox[0].subject
    assert cfp_user.email in djmail.outbox[0].to


@pytest.mark.django_db
def test_wizard_with_questions_saves_answers(
    client, cfp_event, cfp_user, submission_question
):
    """Wizard saves question answers when questions step is present."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    _, q_url = get_response_and_url(client, info_url, data=data)
    assert "/questions/" in q_url

    answer_data = {f"question_{submission_question.pk}": "42"}
    _, profile_url = get_response_and_url(client, q_url, data=answer_data)
    assert "/profile/" in profile_url

    profile_data = {"name": "Jane Doe", "biography": "bio"}
    get_response_and_url(client, profile_url, data=profile_data)

    with scope(event=cfp_event):
        sub = Submission.objects.last()
        answer = sub.answers.first()
        assert answer is not None
        assert answer.question == submission_question
        assert answer.answer == "42"


@pytest.mark.django_db
def test_wizard_new_user_registration_creates_submission(client, cfp_event):
    """An anonymous user can register and complete a submission."""
    djmail.outbox = []
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    _, user_url = get_response_and_url(client, info_url, data=data)
    assert "/user/" in user_url

    user_data = {
        "register_name": "newuser@example.com",
        "register_email": "newuser@example.com",
        "register_password": "testpassw0rd!",
        "register_password_repeat": "testpassw0rd!",
    }
    _, profile_url = get_response_and_url(client, user_url, data=user_data)
    assert "/profile/" in profile_url

    profile_data = {"name": "New Speaker", "biography": "bio"}
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        sub = Submission.objects.last()
        assert sub.title == "Submission title"
        assert sub.state == SubmissionStates.SUBMITTED
        speaker = sub.speakers.get(user__email="newuser@example.com")
        assert speaker.name == "New Speaker"


@pytest.mark.django_db
def test_wizard_existing_user_login_creates_submission(client, cfp_event, cfp_user):
    """An anonymous user who logs in via the wizard completes the submission."""
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    _, user_url = get_response_and_url(client, info_url, data=data)
    assert "/user/" in user_url

    user_data = {"login_email": cfp_user.email, "login_password": "testpassw0rd!"}
    _, profile_url = get_response_and_url(client, user_url, data=user_data)
    assert "/profile/" in profile_url

    profile_data = {"name": "Jane Doe", "biography": "bio"}
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        sub = Submission.objects.last()
        assert sub.speakers.filter(user=cfp_user).exists()


@pytest.mark.django_db
def test_wizard_with_required_track(client, cfp_event, cfp_track, cfp_other_track):
    """When tracks are required, the submission is saved with the chosen track."""
    with scopes_disabled():
        cfp_event.cfp.fields["track"]["visibility"] = "required"
        cfp_event.cfp.save()

    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event, track=cfp_track.pk)
    _, user_url = get_response_and_url(client, info_url, data=data)
    user_data = {
        "register_name": "trackuser@example.com",
        "register_email": "trackuser@example.com",
        "register_password": "testpassw0rd!",
        "register_password_repeat": "testpassw0rd!",
    }
    _, profile_url = get_response_and_url(client, user_url, data=user_data)
    profile_data = {"name": "Track User", "biography": "bio"}
    get_response_and_url(client, profile_url, data=profile_data)

    with scope(event=cfp_event):
        sub = Submission.objects.last()
        assert sub.track == cfp_track


@pytest.mark.django_db
def test_wizard_with_tags(client, cfp_event, cfp_user):
    """Optional tags are saved when provided in the info step."""
    with scopes_disabled():
        tag1 = TagFactory(event=cfp_event, tag="Python", is_public=True)
        tag2 = TagFactory(event=cfp_event, tag="Web", is_public=True)
        TagFactory(event=cfp_event, tag="Private", is_public=False)
        cfp_event.cfp.fields["tags"]["visibility"] = "optional"
        cfp_event.cfp.save()

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event, tags=[tag1.pk, tag2.pk])
    _, profile_url = get_response_and_url(client, info_url, data=data)
    profile_data = {"name": "Tag User", "biography": "bio"}
    get_response_and_url(client, profile_url, data=profile_data)

    with scope(event=cfp_event):
        sub = Submission.objects.last()
        assert set(sub.tags.all()) == {tag1, tag2}


@pytest.mark.django_db
def test_wizard_additional_speakers_send_invitations(client, cfp_event, cfp_user):
    """Additional speaker emails trigger invitation emails."""
    djmail.outbox = []
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(
        cfp_event, additional_speaker="speaker2@example.com,speaker3@example.com"
    )
    _, profile_url = get_response_and_url(client, info_url, data=data)
    profile_data = {"name": "Jane Doe", "biography": "bio"}
    get_response_and_url(client, profile_url, data=profile_data)

    # 1 confirmation + 2 invite emails
    assert len(djmail.outbox) == 3
    all_recipients = {mail.to[0] for mail in djmail.outbox}
    assert "speaker2@example.com" in all_recipients
    assert "speaker3@example.com" in all_recipients


@pytest.mark.django_db
def test_wizard_additional_speaker_mail_fail_no_crash(client, cfp_event, cfp_user):
    """When custom SMTP is configured and fails, submission still succeeds."""
    with scopes_disabled():
        cfp_event.mail_settings["smtp_use_custom"] = True
        cfp_event.save()
    djmail.outbox = []
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, additional_speaker="fail@example.com")
    _, profile_url = get_response_and_url(client, info_url, data=data)
    profile_data = {"name": "Jane Doe", "biography": "bio"}
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        assert Submission.objects.count() == 1
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_wizard_track_access_code_required(
    client, cfp_event, cfp_access_code, cfp_track, cfp_other_track
):
    """Track requiring access code: submission fails without code, succeeds with it."""
    with scopes_disabled():
        cfp_event.cfp.fields["track"]["visibility"] = "required"
        cfp_event.cfp.fields["abstract"]["visibility"] = "do_not_ask"
        cfp_event.cfp.save()
        cfp_track.requires_access_code = True
        cfp_track.save()
        cfp_other_track.requires_access_code = True
        cfp_other_track.save()
        cfp_access_code.tracks.add(cfp_track)
        cfp_access_code.submission_types.add(cfp_event.cfp.default_type)

    _, info_url = start_wizard(client, cfp_event)
    # Attempt without code — stays on info
    data = info_data(cfp_event, track=cfp_track.pk)
    _, url = get_response_and_url(client, info_url, data=data)
    assert "/info/" in url

    # With access code — proceeds
    data = info_data(cfp_event, track=cfp_track.pk)
    _, url = get_response_and_url(
        client, info_url + "?access_code=" + cfp_access_code.code, data=data
    )
    assert "/info/" not in url


@pytest.mark.django_db
def test_wizard_submission_type_access_code(client, cfp_event, cfp_access_code):
    """Submission type requiring access code: fails without code, succeeds with it."""
    with scopes_disabled():
        sub_type = SubmissionType.objects.filter(event=cfp_event).first()
        sub_type.requires_access_code = True
        sub_type.save()
        cfp_access_code.submission_types.add(sub_type)

    _, info_url = start_wizard(client, cfp_event)
    # Without code — stays on info
    data = info_data(cfp_event, submission_type=sub_type.pk)
    _, url = get_response_and_url(client, info_url, data=data)
    assert "/info/" in url

    # With code — proceeds
    data = info_data(cfp_event, submission_type=sub_type.pk)
    _, url = get_response_and_url(
        client, info_url + "?access_code=" + cfp_access_code.code, data=data
    )
    assert "/info/" not in url


@pytest.mark.django_db
def test_wizard_mail_on_new_submission_sends_orga_email(client, cfp_event, cfp_user):
    """When mail_on_new_submission is enabled, both user and orga get emails."""
    with scopes_disabled():
        cfp_event.mail_settings["mail_on_new_submission"] = True
        cfp_event.save()
    djmail.outbox = []
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event)
    _, profile_url = get_response_and_url(client, info_url, data=data)
    profile_data = {"name": "Jane Doe", "biography": "bio"}
    get_response_and_url(client, profile_url, data=profile_data)

    assert len(djmail.outbox) == 2


@pytest.mark.django_db
def test_wizard_submit_twice_no_duplicate_speaker_answers(
    client, cfp_event, cfp_user, speaker_question
):
    """Submitting twice with the same speaker question does not duplicate answers."""
    with scopes_disabled():
        sub_type = SubmissionType.objects.filter(event=cfp_event).first().pk
        answer_data = {f"question_{speaker_question.pk}": "green"}

    client.force_login(cfp_user)
    for _ in range(2):
        _, info_url = start_wizard(client, cfp_event)
        data = info_data(cfp_event, submission_type=sub_type)
        _, q_url = get_response_and_url(client, info_url, data=data)
        _, profile_url = get_response_and_url(client, q_url, data=answer_data)
        profile_data = {"name": "Jane Doe", "biography": "bio"}
        get_response_and_url(client, profile_url, data=profile_data)

    with scope(event=cfp_event):
        assert cfp_event.submissions.count() == 2
        assert speaker_question.answers.count() == 1


@pytest.mark.django_db
def test_wizard_required_avatar_upload(client, cfp_event, cfp_user, make_image):
    """When avatar is required, uploading an avatar completes the wizard."""
    with scopes_disabled():
        cfp_event.cfp.fields["avatar"] = {"visibility": "required"}
        cfp_event.cfp.save()

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event)
    _, profile_url = get_response_and_url(client, info_url, data=data)

    profile_data = {
        "name": "Jane Doe",
        "biography": "bio",
        "avatar_action": "upload",
        "avatar": make_image("avatar.png"),
    }
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        assert Submission.objects.count() == 1


@pytest.mark.django_db
def test_wizard_with_required_availabilities(client, cfp_event):
    """Submitting with required availabilities creates a valid submission."""
    with scopes_disabled():
        cfp_event.cfp.fields["availabilities"]["visibility"] = "required"
        cfp_event.cfp.save()

    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event)
    _, user_url = get_response_and_url(client, info_url, data=data)
    user_data = {
        "register_name": "avail@example.com",
        "register_email": "avail@example.com",
        "register_password": "testpassw0rd!",
        "register_password_repeat": "testpassw0rd!",
    }
    _, profile_url = get_response_and_url(client, user_url, data=user_data)

    avail_data = {
        "availabilities": [
            {
                "start": f"{cfp_event.date_from}T10:00:00.000Z",
                "end": f"{cfp_event.date_from}T18:00:00.000Z",
            }
        ],
        "event": {
            "timezone": str(cfp_event.timezone),
            "date_from": str(cfp_event.date_from),
            "date_to": str(cfp_event.date_to),
        },
    }
    profile_data = {
        "name": "Avail User",
        "biography": "bio",
        "availabilities": json.dumps(avail_data),
    }
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        assert Submission.objects.count() == 1


@pytest.mark.django_db
def test_submit_restart_loads_draft(client, cfp_event, cfp_user):
    """SubmitRestartView stores the draft code in session and redirects to info."""
    client.force_login(cfp_user)
    # First create a draft
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event, title="Draft Talk", action="draft")
    _, final_url = get_response_and_url(client, info_url, data=data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        draft = Submission.all_objects.filter(state=SubmissionStates.DRAFT).last()
        assert draft is not None
        code = draft.code

    # Now restart
    restart_url = f"/{cfp_event.slug}/submit/restart-{code}/"
    response, url = get_response_and_url(client, restart_url, method="GET")

    assert "/info/" in url
    content = response.content.decode()
    assert "Draft Talk" in content


@pytest.mark.django_db
def test_wizard_draft_save_with_valid_data(client, cfp_event, cfp_user):
    """Saving a draft with valid data creates a DRAFT submission."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, title="My Draft", action="draft")
    _, final_url = get_response_and_url(client, info_url, data=data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        draft = Submission.all_objects.filter(state=SubmissionStates.DRAFT).last()
        assert draft is not None
        assert draft.title == "My Draft"


@pytest.mark.django_db
def test_wizard_draft_invalid_data_stays_on_step(client, cfp_event, cfp_user):
    """Saving a draft with invalid data (missing title) stays on the info step."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, title="", action="draft")
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/info/" in url
    with scope(event=cfp_event):
        assert Submission.all_objects.filter(state=SubmissionStates.DRAFT).count() == 0


@pytest.mark.django_db
def test_wizard_draft_anonymous_redirects_to_user_step(client, cfp_event):
    """An anonymous user saving a draft is redirected to the user step with draft=1."""
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, title="Anon Draft", action="draft")
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/user/" in url
    assert "draft=1" in url


@pytest.mark.django_db
def test_wizard_draft_anonymous_login_saves_draft(client, cfp_event, cfp_user):
    """Anonymous user: draft on info → login on user step → draft saved."""
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, title="Anon Draft", action="draft")
    _, user_url = get_response_and_url(client, info_url, data=data)
    assert "/user/" in user_url
    assert "draft=1" in user_url

    user_data = {"login_email": cfp_user.email, "login_password": "testpassw0rd!"}
    _, final_url = get_response_and_url(client, user_url, data=user_data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        draft = Submission.all_objects.filter(state=SubmissionStates.DRAFT).last()
        assert draft is not None
        assert draft.title == "Anon Draft"


@pytest.mark.django_db
def test_wizard_draft_invalid_profile_stays_on_step(client, cfp_event, cfp_user):
    """Saving a draft with invalid profile data (missing name) stays on profile step."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, title="Draft Talk")
    _, profile_url = get_response_and_url(client, info_url, data=data)
    assert "/profile/" in profile_url

    profile_data = {"biography": "bio", "action": "draft"}
    _, url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/profile/" in url
    with scope(event=cfp_event):
        assert Submission.all_objects.filter(state=SubmissionStates.DRAFT).count() == 0


@pytest.mark.django_db
def test_wizard_with_resource_link(client, cfp_event, cfp_user):
    """Resources with links are saved on the submission."""
    with scopes_disabled():
        cfp_event.cfp.fields["resources"] = {"visibility": "optional"}
        cfp_event.cfp.save()

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event, title="Talk with resource")
    data.update(
        {
            "resource-TOTAL_FORMS": "1",
            "resource-0-description": "My slides",
            "resource-0-link": "https://example.com/slides.pdf",
            "resource-0-is_public": "on",
        }
    )
    _, profile_url = get_response_and_url(client, info_url, data=data)
    assert "/profile/" in profile_url

    profile_data = {"name": "Jane Doe", "biography": "bio"}
    get_response_and_url(client, profile_url, data=profile_data)

    with scope(event=cfp_event):
        sub = Submission.objects.last()
        assert sub.resources.count() == 1
        resource = sub.resources.first()
        assert resource.description == "My slides"
        assert resource.link == "https://example.com/slides.pdf"
        assert resource.is_public is True


@pytest.mark.django_db
def test_wizard_with_resources_optional_none_provided(client, cfp_event, cfp_user):
    """When resources are optional, submitting without resources succeeds."""
    with scopes_disabled():
        cfp_event.cfp.fields["resources"] = {"visibility": "optional"}
        cfp_event.cfp.save()

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event)
    _, profile_url = get_response_and_url(client, info_url, data=data)
    profile_data = {"name": "Jane Doe", "biography": "bio"}
    get_response_and_url(client, profile_url, data=profile_data)

    with scope(event=cfp_event):
        sub = Submission.objects.last()
        assert sub.resources.count() == 0


@pytest.mark.django_db
def test_wizard_with_resources_required_blocks_without(client, cfp_event, cfp_user):
    """When resources are required, submitting without blocks at info step."""
    with scopes_disabled():
        cfp_event.cfp.fields["resources"] = {"visibility": "required"}
        cfp_event.cfp.save()

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event)
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/info/" in url

    # Providing a resource proceeds past info
    data = info_data(cfp_event)
    data.update(
        {
            "resource-TOTAL_FORMS": "1",
            "resource-0-description": "Required resource",
            "resource-0-link": "https://example.com/required",
            "resource-0-is_public": "on",
        }
    )
    _, url = get_response_and_url(client, info_url, data=data)
    assert "/profile/" in url


@pytest.mark.django_db
def test_wizard_resource_link_preserved_on_back_navigation(client, cfp_event, cfp_user):
    """Navigating back to the info step preserves resource data."""
    with scopes_disabled():
        cfp_event.cfp.fields["resources"] = {"visibility": "optional"}
        cfp_event.cfp.save()

    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)
    data = info_data(cfp_event, title="Talk with resource")
    data.update(
        {
            "resource-TOTAL_FORMS": "1",
            "resource-0-description": "My slides",
            "resource-0-link": "https://example.com/slides.pdf",
            "resource-0-is_public": "on",
        }
    )
    _, profile_url = get_response_and_url(client, info_url, data=data)
    assert "/profile/" in profile_url

    # Navigate back
    response, back_url = get_response_and_url(client, info_url, method="GET")
    assert "/info/" in back_url
    content = response.content.decode()
    assert "My slides" in content
    assert "https://example.com/slides.pdf" in content


@pytest.mark.django_db
def test_wizard_draft_with_resources(client, cfp_event, cfp_user):
    """Saving a draft preserves resource data."""
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
    _, final_url = get_response_and_url(client, info_url, data=data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        sub = Submission.all_objects.filter(state=SubmissionStates.DRAFT).last()
        assert sub.title == "Draft with resources"
        assert sub.resources.count() == 1
        resource = sub.resources.first()
        assert resource.description == "Draft slides"
        assert resource.link == "https://example.com/draft-slides"


@pytest.mark.django_db
def test_wizard_draft_resources_shown_on_resume(client, cfp_event, cfp_user):
    """Resuming a draft shows its existing resources."""
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
        code = sub.code

    restart_url = f"/{cfp_event.slug}/submit/restart-{code}/"
    response, url = get_response_and_url(client, restart_url, method="GET")

    assert "/info/" in url
    content = response.content.decode()
    assert "Draft slides" in content
    assert "https://example.com/draft-slides" in content
