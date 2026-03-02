# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json

import pytest
from django.http import Http404
from django.urls import ResolverMatch
from django.utils.timezone import now as tz_now

from pretalx.orga.views.submission import (
    AllFeedbacksList,
    Anonymise,
    ApplyPendingBulk,
    CommentDelete,
    CommentList,
    FeedbackList,
    SubmissionContent,
    SubmissionDelete,
    SubmissionFeed,
    SubmissionHistory,
    SubmissionList,
    SubmissionSpeakers,
    SubmissionStateChange,
    SubmissionStats,
    TagView,
)
from pretalx.submission.models import QuestionTarget, QuestionVariant, SubmissionStates
from tests.factories import (
    EventFactory,
    FeedbackFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionCommentFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_submission_view_mixin_get_submission_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionStateChange, request, code=submission.code)

    qs = list(view._get_submission_queryset())

    assert qs == [submission]


def test_submission_view_mixin_get_lightweight_submission_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionStateChange, request, code=submission.code)

    qs = list(view._get_lightweight_submission_queryset())

    assert qs == [submission]


def test_submission_view_mixin_object_resolves_by_code(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert view.object == submission


def test_submission_view_mixin_has_anonymised_review(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert view.has_anonymised_review is False


def test_submission_view_mixin_has_anonymised_review_with_anon_phase(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    phase = event.review_phases.first()
    phase.can_see_speaker_names = False
    phase.save()

    request = make_request(event, user=user)
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert view.has_anonymised_review is True


def test_submission_view_mixin_is_publicly_visible_false(event):
    """Non-public events have non-visible submissions."""
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert view.is_publicly_visible is False


def test_submission_state_change_action(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(
        event,
        user=user,
        resolver_match=ResolverMatch(
            lambda: None, (), {}, url_name="submissions.accept"
        ),
    )
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert view._action == "accept"


def test_submission_state_change_target(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(
        event,
        user=user,
        resolver_match=ResolverMatch(
            lambda: None, (), {}, url_name="submissions.reject"
        ),
    )
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert view._target == SubmissionStates.REJECTED
    assert view.target() == SubmissionStates.REJECTED


def test_submission_state_change_next_url(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    next_url = event.orga_urls.submissions

    request = make_request(
        event,
        user=user,
        path=f"/?next={next_url}",
        resolver_match=ResolverMatch(
            lambda: None, (), {}, url_name="submissions.accept"
        ),
    )
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert view.next_url == next_url


def test_submission_state_change_get_success_url_with_next(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    next_url = event.orga_urls.submissions

    request = make_request(
        event,
        user=user,
        path=f"/?next={next_url}",
        resolver_match=ResolverMatch(
            lambda: None, (), {}, url_name="submissions.accept"
        ),
    )
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert view.get_success_url() == next_url


def test_submission_state_change_get_success_url_default(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(
        event,
        user=user,
        resolver_match=ResolverMatch(
            lambda: None, (), {}, url_name="submissions.accept"
        ),
    )
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert view.get_success_url() == event.orga_urls.submissions


def test_submission_delete_action_text_without_slots(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionDelete, request, code=submission.code)

    text = view.action_text

    assert "schedule" not in str(text).lower()


def test_submission_delete_action_text_with_slots(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission, is_visible=True)
    slot.schedule.freeze("v1", notify_speakers=False)

    request = make_request(event, user=user)
    view = make_view(SubmissionDelete, request, code=submission.code)

    text = str(view.action_text)

    assert "schedule" in text.lower()


def test_submission_delete_action_back_url(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SubmissionDelete, request, code=submission.code)

    assert view.action_back_url == submission.orga_urls.base


def test_submission_speakers_speakers_property(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SubmissionSpeakers, request, code=submission.code)

    speakers = view.speakers

    assert len(speakers) == 1
    assert speakers[0]["speaker"] == speaker


def test_submission_speakers_invitations_property(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SubmissionSpeakers, request, code=submission.code)

    invitations = list(view.invitations)

    assert invitations == []


def test_submission_speakers_get_form_kwargs_includes_event(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SubmissionSpeakers, request, code=submission.code)
    view.form_class = SubmissionSpeakers.form_class
    view.prefix = None
    view.initial = {}

    kwargs = view.get_form_kwargs()

    assert kwargs["event"] == event


def test_submission_speakers_get_success_url(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SubmissionSpeakers, request, code=submission.code)

    assert view.get_success_url() == submission.orga_urls.speakers


def test_submission_content_object_returns_none_for_new(event):
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user, path="/orga/event/test/submissions/new/")
    view = make_view(SubmissionContent, request)

    assert view.object is None


def test_submission_content_object_returns_submission(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionContent, request, code=submission.code)

    assert view.object == submission


def test_submission_content_get_permission_required_for_create(event):
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user, path="/orga/event/test/submissions/new/")
    view = make_view(SubmissionContent, request)
    view.permission_action = "create"

    assert view.get_permission_required() == ["submission.create_submission"]


def test_submission_content_get_permission_required_for_update(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionContent, request, code=submission.code)
    view.permission_action = "update"

    assert view.get_permission_required() == ["submission.orga_list_submission"]


def test_submission_content_can_edit_true_for_orga(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionContent, request, code=submission.code)

    assert view.can_edit is True


def test_submission_content_can_edit_false_for_reviewer(event):
    reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
    submission = SubmissionFactory(event=event)

    request = make_request(event, user=reviewer)
    view = make_view(SubmissionContent, request, code=submission.code)

    assert view.can_edit is False


def test_submission_list_mixin_get_default_filters_orga(event):
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SubmissionList, request)

    filters = view.get_default_filters()

    assert "code__icontains" in filters
    assert "title__icontains" in filters
    assert "speakers__user__name__icontains" in filters
    assert "speakers__name__icontains" in filters


def test_submission_list_mixin_get_default_filters_reviewer_no_speaker_search(event):
    """Reviewers without speaker list permission don't get speaker search fields."""
    reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
    phase = event.review_phases.first()
    phase.can_see_speaker_names = False
    phase.save()

    request = make_request(event, user=reviewer)
    request.GET = {}
    view = make_view(SubmissionList, request)

    filters = view.get_default_filters()

    assert "code__icontains" in filters
    assert "title__icontains" in filters
    assert "speakers__user__name__icontains" not in filters
    assert "speakers__name__icontains" not in filters


def test_submission_list_pending_changes_count(event):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event, pending_state=SubmissionStates.ACCEPTED)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SubmissionList, request)

    assert view.pending_changes == 1


def test_submission_list_show_tracks_false_when_disabled():
    event = EventFactory(feature_flags={"use_tracks": False})
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SubmissionList, request)

    assert not view.show_tracks


def test_submission_list_show_tracks_true_when_multiple():
    event = EventFactory(feature_flags={"use_tracks": True})
    user = make_orga_user(event, can_change_submissions=True)
    TrackFactory(event=event)
    TrackFactory(event=event)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SubmissionList, request)

    assert view.show_tracks is True


def test_submission_list_show_submission_types(event):
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SubmissionList, request)

    assert view.show_submission_types is False


