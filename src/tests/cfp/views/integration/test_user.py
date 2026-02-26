import datetime as dt

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SubmissionError
from pretalx.mail.models import QueuedMailStates
from pretalx.submission.models import (
    Submission,
    SubmissionInvitation,
    SubmissionStates,
    Tag,
)
from pretalx.submission.signals import before_submission_state_change
from tests.factories import (
    QuestionFactory,
    QueuedMailFactory,
    ResourceFactory,
    ReviewFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    SubmitterAccessCodeFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def speaker_and_submission(event):
    """A speaker with a submission on a public event with editing enabled."""
    event.is_public = True
    event.feature_flags["speakers_can_edit_submissions"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
    return speaker, submission, speaker.user


@pytest.fixture
def speaker_client(client, speaker_and_submission):
    """A logged-in client for the speaker user."""
    _, _, user = speaker_and_submission
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


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_submissions_list_view_shows_submissions(
    client, event, item_count, django_assert_num_queries
):
    """Submission list shows all user submissions, query count is constant."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submissions = []
        for _ in range(item_count):
            sub = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
            sub.speakers.add(speaker)
            submissions.append(sub)
    client.force_login(speaker.user)

    with django_assert_num_queries(12):
        response = client.get(event.urls.user_submissions, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    for sub in submissions:
        assert sub.title in content


@pytest.mark.django_db
def test_submissions_list_view_does_not_show_other_users_submissions(
    client, speaker_client, speaker_and_submission, event
):
    """Submission list does not show submissions from other speakers."""
    _, submission, _ = speaker_and_submission
    with scopes_disabled():
        other_sub = SubmissionFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        other_sub.speakers.add(other_speaker)

    response = speaker_client.get(event.urls.user_submissions, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert submission.title in content
    assert other_sub.title not in content


@pytest.mark.django_db
def test_submissions_list_view_shows_drafts(client, event):
    """Submission list shows draft submissions separately."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        draft.speakers.add(speaker)
    client.force_login(speaker.user)

    response = client.get(event.urls.user_submissions, follow=True)

    assert response.status_code == 200
    assert draft.title in response.content.decode()


@pytest.mark.django_db
def test_submissions_list_view_shows_speaker_information(client, event):
    """Submission list shows speaker information items visible to the user."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        info = SpeakerInformationFactory(event=event, target_group="submitters")
    client.force_login(speaker.user)

    response = client.get(event.urls.user_submissions, follow=True)

    assert response.status_code == 200
    assert str(info.title) in response.content.decode()


@pytest.mark.django_db
def test_submissions_list_view_requires_login(client, event):
    """Submission list redirects to login for anonymous users."""
    event.is_public = True
    event.save()
    response = client.get(event.urls.user_submissions, follow=True)

    assert response.status_code == 200
    assert "login" in response.redirect_chain[-1][0]


@pytest.mark.django_db
def test_submissions_edit_view_shows_submission(speaker_client, speaker_and_submission):
    """Edit view displays the submission title and form fields."""
    _, submission, _ = speaker_and_submission

    response = speaker_client.get(submission.urls.user_base, follow=True)

    assert response.status_code == 200
    assert submission.title in response.content.decode()


@pytest.mark.django_db
def test_submissions_edit_view_can_edit_title(speaker_client, speaker_and_submission):
    """Speaker can change the submission title via the edit form."""
    _, submission, _ = speaker_and_submission
    data = _edit_form_data(submission, title="A Completely New Title")

    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.title == "A Completely New Title"


@pytest.mark.django_db
def test_submissions_edit_view_logs_changes(speaker_client, speaker_and_submission):
    """Editing a submission creates a single consolidated log entry including
    both field changes and question answer changes."""
    _, submission, _ = speaker_and_submission
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


@pytest.mark.django_db
def test_submissions_edit_view_with_resources(speaker_client, speaker_and_submission):
    """Speaker can add, update, and delete resources via the edit form."""
    _, submission, _ = speaker_and_submission
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


@pytest.mark.django_db
def test_submissions_edit_view_orga_redirected_to_orga_page(
    client, speaker_and_submission, event
):
    """Organisers who are not speakers get redirected to the orga view."""
    _, submission, _ = speaker_and_submission
    with scopes_disabled():
        orga_user = UserFactory()
        team = TeamFactory(organiser=event.organiser, all_events=True)
        team.members.add(orga_user)
    client.force_login(orga_user)

    response = client.get(submission.urls.user_base, follow=False)

    assert response.status_code == 302
    assert response.url == submission.orga_urls.base


@pytest.mark.django_db
def test_submissions_edit_view_other_user_gets_404(client, speaker_and_submission):
    """A user who is not a speaker on the submission gets 404."""
    _, submission, _ = speaker_and_submission
    other_user = UserFactory()
    client.force_login(other_user)

    response = client.get(submission.urls.user_base, follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_submissions_edit_view_cannot_edit_rejected_submission(client, event):
    """Rejected submissions cannot be edited by the speaker."""
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


@pytest.mark.django_db
def test_submissions_edit_view_cannot_edit_when_feature_disabled(client, event):
    """Accepted submissions cannot be edited when speakers_can_edit_submissions is off."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
        event.feature_flags["speakers_can_edit_submissions"] = False
        event.save()
    client.force_login(speaker.user)
    original_title = submission.title
    data = _edit_form_data(submission, title="Should Not Change")

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.title == original_title


@pytest.mark.django_db
def test_submissions_edit_view_draft_still_editable_when_feature_disabled(
    client, event
):
    """Draft submissions remain editable even when speakers_can_edit_submissions is off."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.DRAFT, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
        event.feature_flags["speakers_can_edit_submissions"] = False
        event.save()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, title="Changed Draft Title")

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.title == "Changed Draft Title"


@pytest.mark.django_db
def test_submissions_edit_view_can_edit_submission_type(client, event):
    """Speaker can change the submission type."""
    event.feature_flags["speakers_can_edit_submissions"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
        new_type = event.submission_types.create(name="Other", default_duration=13)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, submission_type=new_type.pk)

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.submission_type == new_type


@pytest.mark.django_db
def test_submissions_edit_view_cannot_edit_submission_type_after_acceptance(
    client, event
):
    """Speaker cannot change submission type after acceptance."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
        new_type = event.submission_types.create(name="Other", default_duration=13)
    client.force_login(speaker.user)

    data = _edit_form_data(submission, submission_type=new_type.pk)

    response = client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.submission_type != new_type


@pytest.mark.django_db
def test_submissions_edit_view_can_edit_slot_count(client, event):
    """Speaker can change slot_count when present_multiple_times is enabled."""
    event.feature_flags["present_multiple_times"] = True
    event.feature_flags["speakers_can_edit_submissions"] = True
    event.save()
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


@pytest.mark.django_db
def test_submissions_edit_view_tags_shown_when_public(client, event):
    """Edit view shows public tags and hides private tags."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        Tag.objects.create(tag="public-tag", event=event, is_public=True)
        Tag.objects.create(tag="private-tag", event=event, is_public=False)
        event.cfp.fields["tags"] = {"visibility": "optional"}
        event.cfp.save()
    client.force_login(speaker.user)

    response = client.get(submission.urls.user_base, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "public-tag" in content
    assert "private-tag" not in content


@pytest.mark.django_db
def test_submissions_edit_view_private_tags_preserved_on_save(client, event):
    """Private tags assigned by organisers are preserved when speaker edits."""
    event.feature_flags["speakers_can_edit_submissions"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
        public_tag = Tag.objects.create(tag="public-tag", event=event, is_public=True)
        private_tag = Tag.objects.create(
            tag="private-tag", event=event, is_public=False
        )
        submission.tags.add(public_tag, private_tag)
        event.cfp.fields["tags"] = {"visibility": "optional"}
        event.cfp.save()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert public_tag not in submission.tags.all()
        assert private_tag in submission.tags.all()


@pytest.mark.django_db
def test_submissions_edit_view_tags_validation_min(client, event):
    """Form rejects too few tags when minimum is configured."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        tag1 = Tag.objects.create(tag="tag1", event=event, is_public=True)
        Tag.objects.create(tag="tag2", event=event, is_public=True)
        event.cfp.fields["tags"] = {"visibility": "required", "min": 2, "max": None}
        event.cfp.save()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[tag1.pk])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "at least 2 tags" in response.content.decode().lower()


@pytest.mark.django_db
def test_submissions_edit_view_tags_validation_max(client, event):
    """Form rejects too many tags when maximum is configured."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        tag1 = Tag.objects.create(tag="tag1", event=event, is_public=True)
        tag2 = Tag.objects.create(tag="tag2", event=event, is_public=True)
        tag3 = Tag.objects.create(tag="tag3", event=event, is_public=True)
        event.cfp.fields["tags"] = {"visibility": "optional", "min": None, "max": 2}
        event.cfp.save()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[tag1.pk, tag2.pk, tag3.pk])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "at most 2 tags" in response.content.decode().lower()


@pytest.mark.django_db
def test_submissions_withdraw_view_get_shows_form(
    speaker_client, speaker_and_submission
):
    """GET on withdraw page shows the confirmation form."""
    _, submission, _ = speaker_and_submission

    response = speaker_client.get(submission.urls.withdraw, follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
def test_submissions_withdraw_view_withdraws_submitted(
    speaker_client, speaker_and_submission
):
    """POST withdraws a submitted submission."""
    _, submission, _ = speaker_and_submission
    djmail.outbox = []

    response = speaker_client.post(submission.urls.withdraw, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.WITHDRAWN
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_submissions_withdraw_view_sends_orga_email_for_accepted(client, event):
    """Withdrawing an accepted submission sends an organiser notification email."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "transition", ("confirmed", "rejected"), ids=("confirmed", "rejected")
)
def test_submissions_withdraw_view_cannot_withdraw_non_withdrawable(
    client, event, transition
):
    """Cannot withdraw a confirmed or rejected submission."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        if transition == "confirmed":
            submission.accept()
            submission.confirm()
        else:
            submission.reject()
    client.force_login(speaker.user)

    response = client.post(submission.urls.withdraw, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state != SubmissionStates.WITHDRAWN


@pytest.mark.django_db
@pytest.mark.parametrize("availability_visibility", ("optional", "do_not_ask"))
def test_submission_confirm_view_confirms_accepted(
    client, event, availability_visibility
):
    """POST on confirm view transitions accepted submission to confirmed."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        event.cfp.fields["availabilities"] = {"visibility": availability_visibility}
        event.cfp.save()
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
    client.force_login(speaker.user)

    response = client.post(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.CONFIRMED


@pytest.mark.django_db
def test_submission_confirm_view_get_shows_form(client, event):
    """GET on confirm view shows confirmation form for accepted submission."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
    client.force_login(speaker.user)

    response = client.get(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("transition", "expected_state"),
    ((None, SubmissionStates.SUBMITTED), ("reject", SubmissionStates.REJECTED)),
    ids=("submitted", "rejected"),
)
def test_submission_confirm_view_cannot_confirm_non_accepted(
    client, event, transition, expected_state
):
    """Cannot confirm a submission that is not in ACCEPTED state."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        if transition:
            getattr(submission, transition)()
    client.force_login(speaker.user)

    response = client.post(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == expected_state


@pytest.mark.django_db
def test_submission_confirm_view_reconfirm_already_confirmed(client, event):
    """Confirming an already-confirmed submission remains confirmed."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submission_confirm_view_missing_availability_prevents_confirm(client, event):
    """Required availabilities block confirmation when not provided."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        event.cfp.fields["availabilities"] = {"visibility": "required"}
        event.cfp.save()
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
    client.force_login(speaker.user)

    response = client.post(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_confirm_view_redirects_anonymous_to_login(client, event):
    """Anonymous user is redirected to login page."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.accept()

    response = client.post(submission.urls.confirm, follow=True)

    assert response.status_code == 200
    assert response.redirect_chain[-1][1] == 302
    assert "login" in response.redirect_chain[-1][0]
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_confirm_view_non_speaker_sees_error_template(client, event):
    """Non-speaker user sees an error template instead of being redirected."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submission_confirm_view_wrong_code_returns_404(client, event):
    """Confirm view with wrong submission code returns 404."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        submission.accept()
    client.force_login(speaker.user)

    response = client.post(
        submission.urls.confirm.replace(submission.code, "BADCODE"), follow=True
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_submission_draft_discard_view_discards_draft(client, event):
    """POST on discard view deletes a draft submission."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submission_draft_discard_view_404_for_non_draft(
    speaker_client, speaker_and_submission
):
    """Discard view returns 404 for non-draft submissions."""
    _, submission, _ = speaker_and_submission

    response = speaker_client.get(submission.urls.discard, follow=True)
    assert response.status_code == 404

    response = speaker_client.post(submission.urls.discard, follow=True)
    assert response.status_code == 404

    with scopes_disabled():
        assert Submission.objects.filter(pk=submission.pk).exists()


@pytest.mark.django_db
def test_profile_view_edit_profile(client, event):
    """Speaker can edit their profile name and biography."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    client.force_login(speaker.user)

    response = client.post(
        event.urls.user,
        data={
            "name": "Lady Imperator",
            "biography": "Ruling since forever.",
            "form": "profile",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.biography == "Ruling since forever."
        assert speaker.name == "Lady Imperator"


@pytest.mark.django_db
def test_profile_view_edit_profile_unchanged_on_second_save(client, event):
    """Saving the same profile data twice preserves the data correctly."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    client.force_login(speaker.user)
    data = {
        "name": "Lady Imperator",
        "biography": "Ruling since forever.",
        "form": "profile",
    }

    client.post(event.urls.user, data=data, follow=True)
    response = client.post(event.urls.user, data=data, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.biography == "Ruling since forever."


@pytest.mark.django_db
def test_profile_view_edit_login_info(client, event):
    """Speaker can change their email via the login form."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_profile_view_edit_login_info_wrong_password(client, event):
    """Login info update fails with wrong old password."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_profile_view_edit_speaker_questions(client, event):
    """Speaker can answer speaker-targeted questions via the questions form."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "availability_data",
    ({}, {"availabilities": '{"availabilities": []}'}),
    ids=("missing", "empty_json"),
)
def test_profile_view_must_provide_availabilities(client, event, availability_data):
    """Profile update fails when required availabilities are missing or empty."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        event.cfp.fields["availabilities"] = {"visibility": "required"}
        event.cfp.save()
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


@pytest.mark.django_db
def test_delete_account_view_requires_confirmation(client, event):
    """POST without 'really' checkbox redirects without deleting."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event, biography="Has a bio")
    client.force_login(speaker.user)

    response = client.post(event.urls.user_delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        speaker.user.refresh_from_db()
        assert speaker.user.name != "Deleted User"


@pytest.mark.django_db
def test_delete_account_view_deletes_account(client, event):
    """POST with 'really' checkbox deactivates the account and shreds data."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submission_invite_view_sends_invitation(
    speaker_client, speaker_and_submission
):
    """Speaker can invite another person to the submission."""
    _, submission, _ = speaker_and_submission
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


@pytest.mark.django_db
def test_submission_invite_view_rejects_without_url_placeholder(
    speaker_client, speaker_and_submission
):
    """Invitation is rejected when text does not contain {invitation_url}."""
    _, submission, _ = speaker_and_submission
    djmail.outbox = []

    data = {
        "speaker": "other@speaker.org",
        "subject": "Please join!",
        "text": "Come join us, no link here!",
    }

    response = speaker_client.post(submission.urls.invite, follow=True, data=data)

    assert response.status_code == 200
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_submission_invite_view_rejects_existing_speaker(
    speaker_client, speaker_and_submission
):
    """Cannot invite someone who is already a speaker on the submission."""
    _, submission, user = speaker_and_submission
    djmail.outbox = []

    data = {
        "speaker": user.email,
        "subject": "Please join!",
        "text": "Come join us! {invitation_url}",
    }

    response = speaker_client.post(submission.urls.invite, follow=True, data=data)

    assert response.status_code == 200
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_submission_invite_view_rejects_duplicate_invitation(
    speaker_client, speaker_and_submission
):
    """Cannot send a duplicate invitation to the same email."""
    _, submission, _ = speaker_and_submission
    with scopes_disabled():
        SubmissionInvitation.objects.create(
            email="other@example.org", submission=submission
        )
    djmail.outbox = []

    data = {
        "speaker": "other@example.org",
        "subject": "Please join!",
        "text": "Come join us! {invitation_url}",
    }

    response = speaker_client.post(submission.urls.invite, follow=True, data=data)

    assert response.status_code == 200
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_submission_invite_view_respects_max_speakers_limit(client, event):
    """Cannot invite when max_speakers limit would be exceeded."""
    event.is_public = True
    event.feature_flags["speakers_can_edit_submissions"] = True
    event.save()
    with scopes_disabled():
        event.cfp.fields["additional_speaker"] = {"visibility": "optional", "max": 1}
        event.cfp.save()
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


@pytest.mark.django_db
def test_submission_invite_view_get_prefills_email_from_query(
    speaker_client, speaker_and_submission
):
    """GET with ?email= prefills the speaker email field."""
    _, submission, _ = speaker_and_submission

    response = speaker_client.get(
        submission.urls.invite + "?email=prefilled%40example.com", follow=True
    )

    assert response.status_code == 200
    assert "prefilled@example.com" in response.content.decode()


@pytest.mark.django_db
def test_submission_invite_retract_view_deletes_invitation(
    speaker_client, speaker_and_submission
):
    """Speaker can retract a pending invitation."""
    _, submission, _ = speaker_and_submission
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.create(
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


@pytest.mark.django_db
def test_submission_invite_accept_view_adds_speaker(client, event):
    """Accepting an invitation adds the user as a speaker and deletes the invitation."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        user = UserFactory()
        invitation = SubmissionInvitation.objects.create(
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


@pytest.mark.django_db
def test_submission_invite_accept_view_wrong_token_returns_404(client, event):
    """Invalid invitation token returns 404."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        user = UserFactory()
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email=user.email
        )
    client.force_login(user)

    response = client.post(invitation.urls.base.full() + "invalidtoken", follow=True)

    assert response.status_code == 404
    with scopes_disabled():
        assert not submission.speakers.filter(user=user).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_mail_list_view_shows_sent_mails(
    client, event, item_count, django_assert_num_queries
):
    """Mail list shows sent mails for the current user, query count is constant."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_mail_list_view_hides_unsent_mails(client, event):
    """Mail list does not show draft or pending mails."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submissions_edit_view_dedraft_redirects_to_wizard(client, event):
    """Dedraft action redirects to the CfP wizard restart URL."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submissions_edit_view_dedraft_prevented_when_access_code_required(
    client, event
):
    """Dedraft is prevented when the track requires an access code the submission doesn't have."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        track = TrackFactory(event=event)
        track.requires_access_code = True
        track.save()
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


@pytest.mark.django_db
def test_submissions_edit_view_dedraft_with_access_code_includes_code_in_url(
    client, event
):
    """Dedraft with a valid access code includes the code in the redirect URL."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submissions_edit_view_cannot_edit_confirmed_slot_count(client, event):
    """Confirmed submissions cannot have their slot_count changed."""
    with scopes_disabled():
        event.feature_flags["present_multiple_times"] = True
        event.save()
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


@pytest.mark.django_db
def test_profile_view_edit_speaker_answers_multiple_types(client, event):
    """Speaker can answer boolean, string, and file questions, and update existing answers."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submissions_edit_view_can_save_with_tags(client, event):
    """Speaker can successfully assign public tags to their submission."""
    event.feature_flags["speakers_can_edit_submissions"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
        public_tag = Tag.objects.create(tag="public-tag", event=event, is_public=True)
        Tag.objects.create(tag="private-tag", event=event, is_public=False)
        event.cfp.fields["tags"] = {"visibility": "optional"}
        event.cfp.save()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[public_tag.pk])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert public_tag in submission.tags.all()


@pytest.mark.django_db
def test_submissions_edit_view_tags_hidden_when_no_public_tags(client, event):
    """Tags field is hidden when only private (non-public) tags exist."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        Tag.objects.create(tag="private-tag", event=event, is_public=False)
        event.cfp.fields["tags"] = {"visibility": "optional"}
        event.cfp.save()
    client.force_login(speaker.user)

    response = client.get(submission.urls.user_base, follow=True)

    assert response.status_code == 200
    assert "private-tag" not in response.content.decode()


@pytest.mark.django_db
def test_submissions_edit_view_tags_hidden_when_do_not_ask(client, event):
    """Tags are not shown when visibility is set to do_not_ask."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        Tag.objects.create(tag="public-tag", event=event, is_public=True)
        event.cfp.fields["tags"] = {"visibility": "do_not_ask"}
        event.cfp.save()
    client.force_login(speaker.user)

    response = client.get(submission.urls.user_base, follow=True)

    assert response.status_code == 200
    assert "public-tag" not in response.content.decode()


@pytest.mark.django_db
def test_submissions_edit_view_tags_valid_count_saves(client, event):
    """Tags within valid min/max range save successfully."""
    event.feature_flags["speakers_can_edit_submissions"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.SUBMITTED, abstract="Test abstract"
        )
        submission.speakers.add(speaker)
        tag1 = Tag.objects.create(tag="tag1", event=event, is_public=True)
        tag2 = Tag.objects.create(tag="tag2", event=event, is_public=True)
        event.cfp.fields["tags"] = {"visibility": "optional", "min": 1, "max": 2}
        event.cfp.save()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[tag1.pk, tag2.pk])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "you selected" not in response.content.decode().lower()
    with scopes_disabled():
        submission.refresh_from_db()
        assert set(submission.tags.all()) == {tag1, tag2}


@pytest.mark.django_db
def test_submissions_edit_view_tags_required_but_none_submitted(client, event):
    """Required tags field rejects empty submission."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        Tag.objects.create(tag="tag1", event=event, is_public=True)
        event.cfp.fields["tags"] = {"visibility": "required", "min": None, "max": None}
        event.cfp.save()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "this field is required" in response.content.decode().lower()


@pytest.mark.django_db
def test_submissions_edit_view_tags_exact_count_validation(client, event):
    """When min == max, validation message says 'exactly N tags'."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        tag1 = Tag.objects.create(tag="tag1", event=event, is_public=True)
        Tag.objects.create(tag="tag2", event=event, is_public=True)
        Tag.objects.create(tag="tag3", event=event, is_public=True)
        event.cfp.fields["tags"] = {"visibility": "optional", "min": 2, "max": 2}
        event.cfp.save()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, tags=[tag1.pk])

    response = client.post(submission.urls.user_base, data, follow=True)

    assert response.status_code == 200
    assert "exactly 2 tags" in response.content.decode().lower()


