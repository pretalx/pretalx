import pytest
from django.utils.timezone import now
from django_scopes import scope
from i18nfield.strings import LazyI18nString

from pretalx.mail.context import (
    base_placeholders,
    get_all_reviews,
    get_available_placeholders,
    get_invalid_placeholders,
    get_mail_context,
    get_used_placeholders,
    placeholder_aliases,
)
from pretalx.mail.placeholders import SimpleFunctionalMailTextPlaceholder
from tests.factories import (
    ReviewFactory,
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("", set()),
        ("No placeholders here", set()),
        ("{name}", {"name"}),
        ("{name} and {email}", {"name", "email"}),
        ("{name} and {name}", {"name"}),
        ("Hello {event_name}, welcome to {event_slug}!", {"event_name", "event_slug"}),
    ),
)
def test_get_used_placeholders_from_string(text, expected):
    """Extracts placeholder names from Python format strings."""
    assert get_used_placeholders(text) == expected


def test_get_used_placeholders_from_none():
    """None input returns an empty set."""
    assert get_used_placeholders(None) == set()


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            {"en": "Hello {name}", "de": "Hallo {name} bei {event_name}"},
            {"name", "event_name"},
        ),
        ({"en": "Hello {name}", "de": ""}, {"name"}),
    ),
)
def test_get_used_placeholders_from_dict(text, expected):
    """A dict (as used for i18n LazyI18nString data) unions placeholders
    across all language values; empty values are handled gracefully."""
    assert get_used_placeholders(text) == expected


def test_get_used_placeholders_from_lazy_i18n_string():
    """LazyI18nString objects have their .data parsed recursively."""
    text = LazyI18nString({"en": "{code}", "de": "{code} - {event_name}"})
    assert get_used_placeholders(text) == {"code", "event_name"}


def test_get_used_placeholders_unsupported_type_returns_empty():
    """Unsupported types (e.g. int, list) return an empty set."""
    assert get_used_placeholders(42) == set()
    assert get_used_placeholders(["{name}"]) == set()


@pytest.mark.parametrize(
    ("text", "valid", "expected"),
    (
        ("Hello {name}", ["name", "email"], set()),
        ("Hello {name} and {bogus}", ["name"], {"bogus"}),
        ("No placeholders", ["name"], set()),
        ("{a} {b} {c}", ["a", "c"], {"b"}),
    ),
)
def test_get_invalid_placeholders(text, valid, expected):
    """Returns the set of placeholders in text that are not in the valid list."""
    assert get_invalid_placeholders(text, valid) == expected


def test_placeholder_aliases_first_is_visible_rest_hidden():
    """Only the first alias is visible; the rest are hidden aliases."""
    result = placeholder_aliases(
        ["primary", "alias1", "alias2"], ["event"], lambda event: event, "sample"
    )
    assert result[0].is_visible is True
    assert result[1].is_visible is False
    assert result[2].is_visible is False


def test_placeholder_aliases_identifiers_match():
    """Each placeholder has the correct identifier."""
    identifiers = ["event_name", "event"]
    result = placeholder_aliases(
        identifiers,
        ["event"],
        lambda event: event,
        "sample",
        explanation="The event name",
    )
    assert [p.identifier for p in result] == identifiers


def test_placeholder_aliases_render_uses_same_func():
    """All aliases render using the same underlying function."""
    result = placeholder_aliases(
        ["a", "b"], ["event"], lambda event: f"rendered-{event}", "sample"
    )
    context = {"event": "test"}
    assert result[0].render(context) == "rendered-test"
    assert result[1].render(context) == "rendered-test"


@pytest.mark.django_db
def test_get_all_reviews_with_texts(event):
    """Reviews with text are joined by a separator."""
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        ReviewFactory(submission=submission, text="Great talk")
        ReviewFactory(submission=submission, text="Needs work")

        result = get_all_reviews(submission)

    assert result == "Great talk\n\n--------------\n\nNeeds work"


@pytest.mark.django_db
def test_get_all_reviews_no_reviews(event):
    """Returns empty string when submission has no reviews."""
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        assert get_all_reviews(submission) == ""


@pytest.mark.parametrize("unusable_text", (None, "   "))
@pytest.mark.django_db
def test_get_all_reviews_skips_unusable_text(event, unusable_text):
    """Reviews with null or whitespace-only text are excluded."""
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        ReviewFactory(submission=submission, text=unusable_text)
        ReviewFactory(submission=submission, text="Good one")

        result = get_all_reviews(submission)

    assert result == "Good one"


@pytest.mark.django_db
def test_get_all_reviews_all_empty_returns_empty(event):
    """Returns empty string when all reviews have empty/whitespace text."""
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        ReviewFactory(submission=submission, text="  ")
        ReviewFactory(submission=submission, text="")

        assert get_all_reviews(submission) == ""


@pytest.mark.django_db
def test_get_all_reviews_strips_text(event):
    """Review texts are stripped of leading/trailing whitespace."""
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        ReviewFactory(submission=submission, text="  trimmed  ")

        assert get_all_reviews(submission) == "trimmed"


@pytest.mark.django_db
def test_get_mail_context_includes_event_placeholders(event):
    """When called with an event, the context includes event-level
    placeholders like event_name and event_slug."""
    with scope(event=event):
        context = get_mail_context(event=event)

    assert context["event_name"] == event.name
    assert context["event_slug"] == event.slug


@pytest.mark.django_db
def test_get_mail_context_includes_user_placeholders(event):
    """When called with event and user, user-level placeholders are included."""
    user = UserFactory(name="Jane Doe", email="jane@example.org")

    with scope(event=event):
        context = get_mail_context(event=event, user=user)

    assert context["name"] == "Jane Doe"
    assert context["email"] == "jane@example.org"


