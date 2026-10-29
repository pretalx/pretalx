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
    AvailabilityFactory,
    EventFactory,
    QuestionFactory,
    ResourceFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    TagFactory,
    TalkSlotFactory,
    TeamFactory,
    UserApiTokenFactory,
    UserFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

ORGA_ONLY_SPEAKER_FIELDS = (
    "email",
    "timezone",
    "locale",
    "is_managed",
    "has_arrived",
    "internal_notes",
)


@pytest.fixture
def speaker_on_event(event):
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
    return role.speaker, role.submission


@pytest.fixture
def public_speakers(event):
    """A released schedule with two speakers; the first one has two scheduled
    talks, one accepted but unscheduled talk and a non-public resource.
    Also an orga-created bare profile that must stay hidden from the public."""
    with scopes_disabled():
        first = SpeakerRoleFactory(
            speaker__event=event,
            speaker__name="Findablename",
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
        )
        second_talk = SpeakerRoleFactory(
            speaker=first.speaker,
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
        )
        unscheduled = SpeakerRoleFactory(
            speaker=first.speaker,
            submission__event=event,
            submission__state=SubmissionStates.ACCEPTED,
        )
        other = SpeakerRoleFactory(
            speaker__event=event,
            speaker__name="Otherperson",
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
        )
        for role in (first, second_talk, other):
            TalkSlotFactory(submission=role.submission, is_visible=True)
        public_resource = ResourceFactory(submission=first.submission)
        ResourceFactory(submission=first.submission, is_public=False)
        bare = SpeakerFactory(
            event=event,
            user=None,
            name="Bare Speaker",
            origin=SpeakerProfileOrigin.ORGA,
        )
        with scope(event=event):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    return {
        "speaker": first.speaker,
        "scheduled": {first.submission, second_talk.submission},
        "unscheduled": unscheduled.submission,
        "other": other.speaker,
        "bare": bare,
        "public_resource": public_resource,
    }


def test_speaker_anonymous_without_schedule(client):
    event = EventFactory(feature_flags={"show_schedule": False})
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )

    listing = client.get(event.api_urls.speakers, follow=True)
    detail = client.get(event.api_urls.speakers + f"{role.speaker.code}/", follow=True)

    assert listing.status_code == 401
    assert detail.status_code == 404


def test_speaker_list_anonymous_with_schedule(client, event, public_speakers):
    speaker = public_speakers["speaker"]
    with scopes_disabled():
        email = speaker.user.email

    listing = client.get(event.api_urls.speakers, follow=True)
    by_name = client.get(event.api_urls.speakers + "?q=Findablename", follow=True)
    by_email = client.get(event.api_urls.speakers + f"?q={email}", follow=True)

    assert listing.status_code == 200
    results = {r["code"]: r for r in listing.json()["results"]}
    assert set(results) == {speaker.code, public_speakers["other"].code}
    result = results[speaker.code]
    assert result["name"] == "Findablename"
    assert result["biography"] == speaker.biography
    assert set(result["submissions"]) == {s.code for s in public_speakers["scheduled"]}
    assert "email" not in result
    assert "avatar" not in result
    assert by_name.status_code == 200
    assert [r["code"] for r in by_name.json()["results"]] == [speaker.code]
    assert by_email.status_code == 200
    assert by_email.json()["count"] == 0


