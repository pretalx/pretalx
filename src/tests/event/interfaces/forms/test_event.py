# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import translation

from pretalx.common.signals import register_fonts
from pretalx.event.interfaces.forms import (
    EventExtraLinkForm,
    EventFooterLinkFormset,
    EventForm,
    EventHeaderLinkFormset,
    EventWizardBasicsForm,
    EventWizardDisplayForm,
    EventWizardLocalisationForm,
    EventWizardOrganiserForm,
    EventWizardPluginForm,
)
from pretalx.event.models import Event, Organiser
from pretalx.event.models.event import EventExtraLink
from pretalx.orga.forms.widgets import FontSelect, LanguageWidget
from tests.factories import (
    EventExtraLinkFactory,
    EventFactory,
    OrganiserFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_event_wizard_localisation_form_offers_visible_languages_for_both_fields():
    admin = UserFactory(is_administrator=True)
    hidden_info = dict(settings.LANGUAGES_INFORMATION)
    hidden_info["xx-hidden"] = {
        "name": "Hidden",
        "natural_name": "Hidden",
        "official": False,
        "visible": False,
        "code": "xx-hidden",
        "percentage": 100,
    }
    languages = list(settings.LANGUAGES) + [("xx-hidden", "Hidden")]
    with override_settings(LANGUAGES_INFORMATION=hidden_info, LANGUAGES=languages):
        form = EventWizardLocalisationForm(user=admin)

    locale_codes = [code for code, _label in form.fields["locales"].choices]
    assert "xx-hidden" not in locale_codes
    assert len(locale_codes) > 1
    for code in locale_codes:
        assert settings.LANGUAGES_INFORMATION[code].get("visible", True)
    # The default language is narrowed down to the active languages in the
    # browser, so the form itself offers every language the event could use.
    assert form.fields["locale"].choices == form.fields["locales"].choices


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        (
            {"locales": ["de-formal", "en"], "locale": "de-formal", "timezone": "UTC"},
            {},
        ),
        (
            {"locales": ["de"], "locale": "en", "timezone": "UTC"},
            {
                "locale": [
                    "Your default language needs to be one of your active languages."
                ]
            },
        ),
    ),
    ids=("locale_in_locales", "locale_outside_locales"),
)
def test_event_wizard_localisation_form_clean_requires_locale_in_locales(data, errors):
    admin = UserFactory(is_administrator=True)

    form = EventWizardLocalisationForm(data=data, user=admin)

    assert form.is_valid() == (not errors)
    assert form.errors == errors
    assert form.cleaned_data.get("locale") == (None if errors else data["locale"])
    assert "data-autofill" not in form.fields["timezone"].widget.attrs


def test_event_wizard_localisation_form_seeded_from_copy_event():
    admin = UserFactory(is_administrator=True)
    source = EventFactory(
        timezone="Pacific/Auckland", locales=["de", "en"], locale="de"
    )

    form = EventWizardLocalisationForm(user=admin, copy_from_event=source)

    assert form.fields["timezone"].initial == "Pacific/Auckland"
    assert form.fields["locale"].initial == "de"
    assert form.fields["locales"].initial == ["de", "en"]
    assert "data-autofill" not in form.fields["timezone"].widget.attrs


@pytest.mark.parametrize(
    ("language", "expected"),
    (("de", "de"), ("xx", settings.LANGUAGE_CODE)),
    ids=("active", "unknown"),
)
def test_event_wizard_localisation_form_initials_without_copy_event(language, expected):
    admin = UserFactory(is_administrator=True)

    with translation.override(language):
        form = EventWizardLocalisationForm(user=admin)

    assert form.fields["locales"].initial == [expected]
    assert form.fields["locale"].initial == expected
    assert form.fields["timezone"].initial == "UTC"
    assert form.fields["timezone"].widget.attrs["data-autofill"] == "timezone"


@pytest.mark.parametrize(
    ("locale", "expected"), (("de", "de"), (None, "de")), ids=("given", "fallback")
)
def test_event_wizard_basics_form_valid_for_locales_without_english(locale, expected):
    user = UserFactory(is_administrator=True)
    organiser = OrganiserFactory()
    data = {
        "name_0": "Neue Veranstaltung",
        "slug": "wizard-locale-de",
        "email": "test@example.com",
        "date_from": "2025-06-10",
        "date_to": "2025-06-15",
    }

    form = EventWizardBasicsForm(
        data=data, user=user, locales=["de"], locale=locale, organiser=organiser
    )

    assert form.is_valid(), form.errors
    assert form.instance.locale == expected


