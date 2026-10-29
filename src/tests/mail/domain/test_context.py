# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from contextlib import nullcontext
from decimal import Decimal

import pytest
from django.core.exceptions import FieldFetchBlocked
from django.db import DatabaseError
from django.utils.safestring import SafeString, mark_safe
from django_scopes import scope
from i18nfield.strings import LazyI18nString

from pretalx.common.exceptions import MailPlaceholderError
from pretalx.common.text.formatting import (
    MODE_HTML,
    MODE_PLAIN,
    EmailAlternativeString,
    format_map,
)
from pretalx.mail.domain.context import (
    MailContext,
    _validate_safe_extra_context,
    base_placeholders,
    get_all_reviews,
    get_mail_context,
    placeholder_aliases,
)
from pretalx.mail.domain.placeholders import (
    BaseMailTextPlaceholder,
    TrustedPlainMailTextPlaceholder,
)
from pretalx.mail.domain.recipient import Recipient
from tests.factories import (
    ReviewFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


def test_placeholder_aliases_share_render_func_and_hide_all_but_first():
    result = placeholder_aliases(
        ["event_name", "event", "evt"],
        ["event"],
        lambda event: f"rendered-{event}",
        "sample",
        explanation="The event name",
        cls=TrustedPlainMailTextPlaceholder,
    )

    assert [p.identifier for p in result] == ["event_name", "event", "evt"]
    assert [p.is_visible for p in result] == [True, False, False]
    assert [p.render({"event": "test"}) for p in result] == ["rendered-test"] * 3


@pytest.mark.parametrize(
    ("texts", "expected"),
    (
        ([], ""),
        (["Great talk", "Needs work"], "Great talk\n\n--------------\n\nNeeds work"),
        ([None, "Good one"], "Good one"),
        (["   ", "Good one"], "Good one"),
        (["  ", ""], ""),
        (["  trimmed  "], "trimmed"),
    ),
    ids=("none", "two", "skips_null", "skips_blank", "all_blank", "strips"),
)
@pytest.mark.django_db
def test_get_all_reviews_joins_usable_texts(event, texts, expected):
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        for text in texts:
            ReviewFactory(submission=submission, text=text)

        assert get_all_reviews(submission) == expected


@pytest.mark.django_db
def test_get_mail_context_includes_only_event_placeholders_without_user(event):
    with scope(event=event):
        context = get_mail_context(event=event)

    assert context["event_name"] == event.name
    assert context["event_slug"] == event.slug
    assert "name" not in context


@pytest.mark.django_db
def test_get_mail_context_includes_user_placeholders(event):
    user = UserFactory(name="Jane Doe", email="jane@example.org")

    with scope(event=event):
        context = get_mail_context(event=event, user=user)

    # ``name`` and ``email`` are UntrustedPlain placeholders — their
    # values are EmailAlternativeString pairs so the formatter can
    # fence the HTML-body output in a ``<span>``. Legitimate content
    # round-trips through both variants unchanged.
    assert context["name"].plain == "Jane Doe"
    assert context["name"].html == "<span>Jane Doe</span>"
    assert context["email"].plain == "jane@example.org"
    assert context["email"].html == "<span>jane@example.org</span>"


@pytest.mark.parametrize(
    ("profile_name", "expected_name"), (("Jane Doe", "Jane Doe"), (None, "j-doe"))
)
@pytest.mark.django_db
def test_get_mail_context_name_prefers_event_speaker_profile(
    event, profile_name, expected_name
):
    user = UserFactory(name="j-doe")

    with scope(event=event):
        profile = user.get_speaker(event)
        profile.name = profile_name
        profile.save()

        context = get_mail_context(event=event, user=user)

    assert context["name"].plain == expected_name
    assert context["name"].html == f"<span>{expected_name}</span>"


@pytest.mark.django_db
def test_get_mail_context_name_without_event_uses_user_name(event):
    user = UserFactory(name="j-doe")

    context = get_mail_context(user=user)

    assert context["name"].plain == "j-doe"


@pytest.mark.django_db
def test_get_mail_context_degrades_account_only_placeholders_for_managed(event):
    with scope(event=event):
        managed = SpeakerFactory(event=event, user=None, email="managed@example.com")
        submission = SubmissionFactory(event=event)
        submission.speakers.add(managed)

        context = get_mail_context(
            event=event, user=Recipient(managed), submission=submission
        )

    assert context["profile_page_url"] == ""
    assert context["all_submissions_url"] == ""
    assert context["confirmation_link"] == ""
    assert context["proposal_url"] == ""
    # Non-account placeholders still render normally.
    assert context["event_url"].plain == event.urls.base.full()
    assert context["email"].plain == "managed@example.com"


@pytest.mark.django_db
def test_get_mail_context_renders_account_only_placeholders_for_account_backed(event):
    with scope(event=event):
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)

        context = get_mail_context(
            event=event, user=Recipient(speaker), submission=submission
        )

    assert context["profile_page_url"].plain == event.urls.user.full()
    assert context["confirmation_link"].plain == submission.urls.confirm.full()


@pytest.mark.django_db
def test_get_mail_context_includes_submission_placeholders_without_slot(event):
    submission = SubmissionFactory(event=event, title="My Great Talk")

    with scope(event=event):
        context = get_mail_context(event=event, submission=submission)

    # ``proposal_title`` is UntrustedPlain — the value is a
    # EmailAlternativeString. Legit content round-trips unchanged.
    assert context["proposal_title"].plain == "My Great Talk"
    assert context["proposal_title"].html == "<span>My Great Talk</span>"
    assert context["proposal_code"] == submission.code
    assert "session_room" not in context


