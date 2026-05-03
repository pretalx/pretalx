# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json
from urllib.parse import urlparse

import pytest
from django.core import mail as djmail
from django.http.request import QueryDict
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.submission.models import Submission, SubmissionStates
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from tests.cfp.views.conftest import get_response_and_url, info_data, start_wizard
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    SubmitterAccessCodeFactory,
    UserFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_submit_start_redirects_to_info_step(client, cfp_event):
    """GET /submit/ generates a tmpid and redirects to the info step."""
    response, url = start_wizard(client, cfp_event)

    assert response.status_code == 200
    assert "/info/" in url


def test_submit_start_preserves_query_params(client, cfp_event, cfp_track):
    sub_type = cfp_event.cfp.default_type
    params = QueryDict(f"track={cfp_track.pk}&submission_type={sub_type.pk}-slug")
    url = f"/{cfp_event.slug}/submit/?{params.urlencode()}"

    response, current_url = get_response_and_url(client, url, method="GET")

    parsed = urlparse(current_url)
    q = QueryDict(parsed.query)
    assert parsed.path.endswith("/info/")
    assert q["track"] == str(cfp_track.pk)
    assert q["submission_type"] == f"{sub_type.pk}-slug"


@pytest.mark.parametrize(
    "cfp_kwargs",
    (
        {"deadline": now() - dt.timedelta(days=1)},
        {"deadline": None, "opening": now() + dt.timedelta(days=1)},
    ),
    ids=["after_deadline", "before_opening"],
)
def test_wizard_cfp_closed_redirects(client, cfp_kwargs):
    event = EventFactory(**{f"cfp__{k}": v for k, v in cfp_kwargs.items()})
    user = UserFactory()
    client.force_login(user)

    response, url = start_wizard(client, event)

    assert "/info/" not in url


def test_wizard_access_code_bypasses_closed_cfp(client):
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=1))
    access_code = SubmitterAccessCodeFactory(event=event)

    response, url = start_wizard(client, event, access_code=access_code)

    assert "/info/" in url


def test_wizard_expired_access_code_rejected(client):
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=1))
    access_code = SubmitterAccessCodeFactory(
        event=event, valid_until=now() - dt.timedelta(hours=1)
    )

    response, url = start_wizard(client, event, access_code=access_code)

    assert "/info/" not in url


def test_wizard_missing_step_returns_404(client, cfp_event):
    _, info_url = start_wizard(client, cfp_event)

    response = client.get(info_url.replace("info", "wrooooong"))

    assert response.status_code == 404


def test_wizard_info_step_post_invalid_stays(client, cfp_event, cfp_user):
    """Posting invalid data (missing title) keeps user on info step."""
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event, title="")
    response, url = get_response_and_url(client, info_url, data=data)

    assert "/info/" in url


def test_wizard_review_questions_not_shown(client, cfp_event, cfp_user):
    with scopes_disabled():
        QuestionFactory(
            event=cfp_event,
            question="Reviewer only question",
            variant=QuestionVariant.STRING,
            target="reviewer",
            question_required=QuestionRequired.REQUIRED,
            position=4,
        )
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(cfp_event)
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/questions/" not in url
    assert "/profile/" in url


def test_wizard_additional_speaker_mail_fail_no_crash(client):
    """When custom SMTP is configured and fails, submission still succeeds."""
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        mail_settings={"smtp_use_custom": True},
    )
    user = UserFactory()
    djmail.outbox = []
    client.force_login(user)
    _, info_url = start_wizard(client, event)

    data = info_data(event, additional_speaker="fail@example.com")
    _, profile_url = get_response_and_url(client, info_url, data=data)
    profile_data = {"name": "Jane Doe", "biography": "bio"}
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=event):
        assert Submission.objects.count() == 1
    assert len(djmail.outbox) == 0


