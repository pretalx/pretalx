import datetime as dt
from types import SimpleNamespace

import pytest
from django import forms
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import Http404, QueryDict
from django.shortcuts import redirect
from django.test import RequestFactory
from django.urls import NoReverseMatch
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.common.forms.mixins import PretalxI18nModelForm
from pretalx.common.signals import EventPluginSignal
from pretalx.common.text.phrases import phrases
from pretalx.common.views.generic import (
    CreateOrUpdateView,
    CRUDHandlerMap,
    CRUDView,
    FormLoggingMixin,
    FormSignalMixin,
    GenericLoginView,
    GenericResetView,
    OrgaCRUDView,
    OrgaTableMixin,
    get_next_url,
)
from pretalx.submission.models import Tag
from tests.factories import TagFactory, UserFactory
from tests.utils import make_orga_user, make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

_rf = RequestFactory()
_test_form_signal = EventPluginSignal()


def _with_messages(request):
    """Attach message storage to a RequestFactory request."""
    request._messages = FallbackStorage(request)
    return request


def _make_crud_view(
    event, user=None, *, action="list", obj=None, url_name="test.tag", namespace="orga"
):
    view = CRUDView()
    view.model = Tag
    view.action = action
    view.object = obj
    view.url_name = url_name
    view.namespace = namespace
    view.detail_is_update = True
    view.show_history = True
    view.form_class = None

    request = _with_messages(make_request(event, user=user or AnonymousUser()))
    request.resolver_match = SimpleNamespace(url_name="tag.list", namespaces=["orga"])
    view.request = request
    view.kwargs = {}
    return view


def _make_form_signal_mixin(event, extra_forms_signal=None):
    """Create a minimal FormSignalMixin instance for testing."""

    class DummyParent:
        def get_context_data(self, **kwargs):
            return kwargs

        def form_valid(self, form, **kwargs):
            pass

    class TestMixin(FormSignalMixin, DummyParent):
        pass

    instance = TestMixin()
    instance.extra_forms_signal = extra_forms_signal
    instance.request = _with_messages(make_request(event))
    return instance


def _make_form_logging_mixin(event, user, *, action="update", obj=None):
    class DummyParent:
        def form_valid(self, form):
            form.save()
            return redirect("/")

    class TestMixin(FormLoggingMixin, DummyParent):
        pass

    instance = TestMixin()
    instance.request = _with_messages(make_request(event, user=user))
    instance.object = obj
    instance.action = action
    return instance


def _make_table_mixin(event, user, *, table_class=None, request_get=None):
    class DummyParent:
        def get_context_data(self, **kwargs):
            return kwargs

        def get_template_names(self):
            return ["test/template.html"]

    class TestMixin(OrgaTableMixin, DummyParent):
        pass

    mixin = TestMixin()
    mixin.table_class = table_class
    mixin.table_template_name = "django_tables2/table.html"
    request = make_request(event, user=user)
    request.resolver_match = SimpleNamespace(url_name="tag.list")
    if request_get:
        request.GET = QueryDict(request_get)
    mixin.request = request
    return mixin


def _make_orga_crud_view(event, user, *, action="list", obj=None):
    view = OrgaCRUDView()
    view.model = Tag
    view.action = action
    view.object = obj
    view.url_name = "tag"
    view.namespace = "orga"
    view.detail_is_update = True
    view.show_history = True
    view.form_class = None
    view.table_class = None
    view.extra_forms_signal = None

    request = _with_messages(make_request(event, user=user))
    request.resolver_match = SimpleNamespace(url_name="tag.list", namespaces=["orga"])
    view.request = request
    view.kwargs = {}
    return view


# --- get_next_url ---


@pytest.mark.parametrize(
    ("query_string", "omit_params", "expected"),
    (
        ("", None, None),
        ("next=/dashboard/", None, "/dashboard/"),
        ("next=http://evil.com/", None, None),
    ),
    ids=("no_next_param", "valid_next", "rejects_external_url"),
)
def test_get_next_url(query_string, omit_params, expected):
    request = _rf.get("/", QUERY_STRING=query_string)
    assert get_next_url(request, omit_params=omit_params) == expected


def test_get_next_url_preserves_extra_params():
    request = _rf.get("/", QUERY_STRING="next=/dashboard/&page=2&sort=name")
    result = get_next_url(request)
    assert result.startswith("/dashboard/?")
    assert "page=2" in result
    assert "sort=name" in result


def test_get_next_url_omits_specified_params():
    request = _rf.get("/", QUERY_STRING="next=/dashboard/&page=2&secret=yes")
    result = get_next_url(request, omit_params=["secret"])
    assert "secret" not in result
    assert "page=2" in result


def test_get_next_url_returns_plain_url_when_no_extra_params():
    request = _rf.get("/", QUERY_STRING="next=/dashboard/")
    result = get_next_url(request)
    assert result == "/dashboard/"
    assert "?" not in result


# --- FormSignalMixin ---


def test_form_signal_mixin_extra_forms_returns_empty_list_when_no_signal(event):
    mixin = _make_form_signal_mixin(event)
    assert mixin.extra_forms == []


