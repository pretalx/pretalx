import pytest
from django.conf import settings
from django.core import mail as djmail
from django_scopes import scopes_disabled

from pretalx.event.forms import (
    EventWizardBasicsForm,
    EventWizardDisplayForm,
    EventWizardInitialForm,
    EventWizardPluginForm,
    EventWizardTimelineForm,
    OrganiserForm,
    TeamForm,
    TeamInviteForm,
)
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_team_form_init_new_team_uses_organiser_events(event):
    """When creating a new team, limit_events queryset only includes
    events belonging to the provided organiser."""
    EventFactory()  # other organiser's event, should not appear
    organiser = event.organiser
    form = TeamForm(organiser=organiser)

    assert list(form.fields["limit_events"].queryset) == [event]


@pytest.mark.django_db
def test_team_form_init_existing_team_uses_instance_organiser(event):
    """When editing an existing team, limit_events queryset only includes
    events belonging to the team's own organiser."""
    EventFactory()  # other organiser's event, should not appear
    team = TeamFactory(organiser=event.organiser, all_events=True)

    form = TeamForm(instance=team, organiser=event.organiser)

    assert list(form.fields["limit_events"].queryset) == [event]


@pytest.mark.django_db
def test_team_form_init_limit_tracks_with_all_events(event):
    """When the team has all_events or no limit_events, limit_tracks
    queryset covers all tracks for the organiser but excludes others."""
    organiser = event.organiser
    track = TrackFactory(event=event)
    TrackFactory()  # track on another organiser's event, should not appear

    form = TeamForm(organiser=organiser)

    assert list(form.fields["limit_tracks"].queryset) == [track]


@pytest.mark.django_db
def test_team_form_init_limit_tracks_scoped_to_limit_events(event):
    """When an existing team has specific limit_events and all_events is
    False, limit_tracks queryset is narrowed to those events' tracks."""
    organiser = event.organiser
    track = TrackFactory(event=event)
    other_event = EventFactory(organiser=organiser)
    TrackFactory(event=other_event)

    team = TeamFactory(organiser=organiser, all_events=False)
    team.limit_events.add(event)

    form = TeamForm(instance=team, organiser=organiser)

    assert list(form.fields["limit_tracks"].queryset) == [track]


@pytest.mark.django_db
def test_team_form_save_sets_organiser(event):
    """TeamForm.save() sets the organiser on the instance before saving."""
    organiser = event.organiser
    data = {
        "name": "New Team",
        "all_events": True,
        "can_change_submissions": True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)
    assert form.is_valid(), form.errors

    with scopes_disabled():
        team = form.save()

    assert team.organiser == organiser
    assert team.name == "New Team"


@pytest.mark.django_db
def test_team_form_clean_rejects_no_events_and_not_all_events(event):
    """clean() adds an error if neither all_events nor limit_events is set."""
    organiser = event.organiser
    data = {
        "name": "New Team",
        "all_events": False,
        "can_change_submissions": True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)

    assert not form.is_valid()
    assert "limit_events" in form.errors


