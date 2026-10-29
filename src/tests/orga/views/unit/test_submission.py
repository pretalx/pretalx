# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json
from collections import Counter

import pytest
from django.http import Http404
from django.urls import ResolverMatch
from django.utils.timezone import now as tz_now

from pretalx.orga.views.submission import (
    AllFeedbacksList,
    ApplyPendingBulk,
    CommentDelete,
    CommentList,
    FeedbackList,
    SubmissionContent,
    SubmissionDelete,
    SubmissionHistory,
    SubmissionList,
    SubmissionSpeakers,
    SubmissionStateChange,
    SubmissionStats,
    TagView,
    serialize_pie_chart_data,
)
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.models import QuestionTarget, QuestionVariant, SubmissionStates
from tests.factories import (
    EventFactory,
    FeedbackFactory,
    QuestionFactory,
    ResourceFactory,
    SpeakerFactory,
    SubmissionCommentFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
)
from tests.utils import make_orga_user, make_request, make_view, query_dict

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _state_change_view(event, user, submission, url_name, path="/"):
    request = make_request(
        event,
        user=user,
        path=path,
        resolver_match=ResolverMatch(lambda: None, (), {}, url_name=url_name),
    )
    return make_view(SubmissionStateChange, request, code=submission.code)


def test_submission_view_mixin_properties(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    request = make_request(event, user=user)
    view = make_view(SubmissionStateChange, request, code=submission.code)

    assert list(view._get_submission_queryset()) == [submission]
    assert list(view._get_lightweight_submission_queryset()) == [submission]
    assert view.object == submission
    assert view.has_anonymised_review is False
    assert view.is_publicly_visible is False

    phase = event.review_phases.first()
    phase.can_see_speaker_names = False
    phase.save()

    anonymised = make_view(SubmissionStateChange, request, code=submission.code)
    assert anonymised.has_anonymised_review is True


def test_submission_state_change_action_target_and_success_url(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    next_url = event.orga_urls.submissions

    accept = _state_change_view(event, user, submission, "submissions.accept")
    reject = _state_change_view(event, user, submission, "submissions.reject")
    with_next = _state_change_view(
        event, user, submission, "submissions.accept", path=f"/?next={next_url}"
    )

    assert accept._action == "accept"
    assert accept.get_success_url() == event.orga_urls.submissions
    assert reject._target == SubmissionStates.REJECTED
    assert reject.target() == SubmissionStates.REJECTED
    assert with_next.get_success_url() == next_url


def test_submission_delete_action_text_mentions_schedule_only_with_slots(event):
    user = make_orga_user(event, can_change_submissions=True)
    unscheduled = SubmissionFactory(event=event)
    scheduled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    scheduled.speakers.add(SpeakerFactory(event=event))
    slot = TalkSlotFactory(submission=scheduled, is_visible=True)
    freeze_schedule(slot.schedule, "v1", notify_speakers=False)
    request = make_request(event, user=user)

    unscheduled_text = str(
        make_view(SubmissionDelete, request, code=unscheduled.code).action_text
    )
    scheduled_text = str(
        make_view(SubmissionDelete, request, code=scheduled.code).action_text
    )

    assert "schedule" not in unscheduled_text.lower()
    assert "schedule" in scheduled_text.lower()


def test_submission_view_mixin_context_without_comment_feature(event):
    event.feature_flags["use_submission_comments"] = False
    event.save()
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    SubmissionCommentFactory(submission=submission)

    request = make_request(event, user=user)
    view = make_view(SubmissionDelete, request, code=submission.code)
    ctx = view.get_context_data()

    assert ctx["submission_comment_count"] is None
    assert ctx["has_submission_feedback"] is False


def test_submission_speakers_speakers_property(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SubmissionSpeakers, request, code=submission.code)

    assert len(view.speakers) == 1
    assert view.speakers[0]["speaker"] == speaker
    assert view.speakers[0]["other_submissions"] == []


def test_submission_speakers_other_submissions_hidden_outside_reviewer_tracks(event):
    in_track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    team.limit_tracks.add(in_track)
    user = make_orga_user(teams=[team])
    submission = SubmissionFactory(event=event, track=in_track)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    visible = SubmissionFactory(event=event, track=in_track)
    visible.speakers.add(speaker)
    hidden = SubmissionFactory(event=event, track=other_track)
    hidden.speakers.add(speaker)

    request = make_request(event, user=user)
    view = make_view(SubmissionSpeakers, request, code=submission.code)

    assert view.speakers[0]["other_submissions"] == [visible]


def test_submission_content_object_and_can_edit(event):
    user = make_orga_user(event, can_change_submissions=True)
    reviewer = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
    submission = SubmissionFactory(event=event)
    request = make_request(event, user=user)
    new_request = make_request(
        event, user=user, path="/orga/event/test/submissions/new/"
    )
    invalid_request = make_request(event, user=user, path="/invalid/")

    assert make_view(SubmissionContent, new_request).object is None
    assert isinstance(
        make_view(SubmissionContent, invalid_request, code="ZZZZZ").object, Http404
    )
    view = make_view(SubmissionContent, request, code=submission.code)
    assert view.object == submission
    assert view.can_edit is True
    reviewer_view = make_view(
        SubmissionContent, make_request(event, user=reviewer), code=submission.code
    )
    assert reviewer_view.can_edit is False


def test_submission_list_properties(event):
    user = make_orga_user(event, can_change_submissions=True)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    confirmed = SubmissionFactory(
        event=event,
        state=SubmissionStates.CONFIRMED,
        pending_state=SubmissionStates.ACCEPTED,
    )
    SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
    SubmissionFactory(event=event, state=SubmissionStates.CANCELED)
    SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)
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
    request.GET = query_dict()
    view = make_view(SubmissionList, request)
    view.object_list = []

    assert view.pending_changes == 1
    assert set(view.get_queryset()) == {submitted, confirmed}
    assert view.show_submission_types is False
    assert list(view.short_questions) == [short_q]
    assert "submission_type" in view.get_table_kwargs()["exclude"]

    SubmissionTypeFactory(event=event)
    with_types = make_view(SubmissionList, request)
    with_types.object_list = []

    assert with_types.show_submission_types is True
    assert "submission_type" not in with_types.get_table_kwargs()["exclude"]


def test_submission_list_annotates_resource_count(event):
    user = make_orga_user(event, can_change_submissions=True)
    with_resources = SubmissionFactory(event=event)
    with_resources.speakers.add(
        SpeakerFactory(event=event), SpeakerFactory(event=event)
    )
    ResourceFactory(submission=with_resources)
    ResourceFactory(submission=with_resources)
    mixed_resources = SubmissionFactory(event=event)
    ResourceFactory(submission=mixed_resources)
    ResourceFactory(submission=mixed_resources, link="", resource="None")
    with_dead_resources = SubmissionFactory(event=event)
    ResourceFactory(submission=with_dead_resources, link="")
    ResourceFactory(submission=with_dead_resources, link="", resource="None")
    without_resources = SubmissionFactory(event=event)

    request = make_request(event, user=user)
    view = make_view(SubmissionList, request)

    counts = {
        submission.code: submission.resource_count for submission in view.get_queryset()
    }

    assert counts == {
        with_resources.code: 2,
        mixed_resources.code: 1,
        with_dead_resources.code: 0,
        without_resources.code: 0,
    }


def test_submission_list_annotates_full_speaker_count_when_searching_speakers(event):
    user = make_orga_user(event, can_change_submissions=True)
    matched_by_speaker = SubmissionFactory(event=event)
    matched_by_speaker.speakers.add(
        SpeakerFactory(event=event, name="Danielle Dare"),
        SpeakerFactory(event=event, name="Sam Second"),
        SpeakerFactory(event=event, name="Tam Third"),
    )
    matched_by_title = SubmissionFactory(event=event, title="A talk about Danielle")
    without_match = SubmissionFactory(event=event)
    without_match.speakers.add(SpeakerFactory(event=event, name="Nobody Relevant"))

    request = make_request(event, user=user)
    request.GET = query_dict({"q": "Danielle"})
    view = make_view(SubmissionList, request)

    counts = {
        submission.code: submission.speaker_count for submission in view.get_queryset()
    }

    assert counts == {matched_by_speaker.code: 3, matched_by_title.code: 0}


@pytest.mark.parametrize(
    ("use_tracks", "track_count", "expected"),
    ((False, 0, False), (True, 0, False), (True, 1, True)),
    ids=("disabled", "no-tracks", "with-tracks"),
)
def test_submission_list_and_stats_show_tracks(use_tracks, track_count, expected):
    event = EventFactory(feature_flags={"use_tracks": use_tracks})
    user = make_orga_user(event, can_change_submissions=True)
    for _ in range(track_count):
        TrackFactory(event=event)
    request = make_request(event, user=user)
    request.GET = query_dict()

    assert make_view(SubmissionList, request).show_tracks is expected
    assert make_view(SubmissionStats, request).show_tracks is expected


@pytest.mark.parametrize("track_count", (1, 2))
def test_submission_list_show_tracks_with_limit_tracks(track_count):
    event = EventFactory(feature_flags={"use_tracks": True})
    user = make_orga_user(event, can_change_submissions=False, is_reviewer=True)
    tracks = [TrackFactory(event=event) for _ in range(track_count)]
    team = user.teams.first()
    team.limit_tracks.add(*tracks)

    request = make_request(event, user=user)
    view = make_view(SubmissionList, request)

    assert view.show_tracks is True


def test_feedback_list_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    feedback = FeedbackFactory(talk=submission)
    FeedbackFactory(talk=SubmissionFactory())
    request = make_request(event, user=user)

    assert list(
        make_view(FeedbackList, request, code=submission.code).get_queryset()
    ) == [feedback]
    assert list(make_view(AllFeedbacksList, request).get_queryset()) == [feedback]


def test_all_feedbacks_list_queryset_track_limited_reviewer(event):
    in_track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_event_settings=True,
    )
    team.limit_tracks.add(in_track)
    reviewer = make_orga_user(teams=[team])
    visible_sub = SubmissionFactory(event=event, track=in_track)
    hidden_sub = SubmissionFactory(event=event, track=other_track)
    visible_feedback = FeedbackFactory(talk=visible_sub)
    FeedbackFactory(talk=hidden_sub)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    request = make_request(event, user=reviewer)
    view = make_view(AllFeedbacksList, request)

    assert list(view.get_queryset()) == [visible_feedback]