def test_submission_list_short_questions(event):
    user = make_orga_user(event, can_change_submissions=True)
    short_q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )
    QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.TEXT
    )
    QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
    )

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SubmissionList, request)

    result = list(view.short_questions)

    assert result == [short_q]


def test_feedback_list_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    feedback = FeedbackFactory(talk=submission)

    request = make_request(event, user=user)
    view = make_view(FeedbackList, request, code=submission.code)

    qs = list(view.get_queryset())

    assert qs == [feedback]


def test_feedback_list_table_kwargs_excludes_talk(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(FeedbackList, request, code=submission.code)

    kwargs = view.get_table_kwargs()

    assert kwargs["include_talk"] is False


def test_all_feedbacks_list_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    feedback = FeedbackFactory(talk=submission)
    other_submission = SubmissionFactory()
    FeedbackFactory(talk=other_submission)

    request = make_request(event, user=user)
    view = make_view(AllFeedbacksList, request)

    qs = list(view.get_queryset())

    assert qs == [feedback]


def test_submission_feed_title(event):
    view = SubmissionFeed()

    title = view.title(event)

    assert str(event.name) in str(title)


def test_submission_feed_link(event):
    view = SubmissionFeed()

    link = view.link(event)

    assert link == event.orga_urls.submissions.full()


def test_submission_feed_items(event):
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)

    view = SubmissionFeed()

    items = list(view.items(event))

    assert set(items) == {sub1, sub2}