@pytest.mark.django_db
def test_submissions_edit_view_dedraft_prevented_when_submission_type_requires_access_code(
    client, event
):
    """Dedraft is prevented when the submission_type requires an access code."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        submission.speakers.add(speaker)
        submission.submission_type.requires_access_code = True
        submission.submission_type.save()
    client.force_login(speaker.user)

    data = _edit_form_data(submission, action="dedraft")

    response = client.post(submission.urls.user_base, data=data, follow=True)

    assert response.status_code == 200
    submission.refresh_from_db()
    assert submission.state == SubmissionStates.DRAFT


@pytest.mark.django_db
def test_profile_view_edit_speaker_questions_unchanged_skips_log(client, event):
    """Saving questions form with unchanged answers still succeeds but creates no log."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submissions_edit_view_reviewer_redirected_to_orga_page(client, event):
    """A reviewer (with orga_list but not view_submission) is redirected to the orga page."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        reviewer_user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            can_change_submissions=False,
            is_reviewer=True,
        )
        team.members.add(reviewer_user)
    client.force_login(reviewer_user)

    response = client.get(submission.urls.user_base, follow=False)

    assert response.status_code == 302
    assert response.url == submission.orga_urls.base


@pytest.mark.django_db
def test_submissions_withdraw_view_handles_submission_error(
    client, event, register_signal_handler
):
    """SubmissionError raised by a plugin signal prevents withdrawal."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submission_confirm_view_handles_submission_error(
    client, event, register_signal_handler
):
    """SubmissionError raised by a plugin signal prevents confirmation."""
    event.is_public = True
    event.save()
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


