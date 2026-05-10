# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings

from pretalx.event.interfaces.forms import (
    EventWizardBasicsForm,
    EventWizardDisplayForm,
    EventWizardInitialForm,
    EventWizardPluginForm,
    EventWizardTimelineForm,
)
from tests.factories import EventFactory, OrganiserFactory, TeamFactory, UserFactory

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
    modules = [code for code, _label in form.fields["plugins"].choices[0][1]]
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
