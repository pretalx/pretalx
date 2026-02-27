import pytest
from django_scopes import scopes_disabled
from rest_framework import exceptions

from pretalx.api.views.access_code import SubmitterAccessCodeViewSet
from tests.factories import SubmissionFactory, SubmitterAccessCodeFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_access_code_viewset_get_queryset_returns_event_codes():
    """get_queryset returns access codes belonging to the view's event."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory()
        other_code = SubmitterAccessCodeFactory()
    request = make_api_request(event=code.event)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == [code]
    assert other_code not in qs


@pytest.mark.django_db
def test_access_code_viewset_get_queryset_orders_by_pk():
    """get_queryset returns codes ordered by primary key."""
    with scopes_disabled():
        code1 = SubmitterAccessCodeFactory()
        code2 = SubmitterAccessCodeFactory(event=code1.event)
    request = make_api_request(event=code1.event)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == [code1, code2]


@pytest.mark.django_db
def test_access_code_viewset_perform_destroy_deletes_code():
    """perform_destroy removes the access code and its logged actions."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory()
        user = make_orga_user(code.event, can_change_event_settings=True)
        code.log_action("pretalx.access_code.create", person=user)
        code_pk = code.pk
    request = make_api_request(event=code.event, user=user)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "destroy"

    with scopes_disabled():
        view.perform_destroy(code)
        assert not code.event.submitter_access_codes.filter(pk=code_pk).exists()


@pytest.mark.django_db
def test_access_code_viewset_perform_destroy_raises_when_used():
    """perform_destroy raises ValidationError when the code has submissions."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory()
        SubmissionFactory(event=code.event, access_code=code)
    request = make_api_request(event=code.event)
    view = make_view(SubmitterAccessCodeViewSet, request)
    view.action = "destroy"

    with (
        pytest.raises(exceptions.ValidationError, match="cannot delete"),
        scopes_disabled(),
    ):
        view.perform_destroy(code)
