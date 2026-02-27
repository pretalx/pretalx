import datetime as dt
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog
from pretalx.event.models.event import Event, EventExtraLink
from pretalx.orga.forms.event import (
    ENCRYPTED_PASSWORD_PLACEHOLDER,
    EventExtraLinkForm,
    EventFooterLinkFormset,
    EventForm,
    EventHeaderLinkFormset,
    EventHistoryFilterForm,
    MailSettingsForm,
    ReviewPhaseForm,
    ReviewScoreCategoryForm,
    ReviewSettingsForm,
    WidgetGenerationForm,
    WidgetSettingsForm,
    make_naive,
    strip_zeroes,
)
from pretalx.submission.models import ReviewScore
from tests.factories import (
    ActivityLogFactory,
    EventExtraLinkFactory,
    EventFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("year", "month", "day", "hour", "minute", "second"),
    ((2024, 6, 15, 14, 30, 45), (2024, 1, 1, 0, 0, 0), (2024, 6, 15, 14, 30, 59)),
    ids=("with_seconds", "midnight", "boundary_seconds"),
)
def test_make_naive(year, month, day, hour, minute, second):
    moment = dt.datetime(year, month, day, hour, minute, second, tzinfo=dt.UTC)
    result = make_naive(moment)
    assert result == dt.datetime(year, month, day, hour, minute)  # noqa: DTZ001
    assert result.tzinfo is None
    assert result.second == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (Decimal("3.00"), Decimal("3.")),
        (Decimal("3.10"), Decimal("3.1")),
        (Decimal("3.14"), Decimal("3.14")),
        (Decimal("0.00"), Decimal("0.")),
        ("not_a_decimal", "not_a_decimal"),
        (42, 42),
        (None, None),
    ),
    ids=(
        "trailing_zeroes",
        "one_trailing_zero",
        "no_trailing_zeroes",
        "zero_value",
        "string_passthrough",
        "int_passthrough",
        "none_passthrough",
    ),
)
def test_strip_zeroes(value, expected):
    assert strip_zeroes(value) == expected


def _build_event_form_data(event, **overrides):
    """Build minimal valid form data for EventForm."""
    data = {
        "name_0": str(event.name),
        "slug": event.slug,
        "date_from": str(event.date_from),
        "date_to": str(event.date_to),
        "timezone": event.timezone,
        "email": event.email,
        "locale": event.locale,
        "locales": event.locales,
        "content_locales": event.content_locales,
        "custom_css_text": "",
        "schedule": "grid",
        "show_featured": "pre_schedule",
        "landing_page_text_0": "",
        "featured_sessions_text_0": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_eventform_init_sets_locale_initial():
    with scopes_disabled():
        event = EventFactory()
        event.locale_array = "en,de"
        event.save()
        form = EventForm(instance=event, locales=event.locales)

    assert form.initial["locales"] == ["en", "de"]


@pytest.mark.django_db
def test_eventform_init_sets_content_locale_initial():
    with scopes_disabled():
        event = EventFactory()
        event.content_locale_array = "en,de,fr"
        event.save()
        form = EventForm(instance=event, locales=event.locales)

    assert form.initial["content_locales"] == ["en", "de", "fr"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_administrator", "expected_disabled"),
    ((False, True), (True, False)),
    ids=("non_admin", "admin"),
)
def test_eventform_init_slug_disabled(is_administrator, expected_disabled):
    with scopes_disabled():
        event = EventFactory()
        form = EventForm(
            instance=event, locales=event.locales, is_administrator=is_administrator
        )

    assert form.fields["slug"].disabled is expected_disabled


@pytest.mark.django_db
def test_eventform_init_custom_domain_adjusts_slug_addon():
    with scopes_disabled():
        event = EventFactory(custom_domain="https://custom.example.org")
        form = EventForm(instance=event, locales=event.locales)

    assert form.fields["slug"].widget.addon_before == "https://custom.example.org/"


@pytest.mark.django_db
def test_eventform_init_show_featured_help_text_contains_link():
    with scopes_disabled():
        event = EventFactory()
        form = EventForm(instance=event, locales=event.locales)

    help_text = str(form.fields["show_featured"].help_text)
    assert "<a " in help_text
    assert str(event.urls.featured) in help_text


@pytest.mark.django_db
def test_eventform_init_locale_choices_filter_visible():
    """Locale choices include only visible languages (from LANGUAGES_INFORMATION)."""
    with scopes_disabled():
        event = EventFactory()
        form = EventForm(instance=event, locales=event.locales)

    locale_codes = [code for code, _label in form.fields["locales"].choices]
    for code in locale_codes:
        info = settings.LANGUAGES_INFORMATION.get(code, {})
        assert info.get("visible", True) or code in event.plugin_locales


@pytest.mark.django_db
def test_eventform_init_custom_css_text_empty_when_no_css():
    with scopes_disabled():
        event = EventFactory()
        form = EventForm(instance=event, locales=event.locales)

    assert form.initial["custom_css_text"] == ""


@pytest.mark.django_db
def test_eventform_init_custom_css_text_reads_existing_file():
    with scopes_disabled():
        event = EventFactory()
        event.custom_css.save("test.css", ContentFile(b"body { color: red; }"))
        form = EventForm(instance=event, locales=event.locales)

    assert form.initial["custom_css_text"] == "body { color: red; }"


@pytest.mark.django_db
def test_eventform_clean_date_from_after_date_to_invalid():
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(
            event, date_from="2024-06-20", date_to="2024-06-15"
        )
        form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    assert "date_from" in form.errors


@pytest.mark.django_db
def test_eventform_clean_locale_not_in_active_locales_invalid():
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event, locale="de", locales=["en"])
        form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    assert "locale" in form.errors


