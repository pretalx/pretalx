# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from pretalx.common.signals import register_fonts
from pretalx.event.interfaces.forms import (
    EventExtraLinkForm,
    EventFooterLinkFormset,
    EventForm,
    EventHeaderLinkFormset,
    EventWizardBasicsForm,
    EventWizardDisplayForm,
    EventWizardInitialForm,
    EventWizardPluginForm,
    EventWizardTimelineForm,
)
from pretalx.event.models import Event
from pretalx.event.models.event import EventExtraLink
from pretalx.orga.forms.widgets import FontSelect
from tests.factories import (
    EventExtraLinkFactory,
    EventFactory,
    OrganiserFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_event_wizard_initial_form_admin_sees_all_organisers():
    admin = UserFactory(is_administrator=True)
    org1 = OrganiserFactory()
    org2 = OrganiserFactory()

    form = EventWizardInitialForm(user=admin)

    assert set(form.fields["organiser"].queryset) == {org1, org2}


def test_event_wizard_initial_form_non_admin_sees_permitted_organisers():
    """Non-admin users only see organisers where they have
    can_create_events permission via a team."""
    user = UserFactory()
    org_permitted = OrganiserFactory()
    OrganiserFactory()  # org without permission, should not appear
    team = TeamFactory(organiser=org_permitted, can_create_events=True)
    team.members.add(user)

    form = EventWizardInitialForm(user=user)

    assert list(form.fields["organiser"].queryset) == [org_permitted]


def test_event_wizard_initial_form_non_admin_without_teams_sees_empty():
    user = UserFactory()
    OrganiserFactory()

    form = EventWizardInitialForm(user=user)

    assert list(form.fields["organiser"].queryset) == []


def test_event_wizard_initial_form_locales_field_uses_settings_languages():
    admin = UserFactory(is_administrator=True)
    form = EventWizardInitialForm(user=admin)

    assert form.fields["locales"].choices == settings.LANGUAGES


def test_event_wizard_initial_form_initial_organiser_is_first():
    admin = UserFactory(is_administrator=True)
    org1 = OrganiserFactory()
    OrganiserFactory()

    form = EventWizardInitialForm(user=admin)

    assert form.fields["organiser"].initial == org1


def test_event_wizard_basics_form_locale_choices_filtered_by_locales():
    """Locale choices are filtered to only the locales selected in the
    initial step."""
    user = UserFactory(is_administrator=True)
    organiser = OrganiserFactory()
    form = EventWizardBasicsForm(user=user, locales=["en", "de"], organiser=organiser)

    locale_codes = [code for code, _label in form.fields["locale"].choices]
    assert "en" in locale_codes
    assert "de" in locale_codes


def test_event_wizard_basics_form_clean_slug_rejects_duplicate():
    """``Event.clean()`` runs ``validate_event_slug_unique`` during
    ``_post_clean``, surfacing a case-insensitive duplicate as a
    form-level error on the slug field."""
    existing = EventFactory(slug="myevent")
    user = UserFactory(is_administrator=True)
    data = {
        "name_0": "New Event",
        "slug": "MyEvent",
        "timezone": "UTC",
        "email": "test@example.com",
        "locale": "en",
    }

    form = EventWizardBasicsForm(
        data=data, user=user, locales=["en"], organiser=existing.organiser
    )

    assert not form.is_valid()
    assert "slug" in form.errors


def test_event_wizard_basics_form_copy_from_event_field_present():
    """When a user has access to events with can_change_event_settings,
    the copy_from_event field is added."""
    user = UserFactory()
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    team = TeamFactory(
        organiser=organiser, all_events=True, can_change_event_settings=True
    )
    team.members.add(user)

    form = EventWizardBasicsForm(user=user, locales=["en"], organiser=organiser)

    assert "copy_from_event" in form.fields
    assert list(form.fields["copy_from_event"].queryset) == [event]


def test_event_wizard_basics_form_copy_from_event_field_absent():
    """When a user has no events with can_change_event_settings,
    the copy_from_event field is not added."""
    user = UserFactory()
    organiser = OrganiserFactory()

    form = EventWizardBasicsForm(user=user, locales=["en"], organiser=organiser)

    assert "copy_from_event" not in form.fields


def test_event_wizard_basics_form_copy_from_includes_limit_events():
    """Events accessible via limit_events (not just all_events) are
    included in the copy_from_event queryset."""
    user = UserFactory()
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    team = TeamFactory(
        organiser=organiser, all_events=False, can_change_event_settings=True
    )
    team.members.add(user)
    team.limit_events.add(event)

    form = EventWizardBasicsForm(user=user, locales=["en"], organiser=organiser)

    assert "copy_from_event" in form.fields
    assert list(form.fields["copy_from_event"].queryset) == [event]


def test_event_wizard_timeline_form_clean_rejects_end_before_start():
    """The model-level Event.clean() surfaces date-order errors on the
    date_from field."""
    data = {"date_from": "2025-06-15", "date_to": "2025-06-10"}

    form = EventWizardTimelineForm(data=data, user=None, locales=None, organiser=None)

    assert not form.is_valid()
    assert "date_from" in form.errors


@pytest.mark.parametrize(
    "date_to", ("2025-06-15", "2025-06-10"), ids=("multi_day", "same_day")
)
def test_event_wizard_timeline_form_clean_accepts_valid_dates(date_to):
    data = {"date_from": "2025-06-10", "date_to": date_to}

    form = EventWizardTimelineForm(data=data, user=None, locales=None, organiser=None)

    assert form.is_valid(), form.errors


def test_event_wizard_timeline_form_deadline_is_optional():
    data = {"date_from": "2025-06-10", "date_to": "2025-06-15", "deadline": ""}

    form = EventWizardTimelineForm(data=data, user=None, locales=None, organiser=None)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["deadline"] is None


def test_event_wizard_display_form_init_creates_logo_field():
    form = EventWizardDisplayForm(user=None, locales=None, organiser=None)

    assert "logo" in form.fields
    assert "primary_color" in form.fields
    assert "header_pattern" in form.fields


def test_event_wizard_display_form_copy_prefills_color():
    event = EventFactory(
        primary_color="#ff0000", display_settings={"header_pattern": "topo"}
    )

    form = EventWizardDisplayForm(
        user=None, locales=None, organiser=None, copy_from_event=event
    )

    assert form.fields["primary_color"].initial == "#ff0000"
    assert form.fields["header_pattern"].initial == "topo"


def test_event_wizard_display_form_no_copy_no_prefill():
    form = EventWizardDisplayForm(user=None, locales=None, organiser=None)

    assert form.fields["primary_color"].initial is None
    assert form.fields["header_pattern"].initial is None


def test_event_wizard_plugin_form_init_creates_field_for_installed_plugins():
    form = EventWizardPluginForm(user=None, locales=None, organiser=None)

    assert "plugins" in form.fields
    assert form.fields["plugins"].initial == []
    modules = [
        code
        for _group, plugins in form.fields["plugins"].choices
        for code, _label in plugins
    ]
    assert "tests.dummy_app" in modules


def test_event_wizard_plugin_form_copy_preselects_matching_plugins():
    """Copying from an event pre-selects plugins that are both
    enabled on the source and available in the current installation."""
    event = EventFactory(plugins="tests.dummy_app")

    form = EventWizardPluginForm(
        user=None, locales=None, organiser=None, copy_from_event=event
    )

    assert "plugins" in form.fields
    assert "tests.dummy_app" in form.fields["plugins"].initial


def test_event_wizard_plugin_form_copy_ignores_unavailable_plugins():
    """Plugins enabled on the source event but not installed are
    excluded from the initial selection."""
    event = EventFactory(plugins="nonexistent_plugin")

    form = EventWizardPluginForm(
        user=None, locales=None, organiser=None, copy_from_event=event
    )

    assert "plugins" in form.fields
    assert form.fields["plugins"].initial == []


def test_event_wizard_plugin_form_no_plugins_skips_field(monkeypatch):
    """When no plugins are installed, the form does not expose the
    plugins field at all."""
    monkeypatch.setattr(
        "pretalx.event.interfaces.forms.event.get_all_plugins_grouped", dict
    )

    form = EventWizardPluginForm(user=None, locales=None, organiser=None)

    assert "plugins" not in form.fields


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


def test_eventform_init_sets_locale_initial():
    event = EventFactory(locale_array="en,de")
    form = EventForm(instance=event, locales=event.locales)

    assert form.initial["locales"] == ["en", "de"]


def test_eventform_init_sets_content_locale_initial():
    event = EventFactory(content_locale_array="en,de,fr")
    form = EventForm(instance=event, locales=event.locales)

    assert form.initial["content_locales"] == ["en", "de", "fr"]


@pytest.mark.parametrize(
    ("is_administrator", "expected_disabled"),
    ((False, True), (True, False)),
    ids=("non_admin", "admin"),
)
def test_eventform_init_slug_disabled(is_administrator, expected_disabled):
    event = EventFactory()
    form = EventForm(
        instance=event, locales=event.locales, is_administrator=is_administrator
    )

    assert form.fields["slug"].disabled is expected_disabled


def test_eventform_init_custom_domain_adjusts_slug_addon():
    event = EventFactory(custom_domain="https://custom.example.org")
    form = EventForm(instance=event, locales=event.locales)

    assert form.fields["slug"].widget.addon_before == "https://custom.example.org/"


def test_eventform_init_show_featured_help_text_contains_link():
    event = EventFactory()
    form = EventForm(instance=event, locales=event.locales)

    help_text = str(form.fields["show_featured"].help_text)
    assert "<a " in help_text
    assert str(event.urls.featured) in help_text


def test_eventform_init_locale_choices_filter_visible():
    """Locale choices include only visible languages (from LANGUAGES_INFORMATION)."""
    event = EventFactory()
    form = EventForm(instance=event, locales=event.locales)

    locale_codes = [code for code, _label in form.fields["locales"].choices]
    for code in locale_codes:
        info = settings.LANGUAGES_INFORMATION.get(code, {})
        assert info.get("visible", True) or code in event.plugin_locales


def test_eventform_init_custom_css_text_empty_when_no_css():
    event = EventFactory()
    form = EventForm(instance=event, locales=event.locales)

    assert form.initial["custom_css_text"] == ""


def test_eventform_init_custom_css_text_reads_existing_file():
    event = EventFactory()
    event.custom_css.save("test.css", ContentFile(b"body { color: red; }"))
    form = EventForm(instance=event, locales=event.locales)

    assert form.initial["custom_css_text"] == "body { color: red; }"


def test_eventform_clean_date_from_after_date_to_invalid():
    event = EventFactory()
    data = _build_event_form_data(event, date_from="2024-06-20", date_to="2024-06-15")
    form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    assert "date_from" in form.errors


def test_eventform_clean_locale_not_in_active_locales_invalid():
    event = EventFactory()
    data = _build_event_form_data(event, locale="de", locales=["en"])
    form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    assert "locale" in form.errors


def test_eventform_clean_valid_dates():
    event = EventFactory()
    data = _build_event_form_data(event)
    form = EventForm(data=data, instance=event, locales=event.locales)

    assert form.is_valid(), form.errors


def test_eventform_clean_custom_domain_empty_passthrough():
    event = EventFactory()
    data = _build_event_form_data(event, custom_domain="")
    form = EventForm(data=data, instance=event, locales=event.locales)

    form.is_valid()
    assert form.cleaned_data.get("custom_domain") in ("", None)


@override_settings(SITE_HOST="pretalx.example.com")
def test_eventform_clean_custom_domain_rejects_site_url_hostname():
    """Cannot use the default SITE_URL hostname as a custom domain."""
    event = EventFactory()
    data = _build_event_form_data(event, custom_domain="pretalx.example.com")
    form = EventForm(data=data, instance=event, locales=event.locales)

    with patch("pretalx.event.validators.event.socket.gethostbyname"):
        valid = form.is_valid()

    assert not valid
    assert "custom_domain" in form.errors


@override_settings(SITE_HOST="pretalx.example.com")
def test_eventform_clean_custom_domain_rejects_full_site_url():
    """Cannot use the full SITE_URL as a custom domain."""
    event = EventFactory()
    data = _build_event_form_data(event, custom_domain="https://pretalx.example.com")
    form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    assert "custom_domain" in form.errors


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
    event = EventFactory()
    data = _build_event_form_data(event, custom_domain=domain)
    form = EventForm(data=data, instance=event, locales=event.locales)

    with patch(
        "pretalx.event.validators.event._resolve_host",
        return_value=("host", {"127.0.0.1"}),
    ):
        form.is_valid()

    assert form.cleaned_data["custom_domain"] == expected


@pytest.mark.parametrize(
    "submitted",
    (
        "https://custom.example.org",
        "https://custom.example.org/",
        "http://custom.example.org",
        "custom.example.org",
        "CUSTOM.example.org",
    ),
    ids=("exact", "trailing_slash", "http_prefix", "bare", "mixed_case"),
)
def test_eventform_clean_custom_domain_skips_dns_on_normalized_match(submitted):
    """Resubmitting a value equivalent to the stored domain skips the DNS
    lookup but still yields the normalized form in ``cleaned_data``."""
    event = EventFactory(custom_domain="https://custom.example.org")
    data = _build_event_form_data(event, custom_domain=submitted)
    form = EventForm(data=data, instance=event, locales=event.locales)

    with patch("pretalx.event.validators.event._resolve_host") as resolve_host:
        form.is_valid()

    assert not resolve_host.called
    assert form.cleaned_data["custom_domain"] == "https://custom.example.org"


def test_eventform_clean_custom_domain_dns_failure():
    event = EventFactory()
    data = _build_event_form_data(event, custom_domain="nodns.example.org")
    form = EventForm(data=data, instance=event, locales=event.locales)

    with patch(
        "pretalx.event.validators.event._resolve_host", side_effect=OSError("nope")
    ):
        valid = form.is_valid()

    assert not valid
    assert "custom_domain" in form.errors


def test_eventform_clean_custom_domain_warns_on_mismatch():
    event = EventFactory()
    data = _build_event_form_data(event, custom_domain="custom.example.org")
    form = EventForm(data=data, instance=event, locales=event.locales)

    def resolve(host):
        return ({"custom.example.org": "custom.example.org"}.get(host, host), {host})

    with patch("pretalx.event.validators.event._resolve_host", side_effect=resolve):
        assert form.is_valid(), form.errors

    assert form.cleaned_data["custom_domain"] == "https://custom.example.org"
    assert "does not appear to point" in str(form.custom_domain_warning)


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
    event = EventFactory()
    data = _build_event_form_data(event, custom_css_text=css_text)
    form = EventForm(
        data=data, instance=event, locales=event.locales, is_administrator=is_admin
    )

    assert form.is_valid() == expected_valid, form.errors
    if not expected_valid:
        assert "custom_css_text" in form.errors


def test_eventform_clean_custom_css_preserves_existing_on_invalid_submission():
    """A failing validation must not silently wipe the stored custom_css."""
    event = EventFactory()
    event.custom_css.save("test.css", ContentFile(b"body { color: red; }"))
    data = _build_event_form_data(event, date_from="2024-06-20", date_to="2024-06-15")
    form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    event.refresh_from_db()
    assert event.custom_css.read() == b"body { color: red; }"


@pytest.mark.parametrize(
    ("css_content", "expected_valid"),
    ((b"body { color: red; }", True), (b"body { position: fixed; }", False)),
    ids=("valid_css", "malicious_css"),
)
def test_eventform_clean_custom_css_file(css_content, expected_valid):
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


def test_eventform_clean_custom_css_file_admin_bypass():
    """Admin users can upload CSS with any properties."""
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


def test_eventform_save_updates_locale_array():
    event = EventFactory()
    data = _build_event_form_data(event, locales=["en", "de"])
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert event.locale_array == "en,de"


def test_eventform_save_updates_content_locale_array():
    event = EventFactory()
    data = _build_event_form_data(event, content_locales=["en", "de"])
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert event.content_locale_array == "en,de"


def test_eventform_save_custom_css_text():
    event = EventFactory()
    css = "body { color: green; }"
    data = _build_event_form_data(event, custom_css_text=css)
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert event.custom_css.read().decode() == css


def test_eventform_save_processes_image_on_change(make_image):
    """When an image field changes, the image is processed to WebP format."""
    event = EventFactory()
    data = _build_event_form_data(event)
    files = {"logo": make_image("logo.png")}
    form = EventForm(data=data, files=files, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert event.logo
    assert event.logo.name.endswith(".webp")


def test_eventform_change_dates_moves_slots():
    """When event dates change, scheduled talks are moved by the delta."""
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    wip = event.wip_schedule
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=sub, schedule=wip)
    original_start = slot.start

    data = _build_event_form_data(event, date_from="2024-06-11", date_to="2024-06-13")
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    slot.refresh_from_db()

    assert slot.start == original_start + dt.timedelta(days=1)


def test_eventform_change_dates_does_not_move_published_slots():
    """When event dates move, only WIP schedule slots are moved — published
    slots on released schedules stay at their original times."""
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)

    released = ScheduleFactory(event=event, version="v1")
    published_slot = TalkSlotFactory(submission=sub, schedule=released)
    published_original_start = published_slot.start

    wip = event.wip_schedule
    wip_slot = TalkSlotFactory(submission=sub, schedule=wip)
    wip_original_start = wip_slot.start

    data = _build_event_form_data(event, date_from="2024-06-11", date_to="2024-06-13")
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    published_slot.refresh_from_db()
    wip_slot.refresh_from_db()

    assert published_slot.start == published_original_start
    assert wip_slot.start == wip_original_start + dt.timedelta(days=1)