def test_speaker_retrieve_and_expand_anonymous_with_schedule(
    client, event, public_speakers
):
    speaker = public_speakers["speaker"]

    detail = client.get(event.api_urls.speakers + f"{speaker.code}/", follow=True)
    expanded = client.get(
        event.api_urls.speakers + f"{speaker.code}/?expand=submissions", follow=True
    )

    assert detail.status_code == 200
    content = detail.json()
    assert content["code"] == speaker.code
    assert content["name"] == "Findablename"
    assert set(content["submissions"]) == {s.code for s in public_speakers["scheduled"]}
    assert "email" not in content
    assert expanded.status_code == 200
    submissions = {s["code"]: s for s in expanded.json()["submissions"]}
    assert set(submissions) == {s.code for s in public_speakers["scheduled"]}
    resources = {
        pk for submission in submissions.values() for pk in submission["resources"]
    }
    assert resources == {public_speakers["public_resource"].pk}


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
    reviewer_headers = {"Authorization": f"Token {review_token.token}"}

    response = client.get(
        event.api_urls.speakers, follow=True, headers=reviewer_headers
    )
    by_email = client.get(
        event.api_urls.speakers + f"?q={speaker_email}",
        follow=True,
        headers=reviewer_headers,
    )
    orga_response = client.get(
        event.api_urls.speakers,
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert [r["code"] for r in content["results"]] == [speaker.code]
    result = content["results"][0]
    for field in ORGA_ONLY_SPEAKER_FIELDS:
        assert field not in result, field
    assert "biography" in result
    assert secret_notes not in response.text
    assert speaker_email not in response.text
    assert by_email.status_code == 200
    assert by_email.json()["count"] == 0
    orga_result = orga_response.json()["results"][0]
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

    with django_assert_num_queries(14):
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


def test_speaker_orga_reads(client, orga_read_token, event, speaker_on_event):
    speaker, submission = speaker_on_event
    with scopes_disabled():
        account_email = speaker.user.email
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    by_email = client.get(
        event.api_urls.speakers + f"?q={account_email}", follow=True, headers=headers
    )
    expanded = client.get(
        event.api_urls.speakers + "?expand=submissions", follow=True, headers=headers
    )
    detail = client.get(
        event.api_urls.speakers + f"{speaker.code}/", follow=True, headers=headers
    )
    unknown = client.get(
        event.api_urls.speakers + "NOCODE/", follow=True, headers=headers
    )

    assert by_email.status_code == 200
    assert [r["email"] for r in by_email.json()["results"]] == [account_email]
    assert expanded.status_code == 200
    result = expanded.json()["results"][0]
    assert result["code"] == speaker.code
    assert [(s["code"], s["title"]) for s in result["submissions"]] == [
        (submission.code, submission.title)
    ]
    assert detail.status_code == 200
    content = detail.json()
    assert content["code"] == speaker.code
    assert content["name"] == speaker.get_display_name()
    assert content["email"] == account_email
    assert content["is_managed"] is False
    assert unknown.status_code == 404


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_list_expand_submissions_query_count(
    client, orga_read_token, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            target=QuestionTarget.SUBMISSION,
            variant=QuestionVariant.STRING,
            active=True,
        )
        for _ in range(item_count):
            role = SpeakerRoleFactory(
                submission__event=event,
                submission__state=SubmissionStates.CONFIRMED,
                speaker__event=event,
            )
            second_role = SpeakerRoleFactory(
                speaker=role.speaker, submission__event=event
            )
            for submission in (role.submission, second_role.submission):
                AnswerFactory(question=question, submission=submission, speaker=None)

    with django_assert_num_queries(18):
        response = client.get(
            event.api_urls.speakers + "?expand=submissions",
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count
    submissions = content["results"][0]["submissions"]
    assert len(submissions) == 2
    assert all(len(submission["answers"]) == 1 for submission in submissions)


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_list_availabilities_query_count(
    client, orga_read_token, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        event.cfp.fields["availabilities"] = {"visibility": "optional"}
        event.cfp.save()
        for _ in range(item_count):
            role = SpeakerRoleFactory(
                submission__event=event,
                submission__state=SubmissionStates.CONFIRMED,
                speaker__event=event,
            )
            AvailabilityFactory(event=event, person=role.speaker)

    with django_assert_num_queries(15):
        response = client.get(
            event.api_urls.speakers,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count
    assert len(content["results"][0]["availabilities"]) == 1


def test_speaker_expand_answers(client, orga_read_token, event, speaker_on_event):
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
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    listing = client.get(
        event.api_urls.speakers + "?expand=answers,answers.question",
        follow=True,
        headers=headers,
    )
    detail = client.get(
        event.api_urls.speakers + f"{speaker.code}/?expand=answers",
        follow=True,
        headers=headers,
    )

    assert listing.status_code == 200
    result = next(r for r in listing.json()["results"] if r["code"] == speaker.code)
    assert [a["id"] for a in result["answers"]] == [answer.pk]
    assert result["answers"][0]["answer"] == "test answer"
    assert result["answers"][0]["question"]["id"] == question.pk
    assert detail.status_code == 200
    assert [a["id"] for a in detail.json()["answers"]] == [answer.pk]
    assert detail.json()["answers"][0]["question"] == question.pk


@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.parametrize(
    ("expand", "expected_queries"),
    (
        ("answers", 15),
        ("answers,answers.question", 17),
        ("answers.question.tracks", 17),
    ),
)
def test_speaker_list_expand_answers_question_query_count(
    client,
    orga_read_token,
    event,
    item_count,
    expand,
    expected_queries,
    django_assert_num_queries,
):
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.CHOICES,
            active=True,
        )
        for _ in range(item_count):
            role = SpeakerRoleFactory(
                submission__event=event,
                submission__state=SubmissionStates.CONFIRMED,
                speaker__event=event,
            )
            AnswerFactory(question=question, speaker=role.speaker, submission=None)

    with django_assert_num_queries(expected_queries):
        response = client.get(
            event.api_urls.speakers + f"?expand={expand}",
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == item_count
    answers = content["results"][0]["answers"]
    assert len(answers) == 1
    if expand == "answers":
        assert answers[0]["question"] == question.pk
    else:
        assert answers[0]["question"]["id"] == question.pk


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


@pytest.mark.parametrize(
    ("token_fixture", "expected_answers"),
    (("review_token", 0), ("orga_read_token", 1)),
    ids=["hidden_reviewer_cannot_see", "hidden_orga_sees"],
)
def test_speaker_answer_visibility_hidden_questions(
    client, request, event, speaker_on_event, token_fixture, expected_answers
):
    speaker, _ = speaker_on_event
    token = request.getfixturevalue(token_fixture)
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
    assert len(response.json()["answers"]) == expected_answers


def test_speaker_update_by_orga(
    client, orga_write_token, orga_user, event, speaker_on_event
):
    speaker, submission = speaker_on_event
    with scopes_disabled():
        user = speaker.user
        original_name = user.name
        original_email = user.email
        submission.log_action("pretalx.submission.update", person=orga_user)
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data={
            "biography": "An updated biography.",
            "name": "New Speaker Name",
            "email": "newspeaker@example.com",
        },
        follow=True,
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    content = response.json()
    assert content["biography"] == "An updated biography."
    assert content["name"] == "New Speaker Name"
    assert content["email"] == "newspeaker@example.com"
    with scopes_disabled():
        speaker.refresh_from_db()
        user.refresh_from_db()
        assert speaker.biography == "An updated biography."
        assert speaker.name == "New Speaker Name"
        # User-level name is unchanged; only profile name is set
        assert user.name == original_name
        # Email writes target the profile contact email, never the account
        assert speaker.email == "newspeaker@example.com"
        assert user.email == original_email

    log = client.get(
        event.api_urls.speakers + f"{speaker.code}/log/", follow=True, headers=headers
    )

    assert log.status_code == 200
    data = log.json()
    assert data["count"] == 1
    assert data["results"][0]["action_type"] == "pretalx.user.profile.update"
    assert data["results"][0]["person"]["code"] == orga_user.code


def test_speaker_write_rejected_with_read_token(
    client, orga_read_token, event, speaker_on_event
):
    speaker, _ = speaker_on_event
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    updated = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data={"biography": "Should fail"},
        follow=True,
        content_type="application/json",
        headers=headers,
    )
    created = client.post(
        event.api_urls.speakers,
        data={"name": "New Speaker"},
        follow=True,
        content_type="application/json",
        headers=headers,
    )

    assert updated.status_code == 403
    assert created.status_code == 403
    with scopes_disabled():
        speaker.refresh_from_db()
        assert speaker.biography != "Should fail"
        assert not SpeakerProfile.objects.filter(name="New Speaker").exists()


def test_speaker_log_denied_for_reviewer(client, review_token, event, speaker_on_event):
    speaker, _ = speaker_on_event
    with scope(event=event):
        speaker.log_action("pretalx.user.profile.update", data={"key": "val"})

    response = client.get(
        event.api_urls.speakers + f"{speaker.code}/log/",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403


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


def test_speaker_managed_profiles_for_orga(client, orga_read_token, event):
    with scopes_disabled():
        bare = SpeakerFactory(
            event=event,
            user=None,
            name="Bare Speaker",
            email="contact@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        )
        cfp_leftover = SpeakerFactory(
            event=event, name="Draft Leftover", origin=SpeakerProfileOrigin.CFP
        )
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    listing = client.get(event.api_urls.speakers, follow=True, headers=headers)
    detail = client.get(
        event.api_urls.speakers + f"{bare.code}/", follow=True, headers=headers
    )

    assert listing.status_code == 200
    codes = [result["code"] for result in listing.json()["results"]]
    assert bare.code in codes
    assert cfp_leftover.code not in codes
    assert detail.status_code == 200
    content = detail.json()
    assert content["name"] == "Bare Speaker"
    assert content["email"] == "contact@example.com"
    assert content["locale"] == event.locale
    assert content["timezone"] is None
    assert content["is_managed"] is True


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


def test_speaker_sessionless_hidden_from_public(client, event, public_speakers):
    response = client.get(event.api_urls.speakers, follow=True)

    assert response.status_code == 200
    codes = [result["code"] for result in response.json()["results"]]
    assert public_speakers["speaker"].code in codes
    assert public_speakers["bare"].code not in codes


@pytest.mark.parametrize("token_fixture", ("orga_read_token", "review_token"))
def test_speaker_expanded_submissions_show_internals_to_orga_and_reviewers(
    client, event, token_fixture, request
):
    token = request.getfixturevalue(token_fixture)
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=event,
            submission__state=SubmissionStates.CONFIRMED,
            speaker__event=event,
        )
        internal_tag = TagFactory(event=event, is_public=False)
        role.submission.tags.add(internal_tag)
        internal_resource = ResourceFactory(submission=role.submission, is_public=False)

    response = client.get(
        event.api_urls.speakers + "?expand=submissions",
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )

    assert response.status_code == 200
    submission = response.json()["results"][0]["submissions"][0]
    assert submission["tags"] == [internal_tag.pk]
    assert submission["resources"] == [internal_resource.pk]