@pytest.mark.django_db
def test_eventform_clean_valid_dates():
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event)
        form = EventForm(data=data, instance=event, locales=event.locales)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_eventform_clean_custom_domain_empty_passthrough():
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event, custom_domain="")
        form = EventForm(data=data, instance=event, locales=event.locales)

    form.is_valid()
    assert form.cleaned_data.get("custom_domain") in ("", None)


@pytest.mark.django_db
@override_settings(SITE_URL="https://pretalx.example.com")
def test_eventform_clean_custom_domain_rejects_site_url_hostname():
    """Cannot use the default SITE_URL hostname as a custom domain."""
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event, custom_domain="pretalx.example.com")
        form = EventForm(data=data, instance=event, locales=event.locales)

    with patch("pretalx.orga.forms.event.socket.gethostbyname"):
        valid = form.is_valid()

    assert not valid
    assert "custom_domain" in form.errors


@pytest.mark.django_db
@override_settings(SITE_URL="https://pretalx.example.com")
def test_eventform_clean_custom_domain_rejects_full_site_url():
    """Cannot use the full SITE_URL as a custom domain."""
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(
            event, custom_domain="https://pretalx.example.com"
        )
        form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    assert "custom_domain" in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("domain", "expected"),
    (
        ("custom.example.org", "https://custom.example.org"),
        ("http://custom.example.org", "https://custom.example.org"),
        ("https://custom.example.org", "https://custom.example.org"),
        ("https://custom.example.org/", "https://custom.example.org"),
    ),
    ids=("bare_domain", "http_prefix", "https_prefix", "trailing_slash"),
)
def test_eventform_clean_custom_domain_normalizes(domain, expected):
    """Domains are normalized to https:// without trailing slash."""
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event, custom_domain=domain)
        form = EventForm(data=data, instance=event, locales=event.locales)

    with patch("pretalx.orga.forms.event.socket.gethostbyname"):
        form.is_valid()

    assert form.cleaned_data["custom_domain"] == expected


@pytest.mark.django_db
def test_eventform_clean_custom_domain_dns_failure():
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event, custom_domain="nodns.example.org")
        form = EventForm(data=data, instance=event, locales=event.locales)

    with patch(
        "pretalx.orga.forms.event.socket.gethostbyname", side_effect=OSError("nope")
    ):
        valid = form.is_valid()

    assert not valid
    assert "custom_domain" in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("css_text", "is_admin", "expected_valid"),
    (
        ("body { color: red; }", False, True),
        ("body { position: fixed; }", False, False),
        ("body { position: fixed; }", True, True),
        ("", False, True),
    ),
    ids=("valid_non_admin", "malicious_non_admin", "malicious_admin_bypass", "empty"),
)
def test_eventform_clean_custom_css_text(css_text, is_admin, expected_valid):
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event, custom_css_text=css_text)
        form = EventForm(
            data=data, instance=event, locales=event.locales, is_administrator=is_admin
        )

    assert form.is_valid() == expected_valid, form.errors
    if not expected_valid:
        assert "custom_css_text" in form.errors


@pytest.mark.django_db
def test_eventform_clean_custom_css_clears_when_no_file():
    """When no custom_css file exists and none is uploaded, custom_css stays empty."""
    with scopes_disabled():
        event = EventFactory()
        assert not event.custom_css
        data = _build_event_form_data(event)
        form = EventForm(data=data, instance=event, locales=event.locales)
        form.is_valid()

    event.refresh_from_db()
    assert not event.custom_css


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("css_content", "expected_valid"),
    ((b"body { color: red; }", True), (b"body { position: fixed; }", False)),
    ids=("valid_css", "malicious_css"),
)
def test_eventform_clean_custom_css_file(css_content, expected_valid):
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event)
        css_file = SimpleUploadedFile("style.css", css_content, content_type="text/css")
        files = {"custom_css": css_file}
        form = EventForm(data=data, files=files, instance=event, locales=event.locales)

    assert form.is_valid() == expected_valid, form.errors
    if expected_valid:
        assert form.cleaned_data["custom_css"] is not None
    else:
        assert "custom_css" in form.errors


@pytest.mark.django_db
def test_eventform_clean_custom_css_file_admin_bypass():
    """Admin users can upload CSS with any properties."""
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event)
        css_content = b"body { position: fixed; }"
        css_file = SimpleUploadedFile("admin.css", css_content, content_type="text/css")
        files = {"custom_css": css_file}
        form = EventForm(
            data=data,
            files=files,
            instance=event,
            locales=event.locales,
            is_administrator=True,
        )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["custom_css"] is not None


@pytest.mark.django_db
def test_eventform_save_updates_locale_array():
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event, locales=["en", "de"])
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

    event.refresh_from_db()
    assert event.locale_array == "en,de"


@pytest.mark.django_db
def test_eventform_save_updates_content_locale_array():
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event, content_locales=["en", "de"])
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

    event.refresh_from_db()
    assert event.content_locale_array == "en,de"


@pytest.mark.django_db
def test_eventform_save_custom_css_text():
    with scopes_disabled():
        event = EventFactory()
        css = "body { color: green; }"
        data = _build_event_form_data(event, custom_css_text=css)
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

    event.refresh_from_db()
    assert event.custom_css.read().decode() == css


