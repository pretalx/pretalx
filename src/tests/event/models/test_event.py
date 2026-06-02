# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import zoneinfo

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django_scopes import scope

from pretalx.cfp.flow import CfPFlow
from pretalx.common.cache import ObjectRelatedCache
from pretalx.common.language import LANGUAGE_NAMES
from pretalx.common.signals import register_locales
from pretalx.event.models import Event
from pretalx.event.models.event import (
    default_display_settings,
    default_feature_flags,
    event_css_path,
    event_header_path,
    event_logo_path,
    event_og_path,
    validate_event_slug_permitted,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.schedule.domain.release import freeze_schedule
from tests.factories import (
    AvailabilityFactory,
    EventFactory,
    QueuedMailFactory,
    ReviewFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    "slug",
    (
        "_global",
        "__debug__",
        "api",
        "csp_report",
        "events",
        "download",
        "healthcheck",
        "jsi18n",
        "locale",
        "metrics",
        "orga",
        "redirect",
        "relay",
        "widget",
        "400",
        "403",
        "404",
        "500",
        "p",
    ),
)
def test_validate_event_slug_permitted_rejects_reserved_slugs(slug):
    with pytest.raises(ValidationError) as exc_info:
        validate_event_slug_permitted(slug)
    assert exc_info.value.code == "invalid"


@pytest.mark.parametrize("slug", ("_global", "API", "Orga"))
def test_validate_event_slug_permitted_is_case_insensitive(slug):
    with pytest.raises(ValidationError):
        validate_event_slug_permitted(slug)


def test_validate_event_slug_permitted_accepts_valid_slug():
    validate_event_slug_permitted("myconference")


def test_event_feature_flags_validation_runs_on_full_clean():
    event = EventFactory(
        feature_flags={"attendee_signup": True, "present_multiple_times": True}
    )
    with pytest.raises(ValidationError) as exc_info:
        event.clean_fields(exclude=["organiser"])

    assert "feature_flags" in exc_info.value.error_dict


@pytest.mark.parametrize(
    "slug",
    ("a", "ab", "a-b", "test123", "123test"),
    ids=("single", "two_chars", "dash", "alpha_num", "num_alpha"),
)
def test_event_slug_regex_accepts_valid_formats(slug):
    event = Event(
        name="Test",
        slug=slug,
        email="test@example.com",
        date_from=dt.date.today(),
        date_to=dt.date.today(),
    )
    event.clean_fields(exclude=["organiser"])


@pytest.mark.parametrize(
    "slug",
    ("-start", "end-", ".start", "end.", "no spaces", "special!char"),
    ids=("dash_start", "dash_end", "dot_start", "dot_end", "spaces", "special"),
)
def test_event_slug_regex_rejects_invalid_formats(slug):
    event = Event(
        name="Test",
        slug=slug,
        email="test@example.com",
        date_from=dt.date.today(),
        date_to=dt.date.today(),
    )
    with pytest.raises(ValidationError):
        event.clean_fields(exclude=["organiser"])


def test_event_slug_uniqueness():
    EventFactory(slug="unique-slug")
    with pytest.raises(IntegrityError):
        Event.objects.create(
            name="Duplicate",
            slug="unique-slug",
            email="test@example.com",
            date_from=dt.date.today(),
            date_to=dt.date.today(),
        )


def test_event_slug_uniqueness_is_case_insensitive():
    """The DB-level UniqueConstraint(Lower(slug)) rejects mixed-case
    duplicates."""
    EventFactory(slug="unique-slug")
    with pytest.raises(IntegrityError):
        Event.objects.create(
            name="Duplicate",
            slug="Unique-Slug",
            email="test@example.com",
            date_from=dt.date.today(),
            date_to=dt.date.today(),
        )


def test_event_clean_rejects_end_before_start():
    event = EventFactory.build(
        date_from=dt.date(2025, 6, 15), date_to=dt.date(2025, 6, 10)
    )
    with pytest.raises(ValidationError) as exc_info:
        event.clean()

    assert "date_from" in exc_info.value.error_dict


def test_event_clean_accepts_end_equal_to_start():
    event = EventFactory.build(
        date_from=dt.date(2025, 6, 10), date_to=dt.date(2025, 6, 10)
    )
    event.clean()  # no error


def test_event_clean_skips_date_check_when_dates_missing():
    event = EventFactory.build(date_from=None, date_to=None)
    event.clean()  # no error


@pytest.mark.parametrize(
    ("path_func", "filename", "expected_dir", "expected_target"),
    (
        (event_css_path, "style.css", "myconf/css/", "custom"),
        (event_logo_path, "logo.png", "myconf/img/", "logo"),
        (event_header_path, "banner.jpg", "myconf/img/", "header"),
        (event_og_path, "preview.png", "myconf/img/", "og"),
    ),
    ids=("css", "logo", "header", "og"),
)
def test_event_upload_path_contains_slug_and_target(
    path_func, filename, expected_dir, expected_target
):
    instance = type("FakeEvent", (), {"slug": "myconf"})()
    result = path_func(instance, filename)

    assert expected_dir in result
    assert expected_target in result
    ext = filename.rsplit(".", 1)[1]
    assert result.endswith(f".{ext}")


def test_default_feature_flags_returns_independent_copies():
    """Each call returns a new dict, not the same mutable object."""
    a = default_feature_flags()
    b = default_feature_flags()
    a["show_schedule"] = False
    assert b["show_schedule"] is True


def test_event_str_returns_name(event):
    assert str(event) == str(event.name)


@pytest.mark.parametrize(
    ("locale_array", "expected"),
    (("en", ["en"]), ("en,de", ["en", "de"]), ("en,de,fr", ["en", "de", "fr"])),
)
def test_event_locales_parses_locale_array(locale_array, expected):
    event = EventFactory(locale_array=locale_array)
    assert event.locales == expected


@pytest.mark.parametrize(
    ("content_locale_array", "expected"), (("en", ["en"]), ("en,de", ["en", "de"]))
)
def test_event_content_locales_parses_content_locale_array(
    content_locale_array, expected
):
    event = EventFactory(content_locale_array=content_locale_array)
    assert event.content_locales == expected


@pytest.mark.parametrize(
    ("content_locale_array", "expected"), (("en", False), ("en,de", True))
)
def test_event_is_multilingual(content_locale_array, expected):
    event = EventFactory(content_locale_array=content_locale_array)
    assert event.is_multilingual is expected


def test_event_named_locales_returns_code_and_name():
    event = EventFactory(locale_array="en")

    assert event.named_locales == [("en", "English")]


@pytest.mark.parametrize("plugins", (None, ""))
def test_event_plugin_list_empty_when_no_plugins(event, plugins):
    event.plugins = plugins
    assert event.plugin_list == []


def test_event_plugin_list_splits_comma_separated(event):
    event.plugins = "plugin_a,plugin_b"
    assert event.plugin_list == ["plugin_a", "plugin_b"]


@pytest.mark.parametrize(
    ("color", "expected"),
    (("#ff0000", "#ff0000"), (None, settings.DEFAULT_EVENT_PRIMARY_COLOR)),
    ids=("custom_color", "default_when_unset"),
)
def test_event_visible_primary_color(event, color, expected):
    event.primary_color = color
    assert event.visible_primary_color == expected


@pytest.mark.parametrize(
    ("color", "needs_dark_text"),
    (
        ("#000000", False),
        ("#0000ff", False),
        ("#800000", False),
        ("#008000", False),
        ("#3aa57c", False),
        ("#ffffff", True),
        ("#ffff00", True),
        ("#00ffff", True),
        ("#ffcc00", True),
        (None, False),
        ("", False),
    ),
)
def test_event_primary_color_needs_dark_text(event, color, needs_dark_text):
    """Dark colors don't need dark text; light colors do; None returns False."""
    event.primary_color = color
    assert event.primary_color_needs_dark_text is needs_dark_text


@pytest.mark.parametrize(
    ("draft_count", "sent_count", "expected"),
    ((2, 1, 2), (0, 1, 0)),
    ids=("counts_only_drafts", "zero_when_no_drafts"),
)
def test_event_pending_mails_counts_drafts(event, draft_count, sent_count, expected):
    for _ in range(draft_count):
        QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    for _ in range(sent_count):
        QueuedMailFactory(event=event, state=QueuedMailStates.SENT)

    assert event.pending_mails == expected


def test_event_wip_schedule_returns_unreleased(event):
    with scope(event=event):
        wip = event.wip_schedule
        assert wip.version is None
        assert wip.event == event


def test_event_wip_schedule_creates_if_missing(event):
    with scope(event=event):
        event.schedules.filter(version__isnull=True).delete()

    event = refresh(event)
    with scope(event=event):
        wip = event.wip_schedule
        assert wip.version is None
        assert wip.event == event


def test_event_current_schedule_none_when_no_published(event):
    with scope(event=event):
        assert event.current_schedule is None


def test_event_current_schedule_returns_latest_published(event):
    with scope(event=event):
        schedule = ScheduleFactory(event=event, version="v1")

    event = refresh(event)
    with scope(event=event):
        assert event.current_schedule == schedule


@pytest.mark.parametrize(
    ("date_from", "date_to", "expected_duration"),
    (
        (dt.date(2025, 6, 10), dt.date(2025, 6, 10), 1),
        (dt.date(2025, 6, 10), dt.date(2025, 6, 12), 3),
        (dt.date(2025, 6, 10), dt.date(2025, 6, 15), 6),
    ),
    ids=("single_day", "three_days", "six_days"),
)
def test_event_duration_days(date_from, date_to, expected_duration):
    """duration returns the number of event days (inclusive)."""
    event = EventFactory(date_from=date_from, date_to=date_to)
    assert event.duration == expected_duration


def test_event_property_returns_self(event):
    """The event property returns the event itself, for polymorphic
    compatibility with models that have an event FK."""
    assert event.event is event


def test_event_tz_returns_zoneinfo():
    event = EventFactory(timezone="Europe/Berlin")
    assert event.tz == zoneinfo.ZoneInfo("Europe/Berlin")


def test_event_datetime_from_is_midnight_in_event_tz():
    event = EventFactory(
        date_from=dt.date(2025, 7, 1),
        date_to=dt.date(2025, 7, 3),
        timezone="Europe/Berlin",
    )
    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    result = event.datetime_from

    assert result.year == 2025
    assert result.month == 7
    assert result.day == 1
    assert result.hour == 0
    assert result.minute == 0
    assert result.tzinfo is not None
    assert result == dt.datetime(2025, 7, 1, 0, 0, 0, tzinfo=tz)


def test_event_datetime_to_is_end_of_day_in_event_tz():
    event = EventFactory(
        date_from=dt.date(2025, 7, 1),
        date_to=dt.date(2025, 7, 3),
        timezone="Europe/Berlin",
    )
    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    result = event.datetime_to

    assert result.hour == 23
    assert result.minute == 59
    assert result.second == 59
    assert result == dt.datetime(2025, 7, 3, 23, 59, 59, tzinfo=tz)


def test_event_teams_includes_all_events_teams(event):
    team = TeamFactory(organiser=event.organiser, all_events=True)

    assert list(event.teams) == [team]


def test_event_teams_includes_limited_teams(event):
    team = TeamFactory(organiser=event.organiser, all_events=False)
    team.limit_events.add(event)

    assert list(event.teams) == [team]


def test_event_teams_excludes_other_organiser_teams(event):
    TeamFactory()

    assert list(event.teams) == []


def test_event_teams_excludes_limited_teams_without_this_event(event):
    team = TeamFactory(organiser=event.organiser, all_events=False)
    other_event = EventFactory(organiser=event.organiser)
    team.limit_events.add(other_event)

    assert list(event.teams) == []


def test_event_reviewers_returns_reviewer_team_members(event):
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    assert list(event.reviewers) == [user]


def test_event_reviewers_excludes_non_reviewer_teams(event):
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=False)
    team.members.add(user)

    assert list(event.reviewers) == []