def test_wizard_draft_parks_additional_speakers(client, cfp_event, cfp_user):
    """Saving a wizard step as a draft must not send invitations — the
    addresses are parked on ``submission.draft_additional_speakers`` until
    the proposal is actually submitted."""
    djmail.outbox = []
    client.force_login(cfp_user)
    _, info_url = start_wizard(client, cfp_event)

    data = info_data(
        cfp_event,
        additional_speaker="park-me@example.com, also-me@example.com",
        action="draft",
    )
    response, _ = get_response_and_url(client, info_url, data=data)

    assert response.status_code == 200
    with scope(event=cfp_event):
        submission = Submission.all_objects.get(event=cfp_event)
    assert submission.state == SubmissionStates.DRAFT
    assert submission.draft_additional_speakers == [
        "park-me@example.com",
        "also-me@example.com",
    ]
    with scope(event=cfp_event):
        assert submission.invitations.count() == 0
    assert djmail.outbox == []


def test_wizard_dedraft_promotes_draft_additional_speakers(client, cfp_event, cfp_user):
    """Resuming a draft must repopulate the additional_speaker field from
    ``draft_additional_speakers`` so the speaker sees what they had entered,
    and on final submit those addresses are turned into real invitations."""
    djmail.outbox = []
    with scopes_disabled():
        draft = SubmissionFactory(
            event=cfp_event,
            state=SubmissionStates.DRAFT,
            draft_additional_speakers=["parked@example.com"],
        )
        speaker = SpeakerFactory(event=cfp_event, user=cfp_user)
        draft.speakers.add(speaker)
    client.force_login(cfp_user)

    restart_url = f"/{cfp_event.slug}/submit/restart-{draft.code}/"
    response, info_url = get_response_and_url(client, restart_url, method="GET")
    # The parked address must show up in the rendered form so the speaker
    # can see/edit it before re-submitting.
    assert b"parked@example.com" in response.content

    data = info_data(
        cfp_event, title=draft.title, additional_speaker="parked@example.com"
    )
    _, profile_url = get_response_and_url(client, info_url, data=data)
    profile_data = {"name": "Jane Doe", "biography": "bio"}
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        draft.refresh_from_db()
        assert draft.state == SubmissionStates.SUBMITTED
        assert draft.draft_additional_speakers == []
        invited = set(draft.invitations.values_list("email", flat=True))
    assert invited == {"parked@example.com"}
    recipients = [r for m in djmail.outbox for r in m.to]
    assert recipients.count("parked@example.com") == 1


def test_wizard_dedraft_skips_already_invited(client, cfp_event, cfp_user):
    """Dedrafting a submission whose draft already carried an invitation
    must not raise IntegrityError or send a duplicate mail when the same
    email is re-listed in ``additional_speaker``."""
    djmail.outbox = []
    with scopes_disabled():
        draft = SubmissionFactory(event=cfp_event, state=SubmissionStates.DRAFT)
        speaker = SpeakerFactory(event=cfp_event, user=cfp_user)
        draft.speakers.add(speaker)
        SubmissionInvitationFactory(submission=draft, email="existing@example.com")
    client.force_login(cfp_user)

    restart_url = f"/{cfp_event.slug}/submit/restart-{draft.code}/"
    _, info_url = get_response_and_url(client, restart_url, method="GET")
    assert "/info/" in info_url

    data = info_data(
        cfp_event,
        title=draft.title,
        additional_speaker="existing@example.com, fresh@example.com",
    )
    _, profile_url = get_response_and_url(client, info_url, data=data)
    profile_data = {"name": "Jane Doe", "biography": "bio"}
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=cfp_event):
        draft.refresh_from_db()
        assert draft.state == SubmissionStates.SUBMITTED
        invited = set(draft.invitations.values_list("email", flat=True))
    assert invited == {"existing@example.com", "fresh@example.com"}
    # The pre-existing invitation was created without sending and must not be
    # re-sent; the fresh one fires once.
    recipients = [r for m in djmail.outbox for r in m.to]
    assert recipients.count("fresh@example.com") == 1
    assert "existing@example.com" not in recipients


