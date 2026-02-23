import datetime as dt
import zoneinfo

import pytest
from django.conf import settings
from django.core import mail as djmail
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils.timezone import now as tz_now
from django_scopes import scope, scopes_disabled

from pretalx.cfp.flow import CfPFlow
from pretalx.common.cache import ObjectRelatedCache
from pretalx.common.language import LANGUAGE_NAMES
from pretalx.common.mail import CustomSMTPBackend
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
from pretalx.mail.models import MailTemplate, MailTemplateRoles, QueuedMailStates
from pretalx.person.models import SpeakerInformation
from pretalx.person.models.preferences import UserEventPreferences
from pretalx.schedule.models import Schedule
from pretalx.schedule.models.slot import TalkSlot
from pretalx.submission.models import Submission, SubmissionType
from pretalx.submission.models.feedback import Feedback
from pretalx.submission.models.question import Answer, Question
from pretalx.submission.models.resource import Resource
from pretalx.submission.models.tag import Tag
from tests.dummy_app.apps import installed_events, uninstalled_events
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    AvailabilityFactory,
    EventExtraLinkFactory,
    EventFactory,
    MailTemplateFactory,
    OrganiserFactory,
    QuestionFactory,
    QueuedMailFactory,
    ReviewFactory,
    ReviewPhaseFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserEventPreferencesFactory,
    UserFactory,
)
from tests.utils import refresh

pytestmark = pytest.mark.unit


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
    """Each reserved slug raises a ValidationError with code 'invalid'."""
    with pytest.raises(ValidationError) as exc_info:
        validate_event_slug_permitted(slug)
    assert exc_info.value.code == "invalid"


@pytest.mark.parametrize("slug", ("_global", "API", "Orga"))
def test_validate_event_slug_permitted_is_case_insensitive(slug):
    with pytest.raises(ValidationError):
        validate_event_slug_permitted(slug)


def test_validate_event_slug_permitted_accepts_valid_slug():
    validate_event_slug_permitted("myconference")


@pytest.mark.parametrize(
    "slug",
    ("a", "ab", "a-b", "test123", "123test"),
    ids=("single", "two_chars", "dash", "alpha_num", "num_alpha"),
)
@pytest.mark.django_db
def test_event_slug_regex_accepts_valid_formats(slug):
    """The slug field regex validator accepts alphanumeric slugs with dashes/dots."""
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
@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_slug_uniqueness():
    EventFactory(slug="unique-slug")
    with pytest.raises(IntegrityError), scopes_disabled():
        Event.objects.create(
            name="Duplicate",
            slug="unique-slug",
            email="test@example.com",
            date_from=dt.date.today(),
            date_to=dt.date.today(),
        )


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
    """Upload path functions return paths under {slug}/{dir}/ with the correct target name."""
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


@pytest.mark.django_db
def test_event_str_returns_name(event):
    assert str(event) == str(event.name)


@pytest.mark.parametrize(
    ("locale_array", "expected"),
    (("en", ["en"]), ("en,de", ["en", "de"]), ("en,de,fr", ["en", "de", "fr"])),
)
@pytest.mark.django_db
def test_event_locales_parses_locale_array(locale_array, expected):
    event = EventFactory(locale_array=locale_array)
    assert event.locales == expected


@pytest.mark.parametrize(
    ("content_locale_array", "expected"), (("en", ["en"]), ("en,de", ["en", "de"]))
)
@pytest.mark.django_db
def test_event_content_locales_parses_content_locale_array(
    content_locale_array, expected
):
    event = EventFactory(content_locale_array=content_locale_array)
    assert event.content_locales == expected


@pytest.mark.parametrize(
    ("content_locale_array", "expected"), (("en", False), ("en,de", True))
)
@pytest.mark.django_db
def test_event_is_multilingual(content_locale_array, expected):
    event = EventFactory(content_locale_array=content_locale_array)
    assert event.is_multilingual is expected


@pytest.mark.django_db
def test_event_named_locales_returns_code_and_name():
    event = EventFactory(locale_array="en")

    assert event.named_locales == [("en", "English")]


@pytest.mark.parametrize("plugins", (None, ""))
@pytest.mark.django_db
def test_event_plugin_list_empty_when_no_plugins(event, plugins):
    event.plugins = plugins
    assert event.plugin_list == []


@pytest.mark.django_db
def test_event_plugin_list_splits_comma_separated(event):
    event.plugins = "plugin_a,plugin_b"
    assert event.plugin_list == ["plugin_a", "plugin_b"]


@pytest.mark.django_db
def test_event_enable_plugin_adds_to_list(event):
    event.plugins = ""
    event.enable_plugin("tests.dummy_app")
    assert event.plugin_list == ["tests.dummy_app"]