def test_eventform_change_dates_shortening_deschedules_outside_talks():
    """When the event is shortened, talks outside the new range are descheduled."""
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 14))
    wip = event.wip_schedule
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(
        submission=sub,
        schedule=wip,
        start=dt.datetime(2024, 6, 14, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 14, 11, 0, tzinfo=dt.UTC),
    )

    data = _build_event_form_data(event, date_from="2024-06-10", date_to="2024-06-12")
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    slot.refresh_from_db()

    assert slot.start is None
    assert slot.end is None
    assert slot.room is None


def test_eventform_change_dates_no_slots_does_nothing():
    """When there are no scheduled slots, date changes don't error."""
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    data = _build_event_form_data(event, date_from="2024-06-11", date_to="2024-06-13")
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert event.date_from == dt.date(2024, 6, 11)


def test_eventform_change_dates_extending_end_does_not_move_slots():
    """When only date_to is extended (event gets longer), slots stay put."""
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
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


def test_eventform_change_timezone_adjusts_slots():
    """Changing timezone adjusts slot times to preserve apparent local time."""
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
    event = Event.objects.get(pk=event.pk)

    data = _build_event_form_data(event, timezone="Europe/Berlin")
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    slot.refresh_from_db()

    assert slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)


def test_eventform_change_timezone_no_slots_does_nothing():
    """When no scheduled slots exist, changing timezone completes without error."""
    event = EventFactory(timezone="UTC")
    event = Event.objects.get(pk=event.pk)

    data = _build_event_form_data(event, timezone="Europe/Berlin")
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert event.timezone == "Europe/Berlin"


