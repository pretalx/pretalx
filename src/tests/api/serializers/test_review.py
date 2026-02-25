import pytest
from django_scopes import scopes_disabled
from rest_framework.exceptions import ValidationError

from pretalx.api.serializers.review import (
    ReviewerSerializer,
    ReviewScoreCategorySerializer,
    ReviewScoreSerializer,
    ReviewSerializer,
    ReviewWriteSerializer,
)
from tests.factories import (
    EventFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SubmissionFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_review_score_category_serializer_fields():
    with scopes_disabled():
        category = ReviewScoreCategoryFactory()
        request = make_api_request(category.event)

    serializer = ReviewScoreCategorySerializer(category, context={"request": request})
    with scopes_disabled():
        data = serializer.data

    assert set(data.keys()) == {
        "id",
        "name",
        "weight",
        "required",
        "active",
        "limit_tracks",
        "is_independent",
    }
    assert data["id"] == category.pk
    assert data["weight"] == "1.0"
    assert data["required"] is False
    assert data["active"] is True
    assert data["is_independent"] is False
    assert data["limit_tracks"] == []


@pytest.mark.django_db
def test_review_score_category_serializer_with_limit_tracks():
    with scopes_disabled():
        category = ReviewScoreCategoryFactory()
        track = TrackFactory(event=category.event)
        category.limit_tracks.add(track)
        request = make_api_request(category.event)

    serializer = ReviewScoreCategorySerializer(category, context={"request": request})

    with scopes_disabled():
        assert serializer.data["limit_tracks"] == [track.pk]


@pytest.mark.django_db
def test_review_score_serializer_fields():
    with scopes_disabled():
        score = ReviewScoreFactory(label="Good")
        request = make_api_request(score.category.event)

    serializer = ReviewScoreSerializer(score, context={"request": request})
    data = serializer.data

    assert set(data.keys()) == {"id", "category", "value", "label"}
    assert data["id"] == score.pk
    assert data["category"] == score.category.pk
    assert data["value"] == f"{score.value:.2f}"
    assert data["label"] == "Good"


@pytest.mark.django_db
def test_reviewer_serializer_fields():
    user = UserFactory()
    request = make_api_request(event=None, user=user)

    serializer = ReviewerSerializer(user, context={"request": request})
    data = serializer.data

    assert set(data.keys()) == {"code", "name", "email"}
    assert data["code"] == user.code
    assert data["name"] == user.name
    assert data["email"] == user.email


@pytest.mark.django_db
def test_review_write_serializer_init_without_event():
    """When no event is on the request, scores queryset and mandatory flags are not set."""
    request = make_api_request(event=None)
    serializer = ReviewWriteSerializer(context={"request": request})

    assert serializer.fields["answers"].required is False
    assert serializer.fields["score"].read_only is True


@pytest.mark.django_db
def test_review_write_serializer_init_with_event_defaults():
    with scopes_disabled():
        event = EventFactory()
        request = make_api_request(event)
        serializer = ReviewWriteSerializer(context={"request": request})

    assert serializer.fields["answers"].required is False
    assert serializer.fields["score"].read_only is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("text_mandatory", "score_mandatory"),
    ((True, False), (False, True), (True, True), (False, False)),
    ids=[
        "text_mandatory_only",
        "score_mandatory_only",
        "both_mandatory",
        "neither_mandatory",
    ],
)
def test_review_write_serializer_init_mandatory_settings(
    text_mandatory, score_mandatory
):
    with scopes_disabled():
        event = EventFactory()
    event.review_settings["text_mandatory"] = text_mandatory
    event.review_settings["score_mandatory"] = score_mandatory
    event.save()
    request = make_api_request(event)

    with scopes_disabled():
        serializer = ReviewWriteSerializer(context={"request": request})

    assert serializer.fields["text"].required is text_mandatory
    assert serializer.fields["scores"].required is score_mandatory


@pytest.mark.django_db
def test_review_write_serializer_init_submissions_context():
    with scopes_disabled():
        event = EventFactory()
        submission = SubmissionFactory(event=event)
        request = make_api_request(event)
        submissions_qs = event.submissions.all()
        serializer = ReviewWriteSerializer(
            context={"request": request, "submissions": submissions_qs}
        )

    assert list(serializer.fields["submission"].queryset) == [submission]


@pytest.mark.django_db
def test_review_write_serializer_init_scores_queryset_filtered_by_event():
    """Score choices are limited to ReviewScores belonging to the serializer's event."""
    with scopes_disabled():
        event = EventFactory()
        category = ReviewScoreCategoryFactory(event=event)
        score = ReviewScoreFactory(category=category)
        other_category = ReviewScoreCategoryFactory(event=EventFactory())
        other_score = ReviewScoreFactory(category=other_category)
        request = make_api_request(event)
        serializer = ReviewWriteSerializer(context={"request": request})

    scores_qs = serializer.fields["scores"].queryset
    assert score in scores_qs
    assert other_score not in scores_qs
    assert set(scores_qs.values_list("category__event", flat=True)) == {event.pk}