@pytest.mark.parametrize(
    ("overrides", "errors"),
    (
        ({}, {}),
        ({"date_to": "2025-06-10"}, {}),
        ({"deadline": ""}, {}),
        (
            {"slug": "MyEvent"},
            {
                "slug": [
                    (
                        "This short name is already taken, please choose another one "
                        "(or ask the owner of that event to add you to their team)."
                    )
                ]
            },
        ),
        (
            {"date_from": "2025-06-15", "date_to": "2025-06-10"},
            {"date_from": ["The event end cannot be before the start."]},
        ),
    ),
    ids=(
        "multi_day",
        "same_day",
        "empty_deadline",
        "duplicate_slug",
        "end_before_start",
    ),
)
def test_event_wizard_basics_form_clean(overrides, errors):
    existing = EventFactory(slug="myevent")
    data = {
        "name_0": "New Event",
        "slug": "new-event",
        "email": "test@example.com",
        "date_from": "2025-06-10",
        "date_to": "2025-06-15",
        **overrides,
    }

    form = EventWizardBasicsForm(
        data=data, user=None, locales=["en"], organiser=existing.organiser
    )

    assert form.is_valid() == (not errors)
    assert form.errors == errors
    assert form.cleaned_data.get("deadline") is None


def test_event_wizard_organiser_form_hides_single_organiser_and_rejects_others():
    user = UserFactory()
    organiser = OrganiserFactory()
    other = OrganiserFactory()
    team = TeamFactory(organiser=organiser, can_create_events=True)
    team.members.add(user)
    organisers = Organiser.objects.filter(pk=organiser.pk)

    form = EventWizardOrganiserForm(user=user, organisers=organisers)

    assert form.single_organiser == organiser
    assert form.fields["organiser"].widget.is_hidden
    assert form["organiser"].value() == organiser.pk

    form = EventWizardOrganiserForm(
        data={"organiser": other.pk}, user=user, organisers=organisers
    )

    assert not form.is_valid()
    assert form.errors == {
        "organiser": [
            "Select a valid choice. That choice is not one of the available choices."
        ]
    }


@pytest.mark.parametrize(
    ("all_events", "limit_to_event", "offered"),
    ((True, False, True), (False, True, True), (False, False, False)),
    ids=("all_events_team", "limited_team", "no_events"),
)
def test_event_wizard_organiser_form_copy_from_event_lists_permitted_own_events(
    all_events, limit_to_event, offered
):
    user = UserFactory()
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    EventFactory()
    team = TeamFactory(
        organiser=organiser,
        all_events=all_events,
        can_create_events=True,
        can_change_event_settings=True,
    )
    team.members.add(user)
    if limit_to_event:
        team.limit_events.add(event)
    other = OrganiserFactory()
    EventFactory(organiser=other)
    other_team = TeamFactory(
        organiser=other, all_events=True, can_change_event_settings=True
    )
    other_team.members.add(user)

    form = EventWizardOrganiserForm(
        user=user, organisers=Organiser.objects.filter(pk=organiser.pk)
    )

    assert ("copy_from_event" in form.fields) is offered
    if offered:
        assert list(form.fields["copy_from_event"].queryset) == [event]


@pytest.mark.parametrize(
    ("submitted", "expected"),
    ((None, "first"), ("second", "second"), ("not-a-pk", "first")),
    ids=("unbound_initial", "submitted", "invalid_falls_back"),
)
def test_event_wizard_organiser_form_copy_choices_follow_selected_organiser(
    submitted, expected
):
    admin = UserFactory(is_administrator=True)
    first = OrganiserFactory(name="AAA")
    second = OrganiserFactory(name="BBB")
    events = {
        "first": EventFactory(organiser=first),
        "second": EventFactory(organiser=second),
    }
    pks = {"second": second.pk}
    data = None if submitted is None else {"organiser": pks.get(submitted, submitted)}

    form = EventWizardOrganiserForm(
        data=data, user=admin, organisers=Organiser.objects.order_by("name")
    )

    assert form.fields["organiser"].initial == first
    assert list(form.fields["copy_from_event"].queryset) == [events[expected]]