@pytest.mark.django_db
def test_get_mail_context_excludes_placeholders_without_required_context(event):
    """Placeholders whose required context is not present are omitted.
    For example, 'name' requires 'user' and is excluded if no user is passed."""
    with scope(event=event):
        context = get_mail_context(event=event)

    assert "name" not in context


@pytest.mark.django_db
def test_get_mail_context_includes_submission_placeholders(event):
    """Submission-level placeholders are included when a submission is passed."""
    submission = SubmissionFactory(event=event, title="My Great Talk")

    with scope(event=event):
        context = get_mail_context(event=event, submission=submission)

    assert context["proposal_title"] == "My Great Talk"
    assert context["proposal_code"] == submission.code


@pytest.mark.django_db
def test_get_mail_context_auto_adds_slot_from_submission(event):
    """When a submission has a scheduled slot with start and room,
    get_mail_context automatically adds slot-dependent placeholders
    without requiring an explicit slot kwarg."""
    submission = SubmissionFactory(event=event)
    schedule = ScheduleFactory(event=event, version="v1", published=now())
    room = RoomFactory(event=event, name="Room 101")
    TalkSlotFactory(submission=submission, schedule=schedule, room=room)

    with scope(event=event):
        context = get_mail_context(event=event, submission=submission)

    assert context["session_room"] == "Room 101"


@pytest.mark.django_db
def test_get_mail_context_no_slot_omits_slot_placeholders(event):
    """When a submission has no slot, slot-dependent placeholders are omitted."""
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        context = get_mail_context(event=event, submission=submission)

    assert "session_room" not in context


@pytest.mark.django_db
def test_get_mail_context_slot_without_start_omits_slot_placeholders(event):
    """When a submission's slot has no start time, slot-dependent
    placeholders are not auto-added."""
    submission = SubmissionFactory(event=event)
    schedule = ScheduleFactory(event=event, version="v1", published=now())
    room = RoomFactory(event=event, name="Room 101")
    TalkSlotFactory(
        submission=submission, schedule=schedule, room=room, start=None, end=None
    )

    with scope(event=event):
        context = get_mail_context(event=event, submission=submission)

    assert "session_room" not in context


@pytest.mark.django_db
def test_get_mail_context_slot_without_room_omits_slot_placeholders(event):
    """When a submission's slot has no room, slot-dependent
    placeholders are not auto-added."""
    submission = SubmissionFactory(event=event)
    schedule = ScheduleFactory(event=event, version="v1", published=now())
    TalkSlotFactory(submission=submission, schedule=schedule, room=None)

    with scope(event=event):
        context = get_mail_context(event=event, submission=submission)

    assert "session_room" not in context


@pytest.mark.django_db
def test_get_available_placeholders_returns_placeholder_objects(event):
    """Returns a dict mapping identifier to placeholder object, not rendered value."""
    placeholders = get_available_placeholders(event, ["event"])

    assert "event_name" in placeholders
    assert isinstance(placeholders["event_name"], SimpleFunctionalMailTextPlaceholder)


@pytest.mark.parametrize(
    ("kwargs", "expected_present", "expected_absent"),
    (
        (["event"], set(), {"name"}),
        (["event", "user"], {"name", "email"}, set()),
        (["event", "submission"], {"proposal_title", "proposal_code"}, set()),
    ),
)
@pytest.mark.django_db
def test_get_available_placeholders_filters_by_context(
    event, kwargs, expected_present, expected_absent
):
    """Placeholders are included only when their required context keys are present."""
    placeholders = get_available_placeholders(event, kwargs)

    for key in expected_present:
        assert key in placeholders
    for key in expected_absent:
        assert key not in placeholders


@pytest.mark.django_db
def test_base_placeholders_contains_expected_identifiers(event):
    """The base set includes all documented placeholder identifiers as
    SimpleFunctionalMailTextPlaceholder instances."""
    result = base_placeholders(sender=event)
    assert all(isinstance(p, SimpleFunctionalMailTextPlaceholder) for p in result)
    identifiers = {p.identifier for p in result}

    expected_identifiers = {
        "event_name",
        "event",
        "event_slug",
        "event_url",
        "event_schedule_url",
        "event_cfp_url",
        "all_submissions_url",
        "profile_page_url",
        "deadline",
        "proposal_code",
        "session_code",
        "code",
        "talk_url",
        "proposal_url",
        "edit_url",
        "submission_url",
        "confirmation_link",
        "withdraw_link",
        "proposal_title",
        "submission_title",
        "speakers",
        "session_type",
        "submission_type",
        "track_name",
        "session_duration_minutes",
        "all_reviews",
        "session_start_date",
        "session_start_time",
        "session_end_date",
        "session_end_time",
        "session_room",
        "name",
        "email",
        "speaker_schedule_new",
        "notifications",
        "speaker_schedule_full",
    }
    assert expected_identifiers == identifiers


@pytest.mark.django_db
def test_base_placeholders_event_name_renders_correctly(event):
    """The event_name placeholder renders to the event's name."""
    result = base_placeholders(sender=event)
    event_name_placeholder = next(p for p in result if p.identifier == "event_name")

    rendered = event_name_placeholder.render({"event": event})
    assert rendered == event.name


@pytest.mark.django_db
def test_base_placeholders_aliases_share_render_output(event):
    """Aliases like event_name/event render the same value."""
    result = base_placeholders(sender=event)
    by_id = {p.identifier: p for p in result}

    context = {"event": event}
    assert by_id["event_name"].render(context) == by_id["event"].render(context)
    assert by_id["event_name"].render(context) == event.name