@pytest.mark.django_db
def test_event_enable_plugin_twice_is_idempotent(event):
    event.enable_plugin("tests.dummy_app")
    event.enable_plugin("tests.dummy_app")
    assert event.plugin_list.count("tests.dummy_app") == 1


@pytest.mark.django_db
def test_event_disable_plugin_removes_from_list(event):
    event.plugins = ""
    event.enable_plugin("tests.dummy_app")
    assert event.plugin_list == ["tests.dummy_app"]

    event.disable_plugin("tests.dummy_app")
    assert event.plugin_list == []


@pytest.mark.django_db
def test_event_disable_plugin_not_present_is_noop(event):
    event.plugins = ""
    event.disable_plugin("nonexistent")
    assert event.plugin_list == []


@pytest.mark.parametrize(
    ("color", "expected"),
    (("#ff0000", "#ff0000"), (None, settings.DEFAULT_EVENT_PRIMARY_COLOR)),
    ids=("custom_color", "default_when_unset"),
)
@pytest.mark.django_db
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
@pytest.mark.django_db
def test_event_primary_color_needs_dark_text(event, color, needs_dark_text):
    """Dark colors don't need dark text; light colors do; None returns False."""
    event.primary_color = color
    assert event.primary_color_needs_dark_text is needs_dark_text


@pytest.mark.django_db
def test_event_get_default_submission_type_returns_existing(event):
    with scope(event=event):
        existing_type = event.submission_types.first()
        result = event._get_default_submission_type()

        assert result == existing_type
        assert result.event == event


@pytest.mark.django_db
def test_event_get_default_submission_type_creates_when_none(event):
    with scope(event=event):
        # Delete the CfP first to remove the FK constraint, then all types
        event.cfp.delete()
        event.submission_types.all().delete()
        assert SubmissionType.objects.filter(event=event).count() == 0

        result = event._get_default_submission_type()

        assert str(result.name) == "Talk"
        assert result.event == event
        assert result.pk is not None


@pytest.mark.django_db
def test_event_get_mail_template_returns_existing(event):
    with scope(event=event):
        existing = event.mail_templates.get(role="submission.state.accepted")
        template = event.get_mail_template("submission.state.accepted")
        assert template == existing
        assert template.event == event


@pytest.mark.django_db
def test_event_get_mail_template_creates_when_missing(event):
    with scope(event=event):
        event.mail_templates.filter(role="submission.state.accepted").delete()
        template = event.get_mail_template("submission.state.accepted")

        assert template.role == "submission.state.accepted"
        assert template.event == event
        assert template.pk is not None


@pytest.mark.django_db
def test_event_build_initial_data_creates_cfp(event):
    with scope(event=event):
        assert event.cfp.event == event
        assert event.cfp.default_type.event == event


@pytest.mark.django_db
def test_event_build_initial_data_creates_wip_schedule(event):
    with scope(event=event):
        assert event.schedules.filter(version__isnull=True).exists()


@pytest.mark.django_db
def test_event_build_initial_data_creates_mail_templates(event):
    with scope(event=event):
        assert event.mail_templates.count() == len(MailTemplateRoles.choices)


@pytest.mark.django_db
def test_event_build_initial_data_creates_review_phases(event):
    with scope(event=event):
        assert event.review_phases.count() == 2


@pytest.mark.django_db
def test_event_build_initial_data_creates_score_categories(event):
    """build_initial_data creates one score category with three scores (No/Maybe/Yes)."""
    with scope(event=event):
        assert event.score_categories.count() == 1
        category = event.score_categories.first()
        assert category.scores.count() == 3


@pytest.mark.django_db
def test_event_build_initial_data_is_idempotent(event):
    with scope(event=event):
        template_count = event.mail_templates.count()
        schedule_count = event.schedules.count()

        event.build_initial_data()

        assert event.mail_templates.count() == template_count
        assert event.schedules.count() == schedule_count


@pytest.mark.django_db
def test_event_build_initial_data_recreates_after_deletion(event):
    with scope(event=event):
        event.cfp.delete()
        event.mail_templates.all().delete()
        event.build_initial_data()

        assert event.cfp.event == event
        assert event.cfp.default_type.event == event
        assert event.mail_templates.count() == len(MailTemplateRoles.choices)


@pytest.mark.django_db
def test_event_save_calls_build_initial_data_on_create():
    event = EventFactory()
    with scope(event=event):
        assert event.cfp.event == event
        assert event.schedules.filter(version__isnull=True).exists()
        assert event.mail_templates.count() == len(MailTemplateRoles.choices)


@pytest.mark.django_db
def test_event_save_skip_initial_data_flag():
    with scopes_disabled():
        organiser = OrganiserFactory()
        event = Event(
            name="Skip Init",
            slug="skip-init",
            organiser=organiser,
            email="test@example.com",
            date_from=dt.date.today(),
            date_to=dt.date.today(),
        )
        event.save(skip_initial_data=True)

        assert not event.mail_templates.exists()
        assert not event.schedules.exists()