@pytest.mark.parametrize(
    ("can_change_teams", "offered"), ((True, True), (False, False))
)
def test_event_wizard_basics_form_lists_event_specific_teams_of_copy_source(
    can_change_teams, offered
):
    user = UserFactory()
    organiser = OrganiserFactory()
    source = EventFactory(organiser=organiser)
    other = EventFactory(organiser=organiser)
    creator_team = TeamFactory(
        organiser=organiser,
        all_events=True,
        can_create_events=True,
        can_change_event_settings=True,
        can_change_teams=can_change_teams,
    )
    creator_team.members.add(user)
    single = TeamFactory(organiser=organiser, name="<b>Reviewers</b>", all_events=False)
    single.limit_events.add(source)
    multi = TeamFactory(organiser=organiser, name="Helpers", all_events=False)
    multi.limit_events.add(source, other)
    multi.limit_tracks.add(TrackFactory(event=other))
    TeamFactory(organiser=organiser, all_events=False).limit_events.add(other)
    TeamFactory(organiser=OrganiserFactory(), all_events=False).limit_events.add(source)

    form = EventWizardBasicsForm(
        user=user, locales=["en"], organiser=organiser, copy_from_event=source
    )

    assert ("add_to_teams" in form.fields) is offered
    if offered:
        assert form.fields["add_to_teams"].help_text == (
            "Members of these teams have access to the event you are copying: "
            "&lt;b&gt;Reviewers&lt;/b&gt;, Helpers."
        )


def test_event_wizard_basics_form_mentions_track_limits_on_source_tracks():
    admin = UserFactory(is_administrator=True)
    source = EventFactory()
    limited = TeamFactory(organiser=source.organiser, name="Limited", all_events=False)
    limited.limit_events.add(source)
    limited.limit_tracks.add(TrackFactory(event=source))

    form = EventWizardBasicsForm(
        user=admin, locales=["en"], organiser=source.organiser, copy_from_event=source
    )

    assert form.fields["add_to_teams"].help_text == (
        "Members of these teams have access to the event you are copying: Limited. "
        "Their track limits will apply to the copied tracks, too."
    )


@pytest.mark.parametrize(
    ("all_events", "copying"),
    ((True, True), (False, False)),
    ids=("no_event_specific_teams", "not_copying"),
)
def test_event_wizard_basics_form_no_team_field(all_events, copying):
    admin = UserFactory(is_administrator=True)
    source = EventFactory()
    TeamFactory(organiser=source.organiser, all_events=all_events).limit_events.add(
        source
    )

    form = EventWizardBasicsForm(
        user=admin,
        locales=["en"],
        organiser=source.organiser,
        copy_from_event=source if copying else None,
    )

    assert "add_to_teams" not in form.fields


def test_event_wizard_display_form_fields_without_copy_event():
    form = EventWizardDisplayForm(user=None, locales=None, organiser=None)

    assert list(form.fields) == ["primary_color", "header_pattern", "logo"]
    assert form.fields["primary_color"].initial is None
    assert form.fields["header_pattern"].initial is None


def test_event_wizard_display_form_copy_prefills_color_and_pattern():
    event = EventFactory(
        primary_color="#ff0000", display_settings={"header_pattern": "topo"}
    )

    form = EventWizardDisplayForm(
        user=None, locales=None, organiser=None, copy_from_event=event
    )

    assert form.fields["primary_color"].initial == "#ff0000"
    assert form.fields["header_pattern"].initial == "topo"


@pytest.mark.parametrize(
    ("copy_plugins", "expected_initial"),
    ((None, []), ("tests.dummy_app", ["tests.dummy_app"]), ("nonexistent_plugin", [])),
    ids=("no_copy", "copy_available", "copy_unavailable"),
)
def test_event_wizard_plugin_form_lists_installed_plugins_and_preselects_copied(
    copy_plugins, expected_initial
):
    source = None if copy_plugins is None else EventFactory(plugins=copy_plugins)

    form = EventWizardPluginForm(
        user=None, locales=None, organiser=None, copy_from_event=source
    )

    assert form.fields["plugins"].initial == expected_initial
    modules = [
        code
        for _group, plugins in form.fields["plugins"].choices
        for code, _label in plugins
    ]
    assert "tests.dummy_app" in modules