@pytest.mark.django_db
def test_submissions_edit_view_invalid_formset_shows_form_again(client, event):
    """Invalid resource formset data re-renders the form without saving."""
    event.is_public = True
    event.feature_flags["speakers_can_edit_submissions"] = True
    event.save()
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


@pytest.mark.django_db
def test_submissions_edit_view_unchanged_resource_preserved(
    speaker_client, speaker_and_submission
):
    """A resource that is not modified or deleted is preserved as-is."""
    _, submission, _ = speaker_and_submission
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


@pytest.mark.django_db
def test_submissions_edit_view_uneditable_submission_shows_error(
    speaker_client, speaker_and_submission
):
    """POSTing to an uneditable submission returns an error message without saving."""
    _, submission, _ = speaker_and_submission
    with scopes_disabled():
        submission.accept()
        submission.event.feature_flags["speakers_can_edit_submissions"] = False
        submission.event.save()
    original_title = submission.title
    data = _edit_form_data(submission, title="Should Not Change")

    response = speaker_client.post(submission.urls.user_base, follow=False, data=data)

    assert response.status_code == 302
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.title == original_title


@pytest.mark.django_db
def test_submissions_edit_view_duration_change_updates_slot(
    speaker_client, speaker_and_submission
):
    """Changing the duration field updates the scheduled talk slot's end time."""
    _, submission, _ = speaker_and_submission
    with scopes_disabled():
        submission.duration = 30
        submission.save()
        submission.event.cfp.fields["duration"] = {"visibility": "optional"}
        submission.event.cfp.save()
        slot = TalkSlotFactory(submission=submission)
        original_end = slot.end
    data = _edit_form_data(submission, duration=45)

    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        slot.refresh_from_db()
        assert slot.end != original_end
        assert slot.end == slot.start + dt.timedelta(minutes=45)