def test_form_signal_mixin_extra_forms_skips_exception_responses(
    event, register_signal_handler
):
    """Signal responses that are Exceptions are silently skipped."""

    def handler(signal, sender, **kwargs):
        raise ValueError("broken plugin")

    register_signal_handler(_test_form_signal, handler)

    mixin = _make_form_signal_mixin(
        event,
        extra_forms_signal="tests.common.views.unit.test_generic._test_form_signal",
    )
    mixin.get_form_kwargs = dict
    assert mixin.extra_forms == []


def test_form_signal_mixin_extra_forms_extends_list_response(
    event, register_signal_handler
):
    """When a signal returns a list, forms.extend is called."""
    form_a = SimpleNamespace(name="a")
    form_b = SimpleNamespace(name="b")

    def handler(signal, sender, **kwargs):
        return [form_a, form_b]

    register_signal_handler(_test_form_signal, handler)

    mixin = _make_form_signal_mixin(
        event,
        extra_forms_signal="tests.common.views.unit.test_generic._test_form_signal",
    )
    mixin.get_form_kwargs = dict

    assert mixin.extra_forms == [form_a, form_b]


def test_form_signal_mixin_extra_forms_appends_single_response(
    event, register_signal_handler
):
    """When a signal returns a single form, it's appended."""
    form = SimpleNamespace(name="single")

    def handler(signal, sender, **kwargs):
        return form

    register_signal_handler(_test_form_signal, handler)

    mixin = _make_form_signal_mixin(
        event,
        extra_forms_signal="tests.common.views.unit.test_generic._test_form_signal",
    )
    mixin.get_form_kwargs = dict

    assert mixin.extra_forms == [form]


def test_form_signal_mixin_extra_forms_skips_falsy_response(
    event, register_signal_handler
):
    """When a signal returns None/False/empty, it's skipped."""

    def handler(signal, sender, **kwargs):
        return None

    register_signal_handler(_test_form_signal, handler)

    mixin = FormSignalMixin()
    mixin.extra_forms_signal = "tests.common.views.unit.test_generic._test_form_signal"
    mixin.request = _with_messages(make_request(event))
    mixin.get_form_kwargs = dict

    assert mixin.extra_forms == []


def test_form_signal_mixin_get_context_data_includes_extra_forms(event):
    mixin = _make_form_signal_mixin(event)
    context = mixin.get_context_data(foo="bar")
    assert context["extra_forms"] == []
    assert context["foo"] == "bar"


def test_form_signal_mixin_form_valid_shows_error_for_invalid_extra_form(event):
    """When an extra form is invalid and has errors, an error message is added."""
    invalid_form = SimpleNamespace(
        is_valid=lambda: False, errors=["Something went wrong"]
    )

    mixin = _make_form_signal_mixin(event)
    type(mixin).extra_forms = property(lambda self: [invalid_form])

    mixin.form_valid(SimpleNamespace())

    msgs = list(mixin.request._messages)
    assert len(msgs) == 1
    assert "Something went wrong" in str(msgs[0])


def test_form_signal_mixin_form_valid_skips_invalid_extra_form_without_errors(event):
    """When extra form is invalid but has no errors, nothing happens."""
    invalid_form = SimpleNamespace(is_valid=lambda: False, errors=[])

    mixin = _make_form_signal_mixin(event)
    type(mixin).extra_forms = property(lambda self: [invalid_form])

    mixin.form_valid(SimpleNamespace())

    assert len(list(mixin.request._messages)) == 0


def test_form_signal_mixin_form_valid_handles_integrity_error(event):
    """When extra form save raises IntegrityError, error message is shown."""

    def raise_integrity():
        raise IntegrityError("duplicate")

    valid_form = SimpleNamespace(
        is_valid=lambda: True, save=raise_integrity, label=None
    )

    mixin = _make_form_signal_mixin(event)
    type(mixin).extra_forms = property(lambda self: [valid_form])

    mixin.form_valid(SimpleNamespace())

    assert len(list(mixin.request._messages)) == 1


def test_form_signal_mixin_form_valid_handles_validation_error_with_label(event):
    """When extra form save raises ValidationError, error message includes
    the form label."""

    def raise_validation():
        raise ValidationError("bad data")

    valid_form = SimpleNamespace(
        is_valid=lambda: True, save=raise_validation, label="My Plugin"
    )

    mixin = _make_form_signal_mixin(event)
    type(mixin).extra_forms = property(lambda self: [valid_form])

    mixin.form_valid(SimpleNamespace())

    msgs = list(mixin.request._messages)
    assert len(msgs) == 1
    assert "[My Plugin]" in str(msgs[0])


# --- FormLoggingMixin ---


def test_form_logging_mixin_get_log_kwargs_returns_user_and_orga(event):
    user = UserFactory()
    mixin = _make_form_logging_mixin(event, user)
    assert mixin.get_log_kwargs() == {"person": user, "orga": True}


def test_form_logging_mixin_get_log_action_returns_dotted_action(event):
    user = UserFactory()
    mixin = _make_form_logging_mixin(event, user, action="update")
    assert mixin.get_log_action() == ".update"


