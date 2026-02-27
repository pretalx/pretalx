# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from pretalx.orga.views.review import (
    BulkReview,
    BulkTagging,
    RegenerateDecisionMails,
    ReviewAssignment,
    ReviewAssignmentImport,
    ReviewDashboard,
    ReviewExport,
    ReviewSubmission,
    ReviewSubmissionDelete,
)
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import QuestionTarget, QuestionVariant, SubmissionStates
from tests.factories import (
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
from tests.utils import make_orga_user, make_request, make_view

pytestmark = pytest.mark.unit


def _make_reviewer(event, **extra_kwargs):
    return make_orga_user(
        event,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_organiser_settings=False,
        **extra_kwargs,
    )


@pytest.mark.django_db
def test_review_dashboard_filter_range_no_filter(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        SubmissionFactory(event=event)
    request = make_request(event, user=reviewer)
    request.GET = {}
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        qs = view.get_queryset()
        filtered = view.filter_range(qs)
        assert list(filtered) == list(qs)


@pytest.mark.django_db
def test_review_dashboard_filter_range_with_min(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    request.GET = {"review-count": "1,"}
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        qs = view.get_queryset()
        filtered = view.filter_range(qs)
        assert len(list(filtered)) == 1


@pytest.mark.django_db
def test_review_dashboard_filter_range_with_max(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        ReviewFactory(submission=submission)
        ReviewFactory(submission=submission)
    request = make_request(event, user=reviewer)
    request.GET = {"review-count": ",1"}
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        qs = view.get_queryset()
        filtered = view.filter_range(qs)
        assert len(list(filtered)) == 0


@pytest.mark.django_db
def test_review_dashboard_filter_range_with_min_and_max(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        sub1 = SubmissionFactory(event=event)
        ReviewFactory(submission=sub1)
        sub2 = SubmissionFactory(event=event)
        ReviewFactory(submission=sub2)
        ReviewFactory(submission=sub2)
        ReviewFactory(submission=sub2)
    request = make_request(event, user=reviewer)
    request.GET = {"review-count": "1,2"}
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        qs = view.get_queryset()
        filtered = view.filter_range(qs)
        result = list(filtered)
        assert len(result) == 1
        assert result[0].pk == sub1.pk


@pytest.mark.django_db
def test_review_dashboard_filter_range_max_at_ceiling(event):
    """When max_reviews >= max_review_count, the filter is not applied."""
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        ReviewFactory(submission=submission)
        ReviewFactory(submission=submission)
    request = make_request(event, user=reviewer)
    request.GET = {"review-count": ",2"}
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        qs = view.get_queryset()
        filtered = view.filter_range(qs)
        assert len(list(filtered)) == len(list(qs))


@pytest.mark.django_db
def test_review_dashboard_filter_range_invalid(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
    request = make_request(event, user=reviewer)
    request.GET = {"review-count": "invalid"}
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        qs = view.get_queryset()
        filtered = view.filter_range(qs)
        assert list(filtered) == list(qs)


@pytest.mark.django_db
def test_review_dashboard_can_change_submissions_orga(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.can_change_submissions is True


@pytest.mark.django_db
def test_review_dashboard_can_change_submissions_reviewer(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewDashboard, request)

    assert view.can_change_submissions is False


@pytest.mark.django_db
def test_review_dashboard_can_accept_submissions_with_submitted(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        assert view.can_accept_submissions is True


@pytest.mark.django_db
def test_review_dashboard_can_accept_submissions_without_submitted(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        assert view.can_accept_submissions is False


@pytest.mark.django_db
def test_review_dashboard_can_see_all_reviews_orga(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    assert view.can_see_all_reviews is True


@pytest.mark.django_db
def test_review_dashboard_max_review_count(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
        ReviewFactory(submission=submission)
        ReviewFactory(submission=submission)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        assert view.max_review_count == 2


@pytest.mark.django_db
def test_review_dashboard_submissions_reviewed(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        reviewed = list(view.submissions_reviewed)

    assert reviewed == [submission.pk]


@pytest.mark.django_db
def test_review_dashboard_show_submission_types_single(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        assert view.show_submission_types is False


@pytest.mark.django_db
def test_review_dashboard_show_submission_types_multiple(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        SubmissionTypeFactory(event=event)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        assert view.show_submission_types is True


@pytest.mark.django_db
def test_review_dashboard_short_questions_orga(event):
    with scopes_disabled():
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

    with scopes_disabled():
        result = list(view.short_questions)

    assert set(result) == {visible_q, hidden_q}


@pytest.mark.django_db
def test_review_dashboard_short_questions_reviewer(event):
    """Reviewers only see questions marked as visible to reviewers."""
    with scopes_disabled():
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

    with scopes_disabled():
        result = list(view.short_questions)

    assert result == [visible_q]


@pytest.mark.django_db
def test_review_dashboard_independent_categories(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        independent = ReviewScoreCategoryFactory(
            event=event, is_independent=True, active=True
        )
        ReviewScoreCategoryFactory(event=event, is_independent=False, active=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        result = list(view.independent_categories)

    assert result == [independent]


@pytest.mark.django_db
def test_review_dashboard_show_tracks_with_multiple(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        event.feature_flags["use_tracks"] = True
        event.save()
        TrackFactory(event=event)
        TrackFactory(event=event)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        assert view.show_tracks is True


@pytest.mark.django_db
def test_review_dashboard_show_tracks_without(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        assert view.show_tracks is False


@pytest.mark.django_db
def test_review_dashboard_reviews_open(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewDashboard, request)

    with scopes_disabled():
        result = view.reviews_open

    assert result is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("post_data", "expected"), (({"pending": "on"}, True), ({}, False))
)
def test_review_dashboard_get_pending(event, post_data, expected):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, method="post")
    request.POST = post_data
    view = make_view(ReviewDashboard, request)

    result = view.get_pending(request)
    assert result is expected


@pytest.mark.django_db
def test_review_view_mixin_submission(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.submission

    assert result == submission


@pytest.mark.django_db
def test_review_view_mixin_object_returns_own_review(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.object

    assert result == review


@pytest.mark.django_db
def test_review_view_mixin_object_returns_none_without_review(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.object

    assert result is None


@pytest.mark.django_db
def test_review_view_mixin_get_permission_object(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.get_permission_object()

    assert result == submission


@pytest.mark.django_db
def test_review_view_mixin_read_only_for_speaker(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        profile, _ = SpeakerProfile.objects.get_or_create(user=reviewer, event=event)
        submission.speakers.add(profile)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        assert view.read_only is True


@pytest.mark.django_db
def test_review_submission_is_speaker_true(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        profile, _ = SpeakerProfile.objects.get_or_create(user=reviewer, event=event)
        submission.speakers.add(profile)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        assert view.is_speaker is True


@pytest.mark.django_db
def test_review_submission_is_speaker_false(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        assert view.is_speaker is False


@pytest.mark.django_db
def test_review_submission_review_display_with_review(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        ReviewFactory(submission=submission, user=reviewer, text="Nice talk")
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.review_display

    assert result is not None
    assert result["text"] == "Nice talk"
    assert result["user"] == reviewer


@pytest.mark.django_db
def test_review_submission_review_display_none_for_speaker(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        profile, _ = SpeakerProfile.objects.get_or_create(user=reviewer, event=event)
        submission.speakers.add(profile)
        ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.review_display

    assert result is None


@pytest.mark.django_db
def test_review_submission_has_anonymised_review(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        ReviewPhaseFactory(event=event, can_see_speaker_names=False)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        assert view.has_anonymised_review is True


@pytest.mark.django_db
def test_review_submission_has_anonymised_review_false(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.has_anonymised_review

    assert result is False


@pytest.mark.django_db
def test_review_submission_reviews_as_speaker_returns_empty(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        profile, _ = SpeakerProfile.objects.get_or_create(user=reviewer, event=event)
        submission.speakers.add(profile)
        ReviewFactory(submission=submission)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.reviews

    assert result == []


@pytest.mark.django_db
def test_review_submission_reviews_as_reviewer(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        other_reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        ReviewFactory(submission=submission, user=reviewer)
        ReviewFactory(submission=submission, user=other_reviewer, text="Other review")
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.reviews

    assert len(result) == 1
    assert result[0]["text"] == "Other review"


@pytest.mark.django_db
def test_review_submission_get_form_kwargs(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)
    view.model = ReviewSubmission.model
    view.form_class = ReviewSubmission.form_class
    view.fields = None

    with scopes_disabled():
        kwargs = view.get_form_kwargs()

    assert kwargs["event"] == event
    assert kwargs["user"] == reviewer
    assert kwargs["submission"] == submission


@pytest.mark.django_db
def test_review_submission_get_success_url_save(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    request = make_request(event, user=reviewer, method="post")
    request.POST = {"review_submit": "save"}
    request.session = {}
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        url = view.get_success_url()

    assert url == submission.orga_urls.reviews


@pytest.mark.django_db
def test_review_submission_tags_form_no_tags(event):
    """Tags form is None when event has no tags."""
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.tags_form

    assert result is None


@pytest.mark.django_db
def test_review_submission_tags_form_tagging_disabled(event):
    """Tags form is None when tagging is disabled for reviewers."""
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        TagFactory(event=event)
        event.active_review_phase.can_tag_submissions = "never"
        event.active_review_phase.save()
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.tags_form

    assert result is None


@pytest.mark.django_db
def test_review_submission_tags_form_tagging_enabled(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        TagFactory(event=event)
        event.active_review_phase.can_tag_submissions = "use_tags"
        event.active_review_phase.save()
    request = make_request(event, user=reviewer)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.tags_form

    assert result is not None


@pytest.mark.django_db
def test_review_submission_tags_form_orga_permission(event):
    """Users with orga_update_submission permission always get the tags form."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True, is_reviewer=True)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        TagFactory(event=event)
        event.active_review_phase.can_tag_submissions = "never"
        event.active_review_phase.save()
    request = make_request(event, user=user)
    view = make_view(ReviewSubmission, request, code=submission.code)

    with scopes_disabled():
        result = view.tags_form

    assert result is not None


@pytest.mark.django_db
def test_review_submission_delete_action_object_name_own(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(
        ReviewSubmissionDelete, request, code=submission.code, pk=review.pk
    )

    with scopes_disabled():
        result = view.action_object_name()

    assert "Your review" in str(result)


@pytest.mark.django_db
def test_review_submission_delete_action_object_name_other(event):
    with scopes_disabled():
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

    with scopes_disabled():
        result = view.action_object_name()

    assert other_reviewer.get_display_name() in str(result)


@pytest.mark.django_db
def test_review_submission_delete_action_back_url(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        review = ReviewFactory(submission=submission, user=reviewer)
    request = make_request(event, user=reviewer)
    view = make_view(
        ReviewSubmissionDelete, request, code=submission.code, pk=review.pk
    )

    with scopes_disabled():
        url = view.action_back_url

    assert url == submission.orga_urls.reviews


@pytest.mark.django_db
def test_regenerate_decision_mails_count(event):
    with scopes_disabled():
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

    with scopes_disabled():
        assert view.count == 2


@pytest.mark.django_db
def test_regenerate_decision_mails_action_text(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(RegenerateDecisionMails, request)

    with scopes_disabled():
        text = view.action_text()

    assert "regenerate" in str(text).lower()


@pytest.mark.django_db
def test_regenerate_decision_mails_action_back_url(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(RegenerateDecisionMails, request)

    assert view.action_back_url == event.orga_urls.reviews


@pytest.mark.django_db
def test_review_assignment_form_type_default(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(ReviewAssignment, request)

    assert view.form_type == "reviewer"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("direction_param", "expected"),
    (("reviewer", "reviewer"), ("submission", "submission"), ("invalid", "reviewer")),
)
def test_review_assignment_form_type(event, direction_param, expected):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = {"direction": direction_param}
    view = make_view(ReviewAssignment, request)

    assert view.form_type == expected


@pytest.mark.django_db
def test_review_assignment_tablist(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewAssignment, request)

    result = view.tablist()
    assert set(result.keys()) == {"group", "individual"}


@pytest.mark.django_db
def test_review_assignment_review_teams(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        _make_reviewer(event)
    request = make_request(event, user=user)
    view = make_view(ReviewAssignment, request)

    with scopes_disabled():
        teams = list(view.review_teams)

    assert len(teams) == 1
    assert teams[0].is_reviewer is True


@pytest.mark.django_db
def test_review_assignment_review_mapping(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        ReviewFactory(submission=submission, user=reviewer)
        submission.assigned_reviewers.add(reviewer)
    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(ReviewAssignment, request)

    with scopes_disabled():
        mapping = view.review_mapping

    assert "reviewer_to_submissions" in mapping
    assert "submission_to_reviewers" in mapping
    assert "reviewer_to_assigned_submissions" in mapping
    assert "submission_to_assigned_reviewers" in mapping
    assert reviewer.pk in mapping["reviewer_to_submissions"]
    assert submission.pk in mapping["submission_to_assigned_reviewers"]


@pytest.mark.django_db
def test_review_assignment_import_submit_buttons(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewAssignmentImport, request)

    buttons = view.submit_buttons()
    assert len(buttons) == 1


@pytest.mark.django_db
def test_review_export_tablist(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewExport, request)

    result = view.tablist()
    assert set(result.keys()) == {"custom", "api"}


@pytest.mark.django_db
def test_review_export_get_form_kwargs(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ReviewExport, request)
    view.form_class = ReviewExport.form_class
    view.prefix = None
    view.initial = {}

    kwargs = view.get_form_kwargs()

    assert kwargs["event"] == event
    assert kwargs["user"] == user


@pytest.mark.django_db
def test_bulk_review_submissions(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    request = make_request(event, user=reviewer)
    request.GET = {}
    view = make_view(BulkReview, request)

    with scopes_disabled():
        subs = list(view.submissions)

    assert len(subs) == 1


@pytest.mark.django_db
def test_bulk_review_show_tracks(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
    request = make_request(event, user=reviewer)
    view = make_view(BulkReview, request)

    with scopes_disabled():
        assert view.show_tracks is False


@pytest.mark.django_db
def test_bulk_review_categories(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
    request = make_request(event, user=reviewer)
    view = make_view(BulkReview, request)

    with scopes_disabled():
        cats = list(view.categories)

    assert len(cats) == 1


@pytest.mark.django_db
def test_bulk_review_categories_by_track(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)
        category = event.score_categories.first()
        category.limit_tracks.add(track)
    request = make_request(event, user=reviewer)
    request.GET = {}
    view = make_view(BulkReview, request)

    with scopes_disabled():
        result = view._categories_by_track

    assert track.pk in result
    assert None in result


@pytest.mark.django_db
def test_bulk_review_categories_for_submission(event):
    with scopes_disabled():
        reviewer = _make_reviewer(event)
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)
        category = event.score_categories.first()
        category.limit_tracks.add(track)
        submission = SubmissionFactory(event=event, track=track)
    request = make_request(event, user=reviewer)
    request.GET = {}
    view = make_view(BulkReview, request)

    with scopes_disabled():
        cats = view._categories_for_submission(submission)

    assert len(cats) == 2


@pytest.mark.django_db
def test_bulk_tagging_submissions(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(BulkTagging, request)

    with scopes_disabled():
        subs = list(view.submissions)

    assert submission in subs


@pytest.mark.django_db
@pytest.mark.parametrize(("is_reviewer", "expected"), ((False, False), (True, True)))
def test_bulk_tagging_can_view_speakers(event, is_reviewer, expected):
    with scopes_disabled():
        user = make_orga_user(
            event, can_change_submissions=True, is_reviewer=is_reviewer
        )
    request = make_request(event, user=user)
    view = make_view(BulkTagging, request)

    with scopes_disabled():
        assert view.can_view_speakers is expected