def test_event_reviewers_deduplicates_across_multiple_reviewer_teams(event):
    """A user in multiple reviewer teams on the same event appears only once."""
    user = UserFactory()
    first = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    second = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    first.members.add(user)
    second.members.add(user)

    assert list(event.reviewers) == [user]


def test_event_reviewers_excludes_other_events_reviewers(event):
    """Reviewers from a sibling event's limited team must not leak in."""
    other_event = EventFactory(organiser=event.organiser)
    other_team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    other_team.limit_events.add(other_event)
    other_team.members.add(UserFactory())

    assert not event.reviewers.exists()


def test_event_reviews_queryset_filters_by_event(event):
    review = ReviewFactory(submission__event=event)
    ReviewFactory()

    assert list(event.reviews) == [review]


@pytest.mark.parametrize("attr", ("talks", "speakers"))
def test_event_talks_and_speakers_empty_without_published_schedule(event, attr):
    with scope(event=event):
        assert list(getattr(event, attr)) == []


def test_event_submitters_returns_speakers_with_submissions(event):
    """submitters returns SpeakerProfiles of users who have submitted,
    excluding profiles without submissions."""
    speaker = SpeakerFactory(event=event)
    SpeakerFactory(event=event)  # counterfactual: no submissions

    with scope(event=event):
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)

        assert list(event.submitters) == [speaker]