def test_form_logging_mixin_form_valid_shows_success_message(event):
    user = UserFactory()
    mixin = _make_form_logging_mixin(event, user, action="update")

    form = SimpleNamespace(
        save=lambda: None, instance=SimpleNamespace(pk=None), has_changed=lambda: False
    )
    mixin.form_valid(form)

    msgs = list(mixin.request._messages)
    assert len(msgs) == 1
    assert str(msgs[0]) == str(phrases.base.saved)


def test_form_logging_mixin_form_valid_skip_logging_delegates_to_super(event):
    user = UserFactory()
    mixin = _make_form_logging_mixin(event, user, action="update")

    form = SimpleNamespace(
        save=lambda: None, instance=SimpleNamespace(pk=None), has_changed=lambda: False
    )
    result = mixin.form_valid(form, skip_logging=True)
    assert result.status_code == 302


def test_form_logging_mixin_form_valid_logs_action_with_old_and_new_data(event):
    """When form.has_changed() and the object supports get_instance_data,
    old and new data are passed to log_action."""
    user = UserFactory()
    logged = []

    with scopes_disabled():
        tag = TagFactory(event=event, tag="Original", color="#aabbcc")

    tag.log_action = lambda action, **kw: logged.append((action, kw))
    mixin = _make_form_logging_mixin(event, user, action="update", obj=tag)

    def save():
        tag.tag = "Updated"
        tag.save()

    form = SimpleNamespace(save=save, instance=tag, has_changed=lambda: True)
    with scopes_disabled():
        mixin.form_valid(form)

    assert len(logged) == 1
    action, kwargs = logged[0]
    assert action == ".update"
    assert "old_data" in kwargs
    assert "new_data" in kwargs
    assert kwargs["old_data"]["tag"] == "Original"


def test_form_logging_mixin_form_valid_logs_without_get_instance_data(event):
    """When the object has log_action but no get_instance_data,
    logging still works without old/new data."""
    user = UserFactory()
    logged = []

    obj = SimpleNamespace(
        pk=1, log_action=lambda action, **kw: logged.append((action, kw))
    )

    mixin = _make_form_logging_mixin(event, user, action="update", obj=obj)

    form = SimpleNamespace(save=lambda: None, instance=obj, has_changed=lambda: True)
    mixin.form_valid(form)

    assert len(logged) == 1
    action, kwargs = logged[0]
    assert action == ".update"
    assert "old_data" not in kwargs
    assert "new_data" not in kwargs


def test_form_logging_mixin_form_valid_no_message_for_unknown_action(event):
    """When the action has no matching message, no success message is shown."""
    user = UserFactory()
    mixin = _make_form_logging_mixin(event, user, action="custom_action")

    form = SimpleNamespace(
        save=lambda: None, instance=SimpleNamespace(pk=None), has_changed=lambda: False
    )
    mixin.form_valid(form)

    assert len(list(mixin.request._messages)) == 0


def test_form_logging_mixin_form_valid_skip_logging_without_super(event):
    """When skip_logging=True and parent has no form_valid,
    _save_form is used instead."""
    user = UserFactory()

    class TestMixin(FormLoggingMixin):
        def get_success_url(self):
            return "/"

    mixin = TestMixin()
    mixin.request = _with_messages(make_request(event, user=user))
    mixin.object = None
    mixin.action = "update"

    form = SimpleNamespace(
        save=lambda: None, instance=SimpleNamespace(pk=None), has_changed=lambda: False
    )
    result = mixin.form_valid(form, skip_logging=True)
    assert result.status_code == 302


# --- CreateOrUpdateView ---


@pytest.mark.parametrize(
    ("permission_action", "expected"), (("create", ".create"), ("update", ".update"))
)
def test_create_or_update_view_get_log_action(event, permission_action, expected):
    view = CreateOrUpdateView()
    view.permission_action = permission_action
    assert view.get_log_action() == expected


# --- GenericLoginView ---


def test_generic_login_view_get_password_reset_link_returns_none(event):
    view = GenericLoginView()
    view.request = make_request(event)
    assert view.get_password_reset_link() is None


def test_generic_login_view_dispatch_redirects_authenticated_user(event):
    user = UserFactory()

    class TestLoginView(GenericLoginView):
        @property
        def success_url(self):
            return "/orga/"

    view = TestLoginView()
    view.request = make_request(event, user=user)
    view.kwargs = {}
    view.args = []

    response = view.dispatch(view.request)
    assert response.status_code == 302
    assert response.url == "/orga/"


def test_generic_login_view_dispatch_redirects_on_no_reverse_match(event):
    """When get_success_url raises NoReverseMatch, falls back to
    self.success_url."""
    user = UserFactory()

    class TestLoginView(GenericLoginView):
        @property
        def success_url(self):
            return "/fallback/"

        def get_success_url(self, ignore_next=False):
            raise NoReverseMatch("no match")

    view = TestLoginView()
    view.request = make_request(event, user=user)
    view.kwargs = {}
    view.args = []

    response = view.dispatch(view.request)
    assert response.status_code == 302
    assert response.url == "/fallback/"


def test_generic_login_view_get_next_url_or_fallback_returns_next_url():
    request = _rf.get("/", QUERY_STRING="next=/dashboard/")
    result = GenericLoginView.get_next_url_or_fallback(request, "/fallback/")
    assert result == "/dashboard/"