def test_submission_stats_data_without_tracks(event):
    user = make_orga_user(event, can_change_submissions=True)
    sub_type = SubmissionTypeFactory(event=event, name="Keynote", default_duration=30)
    SubmissionFactory(event=event, submission_type=sub_type, state="submitted")
    SubmissionFactory(event=event, submission_type=sub_type, state="accepted")
    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    assert view.show_submission_types() is True
    assert view.show_tracks is False
    assert json.loads(view.submission_state_data) == [
        {"label": "accepted", "value": 1},
        {"label": "submitted", "value": 1},
    ]
    assert json.loads(view.submission_type_data()) == [{"label": "Keynote", "value": 2}]
    assert view.submission_track_data() == ""
    assert json.loads(view.talk_state_data()) == [{"label": "accepted", "value": 1}]
    assert json.loads(view.talk_type_data()) == [{"label": "Keynote", "value": 1}]
    assert view.talk_track_data() == ""
    assert view.talk_timeline_data() == ""


def test_submission_stats_scoped_to_track_limited_reviewer():
    event = EventFactory(feature_flags={"use_tracks": True})
    in_track = TrackFactory(event=event, name="In Track")
    other_track = TrackFactory(event=event, name="Secret Track")
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_event_settings=True,
    )
    team.limit_tracks.add(in_track)
    reviewer = make_orga_user(teams=[team])
    SubmissionFactory(event=event, track=in_track, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, track=other_track, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, track=other_track, state=SubmissionStates.ACCEPTED)
    event.review_phases.filter(is_active=True).update(proposal_visibility="all")

    request = make_request(event, user=reviewer)
    view = make_view(SubmissionStats, request)

    track_data = json.loads(view.submission_track_data())
    state_data = json.loads(view.submission_state_data)

    assert track_data == [{"label": "In Track", "value": 1}]
    assert state_data == [{"label": "submitted", "value": 1}]