@pytest.mark.parametrize(
    ("slot_kwargs", "expected_room"),
    (({}, "Room 101"), ({"start": None, "end": None}, None), ({"room": None}, None)),
    ids=("scheduled", "unscheduled", "no_room"),
)
@pytest.mark.django_db
def test_get_mail_context_auto_adds_placed_slot_from_submission(
    event, slot_kwargs, expected_room
):
    submission = SubmissionFactory(event=event)
    schedule = ScheduleFactory(event=event, version="v1")
    room = RoomFactory(event=event, name="Room 101")
    TalkSlotFactory(
        **{"submission": submission, "schedule": schedule, "room": room, **slot_kwargs}
    )

    with scope(event=event):
        context = get_mail_context(event=event, submission=submission)

    assert ("session_room" in context) == (expected_room is not None)
    assert expected_room is None or context["session_room"] == expected_room


@pytest.mark.django_db
def test_base_placeholders_identifiers_and_alias_rendering(event):
    result = base_placeholders(sender=event)
    assert all(isinstance(p, BaseMailTextPlaceholder) for p in result)
    by_id = {p.identifier: p for p in result}

    assert set(by_id) == {
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
        "inviting_speaker",
        "email",
        "speaker_schedule_new",
        "speaker_schedule_full",
    }
    assert by_id["event_name"].render({"event": event}) == event.name
    assert by_id["event"].render({"event": event}) == event.name


@pytest.mark.parametrize("value", (None, {}))
def test_validate_safe_extra_context_accepts_empty(value):
    _validate_safe_extra_context(value)


@pytest.mark.parametrize(
    ("value", "expectation"),
    (
        (mark_safe("https://example.com"), nullcontext()),
        (EmailAlternativeString("plain", "<b>html</b>"), nullcontext()),
        (42, nullcontext()),
        (3.14, nullcontext()),
        (Decimal("19.95"), nullcontext()),
        (
            "a plain string",
            pytest.raises(TypeError, match="safe_extra_context\\['key'\\]"),
        ),
        (LazyI18nString("hello"), pytest.raises(TypeError, match="safe_extra_context")),
    ),
    ids=(
        "SafeString",
        "EmailAlternativeString",
        "int",
        "float",
        "Decimal",
        "str",
        "LazyI18nString",
    ),
)
def test_validate_safe_extra_context_accepts_only_safe_types(value, expectation):
    with expectation:
        _validate_safe_extra_context({"key": value})


@pytest.mark.django_db
def test_get_mail_context_wraps_urlman_urls_and_keeps_safe_strings(event):
    # Organiser call sites can pass ``obj.urls.foo`` directly instead of
    # spelling out ``mark_safe(obj.urls.foo.full())``.
    url = mark_safe("https://foo.test/?x=1&y=2")

    context = get_mail_context(
        event=event, safe_extra_context={"base": event.urls.base, "url": url}
    )

    assert isinstance(context["base"], SafeString)
    assert context["base"] == event.urls.base.full()
    assert context["url"] is url


@pytest.mark.parametrize(
    ("failure", "exception"),
    (
        # KeyError gotta be different from "unknown placeholder"
        (lambda event: {}["nope"], KeyError),
        (lambda event: event.no_such_attribute, AttributeError),
    ),
)
@pytest.mark.django_db
def test_mail_context_reports_placeholder_failure_as_placeholder_error(
    event, failure, exception
):
    placeholder = TrustedPlainMailTextPlaceholder("boom", ["event"], failure, "sample")
    context = MailContext(
        context_args={"event": event}, placeholders={"boom": placeholder}, values={}
    )

    with pytest.raises(
        MailPlaceholderError, match=f"'boom' raised {exception.__name__}"
    ) as error:
        format_map("{boom}", context, mode=MODE_PLAIN)

    assert isinstance(error.value.__cause__, exception)


@pytest.mark.parametrize("exception", (FieldFetchBlocked, DatabaseError))
@pytest.mark.django_db
def test_mail_context_lets_fetch_and_database_errors_through(event, exception):
    def failure(event):
        raise exception("nope")

    placeholder = TrustedPlainMailTextPlaceholder("boom", ["event"], failure, "sample")
    context = MailContext(
        context_args={"event": event}, placeholders={"boom": placeholder}, values={}
    )

    with pytest.raises(exception):
        format_map("{boom}", context, mode=MODE_PLAIN)


@pytest.mark.django_db
def test_mail_context_tolerates_unknown_placeholder(event):
    with scope(event=event):
        context = get_mail_context(event=event)

    assert format_map("{nope}", context, raise_on_missing=False) == "{nope}"


@pytest.mark.django_db
def test_mail_context_renders_each_placeholder_once(event):
    calls = []

    def count(event):
        calls.append(event)
        return "once"

    placeholder = TrustedPlainMailTextPlaceholder("counted", ["event"], count, "sample")
    context = MailContext(
        context_args={"event": event}, placeholders={"counted": placeholder}, values={}
    )

    assert format_map("{counted}", context) == "once"
    assert format_map("{counted} {counted}", context, mode=MODE_HTML) == "once once"
    assert len(calls) == 1