def test_event_wizard_plugin_form_no_plugins_skips_field(monkeypatch):
    monkeypatch.setattr(
        "pretalx.event.interfaces.forms.event.get_all_plugins_grouped", dict
    )

    form = EventWizardPluginForm(user=None, locales=None, organiser=None)

    assert "plugins" not in form.fields


def _build_event_form_data(event, **overrides):
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


def test_eventform_init_defaults():
    event = EventFactory(
        locales=["en", "de"],
        content_locales=["en", "de", "fr"],
        custom_domain="https://custom.example.org",
        feature_flags={"use_tracks": False},
    )

    form = EventForm(instance=event, locales=event.locales)

    assert form.initial["locales"] == ["en", "de"]
    assert form.initial["content_locales"] == ["en", "de", "fr"]
    assert form.fields["slug"].disabled is True
    assert form.fields["slug"].widget.addon_before == "https://custom.example.org/"
    help_text = str(form.fields["show_featured"].help_text)
    assert f'<a href="{event.urls.featured}">here</a>' in help_text
    for code, _label in form.fields["locales"].choices:
        info = settings.LANGUAGES_INFORMATION.get(code, {})
        assert info.get("visible", True) or code in event.plugin_locales
    rendered = str(form["locale"])
    assert str(LanguageWidget.community_group_label) in rendered
    assert str(LanguageWidget.community_note) in rendered
    assert dict(form.fields["timezone"].choices)["America/New_York"] == (
        "America/New York"
    )
    assert "heading_font" not in form.fields
    assert "text_font" not in form.fields
    assert "attendee_signup_tracks" not in form.fields
    assert "attendee_signup_types" in form.fields


def test_eventform_init_administrator_may_edit_slug():
    event = EventFactory()

    form = EventForm(instance=event, locales=event.locales, is_administrator=True)

    assert form.fields["slug"].disabled is False


@pytest.mark.parametrize(
    ("show_featured", "expected"), (("never", False), ("always", True))
)
def test_eventform_init_featured_text_depends_on_feature_flag(show_featured, expected):
    event = EventFactory(feature_flags={"show_featured": show_featured})

    form = EventForm(instance=event, locales=event.locales)

    assert ("featured_sessions_text" in form.fields) is expected


def test_eventform_init_attendee_signup_fields_scoped_to_event():
    event = EventFactory(feature_flags={"use_tracks": True})
    required_track = TrackFactory(event=event, attendee_signup_required=True)
    optional_track = TrackFactory(event=event, attendee_signup_required=False)
    TrackFactory()
    required_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    SubmissionTypeFactory(event=event, attendee_signup_required=False)

    form = EventForm(instance=event, locales=event.locales)

    assert list(form.fields["attendee_signup_tracks"].queryset) == [
        required_track,
        optional_track,
    ]
    assert form.initial["attendee_signup_tracks"] == [required_track.pk]
    assert form.initial["attendee_signup_types"] == [required_type.pk]


def test_eventform_font_fields_present_when_plugin_provides_fonts(
    register_signal_handler,
):
    event = EventFactory()

    def handler(signal, sender, **kwargs):
        return {"PluginFont": {"regular": {"woff2": "fonts/plugin.woff2"}}}

    register_signal_handler(register_fonts, handler)
    form = EventForm(instance=event, locales=event.locales)

    assert isinstance(form.fields["heading_font"].widget, FontSelect)
    assert isinstance(form.fields["text_font"].widget, FontSelect)
    assert [code for code, _label in form.fields["heading_font"].choices] == [
        "",
        "PluginFont",
    ]
    assert [code for code, _label in form.fields["text_font"].choices] == [
        "",
        "PluginFont",
    ]


def test_eventform_read_only_disables_fields_and_rejects_changes():
    event = EventFactory()
    data = _build_event_form_data(event)

    form = EventForm(data=data, instance=event, locales=event.locales, read_only=True)

    assert all(field.disabled for field in form.fields.values())
    assert not form.is_valid()