@pytest.mark.django_db
def test_team_form_clean_rejects_no_permissions(event):
    """clean() adds a non-field error if no permission checkbox is selected."""
    organiser = event.organiser
    data = {
        "name": "No Permission Team",
        "all_events": True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)

    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.parametrize(
    "permission",
    (
        "can_create_events",
        "can_change_teams",
        "can_change_organiser_settings",
        "can_change_event_settings",
        "can_change_submissions",
        "is_reviewer",
    ),
)
@pytest.mark.django_db
def test_team_form_clean_accepts_any_single_permission(event, permission):
    """Each individual permission is sufficient to pass validation."""
    organiser = event.organiser
    data = {
        "name": "Single Perm Team",
        "all_events": True,
        permission: True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)

    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    ("all_events", "use_limit_events"),
    ((True, False), (False, True)),
    ids=("all_events", "limit_events"),
)
@pytest.mark.django_db
def test_team_form_clean_accepts_events_via_all_or_limit(
    event, all_events, use_limit_events
):
    """Either all_events=True or providing limit_events is sufficient."""
    organiser = event.organiser
    data = {
        "name": "Team",
        "all_events": all_events,
        "can_change_submissions": True,
        "limit_events": [event.pk] if use_limit_events else [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_team_form_init_read_only_disables_all_fields(event):
    """When read_only=True, all form fields are disabled."""
    organiser = event.organiser
    form = TeamForm(organiser=organiser, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


@pytest.mark.django_db
def test_team_form_clean_read_only_rejects_changes(event):
    """A read-only TeamForm rejects any data submission."""
    organiser = event.organiser
    data = {
        "name": "Sneaky Team",
        "all_events": True,
        "can_change_submissions": True,
        "limit_events": [],
        "limit_tracks": [],
    }

    form = TeamForm(data=data, organiser=organiser, read_only=True)

    assert not form.is_valid()


@pytest.mark.parametrize(
    ("bulk_email", "fallback_email", "expected"),
    (
        ("a@example.com\nb@example.com", "", ["a@example.com", "b@example.com"]),
        ("", "single@example.com", []),
    ),
    ids=("valid_emails", "empty"),
)
@pytest.mark.django_db
def test_team_invite_form_clean_bulk_email(bulk_email, fallback_email, expected):
    """clean_bulk_email returns parsed emails or an empty list."""
    data = {"bulk_email": bulk_email, "email": fallback_email}
    form = TeamInviteForm(data=data)
    form.is_valid()

    assert form.cleaned_data["bulk_email"] == expected


@pytest.mark.django_db
def test_team_invite_form_clean_bulk_email_invalid_email_adds_error():
    """Invalid email addresses in bulk_email produce field-level errors."""
    data = {"bulk_email": "valid@example.com\nnot-an-email", "email": ""}
    form = TeamInviteForm(data=data)

    assert not form.is_valid()
    assert "bulk_email" in form.errors


@pytest.mark.django_db
def test_team_invite_form_clean_requires_at_least_one_email():
    """Submitting with neither email nor bulk_email raises a
    non-field validation error."""
    data = {"bulk_email": "", "email": ""}
    form = TeamInviteForm(data=data)

    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.django_db
def test_team_invite_form_clean_accepts_single_email():
    """A single email in the email field is sufficient."""
    data = {"email": "test@example.com", "bulk_email": ""}
    form = TeamInviteForm(data=data)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_team_invite_form_clean_does_not_add_extra_error_if_bulk_errors_exist():
    """When bulk_email already has errors, clean() does not add a
    redundant 'please enter an email' error."""
    data = {"bulk_email": "not-valid-at-all", "email": ""}
    form = TeamInviteForm(data=data)

    form.is_valid()

    assert "bulk_email" in form.errors
    assert "__all__" not in form.errors


@pytest.mark.django_db
def test_team_invite_form_save_single_email():
    """save() with a single email creates one TeamInvite and sends it."""
    djmail.outbox = []
    team = TeamFactory()
    data = {"email": "invitee@example.com", "bulk_email": ""}
    form = TeamInviteForm(data=data)
    assert form.is_valid(), form.errors

    invites = form.save(team=team)

    assert len(invites) == 1
    assert invites[0].team == team
    assert invites[0].email == "invitee@example.com"
    assert invites[0].pk is not None
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_team_invite_form_save_bulk_emails():
    """save() with bulk_email creates multiple TeamInvites and sends each."""
    djmail.outbox = []
    team = TeamFactory()
    data = {"bulk_email": "a@example.com\nb@example.com", "email": ""}
    form = TeamInviteForm(data=data)
    assert form.is_valid(), form.errors

    invites = form.save(team=team)

    assert len(invites) == 2
    assert {i.email for i in invites} == {"a@example.com", "b@example.com"}
    assert all(i.team == team for i in invites)
    assert len(djmail.outbox) == 2


@pytest.mark.django_db
def test_team_invite_form_save_bulk_emails_strips_whitespace():
    """Bulk emails with trailing/leading whitespace are cleaned."""
    djmail.outbox = []
    team = TeamFactory()
    data = {"bulk_email": "  a@example.com  \n  b@example.com  ", "email": ""}
    form = TeamInviteForm(data=data)
    assert form.is_valid(), form.errors

    invites = form.save(team=team)

    assert {i.email for i in invites} == {"a@example.com", "b@example.com"}


@pytest.mark.django_db
def test_team_invite_form_init_read_only_disables_all_fields():
    """When read_only=True, all form fields are disabled."""
    form = TeamInviteForm(read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_organiser_form_init_name_is_required():
    """OrganiserForm makes the name field required."""
    form = OrganiserForm()
    assert form.fields["name"].required is True


@pytest.mark.django_db
def test_organiser_form_slug_disabled_on_edit():
    """When editing an existing organiser, the slug field is disabled."""
    organiser = OrganiserFactory()
    form = OrganiserForm(instance=organiser)

    assert form.fields["slug"].disabled is True


def test_organiser_form_slug_enabled_on_create():
    """When creating a new organiser, the slug field is editable."""
    form = OrganiserForm()

    assert form.fields["slug"].disabled is False


@pytest.mark.django_db
def test_organiser_form_valid_data_saves():
    """A valid OrganiserForm creates an organiser with the correct name."""
    data = {"name_0": "My Org", "slug": "my-org"}
    form = OrganiserForm(data=data)
    assert form.is_valid(), form.errors

    organiser = form.save()

    assert str(organiser.name) == "My Org"
    assert organiser.slug == "my-org"


@pytest.mark.django_db
def test_event_wizard_initial_form_admin_sees_all_organisers():
    """Admin users see all organisers in the organiser queryset."""
    admin = UserFactory(is_administrator=True)
    org1 = OrganiserFactory()
    org2 = OrganiserFactory()

    form = EventWizardInitialForm(user=admin)

    assert set(form.fields["organiser"].queryset) == {org1, org2}


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_wizard_initial_form_non_admin_without_teams_sees_empty():
    """A non-admin user without any teams sees no organisers."""
    user = UserFactory()
    OrganiserFactory()

    form = EventWizardInitialForm(user=user)

    assert list(form.fields["organiser"].queryset) == []


@pytest.mark.django_db
def test_event_wizard_initial_form_locales_field_uses_settings_languages():
    """The locales field choices come from settings.LANGUAGES."""
    admin = UserFactory(is_administrator=True)
    form = EventWizardInitialForm(user=admin)

    assert form.fields["locales"].choices == settings.LANGUAGES


@pytest.mark.django_db
def test_event_wizard_initial_form_initial_organiser_is_first():
    """The organiser field's initial value is the first available organiser."""
    admin = UserFactory(is_administrator=True)
    org1 = OrganiserFactory()
    OrganiserFactory()

    form = EventWizardInitialForm(user=admin)

    assert form.fields["organiser"].initial == org1


@pytest.mark.django_db
def test_event_wizard_basics_form_locale_choices_filtered_by_locales():
    """Locale choices are filtered to only the locales selected in the
    initial step."""
    user = UserFactory(is_administrator=True)
    organiser = OrganiserFactory()
    form = EventWizardBasicsForm(user=user, locales=["en", "de"], organiser=organiser)

    locale_codes = [code for code, _label in form.fields["locale"].choices]
    assert "en" in locale_codes
    assert "de" in locale_codes


@pytest.mark.django_db
def test_event_wizard_basics_form_clean_slug_rejects_duplicate():
    """clean_slug rejects slugs that already exist (case-insensitive)."""
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


@pytest.mark.django_db
def test_event_wizard_basics_form_clean_slug_lowercases():
    """clean_slug returns the slug in lowercase."""
    user = UserFactory(is_administrator=True)
    organiser = OrganiserFactory()
    data = {
        "name_0": "New Event",
        "slug": "MyNewEvent",
        "timezone": "UTC",
        "email": "test@example.com",
        "locale": "en",
    }

    form = EventWizardBasicsForm(
        data=data, user=user, locales=["en"], organiser=organiser
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["slug"] == "mynewevent"


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_wizard_basics_form_copy_from_event_field_absent():
    """When a user has no events with can_change_event_settings,
    the copy_from_event field is not added."""
    user = UserFactory()
    organiser = OrganiserFactory()

    form = EventWizardBasicsForm(user=user, locales=["en"], organiser=organiser)

    assert "copy_from_event" not in form.fields


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_wizard_timeline_form_clean_rejects_end_before_start():
    """clean() adds an error if date_from is after date_to."""
    data = {"date_from": "2025-06-15", "date_to": "2025-06-10"}

    form = EventWizardTimelineForm(data=data, user=None, locales=None, organiser=None)

    assert not form.is_valid()
    assert "date_from" in form.errors


@pytest.mark.parametrize(
    "date_to", ("2025-06-15", "2025-06-10"), ids=("multi_day", "same_day")
)
@pytest.mark.django_db
def test_event_wizard_timeline_form_clean_accepts_valid_dates(date_to):
    """clean() passes when date_from <= date_to, including single-day events."""
    data = {"date_from": "2025-06-10", "date_to": date_to}

    form = EventWizardTimelineForm(data=data, user=None, locales=None, organiser=None)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_event_wizard_timeline_form_deadline_is_optional():
    """The deadline field is not required."""
    data = {"date_from": "2025-06-10", "date_to": "2025-06-15", "deadline": ""}

    form = EventWizardTimelineForm(data=data, user=None, locales=None, organiser=None)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["deadline"] is None


def test_event_wizard_display_form_init_creates_logo_field():
    """The display form dynamically adds a logo ImageField."""
    form = EventWizardDisplayForm(user=None, locales=None, organiser=None)

    assert "logo" in form.fields
    assert "primary_color" in form.fields
    assert "header_pattern" in form.fields


@pytest.mark.django_db
def test_event_wizard_display_form_copy_prefills_color(event):
    """When copy_from_event is passed, primary_color and header_pattern
    are pre-filled from the source event."""
    event.primary_color = "#ff0000"
    event.display_settings["header_pattern"] = "topo"
    event.save()

    form = EventWizardDisplayForm(
        user=None, locales=None, organiser=None, copy_from_event=event
    )

    assert form.fields["primary_color"].initial == "#ff0000"
    assert form.fields["header_pattern"].initial == "topo"


def test_event_wizard_display_form_no_copy_no_prefill():
    """Without copy_from_event, no initial values are set for color
    and header_pattern beyond the field defaults."""
    form = EventWizardDisplayForm(user=None, locales=None, organiser=None)

    assert form.fields["primary_color"].initial is None
    assert form.fields["header_pattern"].initial is None


def test_event_wizard_plugin_form_init_creates_field_for_installed_plugins():
    """The dummy test plugin is discovered and a plugins field is created."""
    form = EventWizardPluginForm(user=None, locales=None, organiser=None)

    assert "plugins" in form.fields
    assert form.fields["plugins"].initial == []
    modules = [code for code, _label in form.fields["plugins"].choices[0][1]]
    assert "tests.dummy_app" in modules


@pytest.mark.django_db
def test_event_wizard_plugin_form_copy_preselects_matching_plugins(event):
    """Copying from an event pre-selects plugins that are both
    enabled on the source and available in the current installation."""
    event.enable_plugin("tests.dummy_app")
    event.save()

    form = EventWizardPluginForm(
        user=None, locales=None, organiser=None, copy_from_event=event
    )

    assert "plugins" in form.fields
    assert "tests.dummy_app" in form.fields["plugins"].initial


@pytest.mark.django_db
def test_event_wizard_plugin_form_copy_ignores_unavailable_plugins(event):
    """Plugins enabled on the source event but not installed are
    excluded from the initial selection."""
    event.enable_plugin("nonexistent_plugin")
    event.save()

    form = EventWizardPluginForm(
        user=None, locales=None, organiser=None, copy_from_event=event
    )

    assert "plugins" in form.fields
    assert form.fields["plugins"].initial == []


def test_event_wizard_plugin_form_no_plugins_skips_field():
    """When no plugins are available, the plugins field is not added."""
    form = EventWizardPluginForm(
        user=None, locales=None, organiser=None, grouped_plugins={}
    )

    assert "plugins" not in form.fields