@pytest.mark.django_db
def test_submissions_edit_view_track_change_updates_review_scores(
    speaker_client, speaker_and_submission
):
    """Changing the track recalculates review scores for that submission."""
    _, submission, _ = speaker_and_submission
    with scopes_disabled():
        submission.event.feature_flags["use_tracks"] = True
        submission.event.save()
        submission.event.cfp.fields["track"] = {"visibility": "optional"}
        submission.event.cfp.save()
        old_track = TrackFactory(event=submission.event, name="Old Track")
        new_track = TrackFactory(event=submission.event, name="New Track")
        submission.track = old_track
        submission.save()
        review = ReviewFactory(submission=submission)
        review.score = 5
        review.save(update_score=False)
    data = _edit_form_data(submission, track=new_track.pk)

    response = speaker_client.post(submission.urls.user_base, follow=True, data=data)

    assert response.status_code == 200
    with scopes_disabled():
        review.refresh_from_db()
        assert review.score is None


@pytest.mark.django_db
def test_submission_invite_view_get_warns_on_invalid_email_query_param(
    speaker_client, speaker_and_submission
):
    """GET with an invalid email in ?email= shows a warning message."""
    _, submission, _ = speaker_and_submission

    response = speaker_client.get(
        submission.urls.invite + "?email=not-an-email", follow=True
    )

    assert response.status_code == 200
    assert "valid email" in response.content.decode().lower()


@pytest.mark.django_db
def test_submission_invite_accept_view_rejects_when_speakers_disabled(client, event):
    """Cannot accept invitation when additional speakers are disabled."""
    event.is_public = True
    event.save()
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="other@example.com"
        )
        event.cfp.fields["additional_speaker"] = {"visibility": "do_not_ask"}
        event.cfp.save()
    other_user = UserFactory()
    client.force_login(other_user)

    response = client.post(invitation.urls.base.full(), follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert not submission.speakers.filter(user=other_user).exists()