@pytest.mark.parametrize(
    ("overrides", "errors"),
    (
        ({}, {}),
        ({"custom_domain": ""}, {}),
        ({"custom_css_text": "body { color: red; }"}, {}),
        (
            {"date_from": "2024-06-20", "date_to": "2024-06-15"},
            {"date_from": ["The event end cannot be before the start."]},
        ),
        (
            {"locale": "de", "locales": ["en"]},
            {
                "locale": [
                    "Your default language needs to be one of your active languages."
                ]
            },
        ),
        (
            {"custom_css_text": "body { position: fixed; }"},
            {
                "custom_css": [
                    "You are not allowed to include “position” keys in your CSS."
                ]
            },
        ),
        (
            {"locales": [], "content_locales": []},
            {
                "locales": ["This field is required."],
                "content_locales": ["This field is required."],
            },
        ),
        (
            {"attendee_signup": "on", "present_multiple_times": "on"},
            {
                "__all__": [
                    (
                        "Attendee signup cannot be combined with multi-slot scheduling "
                        "(sessions taking place multiple times)."
                    )
                ]
            },
        ),
    ),
    ids=(
        "valid",
        "empty_custom_domain",
        "valid_css",
        "end_before_start",
        "locale_not_active",
        "malicious_css",
        "missing_locales",
        "signup_multi_slot_conflict",
    ),
)
def test_eventform_clean(overrides, errors):
    event = EventFactory(
        locales=["en"],
        feature_flags={"attendee_signup": False, "present_multiple_times": False},
    )
    data = _build_event_form_data(event, **overrides)

    form = EventForm(data=data, instance=event, locales=event.locales)

    assert form.is_valid() == (not errors)
    assert form.errors == errors
    assert event.locales == ["en"]


@override_settings(SITE_HOST="pretalx.example.com")
def test_eventform_clean_custom_domain_rejects_site_host():
    event = EventFactory()
    data = _build_event_form_data(event, custom_domain="pretalx.example.com")

    form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    assert form.errors == {
        "custom_domain": [
            "Please do not choose the default domain as custom event domain."
        ]
    }


@pytest.mark.parametrize(
    "submitted",
    ("https://custom.example.org", "CUSTOM.example.org/"),
    ids=("exact", "unnormalised"),
)
def test_eventform_clean_custom_domain_skips_dns_on_normalized_match(submitted):
    event = EventFactory(custom_domain="https://custom.example.org")
    data = _build_event_form_data(event, custom_domain=submitted)
    form = EventForm(data=data, instance=event, locales=event.locales)

    with patch("pretalx.event.validators.event._resolve_host") as resolve_host:
        assert form.is_valid(), form.errors

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
    assert form.errors == {
        "custom_domain": [
            (
                "The domain “https://nodns.example.org” does not have a name server "
                "entry at this time. Please make sure the domain is working before "
                "configuring it here."
            )
        ]
    }


@pytest.mark.parametrize(
    ("ips", "warns"),
    (({"custom.example.org": "9.9.9.9"}, True), ({}, False)),
    ids=("mismatch", "points_to_site"),
)
def test_eventform_clean_custom_domain_normalises_and_warns_on_mismatch(ips, warns):
    event = EventFactory()
    data = _build_event_form_data(event, custom_domain="custom.example.org")
    form = EventForm(data=data, instance=event, locales=event.locales)

    def resolve(host):
        return (host, {ips.get(host, "1.2.3.4")})

    with patch("pretalx.event.validators.event._resolve_host", side_effect=resolve):
        assert form.is_valid(), form.errors

    assert form.cleaned_data["custom_domain"] == "https://custom.example.org"
    assert (form.custom_domain_warning is not None) is warns
    if warns:
        assert "does not appear to point" in str(form.custom_domain_warning)


def test_eventform_saves_with_a_missing_custom_css_file():
    event = EventFactory()
    event.custom_css.save("test.css", ContentFile(b"body { color: red; }"))
    stored_name = event.custom_css.name
    event.custom_css.storage.delete(stored_name)
    data = _build_event_form_data(event, custom_css_text="")

    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert event.custom_css.name == stored_name


def test_eventform_redisplays_custom_css_after_unrelated_error():
    event = EventFactory()
    event.custom_css.save("test.css", ContentFile(b"body { color: red; }"))
    stored_name = event.custom_css.name
    data = _build_event_form_data(
        event,
        custom_css_text="body { color: blue; }",
        date_from="2024-06-20",
        date_to="2024-06-15",
    )
    form = EventForm(data=data, instance=event, locales=event.locales)

    assert not form.is_valid()
    attached, text = form["custom_css"].value()
    assert attached.name == stored_name
    assert text == "body { color: blue; }"
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