@pytest.mark.parametrize(
    ("date_from", "date_to", "expected"),
    (
        (dt.date(2025, 7, 1), dt.date(2025, 7, 1), "July 1, 2025"),
        (dt.date(2025, 7, 1), dt.date(2025, 7, 3), "July 1 \N{EN DASH} 3, 2025"),
    ),
    ids=("single_day", "multi_day"),
)
def test_event_get_date_range_display_formats_date_range(date_from, date_to, expected):
    event = EventFactory(date_from=date_from, date_to=date_to)

    assert event.get_date_range_display() == expected


@pytest.mark.parametrize(
    ("feature", "flags", "expected"),
    (
        ("show_schedule", {"show_schedule": False}, False),
        ("show_schedule", {"show_schedule": True}, True),
        ("use_tracks", {}, True),
        ("nonexistent_feature", {}, False),
    ),
    ids=("overridden_false", "overridden_true", "default_true", "unknown_false"),
)
def test_event_get_feature_flag(event, feature, flags, expected):
    """get_feature_flag returns the flag value from feature_flags, falling
    back to defaults for missing keys and False for unknown features."""
    event.feature_flags = flags
    assert event.get_feature_flag(feature) is expected


@pytest.mark.parametrize(
    ("url_attr", "expected_pattern"),
    (("urls", "/{slug}/"), ("orga_urls", "/orga/event/{slug}/")),
)
def test_event_urls_base(event, url_attr, expected_pattern):
    assert getattr(event, url_attr).base == expected_pattern.format(slug=event.slug)


