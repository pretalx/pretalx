# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from decimal import Decimal

import pytest
from django_scopes import scopes_disabled

from pretalx.submission.domain.review import update_review_score
from pretalx.submission.models import QuestionVariant, Review
from pretalx.submission.models.question import QuestionRequired
from tests.factories import (
    AnswerFactory,
    QuestionFactory,
    ResourceFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SpeakerFactory,
    SubmissionFactory,
    TagFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

EXPAND_ALL = (
    "user,scores.category,submission,submission.speakers,submission.track,"
    "submission.submission_type,submission.tags,answers"
)


def _make_other_review(event, other_submission, name=None):
    other_user = UserFactory(name=name) if name else UserFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    team.members.add(other_user)
    return ReviewFactory(
        submission=other_submission, user=other_user, text="Looks horrible!"
    )


def _allow_other_reviews(event, value="always"):
    with scopes_disabled():
        event.active_review_phase.can_see_other_reviews = value
        event.active_review_phase.save()


def test_reviewviewset_list_anonymous_returns_401(
    client, event, submission, review_user
):
    ReviewFactory(submission=submission, user=review_user, text="Looks great!")

    response = client.get(event.api_urls.reviews, follow=True)

    assert response.status_code == 401


def test_reviewviewset_list_and_detail_organiser(
    client, orga_read_token, event, submission, review_user
):
    review = ReviewFactory(submission=submission, user=review_user, text="Looks great!")
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    listing = client.get(event.api_urls.reviews, follow=True, headers=headers)
    detail = client.get(
        event.api_urls.reviews + f"{review.pk}/", follow=True, headers=headers
    )

    assert listing.status_code == 200
    assert [r["id"] for r in listing.json()["results"]] == [review.pk]
    assert detail.status_code == 200
    content = detail.json()
    assert content["id"] == review.pk
    assert content["submission"] == submission.code
    assert content["user"] == review_user.code
    assert content["text"] == "Looks great!"

    with scopes_disabled():
        event.review_phases.update(is_active=False)
    inactive = client.get(event.api_urls.reviews, follow=True, headers=headers)

    assert inactive.status_code == 200
    assert [r["id"] for r in inactive.json()["results"]] == [review.pk]


def test_reviewviewset_list_reviewer_without_active_phase_returns_403(
    client, review_token, event, submission, review_user
):
    ReviewFactory(submission=submission, user=review_user, text="Looks great!")
    with scopes_disabled():
        event.review_phases.update(is_active=False)

    response = client.get(
        event.api_urls.reviews,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("item_count", (1, 3))
def test_reviewviewset_list_reviewer_query_count(
    client,
    review_token,
    event,
    submission,
    review_user,
    other_submission,
    django_assert_num_queries,
    item_count,
):
    review = ReviewFactory(submission=submission, user=review_user, text="Looks great!")
    other_review = _make_other_review(event, other_submission)
    _allow_other_reviews(event)
    with scopes_disabled():
        if item_count == 1:
            other_review.delete()
        else:
            ReviewFactory.create(submission=SubmissionFactory(event=event))

    with django_assert_num_queries(14):
        response = client.get(
            event.api_urls.reviews,
            follow=True,
            headers={"Authorization": f"Token {review_token.token}"},
        )

    content = response.json()
    assert response.status_code == 200, content
    assert len(content["results"]) == item_count
    assert review.pk in [r["id"] for r in content["results"]]


def test_reviewviewset_list_reviewer_limited_to_track(
    client, review_token, review_user, event, submission, other_submission, track
):
    review = ReviewFactory(submission=submission, user=review_user, text="Looks great!")
    other_review = _make_other_review(event, other_submission)
    _allow_other_reviews(event)
    with scopes_disabled():
        other_track = TrackFactory(event=event, name="Other Track")
        review.submission.track = track
        review.submission.save()
        other_submission.track = other_track
        other_submission.save()
        speaker = review.submission.speakers.first()
        other_submission.speakers.add(speaker)
        review_user.teams.filter(is_reviewer=True).first().limit_tracks.add(track)
    headers = {"Authorization": f"Token {review_token.token}"}

    response = client.get(event.api_urls.reviews, follow=True, headers=headers)
    expanded = client.get(
        f"{event.api_urls.reviews}?expand=submission.speakers",
        follow=True,
        headers=headers,
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == [review.pk]
    assert other_review.pk not in [r["id"] for r in response.json()["results"]]
    assert expanded.status_code == 200
    speakers = expanded.json()["results"][0]["submission"]["speakers"]
    assert [s["code"] for s in speakers] == [speaker.code]
    assert speakers[0]["submissions"] == [review.submission.code]


def test_reviewviewset_list_reviewer_filters_and_hides_own_submission(
    client, review_token, review_user, event, submission, other_submission
):
    review = ReviewFactory(submission=submission, user=review_user, text="Looks great!")
    other_review = _make_other_review(event, other_submission)
    _allow_other_reviews(event)
    headers = {"Authorization": f"Token {review_token.token}"}

    response = client.get(event.api_urls.reviews, follow=True, headers=headers)
    filtered = client.get(
        event.api_urls.reviews + f"?submission={submission.code}",
        follow=True,
        headers=headers,
    )

    assert response.status_code == 200
    assert {r["id"] for r in response.json()["results"]} == {review.pk, other_review.pk}
    assert filtered.status_code == 200
    assert [r["id"] for r in filtered.json()["results"]] == [review.pk]

    with scopes_disabled():
        profile = SpeakerFactory(user=review_user, event=event)
        other_submission.speakers.add(profile)
    response = client.get(event.api_urls.reviews, follow=True, headers=headers)

    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == [review.pk]


def test_reviewviewset_list_and_detail_expanded(
    client, orga_read_token, event, submission, review_user, track
):
    review = ReviewFactory(submission=submission, user=review_user, text="Looks great!")
    with scopes_disabled():
        review_score_category = ReviewScoreCategoryFactory(
            event=event, name="Impact", weight=1
        )
        review_score_positive = ReviewScoreFactory(
            category=review_score_category, value=Decimal("2.0"), label="Good"
        )
        review_question = QuestionFactory(
            event=event,
            variant=QuestionVariant.STRING,
            target="reviewer",
            question_required=QuestionRequired.REQUIRED,
        )
        review.submission.track = track
        review.scores.add(review_score_positive)
        review.submission.save()
        speaker = review.submission.speakers.first()
        submission_type = review.submission.submission_type
        tag = TagFactory(event=event)
        review.submission.tags.add(tag)
        internal_resource = ResourceFactory(
            submission=review.submission, is_public=False
        )
        AnswerFactory(review=review, question=review_question, answer="text!")
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    listing = client.get(
        f"{event.api_urls.reviews}?expand={EXPAND_ALL}", follow=True, headers=headers
    )
    detail = client.get(
        f"{event.api_urls.reviews}{review.pk}/?expand={EXPAND_ALL}",
        follow=True,
        headers=headers,
    )

    content = listing.json()
    assert listing.status_code == 200, content
    assert len(content["results"]) == 1
    data = content["results"][0]
    assert data["id"] == review.pk
    assert data["submission"]["code"] == review.submission.code
    assert data["submission"]["speakers"][0]["code"] == speaker.code
    assert data["submission"]["track"]["name"]["en"] == track.name
    assert data["submission"]["submission_type"]["name"]["en"] == submission_type.name
    assert data["submission"]["tags"][0]["tag"] == tag.tag
    assert data["submission"]["resources"] == [internal_resource.pk]
    assert data["user"]["code"] == review_user.code
    assert data["scores"][0]["category"]["name"]["en"] == review_score_category.name
    assert data["answers"][0]["answer"] == "text!"
    assert detail.status_code == 200
    assert detail.json() == data


@pytest.mark.parametrize("item_count", (1, 3))
def test_reviewviewset_list_expanded_query_count(
    client, orga_read_token, event, django_assert_num_queries, item_count
):
    with scopes_disabled():
        category = ReviewScoreCategoryFactory(event=event, name="Impact", weight=1)
        score = ReviewScoreFactory(
            category=category, value=Decimal("2.0"), label="Good"
        )
        question = QuestionFactory(
            event=event,
            variant=QuestionVariant.STRING,
            target="reviewer",
            question_required=QuestionRequired.REQUIRED,
        )
        for _ in range(item_count):
            proposal = SubmissionFactory(event=event, track=TrackFactory(event=event))
            proposal.speakers.add(SpeakerFactory(event=event))
            proposal.tags.add(TagFactory(event=event))
            review = ReviewFactory(submission=proposal)
            review.scores.add(score)
            AnswerFactory(review=review, question=question, answer="text!")

    with django_assert_num_queries(21):
        response = client.get(
            f"{event.api_urls.reviews}?expand={EXPAND_ALL}",
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    content = response.json()
    assert response.status_code == 200, content
    assert len(content["results"]) == item_count


def test_reviewviewset_detail_reviewer(
    client, review_token, event, submission, review_user, other_submission
):
    review = ReviewFactory(submission=submission, user=review_user, text="Looks great!")
    other_review = _make_other_review(event, other_submission)
    _allow_other_reviews(event, "never")
    headers = {"Authorization": f"Token {review_token.token}"}

    own = client.get(
        event.api_urls.reviews + f"{review.pk}/", follow=True, headers=headers
    )
    forbidden = client.get(
        event.api_urls.reviews + f"{other_review.pk}/", follow=True, headers=headers
    )

    assert own.status_code == 200
    content = own.json()
    assert content["id"] == review.pk
    assert content["submission"] == submission.code
    assert content["user"] == review_user.code
    assert forbidden.status_code == 403

    _allow_other_reviews(event, "always")
    allowed = client.get(
        event.api_urls.reviews + f"{other_review.pk}/", follow=True, headers=headers
    )

    assert allowed.status_code == 200
    assert allowed.json()["id"] == other_review.pk


@pytest.mark.parametrize(
    ("names_visible", "user_filter_status"),
    ((False, 400), (True, 200)),
    ids=("names_hidden", "names_visible"),
)
def test_reviewviewset_reviewer_identity_respects_names_visibility(
    client,
    review_token,
    event,
    submission,
    review_user,
    other_submission,
    names_visible,
    user_filter_status,
):
    secret_name = "Zzxqsearchsentinel McHidden"
    secret_email = "secret-reviewer@example.org"
    with scopes_disabled():
        own_review = ReviewFactory(
            submission=submission, user=review_user, text="Looks great!"
        )
        other_review = _make_other_review(event, other_submission, name=secret_name)
        other_review.user.email = secret_email
        other_review.user.save()
        other_code = other_review.user.code
        phase = event.active_review_phase
        phase.can_see_reviewer_names = names_visible
        phase.can_see_speaker_names = True
        phase.can_see_other_reviews = "always"
        phase.save()
    headers = {"Authorization": f"Token {review_token.token}"}

    expanded = client.get(
        event.api_urls.reviews + "?expand=user", follow=True, headers=headers
    )
    searched = client.get(
        event.api_urls.reviews + "?q=Zzxqsearchsentinel", follow=True, headers=headers
    )
    by_other = client.get(
        event.api_urls.reviews + f"?user={other_code}", follow=True, headers=headers
    )
    by_own = client.get(
        event.api_urls.reviews + f"?user={review_user.code}",
        follow=True,
        headers=headers,
    )

    assert expanded.status_code == 200
    other_data = next(
        r for r in expanded.json()["results"] if r["id"] == other_review.pk
    )
    # When hidden, the reviewer identity is gone entirely, not just anonymised.
    assert ("user" in other_data) is names_visible, other_data
    assert (secret_name in expanded.text) is names_visible
    assert (secret_email in expanded.text) is names_visible
    assert searched.status_code == 200
    assert (
        other_review.pk in {r["id"] for r in searched.json()["results"]}
    ) is names_visible
    assert by_other.status_code == user_filter_status
    if names_visible:
        assert [r["id"] for r in by_other.json()["results"]] == [other_review.pk]
    else:
        assert other_code not in by_other.text
    assert by_own.status_code == 200
    assert [r["id"] for r in by_own.json()["results"]] == [own_review.pk]


def test_reviewviewset_create_reviewer(client, review_token, event, submission):
    with scopes_disabled():
        assert event.active_review_phase.can_review is True
        review_score_category = ReviewScoreCategoryFactory(
            event=event, name="Impact", weight=1
        )
        review_score_positive = ReviewScoreFactory(
            category=review_score_category, value=Decimal("2.0"), label="Good"
        )
    headers = {"Authorization": f"Token {review_token.token}"}

    response = client.post(
        event.api_urls.reviews,
        data={
            "submission": submission.code,
            "text": "Review with scores.",
            "scores": [review_score_positive.pk],
        },
        content_type="application/json",
        headers=headers,
    )
    duplicate = client.post(
        event.api_urls.reviews,
        data={"submission": submission.code, "text": "Duplicate review."},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        new_review = Review.objects.get(submission=submission, user=review_token.user)
        assert new_review.text == "Review with scores."
        assert list(new_review.scores.all()) == [review_score_positive]
        assert (
            new_review.score
            == review_score_positive.value * review_score_category.weight
        )
    assert duplicate.status_code == 400, duplicate.text
    assert duplicate.json() == {
        "submission": ["You have already reviewed this submission."]
    }
    with scopes_disabled():
        assert Review.objects.filter(submission=submission).count() == 1


def test_reviewviewset_create_own_submission_returns_400(
    client, review_token, review_user, event, submission
):
    with scopes_disabled():
        profile = SpeakerFactory(user=review_user, event=event)
        submission.speakers.add(profile)

    response = client.post(
        event.api_urls.reviews,
        data={"submission": submission.code, "text": "Review for my own talk."},
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["submission"]


def test_reviewviewset_create_phase_disallows_returns_403(
    client, review_token, event, submission
):
    with scopes_disabled():
        phase = event.active_review_phase
        phase.can_review = False
        phase.save()

    response = client.post(
        event.api_urls.reviews,
        data={"submission": submission.code, "text": "Review when phase closed."},
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text


def test_reviewviewset_update_and_delete_own(
    client, review_token, event, submission, review_user
):
    review = ReviewFactory(submission=submission, user=review_user, text="Looks great!")
    with scopes_disabled():
        review_score_category = ReviewScoreCategoryFactory(
            event=event, name="Impact", weight=1
        )
        review_score_positive = ReviewScoreFactory(
            category=review_score_category, value=Decimal("2.0"), label="Good"
        )
        review_score_negative = ReviewScoreFactory(
            category=review_score_category, value=Decimal("-1.0"), label="Bad"
        )
        review.scores.add(review_score_negative)
        update_review_score(review)
    url = event.api_urls.reviews + f"{review.pk}/"
    headers = {"Authorization": f"Token {review_token.token}"}

    response = client.patch(
        url,
        data={"text": "Updated review text.", "scores": [review_score_positive.pk]},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    with scopes_disabled():
        review.refresh_from_db()
        assert review.text == "Updated review text."
        assert list(review.scores.all()) == [review_score_positive]
        assert (
            review.score == review_score_positive.value * review_score_category.weight
        )

    response = client.patch(
        url,
        data={"scores": [review_score_positive.pk, review_score_negative.pk]},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 400, response.text
    with scopes_disabled():
        review.refresh_from_db()
        assert list(review.scores.all()) == [review_score_positive]
        assert (
            review.score == review_score_positive.value * review_score_category.weight
        )

    response = client.delete(url, headers=headers)

    assert response.status_code == 204, response.text
    with scopes_disabled():
        assert not Review.objects.filter(pk=review.pk).exists()


def test_reviewviewset_update_other_review_returns_403(
    client, review_token, event, other_submission
):
    other_review = _make_other_review(event, other_submission)

    response = client.patch(
        event.api_urls.reviews + f"{other_review.pk}/",
        data={"text": "Trying to update someone else's review."},
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text