def test_submission_feed_item_title(event):
    submission = SubmissionFactory(event=event)

    view = SubmissionFeed()

    title = str(view.item_title(submission))

    assert submission.title in title
    assert str(event.name) in title


def test_submission_feed_item_link(event):
    submission = SubmissionFactory(event=event)

    view = SubmissionFeed()

    link = view.item_link(submission)

    assert link == submission.orga_urls.base.full()


def test_submission_feed_item_pubdate(event):
    submission = SubmissionFactory(event=event)

    view = SubmissionFeed()

    assert view.item_pubdate(submission) == submission.created


def test_submission_stats_show_submission_types_single(event):
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    assert view.show_submission_types() is False


def test_submission_stats_show_tracks_false_when_disabled():
    event = EventFactory(feature_flags={"use_tracks": False})
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    assert view.show_tracks is False


def test_submission_stats_show_tracks_true_with_multiple():
    event = EventFactory(feature_flags={"use_tracks": True})
    user = make_orga_user(event, can_change_submissions=True)
    TrackFactory(event=event)
    TrackFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    assert view.show_tracks is True


def test_submission_stats_submission_state_data(event):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    data = json.loads(view.submission_state_data)

    assert len(data) == 2
    labels = {item["label"] for item in data}
    assert len(labels) == 2


def test_submission_stats_submission_type_data(event):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    data = json.loads(view.submission_type_data())

    assert len(data) == 1
    assert data[0]["value"] == 1


def test_submission_stats_submission_track_data_empty_when_disabled():
    event = EventFactory(feature_flags={"use_tracks": False})
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    assert view.submission_track_data() == ""


def test_submission_stats_talk_state_data(event):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    data = json.loads(view.talk_state_data())

    assert len(data) == 1
    assert data[0]["value"] == 1


def test_submission_stats_talk_type_data(event):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    data = json.loads(view.talk_type_data())

    assert len(data) == 1
    assert data[0]["value"] == 1


def test_submission_stats_talk_track_data_empty_when_disabled():
    event = EventFactory(feature_flags={"use_tracks": False})
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    assert view.talk_track_data() == ""


def test_tag_view_get_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    tag = TagFactory(event=event)
    TagFactory()

    request = make_request(event, user=user)
    view = make_view(TagView, request)

    qs = list(view.get_queryset())

    assert len(qs) == 1
    assert qs[0] == tag


@pytest.mark.parametrize(
    ("action", "has_instance", "expected_substring"),
    (("create", False, "New tag"), ("list", False, "Tags")),
)
def test_tag_view_get_generic_title(event, action, has_instance, expected_substring):
    user = make_orga_user(event, can_change_submissions=True)
    tag = TagFactory(event=event) if has_instance else None

    request = make_request(event, user=user)
    view = make_view(TagView, request)
    view.action = action

    title = str(view.get_generic_title(tag))

    assert expected_substring in title


def test_tag_view_get_generic_title_with_instance(event):
    user = make_orga_user(event, can_change_submissions=True)
    tag = TagFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(TagView, request)
    view.action = "update"

    title = str(view.get_generic_title(tag))

    assert str(tag.tag) in title