def test_eventform_change_timezone_same_offset_does_not_move():
    """Changing timezone to one with the same UTC offset leaves slots unchanged."""
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


def test_eventform_read_only_rejects_changes():
    event = EventFactory()
    data = _build_event_form_data(event)
    form = EventForm(data=data, instance=event, locales=event.locales, read_only=True)

    assert not form.is_valid()


def test_eventform_read_only_disables_all_fields():
    event = EventFactory()
    form = EventForm(instance=event, locales=event.locales, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_eventform_font_fields_present_when_plugin_provides_fonts(
    register_signal_handler,
):
    event = EventFactory()

    def handler(signal, sender, **kwargs):
        return {"PluginFont": {"regular": {"woff2": "fonts/plugin.woff2"}}}

    register_signal_handler(register_fonts, handler)
    form = EventForm(instance=event, locales=event.locales)

    assert "heading_font" in form.fields
    assert "text_font" in form.fields
    assert isinstance(form.fields["heading_font"].widget, FontSelect)
    assert isinstance(form.fields["text_font"].widget, FontSelect)
    heading_choices = dict(form.fields["heading_font"].choices)
    assert "PluginFont" in heading_choices
    assert "" in heading_choices
    text_choices = dict(form.fields["text_font"].choices)
    assert "PluginFont" in text_choices


def test_eventform_font_fields_removed_when_no_plugins():
    event = EventFactory()

    form = EventForm(instance=event, locales=event.locales)

    assert "heading_font" not in form.fields
    assert "text_font" not in form.fields


def test_eventextralinkform_valid():
    event = EventFactory()
    data = {"label_0": "Example", "url": "https://example.com"}
    form = EventExtraLinkForm(data=data, locales=event.locales)

    assert form.is_valid(), form.errors


def test_eventextralinkform_requires_url():
    event = EventFactory()
    data = {"label_0": "Example", "url": ""}
    form = EventExtraLinkForm(data=data, locales=event.locales)

    assert not form.is_valid()
    assert "url" in form.errors


def test_eventextralinkform_requires_label():
    event = EventFactory()
    data = {"label_0": "", "url": "https://example.com"}
    form = EventExtraLinkForm(data=data, locales=event.locales)

    assert not form.is_valid()
    assert "label" in form.errors


@pytest.mark.parametrize(
    ("formset_cls", "expected_role"),
    ((EventFooterLinkFormset, "footer"), (EventHeaderLinkFormset, "header")),
    ids=("footer", "header"),
)
def test_baseeventextralinkformset_filters_by_role(formset_cls, expected_role):
    event = EventFactory()
    expected_link = EventExtraLinkFactory(event=event, role=expected_role)
    other_role = "header" if expected_role == "footer" else "footer"
    EventExtraLinkFactory(event=event, role=other_role)
    formset = formset_cls(instance=event, event=event)

    assert list(formset.get_queryset()) == [expected_link]


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

    links = list(EventExtraLink.objects.filter(event=event))
    assert len(links) == 1
    assert links[0].role == expected_role


def test_baseeventextralinkformset_uses_event_locales():
    event = EventFactory(locale_array="en,de")
    formset = EventFooterLinkFormset(instance=event, event=event)

    assert formset.locales == event.locales


def test_baseeventextralinkformset_init_without_event():
    """Formset can be created without passing event."""
    event = EventFactory()
    formset = EventFooterLinkFormset(instance=event)

    assert formset.forms is not None


def test_baseeventextralinkformset_get_queryset_cached():
    """Calling get_queryset twice returns the same cached queryset."""
    event = EventFactory()
    formset = EventFooterLinkFormset(instance=event, event=event)
    qs1 = formset.get_queryset()
    qs2 = formset.get_queryset()

    assert qs1 is qs2


def test_baseeventextralinkformset_save_new_commit_false():
    """save_new with commit=False returns an unsaved instance with role set."""
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


def test_eventform_post_clean_skips_locale_array_when_locales_invalid():
    """When the locales field fails validation, ``_post_clean`` skips the
    locale_array assignment so the old value is preserved on the instance."""
    event = EventFactory(locale_array="en")
    data = _build_event_form_data(event, locales=[], content_locales=[])
    form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    assert event.locale_array == "en"
