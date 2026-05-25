# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.person.domain.queries.profile import (
    annotate_speaker_submission_counts,
    annotate_user_submission_counts,
    filter_by_accepted_role,
    other_speaker_profiles,
    speakers_for_event,
    submitters_for_event,
    visible_talk_slots,
)
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    UserFactory,
)
from tests.utils import make_published_schedule

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_other_speaker_profiles_returns_user_profiles_on_other_events():
    user = UserFactory()
    current_event = EventFactory()
    other_event = EventFactory()
    current = SpeakerFactory(user=user, event=current_event, biography="here")
    other = SpeakerFactory(user=user, event=other_event, biography="there")

    result = list(other_speaker_profiles(current))

    assert result == [other]
    assert current not in result


def test_other_speaker_profiles_excludes_other_users():
    user = UserFactory()
    other_user = UserFactory()
    event = EventFactory()
    profile = SpeakerFactory(user=user, event=event)
    SpeakerFactory(user=other_user, event=event)

    assert list(other_speaker_profiles(profile)) == []


def test_annotate_speaker_submission_counts_counts_per_event():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(speaker)
    rejected = SubmissionFactory(event=event, state="rejected")
    rejected.speakers.add(speaker)

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(pk=speaker.pk), event=event
    )
    result = qs.get()

    assert result.submission_count == 2
    assert result.accepted_submission_count == 1


def test_annotate_user_submission_counts_counts_per_events():
    event = EventFactory()
    user = UserFactory()
    profile = SpeakerFactory(user=user, event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(profile)

    qs = annotate_user_submission_counts(
        User.objects.filter(pk=user.pk), events=[event]
    )
    result = qs.get()

    assert result.submission_count == 1
    assert result.accepted_submission_count == 1


def test_visible_talk_slots_no_schedule_returns_empty(event):
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        assert list(visible_talk_slots(speaker)) == []


def test_visible_talk_slots_with_schedule(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    schedule = ScheduleFactory(event=event)
    slot = TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)

    with scope(event=event):
        result = list(visible_talk_slots(speaker, schedule=schedule))

    assert result == [slot]


@pytest.mark.parametrize(
    ("attendee_signup", "expect_annotation"),
    ((True, True), (False, False)),
    ids=("feature_on", "feature_off"),
)
def test_visible_talk_slots_annotates_signup_status_per_feature_flag(
    attendee_signup, expect_annotation
):
    event = EventFactory(feature_flags={"attendee_signup": attendee_signup})
    speaker = SpeakerFactory(event=event)
    schedule = ScheduleFactory(event=event)

    with scope(event=event):
        queryset = visible_talk_slots(speaker, schedule=schedule)

    assert (
        "_annotated_signup_status" in queryset.query.annotations
    ) is expect_annotation


@pytest.mark.parametrize(
    ("role", "expect_with_accepted", "expect_without_accepted"),
    (
        ("speaker", True, False),
        ("submitter", False, True),
        ("all", True, True),
        ("", True, True),
    ),
)
def test_filter_by_accepted_role(role, expect_with_accepted, expect_without_accepted):
    event = EventFactory()
    with_accepted = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(with_accepted)
    without_accepted = SpeakerFactory(event=event)

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(event=event), event=event
    )
    filtered = set(filter_by_accepted_role(qs, role))

    expected = set()
    if expect_with_accepted:
        expected.add(with_accepted)
    if expect_without_accepted:
        expected.add(without_accepted)
    assert filtered == expected


def test_speakers_for_event_returns_speakers_of_scheduled_talks():
    event = EventFactory()
    [scheduled] = make_published_schedule(event, item_count=1)
    with scope(event=event):
        scheduled_speaker = scheduled.speakers.get()
        # A speaker with a confirmed but unscheduled submission must not show up.
        unscheduled_speaker = SpeakerFactory(event=event)
        unscheduled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        unscheduled.speakers.add(unscheduled_speaker)

    with scope(event=event):
        assert list(speakers_for_event(event)) == [scheduled_speaker]


def test_speakers_for_event_no_released_schedule_returns_empty():
    event = EventFactory()
    with scope(event=event):
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
        TalkSlotFactory(submission=sub)

    with scope(event=event):
        assert list(speakers_for_event(event)) == []


def test_speakers_for_event_deduplicates_speakers_on_multiple_talks():
    event = EventFactory()
    [first, second] = make_published_schedule(event, item_count=2)
    with scope(event=event):
        shared = first.speakers.get()
        second.speakers.add(shared)

    with scope(event=event):
        result = list(speakers_for_event(event))

    assert result.count(shared) == 1


def test_submitters_for_event_includes_any_non_draft_state():
    """Withdrawn / rejected / cancelled submitters all count — only DRAFT is
    excluded by the SubmissionManager."""
    event = EventFactory()
    states = (
        SubmissionStates.SUBMITTED,
        SubmissionStates.WITHDRAWN,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.CONFIRMED,
    )
    expected_speakers = set()
    with scope(event=event):
        for state in states:
            speaker = SpeakerFactory(event=event)
            sub = SubmissionFactory(event=event, state=state)
            sub.speakers.add(speaker)
            expected_speakers.add(speaker)

    with scope(event=event):
        result = set(submitters_for_event(event))

    assert result == expected_speakers


def test_submitters_for_event_excludes_draft_submitters():
    """A speaker whose only submission is a draft must not appear, since
    drafts are filtered out by the default Submission manager."""
    event = EventFactory()
    with scope(event=event):
        kept = SpeakerFactory(event=event)
        kept_sub = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        kept_sub.speakers.add(kept)

        draft_only = SpeakerFactory(event=event)
        draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        draft.speakers.add(draft_only)

    with scope(event=event):
        result = list(submitters_for_event(event))

    assert result == [kept]


def test_submitters_for_event_empty_event_returns_empty():
    event = EventFactory()
    with scope(event=event):
        # A speaker without a submission must not appear.
        SpeakerFactory(event=event)

    with scope(event=event):
        assert list(submitters_for_event(event)) == []
