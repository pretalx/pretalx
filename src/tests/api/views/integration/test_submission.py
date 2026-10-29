# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django_scopes import scope, scopes_disabled

from pretalx.common.exceptions import SubmissionError
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile
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
    AttendeeProfileFactory,
    AttendeeSignupFactory,
    AvailabilityFactory,
    CachedFileFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    SpeakerFactory,
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
    return UserApiTokenFactory(
        user=organiser_user,
        limit_events=list(organiser_user.get_events_with_any_permission()),
        endpoints=dict.fromkeys(ENDPOINTS, ["list", "retrieve"]),
    )


@pytest.fixture
def orga_user_write_token(organiser_user):
    return UserApiTokenFactory(
        user=organiser_user,
        limit_events=list(organiser_user.get_events_with_any_permission()),
        endpoints=dict.fromkeys(
            ENDPOINTS, ["list", "retrieve", "create", "update", "destroy", "actions"]
        ),
    )


ORGA_ONLY_SUBMISSION_FIELDS = (
    "access_code",
    "review_code",
    "anonymised_data",
    "reviews",
    "assigned_reviewers",
    "mean_score",
    "median_score",
    "invitations",
)


def test_submission_public_reads(
    client, public_event_with_schedule, published_talk_slot, track
):
    event = public_event_with_schedule
    with scopes_disabled():
        SubmissionFactory(event=event)  # unscheduled, should not appear
        sub = published_talk_slot.submission
        sub.track = track
        sub.save()
        speaker = sub.speakers.select_related("user").first()
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.NUMBER,
            target="submission",
            question_required=QuestionRequired.OPTIONAL,
            is_public=True,
        )
        answer = AnswerFactory(question=question, submission=sub, answer="42")
        ResourceFactory(submission=sub, link="https://example.com/public")
        ResourceFactory(
            submission=sub, link="https://example.com/private", is_public=False
        )
        AttendeeSignupFactory(submission=sub)

    listing = client.get(event.api_urls.submissions, follow=True)
    expanded = client.get(
        event.api_urls.submissions
        + "?expand=track,submission_type,speakers,answers,answers.question,resources",
        follow=True,
    )
    attendees = client.get(event.api_urls.submissions + f"{sub.code}/attendees/")

    assert listing.status_code == 200
    assert [r["code"] for r in listing.json()["results"]] == [sub.code]
    assert listing.json()["results"][0]["title"] == sub.title
    assert expanded.status_code == 200
    assert [r["code"] for r in expanded.json()["results"]] == [sub.code]
    result = expanded.json()["results"][0]
    assert result["track"]["name"]["en"] == track.name
    assert result["submission_type"]["name"]["en"] == sub.submission_type.name
    assert [s["name"] for s in result["speakers"]] == [speaker.get_display_name()]
    assert result["speakers"][0]["biography"] == speaker.biography
    assert "email" not in result["speakers"][0]
    assert [a["id"] for a in result["answers"]] == [answer.pk]
    assert result["answers"][0]["question"]["id"] == question.pk
    assert [r["resource"] for r in result["resources"]] == [
        "https://example.com/public"
    ]
    assert attendees.status_code == 401