@pytest.mark.parametrize(
    ("draft_count", "sent_count", "expected"),
    ((2, 1, 2), (0, 1, 0)),
    ids=("counts_only_drafts", "zero_when_no_drafts"),
)
@pytest.mark.django_db
def test_event_pending_mails_counts_drafts(event, draft_count, sent_count, expected):
    for _ in range(draft_count):
        QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    for _ in range(sent_count):
        QueuedMailFactory(event=event, state=QueuedMailStates.SENT)

    assert event.pending_mails == expected


@pytest.mark.django_db
def test_event_wip_schedule_returns_unreleased(event):
    with scope(event=event):
        wip = event.wip_schedule
        assert wip.version is None
        assert wip.event == event


@pytest.mark.django_db
def test_event_wip_schedule_creates_if_missing(event):
    with scope(event=event):
        event.schedules.filter(version__isnull=True).delete()

    event = refresh(event)
    with scope(event=event):
        wip = event.wip_schedule
        assert wip.version is None
        assert wip.event == event


@pytest.mark.django_db
def test_event_current_schedule_none_when_no_published(event):
    with scope(event=event):
        assert event.current_schedule is None


@pytest.mark.django_db
def test_event_current_schedule_returns_latest_published(event):
    with scope(event=event):
        schedule = ScheduleFactory(event=event, version="v1", published=tz_now())

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
@pytest.mark.django_db
def test_event_duration_days(date_from, date_to, expected_duration):
    """duration returns the number of event days (inclusive)."""
    event = EventFactory(date_from=date_from, date_to=date_to)
    assert event.duration == expected_duration


@pytest.mark.django_db
def test_event_get_mail_backend_default(event):
    """get_mail_backend returns the default Django mail backend when
    smtp_use_custom is falsy."""
    event.mail_settings["smtp_use_custom"] = ""
    backend = event.get_mail_backend()
    assert not isinstance(backend, CustomSMTPBackend)


@pytest.mark.django_db
def test_event_get_mail_backend_custom(event):
    event.mail_settings["smtp_use_custom"] = True
    event.mail_settings["smtp_host"] = "mail.example.com"
    event.mail_settings["smtp_port"] = 465
    event.mail_settings["smtp_username"] = "user"
    event.mail_settings["smtp_password"] = "pass"
    event.mail_settings["smtp_use_tls"] = False
    event.mail_settings["smtp_use_ssl"] = True

    backend = event.get_mail_backend()

    assert isinstance(backend, CustomSMTPBackend)


@pytest.mark.django_db
def test_event_get_mail_backend_force_custom(event):
    """get_mail_backend with force_custom=True returns a CustomSMTPBackend
    even when smtp_use_custom is falsy."""
    event.mail_settings["smtp_use_custom"] = ""
    event.mail_settings["smtp_host"] = "mail.example.com"

    backend = event.get_mail_backend(force_custom=True)

    assert isinstance(backend, CustomSMTPBackend)


@pytest.mark.django_db
def test_event_property_returns_self(event):
    """The event property returns the event itself, for polymorphic
    compatibility with models that have an event FK."""
    assert event.event is event


@pytest.mark.django_db
def test_event_tz_returns_zoneinfo():
    event = EventFactory(timezone="Europe/Berlin")
    assert event.tz == zoneinfo.ZoneInfo("Europe/Berlin")


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_teams_includes_all_events_teams(event):
    team = TeamFactory(organiser=event.organiser, all_events=True)

    assert list(event.teams) == [team]


@pytest.mark.django_db
def test_event_teams_includes_limited_teams(event):
    team = TeamFactory(organiser=event.organiser, all_events=False)
    team.limit_events.add(event)

    assert list(event.teams) == [team]


@pytest.mark.django_db
def test_event_teams_excludes_other_organiser_teams(event):
    TeamFactory()

    assert list(event.teams) == []


@pytest.mark.django_db
def test_event_teams_excludes_limited_teams_without_this_event(event):
    team = TeamFactory(organiser=event.organiser, all_events=False)
    other_event = EventFactory(organiser=event.organiser)
    team.limit_events.add(other_event)

    assert list(event.teams) == []


@pytest.mark.django_db
def test_event_reviewers_returns_reviewer_team_members(event):
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    assert list(event.reviewers) == [user]


@pytest.mark.django_db
def test_event_reviewers_excludes_non_reviewer_teams(event):
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=False)
    team.members.add(user)

    assert list(event.reviewers) == []


@pytest.mark.django_db
def test_event_reviews_queryset_filters_by_event(event):
    review = ReviewFactory(submission__event=event)
    ReviewFactory()

    with scopes_disabled():
        assert list(event.reviews) == [review]