@pytest.mark.django_db
def test_eventform_save_processes_image_on_change(make_image):
    """When an image field changes, the image is processed to WebP format."""
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event)
        files = {"logo": make_image("logo.png")}
        form = EventForm(data=data, files=files, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

    event.refresh_from_db()
    assert event.logo
    assert event.logo.name.endswith(".webp")


@pytest.mark.django_db
def test_eventform_change_dates_moves_slots():
    """When event dates change, scheduled talks are moved by the delta."""
    with scopes_disabled():
        event = EventFactory(
            date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12)
        )
        wip = event.wip_schedule
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=sub, schedule=wip)
        original_start = slot.start

        data = _build_event_form_data(
            event, date_from="2024-06-11", date_to="2024-06-13"
        )
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

        slot.refresh_from_db()

    assert slot.start == original_start + dt.timedelta(days=1)


@pytest.mark.django_db
def test_eventform_change_dates_does_not_move_published_slots():
    """When event dates move, only WIP schedule slots are moved — published
    slots on released schedules stay at their original times."""
    with scopes_disabled():
        event = EventFactory(
            date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12)
        )
        sub = SubmissionFactory(event=event)

        # Create a published slot on a released (versioned) schedule
        released = ScheduleFactory(event=event, version="v1")
        published_slot = TalkSlotFactory(submission=sub, schedule=released)
        published_original_start = published_slot.start

        # Create the corresponding WIP slot
        wip = event.wip_schedule
        wip_slot = TalkSlotFactory(submission=sub, schedule=wip)
        wip_original_start = wip_slot.start

        data = _build_event_form_data(
            event, date_from="2024-06-11", date_to="2024-06-13"
        )
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

        published_slot.refresh_from_db()
        wip_slot.refresh_from_db()

    assert published_slot.start == published_original_start
    assert wip_slot.start == wip_original_start + dt.timedelta(days=1)


@pytest.mark.django_db
def test_eventform_change_dates_shortening_deschedules_outside_talks():
    """When the event is shortened, talks outside the new range are descheduled."""
    with scopes_disabled():
        event = EventFactory(
            date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 14)
        )
        wip = event.wip_schedule
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(
            submission=sub,
            schedule=wip,
            start=dt.datetime(2024, 6, 14, 10, 0, tzinfo=dt.UTC),
            end=dt.datetime(2024, 6, 14, 11, 0, tzinfo=dt.UTC),
        )

        data = _build_event_form_data(
            event, date_from="2024-06-10", date_to="2024-06-12"
        )
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

        slot.refresh_from_db()

    assert slot.start is None
    assert slot.end is None
    assert slot.room is None


@pytest.mark.django_db
def test_eventform_change_dates_no_slots_does_nothing():
    """When there are no scheduled slots, date changes don't error."""
    with scopes_disabled():
        event = EventFactory(
            date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12)
        )
        data = _build_event_form_data(
            event, date_from="2024-06-11", date_to="2024-06-13"
        )
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

    event.refresh_from_db()
    assert event.date_from == dt.date(2024, 6, 11)


@pytest.mark.django_db
def test_eventform_change_dates_extending_end_does_not_move_slots():
    """When only date_to is extended (event gets longer), slots stay put."""
    with scopes_disabled():
        event = EventFactory(
            date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12)
        )
        wip = event.wip_schedule
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(submission=sub, schedule=wip)
        original_start = slot.start

        data = _build_event_form_data(event, date_to="2024-06-14")
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

        slot.refresh_from_db()

    assert slot.start == original_start


@pytest.mark.django_db
def test_eventform_change_timezone_adjusts_slots():
    """Changing timezone adjusts slot times to preserve apparent local time.

    A slot at 10:00 UTC should become 08:00 UTC when the event switches to
    Europe/Berlin (UTC+2 in June), so that it still appears as 10:00 local."""
    with scopes_disabled():
        event = EventFactory(
            date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12), timezone="UTC"
        )
        wip = event.wip_schedule
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(
            submission=sub,
            schedule=wip,
            start=dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC),
            end=dt.datetime(2024, 6, 10, 11, 0, tzinfo=dt.UTC),
        )
        # Re-fetch to clear cached_property (tz), as production views do
        event = Event.objects.get(pk=event.pk)

        data = _build_event_form_data(event, timezone="Europe/Berlin")
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

        slot.refresh_from_db()

    assert slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)


@pytest.mark.django_db
def test_eventform_change_timezone_no_slots_does_nothing():
    """When no scheduled slots exist, changing timezone completes without error."""
    with scopes_disabled():
        event = EventFactory(timezone="UTC")
        event = Event.objects.get(pk=event.pk)

        data = _build_event_form_data(event, timezone="Europe/Berlin")
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

    event.refresh_from_db()
    assert event.timezone == "Europe/Berlin"


@pytest.mark.django_db
def test_eventform_change_timezone_same_offset_does_not_move():
    """Changing timezone to one with the same UTC offset leaves slots unchanged."""
    with scopes_disabled():
        event = EventFactory(
            date_from=dt.date(2024, 6, 10),
            date_to=dt.date(2024, 6, 12),
            timezone="Europe/Berlin",
        )
        wip = event.wip_schedule
        sub = SubmissionFactory(event=event)
        slot = TalkSlotFactory(
            submission=sub,
            schedule=wip,
            start=dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC),
            end=dt.datetime(2024, 6, 10, 9, 0, tzinfo=dt.UTC),
        )
        event = Event.objects.get(pk=event.pk)

        data = _build_event_form_data(event, timezone="Europe/Paris")
        form = EventForm(data=data, instance=event, locales=event.locales)
        assert form.is_valid(), form.errors
        form.save()

        slot.refresh_from_db()

    assert slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)


