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
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, make_request, make_view, query_dict

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _make_reviewer(event, **extra_kwargs):
    return make_orga_user(
        event,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_organiser_settings=False,
        **extra_kwargs,
    )


def test_review_dashboard_filter_range_no_filter(event):
    reviewer = _make_reviewer(event)
    SubmissionFactory(event=event)
    request = make_request(event, user=reviewer)
    request.GET = query_dict()
    view = make_view(ReviewDashboard, request)

    assert len(list(view.get_queryset())) == 1


def test_review_dashboard_filter_range_with_min(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    request.GET = query_dict({"review-count": "1,"})
    view = make_view(ReviewDashboard, request)

    assert len(list(view.get_queryset())) == 1


def test_review_dashboard_filter_range_with_max(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission)
    ReviewFactory(submission=submission)
    request = make_request(event, user=reviewer)
    request.GET = query_dict({"review-count": ",1"})
    view = make_view(ReviewDashboard, request)

    assert len(list(view.get_queryset())) == 0


def test_review_dashboard_filter_range_with_min_and_max(event):
    reviewer = _make_reviewer(event)
    sub1 = SubmissionFactory(event=event)
    ReviewFactory(submission=sub1)
    sub2 = SubmissionFactory(event=event)
    ReviewFactory(submission=sub2)
    ReviewFactory(submission=sub2)
    ReviewFactory(submission=sub2)
    request = make_request(event, user=reviewer)
    request.GET = query_dict({"review-count": "1,2"})
    view = make_view(ReviewDashboard, request)

    result = list(view.get_queryset())
    assert len(result) == 1
    assert result[0].pk == sub1.pk


def test_review_dashboard_filter_range_max_at_ceiling(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission)
    ReviewFactory(submission=submission)
    request = make_request(event, user=reviewer)
    request.GET = query_dict({"review-count": ",2"})
    view = make_view(ReviewDashboard, request)

    # The ceiling is the highest count there is, so it narrows nothing.
    assert len(list(view.get_queryset())) == 1


def test_review_dashboard_filter_range_invalid(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    request = make_request(event, user=reviewer)
    request.GET = query_dict({"review-count": "invalid"})
    view = make_view(ReviewDashboard, request)

    # A nonsense range narrows nothing instead of erroring or hiding rows.
    assert [entry.pk for entry in view.get_queryset()] == [submission.pk]


def test_review_dashboard_can_change_submissions_orga(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.can_change_submissions is True


def test_review_dashboard_can_change_submissions_reviewer(event):
    reviewer = _make_reviewer(event)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewDashboard, request)

    assert view.can_change_submissions is False


def test_review_dashboard_can_accept_submissions_with_submitted(event):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.can_accept_submissions is True


def test_review_dashboard_can_accept_submissions_without_submitted(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.can_accept_submissions is False


def test_review_dashboard_can_see_all_reviews_orga(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.can_see_all_reviews is True


def test_review_dashboard_max_review_count(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission)
    ReviewFactory(submission=submission)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.max_review_count == 2


def test_review_dashboard_submissions_reviewed(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewDashboard, request)

    reviewed = list(view.submissions_reviewed)

    assert reviewed == [submission.pk]


def test_review_dashboard_show_submission_types_single(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.show_submission_types is False


def test_review_dashboard_show_submission_types_multiple(event):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionTypeFactory(event=event)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.show_submission_types is True


def test_review_dashboard_short_questions_orga(event):
    user = make_orga_user(event, can_change_submissions=True)
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
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    result = list(view.short_questions)

    assert set(result) == {visible_q, hidden_q}


def test_review_dashboard_short_questions_reviewer(event):
    reviewer = _make_reviewer(event)
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
    request = make_request(event, user=reviewer)
    view = make_view(ReviewDashboard, request)

    result = list(view.short_questions)

    assert result == [visible_q]


def test_review_dashboard_independent_categories(event):
    user = make_orga_user(event, can_change_submissions=True)
    independent = ReviewScoreCategoryFactory(
        event=event, is_independent=True, active=True
    )
    ReviewScoreCategoryFactory(event=event, is_independent=False, active=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    result = list(view.independent_categories)

    assert result == [independent]


def test_review_dashboard_show_tracks_when_tracks_exist():
    event = EventFactory(feature_flags={"use_tracks": True})
    user = make_orga_user(event, can_change_submissions=True)
    TrackFactory(event=event)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.show_tracks is True


def test_review_dashboard_show_tracks_without(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.show_tracks is False


def test_review_dashboard_reviews_open(event):
    reviewer = _make_reviewer(event)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewDashboard, request)

    result = view.reviews_open

    assert result is True


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


def test_review_view_mixin_submission(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.submission

    assert result == submission


def test_review_view_mixin_object_returns_own_review(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    review = ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.object

    assert result == review


def test_review_view_mixin_object_returns_none_without_review(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.object

    assert result is None


def test_review_view_mixin_read_only_for_speaker(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    profile = SpeakerFactory(user=reviewer, event=event)
    submission.speakers.add(profile)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    assert view.read_only is True


def test_review_submission_is_speaker_true(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    profile = SpeakerFactory(user=reviewer, event=event)
    submission.speakers.add(profile)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    assert view.is_speaker is True


def test_review_submission_is_speaker_false(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    assert view.is_speaker is False


def test_review_submission_review_display_with_review(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    ReviewFactory(submission=submission, user=reviewer, text="Nice talk")
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.review_display

    assert result is not None
    assert result["text"] == "Nice talk"
    assert result["user"] == reviewer


def test_review_submission_review_display_none_for_speaker(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    profile = SpeakerFactory(user=reviewer, event=event)
    submission.speakers.add(profile)
    ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.review_display

    assert result is None


def test_review_submission_has_anonymised_review(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    ReviewPhaseFactory(event=event, can_see_speaker_names=False)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    assert view.has_anonymised_review is True


def test_review_submission_has_anonymised_review_false(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.has_anonymised_review

    assert result is False


def test_review_submission_reviews_as_speaker_returns_empty(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    profile = SpeakerFactory(user=reviewer, event=event)
    submission.speakers.add(profile)
    ReviewFactory(submission=submission)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.reviews

    assert result == []


def test_review_submission_reviews_as_reviewer(event):
    reviewer = _make_reviewer(event)
    other_reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    ReviewFactory(submission=submission, user=reviewer)
    ReviewFactory(submission=submission, user=other_reviewer, text="Other review")
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.reviews

    assert len(result) == 1
    assert result[0]["text"] == "Other review"


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


def test_review_submission_tags_form_no_tags(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.tags_form

    assert result is None


def test_review_submission_tags_form_tagging_disabled(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    TagFactory(event=event)
    event.active_review_phase.can_tag_submissions = "never"
    event.active_review_phase.save()
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.tags_form

    assert result is None


def test_review_submission_tags_form_tagging_enabled(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    TagFactory(event=event)
    event.active_review_phase.can_tag_submissions = "use_tags"
    event.active_review_phase.save()
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.tags_form

    assert result is not None


def test_review_submission_tags_form_orga_permission(event):
    user = make_orga_user(event, can_change_submissions=True, is_reviewer=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    TagFactory(event=event)
    event.active_review_phase.can_tag_submissions = "never"
    event.active_review_phase.save()
    request = make_request(event, user=user)
    view = make_view(ReviewSubmission, request, code=submission.code)

    result = view.tags_form

    assert result is not None


def test_review_submission_delete_action_object_name_own(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    review = ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(
        ReviewSubmissionDelete, request, code=submission.code, pk=review.pk
    )

    result = view.action_object_name()

    assert "Your review" in str(result)


def test_review_submission_delete_action_object_name_other(event):
    reviewer = _make_reviewer(event)
    other_reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    review = ReviewFactory(submission=submission, user=other_reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(
        ReviewSubmissionDelete, request, code=submission.code, pk=review.pk
    )

    result = view.action_object_name()

    assert other_reviewer.get_display_name() in str(result)


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


def test_review_assignment_review_teams(event):
    user = make_orga_user(event, can_change_submissions=True)
    _make_reviewer(event)
    request = make_request(event, user=user)
    view = make_view(ReviewAssignment, request)

    teams = list(view.review_teams)

    assert len(teams) == 1
    assert teams[0].is_reviewer is True


def test_review_assignment_review_mapping(event):
    user = make_orga_user(event, can_change_submissions=True)
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, user=reviewer)
    submission.assigned_reviewers.add(reviewer)
    request = make_request(event, user=user)
    request.GET = query_dict()
    view = make_view(ReviewAssignment, request)

    mapping = view.review_mapping

    assert "reviewer_to_submissions" in mapping
    assert "submission_to_reviewers" in mapping
    assert "reviewer_to_assigned_submissions" in mapping
    assert "submission_to_assigned_reviewers" in mapping
    assert reviewer.pk in mapping["reviewer_to_submissions"]
    assert submission.pk in mapping["submission_to_assigned_reviewers"]


def test_bulk_review_submissions(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    request.GET = query_dict()
    view = make_view(BulkReview, request)

    subs = list(view.submissions)

    assert len(subs) == 1


def test_bulk_review_submissions_with_invalid_filter(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    request.GET = query_dict({"filter-state": "INVALID_STATE"})
    view = make_view(BulkReview, request)

    subs = list(view.submissions)

    assert len(subs) == 1
    assert subs[0] == submission


def test_bulk_review_show_tracks(event):
    reviewer = _make_reviewer(event)
    request = make_request(event, user=reviewer)
    view = make_view(BulkReview, request)

    assert view.show_tracks is False


def test_bulk_review_categories(event):
    reviewer = _make_reviewer(event)
    request = make_request(event, user=reviewer)
    view = make_view(BulkReview, request)

    cats = list(view.categories)

    assert len(cats) == 1


def test_bulk_review_categories_by_track():
    event = EventFactory(feature_flags={"use_tracks": True})
    reviewer = _make_reviewer(event)
    track = TrackFactory(event=event)
    category = event.score_categories.first()
    category.limit_tracks.add(track)
    request = make_request(event, user=reviewer)
    request.GET = query_dict()
    view = make_view(BulkReview, request)

    result = view._categories_by_track

    assert track.pk in result
    assert None in result


def test_bulk_review_categories_for_submission():
    event = EventFactory(feature_flags={"use_tracks": True})
    reviewer = _make_reviewer(event)
    track = TrackFactory(event=event)
    category = event.score_categories.first()
    category.limit_tracks.add(track)
    submission = SubmissionFactory(event=event, track=track)
    request = make_request(event, user=reviewer)
    request.GET = query_dict()
    view = make_view(BulkReview, request)

    cats = view._categories_for_submission(submission)

    assert len(cats) == 2


def test_bulk_tagging_submissions(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    request = make_request(event, user=user)
    request.GET = query_dict()
    view = make_view(BulkTagging, request)

    subs = list(view.submissions)

    assert submission in subs


def test_review_dashboard_filter_range_with_zero_min(event):
    reviewer = _make_reviewer(event)
    SubmissionFactory(event=event)
    request = make_request(event, user=reviewer)
    request.GET = query_dict({"review-count": "0,"})
    view = make_view(ReviewDashboard, request)

    assert len(list(view.get_queryset())) == 1


def test_review_dashboard_get_table_kwargs_tracks_shown():
    event = EventFactory(feature_flags={"use_tracks": True})
    user = make_orga_user(event, can_change_submissions=True)
    TrackFactory(event=event)
    TrackFactory(event=event)
    SubmissionTypeFactory(event=event)
    request = make_request(event, user=user)
    request.GET = query_dict()
    view = make_view(ReviewDashboard, request)
    view.object_list = []

    kwargs = view.get_table_kwargs()

    assert "track" not in kwargs["exclude"]
    assert "submission_type" not in kwargs["exclude"]


def test_review_dashboard_get_table_kwargs_tags_filter_set():
    event = EventFactory(feature_flags={"use_tracks": True})
    user = make_orga_user(event, can_change_submissions=True)
    tag = TagFactory(event=event)
    request = make_request(event, user=user)
    request.GET = query_dict({"tags": str(tag.pk)})
    view = make_view(ReviewDashboard, request)
    view.object_list = []
    list(view.get_queryset())

    kwargs = view.get_table_kwargs()

    assert "tags" not in kwargs["exclude"]


def test_review_submission_delete_get_object(event):
    reviewer = _make_reviewer(event)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    review = ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(
        ReviewSubmissionDelete, request, code=submission.code, pk=review.pk
    )

    result = view.get_object()

    assert result == review


def test_bulk_review_forms_with_track_limited_categories():
    event = EventFactory(feature_flags={"use_tracks": True})
    reviewer = _make_reviewer(event)
    track = TrackFactory(event=event)
    category = event.score_categories.first()
    category.limit_tracks.add(track)
    submission = SubmissionFactory(event=event, track=track)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    request.GET = query_dict()
    view = make_view(BulkReview, request)

    forms = view.forms

    assert submission.code in forms
