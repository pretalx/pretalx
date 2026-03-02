# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django_scopes import scope, scopes_disabled

from pretalx.api.versions import LEGACY
from pretalx.common.exceptions import SubmissionError
from pretalx.person.models.auth_token import ENDPOINTS
from pretalx.submission.models import (
    Resource,
    Submission,
    SubmissionInvitation,
    SubmissionStates,
)
from pretalx.submission.models.question import QuestionRequired, QuestionVariant
from pretalx.submission.models.submission import SubmissionFavourite
from pretalx.submission.signals import before_submission_state_change
from tests.factories import (
    AnswerFactory,
    CachedFileFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    SubmissionFavouriteFactory,
    SubmissionInvitationFactory,
    SubmissionTypeFactory,
    TagFactory,
    TeamFactory,
    TrackFactory,
    UserApiTokenFactory,
    UserFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


# These token fixtures intentionally use `organiser_user` (default team
# permissions) rather than the api-level `orga_user` fixture which grants
# can_change_submissions + can_change_event_settings.  Submission tests
# need to verify behaviour under standard organiser permissions.


@pytest.fixture
def orga_user_token(organiser_user):
    """Read-only API token for the organiser user."""
    return UserApiTokenFactory(
        user=organiser_user,
        events=list(organiser_user.get_events_with_any_permission()),
        endpoints=dict.fromkeys(ENDPOINTS, ["list", "retrieve"]),
    )


@pytest.fixture
def orga_user_write_token(organiser_user):
    """Read-write API token for the organiser user."""
    return UserApiTokenFactory(
        user=organiser_user,
        events=list(organiser_user.get_events_with_any_permission()),
        endpoints=dict.fromkeys(
            ENDPOINTS, ["list", "retrieve", "create", "update", "destroy", "actions"]
        ),
    )


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


def test_submission_list_returns_401_when_schedule_not_public(client):
    """Returns 401 when show_schedule is disabled and no token auth."""
    event = EventFactory(feature_flags={"show_schedule": False})
    response = client.get(event.api_urls.submissions, follow=True)
    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_list_orga_sees_all_submissions(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    """Orga with token sees all submissions, with constant query count."""
    with scopes_disabled():
        roles = SpeakerRoleFactory.create_batch(
            item_count, submission__event=event, speaker__event=event
        )

    with django_assert_num_queries(22):
        response = client.get(
            event.api_urls.submissions,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count
    codes = {r["code"] for r in content["results"]}
    for role in roles:
        assert role.submission.code in codes


def test_submission_list_orga_sees_submissions_when_not_public(
    client, event, orga_user_token, submission
):
    """Orga can still see submissions even if schedule is not public."""
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


def test_submission_list_orga_filter_by_state(
    client, event, orga_user_token, submission
):
    """Filter ?state=rejected returns only rejected submissions."""
    with scopes_disabled():
        rejected = SpeakerRoleFactory(
            submission__event=event, speaker__event=event
        ).submission
        rejected.reject()

    response = client.get(
        event.api_urls.submissions + "?state=rejected",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert content["results"][0]["code"] == rejected.code


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


def test_submission_create_with_write_token(client, event, orga_user_write_token):
    """POST creates a submission, verify DB state and log."""
    with scopes_disabled():
        sub_type = event.cfp.default_type
    response = client.post(
        event.api_urls.submissions,
        follow=True,
        data={
            "title": "New API Talk",
            "abstract": "A talk about APIs",
            "submission_type": sub_type.pk,
            "content_locale": event.locale,
        },
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


def test_submission_create_wrong_locale_returns_400(
    client, event, orga_user_write_token
):
    """Invalid locale is rejected with 400."""
    with scopes_disabled():
        sub_type = event.cfp.default_type
    response = client.post(
        event.api_urls.submissions,
        follow=True,
        data={
            "title": "Bad Locale Talk",
            "submission_type": sub_type.pk,
            "content_locale": "xx-invalid",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400


def test_submission_create_readonly_token_returns_403(client, event, orga_user_token):
    """Read-only token cannot create submissions."""
    with scopes_disabled():
        sub_type = event.cfp.default_type
        initial_count = event.submissions.count()
    response = client.post(
        event.api_urls.submissions,
        follow=True,
        data={"title": "Forbidden Talk", "submission_type": sub_type.pk},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert event.submissions.count() == initial_count


def test_submission_update_with_write_token(
    client, event, orga_user_write_token, submission
):
    """PATCH updates title, verify log with changes."""
    response = client.patch(
        event.api_urls.submissions + f"{submission.code}/",
        follow=True,
        data={"title": "Updated Title"},
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


def test_submission_confirm_changes_state(client, event, orga_user_write_token):
    """Confirm an accepted submission changes state to confirmed."""
    with scopes_disabled():
        sub = SpeakerRoleFactory(
            submission__event=event, speaker__event=event
        ).submission
        sub.accept()

    response = client.post(
        event.api_urls.submissions + f"{sub.code}/confirm/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        sub.refresh_from_db()
        assert sub.state == SubmissionStates.CONFIRMED


def test_submission_cancel_changes_state(client, event, orga_user_write_token):
    """Cancel an accepted submission changes state to canceled."""
    with scopes_disabled():
        sub = SpeakerRoleFactory(
            submission__event=event, speaker__event=event
        ).submission
        sub.accept()

    response = client.post(
        event.api_urls.submissions + f"{sub.code}/cancel/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        sub.refresh_from_db()
        assert sub.state == SubmissionStates.CANCELED


def test_submission_make_submitted_changes_state(client, event, orga_user_write_token):
    """Make a rejected submission submitted again."""
    with scopes_disabled():
        sub = SpeakerRoleFactory(
            submission__event=event, speaker__event=event
        ).submission
        sub.reject()

    response = client.post(
        event.api_urls.submissions + f"{sub.code}/make-submitted/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        sub.refresh_from_db()
        assert sub.state == SubmissionStates.SUBMITTED


def test_submission_add_speaker(client, event, orga_user_write_token, submission):
    """POST add-speaker with email adds a speaker to the submission."""
    new_email = "newspeaker@example.com"
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/add-speaker/",
        follow=True,
        data={"email": new_email},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        speaker_emails = [s.user.email for s in submission.speakers.all()]
        assert new_email in speaker_emails


def test_submission_remove_speaker(client, event, orga_user_write_token, submission):
    """POST remove-speaker with speaker code removes the speaker."""
    with scopes_disabled():
        speaker = submission.speakers.first()
        speaker_code = speaker.code
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/remove-speaker/",
        follow=True,
        data={"user": speaker_code},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert not submission.speakers.filter(code=speaker_code).exists()


def test_submission_remove_speaker_not_found_returns_400(
    client, event, orga_user_write_token, submission
):
    """Removing a non-existent speaker returns 400."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/remove-speaker/",
        follow=True,
        data={"user": "NONEXIST"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400
    assert "Speaker not found" in response.json()["detail"]


def test_submission_invite_speaker(client, event, orga_user_write_token, submission):
    """POST invitations creates an invitation and logs the action."""
    email = "invited@example.com"
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data={"email": email},
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


def test_submission_invite_speaker_already_speaker_returns_400(
    client, event, orga_user_write_token, submission
):
    """Inviting someone who is already a speaker returns 400."""
    with scopes_disabled():
        speaker_email = submission.speakers.first().user.email
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data={"email": speaker_email},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400
    assert "already a speaker" in response.json()["detail"]


def test_submission_invite_speaker_already_invited_returns_400(
    client, event, orga_user_write_token, submission
):
    """Inviting someone who has already been invited returns 400."""
    email = "duplicate@example.com"
    with scopes_disabled():
        SubmissionInvitationFactory(submission=submission, email=email)
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data={"email": email},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400
    assert "already been invited" in response.json()["detail"]


def test_submission_invite_speaker_max_exceeded_returns_400(
    client, event, orga_user_write_token, submission
):
    """Inviting when max_speakers would be exceeded returns 400."""
    with scopes_disabled():
        event.cfp.fields["additional_speaker"]["max"] = 1
        event.cfp.save()
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data={"email": "overflow@example.com"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400
    assert "maximum" in response.json()["detail"].lower()


def test_submission_retract_invitation(
    client, event, orga_user_write_token, submission
):
    """DELETE invitations/{id} retracts the invitation."""
    with scopes_disabled():
        invitation = SubmissionInvitationFactory(
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


def test_submission_add_link_resource(client, event, orga_user_write_token, submission):
    """POST resources with a link creates a resource on the submission."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/resources/",
        follow=True,
        data={"link": "https://example.com/slides", "description": "Slide deck"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert submission.resources.filter(link="https://example.com/slides").exists()


def test_submission_add_resource_both_link_and_file_returns_400(
    client, event, orga_user_write_token, submission
):
    """Providing both link and resource returns 400."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/resources/",
        follow=True,
        data={
            "link": "https://example.com/slides",
            "resource": "file:///fake",
            "description": "Both provided",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400


def test_submission_add_resource_neither_returns_400(
    client, event, orga_user_write_token, submission
):
    """Providing neither link nor resource returns 400."""
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/resources/",
        follow=True,
        data={"description": "No resource"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400


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


def test_submission_expandable_fields(client, event, orga_user_write_token, track):
    """Test expand=speakers,track,submission_type,tags returns nested objects."""
    tag = TagFactory(event=event)
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event, submission__track=track, speaker__event=event
        )
        submission = role.submission
        submission.tags.add(tag)

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


def test_favourites_list_unauthenticated_returns_403(
    client, public_event_with_schedule
):
    """Unauthenticated user cannot list favourites."""
    event = public_event_with_schedule
    response = client.get(
        f"/api/events/{event.slug}/submissions/favourites/", follow=True
    )
    assert response.status_code == 403


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


def test_favourites_list_with_data(
    client, public_event_with_schedule, published_talk_slot
):
    """Authenticated user sees their favourited submission codes."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    with scopes_disabled():
        sub = published_talk_slot.submission
        SubmissionFavouriteFactory(user=user, submission=sub)
    response = client.get(
        f"/api/events/{event.slug}/submissions/favourites/", follow=True
    )
    assert response.status_code == 200
    data = response.json()
    assert sub.code in data


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


def test_favourite_add_nonexistent_returns_404(client, public_event_with_schedule):
    """Adding a non-existent submission as favourite returns 404."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    response = client.post(
        f"/api/events/{event.slug}/submissions/NONEXIST/favourite/", follow=True
    )
    assert response.status_code == 404


def test_favourites_list_no_schedule_permission_returns_403(client, event):
    """Authenticated user without schedule.list_schedule gets 403."""
    user = UserFactory()
    client.force_login(user)

    response = client.get(f"/api/events/{event.slug}/submissions/favourites/")

    assert response.status_code == 403


def test_favourite_add_no_schedule_permission_returns_403(client, event, submission):
    """Authenticated user without schedule.list_schedule gets 403 on add."""
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        f"/api/events/{event.slug}/submissions/{submission.code}/favourite/"
    )

    assert response.status_code == 403


def test_favourite_remove_success(
    client, public_event_with_schedule, published_talk_slot
):
    """DELETE favourite removes the submission from favourites."""
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    with scopes_disabled():
        sub = published_talk_slot.submission
        SubmissionFavouriteFactory(user=user, submission=sub)
    response = client.delete(
        f"/api/events/{event.slug}/submissions/{sub.code}/favourite/", follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert not SubmissionFavourite.objects.filter(
            user=user, submission=sub
        ).exists()


def test_tag_list_anonymous_returns_401(client, event):
    """Anonymous user gets 401 for tags on non-public event."""
    TagFactory(event=event)
    response = client.get(event.api_urls.tags, follow=True)
    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_tag_list_orga(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    """Orga can list tags, with constant query count."""
    tags = TagFactory.create_batch(item_count, event=event)

    with django_assert_num_queries(11):
        response = client.get(
            event.api_urls.tags,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count
    tag_ids = {r["id"] for r in content["results"]}
    for tag in tags:
        assert tag.pk in tag_ids


def test_tag_detail(client, event, orga_user_token):
    """Single tag detail endpoint works."""
    tag = TagFactory(event=event)
    response = client.get(
        event.api_urls.tags + f"{tag.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tag.pk
    assert data["color"] == tag.color


def test_tag_detail_locale_override(client, event, orga_user_token):
    """The ?lang= parameter makes i18n fields return a plain string."""
    tag = TagFactory(event=event)
    response = client.get(
        event.api_urls.tags + f"{tag.pk}/?lang=en",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["tag"], str)


def test_tag_create_with_write_token(client, event, orga_user_write_token):
    """POST with write token creates a tag, verify DB state and log."""
    response = client.post(
        event.api_urls.tags,
        follow=True,
        data={"tag": "new-tag", "color": "#00ff00"},
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


def test_tag_create_duplicate_returns_400(client, event, orga_user_write_token):
    """Creating a tag with a duplicate name returns 400."""
    tag = TagFactory(event=event)
    response = client.post(
        event.api_urls.tags,
        follow=True,
        data={"tag": str(tag.tag), "color": "#ff0000"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 400


def test_tag_create_readonly_token_returns_403(client, event, orga_user_token):
    """Read-only token cannot create tags."""
    response = client.post(
        event.api_urls.tags,
        follow=True,
        data={"tag": "forbidden-tag", "color": "#ff0000"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert not event.tags.filter(tag="forbidden-tag").exists()


def test_tag_update_with_write_token(client, event, orga_user_write_token):
    """PATCH with write token updates the tag name."""
    tag = TagFactory(event=event)
    response = client.patch(
        event.api_urls.tags + f"{tag.pk}/",
        follow=True,
        data={"tag": "updated-tag"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        tag.refresh_from_db()
        assert str(tag.tag) == "updated-tag"


def test_tag_delete_with_write_token(client, event, orga_user_write_token):
    """DELETE with write token removes the tag."""
    tag = TagFactory(event=event)
    tag_pk = tag.pk
    response = client.delete(
        event.api_urls.tags + f"{tag_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert not event.tags.filter(pk=tag_pk).exists()


def test_track_list_anonymous_returns_401(client, event, track):
    """Anonymous user gets 401 for tracks on non-public event."""
    response = client.get(event.api_urls.tracks, follow=True)
    assert response.status_code == 401


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


@pytest.mark.parametrize("item_count", (1, 3))
def test_track_list_orga(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    """Orga can list tracks, with constant query count."""
    tracks = TrackFactory.create_batch(item_count, event=event)

    with django_assert_num_queries(12):
        response = client.get(
            event.api_urls.tracks,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count
    track_ids = {r["id"] for r in content["results"]}
    for t in tracks:
        assert t.pk in track_ids


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


def test_track_create_with_write_token(client, event, orga_write_token):
    """POST with write token creates a track (requires can_change_event_settings)."""
    response = client.post(
        event.api_urls.tracks,
        follow=True,
        data={"name": "New Track", "color": "#0000ff"},
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


def test_track_create_readonly_token_returns_403(client, event, orga_user_token):
    """Read-only token cannot create tracks."""
    response = client.post(
        event.api_urls.tracks,
        follow=True,
        data={"name": "Forbidden Track", "color": "#0000ff"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert not event.tracks.filter(name="Forbidden Track").exists()


def test_track_update_with_write_token(client, event, orga_write_token, track):
    """PATCH with write token updates the track (requires can_change_event_settings)."""
    response = client.patch(
        event.api_urls.tracks + f"{track.pk}/",
        follow=True,
        data={"name": "Updated Track"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        track.refresh_from_db()
        assert str(track.name) == "Updated Track"


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


def test_track_no_legacy_api(client, event, orga_user_token, track):
    """Legacy API version returns 400 for tracks."""

    response = client.get(
        event.api_urls.tracks + f"{track.pk}/",
        follow=True,
        headers={
            "Authorization": f"Token {orga_user_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )
    assert response.status_code == 400


def test_submission_type_list_anonymous_returns_401_when_not_public(client):
    """Anonymous user gets 401 for submission types on non-public event."""
    event = EventFactory(is_public=False)
    response = client.get(event.api_urls.submission_types, follow=True)
    assert response.status_code == 401


def test_submission_type_list_public_event(
    client, public_event_with_schedule, published_talk_slot
):
    """Public event with schedule shows submission types to anonymous users."""
    event = public_event_with_schedule
    response = client.get(event.api_urls.submission_types, follow=True)
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_type_list_orga(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    """Orga can list submission types, with constant query count."""
    types = SubmissionTypeFactory.create_batch(item_count, event=event)

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
    type_ids = {r["id"] for r in content["results"]}
    for st in types:
        assert st.pk in type_ids


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


def test_submission_type_create_with_write_token(client, event, orga_write_token):
    """POST with write token creates a submission type (requires can_change_event_settings)."""
    response = client.post(
        event.api_urls.submission_types,
        follow=True,
        data={"name": "Lightning Talk", "default_duration": 5},
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


def test_submission_type_create_readonly_token_returns_403(
    client, event, orga_user_token
):
    """Read-only token cannot create submission types."""
    response = client.post(
        event.api_urls.submission_types,
        follow=True,
        data={"name": "Forbidden Type", "default_duration": 30},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 403
    with scopes_disabled():
        assert not event.submission_types.filter(name="Forbidden Type").exists()


def test_submission_type_update_with_write_token(client, event, orga_write_token):
    """PATCH with write token updates the submission type (requires can_change_event_settings)."""
    submission_type = SubmissionTypeFactory(
        event=event, name="Workshop", default_duration=60
    )
    response = client.patch(
        event.api_urls.submission_types + f"{submission_type.pk}/",
        follow=True,
        data={"name": "Updated Type"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        submission_type.refresh_from_db()
        assert str(submission_type.name) == "Updated Type"


def test_submission_type_delete_with_write_token(client, event, orga_write_token):
    """DELETE with write token removes the submission type (requires can_change_event_settings)."""
    submission_type = SubmissionTypeFactory(
        event=event, name="Workshop", default_duration=60
    )
    type_pk = submission_type.pk
    response = client.delete(
        event.api_urls.submission_types + f"{type_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )
    assert response.status_code == 204
    with scopes_disabled():
        assert not event.submission_types.filter(pk=type_pk).exists()


def test_submission_type_no_legacy_api(client, event, orga_user_token):
    """Legacy API version returns 400 for submission types."""

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


def test_submission_legacy_api_list(client, event, orga_user_token, submission):
    """Legacy API version returns submissions list."""

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


def test_submission_legacy_api_detail(client, event, orga_user_token, submission):
    """Legacy API version returns submission detail."""

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


def test_submission_legacy_api_anonymous_with_schedule(
    client, public_event_with_schedule, published_talk_slot
):
    """Anonymous user with legacy API can see published submissions."""

    event = public_event_with_schedule
    response = client.get(
        event.api_urls.submissions, follow=True, headers={"Pretalx-Version": LEGACY}
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1


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


def test_submission_invite_speaker_within_max_speakers(
    client, event, orga_user_write_token, submission
):
    """Inviting when max_speakers is set but not exceeded succeeds."""
    with scopes_disabled():
        event.cfp.fields["additional_speaker"]["max"] = 5
        event.cfp.save()
    response = client.post(
        event.api_urls.submissions + f"{submission.code}/invitations/",
        follow=True,
        data={"email": "within-limit@example.com"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert SubmissionInvitation.objects.filter(
            submission=submission, email="within-limit@example.com"
        ).exists()


def test_submission_legacy_api_reviewer_serializer(client, event, submission):
    """Reviewer user with legacy API gets the reviewer serializer (no answers field)."""
    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            is_reviewer=True,
            can_change_submissions=False,
        )
        team.members.add(user)
        token = UserApiTokenFactory(
            user=user,
            events=[event],
            endpoints=dict.fromkeys(ENDPOINTS, ["list", "retrieve"]),
        )

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


def test_submission_legacy_api_anon_param(client, event, orga_user_token, submission):
    """Legacy API ?anon param hides speaker data."""

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


def test_submission_orga_filter_by_track(
    client, event, orga_user_token, other_submission, track
):
    """Filter ?track=<id> returns only submissions on that track."""
    submission = SubmissionFactory(event=event, track=track)

    response = client.get(
        event.api_urls.submissions + f"?track={track.pk}",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert content["results"][0]["code"] == submission.code


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
    is_visible_to_reviewers,
    is_reviewer,
    expected_answer_count,
):
    """Answer visibility is filtered by is_visible_to_reviewers for reviewers."""

    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            is_visible_to_reviewers=is_visible_to_reviewers,
        )
        AnswerFactory(question=question, submission=submission, answer="42")
        review_token = UserApiTokenFactory(
            user=review_user,
            events=[event],
            endpoints=dict.fromkeys(ENDPOINTS, ["list", "retrieve"]),
        )

    token = review_token if is_reviewer else orga_user_token

    response = client.get(
        event.api_urls.submissions + "?expand=answers.question",
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )
    content = response.json()
    assert response.status_code == 200
    assert content["count"] == 1
    assert len(content["results"][0]["answers"]) == expected_answer_count


def test_submission_reviewer_log_access(client, event, submission):
    """Reviewer with appropriate permissions can access the submission log."""

    with scopes_disabled():
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            is_reviewer=True,
            can_change_submissions=False,
        )
        team.members.add(user)
        token = UserApiTokenFactory(
            user=user,
            events=[event],
            endpoints=dict.fromkeys(
                ENDPOINTS,
                ["list", "retrieve", "create", "update", "destroy", "actions"],
            ),
        )

    with scopes_disabled(), scope(event=event):
        submission.log_action("pretalx.submission.update", data={"note": "Reviewed"})

    response = client.get(
        event.api_urls.submissions + f"{submission.code}/log/",
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )
    assert response.status_code == 200


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


def test_submission_expand_invitations(
    client, event, orga_user_write_token, submission
):
    """Expanding invitations returns invitation objects with email, id, created."""
    with scopes_disabled():
        SubmissionInvitationFactory(
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


def test_reviewer_cannot_see_submissions_in_anonymised_phase(
    client, event, orga_user_write_token, submission
):
    """When anonymisation is active, reviewers get 403 but orgas see data normally."""

    with scopes_disabled():
        reviewer = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            is_reviewer=True,
            can_change_submissions=False,
        )
        team.members.add(reviewer)
        review_token = UserApiTokenFactory(
            user=reviewer,
            events=[event],
            endpoints=dict.fromkeys(ENDPOINTS, ["list", "retrieve"]),
        )

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


def test_submission_add_file_resource(client, event, orga_user_write_token, submission):
    """Orga can add a file resource via CachedFile upload."""

    f = SimpleUploadedFile(
        "testfile.pdf", b"test content", content_type="application/pdf"
    )
    cached_file = CachedFileFactory(
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
        data={
            "resource": f"file:{cached_file.pk}",
            "description": "Uploaded slides",
            "is_public": False,
        },
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


def test_submission_remove_resource_with_file_cleans_up(
    client, event, orga_user_write_token, submission
):
    """Removing a resource with an actual file also deletes the file from storage."""

    f = SimpleUploadedFile("testresource.txt", b"a resource")
    with scopes_disabled():
        resource = ResourceFactory(
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


def test_submission_public_expandable_fields(
    client, public_event_with_schedule, published_talk_slot, track
):
    """Anonymous user on a public event can expand speakers, track, answers, and submission_type."""
    event = public_event_with_schedule
    with scopes_disabled():
        sub = published_talk_slot.submission
        sub.track = track
        sub.save()
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            is_public=True,
        )
        answer = AnswerFactory(question=question, submission=sub, answer="42")

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