@pytest.mark.django_db
def test_event_active_review_phase_returns_active_phase(event):
    with scope(event=event):
        phase = event.active_review_phase
        assert phase.is_active is True
        assert phase.event == event


@pytest.mark.django_db
def test_event_active_review_phase_creates_when_none_exist(event):
    with scope(event=event):
        event.review_phases.all().delete()

    event = refresh(event)
    with scope(event=event):
        phase = event.active_review_phase

        assert phase.event == event
        assert phase.pk is not None


@pytest.mark.django_db
def test_event_update_review_phase_keeps_current_when_valid(event):
    with scope(event=event):
        event.review_phases.all().delete()
        phase = ReviewPhaseFactory(
            event=event,
            name="Active",
            start=tz_now() - dt.timedelta(days=1),
            end=tz_now() + dt.timedelta(days=30),
            is_active=True,
            position=0,
        )

    event = refresh(event)
    with scope(event=event):
        result = event.update_review_phase()
        assert result == phase


@pytest.mark.django_db
def test_event_update_review_phase_deactivates_expired(event):
    """update_review_phase deactivates an expired phase and returns None
    when no successor is available."""
    with scope(event=event):
        event.review_phases.all().delete()
        phase = ReviewPhaseFactory(
            event=event,
            name="Expired",
            start=tz_now() - dt.timedelta(days=10),
            end=tz_now() - dt.timedelta(days=3),
            is_active=True,
            position=0,
        )

    event = refresh(event)
    with scope(event=event):
        result = event.update_review_phase()
        assert result is None
        phase.refresh_from_db()
        assert not phase.is_active


@pytest.mark.django_db
def test_event_update_review_phase_activates_next(event):
    with scope(event=event):
        event.review_phases.all().delete()
        expired_phase = ReviewPhaseFactory(
            event=event,
            name="Expired",
            start=tz_now() - dt.timedelta(days=10),
            end=tz_now() - dt.timedelta(days=3),
            is_active=True,
            position=0,
        )
        next_phase = ReviewPhaseFactory(
            event=event,
            name="Next",
            start=expired_phase.end,
            is_active=False,
            position=1,
        )

    event = refresh(event)
    with scope(event=event):
        result = event.update_review_phase()
        assert result == next_phase
        next_phase.refresh_from_db()
        assert next_phase.is_active


@pytest.mark.django_db
def test_event_update_review_phase_deactivates_future_phase(event):
    with scope(event=event):
        event.review_phases.all().delete()
        future_phase = ReviewPhaseFactory(
            event=event,
            name="Future",
            start=tz_now() + dt.timedelta(days=30),
            is_active=True,
            position=0,
        )

    event = refresh(event)
    with scope(event=event):
        result = event.update_review_phase()
        assert result is None
        future_phase.refresh_from_db()
        assert not future_phase.is_active


@pytest.mark.django_db
def test_event_reorder_review_phases_sorts_by_start(event):
    """reorder_review_phases assigns positions by start date, with
    null-start phases coming first."""
    with scope(event=event):
        event.review_phases.all().delete()
        later = ReviewPhaseFactory(
            event=event,
            name="Later",
            start=tz_now() + dt.timedelta(days=10),
            position=0,
        )
        earlier = ReviewPhaseFactory(
            event=event,
            name="Earlier",
            start=tz_now() + dt.timedelta(days=1),
            position=1,
        )
        no_start = ReviewPhaseFactory(
            event=event, name="NoStart", start=None, position=2
        )

        event.reorder_review_phases()

        no_start.refresh_from_db()
        earlier.refresh_from_db()
        later.refresh_from_db()
        assert no_start.position < earlier.position < later.position


@pytest.mark.parametrize("attr", ("talks", "speakers"))
@pytest.mark.django_db
def test_event_talks_and_speakers_empty_without_published_schedule(event, attr):
    with scope(event=event):
        assert list(getattr(event, attr)) == []


@pytest.mark.django_db
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
@pytest.mark.django_db
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
@pytest.mark.django_db
def test_event_get_feature_flag(event, feature, flags, expected):
    """get_feature_flag returns the flag value from feature_flags, falling
    back to defaults for missing keys and False for unknown features."""
    event.feature_flags = flags
    assert event.get_feature_flag(feature) is expected


@pytest.mark.parametrize(
    ("url_attr", "expected_pattern"),
    (("urls", "/{slug}/"), ("orga_urls", "/orga/event/{slug}/")),
)
@pytest.mark.django_db
def test_event_urls_base(event, url_attr, expected_pattern):
    assert getattr(event, url_attr).base == expected_pattern.format(slug=event.slug)