@pytest.mark.django_db
def test_eventform_read_only_rejects_changes():
    with scopes_disabled():
        event = EventFactory()
        data = _build_event_form_data(event)
        form = EventForm(
            data=data, instance=event, locales=event.locales, read_only=True
        )

    assert not form.is_valid()


@pytest.mark.django_db
def test_eventform_read_only_disables_all_fields():
    with scopes_disabled():
        event = EventFactory()
        form = EventForm(instance=event, locales=event.locales, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def _build_mail_form_data(**overrides):
    data = {
        "reply_to": "",
        "subject_prefix": "",
        "signature": "",
        "smtp_use_custom": "",
        "mail_from": "",
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_username": "",
        "smtp_password": "",
        "smtp_use_tls": "",
        "smtp_use_ssl": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_mailsettingsform_valid_without_custom_smtp():
    with scopes_disabled():
        event = EventFactory()
        data = _build_mail_form_data()
        form = MailSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_mailsettingsform_custom_smtp_requires_mail_from():
    with scopes_disabled():
        event = EventFactory()
        data = _build_mail_form_data(
            smtp_use_custom=True, smtp_host="localhost", smtp_port="587"
        )
        form = MailSettingsForm(data=data, obj=event)

    assert not form.is_valid()
    assert "mail_from" in form.errors


@pytest.mark.django_db
def test_mailsettingsform_custom_smtp_tls_and_ssl_conflict():
    with scopes_disabled():
        event = EventFactory()
        data = _build_mail_form_data(
            smtp_use_custom=True,
            mail_from="sender@example.com",
            smtp_host="mail.example.com",
            smtp_port="587",
            smtp_use_tls=True,
            smtp_use_ssl=True,
        )
        form = MailSettingsForm(data=data, obj=event)

    assert not form.is_valid()
    assert "smtp_use_tls" in form.errors


@pytest.mark.django_db
def test_mailsettingsform_custom_smtp_non_local_requires_encryption():
    with scopes_disabled():
        event = EventFactory()
        data = _build_mail_form_data(
            smtp_use_custom=True,
            mail_from="sender@example.com",
            smtp_host="mail.remote.org",
            smtp_port="587",
        )
        form = MailSettingsForm(data=data, obj=event)

    assert not form.is_valid()
    assert "smtp_host" in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    "host",
    ("localhost", "127.0.0.1", "::1", "[::1]", "localhost.localdomain"),
    ids=("localhost", "ipv4_loopback", "ipv6_loopback", "ipv6_bracket", "fqdn"),
)
def test_mailsettingsform_custom_smtp_localhost_no_encryption_ok(host):
    with scopes_disabled():
        event = EventFactory()
        data = _build_mail_form_data(
            smtp_use_custom=True,
            mail_from="sender@example.com",
            smtp_host=host,
            smtp_port="587",
        )
        form = MailSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("use_tls", "use_ssl", "port"),
    ((True, False, "587"), (False, True, "465")),
    ids=("tls", "ssl"),
)
def test_mailsettingsform_custom_smtp_with_encryption_valid(use_tls, use_ssl, port):
    with scopes_disabled():
        event = EventFactory()
        data = _build_mail_form_data(
            smtp_use_custom=True,
            mail_from="sender@example.com",
            smtp_host="mail.remote.org",
            smtp_port=port,
            smtp_use_tls=use_tls,
            smtp_use_ssl=use_ssl,
        )
        form = MailSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_mailsettingsform_password_placeholder_on_existing():
    """When there's an existing password, the field shows the placeholder."""
    with scopes_disabled():
        event = EventFactory()
        event.mail_settings["smtp_password"] = "s3cret"
        event.save()
        form = MailSettingsForm(obj=event)

    assert form.fields["smtp_password"].initial == ENCRYPTED_PASSWORD_PLACEHOLDER


@pytest.mark.django_db
def test_mailsettingsform_password_preserved_when_placeholder_submitted():
    """When the placeholder is submitted, the original password is preserved
    via self.initial (as the view would provide)."""
    with scopes_disabled():
        event = EventFactory()
        event.mail_settings["smtp_password"] = "s3cret"
        event.save()
        data = _build_mail_form_data(
            smtp_use_custom=True,
            mail_from="sender@example.com",
            smtp_host="localhost",
            smtp_port="587",
            smtp_username="user",
            smtp_password=ENCRYPTED_PASSWORD_PLACEHOLDER,
        )
        form = MailSettingsForm(
            data=data, obj=event, initial={"smtp_password": "s3cret"}
        )
        form.is_valid()

    assert form.cleaned_data["smtp_password"] == "s3cret"


@pytest.mark.django_db
def test_mailsettingsform_password_preserved_when_empty_with_username():
    """When password is empty but username is set, the original password is preserved
    via self.initial."""
    with scopes_disabled():
        event = EventFactory()
        event.mail_settings["smtp_password"] = "s3cret"
        event.save()
        data = _build_mail_form_data(
            smtp_use_custom=True,
            mail_from="sender@example.com",
            smtp_host="localhost",
            smtp_port="587",
            smtp_username="user",
            smtp_password="",
        )
        form = MailSettingsForm(
            data=data, obj=event, initial={"smtp_password": "s3cret"}
        )
        form.is_valid()

    assert form.cleaned_data["smtp_password"] == "s3cret"


