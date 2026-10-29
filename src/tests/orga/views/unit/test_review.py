# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage

from pretalx.orga.views.review import (
    BulkReview,
    BulkTagging,
    RegenerateDecisionMails,
    ReviewAssignment,
    ReviewDashboard,
    ReviewSubmission,
    ReviewSubmissionDelete,
)
from pretalx.submission.models import QuestionTarget, QuestionVariant, SubmissionStates
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    ReviewPhaseFactory,
    ReviewScoreCategoryFactory,
    SpeakerFactory,
    SubmissionCommentFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, make_request, make_view, query_dict, refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _make_reviewer(event, **extra_kwargs):
    return make_orga_user(
        event,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_organiser_settings=False,
        **extra_kwargs,
    )


def _review_view(event, user, submission, get_params=None):
    request = make_request(event, user=user)
    request.GET = query_dict(get_params)
    return make_view(ReviewSubmission, request, code=submission.code)


@pytest.mark.parametrize(
    ("review_count", "expected"),
    (
        (None, {"zero", "one", "two"}),
        ("1,", {"one", "two"}),
        (",1", {"zero", "one"}),
        ("1,1", {"one"}),
        (",2", {"zero", "one", "two"}),
        ("invalid", {"zero", "one", "two"}),
        ("0,", {"zero", "one", "two"}),
    ),
    ids=("none", "min", "max", "min-and-max", "max-at-ceiling", "invalid", "zero-min"),
)
def test_review_dashboard_filter_review_count_range(event, review_count, expected):
    reviewer = _make_reviewer(event)
    SubmissionFactory(event=event, title="zero")
    ReviewFactory(submission=SubmissionFactory(event=event, title="one"), user=reviewer)
    two = SubmissionFactory(event=event, title="two")
    ReviewFactory(submission=two)
    ReviewFactory(submission=two)
    request = make_request(event, user=reviewer)
    request.GET = query_dict({"review-count": review_count} if review_count else {})
    view = make_view(ReviewDashboard, request)

    assert {entry.title for entry in view.get_queryset()} == expected


def test_review_dashboard_properties_for_orga():
    event = EventFactory(feature_flags={"use_tracks": True})
    user = make_orga_user(event, can_change_submissions=True)
    bare = make_view(ReviewDashboard, make_request(event, user=user))

    assert bare.can_change_submissions is True
    assert bare.can_see_all_reviews is True
    assert bare.can_accept_submissions is False
    assert bare.show_submission_types is False
    assert bare.show_tracks is False

    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    ReviewFactory(submission=submission)
    ReviewFactory(submission=submission)
    SubmissionTypeFactory(event=event)
    TrackFactory(event=event)
    visible_q = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.STRING,
        is_visible_to_reviewers=True,
    )
    hidden_q = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.STRING,
        is_visible_to_reviewers=False,
    )
    independent = ReviewScoreCategoryFactory(
        event=event, is_independent=True, active=True
    )
    ReviewScoreCategoryFactory(event=event, is_independent=False, active=True)
    view = make_view(ReviewDashboard, make_request(refresh(event), user=user))

    assert view.can_accept_submissions is True
    assert view.max_review_count == 2
    assert view.show_submission_types is True
    assert view.show_tracks is True
    assert set(view.short_questions) == {visible_q, hidden_q}
    assert list(view.independent_categories) == [independent]


def test_review_dashboard_properties_for_reviewer(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, user=reviewer)
    visible_q = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.STRING,
        is_visible_to_reviewers=True,
    )
    QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.STRING,
        is_visible_to_reviewers=False,
    )
    view = make_view(ReviewDashboard, make_request(event, user=reviewer))

    assert view.can_change_submissions is False
    assert view.reviews_open is True
    assert list(view.submissions_reviewed) == [submission.pk]
    assert list(view.short_questions) == [visible_q]


@pytest.mark.parametrize(
    ("post_data", "expected"), (({"pending": "on"}, True), ({}, False))
)
def test_review_dashboard_get_pending(event, post_data, expected):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, method="post")
    request.POST = post_data
    view = make_view(ReviewDashboard, request)

    result = view.get_pending(request)
    assert result is expected