def test_event_urls_custom_domain(event):
    """When a custom domain is set, public-facing URLs use the custom
    domain, but orga URLs still use the default site URL."""
    custom = "https://myevent.example.org"
    event.custom_domain = custom

    assert custom in event.urls.submit.full()
    assert custom not in event.orga_urls.cfp.full()


def test_event_urls_uses_site_url_without_custom_domain(event):
    event.custom_domain = None

    full_url = event.urls.submit.full()
    assert settings.SITE_URL in full_url


def test_event_valid_availabilities_filters_by_event_dates():
    event = EventFactory(date_from=dt.date(2025, 7, 1), date_to=dt.date(2025, 7, 3))
    valid = AvailabilityFactory(event=event)
    AvailabilityFactory(
        event=event,
        start=event.datetime_from - dt.timedelta(days=30),
        end=event.datetime_from - dt.timedelta(days=20),
    )

    with scope(event=event):
        avails = list(event.valid_availabilities)

    assert avails == [valid]


def test_event_cache_returns_object_related_cache(event):
    assert isinstance(event.cache, ObjectRelatedCache)


def test_event_available_content_locales_returns_sorted_known_languages(event):
    """Without plugins, available_content_locales equals the sorted
    built-in LANGUAGE_NAMES."""
    result = event.available_content_locales
    expected = sorted(LANGUAGE_NAMES.items())
    assert result == expected


def test_event_named_content_locales_maps_active_locales():
    event = EventFactory(content_locale_array="en")

    assert event.named_content_locales == [("en", "English")]


@pytest.mark.parametrize(
    ("locale_input", "expected_code", "expected_name"),
    (([("xx", "Custom Language")], "xx", "Custom Language"), (["en"], "en", "English")),
    ids=("tuple_locale", "string_locale"),
)
def test_event_named_plugin_locales(
    event, register_signal_handler, locale_input, expected_code, expected_name
):
    """named_plugin_locales includes tuple locales directly and looks up
    string locales in the event's known language names."""

    def provide_locales(signal, sender, **kwargs):
        return locale_input

    register_signal_handler(register_locales, provide_locales)

    event = refresh(event)
    result = event.named_plugin_locales
    assert result[expected_code] == expected_name


def test_event_plugin_locales_returns_sorted_keys(event):
    result = event.plugin_locales
    assert isinstance(result, list)
    assert result == sorted(result)


def test_event_wip_schedule_handles_multiple_unreleased(event):
    """When multiple unversioned schedules exist (race condition), wip_schedule
    keeps the first and deletes the duplicates."""

    with scope(event=event):
        ScheduleFactory(event=event, version=None)
        assert event.schedules.filter(version__isnull=True).count() == 2

    event = refresh(event)
    with scope(event=event):
        wip = event.wip_schedule

        assert wip.version is None
        assert wip.event == event
        assert event.schedules.filter(version__isnull=True).count() == 1