@pytest.mark.django_db
def test_event_urls_custom_domain(event):
    """When a custom domain is set, public-facing URLs use the custom
    domain, but orga URLs still use the default site URL."""
    custom = "https://myevent.example.org"
    event.custom_domain = custom

    assert custom in event.urls.submit.full()
    assert custom not in event.orga_urls.cfp.full()


@pytest.mark.django_db
def test_event_urls_uses_site_url_without_custom_domain(event):
    event.custom_domain = None

    full_url = event.urls.submit.full()
    assert settings.SITE_URL in full_url


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_cache_returns_object_related_cache(event):
    assert isinstance(event.cache, ObjectRelatedCache)


@pytest.mark.django_db
def test_event_copy_data_from_copies_attributes(event):
    with scopes_disabled():
        other_event = EventFactory(
            organiser=event.organiser,
            primary_color="#ff0000",
            locale="de",
            locale_array="de,en",
        )
        other_event.feature_flags = {"testing": True}
        other_event.save(skip_initial_data=True)

        event.copy_data_from(other_event)

    assert event.primary_color == "#ff0000"
    assert event.locale == "de"
    assert event.feature_flags == {"testing": True}


@pytest.mark.django_db
def test_event_copy_data_from_does_not_copy_custom_domain(event):
    """copy_data_from does not copy custom_domain, preserving the
    target event's domain configuration."""
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        other_event.custom_domain = "https://custom.example.org"
        other_event.save(skip_initial_data=True)

        event.copy_data_from(other_event)

    assert event.custom_domain is None


@pytest.mark.django_db
def test_event_copy_data_from_respects_skip_attributes(event):
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser, primary_color="#ff0000")
        other_event.feature_flags = {"testing": True}
        other_event.save(skip_initial_data=True)

        original_flags = event.feature_flags.copy()
        event.copy_data_from(other_event, skip_attributes=["feature_flags"])

    assert event.feature_flags == original_flags
    assert event.primary_color == "#ff0000"


@pytest.mark.django_db
def test_event_copy_data_from_copies_submission_types(event):
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        SubmissionTypeFactory(event=other_event, name="Workshop")

    with scope(event=other_event):
        source_type_count = other_event.submission_types.count()

    with scopes_disabled():
        event.copy_data_from(other_event)

    with scope(event=event):
        assert event.submission_types.count() == source_type_count


@pytest.mark.django_db
def test_event_copy_data_from_copies_tracks(event):
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        TrackFactory(event=other_event, name="Security")

    with scopes_disabled():
        event.copy_data_from(other_event)

    with scope(event=event):
        track_names = [str(t.name) for t in event.tracks.all()]
        assert track_names == ["Security"]


@pytest.mark.django_db
def test_event_copy_data_from_copies_mail_templates(event):
    """copy_data_from clones non-auto-created mail templates from the
    source event and recreates role-based templates via build_initial_data."""
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        MailTemplateFactory(
            event=other_event,
            subject="Custom Template",
            is_auto_created=False,
            role=None,
        )

    with scopes_disabled():
        event.copy_data_from(other_event)

    with scope(event=event):
        subjects = [str(t.subject) for t in event.mail_templates.all()]
        assert "Custom Template" in subjects


@pytest.mark.django_db
def test_event_shred_deletes_event(event):
    pk = event.pk
    with scopes_disabled():
        event.shred()
    assert not Event.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_event_shred_deletes_related_data(event):
    with scope(event=event):
        sub = SubmissionFactory(event=event)
        template_pks = list(event.mail_templates.values_list("pk", flat=True))

    with scopes_disabled():
        event.shred()

    with scopes_disabled():
        assert not Submission.all_objects.filter(pk=sub.pk).exists()
        assert not MailTemplate.objects.filter(pk__in=template_pks).exists()


@pytest.mark.django_db
def test_event_available_content_locales_returns_sorted_known_languages(event):
    """Without plugins, available_content_locales equals the sorted
    built-in LANGUAGE_NAMES."""
    result = event.available_content_locales
    expected = sorted(LANGUAGE_NAMES.items())
    assert result == expected


@pytest.mark.django_db
def test_event_named_content_locales_maps_active_locales():
    event = EventFactory(content_locale_array="en")

    assert event.named_content_locales == [("en", "English")]


@pytest.mark.parametrize(
    ("locale_input", "expected_code", "expected_name"),
    (([("xx", "Custom Language")], "xx", "Custom Language"), (["en"], "en", "English")),
    ids=("tuple_locale", "string_locale"),
)
@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_plugin_locales_returns_sorted_keys(event):
    result = event.plugin_locales
    assert isinstance(result, list)
    assert result == sorted(result)


@pytest.mark.django_db
def test_event_set_plugins_calls_installed_hook(event):
    installed_events.clear()
    event.set_plugins(["tests.dummy_app"])
    assert installed_events == [event.slug]


