# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.agenda.rules import (
    event_uses_feedback,
    is_agenda_submission_visible,
    is_agenda_visible,
    is_submission_visible_via_featured,
    is_submission_visible_via_schedule,
    is_viewable_speaker,
    is_widget_always_visible,
    is_widget_visible,
)
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import (
    EventFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_public", "show_schedule", "has_schedule", "expected"),
    (
        (True, True, True, True),
        (True, False, True, False),
        (False, True, True, False),
        (True, True, False, False),
        (False, False, False, False),
    ),
    ids=[
        "all_conditions_met",
        "schedule_hidden",
        "not_public",
        "public_with_schedule_flag_but_no_schedule",
        "nothing_set",
    ],
)
def test_is_agenda_visible(is_public, show_schedule, has_schedule, expected):
    event = EventFactory(
        is_public=is_public, feature_flags={"show_schedule": show_schedule}
    )
    if has_schedule:
        ScheduleFactory(version="v1", event=event)

    with scope(event=event):
        assert is_agenda_visible(None, event) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_visible", "expected"),
    ((True, True), (False, False)),
    ids=["visible_slot", "invisible_slot"],
)
def test_is_submission_visible_via_schedule_slot_visibility(
    is_visible, expected, published_talk_slot
):
    schedule = published_talk_slot.schedule
    event = schedule.event

    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=submission, schedule=schedule, is_visible=is_visible)

    with scope(event=event):
        assert is_submission_visible_via_schedule(None, submission) is expected


@pytest.mark.django_db
def test_is_submission_visible_via_schedule_no_slot(published_talk_slot):
    event = published_talk_slot.submission.event
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        assert is_submission_visible_via_schedule(None, submission) is False


def test_is_submission_visible_via_schedule_no_pk():
    submission = Submission()
    assert is_submission_visible_via_schedule(None, submission) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("show_featured", "is_featured", "expected"),
    (("always", True, True), ("always", False, False), ("never", True, False)),
    ids=["featured_and_visible", "not_featured", "feature_disabled"],
)
def test_is_submission_visible_via_featured(show_featured, is_featured, expected):
    event = EventFactory(feature_flags={"show_featured": show_featured})
    submission = SubmissionFactory(event=event, is_featured=is_featured)

    assert is_submission_visible_via_featured(None, submission) is expected


@pytest.mark.django_db
def test_is_agenda_submission_visible_via_schedule(published_talk_slot):
    schedule = published_talk_slot.schedule
    event = schedule.event

    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=submission, schedule=schedule, is_visible=True)

    with scope(event=event):
        assert is_agenda_submission_visible(None, submission) is True


@pytest.mark.django_db
def test_is_agenda_submission_visible_via_featured():
    event = EventFactory(
        feature_flags={"show_featured": "always", "show_schedule": False}
    )

    submission = SubmissionFactory(event=event, is_featured=True)

    assert is_agenda_submission_visible(None, submission) is True


@pytest.mark.django_db
def test_is_agenda_submission_visible_false():
    event = EventFactory(is_public=False, feature_flags={"show_featured": "never"})

    submission = SubmissionFactory(event=event, is_featured=False)

    assert is_agenda_submission_visible(None, submission) is False


@pytest.mark.django_db
def test_is_agenda_submission_visible_unwraps_slot():
    event = EventFactory(feature_flags={"show_featured": "always"})

    submission = SubmissionFactory(event=event, is_featured=True)
    slot = TalkSlotFactory(submission=submission)

    with scope(event=event):
        assert is_agenda_submission_visible(None, slot) is True


@pytest.mark.django_db
def test_is_viewable_speaker_true(published_talk_slot):
    event = published_talk_slot.submission.event
    speaker = published_talk_slot.submission.speakers.first()

    with scope(event=event):
        assert is_viewable_speaker(None, speaker) is True


@pytest.mark.django_db
def test_is_viewable_speaker_false(event):
    speaker = SpeakerFactory(event=event)

    with scope(event=event):
        assert is_viewable_speaker(None, speaker) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["widget_flag_on", "widget_flag_off"],
)
def test_is_widget_always_visible(flag_value, expected):
    event = EventFactory(feature_flags={"show_widget_if_not_public": flag_value})

    assert is_widget_always_visible(None, event) is expected


@pytest.mark.django_db
def test_is_widget_visible_via_agenda(published_talk_slot):
    event = published_talk_slot.submission.event

    with scope(event=event):
        assert is_widget_visible(None, event) is True


@pytest.mark.django_db
def test_is_widget_visible_via_flag():
    event = EventFactory(
        is_public=False, feature_flags={"show_widget_if_not_public": True}
    )

    assert is_widget_visible(None, event) is True


@pytest.mark.django_db
def test_is_widget_visible_false():
    event = EventFactory(is_public=False)

    with scope(event=event):
        assert is_widget_visible(None, event) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["feedback_enabled", "feedback_disabled"],
)
def test_event_uses_feedback(flag_value, expected):
    event = EventFactory(feature_flags={"use_feedback": flag_value})

    assert event_uses_feedback(None, event) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["feedback_enabled", "feedback_disabled"],
)
def test_event_uses_feedback_unwraps_event_attribute(flag_value, expected):
    event = EventFactory(feature_flags={"use_feedback": flag_value})
    submission = SubmissionFactory(event=event)

    assert event_uses_feedback(None, submission) is expected