def test_generic_login_view_get_next_url_or_fallback_returns_fallback_when_ignore_next():
    request = _rf.get("/", QUERY_STRING="next=/dashboard/")
    result = GenericLoginView.get_next_url_or_fallback(
        request, "/fallback/", ignore_next=True
    )
    assert result == "/fallback/"


def test_generic_login_view_get_next_url_or_fallback_preserves_extra_params():
    request = _rf.get("/", QUERY_STRING="page=2&sort=name")
    result = GenericLoginView.get_next_url_or_fallback(request, "/fallback/")
    assert result.startswith("/fallback/?")
    assert "page=2" in result
    assert "sort=name" in result


def test_generic_login_view_get_redirect_falls_back_on_no_reverse_match(event):
    """When get_success_url raises NoReverseMatch, retries with
    ignore_next=True."""
    view = GenericLoginView()
    view.request = make_request(event)

    call_count = 0

    def counted_success_url(ignore_next=False):
        nonlocal call_count
        call_count += 1
        if not ignore_next:
            raise NoReverseMatch("no match")
        return "/safe/"

    view.get_success_url = counted_success_url
    response = view.get_redirect()
    assert response.status_code == 302
    assert response.url == "/safe/"
    assert call_count == 2


def test_generic_login_view_success_url_property_raises_not_implemented():
    view = GenericLoginView()
    with pytest.raises(NotImplementedError):
        _ = view.success_url


def test_generic_login_view_get_form_kwargs_includes_request_and_reset_link(event):
    class TestLoginView(GenericLoginView):
        @property
        def success_url(self):
            return "/orga/"

    view = TestLoginView()
    request = make_request(event)
    request.method = "GET"
    view.request = request
    view.initial = {}
    view.prefix = None
    kwargs = view.get_form_kwargs()
    assert kwargs["request"] is request
    assert kwargs["password_reset_link"] is None
    assert "/orga/" in kwargs["success_url"]


# --- GenericResetView ---


def test_generic_reset_view_form_valid_with_no_user_redirects(event):
    """When user is None, shows success message and redirects."""
    view = GenericResetView()
    view.request = _with_messages(make_request(event))
    view.get_success_url = lambda: "/login/"

    form = SimpleNamespace(cleaned_data={"user": None})
    response = view.form_valid(form)

    assert response.status_code == 302
    assert response.url == "/login/"


def test_generic_reset_view_form_valid_with_recent_reset_redirects(event):
    """When pw_reset_time is recent (within 24h), blocks reset."""
    user = UserFactory()
    user.pw_reset_time = now() - dt.timedelta(hours=1)
    user.save()

    view = GenericResetView()
    view.request = _with_messages(make_request(event))
    view.get_success_url = lambda: "/login/"

    form = SimpleNamespace(cleaned_data={"user": user})
    response = view.form_valid(form)

    assert response.status_code == 302
    assert response.url == "/login/"


def test_generic_reset_view_form_valid_handles_send_mail_exception(event):
    """When reset_password raises SendMailException, shows error."""
    user = UserFactory()
    user.pw_reset_time = None
    user.save()

    def raise_send_mail(*args, **kwargs):
        raise SendMailException("mail broken")

    user.reset_password = raise_send_mail

    view = GenericResetView()
    view.template_name = "orga/auth/reset.html"
    request = _with_messages(make_request(event, method="get"))
    request.resolver_match = SimpleNamespace(namespaces=["orga"])
    view.request = request
    view.args = []
    view.kwargs = {}
    view.get_success_url = lambda: "/login/"

    form = SimpleNamespace(cleaned_data={"user": user})
    view.form_valid(form)

    msgs = list(request._messages)
    assert any(str(phrases.base.error_sending_mail) in str(m) for m in msgs)


def test_generic_reset_view_form_valid_success_sends_reset_and_redirects(event):
    """When reset_password succeeds, logs the action and redirects."""
    user = UserFactory()
    user.pw_reset_time = None
    user.save()

    reset_calls = []
    user.reset_password = lambda **kwargs: reset_calls.append(kwargs)

    log_calls = []
    user.log_action = lambda action_type, **kw: log_calls.append(action_type)

    view = GenericResetView()
    request = _with_messages(make_request(event))
    request.resolver_match = SimpleNamespace(namespaces=["orga"])
    view.request = request
    view.args = []
    view.kwargs = {}
    view.get_success_url = lambda: "/login/"

    form = SimpleNamespace(cleaned_data={"user": user})
    response = view.form_valid(form)

    assert response.status_code == 302
    assert response.url == "/login/"
    assert len(reset_calls) == 1
    assert "pretalx.user.password.reset" in log_calls


# --- CRUDView ---


@pytest.mark.parametrize(
    ("action", "expected"),
    (("list", True), ("create", True), ("update", False), ("delete", False)),
)
def test_crud_view_is_generic(event, action, expected):
    view = _make_crud_view(event, action=action)
    assert view.is_generic is expected


def test_crud_view_permission_denied_raises_http404_for_non_cfp(event):
    view = _make_crud_view(event, action="list")
    with pytest.raises(Http404):
        view.permission_denied()


