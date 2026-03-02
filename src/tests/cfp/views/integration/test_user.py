# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SubmissionError
from pretalx.mail.models import QueuedMailStates
from pretalx.submission.models import Submission, SubmissionInvitation, SubmissionStates
from pretalx.submission.signals import before_submission_state_change
from tests.factories import (
    EventFactory,
    QuestionFactory,
    QueuedMailFactory,
    ResourceFactory,
    ReviewFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TagFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def submission_with_speaker(event):
    """A submitted submission with one speaker on a public event."""
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
    )
    submission.speakers.add(speaker)
    return submission


@pytest.fixture
def speaker_client(client, submission_with_speaker):
    """A logged-in client for the speaker on submission_with_speaker."""
    with scopes_disabled():
        user = submission_with_speaker.speakers.first().user
    client.force_login(user)
    return client


def _edit_form_data(submission, **overrides):
    """Build the standard POST data for the submission edit form."""
    data = {
        "title": submission.title,
        "submission_type": submission.submission_type.pk,
        "content_locale": submission.content_locale,
        "description": submission.description or "",
        "abstract": submission.abstract or "",
        "notes": submission.notes or "",
        "slot_count": submission.slot_count,
        "resource-TOTAL_FORMS": 0,
        "resource-INITIAL_FORMS": 0,
        "resource-MIN_NUM_FORMS": 0,
        "resource-MAX_NUM_FORMS": 1000,
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("item_count", (1, 3))
def test_submissions_list_view_shows_submissions(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submissions = SubmissionFactory.create_batch(
            item_count, event=event, state=SubmissionStates.SUBMITTED
        )
        for sub in submissions:
            sub.speakers.add(speaker)
    client.force_login(speaker.user)

    with django_assert_num_queries(12):
        response = client.get(event.urls.user_submissions, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    for sub in submissions:
        assert sub.title in content


def test_submissions_list_view_does_not_show_other_users_submissions(
    client, speaker_client, submission_with_speaker, event
):
    submission = submission_with_speaker
    with scopes_disabled():
        other_sub = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_sub.speakers.add(other_speaker)

    response = speaker_client.get(event.urls.user_submissions, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert submission.title in content
    assert other_sub.title not in content


def test_submissions_list_view_shows_drafts(client, event):
    """Submission list shows draft submissions separately."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        draft.speakers.add(speaker)
    client.force_login(speaker.user)

    response = client.get(event.urls.user_submissions, follow=True)

    assert response.status_code == 200
    assert draft.title in response.content.decode()


def test_submissions_list_view_shows_speaker_information(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        info = SpeakerInformationFactory(event=event, target_group="submitters")
    client.force_login(speaker.user)

    response = client.get(event.urls.user_submissions, follow=True)

    assert response.status_code == 200
    assert str(info.title) in response.content.decode()


def test_submissions_edit_view_shows_submission(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker

    response = speaker_client.get(submission.urls.user_base, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


def test_submissions_edit_view_can_edit_title(speaker_client, submission_with_speaker):
    submission = submission_with_speaker
    data = _edit_form_data(submission, title="A Completely New Title")

    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.title == "A Completely New Title"


def test_submissions_edit_view_logs_changes(speaker_client, submission_with_speaker):
    """Editing a submission creates a single consolidated log entry including
    both field changes and question answer changes."""
    submission = submission_with_speaker
    with scopes_disabled():
        question = QuestionFactory(
            event=submission.event,
            target="submission",
            variant="number",
            question_required="optional",
        )
        old_title = submission.title
        log_count = submission.logged_actions().count()
    data = _edit_form_data(
        submission, title="Logged Title Change", **{f"question_{question.pk}": "50"}
    )

    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.title == "Logged Title Change"
        logs = submission.logged_actions()
        assert logs.count() == log_count + 1
        update_log = logs.filter(action_type="pretalx.submission.update").first()
        assert update_log
        assert update_log.changes["title"]["old"] == old_title
        assert update_log.changes["title"]["new"] == "Logged Title Change"
        question_key = f"question-{question.pk}"
        assert update_log.changes[question_key]["old"] is None
        assert update_log.changes[question_key]["new"] == "50"


def test_submissions_edit_view_with_resources(speaker_client, submission_with_speaker):
    """Speaker can add, update, and delete resources via the edit form."""
    submission = submission_with_speaker
    with scopes_disabled():
        resource1 = ResourceFactory(submission=submission)
        resource2 = ResourceFactory(submission=submission)
        new_file = SimpleUploadedFile("newfile.txt", b"new_file_content")
    data = _edit_form_data(
        submission,
        **{
            "resource-0-id": resource1.id,
            "resource-0-description": "Updated description",
            "resource-0-link": resource1.link,
            "resource-1-id": resource2.id,
            "resource-1-DELETE": True,
            "resource-1-description": resource2.description or "",
            "resource-1-link": resource2.link,
            "resource-2-id": "",
            "resource-2-description": "brand new resource",
            "resource-2-resource": new_file,
            "resource-TOTAL_FORMS": 3,
            "resource-INITIAL_FORMS": 2,
        },
    )

    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.resources.count() == 2
        resource1.refresh_from_db()
        assert resource1.description == "Updated description"
        assert not submission.resources.filter(pk=resource2.pk).exists()
        new_resource = submission.resources.exclude(pk=resource1.pk).first()
        assert new_resource.description == "brand new resource"
        assert new_resource.resource.read() == b"new_file_content"


def test_submissions_edit_view_orga_redirected_to_orga_page(
    client, submission_with_speaker, event
):
    """Organisers who are not speakers get redirected to the orga view."""
    submission = submission_with_speaker
    with scopes_disabled():
        orga_user = UserFactory()
        team = TeamFactory(organiser=event.organiser, all_events=True)
        team.members.add(orga_user)
    client.force_login(orga_user)

    response = client.get(submission.urls.user_base, follow=False)

    assert response.status_code == 302
    assert response.url == submission.orga_urls.base


def test_submissions_edit_view_cannot_edit_rejected_submission(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.reject()
    client.force_login(speaker.user)
    original_title = submission.title
    data = _edit_form_data(submission, title="Should Not Change")

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.title == original_title


def test_submissions_edit_view_draft_still_editable_when_feature_disabled(client):
    event = EventFactory(feature_flags={"speakers_can_edit_submissions": False})
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.DRAFT, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, title="Changed Draft Title")

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.title == "Changed Draft Title"


def test_submissions_edit_view_can_edit_submission_type(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
        new_type = SubmissionTypeFactory(event=event, name="Other", default_duration=13)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, submission_type=new_type.pk)

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.submission_type == new_type


def test_submissions_edit_view_cannot_edit_submission_type_after_acceptance(
    client, event
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
        new_type = SubmissionTypeFactory(event=event, name="Other", default_duration=13)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, submission_type=new_type.pk)

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.submission_type != new_type


def test_submissions_edit_view_can_edit_slot_count(client):
    event = EventFactory(feature_flags={"present_multiple_times": True})
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, slot_count=13)

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.slot_count == 13


def test_submissions_edit_view_tags_shown_when_public(client):
    with scopes_disabled():
        event = EventFactory(cfp__fields={"tags": {"visibility": "optional"}})
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        TagFactory(tag="public-tag", event=event, is_public=True)
        TagFactory(tag="private-tag", event=event, is_public=False)
    client.force_login(speaker.user)

    response = client.get(submission.urls.user_base, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "public-tag" in content
    assert "private-tag" not in content


def test_submissions_edit_view_private_tags_preserved_on_save(client):
    """Private tags assigned by organisers are preserved when speaker edits."""
    with scopes_disabled():
        event = EventFactory(
            feature_flags={"speakers_can_edit_submissions": True},
            cfp__fields={"tags": {"visibility": "optional"}},
        )
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
        public_tag = TagFactory(tag="public-tag", event=event, is_public=True)
        private_tag = TagFactory(tag="private-tag", event=event, is_public=False)
        submission.tags.add(public_tag, private_tag)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert public_tag not in submission.tags.all()
        assert private_tag in submission.tags.all()


def test_submissions_edit_view_tags_validation_min(client):
    with scopes_disabled():
        event = EventFactory(
            cfp__fields={"tags": {"visibility": "required", "min": 2, "max": None}}
        )
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        tag1 = TagFactory(tag="tag1", event=event, is_public=True)
        TagFactory(tag="tag2", event=event, is_public=True)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[tag1.pk])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "at least 2 tags" in response.content.decode().lower()


def test_submissions_edit_view_tags_validation_max(client):
    with scopes_disabled():
        event = EventFactory(
            cfp__fields={"tags": {"visibility": "optional", "min": None, "max": 2}}
        )
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        tag1 = TagFactory(tag="tag1", event=event, is_public=True)
        tag2 = TagFactory(tag="tag2", event=event, is_public=True)
        tag3 = TagFactory(tag="tag3", event=event, is_public=True)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[tag1.pk, tag2.pk, tag3.pk])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "at most 2 tags" in response.content.decode().lower()


def test_submissions_withdraw_view_withdraws_submitted(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker
    djmail.outbox = []

    response = speaker_client.post(submission.urls.withdraw, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.WITHDRAWN
    assert len(djmail.outbox) == 0


def test_submissions_withdraw_view_sends_orga_email_for_accepted(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
    client.force_login(speaker.user)
    djmail.outbox = []

    response = client.post(submission.urls.withdraw, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.WITHDRAWN
    assert len(djmail.outbox) == 1


def test_submissions_withdraw_view_cannot_withdraw_non_withdrawable(client, event):
    """Cannot withdraw a confirmed submission."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
        submission.confirm()
    client.force_login(speaker.user)

    response = client.post(submission.urls.withdraw, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.CONFIRMED


def test_submission_confirm_view_confirms_accepted(client):
    with scopes_disabled():
        event = EventFactory(cfp__fields={"availabilities": {"visibility": "optional"}})
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
    client.force_login(speaker.user)

    response = client.post(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.CONFIRMED


def test_submission_confirm_view_cannot_confirm_non_accepted(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    response = client.post(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.SUBMITTED


def test_submission_confirm_view_reconfirm_already_confirmed(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
        submission.confirm()
    client.force_login(speaker.user)

    response = client.post(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.CONFIRMED


def test_submission_confirm_view_missing_availability_prevents_confirm(client):
    with scopes_disabled():
        event = EventFactory(cfp__fields={"availabilities": {"visibility": "required"}})
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
    client.force_login(speaker.user)

    response = client.post(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.ACCEPTED


def test_submission_confirm_view_redirects_anonymous_to_login(client, event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.accept()

    response = client.post(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    assert response.redirect_chain[-1][1] == 302
    assert "login" in response.redirect_chain[-1][0]
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.ACCEPTED


def test_submission_confirm_view_non_speaker_sees_error_template(client, event):
    """Non-speaker user sees an error template instead of being redirected."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
        other_user = UserFactory()
    client.force_login(other_user)

    response = client.get(submission.urls.confirm)

    assert response.status_code == 200
    assert "cfp/event/user_submission_confirm_error.html" in [
        t.name for t in response.templates
    ]


def test_submission_draft_discard_view_discards_draft(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        submission.speakers.add(speaker)
        sub_pk = submission.pk
    client.force_login(speaker.user)

    response = client.get(submission.urls.discard, follow=True)
    assert response.status_code == 200

    response = client.post(submission.urls.discard, follow=True)
    assert response.status_code == 200

    with scopes_disabled():
        assert not Submission.all_objects.filter(pk=sub_pk).exists()


def test_profile_view_edit_profile_unchanged_skips_log(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    client.force_login(speaker.user)

    # First POST sets concrete values
    client.post(
        event.urls.user,
        data={
            "name": "Lady Imperator",
            "biography": "Ruling since forever.",
            "form": "profile",
        },
        follow=True,
    )
    with scopes_disabled():
        log_count = speaker.logged_actions().count()

    # Second POST with same values should not create a new log
    response = client.post(
        event.urls.user,
        data={
            "name": "Lady Imperator",
            "biography": "Ruling since forever.",
            "form": "profile",
        },
    )

    assert response.status_code == 302
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.name == "Lady Imperator"
        assert speaker.biography == "Ruling since forever."
        assert speaker.logged_actions().count() == log_count


def test_profile_view_edit_login_info(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    client.force_login(speaker.user)

    response = client.post(
        event.urls.user,
        data={
            "old_password": "testpassword!",
            "email": "new_email@speaker.org",
            "password": "",
            "password_repeat": "",
            "form": "login",
        },
        follow=True,
    )

    assert response.status_code == 200
    speaker.user.refresh_from_db()
    assert speaker.user.email == "new_email@speaker.org"


def test_profile_view_edit_login_info_wrong_password(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    client.force_login(speaker.user)
    original_email = speaker.user.email

    response = client.post(
        event.urls.user,
        data={
            "old_password": "wrongpassword!",
            "email": "new_email@speaker.org",
            "password": "",
            "password_repeat": "",
            "form": "login",
        },
        follow=True,
    )

    assert response.status_code == 200
    speaker.user.refresh_from_db()
    assert speaker.user.email == original_email


def test_profile_view_edit_speaker_questions(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        question = QuestionFactory(
            event=event,
            target="speaker",
            variant="string",
            question_required="optional",
        )
    client.force_login(speaker.user)

    response = client.post(
        event.urls.user,
        data={f"question_{question.pk}": "My answer", "form": "questions"},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        answer = speaker.answers.get(question=question)
        assert answer.answer == "My answer"


@pytest.mark.parametrize(
    "availability_data",
    ({}, {"availabilities": '{"availabilities": []}'}),
    ids=("missing", "empty_json"),
)
def test_profile_view_must_provide_availabilities(client, availability_data):
    with scopes_disabled():
        event = EventFactory(cfp__fields={"availabilities": {"visibility": "required"}})
        speaker = SpeakerFactory(event=event)
    client.force_login(speaker.user)

    response = client.post(
        event.urls.user,
        data={
            "name": "Lady Imperator",
            "biography": "Ruling since forever.",
            "form": "profile",
            **availability_data,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.biography != "Ruling since forever."


def test_delete_account_view_requires_confirmation(client, event):
    """POST without 'really' checkbox redirects without deleting."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event, biography="Has a bio")
    client.force_login(speaker.user)

    response = client.post(event.urls.user_delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        speaker.user.refresh_from_db()
        assert speaker.user.name != "Deleted User"


def test_delete_account_view_deletes_account(client, event):
    """POST with 'really' checkbox deactivates the account and shreds data."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event, biography="Has a bio")
    client.force_login(speaker.user)

    response = client.post(event.urls.user_delete, data={"really": True}, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        speaker.user.refresh_from_db()
        assert speaker.user.name == "Deleted User"
        assert speaker.user.email.startswith("deleted_user")
        speaker.refresh_from_db()
        assert speaker.biography == ""


def test_submission_invite_view_sends_invitation(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker
    djmail.outbox = []

    data = {
        "speaker": "other@speaker.org",
        "subject": "Please join!",
        "text": "Come join us! {invitation_url}",
    }

    response = speaker_client.post(submission.urls.invite, follow=True, data=data)

    assert response.status_code == 200
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["other@speaker.org"]
    with scopes_disabled():
        assert SubmissionInvitation.objects.filter(
            submission=submission, email="other@speaker.org"
        ).exists()
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.invitation.send")
            .exists()
        )


def test_submission_invite_view_rejects_without_url_placeholder(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker
    djmail.outbox = []

    data = {
        "speaker": "other@speaker.org",
        "subject": "Please join!",
        "text": "Come join us, no link here!",
    }

    response = speaker_client.post(submission.urls.invite, follow=True, data=data)

    assert response.status_code == 200
    assert len(djmail.outbox) == 0


def test_submission_invite_view_rejects_existing_speaker(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker
    with scopes_disabled():
        user = submission.speakers.first().user
    djmail.outbox = []

    data = {
        "speaker": user.email,
        "subject": "Please join!",
        "text": "Come join us! {invitation_url}",
    }

    response = speaker_client.post(submission.urls.invite, follow=True, data=data)

    assert response.status_code == 200
    assert len(djmail.outbox) == 0


def test_submission_invite_view_rejects_duplicate_invitation(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker
    with scopes_disabled():
        SubmissionInvitationFactory(email="other@example.org", submission=submission)
    djmail.outbox = []

    data = {
        "speaker": "other@example.org",
        "subject": "Please join!",
        "text": "Come join us! {invitation_url}",
    }

    response = speaker_client.post(submission.urls.invite, follow=True, data=data)

    assert response.status_code == 200
    assert len(djmail.outbox) == 0


def test_submission_invite_view_respects_max_speakers_limit(client):
    with scopes_disabled():
        event = EventFactory(
            feature_flags={"speakers_can_edit_submissions": True},
            cfp__fields={"additional_speaker": {"visibility": "optional", "max": 1}},
        )
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
    client.force_login(speaker.user)
    djmail.outbox = []

    data = {
        "speaker": "other@speaker.org",
        "subject": "Please join!",
        "text": "Come join us! {invitation_url}",
    }

    response = client.post(submission.urls.invite, follow=True, data=data)

    assert response.status_code == 200
    assert len(djmail.outbox) == 0


def test_submission_invite_view_get_prefills_email_from_query(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker

    response = speaker_client.get(
        submission.urls.invite + "?email=prefilled%40example.com", follow=True
    )

    assert response.status_code == 200
    assert "prefilled@example.com" in response.content.decode()


def test_submission_invite_retract_view_deletes_invitation(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker
    with scopes_disabled():
        invitation = SubmissionInvitationFactory(
            submission=submission, email="todelete@example.com"
        )
        invitation_id = invitation.pk

    response = speaker_client.post(
        submission.urls.retract_invitation + f"?id={invitation_id}", follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert not SubmissionInvitation.objects.filter(pk=invitation_id).exists()
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.invitation.retract")
            .exists()
        )


def test_submission_invite_accept_view_adds_speaker(client, event):
    """Accepting an invitation adds the user as a speaker and deletes the invitation."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        user = UserFactory()
        invitation = SubmissionInvitationFactory(
            submission=submission, email=user.email
        )
        invitation_pk = invitation.pk
        initial_count = submission.speakers.count()
    client.force_login(user)

    response = client.post(invitation.urls.base.full(), follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.speakers.count() == initial_count + 1
        assert submission.speakers.filter(user=user).exists()
        assert not SubmissionInvitation.objects.filter(pk=invitation_pk).exists()
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.invitation.accept")
            .exists()
        )


def test_submission_invite_accept_view_wrong_token_returns_404(client, event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        user = UserFactory()
        invitation = SubmissionInvitationFactory(
            submission=submission, email=user.email
        )
    client.force_login(user)

    response = client.post(invitation.urls.base.full() + "invalidtoken", follow=True)

    assert response.status_code == 404
    with scopes_disabled():
        assert not submission.speakers.filter(user=user).exists()


@pytest.mark.parametrize("item_count", (1, 3))
def test_mail_list_view_shows_sent_mails(
    client, event, item_count, django_assert_num_queries
):
    """Mail list shows sent mails for the current user, query count is constant."""
    with scopes_disabled():
        user = UserFactory()
        mails = []
        for _ in range(item_count):
            mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
            mail.to_users.add(user)
            mails.append(mail)
    client.force_login(user)

    with django_assert_num_queries(9):
        response = client.get(event.urls.user_mails, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    for mail in mails:
        assert mail.subject in content


def test_mail_list_view_hides_unsent_mails(client, event):
    with scopes_disabled():
        user = UserFactory()
        draft_mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
        draft_mail.to_users.add(user)
        sent_mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
        sent_mail.to_users.add(user)
    client.force_login(user)

    response = client.get(event.urls.user_mails, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert sent_mail.subject in content
    assert draft_mail.subject not in content


def test_submissions_edit_view_dedraft_redirects_to_wizard(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.DRAFT, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, action="dedraft")

    response = client.post(submission.urls.user_base, data=data)

    assert response.status_code == 302
    assert f"submit/restart-{submission.code}" in response.url


def test_submissions_edit_view_dedraft_prevented_when_access_code_required(
    client, event
):
    """Dedraft is prevented when the track requires an access code the submission doesn't have."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        track = TrackFactory(event=event, requires_access_code=True)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.DRAFT, track=track
        )
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, action="dedraft")

    response = client.post(submission.urls.user_base, data=data, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.DRAFT


def test_submissions_edit_view_dedraft_with_access_code_includes_code_in_url(
    client, event
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        access_code = SubmitterAccessCodeFactory(event=event)
        submission = SubmissionFactory(
            event=event,
            state=SubmissionStates.DRAFT,
            access_code=access_code,
            abstract="Test abstract",
        )
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, action="dedraft")

    response = client.post(submission.urls.user_base, data=data)

    assert response.status_code == 302
    assert f"access_code={access_code.code}" in response.url


def test_submissions_edit_view_cannot_edit_confirmed_slot_count(client):
    event = EventFactory(feature_flags={"present_multiple_times": True})
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
        submission.confirm()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, slot_count=13)

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.slot_count != 13


def test_profile_view_edit_speaker_answers_multiple_types(client, event):
    """Speaker can answer boolean, string, and file questions, and update existing answers."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        string_question = QuestionFactory(
            event=event,
            target="speaker",
            variant="string",
            question_required="optional",
        )
        boolean_question = QuestionFactory(
            event=event,
            target="speaker",
            variant="boolean",
            question_required="optional",
        )
        file_question = QuestionFactory(
            event=event, target="speaker", variant="file", question_required="optional"
        )
    client.force_login(speaker.user)
    test_file = SimpleUploadedFile("testfile.txt", b"file_content")

    response = client.post(
        event.urls.user,
        data={
            f"question_{string_question.pk}": "black as the night",
            f"question_{boolean_question.pk}": "True",
            f"question_{file_question.pk}": test_file,
            "form": "questions",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            speaker.answers.get(question=string_question).answer == "black as the night"
        )
        assert speaker.answers.get(question=boolean_question).answer == "True"
        file_answer = speaker.answers.get(question=file_question)
        assert file_answer.answer.startswith("file://")
        assert file_answer.answer_file.read() == b"file_content"

    response = client.post(
        event.urls.user,
        data={
            f"question_{string_question.pk}": "green as the sky",
            "form": "questions",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            speaker.answers.get(question=string_question).answer == "green as the sky"
        )


def test_submissions_edit_view_tags_hidden_when_no_public_tags(client):
    with scopes_disabled():
        event = EventFactory(cfp__fields={"tags": {"visibility": "optional"}})
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        TagFactory(tag="private-tag", event=event, is_public=False)
    client.force_login(speaker.user)

    response = client.get(submission.urls.user_base, follow=True)

    assert response.status_code == 200
    assert "private-tag" not in response.content.decode()


def test_submissions_edit_view_tags_hidden_when_do_not_ask(client):
    with scopes_disabled():
        event = EventFactory(cfp__fields={"tags": {"visibility": "do_not_ask"}})
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        TagFactory(tag="public-tag", event=event, is_public=True)
    client.force_login(speaker.user)

    response = client.get(submission.urls.user_base, follow=True)

    assert response.status_code == 200
    assert "public-tag" not in response.content.decode()


def test_submissions_edit_view_tags_valid_count_saves(client):
    with scopes_disabled():
        event = EventFactory(
            feature_flags={"speakers_can_edit_submissions": True},
            cfp__fields={"tags": {"visibility": "optional", "min": 1, "max": 2}},
        )
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
        tag1 = TagFactory(tag="tag1", event=event, is_public=True)
        tag2 = TagFactory(tag="tag2", event=event, is_public=True)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[tag1.pk, tag2.pk])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "you selected" not in response.content.decode().lower()
    with scopes_disabled():
        submission.refresh_from_db()
        assert set(submission.tags.all()) == {tag1, tag2}


def test_submissions_edit_view_tags_required_but_none_submitted(client):
    with scopes_disabled():
        event = EventFactory(
            cfp__fields={"tags": {"visibility": "required", "min": None, "max": None}}
        )
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        TagFactory(tag="tag1", event=event, is_public=True)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "this field is required" in response.content.decode().lower()


def test_submissions_edit_view_tags_exact_count_validation(client):
    """When min == max, validation message says 'exactly N tags'."""
    with scopes_disabled():
        event = EventFactory(
            cfp__fields={"tags": {"visibility": "optional", "min": 2, "max": 2}}
        )
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        tag1 = TagFactory(tag="tag1", event=event, is_public=True)
        TagFactory(tag="tag2", event=event, is_public=True)
        TagFactory(tag="tag3", event=event, is_public=True)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[tag1.pk])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "exactly 2 tags" in response.content.decode().lower()


def test_submissions_edit_view_dedraft_prevented_when_submission_type_requires_access_code(
    client, event
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event, requires_access_code=True)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.DRAFT, submission_type=sub_type
        )
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, action="dedraft")

    response = client.post(submission.urls.user_base, data=data, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.DRAFT


def test_profile_view_edit_speaker_questions_unchanged_skips_log(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        question = QuestionFactory(
            event=event,
            target="speaker",
            variant="string",
            question_required="optional",
        )
    client.force_login(speaker.user)
    data = {f"question_{question.pk}": "My answer", "form": "questions"}

    client.post(event.urls.user, data=data, follow=True)
    with scopes_disabled():
        log_count = speaker.logged_actions().count()

    response = client.post(event.urls.user, data=data, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert speaker.answers.get(question=question).answer == "My answer"
        assert speaker.logged_actions().count() == log_count


def test_submissions_withdraw_view_handles_submission_error(
    client, event, register_signal_handler
):
    """SubmissionError raised by a plugin signal prevents withdrawal."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    def block_withdrawal(**kwargs):
        raise SubmissionError("Signal blocked withdrawal")

    register_signal_handler(before_submission_state_change, block_withdrawal)
    response = client.post(submission.urls.withdraw, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED


def test_submission_confirm_view_handles_submission_error(
    client, event, register_signal_handler
):
    """SubmissionError raised by a plugin signal prevents confirmation."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
    client.force_login(speaker.user)

    def block_confirmation(**kwargs):
        raise SubmissionError("Signal blocked confirmation")

    register_signal_handler(before_submission_state_change, block_confirmation)
    response = client.post(submission.urls.confirm, data={}, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.ACCEPTED


def test_submissions_edit_view_invalid_formset_shows_form_again(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
    client.force_login(speaker.user)

    data = _edit_form_data(
        submission,
        **{
            "resource-TOTAL_FORMS": 1,
            "resource-0-id": "",
            "resource-0-description": "New resource",
            # Missing resource file AND link — should be invalid
        },
    )

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        assert submission.resources.count() == 0


def test_submissions_edit_view_unchanged_resource_preserved(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker
    with scopes_disabled():
        resource = ResourceFactory(submission=submission, description="My resource")
    data = _edit_form_data(
        submission,
        **{
            "resource-0-id": resource.id,
            "resource-0-description": resource.description or "",
            "resource-0-link": resource.link or "",
            "resource-TOTAL_FORMS": 1,
            "resource-INITIAL_FORMS": 1,
        },
    )

    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        resource.refresh_from_db()
        assert resource.description == "My resource"


def test_submissions_edit_view_uneditable_submission_shows_error(client):
    event = EventFactory(feature_flags={"speakers_can_edit_submissions": False})
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
    )
    with scopes_disabled():
        submission.speakers.add(speaker)
        submission.accept()
    client.force_login(speaker.user)
    original_title = submission.title
    data = _edit_form_data(submission, title="Should Not Change")

    response = client.post(submission.urls.user_base, follow=False, data=data)

    assert response.status_code == 302
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.title == original_title


def test_submissions_edit_view_duration_change_updates_slot(client):
    """Changing the duration field updates the scheduled talk slot's end time."""
    event = EventFactory(cfp__fields={"duration": {"visibility": "optional"}})
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        abstract="Test abstract",
        duration=30,
    )
    with scopes_disabled():
        submission.speakers.add(speaker)
    client.force_login(speaker.user)
    slot = TalkSlotFactory(submission=submission)
    original_end = slot.end
    data = _edit_form_data(submission, duration=45)

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        slot.refresh_from_db()
        assert slot.end != original_end
        assert slot.end == slot.start + dt.timedelta(minutes=45)


def test_submissions_edit_view_track_change_updates_review_scores(client):
    event = EventFactory(
        feature_flags={"use_tracks": True},
        cfp__fields={"track": {"visibility": "optional"}},
    )
    speaker = SpeakerFactory(event=event)
    old_track = TrackFactory(event=event, name="Old Track")
    new_track = TrackFactory(event=event, name="New Track")
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.SUBMITTED,
        abstract="Test abstract",
        track=old_track,
    )
    with scopes_disabled():
        submission.speakers.add(speaker)
    client.force_login(speaker.user)
    with scopes_disabled():
        review = ReviewFactory(submission=submission)
        review.score = 5
        review.save(update_score=False)
    data = _edit_form_data(submission, track=new_track.pk)

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        review.refresh_from_db()
        assert review.score is None


def test_submission_invite_view_get_warns_on_invalid_email_query_param(
    speaker_client, submission_with_speaker
):
    submission = submission_with_speaker

    response = speaker_client.get(
        submission.urls.invite + "?email=not-an-email", follow=True
    )

    assert response.status_code == 200
    assert "valid email" in response.content.decode().lower()


def test_submission_invite_accept_view_rejects_when_speakers_disabled(client):
    with scopes_disabled():
        event = EventFactory(
            cfp__fields={"additional_speaker": {"visibility": "do_not_ask"}}
        )
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        invitation = SubmissionInvitationFactory(
            submission=submission, email="other@example.com"
        )
    other_user = UserFactory()
    client.force_login(other_user)

    response = client.post(invitation.urls.base.full(), follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert not submission.speakers.filter(user=other_user).exists()