def test_submission_list_returns_401_when_schedule_not_public(client):
    event = EventFactory(feature_flags={"show_schedule": False})
    response = client.get(event.api_urls.submissions, follow=True)
    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_list_orga_sees_all_submissions(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    with scopes_disabled():
        roles = SpeakerRoleFactory.create_batch(
            item_count, submission__event=event, speaker__event=event
        )

    with django_assert_num_queries(20):
        response = client.get(
            event.api_urls.submissions,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert {r["code"] for r in content["results"]} == {
        role.submission.code for role in roles
    }


def test_submission_list_orga_filters(
    client, event, orga_user_token, submission, track
):
    event.feature_flags["show_schedule"] = False
    event.feature_flags["attendee_signup"] = True
    event.save()
    with scopes_disabled():
        submission.attendee_signup_required = True
        submission.attendee_signup_capacity = 5
        submission.save()
        rejected = SpeakerRoleFactory(
            submission__event=event, speaker__event=event
        ).submission
        rejected.reject()
        tracked = SubmissionFactory(event=event, track=track)
    headers = {"Authorization": f"Token {orga_user_token.token}"}

    listing = client.get(event.api_urls.submissions, follow=True, headers=headers)
    by_state = client.get(
        event.api_urls.submissions + "?state=rejected", follow=True, headers=headers
    )
    by_track = client.get(
        event.api_urls.submissions + f"?track={track.pk}", follow=True, headers=headers
    )

    assert listing.status_code == 200
    results = {r["code"]: r for r in listing.json()["results"]}
    assert set(results) == {submission.code, rejected.code, tracked.code}
    assert results[submission.code]["signup_status"] == "open"
    assert by_state.status_code == 200
    assert [r["code"] for r in by_state.json()["results"]] == [rejected.code]
    assert by_track.status_code == 200
    assert [r["code"] for r in by_track.json()["results"]] == [tracked.code]


@pytest.mark.parametrize("casing", ("upper", "lower"))
def test_submission_retrieve_by_code(
    client, event, orga_user_token, submission, casing
):
    code = submission.code.upper() if casing == "upper" else submission.code.lower()
    response = client.get(
        event.api_urls.submissions + f"{code}/",
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == submission.code
    assert data["title"] == submission.title
    assert data["state"] == SubmissionStates.SUBMITTED


def test_submission_create_with_write_token(client, event, orga_user_write_token):
    with scopes_disabled():
        sub_type = event.cfp.default_type
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

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
        headers=headers,
    )
    bad_locale = client.post(
        event.api_urls.submissions,
        follow=True,
        data={
            "title": "Bad Locale Talk",
            "submission_type": sub_type.pk,
            "content_locale": "xx-invalid",
        },
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "New API Talk"
    with scopes_disabled():
        sub = Submission.objects.get(code=data["code"])
        assert sub.title == "New API Talk"
        assert sub.submission_type_id == sub_type.pk
        assert (
            sub.logged_actions()
            .filter(action_type="pretalx.submission.create")
            .exists()
        )
    assert bad_locale.status_code == 400
    assert "content_locale" in bad_locale.json()
    with scopes_disabled():
        assert not Submission.objects.filter(title="Bad Locale Talk").exists()


def test_submission_create_readonly_token_returns_403(client, event, orga_user_token):
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


def test_submission_update_and_delete_with_write_token(
    client, event, orga_user_write_token, submission
):
    url = event.api_urls.submissions + f"{submission.code}/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.patch(
        url,
        follow=True,
        data={"title": "Updated Title"},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.title == "Updated Title"
        action = submission.logged_actions().get(
            action_type="pretalx.submission.update"
        )
        assert "title" in action.data["changes"]

    response = client.delete(url, follow=True, headers=headers)

    assert response.status_code == 204
    with scopes_disabled():
        assert not Submission.objects.filter(code=submission.code).exists()


def test_submission_update_pending_state_and_signup_required(
    client, event, orga_user_write_token, submission
):
    with scopes_disabled():
        AttendeeSignupFactory(submission=submission)
    url = event.api_urls.submissions + f"{submission.code}/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.patch(
        url,
        data={"pending_state": SubmissionStates.ACCEPTED},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == SubmissionStates.SUBMITTED
        assert submission.pending_state == SubmissionStates.ACCEPTED
        assert (
            event.wip_schedule.talks.filter(submission=submission).count()
            == submission.slot_count
        )

    same_as_state = client.patch(
        url,
        data={"pending_state": SubmissionStates.SUBMITTED},
        content_type="application/json",
        headers=headers,
    )

    assert same_as_state.status_code == 400
    assert "pending_state" in same_as_state.json()
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.pending_state == SubmissionStates.ACCEPTED

    with_signups = client.patch(
        url,
        data={"attendee_signup_required": False},
        content_type="application/json",
        headers=headers,
    )

    assert with_signups.status_code == 400
    assert "attendee_signup_required" in with_signups.json()


def test_submission_state_change_actions(
    client, event, orga_user_write_token, submission
):
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    for action, expected_state in (
        ("accept", SubmissionStates.ACCEPTED),
        ("confirm", SubmissionStates.CONFIRMED),
        ("cancel", SubmissionStates.CANCELED),
        ("make-submitted", SubmissionStates.SUBMITTED),
        ("reject", SubmissionStates.REJECTED),
    ):
        response = client.post(
            event.api_urls.submissions + f"{submission.code}/{action}/",
            follow=True,
            content_type="application/json",
            headers=headers,
        )

        assert response.status_code == 200, action
        with scopes_disabled():
            submission.refresh_from_db()
            assert submission.state == expected_state, action


def test_submission_add_speaker_by_email(
    client, event, orga_user_write_token, submission
):
    new_email = "newspeaker@example.com"
    with scopes_disabled():
        existing = SpeakerFactory(
            event=event,
            user=None,
            email="known@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
        profile_count = SpeakerProfile.objects.filter(event=event).count()
    url = event.api_urls.submissions + f"{submission.code}/add-speaker/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.post(
        url,
        follow=True,
        data={"email": new_email},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        new_speaker = submission.speakers.get(email=new_email)
        assert new_speaker.user is None
        assert new_speaker.invitation_token is None
        assert not event.queued_mails.exists()
        assert SpeakerProfile.objects.filter(event=event).count() == profile_count + 1

    reused = client.post(
        url,
        follow=True,
        data={"email": "known@example.com"},
        content_type="application/json",
        headers=headers,
    )

    assert reused.status_code == 200
    with scopes_disabled():
        assert existing in submission.speakers.all()
        assert SpeakerProfile.objects.filter(event=event).count() == profile_count + 1


def test_submission_add_speaker_by_code_next_version(
    client, event, orga_user_write_token, submission
):
    with scopes_disabled():
        bare = SpeakerFactory(
            event=event,
            user=None,
            name="Bare Speaker",
            origin=SpeakerProfileOrigin.ORGA,
        )
        cfp_leftover = SpeakerFactory(
            event=event, name="Draft Leftover", origin=SpeakerProfileOrigin.CFP
        )
    url = event.api_urls.submissions + f"{submission.code}/add-speaker/"
    headers = {
        "Authorization": f"Token {orga_user_write_token.token}",
        "Pretalx-Version": "v-next",
    }

    response = client.post(
        url,
        follow=True,
        data={"speaker": bare.code},
        content_type="application/json",
        headers=headers,
    )
    by_email = client.post(
        url,
        follow=True,
        data={"email": "newspeaker@example.com"},
        content_type="application/json",
        headers=headers,
    )
    unknown = [
        client.post(
            url,
            follow=True,
            data={"speaker": code},
            content_type="application/json",
            headers=headers,
        )
        for code in ("NOCODE", cfp_leftover.code)
    ]

    assert response.status_code == 200
    with scopes_disabled():
        assert bare in submission.speakers.all()
        assert not event.queued_mails.exists()
    assert by_email.status_code == 400
    assert "speaker" in by_email.json()
    for rejected in unknown:
        assert rejected.status_code == 400
        assert "Speaker not found" in rejected.json()["detail"]
    with scopes_disabled():
        assert submission.speakers.count() == 2


def test_submission_orga_expandable_fields(
    client, event, orga_user_write_token, submission, track
):
    with scopes_disabled():
        submission.track = track
        submission.save()
        tag = TagFactory(event=event)
        submission.tags.add(tag)
        speaker = submission.speakers.first()
        managed = SpeakerRoleFactory(
            submission=submission,
            speaker__event=event,
            speaker__user=None,
            speaker__name="Managed Speaker",
        ).speaker
        invitation = SubmissionInvitationFactory(
            submission=submission, email="expandtest@example.com"
        )
        ResourceFactory(submission=submission, link="https://example.com/public")
        ResourceFactory(
            submission=submission, link="https://example.com/private", is_public=False
        )

    response = client.get(
        event.api_urls.submissions
        + f"{submission.code}/?expand=speakers,track,submission_type,tags,"
        + "invitations,resources",
        follow=True,
        headers={"Authorization": f"Token {orga_user_write_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    speakers = {s["code"]: s for s in data["speakers"]}
    assert set(speakers) == {speaker.code, managed.code}
    assert speakers[managed.code]["name"] == "Managed Speaker"
    assert speakers[managed.code]["email"] is None
    assert data["submission_type"]["id"] == submission.submission_type_id
    assert [t["id"] for t in data["tags"]] == [tag.pk]
    assert data["track"]["id"] == track.pk
    assert [(i["id"], i["email"]) for i in data["invitations"]] == [
        (invitation.pk, "expandtest@example.com")
    ]
    assert {r["resource"] for r in data["resources"]} == {
        "https://example.com/public",
        "https://example.com/private",
    }


def test_submission_remove_speaker(client, event, orga_user_write_token, submission):
    with scopes_disabled():
        speaker_code = submission.speakers.first().code
    url = event.api_urls.submissions + f"{submission.code}/remove-speaker/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.post(
        url,
        follow=True,
        data={"user": speaker_code},
        content_type="application/json",
        headers=headers,
    )
    missing = client.post(
        url,
        follow=True,
        data={"user": "NONEXIST"},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert not submission.speakers.filter(code=speaker_code).exists()
    assert missing.status_code == 400
    assert "Speaker not found" in missing.json()["detail"]


def test_submission_invitation_lifecycle(
    client, event, orga_user_write_token, submission
):
    email = "invited@example.com"
    with scopes_disabled():
        event.cfp.fields["additional_speaker"]["max"] = 2
        event.cfp.save()
        speaker_email = submission.speakers.select_related("user").first().user.email
    url = event.api_urls.submissions + f"{submission.code}/invitations/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.post(
        url,
        follow=True,
        data={"email": email},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        invitation = SubmissionInvitation.objects.get(submission=submission)
        assert invitation.email == email
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.invitation.send")
            .exists()
        )

    already_invited = client.post(
        url,
        follow=True,
        data={"email": email},
        content_type="application/json",
        headers=headers,
    )
    already_speaker = client.post(
        url,
        follow=True,
        data={"email": speaker_email},
        content_type="application/json",
        headers=headers,
    )

    assert already_invited.status_code == 400
    assert "already been invited" in already_invited.json()["detail"]
    assert already_speaker.status_code == 400
    assert "already a speaker" in already_speaker.json()["detail"]
    with scopes_disabled():
        assert SubmissionInvitation.objects.filter(submission=submission).count() == 1

    retracted = client.delete(url + f"{invitation.pk}/", follow=True, headers=headers)
    missing = client.delete(url + f"{invitation.pk}/", follow=True, headers=headers)

    assert retracted.status_code == 204
    assert missing.status_code == 404
    with scopes_disabled():
        assert not SubmissionInvitation.objects.filter(pk=invitation.pk).exists()
        event.cfp.fields["additional_speaker"]["max"] = 1
        event.cfp.save()

    overflow = client.post(
        url,
        follow=True,
        data={"email": "overflow@example.com"},
        content_type="application/json",
        headers=headers,
    )

    assert overflow.status_code == 400
    assert "maximum" in overflow.json()["detail"].lower()


def test_submission_link_resource_lifecycle(
    client, event, orga_user_write_token, submission, other_submission
):
    with scopes_disabled():
        foreign = ResourceFactory(submission=other_submission)
    url = event.api_urls.submissions + f"{submission.code}/resources/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.post(
        url,
        follow=True,
        data={"link": "https://example.com/slides", "description": "Slide deck"},
        content_type="application/json",
        headers=headers,
    )
    both = client.post(
        url,
        follow=True,
        data={
            "link": "https://example.com/slides",
            "resource": "file:///fake",
            "description": "Both provided",
        },
        content_type="application/json",
        headers=headers,
    )
    neither = client.post(
        url,
        follow=True,
        data={"description": "No resource"},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    assert both.status_code == 400
    assert neither.status_code == 400
    with scopes_disabled():
        resource = submission.resources.get()
        assert resource.link == "https://example.com/slides"

    removed = client.delete(url + f"{resource.pk}/", follow=True, headers=headers)
    missing = client.delete(url + f"{resource.pk}/", follow=True, headers=headers)
    foreign_removed = client.delete(
        url + f"{foreign.pk}/", follow=True, headers=headers
    )

    assert removed.status_code == 204
    assert missing.status_code == 404
    assert foreign_removed.status_code == 404
    with scopes_disabled():
        assert not Resource.objects.filter(pk=resource.pk).exists()
        assert Resource.objects.filter(pk=foreign.pk).exists()


def test_submission_file_resource_lifecycle(
    client, event, orga_user_write_token, submission, django_capture_on_commit_callbacks
):
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
    url = event.api_urls.submissions + f"{submission.code}/resources/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.post(
        url,
        follow=True,
        data={
            "resource": f"file:{cached_file.pk}",
            "description": "Uploaded slides",
            "is_public": False,
        },
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    with scope(event=event):
        resource = submission.resources.get()
        assert resource.description == "Uploaded slides"
        assert resource.is_public is False
        file_path = resource.resource.path
        assert resource.resource.name.startswith(
            f"{event.slug}/submissions/{submission.code}/resources/"
        )
        cached_file.file.delete(save=False)
        with resource.resource.open("rb") as stored:
            assert stored.read() == b"test content"
        assert resource.resource.storage.exists(file_path)

    with django_capture_on_commit_callbacks(execute=True):
        removed = client.delete(url + f"{resource.pk}/", follow=True, headers=headers)

    assert removed.status_code == 204
    with scopes_disabled():
        assert not Resource.objects.filter(pk=resource.pk).exists()
    assert not resource.resource.storage.exists(file_path)


def test_submission_log_orga_can_view(client, event, orga_user_write_token, submission):
    with scopes_disabled(), scope(event=event):
        for i in range(3):
            submission.log_action(
                f"pretalx.submission.update.{i}", data={"iteration": i}
            )
    url = event.api_urls.submissions + f"{submission.code}/log/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.get(url, follow=True, headers=headers)
    paginated = client.get(url + "?page_size=2", follow=True, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert {r["action_type"] for r in data["results"]} == {
        f"pretalx.submission.update.{i}" for i in range(3)
    }
    assert paginated.status_code == 200
    assert paginated.json()["count"] == 3
    assert paginated.json()["next"] is not None
    assert len(paginated.json()["results"]) == 2


def test_favourites_and_signups_anonymous_returns_403(
    client, public_event_with_schedule, published_talk_slot
):
    event = public_event_with_schedule
    with scopes_disabled():
        sub = published_talk_slot.submission

    favourites = client.get(
        f"/api/events/{event.slug}/submissions/favourites/", follow=True
    )
    added = client.post(
        f"/api/events/{event.slug}/submissions/{sub.code}/favourite/", follow=True
    )
    signups = client.get(f"/api/events/{event.slug}/submissions/signups/", follow=True)

    assert favourites.status_code == 403
    assert added.status_code == 403
    assert signups.status_code == 403


def test_favourite_lifecycle(client, public_event_with_schedule, published_talk_slot):
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    with scopes_disabled():
        sub = published_talk_slot.submission
    list_url = f"/api/events/{event.slug}/submissions/favourites/"
    url = f"/api/events/{event.slug}/submissions/{sub.code}/favourite/"

    empty = client.get(list_url, follow=True)
    removed_before_add = client.delete(url, follow=True)

    assert empty.status_code == 200
    assert empty.json() == []
    assert removed_before_add.status_code == 200

    with scopes_disabled():
        SubmissionFavouriteFactory(user=user, submission=sub)
    listed = client.get(list_url, follow=True)
    removed = client.delete(url, follow=True)

    assert listed.status_code == 200
    assert listed.json() == [sub.code]
    assert removed.status_code == 200
    with scopes_disabled():
        assert not SubmissionFavourite.objects.filter(
            user=user, submission=sub
        ).exists()

    added = client.post(url, follow=True)
    unknown = client.post(
        f"/api/events/{event.slug}/submissions/NONEXIST/favourite/", follow=True
    )

    assert added.status_code == 200
    with scopes_disabled():
        assert SubmissionFavourite.objects.filter(user=user, submission=sub).exists()
    assert unknown.status_code == 404


def test_favourite_as_reviewer(client, public_event_with_schedule, published_talk_slot):
    event = public_event_with_schedule
    user = UserFactory()
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            is_reviewer=True,
            can_change_submissions=False,
        )
        team.members.add(user)
        event.review_phases.update(is_active=False)
        sub = published_talk_slot.submission
    client.force_login(user)

    added = client.post(
        f"/api/events/{event.slug}/submissions/{sub.code}/favourite/", follow=True
    )
    listed = client.get(
        f"/api/events/{event.slug}/submissions/favourites/", follow=True
    )

    assert added.status_code == 200
    with scopes_disabled():
        assert SubmissionFavourite.objects.filter(user=user, submission=sub).exists()
    assert listed.status_code == 200
    assert listed.json() == [sub.code]


def test_favourites_and_signups_no_schedule_permission_returns_403(
    client, event, submission
):
    user = UserFactory()
    client.force_login(user)

    favourites = client.get(f"/api/events/{event.slug}/submissions/favourites/")
    added = client.post(
        f"/api/events/{event.slug}/submissions/{submission.code}/favourite/"
    )
    signups = client.get(f"/api/events/{event.slug}/submissions/signups/")

    assert favourites.status_code == 403
    assert added.status_code == 403
    assert signups.status_code == 403


def test_signups_list_with_data(
    client, public_event_with_schedule, published_talk_slot
):
    event = public_event_with_schedule
    user = UserFactory()
    client.force_login(user)
    with scopes_disabled():
        sub = published_talk_slot.submission
        profile = AttendeeProfileFactory(user=user, event=event)
        AttendeeSignupFactory(submission=sub, attendee=profile)
    response = client.get(f"/api/events/{event.slug}/submissions/signups/", follow=True)
    assert response.status_code == 200
    assert response.json() == [sub.code]


def test_tag_and_track_list_anonymous_returns_401(client, event, track):
    TagFactory(event=event)

    tags = client.get(event.api_urls.tags, follow=True)
    tracks = client.get(event.api_urls.tracks, follow=True)

    assert tags.status_code == 401
    assert tracks.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_tag_list_orga(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    tags = TagFactory.create_batch(item_count, event=event)

    with django_assert_num_queries(10):
        response = client.get(
            event.api_urls.tags,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )

    assert response.status_code == 200
    assert {r["id"] for r in response.json()["results"]} == {tag.pk for tag in tags}


def test_tag_detail(client, event, orga_user_token):
    tag = TagFactory(event=event)
    headers = {"Authorization": f"Token {orga_user_token.token}"}

    response = client.get(
        event.api_urls.tags + f"{tag.pk}/", follow=True, headers=headers
    )
    localised = client.get(
        event.api_urls.tags + f"{tag.pk}/?lang=en", follow=True, headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tag.pk
    assert data["color"] == tag.color
    assert data["tag"] == str(tag.tag)
    assert data["description"] == {"en": str(tag.description)}
    assert localised.status_code == 200
    assert localised.json()["description"] == str(tag.description)


def test_tag_create_with_write_token(client, event, orga_user_write_token):
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.post(
        event.api_urls.tags,
        follow=True,
        data={"tag": "new-tag", "color": "#00ff00"},
        content_type="application/json",
        headers=headers,
    )
    duplicate = client.post(
        event.api_urls.tags,
        follow=True,
        data={"tag": "new-tag", "color": "#ff0000"},
        content_type="application/json",
        headers=headers,
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
    assert duplicate.status_code == 400
    with scopes_disabled():
        assert event.tags.count() == 1


def test_tag_track_and_type_create_readonly_token_returns_403(
    client, event, orga_user_token
):
    headers = {"Authorization": f"Token {orga_user_token.token}"}

    tag = client.post(
        event.api_urls.tags,
        follow=True,
        data={"tag": "forbidden-tag", "color": "#ff0000"},
        content_type="application/json",
        headers=headers,
    )
    track = client.post(
        event.api_urls.tracks,
        follow=True,
        data={"name": "Forbidden Track", "color": "#0000ff"},
        content_type="application/json",
        headers=headers,
    )
    sub_type = client.post(
        event.api_urls.submission_types,
        follow=True,
        data={"name": "Forbidden Type", "default_duration": 30},
        content_type="application/json",
        headers=headers,
    )

    assert tag.status_code == 403
    assert track.status_code == 403
    assert sub_type.status_code == 403
    with scopes_disabled():
        assert not event.tags.filter(tag="forbidden-tag").exists()
        assert not event.tracks.filter(name="Forbidden Track").exists()
        assert not event.submission_types.filter(name="Forbidden Type").exists()


def test_tag_update_and_delete_with_write_token(client, event, orga_user_write_token):
    tag = TagFactory(event=event)
    url = event.api_urls.tags + f"{tag.pk}/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    response = client.patch(
        url,
        follow=True,
        data={"tag": "updated-tag"},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        tag.refresh_from_db()
        assert str(tag.tag) == "updated-tag"

    response = client.delete(url, follow=True, headers=headers)

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.tags.filter(pk=tag.pk).exists()


def test_track_and_type_list_public_event(
    client, public_event_with_schedule, published_talk_slot
):
    event = public_event_with_schedule
    with scopes_disabled():
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)
        default_type = event.cfp.default_type

    tracks = client.get(event.api_urls.tracks, follow=True)
    types = client.get(event.api_urls.submission_types, follow=True)

    assert tracks.status_code == 200
    assert [t["id"] for t in tracks.json()["results"]] == [track.pk]
    assert types.status_code == 200
    assert [t["id"] for t in types.json()["results"]] == [default_type.pk]


@pytest.mark.parametrize("item_count", (1, 3))
def test_track_list_orga(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    tracks = TrackFactory.create_batch(item_count, event=event)

    with django_assert_num_queries(11):
        response = client.get(
            event.api_urls.tracks,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )

    assert response.status_code == 200
    assert {r["id"] for r in response.json()["results"]} == {t.pk for t in tracks}


def test_track_detail(client, event, orga_user_token, track):
    headers = {"Authorization": f"Token {orga_user_token.token}"}

    response = client.get(
        event.api_urls.tracks + f"{track.pk}/", follow=True, headers=headers
    )
    localised = client.get(
        event.api_urls.tracks + f"{track.pk}/?lang=en", follow=True, headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == track.pk
    assert data["color"] == track.color
    assert data["name"] == {"en": str(track.name)}
    assert localised.status_code == 200
    assert localised.json()["name"] == str(track.name)


def test_track_create_with_write_token(client, event, orga_write_token):
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


def test_track_update_and_delete_with_write_token(
    client, event, orga_write_token, track
):
    url = event.api_urls.tracks + f"{track.pk}/"
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.patch(
        url,
        follow=True,
        data={"name": "Updated Track"},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        track.refresh_from_db()
        assert str(track.name) == "Updated Track"

    response = client.delete(url, follow=True, headers=headers)

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.tracks.filter(pk=track.pk).exists()


def test_submission_type_list_anonymous_returns_401_when_not_public(client):
    event = EventFactory(is_public=False)
    response = client.get(event.api_urls.submission_types, follow=True)
    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_type_list_orga(
    client, event, orga_user_token, item_count, django_assert_num_queries
):
    types = SubmissionTypeFactory.create_batch(item_count, event=event)
    with scopes_disabled():
        default_type = event.cfp.default_type

    with django_assert_num_queries(10):
        response = client.get(
            event.api_urls.submission_types,
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )

    assert response.status_code == 200
    assert {r["id"] for r in response.json()["results"]} == {
        default_type.pk,
        *(st.pk for st in types),
    }


def test_submission_type_detail(client, event, orga_user_token):
    with scopes_disabled():
        sub_type = event.cfp.default_type
    headers = {"Authorization": f"Token {orga_user_token.token}"}

    response = client.get(
        event.api_urls.submission_types + f"{sub_type.pk}/",
        follow=True,
        headers=headers,
    )
    localised = client.get(
        event.api_urls.submission_types + f"{sub_type.pk}/?lang=en",
        follow=True,
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sub_type.pk
    assert data["default_duration"] == sub_type.default_duration
    assert data["name"] == {"en": str(sub_type.name)}
    assert localised.status_code == 200
    assert localised.json()["name"] == str(sub_type.name)


def test_submission_type_create_with_write_token(client, event, orga_write_token):
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


def test_submission_type_update_and_delete_with_write_token(
    client, event, orga_write_token
):
    submission_type = SubmissionTypeFactory(
        event=event, name="Workshop", default_duration=60
    )
    url = event.api_urls.submission_types + f"{submission_type.pk}/"
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.patch(
        url,
        follow=True,
        data={"name": "Updated Type"},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        submission_type.refresh_from_db()
        assert str(submission_type.name) == "Updated Type"

    response = client.delete(url, follow=True, headers=headers)

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.submission_types.filter(pk=submission_type.pk).exists()


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
            limit_events=[event],
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


def test_submission_reviewer_log_access(client, event, submission, review_token):
    with scopes_disabled(), scope(event=event):
        submission.log_action("pretalx.submission.update", data={"note": "Reviewed"})

    response = client.get(
        event.api_urls.submissions + f"{submission.code}/log/",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert content["results"][0]["action_type"] == "pretalx.submission.update"
    assert content["results"][0]["data"] == {"note": "Reviewed"}


@pytest.mark.parametrize(
    ("action_url", "payload"),
    (
        ("accept", {}),
        ("reject", {}),
        ("confirm", {}),
        ("cancel", {}),
        ("make-submitted", {}),
        ("add-speaker", {"email": "new@example.com"}),
        ("remove-speaker", {"user": "ABCDE"}),
        ("invitations", {"email": "invited@example.com"}),
        ("resources", {"link": "https://example.com/slides"}),
    ),
)
def test_submission_action_denied_for_reviewer(
    client, event, review_token, submission, action_url, payload
):
    original_state = submission.state

    response = client.post(
        event.api_urls.submissions + f"{submission.code}/{action_url}/",
        follow=True,
        data=payload,
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        submission.refresh_from_db()
        assert submission.state == original_state
        assert submission.speakers.count() == 1
        assert submission.resources.count() == 0
        assert SubmissionInvitation.objects.filter(submission=submission).count() == 0


def test_reviewer_cannot_see_submissions_in_anonymised_phase(
    client, event, orga_user_write_token, review_token, submission
):
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


@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.parametrize(
    ("expand", "expected_queries"),
    (
        ("speakers", 21),
        ("answers.question,speakers.answers.question", 27),
        ("answers.question.tracks", 23),
    ),
)
def test_submission_list_expand_answers_question_query_count(
    client,
    event,
    orga_user_token,
    item_count,
    expand,
    expected_queries,
    django_assert_num_queries,
):
    with scopes_disabled():
        submission_question = QuestionFactory(
            event=event, variant=QuestionVariant.CHOICES, target="submission"
        )
        speaker_question = QuestionFactory(
            event=event, variant=QuestionVariant.CHOICES, target="speaker"
        )
        for _ in range(item_count):
            role = SpeakerRoleFactory(submission__event=event, speaker__event=event)
            AnswerFactory(question=submission_question, submission=role.submission)
            AnswerFactory(
                question=speaker_question, speaker=role.speaker, submission=None
            )

    with django_assert_num_queries(expected_queries):
        response = client.get(
            event.api_urls.submissions + f"?expand={expand}",
            follow=True,
            headers={"Authorization": f"Token {orga_user_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count
    result = content["results"][0]
    if expand == "speakers":
        assert len(result["speakers"][0]["answers"]) == 1
    elif expand == "answers.question.tracks":
        assert result["answers"][0]["question"]["id"] == submission_question.pk
    else:
        assert result["answers"][0]["question"]["id"] == submission_question.pk
        assert (
            result["speakers"][0]["answers"][0]["question"]["id"] == speaker_question.pk
        )


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_list_expand_speakers_availabilities_query_count(
    client, event, orga_read_token, item_count, django_assert_num_queries
):
    with scopes_disabled():
        event.cfp.fields["availabilities"] = {"visibility": "optional"}
        event.cfp.save()
        for _ in range(item_count):
            role = SpeakerRoleFactory(submission__event=event, speaker__event=event)
            AvailabilityFactory(event=event, person=role.speaker)

    with django_assert_num_queries(22):
        response = client.get(
            event.api_urls.submissions + "?expand=speakers",
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count
    assert len(content["results"][0]["speakers"][0]["availabilities"]) == 1


def test_submission_attendees_orga_can_list(
    client, event, orga_user_write_token, submission
):
    with scopes_disabled():
        cancelled = AttendeeSignupFactory(
            submission=submission, position=0, state="canceled"
        )
        confirmed_late = AttendeeSignupFactory(submission=submission, position=2)
        confirmed_early = AttendeeSignupFactory(submission=submission, position=1)
    url = event.api_urls.submissions + f"{submission.code}/attendees/"
    headers = {"Authorization": f"Token {orga_user_write_token.token}"}

    not_required = client.get(url, headers=headers)

    assert not_required.status_code == 404

    with scopes_disabled():
        submission.attendee_signup_required = True
        submission.save()
    response = client.get(url, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert [row["id"] for row in data] == [
        cancelled.pk,
        confirmed_early.pk,
        confirmed_late.pk,
    ]
    assert data[1]["name"] == confirmed_early.attendee.user.name
    assert data[1]["email"] == confirmed_early.attendee.user.email
    assert data[1]["state"] == "confirmed"
    assert data[0]["state"] == "canceled"


def test_submission_attendees_denied_without_write_permission(
    client, event, orga_user_token, submission, review_user
):
    with scopes_disabled():
        submission.attendee_signup_required = True
        submission.save()
        AttendeeSignupFactory(submission=submission)
        reviewer_token = UserApiTokenFactory(
            user=review_user,
            limit_events=[event],
            endpoints=dict.fromkeys(ENDPOINTS, ["list", "retrieve", "actions"]),
        )
    url = event.api_urls.submissions + f"{submission.code}/attendees/"

    readonly = client.get(
        url, headers={"Authorization": f"Token {orga_user_token.token}"}
    )
    reviewer = client.get(
        url, headers={"Authorization": f"Token {reviewer_token.token}"}
    )

    assert readonly.status_code == 403
    assert reviewer.status_code == 403


def test_submission_list_reviewer_does_not_get_orga_only_fields(
    client, event, orga_user_token, review_user, review_token, submission
):
    secret_notes = "SPEAKER INTERNAL SENTINEL NOTES"
    with scopes_disabled():
        submission.anonymised = {"_anonymised": True, "title": "SECRET ANON TITLE"}
        submission.review_code = "REVIEWCODE123456"
        submission.save()
        submission.assigned_reviewers.add(review_user)
        profile = submission.speakers.select_related("user").first()
        profile.internal_notes = secret_notes
        profile.save()
        speaker_email = profile.user.email
    reviewer_headers = {"Authorization": f"Token {review_token.token}"}

    response = client.get(
        event.api_urls.submissions, follow=True, headers=reviewer_headers
    )
    expanded = client.get(
        event.api_urls.submissions + "?expand=speakers",
        follow=True,
        headers=reviewer_headers,
    )
    orga_response = client.get(
        event.api_urls.submissions,
        follow=True,
        headers={"Authorization": f"Token {orga_user_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    result = content["results"][0]
    for field in ORGA_ONLY_SUBMISSION_FIELDS:
        assert field not in result, field
    assert "internal_notes" in result
    assert "notes" in result
    assert "REVIEWCODE123456" not in response.text
    assert expanded.status_code == 200
    speaker = expanded.json()["results"][0]["speakers"][0]
    assert speaker["code"] == profile.code
    assert "email" not in speaker, speaker
    assert "internal_notes" not in speaker, speaker
    assert secret_notes not in expanded.text
    assert speaker_email not in expanded.text
    orga_result = orga_response.json()["results"][0]
    for field in ORGA_ONLY_SUBMISSION_FIELDS:
        assert field in orga_result, field


def test_submission_reviewer_state_change_action_hides_orga_fields(
    client, event, review_token, submission
):
    with scopes_disabled():
        submission.anonymised = {"_anonymised": True, "title": "SECRET ANON TITLE"}
        submission.review_code = "REVIEWCODE123456"
        submission.save()
        phase = event.active_review_phase
        phase.can_change_submission_state = True
        phase.save()

    response = client.post(
        event.api_urls.submissions + f"{submission.code}/accept/",
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )
    assert response.status_code == 200, response.content
    result = response.json()

    for field in ORGA_ONLY_SUBMISSION_FIELDS:
        assert field not in result, field
    assert "internal_notes" in result
    assert result["state"] == SubmissionStates.ACCEPTED
    assert "SECRET ANON TITLE" not in response.text
    assert "REVIEWCODE123456" not in response.text