def test_crud_view_permission_denied_redirects_anonymous_cfp_user(event):
    """Anonymous users in CFP namespace get redirected to login."""
    view = _make_crud_view(event, action="list")
    view.request.resolver_match = SimpleNamespace(namespaces=["cfp"])
    response = view.permission_denied()
    assert response.status_code == 302
    assert event.urls.login in response.url


def test_crud_view_permission_denied_redirect_includes_get_params(event):
    view = _make_crud_view(event, action="list")
    view.request.resolver_match = SimpleNamespace(namespaces=["cfp"])
    view.request.GET = QueryDict("page=2&sort=name")
    response = view.permission_denied()
    assert "page=2" in response.url
    assert "sort=name" in response.url


def test_crud_view_dispatch_calls_permission_denied_on_no_access(event):
    """dispatch raises Http404 when has_permission is False."""
    view = _make_crud_view(event, action="list")
    view.get_generic_permission_object = lambda: event
    with pytest.raises(Http404):
        view.dispatch(view.request)


def test_crud_view_list_with_pagination(event):
    user = make_orga_user(event)
    view = _make_crud_view(event, user=user, action="list")
    view.get_generic_permission_object = lambda: event
    view.filter_fields = []
    with scopes_disabled():
        view.get_queryset = lambda: Tag.objects.filter(event=event)
        view.get_paginate_by = lambda: 10
        view.render_to_response = lambda ctx: ctx
        context = view.list(view.request)
    assert "page_obj" in context
    assert "paginator" in context


def test_crud_view_detail_returns_context_with_instance(event):
    user = make_orga_user(event)
    with scopes_disabled():
        tag = TagFactory(event=event)
    view = _make_crud_view(event, user=user, action="detail", obj=tag)
    view.get_generic_permission_object = lambda: event
    view.render_to_response = lambda ctx: ctx
    context = view.detail(view.request)
    assert context["instance"] is tag


def test_crud_view_get_table_data_returns_filtered_queryset(event):
    user = make_orga_user(event)
    view = _make_crud_view(event, user=user, action="list")

    with scopes_disabled():
        tag = TagFactory(event=event)
        view.filter_fields = []
        view.get_queryset = lambda: Tag.objects.filter(event=event)
        data = list(view.get_table_data())
    assert tag in data


@pytest.mark.parametrize(
    "queryset_attr",
    (None, "explicit"),
    ids=("from_default_manager", "from_explicit_queryset"),
)
def test_crud_view_get_queryset(event, queryset_attr):
    view = _make_crud_view(event, action="list")
    with scopes_disabled():
        if queryset_attr == "explicit":
            view.queryset = Tag.objects.filter(event=event)
        else:
            view.queryset = None
        qs = view.get_queryset()
    assert qs.model is Tag


def test_crud_view_get_success_url_returns_next_url_when_present(event):
    user = make_orga_user(event)
    view = _make_crud_view(event, user=user, action="update")
    view.request.GET = QueryDict("next=/custom/")
    assert view.get_success_url() == "/custom/"


def test_crud_view_get_success_url_returns_list_for_delete(event):
    user = make_orga_user(event)
    view = _make_crud_view(event, user=user, action="delete")
    view.reverse = lambda action, instance=None: f"/reversed/{action}/"
    assert view.get_success_url() == "/reversed/list/"


def test_crud_view_get_success_url_returns_detail_when_not_detail_is_update(event):
    """When detail_is_update is False and not delete, returns detail."""
    user = make_orga_user(event)
    view = _make_crud_view(event, user=user, action="update")
    view.detail_is_update = False
    view.reverse = lambda action, instance=None: f"/reversed/{action}/"
    assert view.get_success_url() == "/reversed/detail/"


@pytest.mark.parametrize(
    ("page_param", "expected_page"),
    (("last", 1), ("abc", 1), ("999", 1)),
    ids=("page_last", "invalid_page_number", "out_of_range_page"),
)
def test_crud_view_paginate_queryset_edge_cases(event, page_param, expected_page):
    view = _make_crud_view(event, action="list")
    qs = Tag.objects.none()
    view.request.GET = QueryDict(f"page={page_param}")
    page = view.paginate_queryset(qs, 10)
    assert page.number == expected_page


@pytest.mark.parametrize(
    ("action", "custom_name", "expected"),
    (
        ("update", None, "tag"),
        ("list", None, "tag_list"),
        ("update", "my_tag", "my_tag"),
    ),
    ids=("model_name_for_single", "appends_list_for_list", "custom_name"),
)
def test_crud_view_get_context_object_name(event, action, custom_name, expected):
    view = _make_crud_view(event, action=action)
    if custom_name:
        view.context_object_name = custom_name
    assert view.get_context_object_name() == expected


def test_crud_view_reverse_includes_namespace(event):
    user = make_orga_user(event)
    view = _make_crud_view(event, user=user, action="list", namespace="orga")

    url_name = f"{view.url_name}.list"
    expected = f"{view.namespace}:{url_name}"
    assert expected == "orga:test.tag.list"


