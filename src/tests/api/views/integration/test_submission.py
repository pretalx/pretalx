import json

import pytest
from django_scopes import scope, scopes_disabled

from pretalx.api.versions import LEGACY
from pretalx.common.exceptions import SubmissionError
from pretalx.submission.models import (
    Resource,
    Submission,
    SubmissionInvitation,
    SubmissionStates,
)
from pretalx.submission.models.submission import SubmissionFavourite
from pretalx.submission.signals import before_submission_state_change
from tests.factories import (
    ResourceFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TeamFactory,
    TrackFactory,
    UserApiTokenFactory,
    UserFactory,
)

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_submission_list_anonymous_sees_only_scheduled(
    client, public_event_with_schedule, published_talk_slot
):
    """Anonymous user sees only submissions in the released schedule."""
    event = public_event_with_schedule
    with scopes_disabled():
        SubmissionFactory(event=event)  # unscheduled, should not appear
    response = client.get(event.api_urls.submissions, follow=True)
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert content["results"][0]["title"] == published_talk_slot.submission.title


@pytest.mark.django_db
def test_submission_list_returns_401_when_schedule_not_public(client, event):
    """Returns 401 when show_schedule is disabled and no token auth."""
    event.feature_flags["show_schedule"] = False
    event.save()
    response = client.get(event.api_urls.submissions, follow=True)
    assert response.status_code == 401


