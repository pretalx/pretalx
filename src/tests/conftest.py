import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_scopes import scopes_disabled

from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AnswerFactory,
    AvailabilityFactory,
    EventFactory,
    FeedbackFactory,
    QuestionFactory,
    ResourceFactory,
    ReviewFactory,
    RoomFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    TagFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)


@pytest.fixture
def event():
    with scopes_disabled():
        return EventFactory()


@pytest.fixture
def user_with_event():
    """A user with a team membership granting organiser access to an event,
    returning (user, event)."""
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True)
    user = UserFactory()
    team.members.add(user)
    return user, event


@pytest.fixture
def populated_event():
    """An event with related data across all major models: submissions,
    speakers, rooms, slots, questions, answers, reviews, feedback,
    resources, tracks, tags, and speaker information.

    Use this when you need a fully-loaded event, e.g. for shred or
    copy tests that exercise cascading operations.
    """
    with scopes_disabled():
        event = EventFactory()

        TrackFactory(event=event)
        room = RoomFactory(event=event)
        AvailabilityFactory(event=event, room=room)

        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)

        question = QuestionFactory(event=event)
        AnswerFactory(question=question, submission=submission)

        ReviewFactory(submission=submission)
        FeedbackFactory(talk=submission)
        ResourceFactory(submission=submission)

        TagFactory(event=event)
        SpeakerInformationFactory(event=event)

        TalkSlotFactory(submission=submission)

    return event


@pytest.fixture
def register_signal_handler(settings):
    """Connect a temporary handler to an EventPluginSignal for the duration
    of a single test.

    Adds ``"tests._test_plugin"`` to ``CORE_MODULES`` and sets each
    handler's ``__module__`` to match, so handlers pass
    ``EventPluginSignal._is_active`` without needing a real plugin.
    The ``settings`` fixture auto-restores ``CORE_MODULES`` after the test;
    handlers are disconnected explicitly on teardown.

    Usage::

        def test_pre_send_hook(register_signal_handler, event):
            received = []

            def handler(signal, sender, **kwargs):
                received.append(kwargs["mail"])

            register_signal_handler(some_event_plugin_signal, handler)
            # … trigger the signal …
            assert len(received) == 1
    """
    registered = []
    settings.CORE_MODULES = [*settings.CORE_MODULES, "tests._test_plugin"]

    def _register(signal, handler):
        handler.__module__ = "tests._test_plugin"
        signal.connect(handler)
        registered.append((signal, handler))

    yield _register

    for signal, handler in registered:
        signal.disconnect(handler)


@pytest.fixture
def talk_slot(event):
    """An event with a WIP schedule containing one visible, confirmed talk slot."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        return TalkSlotFactory(submission=submission, is_visible=True)


@pytest.fixture
def published_talk_slot(talk_slot):
    """A talk slot in a released schedule — event.current_schedule is set,
    so event.talks and event.speakers are populated."""
    with scopes_disabled():
        talk_slot.schedule.freeze("v1", notify_speakers=False)
    return talk_slot


@pytest.fixture
def schedule_with_talk(talk_slot):
    return talk_slot.schedule


@pytest.fixture
def make_image():
    """Returns a factory function that creates a minimal valid 1x1 PNG as a
    SimpleUploadedFile. Useful for any test that needs a real image file
    (e.g. avatar uploads, submission images)."""

    def _make(name="test.png"):
        data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01"
            b"\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return SimpleUploadedFile(name, data, content_type="image/png")

    return _make
