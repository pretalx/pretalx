import pytest
from django_scopes import scope, scopes_disabled

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
from tests.factories import SpeakerFactory, SubmissionFactory, TalkSlotFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_public", "show_schedule", "expected"),
    ((True, True, True), (True, False, False), (False, True, False)),
    ids=["all_conditions_met", "schedule_hidden", "not_public"],
)
def test_is_agenda_visible(is_public, show_schedule, expected, published_schedule):
    event = published_schedule.event
    event.is_public = is_public
    event.feature_flags["show_schedule"] = show_schedule
    event.save()

    with scope(event=event):
        assert is_agenda_visible(None, event) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_public", "show_schedule"),
    ((True, True), (False, False)),
    ids=["public_with_schedule_flag", "nothing_set"],
)
def test_is_agenda_visible_no_schedule(is_public, show_schedule, event):
    """Without a published schedule, agenda is never visible regardless of flags."""
    event.is_public = is_public
    event.feature_flags["show_schedule"] = show_schedule
    event.save()

    with scope(event=event):
        assert is_agenda_visible(None, event) is False


@pytest.mark.django_db
def test_is_agenda_visible_with_none_event():
    """is_agenda_visible handles event.event returning None gracefully."""

    class FakeObj:
        event = None

    assert is_agenda_visible(None, FakeObj()) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_visible", "expected"),
    ((True, True), (False, False)),
    ids=["visible_slot", "invisible_slot"],
)
def test_is_submission_visible_via_schedule_slot_visibility(
    is_visible, expected, published_schedule
):
    """Submission visibility depends on whether its slot is visible."""
    event = published_schedule.event
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()

    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scopes_disabled():
        TalkSlotFactory(
            submission=submission, schedule=published_schedule, is_visible=is_visible
        )

    with scope(event=event):
        assert is_submission_visible_via_schedule(None, submission) is expected


@pytest.mark.django_db
def test_is_submission_visible_via_schedule_no_slot(published_schedule):
    """Submission without a slot in the current schedule is not visible."""
    event = published_schedule.event
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()

    submission = SubmissionFactory(event=event)

    with scope(event=event):
        assert is_submission_visible_via_schedule(None, submission) is False


def test_is_submission_visible_via_schedule_none_submission():
    assert is_submission_visible_via_schedule(None, None) is False


def test_is_submission_visible_via_schedule_no_pk():
    """Unsaved submission (no pk) is never visible via schedule."""
    submission = Submission()
    assert is_submission_visible_via_schedule(None, submission) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("show_featured", "is_featured", "expected"),
    (("always", True, True), ("always", False, False), ("never", True, False)),
    ids=["featured_and_visible", "not_featured", "feature_disabled"],
)
def test_is_submission_visible_via_featured(
    show_featured, is_featured, expected, event
):
    event.is_public = True
    event.feature_flags["show_featured"] = show_featured
    event.save()
    submission = SubmissionFactory(event=event, is_featured=is_featured)

    assert is_submission_visible_via_featured(None, submission) is expected


def test_is_submission_visible_via_featured_none_submission():
    assert is_submission_visible_via_featured(None, None) is False


@pytest.mark.django_db
def test_is_agenda_submission_visible_via_schedule(published_schedule):
    """Submission visible through schedule path."""
    event = published_schedule.event
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()

    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scopes_disabled():
        TalkSlotFactory(
            submission=submission, schedule=published_schedule, is_visible=True
        )

    with scope(event=event):
        assert is_agenda_submission_visible(None, submission) is True


@pytest.mark.django_db
def test_is_agenda_submission_visible_via_featured(event):
    """Submission visible through featured path when schedule is not visible."""
    event.is_public = True
    event.feature_flags["show_featured"] = "always"
    event.feature_flags["show_schedule"] = False
    event.save()

    submission = SubmissionFactory(event=event, is_featured=True)

    assert is_agenda_submission_visible(None, submission) is True


@pytest.mark.django_db
def test_is_agenda_submission_visible_false(event):
    """Submission is not visible when neither schedule nor featured conditions are met."""
    event.is_public = False
    event.feature_flags["show_featured"] = "never"
    event.save()

    submission = SubmissionFactory(event=event, is_featured=False)

    assert is_agenda_submission_visible(None, submission) is False


def test_is_agenda_submission_visible_none():
    assert is_agenda_submission_visible(None, None) is False


@pytest.mark.django_db
def test_is_agenda_submission_visible_unwraps_slot(event):
    """is_agenda_submission_visible follows .submission on slot-like objects."""
    event.is_public = True
    event.feature_flags["show_featured"] = "always"
    event.save()

    submission = SubmissionFactory(event=event, is_featured=True)
    slot = TalkSlotFactory(submission=submission)

    with scope(event=event):
        assert is_agenda_submission_visible(None, slot) is True


@pytest.mark.django_db
def test_is_viewable_speaker_true(published_talk_slot):
    """Speaker with a slot in the released schedule is viewable."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        speaker = published_talk_slot.submission.speakers.first()

    with scope(event=event):
        assert is_viewable_speaker(None, speaker) is True


@pytest.mark.django_db
def test_is_viewable_speaker_false(event):
    """Speaker without a slot in the released schedule is not viewable."""
    speaker = SpeakerFactory(event=event)

    with scope(event=event):
        assert is_viewable_speaker(None, speaker) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["widget_flag_on", "widget_flag_off"],
)
def test_is_widget_always_visible(flag_value, expected, event):
    event.feature_flags["show_widget_if_not_public"] = flag_value
    event.save()

    assert is_widget_always_visible(None, event) is expected


@pytest.mark.django_db
def test_is_widget_visible_via_agenda(published_schedule):
    """Widget is visible when the agenda itself is visible."""
    event = published_schedule.event
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.feature_flags["show_widget_if_not_public"] = False
    event.save()

    with scope(event=event):
        assert is_widget_visible(None, event) is True


@pytest.mark.django_db
def test_is_widget_visible_via_flag(event):
    """Widget is visible even without agenda when flag is set."""
    event.is_public = False
    event.feature_flags["show_widget_if_not_public"] = True
    event.save()

    assert is_widget_visible(None, event) is True


@pytest.mark.django_db
def test_is_widget_visible_false(event):
    """Widget is not visible when neither agenda nor flag are active."""
    event.is_public = False
    event.feature_flags["show_widget_if_not_public"] = False
    event.save()

    with scope(event=event):
        assert is_widget_visible(None, event) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flag_value", "expected"),
    ((True, True), (False, False)),
    ids=["feedback_enabled", "feedback_disabled"],
)
def test_event_uses_feedback(flag_value, expected, event):
    event.feature_flags["use_feedback"] = flag_value
    event.save()

    assert event_uses_feedback(None, event) is expected


def test_event_uses_feedback_none():
    """event_uses_feedback returns falsy when event resolves to None."""

    class FakeObj:
        event = None

    assert not event_uses_feedback(None, FakeObj())


@pytest.mark.django_db
def test_event_uses_feedback_unwraps_event_attribute(event):
    """event_uses_feedback follows .event on objects that aren't events."""
    event.feature_flags["use_feedback"] = True
    event.save()
    submission = SubmissionFactory(event=event)

    assert event_uses_feedback(None, submission) is True