def test_eventform_save_updates_locales_and_custom_css_text():
    event = EventFactory()
    css = "body { color: green; }"
    data = _build_event_form_data(
        event, locales=["en", "de"], content_locales=["en", "de"], custom_css_text=css
    )
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert event.locales == ["en", "de"]
    assert event.content_locales == ["en", "de"]
    assert event.custom_css.read().decode() == css


def test_eventform_save_leaves_untouched_invalid_custom_css_alone():
    event = EventFactory()
    invalid_css = "body { position: fixed; }"
    event.custom_css.save("test.css", ContentFile(invalid_css.encode()))
    old_name = event.custom_css.name
    data = _build_event_form_data(
        event, custom_css_text=invalid_css, email="new@example.org"
    )
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert event.email == "new@example.org"
    assert event.custom_css.name == old_name


def test_eventform_save_removes_invalid_custom_css():
    event = EventFactory()
    invalid_css = "body { position: fixed; }"
    event.custom_css.save("test.css", ContentFile(invalid_css.encode()))
    data = _build_event_form_data(event, custom_css_text=invalid_css)
    data["custom_css-clear"] = "on"
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    assert not event.custom_css


def test_eventform_save_processes_image_on_change(
    make_image, django_capture_on_commit_callbacks
):
    event = EventFactory()
    data = _build_event_form_data(event)
    files = {"logo": make_image("logo.png")}
    form = EventForm(data=data, files=files, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    with django_capture_on_commit_callbacks(execute=True):
        form.save()

    event.refresh_from_db()
    assert event.logo
    assert event.logo.name.endswith(".webp")


def test_eventform_save_applies_date_and_timezone_changes_to_slots():
    event = EventFactory(
        date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12), timezone="UTC"
    )
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 11, 0, tzinfo=dt.UTC),
    )
    event = Event.objects.get(pk=event.pk)
    data = _build_event_form_data(
        event, date_from="2024-06-11", date_to="2024-06-13", timezone="Europe/Berlin"
    )
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors

    form.save()

    event.refresh_from_db()
    slot.refresh_from_db()
    assert event.date_from == dt.date(2024, 6, 11)
    assert event.timezone == "Europe/Berlin"
    assert slot.start == dt.datetime(2024, 6, 11, 8, 0, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        ({"label_0": "Example", "url": "https://example.com"}, {}),
        ({"label_0": "Example", "url": ""}, {"url": ["This field is required."]}),
        (
            {"label_0": "", "url": "https://example.com"},
            {"label": ["This field is required."]},
        ),
    ),
    ids=("valid", "missing_url", "missing_label"),
)
def test_eventextralinkform_clean(data, errors):
    event = EventFactory()

    form = EventExtraLinkForm(data=data, locales=event.locales)

    assert form.is_valid() == (not errors)
    assert form.errors == errors


@pytest.mark.parametrize(
    ("formset_cls", "expected_role"),
    ((EventFooterLinkFormset, "footer"), (EventHeaderLinkFormset, "header")),
    ids=("footer", "header"),
)
def test_baseeventextralinkformset_filters_by_role(formset_cls, expected_role):
    event = EventFactory(locales=["en", "de"])
    expected_link = EventExtraLinkFactory(event=event, role=expected_role)
    other_role = "header" if expected_role == "footer" else "footer"
    EventExtraLinkFactory(event=event, role=other_role)

    formset = formset_cls(instance=event, event=event)

    assert formset.locales == ["en", "de"]
    assert list(formset.get_queryset()) == [expected_link]
    assert formset.get_queryset() is formset.get_queryset()


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

    link = EventExtraLink.objects.get(event=event)
    assert (str(link.label), link.url, link.role) == (
        label,
        "https://example.com/new",
        expected_role,
    )


def test_baseeventextralinkformset_init_without_event():
    event = EventFactory()
    formset = EventFooterLinkFormset(instance=event)

    assert formset.forms is not None


def test_baseeventextralinkformset_save_new_commit_false():
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