def test_crud_view_reverse_without_namespace(event):
    """When namespace is empty, NoReverseMatch is raised (no registered URL)
    but the branch without namespace prefix is still exercised."""
    view = _make_crud_view(event, action="list", namespace="")
    with pytest.raises(NoReverseMatch):
        view.reverse("list")


def test_crud_view_get_generic_title_returns_str_of_instance(event):
    with scopes_disabled():
        tag = TagFactory(event=event, tag="Python")
    view = _make_crud_view(event, action="update")
    assert view.get_generic_title(instance=tag) == "Python"


def test_crud_view_get_generic_title_returns_model_name_without_instance(event):
    view = _make_crud_view(event, action="list")
    assert view.get_generic_title() == "Tag"


def test_crud_view_get_permission_object_returns_self_object(event):
    with scopes_disabled():
        tag = TagFactory(event=event)
    view = _make_crud_view(event, action="update", obj=tag)
    assert view.get_permission_object() is tag


def test_crud_view_get_permission_required_uses_model_get_perm(event):
    view = _make_crud_view(event, action="list")
    assert view.get_permission_required() == Tag.get_perm("list")


def test_crud_view_get_form_kwargs_includes_locales_for_i18n_form(event):
    view = _make_crud_view(event, action="create")
    view.form_class = PretalxI18nModelForm
    kwargs = view.get_form_kwargs()
    assert kwargs["locales"] == event.locales


def test_crud_view_get_context_data_for_object(event):
    user = make_orga_user(event)
    with scopes_disabled():
        tag = TagFactory(event=event)

    view = _make_crud_view(event, user=user, action="update", obj=tag)
    view.get_generic_permission_object = lambda: event
    context = view.get_context_data()
    assert context["object"] is tag
    assert context["tag"] is tag
    assert context["action"] == "update"


def test_crud_view_get_context_data_for_object_list(event):
    user = make_orga_user(event)

    view = _make_crud_view(event, user=user, action="list")
    view.get_generic_permission_object = lambda: event
    view.object_list = Tag.objects.none()
    context = view.get_context_data()
    assert "object_list" in context
    assert "tag_list" in context


def test_crud_view_get_context_data_without_create_permission(event):
    """When has_create_permission is False, create_url is not set."""
    user = make_orga_user(event)

    view = _make_crud_view(event, user=user, action="list")
    view.get_generic_permission_object = lambda: event
    view.object_list = Tag.objects.none()
    view.__dict__["has_create_permission"] = False
    context = view.get_context_data()
    assert "create_url" not in context


def test_crud_view_get_context_data_shows_history_for_detail(event):
    user = make_orga_user(event)
    with scopes_disabled():
        tag = TagFactory(event=event)

    view = _make_crud_view(event, user=user, action="detail", obj=tag)
    view.get_generic_permission_object = lambda: event
    context = view.get_context_data()
    assert "show_history" in context


def test_crud_view_get_context_data_skips_context_object_name_when_empty(event):
    """When context_object_name is empty string, name assignment is skipped."""
    user = make_orga_user(event)
    with scopes_disabled():
        tag = TagFactory(event=event)

    view = _make_crud_view(event, user=user, action="update")
    view.object = tag
    view.context_object_name = ""
    view.get_generic_permission_object = lambda: event
    context = view.get_context_data()
    assert context["object"] is tag
    assert "tag" not in context or context.get("tag") is not tag


def test_crud_view_get_context_data_skips_list_name_when_empty(event):
    """When context_object_name is empty for list, no named key is set."""
    user = make_orga_user(event)

    view = _make_crud_view(event, user=user, action="list")
    view.context_object_name = ""
    view.get_generic_permission_object = lambda: event
    view.object_list = Tag.objects.none()
    context = view.get_context_data()
    assert "object_list" in context
    assert "_list" not in context


def test_crud_view_perform_delete_no_message(event):
    """When no message matches the action, no message is shown."""
    user = make_orga_user(event)
    with scopes_disabled():
        tag = TagFactory(event=event)

    view = _make_crud_view(event, user=user, action="delete", obj=tag)
    view.messages = {}

    deleted = []
    tag.delete = lambda log_kwargs=None: deleted.append(True)
    view.perform_delete()
    assert deleted == [True]
    assert len(list(view.request._messages)) == 0


def test_crud_view_get_reverse_kwargs_with_instance(event):
    view = _make_crud_view(event, action="update")
    with scopes_disabled():
        tag = TagFactory(event=event)
    kwargs = view.get_reverse_kwargs("update", instance=tag)
    assert kwargs == {"pk": tag.pk}


# --- CRUDView class methods ---


@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("list", "tags/"),
        ("create", "tags/new/"),
        ("detail", "tags/<int:pk>/"),
        ("delete", "tags/<int:pk>/delete/"),
    ),
)
def test_crud_view_get_url_pattern(action, expected):
    assert CRUDView.get_url_pattern("tags", action) == expected


def test_crud_view_get_url_pattern_update_with_detail_is_update():
    """When detail_is_update is True, update URL is same as detail."""
    CRUDView.detail_is_update = True
    assert CRUDView.get_url_pattern("tags", "update") == "tags/<int:pk>/"