@pytest.mark.django_db
def test_event_set_plugins_calls_uninstalled_hook(event):
    uninstalled_events.clear()
    event.plugins = "tests.dummy_app"
    event.set_plugins([])
    assert uninstalled_events == [event.slug]


@pytest.mark.django_db
def test_event_set_plugins_skips_missing_installed_hook(event):
    """Enabling a plugin whose app has no installed() method doesn't error."""
    event.set_plugins(["tests.dummy_app_no_hooks"])

    assert event.plugin_list == ["tests.dummy_app_no_hooks"]


@pytest.mark.django_db
def test_event_set_plugins_skips_missing_uninstalled_hook(event):
    """Disabling a plugin whose app has no uninstalled() method doesn't error."""
    event.plugins = "tests.dummy_app_no_hooks"

    event.set_plugins([])

    assert event.plugin_list == []


@pytest.mark.django_db
def test_event_copy_data_from_copies_extra_links(event):
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        EventExtraLinkFactory(
            event=other_event,
            label="Blog",
            url="https://blog.example.com",
            role="footer",
        )

        event.copy_data_from(other_event)

    with scope(event=event):
        links = list(event.extra_links.all())
        assert len(links) == 1
        assert str(links[0].label) == "Blog"
        assert links[0].url == "https://blog.example.com"


@pytest.mark.django_db
def test_event_copy_data_from_copies_rooms_and_availabilities(event):
    """copy_data_from clones rooms and their availabilities, shifting
    availability times by the date delta between events."""
    with scopes_disabled():
        other_event = EventFactory(
            organiser=event.organiser,
            date_from=dt.date(2025, 1, 1),
            date_to=dt.date(2025, 1, 3),
        )
        room = RoomFactory(event=other_event, name="Main Hall")
        avail = AvailabilityFactory(event=other_event, room=room)
        event.rooms.all().delete()

        event.copy_data_from(other_event)

    delta = event.date_from - other_event.date_from
    with scope(event=event):
        rooms = list(event.rooms.all())
        assert len(rooms) == 1
        assert str(rooms[0].name) == "Main Hall"
        copied_avail = rooms[0].availabilities.first()
        assert copied_avail is not None
        assert copied_avail.start == avail.start + delta
        assert copied_avail.end == avail.end + delta


@pytest.mark.django_db
def test_event_copy_data_from_skips_rooms_when_target_has_rooms(event):
    """copy_data_from does not copy rooms when the target event already
    has rooms, to avoid duplicating manually configured rooms."""
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        RoomFactory(event=other_event, name="Source Room")
        RoomFactory(event=event, name="Existing Room")

        event.copy_data_from(other_event)

    with scope(event=event):
        room_names = [str(r.name) for r in event.rooms.all()]
        assert "Existing Room" in room_names
        assert "Source Room" not in room_names


@pytest.mark.django_db
def test_event_copy_data_from_copies_questions_with_options_and_tracks(event):
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        track = TrackFactory(event=other_event, name="DevTrack")
        sub_type = SubmissionTypeFactory(event=other_event, name="Lightning")
        question = QuestionFactory(
            event=other_event,
            question="What is your experience level?",
            variant="choices",
            target="submission",
        )
        AnswerOptionFactory(question=question, answer="Beginner")
        AnswerOptionFactory(question=question, answer="Expert")
        question.tracks.add(track)
        question.submission_types.add(sub_type)

        event.copy_data_from(other_event)

    with scope(event=event):
        questions = list(event.questions.all())
        assert len(questions) == 1
        copied_q = questions[0]
        assert str(copied_q.question) == "What is your experience level?"
        assert copied_q.options.count() == 2
        assert copied_q.tracks.count() == 1
        assert copied_q.submission_types.count() == 1


@pytest.mark.django_db
def test_event_copy_data_from_does_not_copy_question_answers(event):
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        question = QuestionFactory(
            event=other_event,
            question="Dietary needs?",
            variant="choices",
            target="speaker",
        )
        AnswerOptionFactory(question=question, answer="Vegan")
        sub = SubmissionFactory(event=other_event)
        AnswerFactory(question=question, answer="Vegan", submission=sub)

        event.copy_data_from(other_event)

    with scope(event=event):
        copied_q = event.questions.first()
        assert copied_q is not None
        assert str(copied_q.question) == "Dietary needs?"
        assert Answer.objects.filter(question=copied_q).count() == 0


@pytest.mark.django_db
def test_event_copy_data_from_copies_speaker_information(event):
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        track = TrackFactory(event=other_event, name="InfoTrack")
        sub_type = SubmissionTypeFactory(event=other_event, name="Workshop")
        info = SpeakerInformationFactory(
            event=other_event, title="Travel Info", text="We cover travel costs."
        )
        info.limit_tracks.add(track)
        info.limit_types.add(sub_type)

        event.copy_data_from(other_event)

    with scope(event=event):
        infos = list(event.information.all())
        assert len(infos) == 1
        copied_info = infos[0]
        assert str(copied_info.title) == "Travel Info"
        assert copied_info.limit_tracks.count() == 1
        assert copied_info.limit_types.count() == 1