def test_wizard_dedraft_updates_existing_resource_in_place(client, cfp_user):
    """Editing an existing resource on a dedraft must update the row, not
    create a duplicate. The formset rebinds to the resource via the hidden
    id field, so the wizard's done() handler has to reuse the bound
    instance rather than always inserting a fresh row."""
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"resources": {"visibility": "optional"}},
    )
    with scopes_disabled():
        draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        speaker = SpeakerFactory(event=event, user=cfp_user)
        draft.speakers.add(speaker)
        resource = ResourceFactory(
            submission=draft,
            link="https://example.com/slides.pdf",
            description="Old description",
        )
    client.force_login(cfp_user)

    restart_url = f"/{event.slug}/submit/restart-{draft.code}/"
    _, info_url = get_response_and_url(client, restart_url, method="GET")

    data = info_data(event, title=draft.title)
    data.update(
        {
            "resource-TOTAL_FORMS": "1",
            "resource-INITIAL_FORMS": "1",
            "resource-0-id": str(resource.pk),
            "resource-0-description": "New description",
            "resource-0-link": "https://example.com/slides.pdf",
        }
    )
    _, profile_url = get_response_and_url(client, info_url, data=data)
    profile_data = {"name": "Jane Doe", "biography": "bio"}
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=event):
        draft.refresh_from_db()
        assert draft.state == SubmissionStates.SUBMITTED
        resources = list(draft.resources.all())
    assert len(resources) == 1
    assert resources[0].pk == resource.pk
    assert resources[0].description == "New description"


def test_wizard_submit_twice_no_duplicate_speaker_answers(client, cfp_event, cfp_user):
    with scopes_disabled():
        speaker_question = QuestionFactory(
            event=cfp_event,
            question="What is your favourite color?",
            variant=QuestionVariant.STRING,
            target="speaker",
            question_required=QuestionRequired.OPTIONAL,
            position=3,
        )
        sub_type = cfp_event.cfp.default_type_id
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


def test_wizard_required_avatar_upload(client, make_image):
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"avatar": {"visibility": "required"}},
    )
    user = UserFactory()
    client.force_login(user)
    _, info_url = start_wizard(client, event)
    data = info_data(event)
    _, profile_url = get_response_and_url(client, info_url, data=data)

    profile_data = {
        "name": "Jane Doe",
        "biography": "bio",
        "avatar_action": "upload",
        "avatar": make_image("avatar.png"),
    }
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=event):
        assert Submission.objects.count() == 1


def test_wizard_with_required_availabilities(client):
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"availabilities": {"visibility": "required"}},
    )

    _, info_url = start_wizard(client, event)
    data = info_data(event)
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
                "start": f"{event.date_from}T10:00:00.000Z",
                "end": f"{event.date_from}T18:00:00.000Z",
            }
        ],
        "event": {
            "timezone": str(event.timezone),
            "date_from": str(event.date_from),
            "date_to": str(event.date_to),
        },
    }
    profile_data = {
        "name": "Avail User",
        "biography": "bio",
        "availabilities": json.dumps(avail_data),
    }
    _, final_url = get_response_and_url(client, profile_url, data=profile_data)

    assert "/me/submissions/" in final_url
    with scope(event=event):
        assert Submission.objects.count() == 1


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


def test_wizard_with_resources_required_blocks_without(client):
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"resources": {"visibility": "required"}},
    )
    user = UserFactory()
    client.force_login(user)
    _, info_url = start_wizard(client, event)
    data = info_data(event)
    _, url = get_response_and_url(client, info_url, data=data)

    assert "/info/" in url

    # Providing a resource proceeds past info
    data = info_data(event)
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


def test_wizard_does_not_leak_other_submissions_resources(client):
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"resources": {"visibility": "optional"}},
    )
    access_code = SubmitterAccessCodeFactory(event=event)
    with scopes_disabled():
        other_submission = SubmissionFactory(event=event, title="Other talk")
        ResourceFactory(
            submission=other_submission,
            link="https://leak.example.com/secret.pdf",
            description="Slides from other submission",
        )

    response, info_url = start_wizard(client, event, access_code=access_code)
    assert "/info/" in info_url
    content = response.content.decode()
    assert "Slides from other submission" not in content
    assert "https://leak.example.com/secret.pdf" not in content


def test_wizard_resource_link_preserved_on_back_navigation(client):
    event = EventFactory(
        cfp__deadline=now() + dt.timedelta(days=30),
        cfp__fields={"resources": {"visibility": "optional"}},
    )
    user = UserFactory()
    client.force_login(user)
    _, info_url = start_wizard(client, event)
    data = info_data(event, title="Talk with resource")
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