def test_event_current_schedule_uses_prefetched_pk(event):
    """When _current_schedule_pk is set (by middleware), current_schedule
    uses it to fetch the schedule directly."""

    with scope(event=event):
        schedule = ScheduleFactory(event=event, version="v1")

    event = refresh(event)
    event._current_schedule_pk = schedule.pk
    with scope(event=event):
        assert event.current_schedule == schedule


def test_event_talks_returns_submissions_in_published_schedule(event):
    with scope(event=event):
        sub = SubmissionFactory(event=event, state="confirmed")
        speaker = SpeakerFactory(event=event)
        sub.speakers.add(speaker)

        room = RoomFactory(event=event, name="Room A")
        TalkSlotFactory(submission=sub, room=room)

    freeze_schedule(event.wip_schedule, name="v1")

    event = refresh(event)
    with scope(event=event):
        talks = list(event.talks)
        assert talks == [sub]


def test_event_cfp_flow_returns_cfp_flow_instance(event):
    with scope(event=event):
        flow = event.cfp_flow
        assert isinstance(flow, CfPFlow)


def test_event_meta_ordering():
    later = EventFactory(date_from=dt.date(2025, 6, 1), date_to=dt.date(2025, 6, 2))
    earlier = EventFactory(date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 1, 2))

    events = list(Event.objects.filter(pk__in=[earlier.pk, later.pk]))

    assert events == [earlier, later]


def test_event_talks_deduplicates_shared_speakers(event):
    """When a speaker has multiple slots in the published schedule,
    event.talks and event.speakers contain no duplicates."""
    with scope(event=event):
        speaker = SpeakerFactory(event=event)
        sub1 = SubmissionFactory(event=event, state="confirmed")
        sub2 = SubmissionFactory(event=event, state="confirmed")
        sub1.speakers.add(speaker)
        sub2.speakers.add(speaker)

        room = RoomFactory(event=event)
        TalkSlotFactory(submission=sub1, room=room)
        TalkSlotFactory(
            submission=sub2,
            room=room,
            start=event.datetime_from + dt.timedelta(hours=2),
            end=event.datetime_from + dt.timedelta(hours=3),
        )

    freeze_schedule(event.wip_schedule, name="v1")

    event = refresh(event)
    with scope(event=event):
        talks = list(event.talks)
        speakers = list(event.speakers)

        assert set(talks) == {sub1, sub2}
        assert len(speakers) == len(set(speakers))
        assert speakers == [speaker]


def test_has_custom_styles_false_by_default():
    event = EventFactory()

    assert event.has_custom_styles is False


def test_has_custom_styles_true_with_primary_color():
    event = EventFactory(primary_color="#ff0000")

    assert event.has_custom_styles is True


def test_has_custom_styles_true_with_heading_font():
    settings = default_display_settings()
    settings["heading_font"] = "SomeFont"
    event = EventFactory(display_settings=settings)

    assert event.has_custom_styles is True


def test_has_custom_styles_true_with_text_font():
    settings = default_display_settings()
    settings["text_font"] = "SomeFont"
    event = EventFactory(display_settings=settings)

    assert event.has_custom_styles is True


def test_event_active_review_phase_returns_active_phase(event):
    with scope(event=event):
        phase = event.active_review_phase
        assert phase.is_active is True
        assert phase.event == event


def test_event_active_review_phase_none_when_no_active_phase(event):
    with scope(event=event):
        event.review_phases.update(is_active=False)
        event.__dict__.pop("active_review_phase", None)
        assert event.active_review_phase is None


def test_event_active_review_phase_none_when_no_phases(event):
    with scope(event=event):
        event.review_phases.all().delete()
        event.__dict__.pop("active_review_phase", None)
        assert event.active_review_phase is None


def test_event_talks_slot_with_submission(event):
    """event.talks delegates to talks_for_event, returning slotted
    submissions in the current schedule."""
    with scope(event=event):
        sub = SubmissionFactory(event=event, state="confirmed")
        sub.speakers.add(SpeakerFactory(event=event))
        TalkSlotFactory(submission=sub, room=RoomFactory(event=event))

    freeze_schedule(event.wip_schedule, name="v1")
    event = refresh(event)
    with scope(event=event):
        assert list(event.talks) == [sub]


def test_event_clean_skips_locale_check_when_locale_empty():
    """When ``locale`` is empty, the locale-in-locales check is skipped."""
    event = EventFactory.build(locale="", locale_array="en,de")
    event.clean()  # no error
