# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope, scopes_disabled

from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile
from pretalx.person.models.auth_token import ENDPOINTS, READ_PERMISSIONS
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import QuestionTarget, QuestionVariant, SubmissionStates
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    TalkSlotFactory,
    TeamFactory,
    UserApiTokenFactory,
    UserFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def speaker_on_event(event):
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
    return role.speaker, role.submission


def test_speaker_list_anonymous_without_schedule_returns_401(client):
    event = EventFactory(feature_flags={"show_schedule": False})
    with scopes_disabled():
        SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )

    response = client.get(event.api_urls.speakers, follow=True)

    assert response.status_code == 401


def test_speaker_list_anonymous_with_schedule(client, event):
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        speaker = role.speaker
        sub = role.submission
        TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers, follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    result = content["results"][0]
    assert result["code"] == speaker.code
    assert result["name"] == speaker.get_display_name()
    assert result["biography"] == speaker.biography
    assert sub.code in result["submissions"]
    assert "email" not in result
    assert "avatar" not in result


def test_speaker_list_anonymous_excludes_unscheduled_submissions(client, event):
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        speaker = role.speaker
        scheduled_sub = role.submission
        TalkSlotFactory(submission=scheduled_sub, is_visible=True)

        role2 = SpeakerRoleFactory(
            speaker=speaker,
            submission__event=event,
            submission__state=SubmissionStates.ACCEPTED,
        )
        accepted_sub = role2.submission

        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers, follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    result = content["results"][0]
    assert scheduled_sub.code in result["submissions"]
    assert accepted_sub.code not in result["submissions"]


