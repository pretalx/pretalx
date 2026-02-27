import json

import pytest
from django_scopes import scope, scopes_disabled

from pretalx.person.models.auth_token import ENDPOINTS, READ_PERMISSIONS
from pretalx.submission.models import QuestionTarget, QuestionVariant, SubmissionStates
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    UserApiTokenFactory,
    UserFactory,
)

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_speaker_list_anonymous_without_schedule_returns_401(client, event):
    """Anonymous users get 401 when schedule is not publicly visible."""
    event.feature_flags["show_schedule"] = False
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)

    response = client.get(event.api_urls.speakers, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_speaker_list_anonymous_with_schedule(client, event):
    """Anonymous users see published speakers when the schedule is public."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
        TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)

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


@pytest.mark.django_db
def test_speaker_list_anonymous_excludes_unscheduled_submissions(client, event):
    """Anonymous users only see submissions from the published schedule,
    not accepted-but-unscheduled ones."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        scheduled_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        scheduled_sub.speakers.add(speaker)
        TalkSlotFactory(submission=scheduled_sub, is_visible=True)

        accepted_sub = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        accepted_sub.speakers.add(speaker)

        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers, follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    result = content["results"][0]
    assert scheduled_sub.code in result["submissions"]
    assert accepted_sub.code not in result["submissions"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "show_schedule", (True, False), ids=["public_schedule", "private_schedule"]
)
def test_speaker_list_reviewer_names_hidden_returns_403(
    client, review_token, event, show_schedule
):
    """Reviewers are denied when speaker name anonymisation is active,
    regardless of schedule visibility."""
    event.feature_flags["show_schedule"] = show_schedule
    event.save()
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


@pytest.mark.django_db
def test_speaker_list_reviewer_names_visible(
    client, review_token, event, speaker_on_event
):
    """Reviewers see speakers when the active review phase allows speaker names."""
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


@pytest.mark.django_db
def test_speaker_list_orga(client, orga_token, event, speaker_on_event):
    """Organisers see all speakers with extended fields like email and has_arrived."""
    speaker, submission = speaker_on_event

    response = client.get(
        event.api_urls.speakers,
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    result = content["results"][0]
    assert result["code"] == speaker.code
    assert result["email"] == speaker.user.email
    assert result["has_arrived"] is False


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_list_orga_query_count(
    client, orga_token, event, item_count, django_assert_num_queries
):
    """Query count is constant regardless of the number of speakers (N+1 prevention)."""
    with scopes_disabled():
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
            sub.speakers.add(speaker)

    with django_assert_num_queries(16):
        response = client.get(
            event.api_urls.speakers,
            follow=True,
            headers={"Authorization": f"Token {orga_token.token}"},
        )

    assert response.status_code == 200
    assert response.json()["count"] == item_count


@pytest.mark.django_db
def test_speaker_list_pagination_limit_offset(
    client, orga_token, event, speaker_on_event
):
    """Limit/offset pagination works on the speaker list."""
    with scopes_disabled():
        speaker2 = SpeakerFactory(event=event)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub2.speakers.add(speaker2)

    response = client.get(
        event.api_urls.speakers + "?limit=1&offset=0",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 2
    assert len(content["results"]) == 1
    assert "offset=1" in content["next"]


@pytest.mark.django_db
def test_speaker_list_pagination_page_number(
    client, orga_token, event, speaker_on_event
):
    """Page-number pagination works on the speaker list."""
    with scopes_disabled():
        speaker2 = SpeakerFactory(event=event)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub2.speakers.add(speaker2)

    response = client.get(
        event.api_urls.speakers + "?page_size=1",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 2
    assert len(content["results"]) == 1
    assert "page=2" in content["next"]


@pytest.mark.django_db
def test_speaker_list_search_by_name(client, event):
    """The ?q= parameter filters speakers by name."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        target = SpeakerFactory(event=event, name="Findablename")
        target_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        target_sub.speakers.add(target)
        TalkSlotFactory(submission=target_sub, is_visible=True)

        other = SpeakerFactory(event=event, name="Otherperson")
        other_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        other_sub.speakers.add(other)
        TalkSlotFactory(submission=other_sub, is_visible=True)

        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers + "?q=Findablename", follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert content["results"][0]["name"] == "Findablename"


@pytest.mark.django_db
def test_speaker_list_search_by_email_anonymous_finds_nothing(client, event):
    """Anonymous users cannot search speakers by email."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
        TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)
        email = speaker.user.email

    response = client.get(event.api_urls.speakers + f"?q={email}", follow=True)

    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.django_db
def test_speaker_list_search_by_email_orga(client, orga_token, event, speaker_on_event):
    """Organisers can search speakers by email."""
    speaker, _ = speaker_on_event

    response = client.get(
        event.api_urls.speakers + f"?q={speaker.user.email}",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert content["results"][0]["email"] == speaker.user.email


@pytest.mark.django_db
def test_speaker_list_expand_submissions(client, orga_token, event, speaker_on_event):
    """Expanding submissions returns full submission objects instead of codes."""
    speaker, submission = speaker_on_event

    response = client.get(
        event.api_urls.speakers + "?expand=submissions",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    result = next(r for r in content["results"] if r["code"] == speaker.code)
    assert isinstance(result["submissions"], list)
    assert len(result["submissions"]) == 1
    assert result["submissions"][0]["code"] == submission.code
    assert result["submissions"][0]["title"] == submission.title


@pytest.mark.django_db
def test_speaker_list_expand_answers(client, orga_token, event, speaker_on_event):
    """Expanding answers returns full answer objects with question data,
    scoped to the correct speaker."""
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
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        other_sub.speakers.add(other_speaker)
        AnswerFactory(
            question=question,
            speaker=other_speaker,
            submission=None,
            answer="other answer",
        )

    response = client.get(
        event.api_urls.speakers + "?expand=answers,answers.question",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    result = next(r for r in content["results"] if r["code"] == speaker.code)
    assert isinstance(result["answers"], list)
    assert len(result["answers"]) == 1
    assert result["answers"][0]["id"] == answer.pk
    assert result["answers"][0]["answer"] == "test answer"
    assert result["answers"][0]["question"]["id"] == question.pk


@pytest.mark.django_db
def test_speaker_list_expand_block_recursion(
    client, orga_token, event, speaker_on_event
):
    """Attempting to expand answers recursively returns 400."""
    response = client.get(
        event.api_urls.speakers
        + "?expand=answers,answers.question,answers.question.answers",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_speaker_list_multiple_talks_not_duplicated(client, event):
    """A speaker with multiple talks appears only once in the list."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub1 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub1.speakers.add(speaker)
        TalkSlotFactory(submission=sub1, is_visible=True)
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub2.speakers.add(speaker)
        TalkSlotFactory(submission=sub2, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers, follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    assert content["results"][0]["code"] == speaker.code
    assert set(content["results"][0]["submissions"]) == {sub1.code, sub2.code}


@pytest.mark.django_db
def test_speaker_retrieve_anonymous_with_schedule(client, event):
    """Anonymous users can retrieve a speaker detail when the schedule is public."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
        TalkSlotFactory(submission=sub, is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)

    response = client.get(event.api_urls.speakers + f"{speaker.code}/", follow=True)

    assert response.status_code == 200
    content = response.json()
    assert content["code"] == speaker.code
    assert content["name"] == speaker.get_display_name()
    assert sub.code in content["submissions"]
    assert "email" not in content


@pytest.mark.django_db
def test_speaker_retrieve_anonymous_without_schedule_returns_404(client, event):
    """Anonymous users get 404 for a speaker when the schedule is not public."""
    event.feature_flags["show_schedule"] = False
    event.save()
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)

    response = client.get(event.api_urls.speakers + f"{speaker.code}/", follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_speaker_retrieve_orga(client, orga_token, event, speaker_on_event):
    """Organisers see extended fields (email, etc.) on speaker detail."""
    speaker, _ = speaker_on_event

    response = client.get(
        event.api_urls.speakers + f"{speaker.code}/",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["code"] == speaker.code
    assert content["name"] == speaker.get_display_name()
    assert "email" in content
    assert content["email"] == speaker.user.email


@pytest.mark.django_db
def test_speaker_retrieve_expand_answers(client, orga_token, event, speaker_on_event):
    """Expanding answers on detail view returns full answer objects,
    scoped to the correct speaker."""
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
        other_speaker = SpeakerFactory(event=event)
        other_sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        other_sub.speakers.add(other_speaker)
        AnswerFactory(
            question=question,
            speaker=other_speaker,
            submission=None,
            answer="other answer",
        )

    response = client.get(
        event.api_urls.speakers + f"{speaker.code}/?expand=answers",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert isinstance(content["answers"], list)
    assert len(content["answers"]) == 1
    assert content["answers"][0]["id"] == answer.pk


@pytest.mark.django_db
@pytest.mark.parametrize("expand", (False, True), ids=["no_expand", "expand"])
@pytest.mark.parametrize(
    ("is_visible_to_reviewers", "is_reviewer", "can_see"),
    (
        (True, True, True),
        (False, True, False),
        (True, False, True),
        (False, False, True),
    ),
    ids=[
        "visible_reviewer_sees",
        "hidden_reviewer_cannot_see",
        "visible_orga_sees",
        "hidden_orga_sees",
    ],
)
def test_speaker_answer_visibility(
    client,
    orga_token,
    review_token,
    event,
    speaker_on_event,
    is_visible_to_reviewers,
    is_reviewer,
    can_see,
    expand,
):
    """Answer visibility depends on question visibility settings and user role."""
    speaker, _ = speaker_on_event
    token = review_token if is_reviewer else orga_token
    with scopes_disabled():
        question = QuestionFactory(
            event=event,
            target=QuestionTarget.SPEAKER,
            variant=QuestionVariant.STRING,
            active=True,
            is_visible_to_reviewers=is_visible_to_reviewers,
        )
        answer = AnswerFactory(
            question=question, speaker=speaker, submission=None, answer="visible?"
        )

    expand_param = "?expand=answers" if expand else ""
    response = client.get(
        event.api_urls.speakers + f"{speaker.code}/{expand_param}",
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )

    assert response.status_code == 200
    content = response.json()

    if can_see:
        assert len(content["answers"]) == 1
        if expand:
            assert content["answers"][0]["id"] == answer.pk
        else:
            assert content["answers"][0] == answer.pk
    else:
        assert len(content["answers"]) == 0


@pytest.mark.django_db
def test_speaker_update_by_orga(client, orga_write_token, event, speaker_on_event):
    """Organisers with write tokens can update speaker biography."""
    speaker, _ = speaker_on_event
    new_bio = "An updated biography."

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data=json.dumps({"biography": new_bio}),
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


@pytest.mark.django_db
def test_speaker_update_by_orga_readonly_token_returns_403(
    client, orga_token, event, speaker_on_event
):
    """Organisers with read-only tokens cannot update speakers."""
    speaker, _ = speaker_on_event

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data=json.dumps({"biography": "Should fail"}),
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_speaker_update_by_reviewer_returns_403(
    client, review_token, event, speaker_on_event
):
    """Reviewers cannot update speakers."""
    speaker, _ = speaker_on_event

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data=json.dumps({"biography": "Should fail"}),
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_speaker_update_by_anonymous_returns_401(client, event, speaker_on_event):
    """Anonymous users cannot update speakers."""
    speaker, _ = speaker_on_event
    # Make schedule public so speaker is accessible for anonymous read
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scopes_disabled():
        TalkSlotFactory(submission=speaker_on_event[1], is_visible=True)
        with scope(event=event):
            event.wip_schedule.freeze("v1", notify_speakers=False)

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data=json.dumps({"biography": "Should fail"}),
        follow=True,
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_speaker_update_change_name_and_email(
    client, orga_write_token, event, speaker_on_event
):
    """Orga can update both speaker name and email, name is profile-level, email is user-level."""
    speaker, _ = speaker_on_event
    new_name = "New Speaker Name"
    new_email = "newspeaker@example.com"

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data=json.dumps({"name": new_name, "email": new_email}),
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["name"] == new_name
    assert content["email"] == new_email
    with scopes_disabled():
        speaker.refresh_from_db()
        speaker.user.refresh_from_db()
        assert speaker.name == new_name
        # User-level name is unchanged; only profile name is set
        assert speaker.user.name != new_name
        assert speaker.user.email == new_email


@pytest.mark.django_db
def test_speaker_update_duplicate_email_returns_400(
    client, orga_write_token, event, speaker_on_event
):
    """Updating a speaker's email to one that already exists returns 400."""
    speaker, _ = speaker_on_event
    other_user = UserFactory()

    response = client.patch(
        event.api_urls.speakers + f"{speaker.code}/",
        data=json.dumps({"email": other_user.email}),
        follow=True,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    with scopes_disabled():
        speaker.user.refresh_from_db()
        assert speaker.user.email != other_user.email


@pytest.mark.django_db
def test_speaker_retrieve_answers_scoped_to_event(client, event):
    """Answers from other events do not leak into the speaker detail."""
    with scopes_disabled():
        # Set up speaker on primary event
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
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
        other_speaker = SpeakerFactory(event=other_event, user=speaker.user)
        other_sub = SubmissionFactory(
            event=other_event, state=SubmissionStates.CONFIRMED
        )
        other_sub.speakers.add(other_speaker)
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
        token.events.add(event)

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


@pytest.mark.django_db
def test_speaker_list_legacy_version(client, orga_token, event, speaker_on_event):
    """The LEGACY API version returns speakers with the legacy serializer format."""
    speaker, submission = speaker_on_event

    response = client.get(
        event.api_urls.speakers,
        follow=True,
        headers={
            "Authorization": f"Token {orga_token.token}",
            "pretalx-version": "LEGACY",
        },
    )

    assert response.status_code == 200
    content = response.json()
    assert content["count"] == 1
    result = content["results"][0]
    assert result["code"] == speaker.code
    assert result["name"] == speaker.user.name
    assert result["email"] == speaker.user.email