@pytest.mark.django_db
def test_event_copy_data_from_copies_user_preferences(event):
    user = UserFactory()
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        UserEventPreferencesFactory(
            user=user, event=other_event, preferences={"theme": "dark"}
        )

        event.copy_data_from(other_event)

    with scopes_disabled():
        prefs = UserEventPreferences.objects.filter(event=event, user=user).first()
        assert prefs is not None
        assert prefs.preferences == {"theme": "dark"}


@pytest.mark.django_db
def test_event_copy_data_from_copies_score_categories_with_tracks(event):
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        track = TrackFactory(event=other_event, name="ScoreTrack")
        # Clear existing categories on source (from build_initial_data)
        other_event.score_categories.all().delete()
        category = ReviewScoreCategoryFactory(event=other_event, name="Quality")
        category.limit_tracks.add(track)
        ReviewScoreFactory(category=category, value=0, label="Bad")
        ReviewScoreFactory(category=category, value=1, label="Good")

        event.copy_data_from(other_event)

    with scope(event=event):
        categories = list(event.score_categories.all())
        assert len(categories) == 1
        quality_cat = categories[0]
        assert str(quality_cat.name) == "Quality"
        assert quality_cat.scores.count() == 2
        assert quality_cat.limit_tracks.count() == 1


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_current_schedule_uses_prefetched_pk(event):
    """When _current_schedule_pk is set (by middleware), current_schedule
    uses it to fetch the schedule directly."""

    with scope(event=event):
        schedule = ScheduleFactory(event=event, version="v1", published=tz_now())

    event = refresh(event)
    event._current_schedule_pk = schedule.pk
    with scope(event=event):
        assert event.current_schedule == schedule


@pytest.mark.django_db
def test_event_talks_returns_submissions_in_published_schedule(event):
    with scope(event=event):
        sub = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        sub.speakers.add(speaker)
        sub.state = "confirmed"
        sub.save()

        room = RoomFactory(event=event, name="Room A")
        TalkSlotFactory(submission=sub, room=room)

    with scopes_disabled():
        event.wip_schedule.freeze(name="v1")

    event = refresh(event)
    with scope(event=event):
        talks = list(event.talks)
        assert talks == [sub]


@pytest.mark.django_db
def test_event_cfp_flow_returns_cfp_flow_instance(event):
    with scope(event=event):
        flow = event.cfp_flow
        assert isinstance(flow, CfPFlow)


@pytest.mark.django_db
def test_event_release_schedule_freezes_wip_schedule(event):
    with scope(event=event):
        initial_published = event.schedules.filter(published__isnull=False).count()

    with scopes_disabled():
        event.release_schedule(name="v1")

    with scope(event=event):
        assert (
            event.schedules.filter(published__isnull=False).count()
            == initial_published + 1
        )
        released = event.schedules.get(version="v1")
        assert released.published is not None


@pytest.mark.django_db
def test_event_send_orga_mail_delivers_email(event):
    """send_orga_mail formats placeholders and sends to the event's email."""
    djmail.outbox = []
    text = "Dashboard: {event_dashboard}, Submissions: {submission_count}"

    with scope(event=event):
        event.send_orga_mail(text)

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.to == [event.email]
    assert sent.subject == "News from your content system"
    assert sent.body == (f"Dashboard: {event.orga_urls.base.full()}, Submissions: 0")


@pytest.mark.django_db
def test_event_send_orga_mail_with_stats(event):

    with scope(event=event):
        wip = event.wip_schedule
    with scopes_disabled():
        wip.freeze(name="v1")

    event = refresh(event)
    djmail.outbox = []
    text = (
        "Talks: {talk_count}, Reviews: {review_count}, "
        "Schedules: {schedule_count}, Mails: {mail_count}, "
        "Submissions: {submission_count}"
    )

    with scope(event=event):
        event.send_orga_mail(text, stats=True)

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.to == [event.email]
    assert sent.subject == "News from your content system"
    assert sent.body == "Talks: 0, Reviews: 0, Schedules: 1, Mails: 0, Submissions: 0"


@pytest.mark.django_db
def test_event_has_unreleased_schedule_changes_false_initially(event):
    with scope(event=event):
        assert event.has_unreleased_schedule_changes is False


@pytest.mark.django_db
def test_event_update_review_phase_returns_none_when_no_active_and_no_eligible(event):
    with scope(event=event):
        event.review_phases.all().delete()
        future_phase = ReviewPhaseFactory(
            event=event,
            name="Future",
            start=tz_now() + dt.timedelta(days=30),
            is_active=False,
            position=0,
        )

    event = refresh(event)
    with scope(event=event):
        result = event.update_review_phase()

        assert result is None
        future_phase.refresh_from_db()
        assert not future_phase.is_active