@pytest.mark.parametrize(
    ("counts", "expected"),
    (
        ({}, ""),
        ({"only zeroes": 0}, ""),
        ({"zero": 0, "two": 2}, '[{"label": "two", "value": 2}]'),
        (
            {"beta": 2, "alpha": 1},
            '[{"label": "alpha", "value": 1}, {"label": "beta", "value": 2}]',
        ),
    ),
)
def test_serialize_pie_chart_data(counts, expected):
    assert serialize_pie_chart_data(Counter(counts)) == expected


def test_submission_stats_data_empty_without_matching_submissions():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    empty = make_view(SubmissionStats, request)

    assert empty.show_submission_types() is False
    assert empty.submission_state_data == ""
    assert empty.submission_type_data() == ""
    assert empty.submission_track_data() == ""
    assert empty.submission_timeline_data() == ""
    assert empty.total_submission_timeline_data() == ""

    sub = SubmissionFactory(event=event, track=track, state=SubmissionStates.SUBMITTED)
    sub.log_action("pretalx.submission.create")
    unaccepted = make_view(SubmissionStats, request)

    assert unaccepted.talk_state_data() == ""
    assert unaccepted.talk_type_data() == ""
    assert unaccepted.talk_track_data() == ""
    assert unaccepted.raw_submission_timeline_data is None
    assert unaccepted.submission_timeline_data() == ""
    assert unaccepted.total_submission_timeline_data() == ""