@pytest.mark.django_db
def test_mailsettingsform_password_placeholder_without_username_passes_through():
    """When no username is set, the password preservation logic is skipped
    entirely — the placeholder string goes through as-is."""
    with scopes_disabled():
        event = EventFactory()
        event.mail_settings["smtp_password"] = "s3cret"
        event.save()
        data = _build_mail_form_data(
            smtp_use_custom=True,
            mail_from="sender@example.com",
            smtp_host="localhost",
            smtp_port="587",
            smtp_username="",
            smtp_password=ENCRYPTED_PASSWORD_PLACEHOLDER,
        )
        form = MailSettingsForm(data=data, obj=event)
        form.is_valid()

    assert form.cleaned_data["smtp_password"] == ENCRYPTED_PASSWORD_PLACEHOLDER


@pytest.mark.django_db
def test_mailsettingsform_new_password_with_username_accepted():
    """When a real new password is provided with a username, it passes through unchanged."""
    with scopes_disabled():
        event = EventFactory()
        data = _build_mail_form_data(
            smtp_use_custom=True,
            mail_from="sender@example.com",
            smtp_host="localhost",
            smtp_port="587",
            smtp_username="user",
            smtp_password="newRealP4ss!",
        )
        form = MailSettingsForm(
            data=data, obj=event, initial={"smtp_password": "oldpass"}
        )
        form.is_valid()

    assert form.cleaned_data["smtp_password"] == "newRealP4ss!"


@pytest.mark.django_db
def test_mailsettingsform_read_only_disables_fields():
    with scopes_disabled():
        event = EventFactory()
        form = MailSettingsForm(obj=event, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


@pytest.mark.django_db
def test_reviewsettingsform_valid_defaults():
    with scopes_disabled():
        event = EventFactory()
        data = {
            "score_mandatory": False,
            "text_mandatory": False,
            "score_format": "words_numbers",
            "aggregate_method": "median",
            "review_help_text_0": "",
            "use_submission_comments": True,
        }
        form = ReviewSettingsForm(data=data, obj=event, initial={})

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_reviewsettingsform_all_score_formats():
    with scopes_disabled():
        event = EventFactory()
        for fmt in ("words_numbers", "numbers_words", "numbers", "words"):
            data = {
                "score_mandatory": False,
                "text_mandatory": False,
                "score_format": fmt,
                "aggregate_method": "median",
                "review_help_text_0": "",
                "use_submission_comments": True,
            }
            form = ReviewSettingsForm(data=data, obj=event, initial={})
            assert form.is_valid(), f"Format {fmt} failed: {form.errors}"


@pytest.mark.django_db
def test_widgetsettingsform_valid():
    with scopes_disabled():
        event = EventFactory()
        data = {"show_widget_if_not_public": True}
        form = WidgetSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_widgetsettingsform_unchecked():
    with scopes_disabled():
        event = EventFactory()
        data = {}
        form = WidgetSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_widgetgenerationform_init_sets_day_choices():
    with scopes_disabled():
        event = EventFactory(
            date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12)
        )
        form = WidgetGenerationForm(instance=event)

    days = [choice[0] for choice in form.fields["days"].choices]
    assert len(days) == 3
    assert days[0] == dt.date(2024, 6, 10)
    assert days[-1] == dt.date(2024, 6, 12)


@pytest.mark.django_db
def test_widgetgenerationform_init_sets_room_queryset():
    with scopes_disabled():
        event = EventFactory()
        room1 = RoomFactory(event=event)
        room2 = RoomFactory(event=event)
        form = WidgetGenerationForm(instance=event)

    assert set(form.fields["rooms"].queryset) == {room1, room2}


@pytest.mark.django_db
def test_widgetgenerationform_init_room_queryset_excludes_other_events():
    with scopes_disabled():
        event = EventFactory()
        RoomFactory(event=event)
        other_event = EventFactory()
        other_room = RoomFactory(event=other_event)
        form = WidgetGenerationForm(instance=event)

    assert other_room not in form.fields["rooms"].queryset


@pytest.mark.django_db
def test_widgetgenerationform_init_locale_label():
    with scopes_disabled():
        event = EventFactory()
        form = WidgetGenerationForm(instance=event)

    assert "language" in str(form.fields["locale"].label).lower()


@pytest.mark.django_db
def test_reviewphaseform_valid_data():
    with scopes_disabled():
        event = EventFactory()
        data = {
            "name": "Phase 1",
            "start": "",
            "end": "",
            "can_review": True,
            "proposal_visibility": "all",
            "can_see_speaker_names": True,
            "can_see_reviewer_names": True,
            "can_change_submission_state": False,
            "can_see_other_reviews": "always",
            "can_tag_submissions": "never",
            "speakers_can_change_submissions": False,
        }
        form = ReviewPhaseForm(data=data, event=event, locales=event.locales)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_reviewphaseform_start_after_end_invalid():
    with scopes_disabled():
        event = EventFactory()
        data = {
            "name": "Phase 1",
            "start": "2024-06-20 10:00",
            "end": "2024-06-15 10:00",
            "can_review": True,
            "proposal_visibility": "all",
            "can_see_speaker_names": True,
            "can_see_reviewer_names": True,
            "can_change_submission_state": False,
            "can_see_other_reviews": "always",
            "can_tag_submissions": "never",
            "speakers_can_change_submissions": False,
        }
        form = ReviewPhaseForm(data=data, event=event, locales=event.locales)

    assert not form.is_valid()
    assert "end" in form.errors