def test_eventform_can_flip_conflicting_flags_in_one_submission():
    event = EventFactory(
        feature_flags={"attendee_signup": False, "present_multiple_times": True}
    )
    data = _build_event_form_data(
        event, attendee_signup="on", present_multiple_times=""
    )
    form = EventForm(data=data, instance=event, locales=event.locales)

    assert form.is_valid(), form.errors
    form.save()
    event.refresh_from_db()
    assert event.feature_flags["attendee_signup"] is True
    assert event.feature_flags["present_multiple_times"] is False


def test_eventform_save_leaves_track_and_type_flags_when_feature_off():
    event = EventFactory(feature_flags={"use_tracks": True, "attendee_signup": False})
    track = TrackFactory(event=event, attendee_signup_required=True)
    stype = SubmissionTypeFactory(event=event, attendee_signup_required=True)

    data = _build_event_form_data(event)
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    track.refresh_from_db()
    stype.refresh_from_db()
    assert track.attendee_signup_required is True
    assert stype.attendee_signup_required is True


def test_eventform_save_persists_signup_settings_and_only_touches_changed_objects():
    event = EventFactory(feature_flags={"use_tracks": True, "attendee_signup": True})
    track_stays_required = TrackFactory(event=event, attendee_signup_required=True)
    track_to_flip_off = TrackFactory(event=event, attendee_signup_required=True)
    track_to_flip_on = TrackFactory(event=event, attendee_signup_required=False)
    type_stays_required = SubmissionTypeFactory(
        event=event, attendee_signup_required=True
    )
    type_unrelated = SubmissionTypeFactory(event=event, attendee_signup_required=False)
    default_type = event.cfp.default_type
    default_type.attendee_signup_required = True
    default_type.save()

    stamps_before = {
        "track_stays_required": track_stays_required.updated,
        "track_to_flip_off": track_to_flip_off.updated,
        "track_to_flip_on": track_to_flip_on.updated,
        "type_stays_required": type_stays_required.updated,
        "type_unrelated": type_unrelated.updated,
    }

    data = _build_event_form_data(
        event,
        attendee_signup="on",
        signup_domains="company.example",
        attendee_signup_tracks=[track_stays_required.pk, track_to_flip_on.pk],
        attendee_signup_types=[type_stays_required.pk],
    )
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert form.is_valid(), form.errors
    form.save()

    event.refresh_from_db()
    for obj in (
        track_stays_required,
        track_to_flip_off,
        track_to_flip_on,
        type_stays_required,
        type_unrelated,
        default_type,
    ):
        obj.refresh_from_db()

    assert event.feature_flags["attendee_signup"] is True
    assert event.attendee_signup_settings == {"signup_domains": ["company.example"]}
    assert track_stays_required.attendee_signup_required is True
    assert track_to_flip_off.attendee_signup_required is False
    assert track_to_flip_on.attendee_signup_required is True
    assert type_stays_required.attendee_signup_required is True
    assert type_unrelated.attendee_signup_required is False
    assert default_type.attendee_signup_required is False
    assert track_stays_required.updated == stamps_before["track_stays_required"]
    assert type_stays_required.updated == stamps_before["type_stays_required"]
    assert type_unrelated.updated == stamps_before["type_unrelated"]
    assert track_to_flip_off.updated > stamps_before["track_to_flip_off"]
    assert track_to_flip_on.updated > stamps_before["track_to_flip_on"]


def test_eventform_save_signup_on_skips_track_branch_when_field_absent():
    event = EventFactory(feature_flags={"use_tracks": False, "attendee_signup": True})
    leftover = TrackFactory(event=event, attendee_signup_required=True)
    stype = SubmissionTypeFactory(event=event, attendee_signup_required=False)

    data = _build_event_form_data(
        event, attendee_signup="on", attendee_signup_types=[stype.pk]
    )
    form = EventForm(data=data, instance=event, locales=event.locales)
    assert "attendee_signup_tracks" not in form.fields
    assert form.is_valid(), form.errors
    form.save()

    leftover.refresh_from_db()
    stype.refresh_from_db()
    assert leftover.attendee_signup_required is True
    assert stype.attendee_signup_required is True


def test_apply_signup_required_flag_no_op_when_selection_matches():
    event = EventFactory()
    required = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    SubmissionTypeFactory(event=event, attendee_signup_required=False)
    stamp_before = required.updated

    EventForm._apply_signup_required_flag(event.submission_types, [required])

    required.refresh_from_db()
    assert required.updated == stamp_before