def test_crud_view_get_url_pattern_update_without_detail_is_update():
    """When detail_is_update is False, update has /edit/ suffix."""

    class TestView(CRUDView):
        detail_is_update = False

    assert TestView.get_url_pattern("tags", "update") == "tags/<int:pk>/edit/"


def test_crud_view_get_urls_excludes_detail_when_detail_is_update():
    urls = CRUDView.get_urls("tags", "tag", namespace="orga")
    url_names = [u.name for u in urls]
    assert "tag.detail" not in url_names
    assert "tag.list" in url_names
    assert "tag.update" in url_names


def test_crud_view_get_urls_includes_detail_when_not_detail_is_update():
    class TestView(CRUDView):
        detail_is_update = False
        model = Tag

    urls = TestView.get_urls("tags", "tag", namespace="orga")
    url_names = [u.name for u in urls]
    assert "tag.detail" in url_names


def test_crud_view_as_view_returns_callable():
    view_fn = CRUDView.as_view(action="list", url_name="tag", namespace="orga")
    assert callable(view_fn)
    assert view_fn.view_class is CRUDView


def test_crud_handler_map_has_expected_actions():
    assert set(CRUDHandlerMap.keys()) == {
        "list",
        "detail",
        "create",
        "update",
        "delete",
    }


# --- CRUDView template names ---


def test_crud_view_list_template_names():
    view = CRUDView()
    view.model = Tag
    view.action = "list"
    view.template_namespace = None
    templates = view.get_template_names()
    assert "common/tag/list.html" in templates
    assert "common/tag_list.html" in templates
    assert templates[-1] == "common/generic/list.html"


def test_crud_view_create_template_names_include_form_fallback():
    view = CRUDView()
    view.model = Tag
    view.action = "create"
    view.template_namespace = None
    templates = view.get_template_names()
    assert "common/tag/_form.html" in templates
    assert "common/tag_form.html" in templates
    assert templates[-1] == "common/generic/create.html"


def test_crud_view_custom_namespace_template_names():
    view = CRUDView()
    view.model = Tag
    view.action = "list"
    view.template_namespace = "orga/submission"
    templates = view.get_template_names()
    assert "orga/submission/tag/list.html" in templates


# --- OrgaTableMixin ---


def test_orga_table_mixin_get_paginate_by_returns_none_when_table_class_set(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user, table_class="SomeTable")
    assert mixin.get_paginate_by() is None