def test_review_dashboard_get_table_kwargs_shows_filtered_columns():
    event = EventFactory(feature_flags={"use_tracks": True})
    user = make_orga_user(event, can_change_submissions=True)
    TrackFactory(event=event)
    TrackFactory(event=event)
    SubmissionTypeFactory(event=event)
    tag = TagFactory(event=event)
    request = make_request(event, user=user)
    request.GET = query_dict({"tags": str(tag.pk)})
    view = make_view(ReviewDashboard, request)
    view.object_list = []
    list(view.get_queryset())

    kwargs = view.get_table_kwargs()

    assert "track" not in kwargs["exclude"]
    assert "submission_type" not in kwargs["exclude"]
    assert "tags" not in kwargs["exclude"]


def test_review_submission_as_reviewer_with_own_review(event):
    reviewer = _make_reviewer(event)
    other_reviewer = _make_reviewer(event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    other = SubmissionFactory(event=event)
    other.speakers.add(speaker)
    review = ReviewFactory(submission=submission, user=reviewer, text="Nice talk")
    ReviewFactory(submission=submission, user=other_reviewer, text="Other review")
    view = _review_view(event, reviewer, submission)

    assert view.submission == submission
    assert view.object == review
    assert view.is_speaker is False
    assert view.read_only is False
    assert view.review_display["text"] == "Nice talk"
    assert view.review_display["user"] == reviewer
    assert [r["text"] for r in view.reviews] == ["Other review"]
    assert view.speakers == [{"speaker": speaker, "other_submissions": [other]}]
    assert view.has_anonymised_review is False
    assert view.tags_form is None


def test_review_submission_as_speaker_is_read_only(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    profile = SpeakerFactory(user=reviewer, event=event)
    submission.speakers.add(profile)
    ReviewFactory(submission=submission, user=reviewer)
    ReviewFactory(submission=submission)
    view = _review_view(event, reviewer, submission)

    assert view.is_speaker is True
    assert view.read_only is True
    assert view.review_display is None
    assert view.reviews == []


def test_review_submission_without_review_in_anonymised_phase(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(SpeakerFactory(event=event))
    ReviewPhaseFactory(event=event, can_see_speaker_names=False)
    view = _review_view(event, reviewer, submission)

    assert view.object is None
    assert view.has_anonymised_review is True


@pytest.mark.parametrize(
    ("can_change_submissions", "can_tag_submissions", "expected"),
    ((False, "never", False), (False, "use_tags", True), (True, "never", True)),
    ids=("reviewer-disabled", "reviewer-enabled", "orga-permission"),
)
def test_review_submission_tags_form(
    event, can_change_submissions, can_tag_submissions, expected
):
    user = make_orga_user(
        event, is_reviewer=True, can_change_submissions=can_change_submissions
    )
    submission = SubmissionFactory(event=event)
    submission.speakers.add(SpeakerFactory(event=event))
    TagFactory(event=event)
    event.active_review_phase.can_tag_submissions = can_tag_submissions
    event.active_review_phase.save()
    view = _review_view(event, user, submission)

    assert (view.tags_form is not None) is expected


def test_review_submission_get_success_url_save(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    request = make_request(event, user=reviewer, method="post")
    request.POST = {"review_submit": "save"}
    request.session = {}
    view = make_view(ReviewSubmission, request, code=submission.code)

    url = view.get_success_url()

    assert url == submission.orga_urls.reviews


def test_review_submission_get_success_url_save_and_next_returns_event_url(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    # Mark the submission as reviewed so unreviewed_submissions_for_user
    # returns an empty queryset; the ignored list is empty too, so the
    # fallback branch must NOT re-run the same query.
    ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer, method="post")
    request.POST = {"review_submit": "save_and_next"}
    request.session = {}
    request._messages = FallbackStorage(request)
    view = make_view(ReviewSubmission, request, code=submission.code)

    url = view.get_success_url()

    assert url == event.orga_urls.reviews


def test_review_submission_get_success_url_skip_for_now_resets_ignored(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    other = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    other_speaker = SpeakerFactory(event=event)
    other.speakers.add(other_speaker)
    request = make_request(event, user=reviewer, method="post")
    request.POST = {"review_submit": "skip_for_now"}
    key = f"{event.slug}_ignored_reviews"
    request.session = {key: [submission.pk, other.pk]}
    view = make_view(ReviewSubmission, request, code=submission.code)

    url = view.get_success_url()

    # The session now contains just the current submission; ``other`` is
    # available again, so the redirect targets it.
    assert request.session[key] == [submission.pk]
    assert url == other.orga_urls.reviews


def test_review_submission_delete_object_and_action_object_name(event):
    reviewer = _make_reviewer(event)
    other_reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(SpeakerFactory(event=event))
    own = ReviewFactory(submission=submission, user=reviewer)
    other = ReviewFactory(submission=submission, user=other_reviewer)
    request = make_request(event, user=reviewer)
    own_view = make_view(
        ReviewSubmissionDelete, request, code=submission.code, pk=own.pk
    )
    other_view = make_view(
        ReviewSubmissionDelete, request, code=submission.code, pk=other.pk
    )

    assert own_view.get_object() == own
    assert "Your review" in str(own_view.action_object_name())
    assert other_reviewer.get_display_name() in str(other_view.action_object_name())


def test_review_view_mixin_context_without_comment_feature(event):
    event.feature_flags["use_submission_comments"] = False
    event.save()
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    SubmissionCommentFactory(submission=submission)
    review = ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(
        ReviewSubmissionDelete, request, code=submission.code, pk=review.pk
    )

    ctx = view.get_context_data()

    assert ctx["submission_comment_count"] is None
    assert ctx["has_submission_feedback"] is False


def test_regenerate_decision_mails_count(event):
    user = make_orga_user(event, can_change_submissions=True)
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    speaker1 = SpeakerFactory(event=event)
    accepted.speakers.add(speaker1)
    rejected = SubmissionFactory(event=event)
    rejected_speaker = SpeakerFactory(event=event)
    rejected.speakers.add(rejected_speaker)
    rejected.reject()
    request = make_request(event, user=user)
    view = make_view(RegenerateDecisionMails, request)

    assert view.count == 2


@pytest.mark.parametrize(
    ("get_params", "expected"),
    (
        ({}, "reviewer"),
        ({"direction": "reviewer"}, "reviewer"),
        ({"direction": "submission"}, "submission"),
        ({"direction": "invalid"}, "reviewer"),
    ),
)
def test_review_assignment_form_type(event, get_params, expected):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = get_params
    view = make_view(ReviewAssignment, request)

    assert view.form_type == expected
    assert view.direction() == expected


def test_review_assignment_review_teams_and_mapping(event):
    user = make_orga_user(event, can_change_submissions=True)
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, user=reviewer)
    submission.assigned_reviewers.add(reviewer)
    request = make_request(event, user=user)
    request.GET = query_dict()
    view = make_view(ReviewAssignment, request)

    mapping = view.review_mapping

    assert [team.is_reviewer for team in view.review_teams] == [True]
    assert mapping["reviewer_to_submissions"] == {reviewer.pk: [submission.pk]}
    assert mapping["submission_to_reviewers"] == {submission.pk: [reviewer.pk]}
    assert mapping["reviewer_to_assigned_submissions"] == {reviewer.pk: [submission.pk]}
    assert mapping["submission_to_assigned_reviewers"] == {submission.pk: [reviewer.pk]}


def test_bulk_review_submissions_and_categories(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(SpeakerFactory(event=event))
    request = make_request(event, user=reviewer)
    request.GET = query_dict()
    view = make_view(BulkReview, request)
    filtered_request = make_request(event, user=reviewer)
    filtered_request.GET = query_dict({"filter-state": "INVALID_STATE"})

    assert list(view.submissions) == [submission]
    assert list(make_view(BulkReview, filtered_request).submissions) == [submission]
    assert view.show_tracks is False
    assert list(view.categories) == [event.score_categories.get()]


def test_bulk_review_track_limited_categories():
    event = EventFactory(feature_flags={"use_tracks": True})
    reviewer = _make_reviewer(event)
    track = TrackFactory(event=event)
    category = event.score_categories.first()
    category.limit_tracks.add(track)
    submission = SubmissionFactory(event=event, track=track)
    submission.speakers.add(SpeakerFactory(event=event))
    request = make_request(event, user=reviewer)
    request.GET = query_dict()
    view = make_view(BulkReview, request)

    assert set(view._categories_by_track) == {track.pk, None}
    assert len(view._categories_for_submission(submission)) == 2
    assert submission.code in view.forms


def test_bulk_tagging_submissions(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    request = make_request(event, user=user)
    request.GET = query_dict()
    view = make_view(BulkTagging, request)

    subs = list(view.submissions)

    assert submission in subs