@pytest.mark.django_db
def test_event_meta_ordering():
    later = EventFactory(date_from=dt.date(2025, 6, 1), date_to=dt.date(2025, 6, 2))
    earlier = EventFactory(date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 1, 2))

    with scopes_disabled():
        events = list(Event.objects.filter(pk__in=[earlier.pk, later.pk]))

    assert events == [earlier, later]


@pytest.mark.django_db
def test_event_shred_deletes_all_related_data(populated_event):
    """shred() deletes the event and all related data including submissions,
    speakers, rooms, slots, questions, answers, reviews, feedback, resources,
    tracks, tags, mail templates, and schedules."""
    event = populated_event
    pk = event.pk

    with scopes_disabled():
        event.shred()

    with scopes_disabled():
        assert not Event.objects.filter(pk=pk).exists()
        assert not Submission.all_objects.filter(event_id=pk).exists()
        assert not TalkSlot.objects.filter(schedule__event_id=pk).exists()
        assert not Feedback.objects.filter(talk__event_id=pk).exists()
        assert not Resource.objects.filter(submission__event_id=pk).exists()
        assert not Answer.objects.filter(question__event_id=pk).exists()
        assert not Question.all_objects.filter(event_id=pk).exists()
        assert not Tag.objects.filter(event_id=pk).exists()
        assert not SpeakerInformation.objects.filter(event_id=pk).exists()
        assert not MailTemplate.objects.filter(event_id=pk).exists()
        assert not Schedule.objects.filter(event_id=pk).exists()


@pytest.mark.django_db
def test_event_copy_data_from_copies_hierarkey_settings(event):
    """copy_data_from copies hierarkey settings from the source event,
    excluding file-based settings."""
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        other_event.settings.custom_value = "test123"

        event.copy_data_from(other_event)

    assert event.settings.custom_value == "test123"


@pytest.mark.django_db
def test_event_copy_data_from_copies_cfp_deadline(event):
    with scopes_disabled():
        other_event = EventFactory(organiser=event.organiser)
        deadline = tz_now() + dt.timedelta(days=30)
        other_event.cfp.deadline = deadline
        other_event.cfp.save()

        event.copy_data_from(other_event)

    with scope(event=event):
        assert event.cfp.deadline == deadline


@pytest.mark.django_db
def test_event_copy_data_from_copies_review_phases_with_date_shift(event):
    """copy_data_from copies review phases from the source event, shifting
    start/end dates by the delta between event date_from values and
    deactivating all phases."""
    with scopes_disabled():
        other_event = EventFactory(
            organiser=event.organiser,
            date_from=dt.date(2025, 1, 1),
            date_to=dt.date(2025, 1, 3),
        )

    delta = event.date_from - other_event.date_from
    with scope(event=other_event):
        other_event.review_phases.all().delete()
        phase_start = tz_now()
        phase_end = tz_now() + dt.timedelta(days=14)
        ReviewPhaseFactory(
            event=other_event,
            name="Source Phase",
            start=phase_start,
            end=phase_end,
            is_active=True,
            position=0,
        )

    with scopes_disabled():
        event.copy_data_from(other_event)

    with scope(event=event):
        phases = list(event.review_phases.all())
        assert len(phases) == 1
        phase = phases[0]
        assert str(phase.name) == "Source Phase"
        assert phase.is_active is False
        assert phase.start == phase_start + delta
        assert phase.end == phase_end + delta


@pytest.mark.django_db
def test_event_talks_deduplicates_shared_speakers(event):
    """When a speaker has multiple slots in the published schedule,
    event.talks and event.speakers contain no duplicates."""
    with scope(event=event):
        speaker = SpeakerFactory(event=event)
        sub1 = SubmissionFactory(event=event)
        sub2 = SubmissionFactory(event=event)
        sub1.speakers.add(speaker)
        sub2.speakers.add(speaker)
        sub1.state = "confirmed"
        sub1.save()
        sub2.state = "confirmed"
        sub2.save()

        room = RoomFactory(event=event)
        TalkSlotFactory(submission=sub1, room=room)
        TalkSlotFactory(
            submission=sub2,
            room=room,
            start=event.datetime_from + dt.timedelta(hours=2),
            end=event.datetime_from + dt.timedelta(hours=3),
        )

    with scopes_disabled():
        event.wip_schedule.freeze(name="v1")

    event = refresh(event)
    with scope(event=event):
        talks = list(event.talks)
        speakers = list(event.speakers)

        assert len(talks) == len(set(talks))
        assert set(talks) == {sub1, sub2}
        assert len(speakers) == len(set(speakers))
        assert speakers == [speaker]
