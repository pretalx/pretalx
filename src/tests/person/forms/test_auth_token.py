import pytest
from django_scopes import scopes_disabled

from pretalx.person.forms import AuthTokenForm
from pretalx.person.models.auth_token import (
    ENDPOINTS,
    READ_PERMISSIONS,
    WRITE_PERMISSIONS,
)
from tests.factories import EventFactory

pytestmark = pytest.mark.unit


def _build_form_data(event, preset="read", name="My Token"):
    """Build minimal valid form data for AuthTokenForm."""
    data = {
        "name": name,
        "events": [event.pk],
        "expires": "",
        "permission_preset": preset,
    }
    if preset == "custom":
        for endpoint in ENDPOINTS:
            data[f"endpoint_{endpoint}"] = READ_PERMISSIONS
    return data


@pytest.mark.django_db
def test_auth_token_form_init_events_queryset_limited_to_user_events(user_with_event):
    """The events field only contains events the user has permission for."""
    user, event = user_with_event
    EventFactory()  # event the user has no access to

    form = AuthTokenForm(user=user)

    assert list(form.fields["events"].queryset) == [event]


@pytest.mark.django_db
def test_auth_token_form_init_creates_endpoint_fields(user_with_event):
    """Form init creates a checkbox field for each endpoint, defaulting to read."""
    user, _ = user_with_event

    form = AuthTokenForm(user=user)

    for endpoint in ENDPOINTS:
        field_name = f"endpoint_{endpoint}"
        assert field_name in form.fields
        assert form.fields[field_name].label == f"/{endpoint}"
        assert form.fields[field_name].initial == READ_PERMISSIONS


@pytest.mark.django_db
def test_auth_token_form_get_endpoint_fields_returns_bound_fields(user_with_event):
    """get_endpoint_fields() returns (name, BoundField) pairs for templates."""
    user, _ = user_with_event
    form = AuthTokenForm(user=user)

    endpoint_fields = form.get_endpoint_fields()

    assert len(endpoint_fields) == len(ENDPOINTS)
    for field_name, bound_field in endpoint_fields:
        assert field_name.startswith("endpoint_")
        assert bound_field.name == field_name


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("preset", "expected_permissions"),
    (("read", READ_PERMISSIONS), ("write", WRITE_PERMISSIONS)),
)
def test_auth_token_form_clean_preset_sets_permissions(
    user_with_event, preset, expected_permissions
):
    """The read/write presets set all endpoints to the corresponding permissions."""
    user, event = user_with_event
    data = _build_form_data(event, preset=preset)

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    for endpoint in ENDPOINTS:
        assert form.cleaned_data["endpoints"][endpoint] == expected_permissions


@pytest.mark.django_db
def test_auth_token_form_clean_custom_preset_uses_per_endpoint_selections(
    user_with_event,
):
    """The 'custom' preset reads permissions from individual endpoint fields."""
    user, event = user_with_event
    data = _build_form_data(event, preset="custom")
    data["endpoint_teams"] = ["list", "retrieve", "create"]
    data["endpoint_events"] = ["list"]

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    assert form.cleaned_data["endpoints"]["teams"] == ["list", "retrieve", "create"]
    assert form.cleaned_data["endpoints"]["events"] == ["list"]


@pytest.mark.django_db
def test_auth_token_form_save_sets_user_and_endpoints(user_with_event):
    """save() sets the user and endpoints on the token instance."""
    user, event = user_with_event
    data = _build_form_data(event, preset="read")

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    with scopes_disabled():
        token = form.save()

    assert token.user == user
    assert token.name == "My Token"
    assert token.endpoints == dict.fromkeys(ENDPOINTS, READ_PERMISSIONS)
    assert token.pk is not None


@pytest.mark.django_db
def test_auth_token_form_save_associates_events(user_with_event):
    """save() associates selected events with the token."""
    user, event = user_with_event
    data = _build_form_data(event, preset="read")

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    with scopes_disabled():
        token = form.save()

    assert list(token.events.all()) == [event]