@pytest.mark.django_db
def test_reviewphaseform_speakers_edit_disabled_when_event_flag_off():
    """When event-level speaker editing is disabled, the form field is disabled."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["speakers_can_edit_submissions"] = False
        event.save()
        form = ReviewPhaseForm(event=event, locales=event.locales)

    assert form.fields["speakers_can_change_submissions"].disabled is True
    assert form.fields["speakers_can_change_submissions"].initial is False


@pytest.mark.django_db
def test_reviewphaseform_speakers_edit_enabled_when_event_flag_on():
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["speakers_can_edit_submissions"] = True
        event.save()
        form = ReviewPhaseForm(event=event, locales=event.locales)

    assert form.fields["speakers_can_change_submissions"].disabled is False


@pytest.mark.django_db
def test_reviewscorecategoryform_init_no_tracks():
    """When use_tracks is disabled, limit_tracks field is removed."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = False
        event.save()
        category = ReviewScoreCategoryFactory(event=event)
        form = ReviewScoreCategoryForm(
            data={}, instance=category, event=event, locales=event.locales, prefix="cat"
        )

    assert "limit_tracks" not in form.fields


@pytest.mark.django_db
def test_reviewscorecategoryform_init_with_tracks():
    """When use_tracks is enabled, limit_tracks shows event's tracks."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = True
        event.save()
        track = TrackFactory(event=event)
        other_event_track = TrackFactory()
        category = ReviewScoreCategoryFactory(event=event)
        form = ReviewScoreCategoryForm(
            data={}, instance=category, event=event, locales=event.locales, prefix="cat"
        )

    assert "limit_tracks" in form.fields
    assert track in form.fields["limit_tracks"].queryset
    assert other_event_track not in form.fields["limit_tracks"].queryset


@pytest.mark.django_db
def test_reviewscorecategoryform_init_loads_existing_scores():
    with scopes_disabled():
        event = EventFactory()
        category = ReviewScoreCategoryFactory(event=event)
        score = ReviewScoreFactory(category=category, value=3, label="Good")
        form = ReviewScoreCategoryForm(
            data={}, instance=category, event=event, locales=event.locales, prefix="cat"
        )

    assert f"value_{score.id}" in form.fields
    assert f"label_{score.id}" in form.fields


@pytest.mark.django_db
def test_reviewscorecategoryform_init_new_instance():
    """A new (unsaved) ReviewScoreCategory has no label_fields."""
    with scopes_disabled():
        event = EventFactory()
        form = ReviewScoreCategoryForm(
            data={}, event=event, locales=event.locales, prefix="cat"
        )

    assert form.label_fields == []


@pytest.mark.django_db
def test_reviewscorecategoryform_get_label_fields():
    with scopes_disabled():
        event = EventFactory()
        category = ReviewScoreCategoryFactory(event=event)
        ReviewScoreFactory(category=category, value=1, label="Bad")
        ReviewScoreFactory(category=category, value=3, label="Good")
        form = ReviewScoreCategoryForm(
            data={}, instance=category, event=event, locales=event.locales, prefix="cat"
        )

    label_pairs = list(form.get_label_fields())
    assert len(label_pairs) == 2


@pytest.mark.django_db
def test_reviewscorecategoryform_save_creates_new_scores():
    with scopes_disabled():
        event = EventFactory()
        category = ReviewScoreCategoryFactory(event=event)
        prefix = "cat"
        data = {
            f"{prefix}-name_0": "Updated",
            f"{prefix}-is_independent": False,
            f"{prefix}-weight": "1.0",
            f"{prefix}-required": True,
            f"{prefix}-active": True,
            f"{prefix}-new_scores": "new1",
            f"{prefix}-value_new1": "5",
            f"{prefix}-label_new1": "Excellent",
        }
        form = ReviewScoreCategoryForm(
            data=data,
            instance=category,
            event=event,
            locales=event.locales,
            prefix=prefix,
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        scores = list(category.scores.all())
    assert len(scores) == 1
    assert scores[0].value == Decimal(5)
    assert scores[0].label == "Excellent"


@pytest.mark.django_db
def test_reviewscorecategoryform_save_deletes_score_when_value_cleared():
    with scopes_disabled():
        event = EventFactory()
        category = ReviewScoreCategoryFactory(event=event)
        score = ReviewScoreFactory(category=category, value=3, label="Good")
        prefix = "cat"
        data = {
            f"{prefix}-name_0": "Updated",
            f"{prefix}-is_independent": False,
            f"{prefix}-weight": "1.0",
            f"{prefix}-required": True,
            f"{prefix}-active": True,
            f"{prefix}-new_scores": "",
            f"{prefix}-value_{score.id}": "",
            f"{prefix}-label_{score.id}": "Good",
        }
        form = ReviewScoreCategoryForm(
            data=data,
            instance=category,
            event=event,
            locales=event.locales,
            prefix=prefix,
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        assert not ReviewScore.objects.filter(id=score.id).exists()


@pytest.mark.django_db
def test_reviewscorecategoryform_save_updates_existing_score():
    with scopes_disabled():
        event = EventFactory()
        category = ReviewScoreCategoryFactory(event=event)
        score = ReviewScoreFactory(category=category, value=3, label="Good")
        prefix = "cat"
        data = {
            f"{prefix}-name_0": "Updated",
            f"{prefix}-is_independent": False,
            f"{prefix}-weight": "1.0",
            f"{prefix}-required": True,
            f"{prefix}-active": True,
            f"{prefix}-new_scores": "",
            f"{prefix}-value_{score.id}": "4",
            f"{prefix}-label_{score.id}": "Great",
        }
        form = ReviewScoreCategoryForm(
            data=data,
            instance=category,
            event=event,
            locales=event.locales,
            prefix=prefix,
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        score.refresh_from_db()
    assert score.value == Decimal(4)
    assert score.label == "Great"


@pytest.mark.django_db
def test_reviewscorecategoryform_save_unchanged_scores_preserved():
    """Saving a form without changing score data preserves existing scores."""
    with scopes_disabled():
        event = EventFactory()
        category = ReviewScoreCategoryFactory(event=event)
        score = ReviewScoreFactory(category=category, value=3, label="Good")
        prefix = "cat"
        data = {
            f"{prefix}-name_0": str(category.name),
            f"{prefix}-is_independent": False,
            f"{prefix}-weight": "1.0",
            f"{prefix}-required": True,
            f"{prefix}-active": True,
            f"{prefix}-new_scores": "",
            f"{prefix}-value_{score.id}": "3",
            f"{prefix}-label_{score.id}": "Good",
        }
        form = ReviewScoreCategoryForm(
            data=data,
            instance=category,
            event=event,
            locales=event.locales,
            prefix=prefix,
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        score.refresh_from_db()
    assert score.value == Decimal(3)
    assert score.label == "Good"


@pytest.mark.django_db
def test_reviewscorecategoryform_save_new_score_without_label_skipped():
    """A new score with a value but no label is silently skipped."""
    with scopes_disabled():
        event = EventFactory()
        category = ReviewScoreCategoryFactory(event=event)
        prefix = "cat"
        data = {
            f"{prefix}-name_0": "Updated",
            f"{prefix}-is_independent": False,
            f"{prefix}-weight": "1.0",
            f"{prefix}-required": True,
            f"{prefix}-active": True,
            f"{prefix}-new_scores": "new1",
            f"{prefix}-value_new1": "5",
            f"{prefix}-label_new1": "",
        }
        form = ReviewScoreCategoryForm(
            data=data,
            instance=category,
            event=event,
            locales=event.locales,
            prefix=prefix,
        )
        assert form.is_valid(), form.errors
        form.save()

    with scopes_disabled():
        assert category.scores.count() == 0


@pytest.mark.django_db
def test_eventextralinkform_valid():
    with scopes_disabled():
        event = EventFactory()
        data = {"label_0": "Example", "url": "https://example.com"}
        form = EventExtraLinkForm(data=data, locales=event.locales)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_eventextralinkform_requires_url():
    with scopes_disabled():
        event = EventFactory()
        data = {"label_0": "Example", "url": ""}
        form = EventExtraLinkForm(data=data, locales=event.locales)

    assert not form.is_valid()
    assert "url" in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("formset_cls", "expected_role"),
    ((EventFooterLinkFormset, "footer"), (EventHeaderLinkFormset, "header")),
    ids=("footer", "header"),
)
def test_baseeventextralinkformset_filters_by_role(formset_cls, expected_role):
    with scopes_disabled():
        event = EventFactory()
        expected_link = EventExtraLinkFactory(event=event, role=expected_role)
        other_role = "header" if expected_role == "footer" else "footer"
        EventExtraLinkFactory(event=event, role=other_role)
        formset = formset_cls(instance=event, event=event)

    assert list(formset.get_queryset()) == [expected_link]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("formset_cls", "expected_role", "label"),
    (
        (EventFooterLinkFormset, "footer", "New Footer"),
        (EventHeaderLinkFormset, "header", "New Header"),
    ),
    ids=("footer", "header"),
)
def test_baseeventextralinkformset_save_new_sets_role(
    formset_cls, expected_role, label
):
    with scopes_disabled():
        event = EventFactory()
        data = {
            "extra_links-TOTAL_FORMS": "1",
            "extra_links-INITIAL_FORMS": "0",
            "extra_links-MIN_NUM_FORMS": "0",
            "extra_links-MAX_NUM_FORMS": "1000",
            "extra_links-0-label_0": label,
            "extra_links-0-url": "https://example.com/new",
            "extra_links-0-id": "",
        }
        formset = formset_cls(data=data, instance=event, event=event)
        assert formset.is_valid(), formset.errors
        formset.save()

    with scopes_disabled():
        links = list(EventExtraLink.objects.filter(event=event))
    assert len(links) == 1
    assert links[0].role == expected_role


@pytest.mark.django_db
def test_baseeventextralinkformset_uses_event_locales():
    with scopes_disabled():
        event = EventFactory()
        event.locale_array = "en,de"
        event.save()
        formset = EventFooterLinkFormset(instance=event, event=event)

    assert formset.locales == event.locales


@pytest.mark.django_db
def test_baseeventextralinkformset_init_without_event():
    """Formset can be created without passing event."""
    with scopes_disabled():
        event = EventFactory()
        formset = EventFooterLinkFormset(instance=event)

    assert formset.forms is not None


@pytest.mark.django_db
def test_baseeventextralinkformset_get_queryset_cached():
    """Calling get_queryset twice returns the same cached queryset."""
    with scopes_disabled():
        event = EventFactory()
        formset = EventFooterLinkFormset(instance=event, event=event)
        qs1 = formset.get_queryset()
        qs2 = formset.get_queryset()

    assert qs1 is qs2


@pytest.mark.django_db
def test_baseeventextralinkformset_save_new_commit_false():
    """save_new with commit=False returns an unsaved instance with role set."""
    with scopes_disabled():
        event = EventFactory()
        data = {
            "extra_links-TOTAL_FORMS": "1",
            "extra_links-INITIAL_FORMS": "0",
            "extra_links-MIN_NUM_FORMS": "0",
            "extra_links-MAX_NUM_FORMS": "1000",
            "extra_links-0-label_0": "Test",
            "extra_links-0-url": "https://example.com",
            "extra_links-0-id": "",
        }
        formset = EventFooterLinkFormset(data=data, instance=event, event=event)
        assert formset.is_valid(), formset.errors
        new_form = formset.forms[0]
        instance = formset.save_new(new_form, commit=False)

    assert instance.role == "footer"
    assert instance.pk is None


@pytest.mark.django_db
def test_eventhistoryfilterform_init_without_event():
    form = EventHistoryFilterForm()
    assert "object_type" in form.fields
    assert "action_type" in form.fields


@pytest.mark.django_db
def test_eventhistoryfilterform_object_type_choices_from_logs():
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        ActivityLogFactory(event=event, content_object=sub)

        form = EventHistoryFilterForm(event=event)

    choices = dict(form.fields["object_type"].choices)
    # The empty "All object types" option should be there
    assert "" in choices
    # Should contain the content type for Submission
    ct = ContentType.objects.get_for_model(sub)
    assert ct.id in choices


@pytest.mark.django_db
def test_eventhistoryfilterform_object_type_excludes_unrelated_events():
    with scopes_disabled():
        event = EventFactory()
        other_event = EventFactory()
        other_sub = SubmissionFactory(event=other_event)
        ActivityLogFactory(event=other_event, content_object=other_sub)

        form = EventHistoryFilterForm(event=event)

    ct = ContentType.objects.get_for_model(other_sub)
    choice_ids = [c[0] for c in form.fields["object_type"].choices]
    assert ct.id not in choice_ids


@pytest.mark.django_db
def test_eventhistoryfilterform_action_type_choices_from_logs():
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.submission.create"
        )

        form = EventHistoryFilterForm(event=event)

    # Flatten grouped choices to find action types
    all_actions = set()
    for choice in form.fields["action_type"].choices:
        if isinstance(choice[1], list):
            for action_type, _label in choice[1]:
                all_actions.add(action_type)
        else:
            all_actions.add(choice[0])
    assert "pretalx.submission.create" in all_actions


@pytest.mark.django_db
def test_eventhistoryfilterform_ungrouped_action_added_to_other():
    """Action types not in ACTION_TYPE_GROUPS appear under 'Other'."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.custom.action"
        )
        ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.another.custom"
        )

        form = EventHistoryFilterForm(event=event)

    # Find all ungrouped actions in the "Other" group
    other_actions = []
    for choice in form.fields["action_type"].choices:
        if isinstance(choice[1], list):
            other_actions.extend(action_type for action_type, _label in choice[1])
    assert "pretalx.custom.action" in other_actions
    assert "pretalx.another.custom" in other_actions