@pytest.mark.django_db
def test_review_write_serializer_validate_scores_unique_categories():
    with scopes_disabled():
        category_a = ReviewScoreCategoryFactory()
        category_b = ReviewScoreCategoryFactory(event=category_a.event)
        score_a = ReviewScoreFactory(category=category_a)
        score_b = ReviewScoreFactory(category=category_b)
        request = make_api_request(category_a.event)
        serializer = ReviewWriteSerializer(context={"request": request})

    result = serializer.validate_scores([score_a, score_b])

    assert result == [score_a, score_b]


@pytest.mark.django_db
def test_review_write_serializer_validate_scores_duplicate_category_raises():
    with scopes_disabled():
        category = ReviewScoreCategoryFactory()
        score_a = ReviewScoreFactory(category=category, value=1)
        score_b = ReviewScoreFactory(category=category, value=2)
        request = make_api_request(category.event)
        serializer = ReviewWriteSerializer(context={"request": request})

    with pytest.raises(ValidationError, match="one score per category"):
        serializer.validate_scores([score_a, score_b])


@pytest.mark.django_db
def test_review_write_serializer_validate_submission_already_reviewed():
    with scopes_disabled():
        review = ReviewFactory()
        event = review.submission.event
        request = make_api_request(event, user=review.user)
        serializer = ReviewWriteSerializer(context={"request": request})

    with scopes_disabled(), pytest.raises(ValidationError, match="already reviewed"):
        serializer.validate_submission(review.submission)


@pytest.mark.django_db
def test_review_write_serializer_validate_submission_not_yet_reviewed():
    with scopes_disabled():
        event = EventFactory()
        submission = SubmissionFactory(event=event)
    user = UserFactory()
    request = make_api_request(event, user=user)

    with scopes_disabled():
        serializer = ReviewWriteSerializer(context={"request": request})
        result = serializer.validate_submission(submission)

    assert result == submission


@pytest.mark.django_db
def test_review_write_serializer_create_sets_user():
    with scopes_disabled():
        event = EventFactory()
        submission = SubmissionFactory(event=event)
    user = UserFactory()
    request = make_api_request(event, user=user)

    with scopes_disabled():
        serializer = ReviewWriteSerializer(context={"request": request})
        review = serializer.create(
            {"submission": submission, "text": "Great talk", "answers": []}
        )

    assert review.user == user
    assert review.submission == submission
    assert review.text == "Great talk"


@pytest.mark.django_db
def test_review_write_serializer_create_with_scores():
    with scopes_disabled():
        event = EventFactory()
        submission = SubmissionFactory(event=event)
        category = ReviewScoreCategoryFactory(event=event)
        score = ReviewScoreFactory(category=category)
    user = UserFactory()
    request = make_api_request(event, user=user)

    with scopes_disabled():
        serializer = ReviewWriteSerializer(context={"request": request})
        review = serializer.create(
            {"submission": submission, "text": "Nice", "scores": [score], "answers": []}
        )
        assert list(review.scores.all()) == [score]


@pytest.mark.django_db
def test_review_write_serializer_create_without_scores():
    with scopes_disabled():
        event = EventFactory()
        submission = SubmissionFactory(event=event)
    user = UserFactory()
    request = make_api_request(event, user=user)

    with scopes_disabled():
        serializer = ReviewWriteSerializer(context={"request": request})
        review = serializer.create(
            {"submission": submission, "text": "Text only", "answers": []}
        )
        assert list(review.scores.all()) == []


@pytest.mark.django_db
def test_review_write_serializer_update_sets_user():
    with scopes_disabled():
        review = ReviewFactory()
    user = UserFactory()
    request = make_api_request(review.submission.event, user=user)

    with scopes_disabled():
        serializer = ReviewWriteSerializer(context={"request": request})
        updated = serializer.update(review, {"text": "Updated text", "answers": []})

    assert updated.user == user
    assert updated.text == "Updated text"


@pytest.mark.django_db
def test_review_write_serializer_update_with_scores():
    with scopes_disabled():
        review = ReviewFactory()
        category = ReviewScoreCategoryFactory(event=review.submission.event)
        score = ReviewScoreFactory(category=category)
    request = make_api_request(review.submission.event, user=review.user)

    with scopes_disabled():
        serializer = ReviewWriteSerializer(context={"request": request})
        updated = serializer.update(
            review, {"text": "Updated", "scores": [score], "answers": []}
        )
        assert list(updated.scores.all()) == [score]


@pytest.mark.django_db
def test_review_serializer_fields():
    with scopes_disabled():
        review = ReviewFactory()
        request = make_api_request(review.submission.event)
        serializer = ReviewSerializer(review, context={"request": request})
        data = serializer.data

    assert set(data.keys()) == {
        "id",
        "submission",
        "text",
        "score",
        "scores",
        "answers",
        "user",
    }
    assert data["id"] == review.pk
    assert data["submission"] == review.submission.code
    assert data["user"] == review.user.code
