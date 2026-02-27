import sys

import pytest
from django.conf import settings
from django.test import override_settings
from django_scopes import scopes_disabled

from pretalx.common.update_check import check_result_table
from pretalx.orga.views.admin import AdminDashboard, AdminUserView, UpdateCheckView
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory, UserFactory
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_admin_dashboard_queue_length_eager_returns_none(event):
    """queue_length returns None when Celery runs in eager mode."""
    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    view = make_view(AdminDashboard, request)

    assert view.queue_length() is None


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_admin_dashboard_queue_length_broker_error_returns_string(event):
    """queue_length returns error string when broker connection fails."""
    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    view = make_view(AdminDashboard, request)

    result = view.queue_length()

    assert isinstance(result, str)


@pytest.mark.django_db
def test_admin_dashboard_executable_returns_sys_executable(event):
    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    view = make_view(AdminDashboard, request)

    assert view.executable() == sys.executable


@pytest.mark.django_db
def test_admin_dashboard_pretalx_version_returns_setting(event):
    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    view = make_view(AdminDashboard, request)

    assert view.pretalx_version() == settings.PRETALX_VERSION


@pytest.mark.django_db
def test_update_check_view_result_table(event):
    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    view = make_view(UpdateCheckView, request)

    result = view.result_table()

    assert result == check_result_table()


@pytest.mark.django_db
def test_update_check_view_get_success_url(event):
    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    view = make_view(UpdateCheckView, request)

    assert view.get_success_url() == "/orga/admin/update/"


@pytest.mark.django_db
@pytest.mark.parametrize("is_administrator", (True, False))
def test_admin_user_view_has_permission(event, is_administrator):
    user = UserFactory(is_administrator=is_administrator)
    request = make_request(event, user=user)
    view = make_view(AdminUserView, request)

    assert view.has_permission() is is_administrator


@pytest.mark.django_db
@pytest.mark.parametrize("search", ("", "ab"))
def test_admin_user_view_get_queryset_list_insufficient_search(search):
    """List action with no or too-short search query returns empty queryset."""
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    request.GET = {"q": search} if search else {}
    view = make_view(AdminUserView, request)
    view.action = "list"

    qs = view.get_queryset()

    assert qs.count() == 0


@pytest.mark.django_db
def test_admin_user_view_get_queryset_list_with_search():
    """List action with sufficient search query filters by name/email."""
    target_user = UserFactory(name="Searchable Name")
    UserFactory(name="Other Person")
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    request.GET = {"q": "Searchable"}
    view = make_view(AdminUserView, request)
    view.action = "list"

    qs = view.get_queryset()

    assert list(qs) == [target_user]


@pytest.mark.django_db
def test_admin_user_view_get_queryset_list_search_by_email():
    """List action search also matches email addresses."""
    target_user = UserFactory(email="findme@example.com")
    UserFactory(email="other@example.com")
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    request.GET = {"q": "findme@example"}
    view = make_view(AdminUserView, request)
    view.action = "list"

    qs = view.get_queryset()

    assert list(qs) == [target_user]


@pytest.mark.django_db
def test_admin_user_view_get_queryset_detail_returns_all():
    """Non-list actions return all users."""
    user1 = UserFactory()
    user2 = UserFactory()
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    request.GET = {}
    view = make_view(AdminUserView, request)
    view.action = "detail"

    qs = view.get_queryset()

    assert set(qs) == {user1, user2, admin_user}


@pytest.mark.django_db
def test_admin_user_view_get_queryset_annotates_submission_count():
    """Queryset annotates submission_count from speaker profiles."""
    user = UserFactory()
    event = EventFactory()
    speaker = SpeakerFactory(user=user, event=event)
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)
    with scopes_disabled():
        sub1.speakers.add(speaker)
        sub2.speakers.add(speaker)

    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    request.GET = {"q": user.name}
    view = make_view(AdminUserView, request)
    view.action = "list"

    result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0].submission_count == 2


@pytest.mark.django_db
def test_admin_user_view_get_success_url():
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    view = make_view(AdminUserView, request)

    assert view.get_success_url() == "/orga/admin/users/"


@pytest.mark.django_db
def test_admin_user_view_get_generic_title_with_instance():
    user = UserFactory(name="Test Speaker")
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    view = make_view(AdminUserView, request)

    assert view.get_generic_title(instance=user) == "Test Speaker"


@pytest.mark.django_db
def test_admin_user_view_get_generic_title_without_instance():
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    view = make_view(AdminUserView, request)

    assert str(view.get_generic_title()) == "Users"