def test_tag_view_get_queryset_counts_non_draft_submissions(event):
    user = make_orga_user(event, can_change_submissions=True)
    tag = TagFactory(event=event)
    TagFactory()
    published = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    published.tags.add(tag)
    draft.tags.add(tag)

    request = make_request(event, user=user)
    view = make_view(TagView, request)

    qs = list(view.get_queryset())

    assert qs == [tag]
    assert qs[0].submission_count == 1


def test_comment_list_and_delete_resolve_comment(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    comment = SubmissionCommentFactory(submission=submission, user=user)
    request = make_request(event, user=user)

    assert list(make_view(CommentList, request, code=submission.code).comments) == [
        comment
    ]
    assert (
        make_view(CommentDelete, request, code=submission.code, pk=comment.pk).object
        == comment
    )


def test_submission_history_queryset(event):
    user = make_orga_user(event, can_change_submissions=True)
    submission = SubmissionFactory(event=event)
    submission.log_action("pretalx.submission.update", person=user, orga=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionHistory, request, code=submission.code)

    qs = list(view.get_queryset())

    assert len(qs) == 1


@pytest.mark.parametrize(
    "state",
    (SubmissionStates.SUBMITTED, SubmissionStates.REJECTED),
    ids=("live_state", "dead_state"),
)
def test_apply_pending_bulk_submissions(event, state):
    user = make_orga_user(event, can_change_submissions=True)
    sub1 = SubmissionFactory(
        event=event, state=state, pending_state=SubmissionStates.ACCEPTED
    )
    SubmissionFactory(event=event)

    request = make_request(event, user=user)
    request.GET = query_dict()
    view = make_view(ApplyPendingBulk, request)

    assert list(view.submissions) == [sub1]
    assert view.submission_count == 1


@pytest.mark.parametrize(
    ("user_kwargs", "expected"),
    (
        ({"can_change_submissions": False, "is_reviewer": True}, True),
        (
            {
                "can_change_submissions": False,
                "is_reviewer": True,
                "can_change_event_settings": True,
            },
            True,
        ),
        ({"can_change_submissions": True}, False),
    ),
    ids=["reviewer_only", "reviewer_extra_permission", "orga"],
)
def test_reviewer_submission_filter_is_only_reviewer(event, user_kwargs, expected):
    user = make_orga_user(event, **user_kwargs)

    request = make_request(event, user=user)
    view = make_view(SubmissionSpeakers, request, code="FAKE")

    assert view.is_only_reviewer is expected


def test_submission_stats_timeline_annotations_with_cfp_deadline():
    event = EventFactory(cfp__deadline=tz_now() + dt.timedelta(days=7))
    user = make_orga_user(event, can_change_submissions=True)

    request = make_request(event, user=user)
    view = make_view(SubmissionStats, request)

    data = json.loads(view.timeline_annotations())

    assert len(data["deadlines"]) == 1
