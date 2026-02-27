import json

import pytest
from django_scopes import scopes_disabled

from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import Answer, Review
from tests.factories import ReviewFactory, SubmissionFactory, TrackFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_reviewviewset_list_anonymous_returns_401(client, event, review):
    """Anonymous users cannot access the review list."""
    response = client.get(event.api_urls.reviews, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_reviewviewset_list_organiser(client, orga_read_token, event, review):
    """Organiser can list reviews."""
    response = client.get(
        event.api_urls.reviews,
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == 1


@pytest.mark.django_db
def test_reviewviewset_list_organiser_without_active_phase(
    client, orga_read_token, event, review
):
    """Organiser can still see reviews even without an active review phase."""
    with scopes_disabled():
        event.review_phases.all().update(is_active=False)
        assert event.review_phases.filter(is_active=True).count() == 0

    response = client.get(
        event.api_urls.reviews,
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == 1


@pytest.mark.django_db
def test_reviewviewset_list_reviewer_without_active_phase_returns_403(
    client, review_token, event, review
):
    """Reviewer cannot see reviews when no review phase is active."""
    with scopes_disabled():
        event.review_phases.all().update(is_active=False)

    response = client.get(
        event.api_urls.reviews,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_reviewviewset_list_reviewer_query_count(
    client,
    review_token,
    event,
    review,
    other_review,
    django_assert_num_queries,
    item_count,
):
    """Reviewer can see reviews with constant query count; visibility depends on phase."""
    with scopes_disabled():
        event.active_review_phase.can_see_other_reviews = "always"
        event.active_review_phase.save()
        if item_count == 1:
            other_review.delete()
        else:
            ReviewFactory.create(submission=SubmissionFactory(event=event))

    with django_assert_num_queries(17):
        response = client.get(
            event.api_urls.reviews,
            follow=True,
            headers={"Authorization": f"Token {review_token.token}"},
        )

    content = response.json()
    assert response.status_code == 200, content
    assert len(content["results"]) == item_count
    assert review.pk in [r["id"] for r in content["results"]]


@pytest.mark.django_db
def test_reviewviewset_list_reviewer_by_track(
    client, review_token, review_user, event, review, other_review, track, talk_slot
):
    """Reviewer with track limits only sees reviews for submissions in their tracks,
    even when a schedule exists on the event."""
    with scopes_disabled():
        other_track = TrackFactory(event=event, name="Other Track")
        event.active_review_phase.can_see_other_reviews = "always"
        event.active_review_phase.save()
        review.submission.track = track
        review.submission.save()
        other_review.submission.track = other_track
        other_review.submission.save()
        review_user.teams.filter(is_reviewer=True).first().limit_tracks.add(track)

    response = client.get(
        event.api_urls.reviews,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == 1


@pytest.mark.django_db
def test_reviewviewset_list_reviewer_cannot_see_own_submission(
    client, review_token, review_user, event, review, other_review
):
    """Reviewer cannot see reviews on submissions they are a speaker on."""
    with scopes_disabled():
        event.active_review_phase.can_see_other_reviews = "always"
        event.active_review_phase.save()
        profile, _ = SpeakerProfile.objects.get_or_create(user=review_user, event=event)
        other_review.submission.speakers.add(profile)

    response = client.get(
        event.api_urls.reviews,
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == 1


@pytest.mark.django_db
def test_reviewviewset_list_filter_by_submission(
    client, review_token, event, review, other_review
):
    """?submission= filters reviews to a specific submission."""
    with scopes_disabled():
        event.active_review_phase.can_see_other_reviews = "always"
        event.active_review_phase.save()

    response = client.get(
        event.api_urls.reviews + f"?submission={review.submission.code}",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == 1


@pytest.mark.django_db
def test_reviewviewset_list_expanded(
    client,
    orga_read_token,
    event,
    review,
    track,
    review_score_positive,
    review_question,
):
    """Organiser can expand submission, user, scores.category, answers in list view."""
    with scopes_disabled():
        review.submission.track = track
        review.scores.add(review_score_positive)
        review.submission.save()
        speaker = review.submission.speakers.all().first()
        submission_type = review.submission.submission_type
        user = review.user
        category = review_score_positive.category
        Answer.objects.create(review=review, question=review_question, answer="text!")

    params = "user,scores.category,submission.speakers,submission.track,submission.submission_type,answers"
    response = client.get(
        f"{event.api_urls.reviews}?expand={params}",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert len(content["results"]) == 1
    data = content["results"][0]
    assert data["submission"]["code"] == review.submission.code
    assert data["submission"]["speakers"][0]["code"] == speaker.code
    assert data["submission"]["track"]["name"]["en"] == track.name
    assert data["submission"]["submission_type"]["name"]["en"] == submission_type.name
    assert data["user"]["code"] == user.code
    assert data["scores"][0]["category"]["name"]["en"] == category.name
    assert data["answers"][0]["answer"] == "text!"


@pytest.mark.django_db
def test_reviewviewset_detail_anonymous_returns_404(client, event, review):
    """Anonymous users get 404 on review detail (not 401 — object-level)."""
    response = client.get(event.api_urls.reviews + f"{review.pk}/", follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_reviewviewset_detail_organiser(client, orga_read_token, event, review):
    """Organiser can see review detail."""
    response = client.get(
        event.api_urls.reviews + f"{review.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert content["id"] == review.pk
    assert content["submission"] == review.submission.code
    assert content["user"] == review.user.code


@pytest.mark.django_db
def test_reviewviewset_detail_organiser_expanded(
    client,
    orga_read_token,
    event,
    review,
    track,
    review_score_positive,
    review_question,
):
    """Organiser can see expanded review detail with all related objects."""
    with scopes_disabled():
        review.submission.track = track
        review.scores.add(review_score_positive)
        review.submission.save()
        speaker = review.submission.speakers.all().first()
        category = review_score_positive.category
        Answer.objects.create(review=review, question=review_question, answer="text!")

    params = "user,scores.category,submission.speakers,submission.track,submission.submission_type,answers"
    response = client.get(
        f"{event.api_urls.reviews}{review.pk}/?expand={params}",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert content["id"] == review.pk
    assert content["submission"]["code"] == review.submission.code
    assert content["submission"]["speakers"][0]["code"] == speaker.code
    assert content["submission"]["track"]["name"]["en"] == track.name
    assert content["user"]["code"] == review.user.code
    assert content["scores"][0]["category"]["name"]["en"] == category.name
    assert content["answers"][0]["answer"] == "text!"


@pytest.mark.django_db
def test_reviewviewset_detail_reviewer_own(client, review_token, event, review):
    """Reviewer can see their own review detail."""
    response = client.get(
        event.api_urls.reviews + f"{review.pk}/",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert content["id"] == review.pk
    assert content["submission"] == review.submission.code
    assert content["user"] == review.user.code


@pytest.mark.django_db
def test_reviewviewset_detail_reviewer_other_when_allowed(
    client, review_token, event, other_review
):
    """Reviewer can see another review when can_see_other_reviews=always."""
    with scopes_disabled():
        event.active_review_phase.can_see_other_reviews = "always"
        event.active_review_phase.save()

    response = client.get(
        event.api_urls.reviews + f"{other_review.pk}/",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert content["id"] == other_review.pk


@pytest.mark.django_db
def test_reviewviewset_detail_reviewer_other_when_not_allowed(
    client, review_token, event, other_review
):
    """Reviewer cannot see another review when can_see_other_reviews=never."""
    with scopes_disabled():
        event.active_review_phase.can_see_other_reviews = "never"
        event.active_review_phase.save()

    response = client.get(
        event.api_urls.reviews + f"{other_review.pk}/",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_reviewviewset_detail_reviewer_own_submission_returns_404(
    client, review_token, review_user, event, other_review
):
    """Reviewer cannot see reviews on their own submissions."""
    with scopes_disabled():
        event.active_review_phase.can_see_other_reviews = "always"
        event.active_review_phase.save()
        profile, _ = SpeakerProfile.objects.get_or_create(user=review_user, event=event)
        other_review.submission.speakers.add(profile)

    response = client.get(
        event.api_urls.reviews + f"{other_review.pk}/",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_reviewviewset_detail_reviewer_by_track(
    client, review_token, review_user, event, other_review, track
):
    """Reviewer with track limits can see reviews on submissions in their tracks."""
    with scopes_disabled():
        event.active_review_phase.can_see_other_reviews = "always"
        event.active_review_phase.save()
        other_review.submission.track = track
        other_review.submission.save()
        review_user.teams.filter(is_reviewer=True).first().limit_tracks.add(track)

    response = client.get(
        event.api_urls.reviews + f"{other_review.pk}/",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    content = response.json()
    assert response.status_code == 200
    assert content["id"] == other_review.pk


@pytest.mark.django_db
def test_reviewviewset_detail_reviewer_outside_track_returns_404(
    client, review_token, review_user, event, other_review, track
):
    """Reviewer with track limits cannot see reviews on submissions outside their tracks."""
    with scopes_disabled():
        other_track = TrackFactory(event=event, name="Other Track")
        event.active_review_phase.can_see_other_reviews = "always"
        event.active_review_phase.save()
        other_review.submission.track = other_track
        other_review.submission.save()
        review_user.teams.filter(is_reviewer=True).first().limit_tracks.add(track)

    response = client.get(
        event.api_urls.reviews + f"{other_review.pk}/",
        follow=True,
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_reviewviewset_create_reviewer(client, review_token, event, submission):
    """Reviewer can create a review for a submission."""
    with scopes_disabled():
        assert event.active_review_phase.can_review is True

    response = client.post(
        event.api_urls.reviews,
        data=json.dumps(
            {"submission": submission.code, "text": "This is a new review."}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        new_review = Review.objects.get(submission=submission, user=review_token.user)
        assert new_review.text == "This is a new review."
        assert new_review.score is None


@pytest.mark.django_db
def test_reviewviewset_create_reviewer_with_scores(
    client,
    review_token,
    event,
    submission,
    review_score_category,
    review_score_positive,
):
    """Reviewer can create a review with score values."""
    response = client.post(
        event.api_urls.reviews,
        data=json.dumps(
            {
                "submission": submission.code,
                "text": "Review with scores.",
                "scores": [review_score_positive.pk],
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        new_review = Review.objects.get(submission=submission, user=review_token.user)
        assert new_review.scores.count() == 1
        assert new_review.scores.first() == review_score_positive
        assert (
            new_review.score
            == review_score_positive.value * review_score_category.weight
        )


@pytest.mark.django_db
def test_reviewviewset_create_duplicate_returns_400(
    client, review_token, event, review
):
    """A reviewer cannot submit two reviews for the same submission."""
    response = client.post(
        event.api_urls.reviews,
        data=json.dumps(
            {"submission": review.submission.code, "text": "Duplicate review."}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 400, response.text
    content = response.json()
    assert "You have already reviewed this submission." in content["submission"]


@pytest.mark.django_db
def test_reviewviewset_create_own_submission_returns_400(
    client, review_token, review_user, event, submission
):
    """Reviewer cannot review their own submission."""
    with scopes_disabled():
        profile, _ = SpeakerProfile.objects.get_or_create(user=review_user, event=event)
        submission.speakers.add(profile)

    response = client.post(
        event.api_urls.reviews,
        data=json.dumps(
            {"submission": submission.code, "text": "Review for my own talk."}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["submission"]


@pytest.mark.django_db
def test_reviewviewset_create_phase_disallows_returns_403(
    client, review_token, event, submission
):
    """Reviewer cannot create review when phase has can_review=False."""
    with scopes_disabled():
        phase = event.active_review_phase
        phase.can_review = False
        phase.save()

    response = client.post(
        event.api_urls.reviews,
        data=json.dumps(
            {"submission": submission.code, "text": "Review when phase closed."}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text


@pytest.mark.django_db
def test_reviewviewset_create_anonymous_returns_401(client, event, submission):
    """Anonymous users cannot create reviews."""
    response = client.post(
        event.api_urls.reviews,
        data=json.dumps({"submission": submission.code, "text": "Anonymous review."}),
        content_type="application/json",
    )

    assert response.status_code == 401, response.text


@pytest.mark.django_db
def test_reviewviewset_update_own_text(client, review_token, event, review):
    """Reviewer can update the text of their own review."""
    new_text = "This is an updated review text."

    response = client.patch(
        event.api_urls.reviews + f"{review.pk}/",
        data=json.dumps({"text": new_text}),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 200, response.text
    with scopes_disabled():
        review.refresh_from_db()
        assert review.text == new_text


@pytest.mark.django_db
def test_reviewviewset_update_own_scores(
    client,
    review_token,
    event,
    review,
    review_score_category,
    review_score_positive,
    review_score_negative,
):
    """Reviewer can update their review's scores, replacing old ones."""
    with scopes_disabled():
        review.scores.add(review_score_negative)
        review.save()
        initial_score = review.score

    response = client.patch(
        event.api_urls.reviews + f"{review.pk}/",
        data=json.dumps({"scores": [review_score_positive.pk]}),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 200, response.text
    with scopes_disabled():
        review.refresh_from_db()
        assert review.scores.count() == 1
        assert review.scores.first() == review_score_positive
        assert review.score != initial_score
        assert (
            review.score == review_score_positive.value * review_score_category.weight
        )


@pytest.mark.django_db
def test_reviewviewset_update_multiple_scores_same_category_returns_400(
    client,
    review_token,
    event,
    review,
    review_score_category,
    review_score_positive,
    review_score_negative,
):
    """Cannot add multiple score values from the same category."""
    with scopes_disabled():
        review.scores.add(review_score_negative)
        review.save()
        initial_score = review.score

    response = client.patch(
        event.api_urls.reviews + f"{review.pk}/",
        data=json.dumps(
            {"scores": [review_score_positive.pk, review_score_negative.pk]}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 400, response.text
    with scopes_disabled():
        review.refresh_from_db()
        assert review.scores.count() == 1
        assert review.scores.first() == review_score_negative
        assert review.score == initial_score


@pytest.mark.django_db
def test_reviewviewset_update_other_review_returns_403(
    client, review_token, event, other_review
):
    """Reviewer cannot update another reviewer's review."""
    response = client.patch(
        event.api_urls.reviews + f"{other_review.pk}/",
        data=json.dumps({"text": "Trying to update someone else's review."}),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text


@pytest.mark.django_db
def test_reviewviewset_update_phase_disallows_returns_403(
    client, review_token, event, review
):
    """Reviewer cannot update review when phase has can_review=False."""
    with scopes_disabled():
        phase = event.active_review_phase
        phase.can_review = False
        phase.save()

    response = client.patch(
        event.api_urls.reviews + f"{review.pk}/",
        data=json.dumps({"text": "Update when phase closed."}),
        content_type="application/json",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text


@pytest.mark.django_db
def test_reviewviewset_update_anonymous_returns_404(client, event, review):
    """Anonymous users get 404 when trying to update a review."""
    response = client.patch(
        event.api_urls.reviews + f"{review.pk}/",
        data=json.dumps({"text": "Anonymous update."}),
        content_type="application/json",
    )

    assert response.status_code == 404, response.text


@pytest.mark.django_db
def test_reviewviewset_delete_own(client, review_token, event, review):
    """Reviewer can delete their own review."""
    review_pk = review.pk

    response = client.delete(
        event.api_urls.reviews + f"{review_pk}/",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 204, response.text
    with scopes_disabled():
        assert not Review.objects.filter(pk=review_pk).exists()


@pytest.mark.django_db
def test_reviewviewset_delete_other_returns_403(
    client, review_token, event, other_review
):
    """Reviewer cannot delete another reviewer's review."""
    response = client.delete(
        event.api_urls.reviews + f"{other_review.pk}/",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text
    with scopes_disabled():
        assert Review.objects.filter(pk=other_review.pk).exists()


@pytest.mark.django_db
def test_reviewviewset_delete_phase_disallows_returns_403(
    client, review_token, event, review
):
    """Reviewer cannot delete review when phase has can_review=False."""
    with scopes_disabled():
        phase = event.active_review_phase
        phase.can_review = False
        phase.save()

    response = client.delete(
        event.api_urls.reviews + f"{review.pk}/",
        headers={"Authorization": f"Token {review_token.token}"},
    )

    assert response.status_code == 403, response.text
    with scopes_disabled():
        assert Review.objects.filter(pk=review.pk).exists()


@pytest.mark.django_db
def test_reviewviewset_delete_anonymous_returns_404(client, event, review):
    """Anonymous users get 404 when trying to delete a review."""
    response = client.delete(event.api_urls.reviews + f"{review.pk}/")

    assert response.status_code == 404, response.text
    with scopes_disabled():
        assert Review.objects.filter(pk=review.pk).exists()