def test_comment_list_get_form_kwargs(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(CommentList, request, code=submission.code)
    view.form_class = CommentList.form_class
    view.prefix = None
    view.initial = {}

    kwargs = view.get_form_kwargs()

    assert kwargs["submission"] == submission
    assert kwargs["user"] == user


def test_comment_list_comments_property(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    comment = SubmissionCommentFactory(submission=submission, user=user)

    request = make_request(event, user=user)
    view = make_view(CommentList, request, code=submission.code)

    comments = list(view.comments)

    assert comments == [comment]


def test_comment_delete_object(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    comment = SubmissionCommentFactory(submission=submission, user=user)

    request = make_request(event, user=user)
    view = make_view(CommentDelete, request, code=submission.code, pk=comment.pk)

    assert view.object == comment


def test_comment_delete_action_back_url(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    comment = SubmissionCommentFactory(submission=submission, user=user)

    request = make_request(event, user=user)
    view = make_view(CommentDelete, request, code=submission.code, pk=comment.pk)

    assert view.action_back_url == submission.orga_urls.comments


def test_comment_delete_action_object_name(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    comment = SubmissionCommentFactory(submission=submission, user=user)

    request = make_request(event, user=user)
    view = make_view(CommentDelete, request, code=submission.code, pk=comment.pk)

    name = str(view.action_object_name)

    assert submission.title in name


def test_submission_history_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    submission.log_action("pretalx.submission.update", person=user, orga=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionHistory, request, code=submission.code)

    qs = list(view.get_queryset())

    assert len(qs) == 1


def test_anonymise_next_unanonymised(event):
    """next_unanonymised returns an unanonymised submission from the event."""
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    other = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(Anonymise, request, code=submission.code)

    result = view.next_unanonymised

    assert result in (submission, other)


def test_apply_pending_bulk_submissions(event):
    user = make_orga_user(event, can_change_submissions=True)
    sub1 = SubmissionFactory(event=event, pending_state=SubmissionStates.ACCEPTED)
    SubmissionFactory(event=event)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(ApplyPendingBulk, request)

    subs = list(view.submissions)

    assert subs == [sub1]


def test_apply_pending_bulk_submission_count(event):
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionFactory(event=event, pending_state=SubmissionStates.ACCEPTED)
    SubmissionFactory(event=event, pending_state=SubmissionStates.REJECTED)

    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(ApplyPendingBulk, request)

    assert view.submission_count == 2


def test_reviewer_submission_filter_is_only_reviewer(event):
    reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)

    request = make_request(event, user=reviewer)
    view = make_view(SubmissionSpeakers, request, code="FAKE")
    # Access the cached property from the mixin
    view.request = request

    assert view.is_only_reviewer is True


def test_reviewer_submission_filter_is_only_reviewer_false_for_orga(event):
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionSpeakers, request, code="FAKE")

    assert view.is_only_reviewer is False


def test_submission_stats_submission_timeline_data_empty_with_no_submissions(event):
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    assert view.submission_timeline_data() == ""
    assert view.total_submission_timeline_data() == ""


def test_submission_stats_submission_timeline_data_empty_with_single_date(event):
    user = make_orga_user(event, can_change_submissions=True)
    sub = SubmissionFactory(event=event)
    sub.log_action("pretalx.submission.create")

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    assert view.raw_submission_timeline_data is None
    assert view.submission_timeline_data() == ""
    assert view.total_submission_timeline_data() == ""


def test_submission_stats_talk_timeline_data_empty(event):
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    assert view.talk_timeline_data() == ""


def test_submission_stats_timeline_annotations_with_cfp_deadline():
    event = EventFactory(cfp__deadline=tz_now() + dt.timedelta(days=7))
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    data = json.loads(view.timeline_annotations())

    assert len(data["deadlines"]) == 1


@pytest.mark.parametrize(("track_count", "expected"), ((1, False), (2, True)))
def test_submission_list_show_tracks_with_limit_tracks(track_count, expected):
    event = EventFactory(feature_flags={"use_tracks": True})
    user = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
    tracks = [TrackFactory(event=event) for _ in range(track_count)]
    team = user.teams.first()
    team.limit_tracks.add(*tracks)

    request = make_request(event, user=user)
    view = make_view(SubmissionList, request)

    assert view.show_tracks is expected


def test_submission_content_object_returns_not_found_for_invalid_code(event):
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user, path="/invalid/")
    view = make_view(SubmissionContent, request, code="ZZZZZ")

    result = view.object

    assert isinstance(result, Http404)


def test_submission_list_get_table_kwargs_with_multiple_types(event):
    """When multiple submission types exist, 'submission_type' is not excluded."""
    user = make_orga_user(event, can_change_submissions=True)
    SubmissionTypeFactory(event=event)
    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(SubmissionList, request)
    view.object_list = []

    kwargs = view.get_table_kwargs()

    assert "submission_type" not in kwargs["exclude"]
