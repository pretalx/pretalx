# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import zoneinfo

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db.utils import IntegrityError
from django_scopes import scope

from pretalx.cfp.flow import CfPFlow
from pretalx.common.cache import ObjectRelatedCache
from pretalx.common.language import LANGUAGE_NAMES
from pretalx.common.signals import register_locales
from pretalx.event.models import Event
from pretalx.event.models.event import (
    default_feature_flags,
    event_css_path,
    event_header_path,
    event_logo_path,
    event_og_path,
    validate_event_slug_permitted,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.schedule.domain.release import freeze_schedule
from tests.factories import (
    AvailabilityFactory,
    EventFactory,
    OrganiserFactory,
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
        "API",
        "csp_report",
        "events",
        "download",
        "healthcheck",
        "jsi18n",
        "locale",
        "metrics",
        "orga",
        "Orga",
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


@pytest.mark.parametrize(
    "slug", ("unique-slug", "Unique-Slug"), ids=("same_case", "other_case")
)
def test_event_slug_uniqueness_is_case_insensitive(slug):
    EventFactory(slug="unique-slug")
    with pytest.raises(IntegrityError):
        Event.objects.create(
            name="Duplicate",
            slug=slug,
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


@pytest.mark.parametrize(
    "kwargs",
    (
        {"date_from": dt.date(2025, 6, 10), "date_to": dt.date(2025, 6, 10)},
        {"date_from": None, "date_to": None},
        {"locale": "", "locales": ["en", "de"]},
    ),
    ids=("end_equal_to_start", "dates_missing", "locale_empty"),
)
def test_event_clean_accepts_and_lowercases_slug(kwargs):
    event = EventFactory.build(slug="MyConf", **kwargs)

    event.clean()

    assert event.slug == "myconf"


def test_event_clean_defers_empty_slug_to_field_validation():
    event = EventFactory.build(slug="", organiser=OrganiserFactory())

    with pytest.raises(ValidationError) as excinfo:
        event.full_clean()

    assert excinfo.value.message_dict == {"slug": ["This field cannot be blank."]}


@pytest.mark.parametrize(
    ("path_func", "filename", "expected_dir", "expected_target", "expected_ext"),
    (
        (event_css_path, "style.css", "myconf/css/", "custom", ".css"),
        (event_css_path, "pwn.html", "myconf/css/", "custom", ".css"),
        (event_logo_path, "logo.png", "myconf/img/", "logo", ".png"),
        (event_header_path, "banner.jpg", "myconf/img/", "header", ".jpg"),
        (event_og_path, "preview.png", "myconf/img/", "og", ".png"),
    ),
    ids=("css", "css_forced_extension", "logo", "header", "og"),
)
def test_event_upload_path_contains_slug_and_target(
    path_func, filename, expected_dir, expected_target, expected_ext
):
    instance = type("FakeEvent", (), {"slug": "myconf"})()
    result = path_func(instance, filename)

    assert result.startswith(f"{expected_dir}{expected_target}")
    assert result.endswith(expected_ext)
    assert ".html" not in result


def test_default_feature_flags_returns_independent_copies():
    a = default_feature_flags()
    b = default_feature_flags()
    a["show_schedule"] = False
    assert b["show_schedule"] is True


def test_event_locales_default_to_default_language():
    event = EventFactory()

    assert event.locales == ["en"]
    assert event.content_locales == ["en"]
    assert event.named_locales == [("en", "English")]
    assert event.named_content_locales == [("en", "English")]
    assert event.available_content_locales == sorted(LANGUAGE_NAMES.items())


@pytest.mark.parametrize(
    ("content_locales", "expected"), ((["en"], False), (["en", "de"], True))
)
def test_event_is_multilingual(content_locales, expected):
    event = EventFactory(content_locales=content_locales)
    assert event.is_multilingual is expected


@pytest.mark.parametrize(
    ("plugins", "expected"),
    ((None, []), ("", []), ("plugin_a,plugin_b", ["plugin_a", "plugin_b"])),
    ids=("null", "empty", "comma_separated"),
)
def test_event_plugin_list(event, plugins, expected):
    event.plugins = plugins
    assert event.plugin_list == expected


@pytest.mark.parametrize(
    ("plugins", "expected"),
    (
        ("pretalx_downstream,other", True),
        ("other,pretalx_downstream,another", True),
        ("other,pretalx_downstream", True),
        ("pretalx_downstream", True),
        ("pretalx_downstream_extra,xpretalx_downstream", False),
        ("", False),
        (None, False),
    ),
    ids=("leading", "middle", "trailing", "only", "substring", "empty", "null"),
)
def test_event_with_plugin_matches_whole_token(plugins, expected):
    event = EventFactory(plugins=plugins)
    EventFactory(plugins="other")

    result = list(Event.objects.with_plugin("pretalx_downstream"))

    assert result == ([event] if expected else [])


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


def test_event_wip_schedule_returns_recreates_and_deduplicates_unreleased(event):
    with scope(event=event):
        wip = event.wip_schedule
        assert wip.version is None
        assert wip.event == event

        event.schedules.filter(version__isnull=True).delete()

    event = refresh(event)
    with scope(event=event):
        assert event.wip_schedule.version is None
        assert event.wip_schedule.pk != wip.pk

        ScheduleFactory(event=event, version=None)
        assert event.schedules.filter(version__isnull=True).count() == 2

    event = refresh(event)
    with scope(event=event):
        assert event.wip_schedule.version is None
        assert event.schedules.filter(version__isnull=True).count() == 1


def test_event_current_schedule_returns_latest_published_or_prefetched(event):
    with scope(event=event):
        assert event.current_schedule is None

        schedule = ScheduleFactory(event=event, version="v1")

    event = refresh(event)
    with scope(event=event):
        assert event.current_schedule == schedule

    event = refresh(event)
    event._current_schedule_pk = schedule.pk
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
    event = EventFactory(date_from=date_from, date_to=date_to)
    assert event.duration == expected_duration


def test_event_accessor_properties():
    event = EventFactory(timezone="Europe/Berlin")

    assert event.event is event
    assert event.tz == zoneinfo.ZoneInfo("Europe/Berlin")
    assert isinstance(event.cache, ObjectRelatedCache)
    with scope(event=event):
        assert isinstance(event.cfp_flow, CfPFlow)


def test_event_datetime_bounds_in_event_tz():
    event = EventFactory(
        date_from=dt.date(2025, 7, 1),
        date_to=dt.date(2025, 7, 3),
        timezone="Europe/Berlin",
    )
    tz = zoneinfo.ZoneInfo("Europe/Berlin")

    assert event.datetime_from == dt.datetime(2025, 7, 1, 0, 0, 0, tzinfo=tz)
    assert event.datetime_to == dt.datetime(2025, 7, 3, 23, 59, 59, tzinfo=tz)


def test_event_teams_includes_all_events_and_limited_teams_only(event):
    all_events_team = TeamFactory(organiser=event.organiser, all_events=True)
    limited_team = TeamFactory(organiser=event.organiser, all_events=False)
    limited_team.limit_events.add(event)
    other_event_team = TeamFactory(organiser=event.organiser, all_events=False)
    other_event_team.limit_events.add(EventFactory(organiser=event.organiser))
    TeamFactory()

    assert set(event.teams) == {all_events_team, limited_team}


def test_event_reviewers_returns_distinct_reviewer_team_members(event):
    user = UserFactory()
    first = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    second = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    first.members.add(user)
    second.members.add(user)
    non_reviewer = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=False
    )
    non_reviewer.members.add(UserFactory())
    other_team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    other_team.limit_events.add(EventFactory(organiser=event.organiser))
    other_team.members.add(UserFactory())

    assert list(event.reviewers) == [user]


def test_event_reviews_queryset_filters_by_event(event):
    review = ReviewFactory(submission__event=event)
    ReviewFactory()

    assert list(event.reviews) == [review]


def test_event_submitters_returns_speakers_with_submissions(event):
    speaker = SpeakerFactory(event=event)
    # Bare orga-created profiles, not in event.submitters, only in submitters_for_event
    SpeakerFactory(event=event)
    SpeakerFactory(event=event, user=None, origin=SpeakerProfileOrigin.ORGA)

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
    event.feature_flags = flags
    assert event.get_feature_flag(feature) is expected


@pytest.mark.parametrize(
    ("url_attr", "expected_pattern"),
    (("urls", "/{slug}/"), ("orga_urls", "/orga/event/{slug}/")),
)
def test_event_urls_base(event, url_attr, expected_pattern):
    assert getattr(event, url_attr).base == expected_pattern.format(slug=event.slug)


@pytest.mark.parametrize(
    ("custom_domain", "public_host"),
    (("https://myevent.example.org", "https://myevent.example.org"), (None, None)),
    ids=("custom_domain", "site_url"),
)
def test_event_urls_full_uses_custom_domain_for_public_urls_only(
    event, custom_domain, public_host
):
    event.custom_domain = custom_domain
    public_host = public_host or settings.SITE_URL

    assert event.urls.submit.full() == f"{public_host}/{event.slug}/submit/"
    assert event.orga_urls.cfp.full() == (
        f"{settings.SITE_URL}/orga/event/{event.slug}/cfp/"
    )


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


@pytest.mark.parametrize(
    ("locale_input", "expected_code", "expected_name"),
    (([("xx", "Custom Language")], "xx", "Custom Language"), (["en"], "en", "English")),
    ids=("tuple_locale", "string_locale"),
)
def test_event_named_plugin_locales(
    event, register_signal_handler, locale_input, expected_code, expected_name
):
    def provide_locales(signal, sender, **kwargs):
        return locale_input

    register_signal_handler(register_locales, provide_locales)

    event = refresh(event)
    assert event.named_plugin_locales == {expected_code: expected_name}
    assert event.plugin_locales == [expected_code]


def test_event_talks_and_speakers_follow_published_schedule_and_deduplicate(event):
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
        assert list(event.talks) == []
        assert list(event.speakers) == []

    freeze_schedule(event.wip_schedule, name="v1")

    event = refresh(event)
    with scope(event=event):
        assert set(event.talks) == {sub1, sub2}
        assert list(event.speakers) == [speaker]


def test_event_meta_ordering():
    later = EventFactory(date_from=dt.date(2025, 6, 1), date_to=dt.date(2025, 6, 2))
    earlier = EventFactory(date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 1, 2))

    events = list(Event.objects.filter(pk__in=[earlier.pk, later.pk]))

    assert events == [earlier, later]


def test_style_version_stable_without_style_settings():
    event = EventFactory()
    event.display_settings.update({"heading_font": None, "text_font": None})

    assert event.has_custom_styles is False
    assert event.style_version == EventFactory().style_version


@pytest.mark.parametrize(
    "change",
    (
        lambda event: setattr(event, "primary_color", "#ff0000"),
        lambda event: event.display_settings.update({"heading_font": "SomeFont"}),
        lambda event: event.display_settings.update({"text_font": "SomeFont"}),
        lambda event: event.custom_css.save(
            "custom.css", ContentFile(b"body { color: red; }"), save=False
        ),
    ),
    ids=("color", "heading_font", "text_font", "custom_css"),
)
def test_style_settings_mark_custom_styles_and_change_style_version(change):
    event = EventFactory()
    before = event.style_version
    assert event.has_custom_styles is False

    change(event)
    del event.style_version
    del event.has_custom_styles

    assert event.has_custom_styles is True
    assert event.style_version != before


def test_settings_css_url_carries_style_version():
    event = EventFactory(primary_color="#ff0000")

    assert event.urls.settings_css == (
        f"/{event.slug}/static/event.css?v={event.style_version}"
    )
    assert event.urls.settings_css_orga == f"{event.urls.settings_css}&target=orga"


def test_event_active_review_phase_follows_phase_state(event):
    with scope(event=event):
        phase = event.active_review_phase
        assert phase.is_active is True
        assert phase.event == event

        event.review_phases.update(is_active=False)
        del event.active_review_phase
        assert event.active_review_phase is None

        event.review_phases.all().delete()
        del event.active_review_phase
        assert event.active_review_phase is None