@pytest.mark.django_db
def test_eventhistoryfilterform_filter_queryset_by_object_type():
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        log = ActivityLogFactory(event=event, content_object=sub)
        ct = ContentType.objects.get_for_model(sub)

        data = {"object_type": str(ct.id), "action_type": ""}
        form = EventHistoryFilterForm(data=data, event=event)
        assert form.is_valid(), form.errors
        qs = form.filter_queryset(ActivityLog.objects.filter(event=event))

    assert list(qs) == [log]


@pytest.mark.django_db
def test_eventhistoryfilterform_filter_queryset_by_action_type():
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        log_create = ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.submission.create"
        )
        ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.submission.update"
        )

        data = {"object_type": "", "action_type": "pretalx.submission.create"}
        form = EventHistoryFilterForm(data=data, event=event)
        assert form.is_valid(), form.errors
        qs = form.filter_queryset(ActivityLog.objects.filter(event=event))

    assert list(qs) == [log_create]


@pytest.mark.django_db
def test_eventhistoryfilterform_filter_queryset_empty_filters_returns_all():
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        log1 = ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.submission.create"
        )
        log2 = ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.submission.update"
        )

        data = {"object_type": "", "action_type": ""}
        form = EventHistoryFilterForm(data=data, event=event)
        assert form.is_valid(), form.errors
        qs = form.filter_queryset(ActivityLog.objects.filter(event=event))

    assert set(qs) == {log1, log2}


@pytest.mark.django_db
def test_eventhistoryfilterform_filter_queryset_by_both_type_and_action():
    """Applying both object_type and action_type filters narrows results."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        room = RoomFactory(event=event)
        sub_ct = ContentType.objects.get_for_model(sub)
        log_match = ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.submission.create"
        )
        ActivityLogFactory(
            event=event, content_object=sub, action_type="pretalx.submission.update"
        )
        ActivityLogFactory(
            event=event, content_object=room, action_type="pretalx.room.create"
        )

        data = {
            "object_type": str(sub_ct.id),
            "action_type": "pretalx.submission.create",
        }
        form = EventHistoryFilterForm(data=data, event=event)
        assert form.is_valid(), form.errors
        qs = form.filter_queryset(ActivityLog.objects.filter(event=event))

    assert list(qs) == [log_match]
