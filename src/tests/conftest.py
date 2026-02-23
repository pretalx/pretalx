import pytest
from django_scopes import scopes_disabled

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
    TrackFactory,
)


@pytest.fixture
def event():
    with scopes_disabled():
        return EventFactory()


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