@pytest.mark.django_db
def test_submission_list_orga_sees_all_submissions(
    client, event, orga_user_token, submission, other_submission
):
    """Orga with token sees all submissions regardless of schedule state."""
    response = client.get(
        event.api_urls.submissions,
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 2
    codes = {r["code"] for r in content["results"]}
    assert submission.code in codes
    assert other_submission.code in codes


@pytest.mark.django_db
def test_submission_list_orga_sees_submissions_when_not_public(
    client, event, orga_user_token, submission
):
    """Orga can still see submissions even if schedule is not public."""
    event.is_public = False
    event.feature_flags["show_schedule"] = False
    event.save()
    response = client.get(
        event.api_urls.submissions,
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_list_query_count(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    """Query count for submission list is constant regardless of item count."""
    with scopes_disabled():
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            sub = SubmissionFactory(event=event)
            sub.speakers.add(speaker)

    with django_assert_num_queries(22):
        response = client.get(
            event.api_urls.submissions,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count


@pytest.mark.django_db
def test_submission_list_orga_filter_by_state(
    client, event, orga_user_token, submission, rejected_submission
):
    """Filter ?state=rejected returns only rejected submissions."""
    response = client.get(
        event.api_urls.submissions + "?state=rejected",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert content["results"][0]["code"] == rejected_submission.code


@pytest.mark.django_db
def test_submission_retrieve_by_code(client, event, orga_user_token, submission):
    """Get single submission by code."""
    response = client.get(
        event.api_urls.submissions + f"{submission.code}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == submission.code
    assert data["title"] == submission.title
    assert data["state"] == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_submission_create_with_write_token(client, event, orga_user_write_token):
    """POST creates a submission, verify DB state and log."""
    with scopes_disabled():
        sub_type = event.cfp.default_type
    response = client.post(
        event.api_urls.submissions,
        follow=True,
        data=json.dumps(
            {
                "title": "New API Talk",
                "abstract": "A talk about APIs",
                "submission_type": sub_type.pk,
                "content_locale": event.locale,
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "New API Talk"
    with scopes_disabled():
        sub = Submission.objects.get(code=data["code"])
        assert sub.title == "New API Talk"
        assert sub.submission_type == sub_type
        assert (
            sub.logged_actions()
            .filter(action_type="pretalx.submission.create")
            .exists()
        )


@pytest.mark.django_db
def test_submission_create_wrong_locale_returns_400(
    client, event, orga_user_write_token
):
    """Invalid locale is rejected with 400."""
    with scopes_disabled():
        sub_type = event.cfp.default_type
    response = client.post(
        event.api_urls.submissions,
        follow=True,
        data=json.dumps(
            {
                "title": "Bad Locale Talk",
                "submission_type": sub_type.pk,
                "content_locale": "xx-invalid",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_submission_create_readonly_token_returns_403(client, event, orga_user_token):
    """Read-only token cannot create submissions."""
    with scopes_disabled():
        sub_type = event.cfp.default_type
        initial_count = event.submissions.count()
    response = client.post(
        event.api_urls.submissions,
        follow=True,
        data=json.dumps({"title": "Forbidden Talk", "submission_type": sub_type.pk}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert event.submissions.count() == initial_count


@pytest.mark.django_db
def test_submission_update_with_write_token(
    client, event, orga_user_write_token, submission
):
    """PATCH updates title, verify log with changes."""
    response = client.patch(
        event.api_urls.submissions + f"{submission.code}/",
        follow=True,
        data=json.dumps({"title": "Updated Title"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.title == "Updated Title"
        action = (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.update")
            .first()
        )
        assert action is not None
        assert "title" in action.data.get("changes", {})


@pytest.mark.django_db
def test_submission_update_readonly_token_returns_403(
    client, event, orga_user_token, submission
):
    """Read-only token cannot update submissions."""
    original_title = submission.title
    response = client.patch(
        event.api_urls.submissions + f"{submission.code}/",
        follow=True,
        data=json.dumps({"title": "Should Not Change"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.title == original_title


@pytest.mark.django_db
def test_submission_delete_with_write_token(
    client, event, orga_user_write_token, submission
):
    """DELETE removes submission."""
    code = submission.code
    response = client.delete(
        event.api_urls.submissions + f"{code}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert not Submission.objects.filter(code=code).exists()


@pytest.mark.django_db
def test_submission_accept_changes_state(
    client, event, orga_user_write_token, submission
):
    """POST accept changes state to accepted."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/accept/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_accept_readonly_token_returns_403(
    client, event, orga_user_token, submission
):
    """Read-only token cannot accept submissions."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/accept/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_submission_reject_changes_state(
    client, event, orga_user_write_token, submission
):
    """POST reject changes state to rejected."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/reject/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.REJECTED


@pytest.mark.django_db
def test_submission_reject_readonly_token_returns_403(
    client, event, orga_user_token, submission
):
    """Read-only token cannot reject submissions."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/reject/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_submission_confirm_changes_state(
    client, event, orga_user_write_token, accepted_submission
):
    """Confirm an accepted submission changes state to confirmed."""
    response = client.post(
        event.api_urls.submissions + f"{accepted_submission.code}/confirm/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        accepted_submission.refresh_from_db()
        assert accepted_submission.state == SubmissionStates.CONFIRMED


@pytest.mark.django_db
def test_submission_confirm_readonly_token_returns_403(
    client, event, orga_user_token, accepted_submission
):
    """Read-only token cannot confirm submissions."""
    response = client.post(
        event.api_urls.submissions + f"{accepted_submission.code}/confirm/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        accepted_submission.refresh_from_db()
        assert accepted_submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_cancel_changes_state(
    client, event, orga_user_write_token, accepted_submission
):
    """Cancel an accepted submission changes state to canceled."""
    response = client.post(
        event.api_urls.submissions + f"{accepted_submission.code}/cancel/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        accepted_submission.refresh_from_db()
        assert accepted_submission.state == SubmissionStates.CANCELED


@pytest.mark.django_db
def test_submission_cancel_readonly_token_returns_403(
    client, event, orga_user_token, accepted_submission
):
    """Read-only token cannot cancel submissions."""
    response = client.post(
        event.api_urls.submissions + f"{accepted_submission.code}/cancel/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        accepted_submission.refresh_from_db()
        assert accepted_submission.state == SubmissionStates.ACCEPTED


@pytest.mark.django_db
def test_submission_make_submitted_changes_state(
    client, event, orga_user_write_token, rejected_submission
):
    """Make a rejected submission submitted again."""
    response = client.post(
        event.api_urls.submissions + f"{rejected_submission.code}/make-submitted/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        rejected_submission.refresh_from_db()
        assert rejected_submission.state == SubmissionStates.SUBMITTED


@pytest.mark.django_db
def test_submission_make_submitted_readonly_token_returns_403(
    client, event, orga_user_token, rejected_submission
):
    """Read-only token cannot change submission to submitted."""
    response = client.post(
        event.api_urls.submissions + f"{rejected_submission.code}/make-submitted/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        rejected_submission.refresh_from_db()
        assert rejected_submission.state == SubmissionStates.REJECTED


@pytest.mark.django_db
def test_submission_add_speaker(client, event, orga_user_write_token, submission):
    """POST add-speaker with email adds a speaker to the submission."""
    new_email = "newspeaker@example.com"
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/add-speaker/",
        follow=True,
        data=json.dumps({"email": new_email}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        speaker_emails = [s.user.email for s in submission.speakers.all()]
        assert new_email in speaker_emails


@pytest.mark.django_db
def test_submission_add_speaker_readonly_token_returns_403(
    client, event, orga_user_token, submission
):
    """Read-only token cannot add speakers."""
    with scopes_disabled():
        initial_count = submission.speakers.count()
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/add-speaker/",
        follow=True,
        data=json.dumps({"email": "test@example.com"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert submission.speakers.count() == initial_count


@pytest.mark.django_db
def test_submission_remove_speaker(client, event, orga_user_write_token, submission):
    """POST remove-speaker with speaker code removes the speaker."""
    with scopes_disabled():
        speaker = submission.speakers.first()
        speaker_code = speaker.code
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/remove-speaker/",
        follow=True,
        data=json.dumps({"user": speaker_code}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert not submission.speakers.filter(code=speaker_code).exists()


@pytest.mark.django_db
def test_submission_remove_speaker_not_found_returns_400(
    client, event, orga_user_write_token, submission
):
    """Removing a non-existent speaker returns 400."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/remove-speaker/",
        follow=True,
        data=json.dumps({"user": "NONEXIST"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400
    assert "Speaker not found" in response.json()["detail"]


@pytest.mark.django_db
def test_submission_remove_speaker_readonly_token_returns_403(
    client, event, orga_user_token, submission
):
    """Read-only token cannot remove speakers."""
    with scopes_disabled():
        speaker = submission.speakers.first()
        speaker_code = speaker.code
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/remove-speaker/",
        follow=True,
        data=json.dumps({"user": speaker_code}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert submission.speakers.filter(code=speaker_code).exists()


@pytest.mark.django_db
def test_submission_invite_speaker(client, event, orga_user_write_token, submission):
    """POST invitations creates an invitation and logs the action."""
    email = "invited@example.com"
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data=json.dumps({"email": email}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert SubmissionInvitation.objects.filter(
            submission=submission, email=email
        ).exists()
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.invitation.send")
            .exists()
        )


@pytest.mark.django_db
def test_submission_invite_speaker_already_speaker_returns_400(
    client, event, orga_user_write_token, submission
):
    """Inviting someone who is already a speaker returns 400."""
    with scopes_disabled():
        speaker_email = submission.speakers.first().user.email
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data=json.dumps({"email": speaker_email}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400
    assert "already a speaker" in response.json()["detail"]


@pytest.mark.django_db
def test_submission_invite_speaker_already_invited_returns_400(
    client, event, orga_user_write_token, submission
):
    """Inviting someone who has already been invited returns 400."""
    email = "duplicate@example.com"
    with scopes_disabled():
        SubmissionInvitation.objects.create(submission=submission, email=email)
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data=json.dumps({"email": email}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400
    assert "already been invited" in response.json()["detail"]


@pytest.mark.django_db
def test_submission_invite_speaker_max_exceeded_returns_400(
    client, event, orga_user_write_token, submission
):
    """Inviting when max_speakers would be exceeded returns 400."""
    with scopes_disabled():
        cfp = event.cfp
        fields = cfp.fields or {}
        fields["additional_speaker"] = fields.get("additional_speaker", {})
        fields["additional_speaker"]["max"] = 1
        cfp.fields = fields
        cfp.save()
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data=json.dumps({"email": "overflow@example.com"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400
    assert "maximum" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_submission_invite_speaker_readonly_token_returns_403(
    client, event, orga_user_token, submission
):
    """Read-only token cannot invite speakers."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data=json.dumps({"email": "nope@example.com"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert not SubmissionInvitation.objects.filter(
            submission=submission, email="nope@example.com"
        ).exists()


@pytest.mark.django_db
def test_submission_retract_invitation(
    client, event, orga_user_write_token, submission
):
    """DELETE invitations/{id} retracts the invitation."""
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="retract@example.com"
        )
        invitation_id = invitation.pk
    response = client.delete(
        event.api_urls.submissions + f"{submission.code}/invitations/{invitation_id}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert not SubmissionInvitation.objects.filter(pk=invitation_id).exists()


@pytest.mark.django_db
def test_submission_retract_invitation_not_found_returns_404(
    client, event, orga_user_write_token, submission
):
    """Retracting a non-existent invitation returns 404."""
    response = client.delete(
        event.api_urls.submissions + f"{submission.code}/invitations/99999/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_submission_retract_invitation_readonly_token_returns_403(
    client, event, orga_user_token, submission
):
    """Read-only token cannot retract invitations."""
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.create(
            submission=submission, email="keep@example.com"
        )
    response = client.delete(
        event.api_urls.submissions + f"{submission.code}/invitations/{invitation.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert SubmissionInvitation.objects.filter(pk=invitation.pk).exists()


@pytest.mark.django_db
def test_submission_add_link_resource(client, event, orga_user_write_token, submission):
    """POST resources with a link creates a resource on the submission."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/resources/",
        follow=True,
        data=json.dumps(
            {"link": "https://example.com/slides", "description": "Slide deck"}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert submission.resources.filter(link="https://example.com/slides").exists()


@pytest.mark.django_db
def test_submission_add_resource_both_link_and_file_returns_400(
    client, event, orga_user_write_token, submission
):
    """Providing both link and resource returns 400."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/resources/",
        follow=True,
        data=json.dumps(
            {
                "link": "https://example.com/slides",
                "resource": "file:///fake",
                "description": "Both provided",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_submission_add_resource_neither_returns_400(
    client, event, orga_user_write_token, submission
):
    """Providing neither link nor resource returns 400."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/resources/",
        follow=True,
        data=json.dumps({"description": "No resource"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_submission_add_resource_readonly_token_returns_403(
    client, event, orga_user_token, submission
):
    """Read-only token cannot add resources."""
    with scopes_disabled():
        initial_count = submission.resources.count()
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/resources/",
        follow=True,
        data=json.dumps(
            {"link": "https://example.com/forbidden", "description": "Nope"}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert submission.resources.count() == initial_count


@pytest.mark.django_db
def test_submission_remove_resource(client, event, orga_user_write_token, submission):
    """DELETE resources/{id} removes the resource."""
    with scopes_disabled():
        resource = ResourceFactory(submission=submission)
        resource_id = resource.pk
    response = client.delete(
        event.api_urls.submissions + f"{submission.code}/resources/{resource_id}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert not Resource.objects.filter(pk=resource_id).exists()


@pytest.mark.django_db
def test_submission_remove_resource_not_found_returns_404(
    client, event, orga_user_write_token, submission
):
    """Removing a non-existent resource returns 404."""
    response = client.delete(
        event.api_urls.submissions + f"{submission.code}/resources/99999/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_submission_remove_resource_readonly_token_returns_403(
    client, event, orga_user_token, submission
):
    """Read-only token cannot remove resources."""
    with scopes_disabled():
        resource = ResourceFactory(submission=submission)
    response = client.delete(
        event.api_urls.submissions + f"{submission.code}/resources/{resource.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert Resource.objects.filter(pk=resource.pk).exists()


@pytest.mark.django_db
def test_submission_remove_resource_from_different_submission_returns_404(
    client, event, orga_user_write_token, submission, other_submission
):
    """Cannot remove a resource from a different submission."""
    with scopes_disabled():
        resource = ResourceFactory(submission=other_submission)
    response = client.delete(
        event.api_urls.submissions + f"{submission.code}/resources/{resource.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 404
    with scopes_disabled():
        assert Resource.objects.filter(pk=resource.pk).exists()


@pytest.mark.django_db
def test_submission_public_only_sees_public_resources(
    client, public_event_with_schedule, published_talk_slot
):
    """Anonymous user sees only public resources when expanding resources."""
    event = public_event_with_schedule
    with scopes_disabled():
        sub = published_talk_slot.submission
        ResourceFactory(submission=sub, link="https://example.com/public")
        ResourceFactory(
            submission=sub, link="https://example.com/private", is_public=False
        )
    response = client.get(
        event.api_urls.submissions + f"{sub.code}/?expand=resources", follow=True
    )
    assert response.status_code == 200
    data = response.json()
    resources = data["resources"]
    assert len(resources) == 1
    assert resources[0]["resource"] == "https://example.com/public"


@pytest.mark.django_db
def test_submission_orga_sees_all_resources(
    client, event, orga_user_write_token, submission
):
    """Orga sees both public and private resources."""
    with scopes_disabled():
        ResourceFactory(submission=submission, link="https://example.com/public")
        ResourceFactory(
            submission=submission, link="https://example.com/private", is_public=False
        )
    response = client.get(
        event.api_urls.submissions + f"{submission.code}/?expand=resources",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    resources = data["resources"]
    assert len(resources) == 2
    urls = {r["resource"] for r in resources}
    assert "https://example.com/public" in urls
    assert "https://example.com/private" in urls


@pytest.mark.django_db
def test_submission_log_orga_can_view(client, event, orga_user_write_token, submission):
    """Orga can view the log endpoint for a submission."""
    with scopes_disabled(), scope(event=event):
        submission.log_action("pretalx.test.action", data={"key": "val"})
    response = client.get(
        event.api_urls.submissions + f"{submission.code}/log/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["action_type"] == "pretalx.test.action"


@pytest.mark.django_db
def test_submission_expandable_fields(
    client, event, orga_user_write_token, submission, tag, track
):
    """Test expand=speakers,track,submission_type,tags returns nested objects."""
    with scopes_disabled():
        submission.tags.add(tag)
        submission.track = track
        submission.save()

    response = client.get(
        event.api_urls.submissions
        + f"{submission.code}/?expand=speakers,track,submission_type,tags",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["speakers"]) == 1
    assert "code" in data["speakers"][0]
    assert "name" in data["speakers"][0]
    assert isinstance(data["submission_type"], dict)
    assert data["submission_type"]["id"] == submission.submission_type_id
    assert len(data["tags"]) == 1
    assert data["tags"][0]["id"] == tag.pk
    assert isinstance(data["track"], dict)
    assert data["track"]["id"] == track.pk


@pytest.mark.django_db
def test_favourites_list_unauthenticated_returns_403(
    client, public_event_with_schedule
):
    """Unauthenticated user cannot list favourites."""
    event = public_event_with_schedule
    response = client.get(
        f"/api/events/{event.slug}/submissions/favourites/", follow=True
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_favourites_list_schedule_not_public_returns_403(client, event):
    """Logged in user gets 403 when schedule is hidden."""
    user = UserFactory()
    client.force_login(user)
    event.feature_flags["show_schedule"] = False
    event.save()
    response = client.get(
        f"/api/events/{event.slug}/submissions/favourites/", follow=True
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_favourites_list_empty(client, public_event_with_schedule):
    """Authenticated user with no favourites gets empty list."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    response = client.get(
        f"/api/events/{event.slug}/submissions/favourites/", follow=True
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_favourites_list_with_data(
    client, public_event_with_schedule, published_talk_slot
):
    """Authenticated user sees their favourited submission codes."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    with scopes_disabled():
        sub = published_talk_slot.submission
        SubmissionFavourite.objects.create(user=user, submission=sub)
    response = client.get(
        f"/api/events/{event.slug}/submissions/favourites/", follow=True
    )
    assert response.status_code == 200
    data = response.json()
    assert sub.code in data


@pytest.mark.django_db
def test_favourite_add_success(client, public_event_with_schedule, published_talk_slot):
    """POST favourite adds the submission to favourites."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    with scopes_disabled():
        sub = published_talk_slot.submission
    response = client.post(
        f"/api/events/{event.slug}/submissions/{sub.code}/favourite/", follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert SubmissionFavourite.objects.filter(user=user, submission=sub).exists()


@pytest.mark.django_db
def test_favourite_add_unauthenticated_returns_403(
    client, public_event_with_schedule, published_talk_slot
):
    """Unauthenticated user cannot add favourites."""
    event = public_event_with_schedule
    with scopes_disabled():
        sub = published_talk_slot.submission
    response = client.post(
        f"/api/events/{event.slug}/submissions/{sub.code}/favourite/", follow=True
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_favourite_add_nonexistent_returns_404(client, public_event_with_schedule):
    """Adding a non-existent submission as favourite returns 404."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    response = client.post(
        f"/api/events/{event.slug}/submissions/NONEXIST/favourite/", follow=True
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_favourite_remove_success(
    client, public_event_with_schedule, published_talk_slot
):
    """DELETE favourite removes the submission from favourites."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    with scopes_disabled():
        sub = published_talk_slot.submission
        SubmissionFavourite.objects.create(user=user, submission=sub)
    response = client.delete(
        f"/api/events/{event.slug}/submissions/{sub.code}/favourite/", follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert not SubmissionFavourite.objects.filter(
            user=user, submission=sub
        ).exists()


@pytest.mark.django_db
def test_tag_list_anonymous_returns_401(client, event, tag):
    """Anonymous user gets 401 for tags on non-public event."""
    response = client.get(event.api_urls.tags, follow=True)
    assert response.status_code == 401


@pytest.mark.django_db
def test_tag_list_orga(client, event, orga_user_token, tag):
    """Orga can list tags."""
    response = client.get(
        event.api_urls.tags,
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert content["results"][0]["id"] == tag.pk


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_tag_list_query_count(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    """Query count for tag list is constant regardless of item count."""
    for _ in range(item_count):
        TagFactory(event=event)

    with django_assert_num_queries(11):
        response = client.get(
            event.api_urls.tags,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count


@pytest.mark.django_db
def test_tag_detail(client, event, orga_user_token, tag):
    """Single tag detail endpoint works."""
    response = client.get(
        event.api_urls.tags + f"{tag.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tag.pk
    assert data["color"] == tag.color


@pytest.mark.django_db
def test_tag_detail_locale_override(client, event, orga_user_token, tag):
    """The ?lang= parameter makes i18n fields return a plain string."""
    response = client.get(
        event.api_urls.tags + f"{tag.pk}/?lang=en",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["tag"], str)


@pytest.mark.django_db
def test_tag_create_with_write_token(client, event, orga_user_write_token):
    """POST with write token creates a tag, verify DB state and log."""
    response = client.post(
        event.api_urls.tags,
        follow=True,
        data=json.dumps({"tag": "new-tag", "color": "#00ff00"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 201
    with scopes_disabled():
        created_tag = event.tags.get(tag="new-tag")
        assert created_tag.color == "#00ff00"
        assert (
            created_tag.logged_actions()
            .filter(action_type="pretalx.tag.create")
            .exists()
        )


@pytest.mark.django_db
def test_tag_create_duplicate_returns_400(client, event, orga_user_write_token, tag):
    """Creating a tag with a duplicate name returns 400."""
    response = client.post(
        event.api_urls.tags,
        follow=True,
        data=json.dumps({"tag": str(tag.tag), "color": "#ff0000"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_tag_create_readonly_token_returns_403(client, event, orga_user_token):
    """Read-only token cannot create tags."""
    response = client.post(
        event.api_urls.tags,
        follow=True,
        data=json.dumps({"tag": "forbidden-tag", "color": "#ff0000"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert not event.tags.filter(tag="forbidden-tag").exists()


@pytest.mark.django_db
def test_tag_update_with_write_token(client, event, orga_user_write_token, tag):
    """PATCH with write token updates the tag name."""
    response = client.patch(
        event.api_urls.tags + f"{tag.pk}/",
        follow=True,
        data=json.dumps({"tag": "updated-tag"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        tag.refresh_from_db()
        assert str(tag.tag) == "updated-tag"


@pytest.mark.django_db
def test_tag_update_readonly_token_returns_403(client, event, orga_user_token, tag):
    """Read-only token cannot update tags."""
    original_tag = str(tag.tag)
    response = client.patch(
        event.api_urls.tags + f"{tag.pk}/",
        follow=True,
        data=json.dumps({"tag": "should-not-change"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        tag.refresh_from_db()
        assert str(tag.tag) == original_tag


@pytest.mark.django_db
def test_tag_delete_with_write_token(client, event, orga_user_write_token, tag):
    """DELETE with write token removes the tag."""
    tag_pk = tag.pk
    response = client.delete(
        event.api_urls.tags + f"{tag_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert not event.tags.filter(pk=tag_pk).exists()


@pytest.mark.django_db
def test_tag_delete_readonly_token_returns_403(client, event, orga_user_token, tag):
    """Read-only token cannot delete tags."""
    response = client.delete(
        event.api_urls.tags + f"{tag.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert event.tags.filter(pk=tag.pk).exists()


@pytest.mark.django_db
def test_track_list_anonymous_returns_401(client, event, track):
    """Anonymous user gets 401 for tracks on non-public event."""
    response = client.get(event.api_urls.tracks, follow=True)
    assert response.status_code == 401


@pytest.mark.django_db
def test_track_list_public_event_shows_tracks(
    client, public_event_with_schedule, published_talk_slot
):
    """Public event with schedule shows tracks to anonymous users."""
    event = public_event_with_schedule
    with scopes_disabled():
        event.feature_flags["use_tracks"] = True
        event.save()
        TrackFactory(event=event)
    response = client.get(event.api_urls.tracks, follow=True)
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1


@pytest.mark.django_db
def test_track_list_orga(client, event, orga_user_token, track):
    """Orga can list tracks."""
    response = client.get(
        event.api_urls.tracks,
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_track_list_query_count(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    """Query count for track list is constant regardless of item count."""
    with scopes_disabled():
        event.feature_flags["use_tracks"] = True
        event.save()
    for _ in range(item_count):
        TrackFactory(event=event)

    with django_assert_num_queries(11):
        response = client.get(
            event.api_urls.tracks,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count


@pytest.mark.django_db
def test_track_detail(client, event, orga_user_token, track):
    """Single track detail endpoint works."""
    response = client.get(
        event.api_urls.tracks + f"{track.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == track.pk
    assert data["color"] == track.color


@pytest.mark.django_db
def test_track_detail_locale_override(client, event, orga_user_token, track):
    """The ?lang= parameter makes i18n fields return a plain string."""
    response = client.get(
        event.api_urls.tracks + f"{track.pk}/?lang=en",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["name"], str)


@pytest.mark.django_db
def test_track_create_with_write_token(client, event, orga_write_token):
    """POST with write token creates a track (requires can_change_event_settings)."""
    response = client.post(
        event.api_urls.tracks,
        follow=True,
        data=json.dumps({"name": "New Track", "color": "#0000ff"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )
    assert response.status_code == 201
    with scopes_disabled():
        created_track = event.tracks.get(name="New Track")
        assert created_track.color == "#0000ff"
        assert (
            created_track.logged_actions()
            .filter(action_type="pretalx.track.create")
            .exists()
        )


@pytest.mark.django_db
def test_track_create_readonly_token_returns_403(client, event, orga_user_token):
    """Read-only token cannot create tracks."""
    response = client.post(
        event.api_urls.tracks,
        follow=True,
        data=json.dumps({"name": "Forbidden Track", "color": "#0000ff"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert not event.tracks.filter(name="Forbidden Track").exists()


@pytest.mark.django_db
def test_track_update_with_write_token(client, event, orga_write_token, track):
    """PATCH with write token updates the track (requires can_change_event_settings)."""
    response = client.patch(
        event.api_urls.tracks + f"{track.pk}/",
        follow=True,
        data=json.dumps({"name": "Updated Track"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        track.refresh_from_db()
        assert str(track.name) == "Updated Track"


@pytest.mark.django_db
def test_track_update_readonly_token_returns_403(client, event, orga_user_token, track):
    """Read-only token cannot update tracks."""
    original_name = str(track.name)
    response = client.patch(
        event.api_urls.tracks + f"{track.pk}/",
        follow=True,
        data=json.dumps({"name": "Should Not Change"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        track.refresh_from_db()
        assert str(track.name) == original_name


@pytest.mark.django_db
def test_track_delete_with_write_token(client, event, orga_write_token, track):
    """DELETE with write token removes the track (requires can_change_event_settings)."""
    track_pk = track.pk
    response = client.delete(
        event.api_urls.tracks + f"{track_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert not event.tracks.filter(pk=track_pk).exists()


@pytest.mark.django_db
def test_track_delete_readonly_token_returns_403(client, event, orga_user_token, track):
    """Read-only token cannot delete tracks."""
    response = client.delete(
        event.api_urls.tracks + f"{track.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert event.tracks.filter(pk=track.pk).exists()


@pytest.mark.django_db
def test_track_no_legacy_api(client, event, orga_user_token, track):
    """Legacy API version returns 400 for tracks."""
    from pretalx.api.versions import LEGACY  # noqa: PLC0415

    response = client.get(
        event.api_urls.tracks + f"{track.pk}/",
        follow=True,
        headers={
            "Authorization": f"Token {orga_user_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_submission_type_list_anonymous_returns_401_when_not_public(client, event):
    """Anonymous user gets 401 for submission types on non-public event."""
    response = client.get(event.api_urls.submission_types, follow=True)
    assert response.status_code == 401


@pytest.mark.django_db
def test_submission_type_list_public_event(
    client, public_event_with_schedule, published_talk_slot
):
    """Public event with schedule shows submission types to anonymous users."""
    event = public_event_with_schedule
    response = client.get(event.api_urls.submission_types, follow=True)
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1


@pytest.mark.django_db
def test_submission_type_list_orga(client, event, orga_user_token, submission_type):
    """Orga can list submission types."""
    response = client.get(
        event.api_urls.submission_types,
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 2


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_type_list_query_count(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    """Query count for submission type list is constant regardless of item count."""
    for _ in range(item_count):
        SubmissionTypeFactory(event=event)

    with django_assert_num_queries(11):
        response = client.get(
            event.api_urls.submission_types,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )
    assert response.status_code == 200
    content = response.json()
    # item_count + 1 for the default_type
    assert content["count"] == item_count + 1


@pytest.mark.django_db
def test_submission_type_detail(client, event, orga_user_token):
    """Single submission type detail endpoint works."""
    with scopes_disabled():
        sub_type = event.cfp.default_type
    response = client.get(
        event.api_urls.submission_types + f"{sub_type.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sub_type.pk
    assert data["default_duration"] == sub_type.default_duration


@pytest.mark.django_db
def test_submission_type_detail_locale_override(client, event, orga_user_token):
    """The ?lang= parameter makes i18n fields return a plain string."""
    with scopes_disabled():
        sub_type = event.cfp.default_type
    response = client.get(
        event.api_urls.submission_types + f"{sub_type.pk}/?lang=en",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["name"], str)


@pytest.mark.django_db
def test_submission_type_create_with_write_token(client, event, orga_write_token):
    """POST with write token creates a submission type (requires can_change_event_settings)."""
    response = client.post(
        event.api_urls.submission_types,
        follow=True,
        data=json.dumps({"name": "Lightning Talk", "default_duration": 5}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )
    assert response.status_code == 201
    with scopes_disabled():
        created_type = event.submission_types.get(name="Lightning Talk")
        assert created_type.default_duration == 5
        assert (
            created_type.logged_actions()
            .filter(action_type="pretalx.submission_type.create")
            .exists()
        )


@pytest.mark.django_db
def test_submission_type_create_readonly_token_returns_403(
    client, event, orga_user_token
):
    """Read-only token cannot create submission types."""
    response = client.post(
        event.api_urls.submission_types,
        follow=True,
        data=json.dumps({"name": "Forbidden Type", "default_duration": 30}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert not event.submission_types.filter(name="Forbidden Type").exists()


@pytest.mark.django_db
def test_submission_type_update_with_write_token(
    client, event, orga_write_token, submission_type
):
    """PATCH with write token updates the submission type (requires can_change_event_settings)."""
    response = client.patch(
        event.api_urls.submission_types + f"{submission_type.pk}/",
        follow=True,
        data=json.dumps({"name": "Updated Type"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission_type.refresh_from_db()
        assert str(submission_type.name) == "Updated Type"


@pytest.mark.django_db
def test_submission_type_update_readonly_token_returns_403(
    client, event, orga_user_token, submission_type
):
    """Read-only token cannot update submission types."""
    original_name = str(submission_type.name)
    response = client.patch(
        event.api_urls.submission_types + f"{submission_type.pk}/",
        follow=True,
        data=json.dumps({"name": "Should Not Change"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        submission_type.refresh_from_db()
        assert str(submission_type.name) == original_name


@pytest.mark.django_db
def test_submission_type_delete_with_write_token(
    client, event, orga_write_token, submission_type
):
    """DELETE with write token removes the submission type (requires can_change_event_settings)."""
    type_pk = submission_type.pk
    response = client.delete(
        event.api_urls.submission_types + f"{type_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert not event.submission_types.filter(pk=type_pk).exists()


@pytest.mark.django_db
def test_submission_type_no_legacy_api(client, event, orga_user_token):
    """Legacy API version returns 400 for submission types."""
    from pretalx.api.versions import LEGACY  # noqa: PLC0415

    with scopes_disabled():
        sub_type = event.cfp.default_type
    response = client.get(
        event.api_urls.submission_types + f"{sub_type.pk}/",
        follow=True,
        headers={
            "Authorization": f"Token {orga_user_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action_url", "starting_state"),
    (
        ("accept", SubmissionStates.SUBMITTED),
        ("reject", SubmissionStates.SUBMITTED),
        ("confirm", SubmissionStates.ACCEPTED),
        ("cancel", SubmissionStates.ACCEPTED),
        ("make-submitted", SubmissionStates.ACCEPTED),
    ),
)
def test_submission_state_change_signal_rejection_returns_400(
    client,
    event,
    orga_user_write_token,
    submission,
    register_signal_handler,
    action_url,
    starting_state,
):
    """Signal handler raising SubmissionError causes any state change to return 400."""
    if starting_state != SubmissionStates.SUBMITTED:
        with scopes_disabled():
            submission.accept()

    def reject_transition(signal, sender, **kwargs):
        raise SubmissionError("Blocked by signal")

    register_signal_handler(before_submission_state_change, reject_transition)
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/{action_url}/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400
    assert "Blocked by signal" in response.json()["detail"]


@pytest.mark.django_db
def test_submission_legacy_api_list(client, event, orga_user_token, submission):
    """Legacy API version returns submissions list."""
    from pretalx.api.versions import LEGACY  # noqa: PLC0415

    response = client.get(
        event.api_urls.submissions,
        follow=True,
        headers={
            "Authorization": f"Token {orga_user_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1


@pytest.mark.django_db
def test_submission_legacy_api_detail(client, event, orga_user_token, submission):
    """Legacy API version returns submission detail."""
    from pretalx.api.versions import LEGACY  # noqa: PLC0415

    response = client.get(
        event.api_urls.submissions + f"{submission.code}/",
        follow=True,
        headers={
            "Authorization": f"Token {orga_user_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == submission.code


@pytest.mark.django_db
def test_submission_legacy_api_anonymous_with_schedule(
    client, public_event_with_schedule, published_talk_slot
):
    """Anonymous user with legacy API can see published submissions."""
    from pretalx.api.versions import LEGACY  # noqa: PLC0415

    event = public_event_with_schedule
    response = client.get(
        event.api_urls.submissions, follow=True, headers={"Pretalx-Version": LEGACY}
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1


@pytest.mark.django_db
def test_favourite_add_schedule_not_public_returns_403(
    client, public_event_with_schedule, published_talk_slot
):
    """favourite_view returns 403 when schedule is hidden."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    event.feature_flags["show_schedule"] = False
    event.save()
    with scopes_disabled():
        sub = published_talk_slot.submission
    response = client.post(
        f"/api/events/{event.slug}/submissions/{sub.code}/favourite/", follow=True
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_submission_expand_speakers_user(
    client, event, orga_user_write_token, submission
):
    """Expanding speakers.user includes user data in the response."""
    response = client.get(
        event.api_urls.submissions + f"{submission.code}/?expand=speakers.user",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["speakers"]) == 1


@pytest.mark.django_db
def test_submission_expand_answers_question(
    client, event, orga_user_write_token, submission
):
    """Expanding answers.question includes question data in the response."""
    response = client.get(
        event.api_urls.submissions + f"{submission.code}/?expand=answers.question",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_submission_invite_speaker_within_max_speakers(
    client, event, orga_user_write_token, submission
):
    """Inviting when max_speakers is set but not exceeded succeeds."""
    with scopes_disabled():
        cfp = event.cfp
        fields = cfp.fields or {}
        fields["additional_speaker"] = fields.get("additional_speaker", {})
        fields["additional_speaker"]["max"] = 5
        cfp.fields = fields
        cfp.save()
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data=json.dumps({"email": "within-limit@example.com"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert SubmissionInvitation.objects.filter(
            submission=submission, email="within-limit@example.com"
        ).exists()


@pytest.mark.django_db
def test_submission_legacy_api_anonymous_no_schedule_returns_401(client, event):
    """Anonymous legacy API request with no released schedule returns 401.

    Even on a public event, anonymous users need a released schedule to
    access the submissions endpoint.
    """
    event.is_public = True
    event.save()
    response = client.get(
        event.api_urls.submissions, follow=True, headers={"Pretalx-Version": LEGACY}
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_submission_legacy_api_reviewer_serializer(client, event, submission):
    """Reviewer user with legacy API gets the reviewer serializer (no answers field)."""
    from pretalx.api.versions import LEGACY  # noqa: PLC0415
    from pretalx.person.models.auth_token import ENDPOINTS  # noqa: PLC0415
    from tests.factories import UserApiTokenFactory  # noqa: PLC0415

    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            is_reviewer=True,
            can_change_submissions=False,
        )
        team.members.add(user)
        token = UserApiTokenFactory(user=user)
        token.events.add(event)
        token.endpoints = dict.fromkeys(ENDPOINTS, ["list", "retrieve"])
        token.save()

    response = client.get(
        event.api_urls.submissions,
        follow=True,
        headers={"Authorization": f"Token {token.token}", "Pretalx-Version": LEGACY},
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    result = content["results"][0]
    # Reviewer serializer inherits all orga fields including created and answers
    assert "answers" in result
    assert "created" in result
    assert result["code"] == submission.code


@pytest.mark.django_db
def test_submission_legacy_api_anon_param(client, event, orga_user_token, submission):
    """Legacy API ?anon param hides speaker data."""
    from pretalx.api.versions import LEGACY  # noqa: PLC0415

    response = client.get(
        event.api_urls.submissions + "?anon=1",
        follow=True,
        headers={
            "Authorization": f"Token {orga_user_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    result = content["results"][0]
    assert result["speakers"] == []


@pytest.mark.django_db
def test_submission_orga_filter_by_track(
    client, event, orga_user_token, submission, other_submission, track
):
    """Filter ?track=<id> returns only submissions on that track."""
    with scopes_disabled():
        submission.track = track
        submission.save()

    response = client.get(
        event.api_urls.submissions + f"?track={track.pk}",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert content["results"][0]["code"] == submission.code


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_visible_to_reviewers", "is_reviewer", "expected_answer_count"),
    ((True, True, 1), (False, True, 0), (True, False, 1), (False, False, 1)),
)
def test_submission_answer_visibility_to_reviewers(
    client,
    event,
    orga_user_token,
    review_user,
    submission,
    answer,
    is_visible_to_reviewers,
    is_reviewer,
    expected_answer_count,
):
    """Answer visibility is filtered by is_visible_to_reviewers for reviewers."""
    from pretalx.person.models.auth_token import ENDPOINTS  # noqa: PLC0415

    with scopes_disabled():
        review_token = UserApiTokenFactory(user=review_user)
        review_token.events.add(event)
        review_token.endpoints = dict.fromkeys(ENDPOINTS, ["list", "retrieve"])
        review_token.save()

    token = review_token if is_reviewer else orga_user_token
    with scope(event=event):
        question = answer.question
        question.is_visible_to_reviewers = is_visible_to_reviewers
        question.save()

    response = client.get(
        event.api_urls.submissions + "?expand=answers.question",
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert len(content["results"][0]["answers"]) == expected_answer_count


@pytest.mark.django_db
def test_submission_reviewer_log_access(client, event, submission):
    """Reviewer with appropriate permissions can access the submission log."""
    from pretalx.person.models.auth_token import ENDPOINTS  # noqa: PLC0415

    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            is_reviewer=True,
            can_change_submissions=False,
        )
        team.members.add(user)
        token = UserApiTokenFactory(user=user)
        token.events.add(event)
        token.endpoints = dict.fromkeys(
            ENDPOINTS, ["list", "retrieve", "create", "update", "destroy", "actions"]
        )
        token.save()

    with scopes_disabled(), scope(event=event):
        submission.log_action("pretalx.submission.update", data={"note": "Reviewed"})

    response = client.get(
        event.api_urls.submissions + f"{submission.code}/log/",
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_submission_log_pagination(client, event, orga_user_write_token, submission):
    """Log endpoint supports pagination when many entries exist."""
    with scopes_disabled(), scope(event=event):
        for i in range(3):
            submission.log_action(
                f"pretalx.submission.update.{i}", data={"iteration": i}
            )

    response = client.get(
        event.api_urls.submissions + f"{submission.code}/log/?page_size=2",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 3
    assert content["next"] is not None
    assert len(content["results"]) == 2


@pytest.mark.django_db
def test_submission_expand_invitations(
    client, event, orga_user_write_token, submission
):
    """Expanding invitations returns invitation objects with email, id, created."""
    with scopes_disabled():
        SubmissionInvitation.objects.create(
            submission=submission, email="expandtest@example.com"
        )

    response = client.get(
        event.api_urls.submissions + "?expand=invitations",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    sub_data = next(s for s in content["results"] if s["code"] == submission.code)
    assert len(sub_data["invitations"]) == 1
    assert sub_data["invitations"][0]["email"] == "expandtest@example.com"
    assert "id" in sub_data["invitations"][0]
    assert "created" in sub_data["invitations"][0]


@pytest.mark.django_db
def test_favourite_remove_not_favourited(
    client, public_event_with_schedule, published_talk_slot
):
    """Removing a favourite that doesn't exist succeeds gracefully."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    with scopes_disabled():
        sub = published_talk_slot.submission
    response = client.delete(
        f"/api/events/{event.slug}/submissions/{sub.code}/favourite/", follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert not SubmissionFavourite.objects.filter(
            user=user, submission=sub
        ).exists()


@pytest.mark.django_db
def test_submission_type_delete_readonly_token_returns_403(
    client, event, orga_user_token, submission_type
):
    """Read-only token cannot delete submission types."""
    response = client.delete(
        event.api_urls.submission_types + f"{submission_type.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert event.submission_types.filter(pk=submission_type.pk).exists()


@pytest.mark.django_db
def test_submission_legacy_api_with_expanded_speakers(
    client, public_event_with_schedule, published_talk_slot, orga_user_token
):
    """Legacy API with speakers expanded returns speaker name and biography."""
    event = public_event_with_schedule
    response = client.get(
        event.api_urls.submissions,
        follow=True,
        headers={
            "Authorization": f"Token {orga_user_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] >= 1
    result = next(
        r
        for r in content["results"]
        if r["code"] == published_talk_slot.submission.code
    )
    assert isinstance(result["speakers"], list)
    assert len(result["speakers"]) >= 1
    assert "name" in result["speakers"][0]
    assert "biography" in result["speakers"][0]


@pytest.mark.django_db
def test_reviewer_cannot_see_submissions_in_anonymised_phase(
    client, event, orga_user_write_token, submission
):
    """When anonymisation is active, reviewers get 403 but orgas see data normally."""
    from pretalx.person.models.auth_token import ENDPOINTS  # noqa: PLC0415

    with scopes_disabled():
        reviewer = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            is_reviewer=True,
            can_change_submissions=False,
        )
        team.members.add(reviewer)
        review_token = UserApiTokenFactory(user=reviewer)
        review_token.events.add(event)
        review_token.endpoints = dict.fromkeys(ENDPOINTS, ["list", "retrieve"])
        review_token.save()

    with scope(event=event):
        phase = event.active_review_phase
        phase.can_see_speaker_names = False
        phase.save()

    # Orga still sees submissions
    response = client.get(
        event.api_urls.submissions,
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert len(content["results"][0]["speakers"]) == 1

    # Reviewer gets 403 during anonymised phase
    response = client.get(
        event.api_urls.submissions,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_submission_add_file_resource(client, event, orga_user_write_token, submission):
    """Orga can add a file resource via CachedFile upload."""
    from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: PLC0415
    from django.utils import timezone  # noqa: PLC0415

    from pretalx.common.models import CachedFile  # noqa: PLC0415

    f = SimpleUploadedFile(
        "testfile.pdf", b"test content", content_type="application/pdf"
    )
    cached_file = CachedFile.objects.create(
        session_key=f"api-upload-{orga_user_write_token.token}",
        filename="testfile.pdf",
        content_type="application/pdf",
        expires=timezone.now() + timezone.timedelta(hours=1),
    )
    cached_file.file.save("testfile.pdf", f)
    cached_file.save()

    response = client.post(
        event.api_urls.submissions + f"{submission.code}/resources/",
        follow=True,
        data=json.dumps(
            {
                "resource": f"file:{cached_file.pk}",
                "description": "Uploaded slides",
                "is_public": False,
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200, response.text
    with scope(event=event):
        submission.refresh_from_db()
        assert submission.resources.count() == 1
        resource = submission.resources.first()
        assert resource.resource is not None
        assert resource.description == "Uploaded slides"
        assert resource.is_public is False


@pytest.mark.django_db
def test_submission_remove_resource_with_file_cleans_up(
    client, event, orga_user_write_token, submission
):
    """Removing a resource with an actual file also deletes the file from storage."""
    from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: PLC0415

    f = SimpleUploadedFile("testresource.txt", b"a resource")
    with scopes_disabled():
        resource = Resource.objects.create(
            submission=submission,
            resource=f,
            description="File resource",
            is_public=True,
        )
    resource_id = resource.pk
    file_path = resource.resource.path
    assert resource.resource.storage.exists(file_path)

    response = client.delete(
        event.api_urls.submissions + f"{submission.code}/resources/{resource_id}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert not Resource.objects.filter(pk=resource_id).exists()
    assert not resource.resource.storage.exists(file_path)


@pytest.mark.django_db
def test_submission_public_with_expanded_speakers(
    client, public_event_with_schedule, published_talk_slot
):
    """Anonymous user sees public talks with expanded speakers showing name and biography."""
    event = public_event_with_schedule
    response = client.get(event.api_urls.submissions + "?expand=speakers", follow=True)
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert content["results"][0]["title"] == published_talk_slot.submission.title
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()
        assert (
            content["results"][0]["speakers"][0]["name"] == speaker.get_display_name()
        )
        assert content["results"][0]["speakers"][0]["biography"] == speaker.biography


@pytest.mark.django_db
def test_submission_public_expandable_fields(
    client, public_event_with_schedule, published_talk_slot, track, answer
):
    """Anonymous user on a public event can expand speakers, track, answers, and submission_type."""
    event = public_event_with_schedule
    with scopes_disabled():
        sub = published_talk_slot.submission
        sub.track = track
        sub.save()
        answer.submission = sub
        answer.save()
        answer.question.is_public = True
        answer.question.target = "submission"
        answer.question.save()

    expand_fields = "track,submission_type,speakers,answers,answers.question"
    response = client.get(
        event.api_urls.submissions + f"?expand={expand_fields}", follow=True
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    result = content["results"][0]

    with scopes_disabled():
        assert result["track"]["name"]["en"] == sub.track.name
        assert result["submission_type"]["name"]["en"] == sub.submission_type.name
        speaker = sub.speakers.first()
        assert result["speakers"][0]["name"] == speaker.get_display_name()
        assert "email" not in result["speakers"]
        assert len(result["answers"]) == 1
        assert result["answers"][0]["question"]["id"] == answer.question_id