def test_orga_table_mixin_get_paginate_by_returns_default(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    assert mixin.get_paginate_by() == 50


def test_orga_table_mixin_get_paginate_by_handles_page_size_param(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user, request_get="page_size=25")
    assert mixin.get_paginate_by() == 25


def test_orga_table_mixin_get_paginate_by_clamps_to_max_page_size(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user, request_get="page_size=9999")
    mixin.max_page_size = 100
    assert mixin.get_paginate_by() == 100


def test_orga_table_mixin_get_paginate_by_invalid_page_size_returns_default(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user, request_get="page_size=abc")
    assert mixin.get_paginate_by() == 50


def test_orga_table_mixin_get_paginate_by_stores_page_size_in_session(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user, request_get="page_size=30")
    mixin.get_paginate_by()
    assert mixin.request.session["stored_page_size_tag.list"] == 30


def test_orga_table_mixin_get_paginate_by_uses_table_page_size_when_set(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    mixin._table_page_size = 15
    assert mixin.get_paginate_by() == 15


def test_orga_table_mixin_get_paginate_by_stores_in_preferences(event):
    """When user is authenticated and table has event, page_size is stored
    in user preferences."""
    user = UserFactory()
    mixin = _make_table_mixin(event, user, request_get="page_size=20")
    mixin.request.user = user
    mixin.table = SimpleNamespace(name="test_table", event=event)
    assert mixin.get_paginate_by() == 20


def test_orga_table_mixin_get_paginate_by_no_clamping_when_max_page_size_zero(event):
    """When max_page_size is 0/None, no clamping happens."""
    user = make_orga_user(event)
    mixin = OrgaTableMixin()
    mixin.table_class = None
    mixin.table_template_name = "django_tables2/table.html"
    mixin.max_page_size = 0
    request = make_request(event, user=user)
    request.resolver_match = SimpleNamespace(url_name="tag.list")
    request.GET = QueryDict("page_size=200")
    mixin.request = request
    assert mixin.get_paginate_by() == 200


def test_orga_table_mixin_get_context_data_with_table_without_page(event):
    """When table exists but has no page, is_paginated is not True."""
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    mixin.get_table = lambda *a, **kw: SimpleNamespace(page=None, paginator=None)
    mixin.object_list = []
    context = mixin.get_context_data()
    assert context.get("is_paginated") is not True


def test_orga_table_mixin_get_table_kwargs_adds_event_and_user(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    kwargs = mixin.get_table_kwargs()
    assert kwargs["event"] is event
    assert kwargs["user"] is user


def test_orga_table_mixin_get_table_returns_none_when_no_table_class(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    assert mixin.get_table() is None


def test_orga_table_mixin_get_context_data_with_table_page(event):
    """When table has a page, context gets page_obj and paginator."""
    fake_paginator = SimpleNamespace(count=10)
    fake_page = SimpleNamespace(paginator=fake_paginator, has_other_pages=lambda: True)
    fake_table = SimpleNamespace(page=fake_page, paginator=fake_paginator)

    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    mixin.get_table = lambda *a, **kw: fake_table
    mixin.object_list = []
    context = mixin.get_context_data()
    assert context["page_obj"] is fake_page
    assert context["paginator"] is fake_paginator
    assert context["is_paginated"] is True


def test_orga_table_mixin_get_template_names_returns_htmx_partial(event):
    """For HTMX requests targeting table-content, returns partial template."""
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    mixin.table_class = "SomeTable"
    mixin.request.META["HTTP_HX_REQUEST"] = "true"
    mixin.request.META["HTTP_HX_TARGET"] = "table-content-main"
    assert mixin.get_template_names() == ["django_tables2/table.html#table-content"]


def test_orga_table_mixin_get_template_names_returns_normal_for_non_htmx(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    assert mixin.get_template_names() == ["test/template.html"]


def test_orga_table_mixin_dispatch_sets_hx_push_url_for_htmx(event):
    """HTMX table requests get HX-Push-Url header."""
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    mixin.table_class = "SomeTable"
    mixin.request.META["HTTP_HX_REQUEST"] = "true"
    mixin.request.META["HTTP_HX_TARGET"] = "table-content-main"

    headers = {}

    class FakeResponse:
        status_code = 200

        def __setitem__(self, key, value):
            headers[key] = value

    class TestParent:
        def dispatch(self, request, *args, **kwargs):
            return FakeResponse()

    original_bases = type(mixin).__bases__
    mixin.__class__.__bases__ = (OrgaTableMixin, TestParent)
    try:
        mixin.dispatch(mixin.request)
        assert "HX-Push-Url" in headers
    finally:
        mixin.__class__.__bases__ = original_bases


# --- OrgaCRUDView ---


def test_orga_crud_view_event_property(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    assert view.event is event


def test_orga_crud_view_organiser_property(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    view.request.organiser = event.organiser
    assert view.organiser is event.organiser


def test_orga_crud_view_get_reverse_kwargs_includes_event_slug(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    kwargs = view.get_reverse_kwargs("list")
    assert kwargs["event"] == event.slug


def test_orga_crud_view_get_reverse_kwargs_includes_organiser_slug(event):
    """When event is not set but organiser is, uses organiser slug."""
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    del view.request.event
    view.request.organiser = event.organiser
    view.__dict__.pop("event", None)
    view.__dict__.pop("organiser", None)
    kwargs = view.get_reverse_kwargs("list")
    assert kwargs.get("organiser") == event.organiser.slug


def test_orga_crud_view_get_reverse_kwargs_without_event_or_organiser(event):
    """When neither event nor organiser is set, result has neither."""
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    del view.request.event
    view.__dict__.pop("event", None)
    view.__dict__.pop("organiser", None)
    kwargs = view.get_reverse_kwargs("list")
    assert "event" not in kwargs
    assert "organiser" not in kwargs


def test_orga_crud_view_get_form_kwargs_includes_event(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    view.form_class = forms.Form
    kwargs = view.get_form_kwargs()
    assert kwargs["event"] is event


def test_orga_crud_view_get_form_kwargs_includes_organiser_when_no_event(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    view.form_class = forms.Form
    del view.request.event
    view.request.organiser = event.organiser
    view.__dict__.pop("event", None)
    kwargs = view.get_form_kwargs()
    assert kwargs.get("organiser") is event.organiser


def test_orga_crud_view_get_form_kwargs_without_event_or_organiser(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    view.form_class = forms.Form
    del view.request.event
    view.__dict__.pop("event", None)
    view.__dict__.pop("organiser", None)
    kwargs = view.get_form_kwargs()
    assert "event" not in kwargs
    assert "organiser" not in kwargs


def test_orga_crud_view_form_valid_without_event_skips_event_assignment(event):
    """When event is None, form_valid does not set event on instance."""
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user, action="update")
    del view.request.event
    view.__dict__.pop("event", None)
    view.get_success_url = lambda: "/"

    instance = SimpleNamespace(pk=1, event=None)
    form = SimpleNamespace(
        save=lambda: None, instance=instance, has_changed=lambda: False
    )
    result = view.form_valid(form)
    assert result.status_code == 302
    assert instance.event is None


def test_orga_crud_view_get_generic_permission_object_returns_event(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    assert view.get_generic_permission_object() is event


def test_orga_crud_view_get_generic_permission_object_returns_organiser(event):
    """When event is None, returns organiser."""
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    del view.request.event
    view.request.organiser = event.organiser
    view.__dict__.pop("event", None)
    assert view.get_generic_permission_object() is event.organiser


def test_orga_crud_view_get_log_kwargs_includes_orga_true(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    assert view.get_log_kwargs()["orga"] is True


def test_orga_crud_view_get_template_names_includes_orga_generic(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user, action="list")
    templates = view.get_template_names()
    assert templates[-1] == "orga/generic/list.html"


def test_orga_crud_view_get_table_kwargs_includes_permissions(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    kwargs = view.get_table_kwargs()
    assert "has_update_permission" in kwargs
    assert "has_delete_permission" in kwargs
