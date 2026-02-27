import pytest
from django_scopes import scopes_disabled
from rest_framework.permissions import AllowAny

from pretalx.api.permissions import ApiPermission
from pretalx.api.serializers.feedback import FeedbackSerializer, FeedbackWriteSerializer
from pretalx.api.views.feedback import FeedbackViewSet
from tests.factories import FeedbackFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = pytest.mark.unit


def test_feedback_viewset_get_permissions_create_returns_allowany():
    """get_permissions returns AllowAny for the create action."""
    request = make_api_request()
    view = make_view(FeedbackViewSet, request)
    view.action = "create"

    permissions = view.get_permissions()

    assert len(permissions) == 1
    assert isinstance(permissions[0], AllowAny)


def test_feedback_viewset_get_permissions_list_returns_api_permission():
    """get_permissions returns default ApiPermission for the list action."""
    request = make_api_request()
    view = make_view(FeedbackViewSet, request)
    view.action = "list"

    permissions = view.get_permissions()

    assert any(isinstance(p, ApiPermission) for p in permissions)


def test_feedback_viewset_get_unversioned_serializer_class_create():
    """get_unversioned_serializer_class returns FeedbackWriteSerializer for create."""
    request = make_api_request()
    view = make_view(FeedbackViewSet, request)
    view.action = "create"

    assert view.get_unversioned_serializer_class() is FeedbackWriteSerializer


def test_feedback_viewset_get_unversioned_serializer_class_list():
    """get_unversioned_serializer_class returns FeedbackSerializer for list."""
    request = make_api_request()
    view = make_view(FeedbackViewSet, request)
    view.action = "list"

    assert view.get_unversioned_serializer_class() is FeedbackSerializer


@pytest.mark.django_db
def test_feedback_viewset_get_queryset_anonymous_returns_empty():
    """get_queryset returns an empty queryset for anonymous users."""
    with scopes_disabled():
        feedback = FeedbackFactory()
    request = make_api_request(event=feedback.talk.event)
    view = make_view(FeedbackViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == []


@pytest.mark.django_db
def test_feedback_viewset_get_queryset_authenticated_returns_event_feedback():
    """get_queryset returns feedback for the event when user is authenticated."""
    with scopes_disabled():
        feedback = FeedbackFactory()
        event = feedback.talk.event
        other_feedback = FeedbackFactory()
        user = make_orga_user(event, can_change_submissions=True)
    request = make_api_request(event=event, user=user)
    view = make_view(FeedbackViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == [feedback]
    assert other_feedback not in qs