def test_speaker_list_reviewer_names_hidden_returns_403(client, review_token, event):
    with scopes_disabled():
        phase = event.active_review_phase
        phase.can_see_speaker_names = False
        phase.save()

    response = client.get(
        event.api_urls.speakers,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403


def test_speaker_list_reviewer_names_visible(
    client, review_token, event, speaker_on_event
):
    speaker, submission = speaker_on_event
    with scopes_disabled():
        phase = event.active_review_phase
        phase.can_see_speaker_names = True
        phase.save()

    response = client.get(
        event.api_urls.speakers,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert content["results"][0]["code"] == speaker.code


ORGA_ONLY_SPEAKER_FIELDS = (
    "email",
    "timezone",
    "locale",
    "is_managed",
    "has_arrived",
    "internal_notes",
)


def test_speaker_list_reviewer_does_not_get_orga_only_fields(
    client, review_token, orga_read_token, event, speaker_on_event
):
    secret_notes = "SPEAKER INTERNAL SENTINEL NOTES"
    speaker, _ = speaker_on_event
    with scopes_disabled():
        speaker.internal_notes = secret_notes
        speaker.save()
        speaker_email = speaker.user.email
        phase = event.active_review_phase
        phase.can_see_speaker_names = True
        phase.save()

    response = client.get(
        event.api_urls.speakers,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    result = content["results"][0]

    for field in ORGA_ONLY_SPEAKER_FIELDS:
        assert field not in result, field
    assert result["code"] == speaker.code
    assert "biography" in result
    assert secret_notes not in response.text
    assert speaker_email not in response.text

    response = client.get(
        event.api_urls.speakers,
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )
    orga_result = response.json()["results"][0]
    for field in ORGA_ONLY_SPEAKER_FIELDS:
        assert field in orga_result, field


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_list_orga(
    client, orga_read_token, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        SpeakerRoleFactory.create_batch(
            item_count,
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )

    with django_assert_num_queries(15):
        response = client.get(
            event.api_urls.speakers,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count
    result = content["results"][0]
    assert "email" in result
    assert result["has_arrived"] is False


def test_speaker_list_search_by_name(client, event):
    with scopes_disabled():
        role1 = SpeakerRoleFactory(
            speaker__event=event,
            speaker__name="Findablename",
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
        )
        TalkSlotFactory(submission=role1.submission, is_visible=True)

        role2 = SpeakerRoleFactory(
            speaker__event=event,
            speaker__name="Otherperson",
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
        )
        TalkSlotFactory(submission=role2.submission, is_visible=True)

        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers + "?q=Findablename", follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert content["results"][0]["name"] == "Findablename"


def test_speaker_list_search_by_email_anonymous_finds_nothing(client, event):
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        speaker = role.speaker
        TalkSlotFactory(submission=role.submission, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        email = speaker.user.email

    response = client.get(event.api_urls.speakers + f"?q={email}", follow=True)

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_speaker_list_search_by_email_orga(
    client, orga_read_token, event, speaker_on_event
):
    speaker, _ = speaker_on_event

    response = client.get(
        event.api_urls.speakers + f"?q={speaker.user.email}",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert content["results"][0]["email"] == speaker.user.email


def test_speaker_list_search_by_email_reviewer_finds_nothing(
    client, review_token, event, speaker_on_event
):
    speaker, _ = speaker_on_event
    with scopes_disabled():
        phase = event.active_review_phase
        phase.can_see_speaker_names = True
        phase.save()
        email = speaker.user.email

    response = client.get(
        event.api_urls.speakers + f"?q={email}",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_speaker_list_expand_submissions(
    client, orga_read_token, event, speaker_on_event
):
    speaker, submission = speaker_on_event

    response = client.get(
        event.api_urls.speakers + "?expand=submissions",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    result = next(r for r in content["results"] if r["code"] == speaker.code)
    assert isinstance(result["submissions"], list)
    assert len(result["submissions"]) == 1
    assert result["submissions"][0]["code"] == submission.code
    assert result["submissions"][0]["title"] == submission.title


def test_speaker_list_expand_answers(client, orga_read_token, event, speaker_on_event):
    speaker, _ = speaker_on_event
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            active=True,
        )
        answer = AnswerFactory(
            question=question, speaker=speaker, submission=None, answer="test answer"
        )
        # Decoy answer for another speaker — must not leak into the target speaker's answers
        other_role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        AnswerFactory(
            question=question,
            speaker=other_role.speaker,
            submission=None,
            answer="other answer",
        )

    response = client.get(
        event.api_urls.speakers + "?expand=answers,answers.question",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    result = next(r for r in content["results"] if r["code"] == speaker.code)
    assert isinstance(result["answers"], list)
    assert len(result["answers"]) == 1
    assert result["answers"][0]["id"] == answer.pk
    assert result["answers"][0]["answer"] == "test answer"
    assert result["answers"][0]["question"]["id"] == question.pk


def test_speaker_list_expand_block_recursion(
    client, orga_read_token, event, speaker_on_event
):
    response = client.get(
        event.api_urls.speakers
        + "?expand=answers,answers.question,answers.question.answers",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 400


def test_speaker_list_multiple_talks_not_duplicated(client, event):
    with scopes_disabled():
        role1 = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        speaker = role1.speaker
        sub1 = role1.submission
        TalkSlotFactory(submission=sub1, is_visible=True)
        role2 = SpeakerRoleFactory(
            speaker=speaker,
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
        )
        sub2 = role2.submission
        TalkSlotFactory(submission=sub2, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers, follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert content["results"][0]["code"] == speaker.code
    assert set(content["results"][0]["submissions"]) == {sub1.code, sub2.code}


def test_speaker_retrieve_anonymous_with_schedule(client, event):
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        speaker = role.speaker
        sub = role.submission
        TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers + f"{speaker.code}/", follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["code"] == speaker.code
    assert content["name"] == speaker.get_display_name()
    assert sub.code in content["submissions"]
    assert "email" not in content


def test_speaker_retrieve_anonymous_without_schedule_returns_404(client):
    event = EventFactory(feature_flags={"show_schedule": False})
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )

    response = client.get(
        event.api_urls.speakers + f"{role.speaker.code}/", follow=True
    )

    assert response.status_code == 404


def test_speaker_retrieve_orga(client, orga_read_token, event, speaker_on_event):
    speaker, _ = speaker_on_event

    response = client.get(
        event.api_urls.speakers + f"{speaker.code}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["code"] == speaker.code
    assert content["name"] == speaker.get_display_name()
    assert "email" in content
    assert content["email"] == speaker.user.email


def test_speaker_retrieve_expand_answers(
    client, orga_read_token, event, speaker_on_event
):
    speaker, _ = speaker_on_event
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            active=True,
        )
        answer = AnswerFactory(
            question=question, speaker=speaker, submission=None, answer="detail answer"
        )
        # Decoy answer for another speaker — must not leak into the target speaker's answers
        other_role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        AnswerFactory(
            question=question,
            speaker=other_role.speaker,
            submission=None,
            answer="other answer",
        )

    response = client.get(
        event.api_urls.speakers + f"{speaker.code}/?expand=answers",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert isinstance(content["answers"], list)
    assert len(content["answers"]) == 1
    assert content["answers"][0]["id"] == answer.pk


@pytest.mark.parametrize(
    ("is_reviewer", "can_see"),
    ((True, False), (False, True)),
    ids=["hidden_reviewer_cannot_see", "hidden_orga_sees"],
)
def test_speaker_answer_visibility_hidden_questions(
    client, orga_read_token, review_token, event, speaker_on_event, is_reviewer, can_see
):
    speaker, _ = speaker_on_event
    token = review_token if is_reviewer else orga_read_token
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            active=True,
            is_visible_to_reviewers=False,
        )
        AnswerFactory(
            question=question, speaker=speaker, submission=None, answer="visible?"
        )

    response = client.get(
        event.api_urls.speakers + f"{speaker.code}/",
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )

    assert response.status_code == 200
    content = response.json()

    if can_see:
        assert len(content["answers"]) == 1
    else:
        assert len(content["answers"]) == 0


def test_speaker_update_by_orga(client, orga_write_token, event, speaker_on_event):
    speaker, _ = speaker_on_event
    new_bio = "An updated biography."

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data={"biography": new_bio},
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    assert response.json()["biography"] == new_bio
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.biography == new_bio
        assert (
            speaker.logged_actions()
            .filter(action_type="pretalx.user.profile.update")
            .exists()
        )


def test_speaker_update_by_orga_readonly_token_returns_403(
    client, orga_read_token, event, speaker_on_event
):
    speaker, _ = speaker_on_event

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data={"biography": "Should fail"},
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403


def test_speaker_update_change_name(client, orga_write_token, event, speaker_on_event):
    speaker, _ = speaker_on_event
    new_name = "New Speaker Name"
    with scopes_disabled():
        original_email = speaker.user.email

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data={"name": new_name, "email": "newspeaker@example.com"},
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["name"] == new_name
    assert content["email"] == "newspeaker@example.com"
    with scopes_disabled():
        speaker.refresh_from_db()
        speaker.user.refresh_from_db()
        assert speaker.name == new_name
        # User-level name is unchanged; only profile name is set
        assert speaker.user.name != new_name
        # Email writes target the profile contact email, never the account
        assert speaker.email == "newspeaker@example.com"
        assert speaker.user.email == original_email


def test_speaker_retrieve_answers_scoped_to_event(client, event):
    with scopes_disabled():
        # Set up speaker on primary event
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        speaker = role.speaker
        q1 = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            active=True,
        )
        a1 = AnswerFactory(
            question=q1, speaker=speaker, submission=None, answer="Event 1 answer"
        )

        # Set up same user on a different event
        other_event = EventFactory()
        other_role = SpeakerRoleFactory(
            submission__event=other_event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=other_event,
            speaker__user=speaker.user,
        )
        other_speaker = other_role.speaker
        q2 = QuestionFactory(
            event=other_event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            active=True,
        )
        AnswerFactory(
            question=q2, speaker=other_speaker, submission=None, answer="Event 2 answer"
        )

        # Set up orga token for primary event
        orga_user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser, all_events=True, can_change_submissions=True
        )
        team.members.add(orga_user)
        token = UserApiTokenFactory(
            user=orga_user, endpoints={ep: list(READ_PERMISSIONS) for ep in ENDPOINTS}
        )
        token.limit_events.add(event)

    response = client.get(
        event.api_urls.speakers + f"{speaker.code}/?expand=answers",
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert len(content["answers"]) == 1
    assert content["answers"][0]["id"] == a1.pk
    assert content["answers"][0]["answer"] == "Event 1 answer"


def test_speaker_retrieve_unknown_code_still_404s(client, event, orga_read_token):
    response = client.get(
        event.api_urls.speakers + "NOCODE/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 404


def test_speaker_retrieve_managed_effective_values(client, orga_read_token, event):
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
            speaker__user=None,
            speaker__name="Managed Speaker",
            speaker__email="contact@example.com",
            speaker__origin=SpeakerProfileOrigin.ORGA,
        )
        managed_speaker = role.speaker

    response = client.get(
        event.api_urls.speakers + f"{managed_speaker.code}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["email"] == "contact@example.com"
    assert content["locale"] == event.locale
    assert content["timezone"] is None
    assert content["is_managed"] is True


def test_speaker_retrieve_account_effective_values(
    client, orga_read_token, event, speaker_on_event
):
    speaker, _ = speaker_on_event
    with scopes_disabled():
        account_email = speaker.user.email

    response = client.get(
        event.api_urls.speakers + f"{speaker.code}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["email"] == account_email
    assert content["is_managed"] is False


def test_speaker_update_email_writes_contact_email(
    client, orga_write_token, event, speaker_on_event
):
    speaker, _ = speaker_on_event
    with scopes_disabled():
        account_email = speaker.user.email

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data={"email": "contact@example.com"},
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "contact@example.com"
    with scopes_disabled():
        speaker.refresh_from_db()
        speaker.user.refresh_from_db()
        assert speaker.email == "contact@example.com"
        assert speaker.user.email == account_email
        assert (
            speaker.logged_actions()
            .filter(action_type="pretalx.user.profile.update")
            .exists()
        )


def test_speaker_create(client, orga_write_token, event):
    response = client.post(
        event.api_urls.speakers,
        data={"name": "New Speaker", "email": "new@example.com"},
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    content = response.json()
    assert content["name"] == "New Speaker"
    assert content["email"] == "new@example.com"
    assert content["is_managed"] is True
    with scopes_disabled():
        profile = SpeakerProfile.objects.get(event=event, code=content["code"])
        assert profile.user is None
        assert profile.origin == SpeakerProfileOrigin.ORGA
        assert profile.invitation_token is None
        assert not event.queued_mails.exists()
        assert (
            profile.logged_actions()
            .filter(action_type="pretalx.speaker.create")
            .exists()
        )


def test_speaker_create_read_only_token_returns_403(client, orga_read_token, event):
    response = client.post(
        event.api_urls.speakers,
        data={"name": "New Speaker"},
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403


def test_speaker_sessionless_orga_created_listed_and_retrievable(
    client, orga_read_token, event
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

    list_response = client.get(
        event.api_urls.speakers,
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )
    assert list_response.status_code == 200
    codes = [result["code"] for result in list_response.json()["results"]]
    assert bare.code in codes
    assert cfp_leftover.code not in codes

    detail_response = client.get(
        event.api_urls.speakers + f"{bare.code}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "Bare Speaker"


def test_speaker_sessionless_hidden_from_public(client, event):
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        TalkSlotFactory(submission=role.submission, is_visible=True)
        bare = SpeakerFactory(
            event=event,
            user=None,
            name="Bare Speaker",
            origin=SpeakerProfileOrigin.ORGA,
        )
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers, follow=True)

    assert response.status_code == 200
    codes = [result["code"] for result in response.json()["results"]]
    assert role.speaker.code in codes
    assert bare.code not in codes
