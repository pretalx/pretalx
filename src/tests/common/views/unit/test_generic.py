# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
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

from pretalx.common.exceptions import SendMailException
from pretalx.common.forms.mixins import PretalxI18nModelForm
from pretalx.common.models import ActivityLog
from pretalx.common.signals import EventPluginSignal
from pretalx.common.text.phrases import phrases
from pretalx.common.views.generic import (
    CreateOrUpdateView,
    CRUDView,
    FormLoggingMixin,
    FormSignalMixin,
    GenericLoginView,
    GenericResetView,
    OrgaCRUDView,
    OrgaTableMixin,
)
from pretalx.submission.models import Tag
from tests.factories import ActivityLogFactory, TagFactory, UserFactory
from tests.utils import make_orga_user, make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

_rf = RequestFactory()
_test_form_signal = EventPluginSignal()


def _with_messages(request):
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


def _make_table_mixin(
    event, user, *, table_class=None, request_get=None, request_headers=None
):
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
    request = make_request(event, user=user, headers=request_headers)
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


# --- FormSignalMixin ---


def test_form_signal_mixin_extra_forms_collects_handler_responses(
    event, register_signal_handler
):
    form_a = SimpleNamespace(name="a")
    form_b = SimpleNamespace(name="b")
    form_single = SimpleNamespace(name="single")

    def list_handler(signal, sender, **kwargs):
        return [form_a, form_b]

    def single_handler(signal, sender, **kwargs):
        return form_single

    def falsy_handler(signal, sender, **kwargs):
        return None

    def broken_handler(signal, sender, **kwargs):
        raise ValueError("broken plugin")

    for handler in (list_handler, single_handler, falsy_handler, broken_handler):
        register_signal_handler(_test_form_signal, handler)
    mixin = _make_form_signal_mixin(
        event,
        extra_forms_signal="tests.common.views.unit.test_generic._test_form_signal",
    )
    mixin.get_form_kwargs = dict

    assert mixin.extra_forms == [form_a, form_b, form_single]


def test_form_signal_mixin_get_context_data_includes_extra_forms(event):
    mixin = _make_form_signal_mixin(event)

    context = mixin.get_context_data(foo="bar")

    assert mixin.extra_forms == []
    assert context == {"foo": "bar", "extra_forms": []}


def _raise(exc):
    def raiser():
        raise exc

    return raiser


@pytest.mark.parametrize(
    ("extra_form", "expected_messages"),
    (
        pytest.param(
            SimpleNamespace(is_valid=lambda: False, errors=["Something went wrong"]),
            ["Something went wrong"],
            id="invalid_with_errors",
        ),
        pytest.param(
            SimpleNamespace(is_valid=lambda: False, errors=[]),
            [],
            id="invalid_without_errors",
        ),
        pytest.param(
            SimpleNamespace(
                is_valid=lambda: True,
                save=_raise(IntegrityError("duplicate")),
                label=None,
            ),
            ["Some changes could not be saved."],
            id="integrity_error",
        ),
        pytest.param(
            SimpleNamespace(
                is_valid=lambda: True,
                save=_raise(ValidationError("bad data")),
                label="My Plugin",
            ),
            ["[My Plugin] Some changes could not be saved."],
            id="validation_error_with_label",
        ),
    ),
)
def test_form_signal_mixin_form_valid_reports_extra_form_failures(
    event, extra_form, expected_messages
):
    mixin = _make_form_signal_mixin(event)
    type(mixin).extra_forms = property(lambda self: [extra_form])

    mixin.form_valid(SimpleNamespace())

    assert [str(m) for m in mixin.request._messages] == expected_messages


# --- FormLoggingMixin ---


def test_form_logging_mixin_form_valid_shows_message_for_known_actions_only(event):
    user = UserFactory()
    form = SimpleNamespace(
        save=lambda: None, instance=SimpleNamespace(pk=None), has_changed=lambda: False
    )

    mixin = _make_form_logging_mixin(event, user, action="update")
    mixin.form_valid(form)

    assert mixin.get_log_kwargs() == {"person": user, "orga": True}
    assert [str(m) for m in mixin.request._messages] == [str(phrases.base.saved)]

    mixin = _make_form_logging_mixin(event, user, action="custom_action")
    mixin.form_valid(form)

    assert list(mixin.request._messages) == []


def test_form_logging_mixin_form_valid_skip_logging_delegates_to_super(event):
    user = UserFactory()
    mixin = _make_form_logging_mixin(event, user, action="update")

    form = SimpleNamespace(
        save=lambda: None, instance=SimpleNamespace(pk=None), has_changed=lambda: False
    )
    result = mixin.form_valid(form, skip_logging=True)
    assert result.status_code == 302


def test_form_logging_mixin_form_valid_logs_action_with_old_and_new_data(event):
    user = UserFactory()
    logged = []

    tag = TagFactory(event=event, tag="Original", color="#aabbcc")

    tag.log_action = lambda action, **kw: logged.append((action, kw))
    mixin = _make_form_logging_mixin(event, user, action="update", obj=tag)

    def save():
        tag.tag = "Updated"
        tag.save()

    form = SimpleNamespace(save=save, instance=tag, has_changed=lambda: True)
    mixin.form_valid(form)

    assert len(logged) == 1
    action, kwargs = logged[0]
    assert action == ".update"
    assert "old_data" in kwargs
    assert "new_data" in kwargs
    assert kwargs["old_data"]["tag"] == "Original"


def test_form_logging_mixin_form_valid_logs_without_get_instance_data(event):
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


def test_form_logging_mixin_form_valid_skip_logging_without_super(event):
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


def test_generic_login_view_dispatch_redirects_authenticated_user(event):
    user = UserFactory()

    class TestLoginView(GenericLoginView):
        @property
        def success_url(self):
            return "/orga/"

    class BrokenLoginView(TestLoginView):
        def get_success_url(self, ignore_next=False):
            raise NoReverseMatch("no match")

    for view_class in (TestLoginView, BrokenLoginView):
        view = view_class()
        view.request = make_request(event, user=user)
        view.kwargs = {}
        view.args = []

        response = view.dispatch(view.request)

        assert response.status_code == 302
        assert response.url == "/orga/"


@pytest.mark.parametrize(
    ("query", "ignore_next", "expected"),
    (
        ("next=/dashboard/", False, "/dashboard/"),
        ("next=/dashboard/", True, "/fallback/"),
        ("page=2&sort=name", False, "/fallback/?page=2&sort=name"),
    ),
    ids=("next", "ignore_next", "preserves_extra_params"),
)
def test_generic_login_view_get_next_url_or_fallback(query, ignore_next, expected):
    request = _rf.get("/", QUERY_STRING=query)

    result = GenericLoginView.get_next_url_or_fallback(
        request, "/fallback/", ignore_next=ignore_next
    )

    assert result == expected


def test_generic_login_view_get_redirect_falls_back_on_no_reverse_match(event):
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


def test_generic_reset_view_form_valid_redirects_without_mail_for_no_or_recent_user(
    event,
):
    user = UserFactory(pw_reset_time=now() - dt.timedelta(hours=1))
    view = GenericResetView()
    view.request = _with_messages(make_request(event))
    view.get_success_url = lambda: "/login/"

    for form_user in (None, user):
        response = view.form_valid(SimpleNamespace(cleaned_data={"user": form_user}))

        assert response.status_code == 302
        assert response.url == "/login/"

    assert not ActivityLog.objects.filter(
        action_type="pretalx.user.password.reset"
    ).exists()


def test_generic_reset_view_form_valid_handles_send_mail_exception(event, monkeypatch):
    user = UserFactory(pw_reset_time=None)

    def raise_send_mail(*args, **kwargs):
        raise SendMailException("mail broken")

    monkeypatch.setattr("pretalx.common.views.generic.reset_password", raise_send_mail)

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


def test_generic_reset_view_form_valid_success_logs_action_exactly_once(event):
    user = UserFactory(pw_reset_time=None)

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
    actions = ActivityLog.objects.filter(
        person=user, action_type="pretalx.user.password.reset"
    )
    assert actions.count() == 1


# --- CRUDView ---


@pytest.mark.parametrize(
    ("action", "expected"),
    (("list", True), ("create", True), ("update", False), ("delete", False)),
)
def test_crud_view_is_generic(event, action, expected):
    view = _make_crud_view(event, action=action)
    assert view.is_generic is expected


def test_crud_view_permission_denied_redirects_only_anonymous_cfp_users(event):
    view = _make_crud_view(event, action="list")
    view.get_generic_permission_object = lambda: event

    with pytest.raises(Http404):
        view.permission_denied()
    with pytest.raises(Http404):
        view.dispatch(view.request)

    view.request.resolver_match = SimpleNamespace(namespaces=["cfp"])
    view.request.GET = QueryDict("page=2&sort=name")
    response = view.permission_denied()

    assert response.status_code == 302
    assert (
        response.url == f"http://testserver{event.urls.login}?next=/&page=2&sort=name"
    )


def test_crud_view_list_with_pagination(event):
    user = make_orga_user(event)
    view = _make_crud_view(event, user=user, action="list")
    view.get_generic_permission_object = lambda: event
    view.get_queryset = lambda: Tag.objects.filter(event=event)
    view.get_paginate_by = lambda: 10
    view.render_to_response = lambda ctx: ctx
    context = view.list(view.request)
    assert "page_obj" in context
    assert "paginator" in context


def test_crud_view_detail_returns_context_with_instance(event):
    user = make_orga_user(event)
    tag = TagFactory(event=event)
    view = _make_crud_view(event, user=user, action="detail", obj=tag)
    view.get_generic_permission_object = lambda: event
    view.render_to_response = lambda ctx: ctx
    context = view.detail(view.request)
    assert context["instance"] is tag


def test_crud_view_get_table_data_returns_filtered_queryset(event):
    user = make_orga_user(event)
    view = _make_crud_view(event, user=user, action="list")

    tag = TagFactory(event=event)
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
    if queryset_attr == "explicit":
        view.queryset = Tag.objects.filter(event=event)
    else:
        view.queryset = None
    qs = view.get_queryset()
    assert qs.model is Tag


def test_crud_view_get_success_url(event):
    user = make_orga_user(event)

    view = _make_crud_view(event, user=user, action="update")
    view.request.GET = QueryDict("next=/custom/")
    assert view.get_success_url() == "/custom/"

    view = _make_crud_view(event, user=user, action="update")
    view.reverse = lambda action, instance=None: f"/reversed/{action}/"
    assert view.get_success_url() == "/reversed/list/"
    view.detail_is_update = False
    assert view.get_success_url() == "/reversed/detail/"
    view.action = "delete"
    assert view.get_success_url() == "/reversed/list/"


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


def test_crud_view_reverse_without_namespace(event):
    view = _make_crud_view(event, action="list", namespace="")
    with pytest.raises(NoReverseMatch):
        view.reverse("list")


def test_crud_view_get_generic_title(event):
    tag = TagFactory(event=event, tag="Python")
    view = _make_crud_view(event, action="update")

    assert view.get_generic_title(instance=tag) == "Python"
    assert view.get_generic_title() == "Tag"


def test_crud_view_get_permission_object_returns_self_object(event):
    tag = TagFactory(event=event)
    view = _make_crud_view(event, action="update", obj=tag)
    assert view.get_permission_object() is tag


def test_crud_view_get_form_kwargs_includes_locales_for_i18n_form(event):
    view = _make_crud_view(event, action="create")
    view.form_class = PretalxI18nModelForm
    kwargs = view.get_form_kwargs()
    assert kwargs["locales"] == event.locales


def test_crud_view_get_context_data_for_object_list(event):
    user = make_orga_user(event)
    view = _make_crud_view(event, user=user, action="list")
    view.get_generic_permission_object = lambda: event
    view.reverse = lambda action, instance=None: f"/reversed/{action}/"
    view.object_list = Tag.objects.none()

    context = view.get_context_data()
    assert "object_list" in context
    assert "tag_list" in context
    assert context["create_url"] == "/reversed/create/"

    view.__dict__["has_create_permission"] = False
    view.context_object_name = ""
    context = view.get_context_data()
    assert "object_list" in context
    assert "tag_list" not in context
    assert "_list" not in context
    assert "create_url" not in context


@pytest.mark.parametrize("action", ("detail", "update"))
def test_crud_view_get_context_data_hides_history_without_log_entries(event, action):
    user = make_orga_user(event)
    tag = TagFactory(event=event)

    view = _make_crud_view(event, user=user, action=action, obj=tag)
    view.get_generic_permission_object = lambda: event
    context = view.get_context_data()

    assert view.history_log_entries == []
    assert "tablist" not in context
    assert context["object"] is tag
    assert context["tag"] is tag
    assert context["action"] == action


@pytest.mark.parametrize("action", ("detail", "update"))
def test_crud_view_get_context_data_shows_history_with_log_entries(event, action):
    user = make_orga_user(event)
    tag = TagFactory(event=event)
    log = ActivityLogFactory(event=event, content_object=tag)

    view = _make_crud_view(event, user=user, action=action, obj=tag)
    view.get_generic_permission_object = lambda: event
    context = view.get_context_data()

    assert view.history_log_entries == [log]
    assert context["tablist"] == {"edit": "Edit", "history": "History"}


@pytest.mark.parametrize("action", ("detail", "update"))
def test_crud_view_history_entries_not_queried_when_disabled(event, action):
    user = make_orga_user(event)
    tag = TagFactory(event=event)
    ActivityLogFactory(event=event, content_object=tag)

    view = _make_crud_view(event, user=user, action=action, obj=tag)
    view.get_generic_permission_object = lambda: event
    view.show_history = False
    view.get_history_entries = lambda: pytest.fail("should not be called")

    assert "tablist" not in view.get_context_data()


def test_crud_view_get_context_data_skips_context_object_name_when_empty(event):
    user = make_orga_user(event)
    tag = TagFactory(event=event)

    view = _make_crud_view(event, user=user, action="update")
    view.object = tag
    view.context_object_name = ""
    view.get_generic_permission_object = lambda: event
    context = view.get_context_data()
    assert context["object"] is tag
    assert "tag" not in context or context.get("tag") is not tag


def test_crud_view_perform_delete_no_message(event):
    user = make_orga_user(event)
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


def test_crud_view_get_url_pattern_update_depends_on_detail_is_update():
    class TestView(CRUDView):
        detail_is_update = False

    assert CRUDView.get_url_pattern("tags", "update") == "tags/<int:pk>/"
    assert TestView.get_url_pattern("tags", "update") == "tags/<int:pk>/edit/"


def test_crud_view_get_urls_includes_detail_only_when_not_detail_is_update():
    class TestView(CRUDView):
        detail_is_update = False
        model = Tag

    assert [u.name for u in CRUDView.get_urls("tags", "tag", namespace="orga")] == [
        "tag.list",
        "tag.create",
        "tag.update",
        "tag.delete",
    ]
    assert [u.name for u in TestView.get_urls("tags", "tag", namespace="orga")] == [
        "tag.list",
        "tag.detail",
        "tag.create",
        "tag.update",
        "tag.delete",
    ]


# --- CRUDView template names ---


@pytest.mark.parametrize(
    ("action", "template_namespace", "expected"),
    (
        (
            "list",
            None,
            [
                "common/tag/list.html",
                "common/tag_list.html",
                "common/generic/list.html",
            ],
        ),
        (
            "create",
            None,
            [
                "common/tag/create.html",
                "common/tag_create.html",
                "common/tag/_form.html",
                "common/tag_form.html",
                "common/generic/create.html",
            ],
        ),
        (
            "list",
            "orga/submission",
            [
                "orga/submission/tag/list.html",
                "orga/submission/tag_list.html",
                "common/generic/list.html",
            ],
        ),
    ),
    ids=("list", "create_with_form_fallback", "custom_namespace"),
)
def test_crud_view_get_template_names(action, template_namespace, expected):
    view = CRUDView()
    view.model = Tag
    view.action = action
    view.template_namespace = template_namespace

    assert view.get_template_names() == expected


# --- OrgaTableMixin ---


@pytest.mark.parametrize(
    ("request_get", "max_page_size", "expected"),
    (
        (None, 100, 50),
        ("page_size=abc", 100, 50),
        ("page_size=30", 100, 30),
        ("page_size=9999", 100, 100),
        ("page_size=200", 0, 200),
    ),
    ids=("default", "invalid", "explicit", "clamped", "unclamped"),
)
def test_orga_table_mixin_get_paginate_by_from_query(
    event, request_get, max_page_size, expected
):
    user = UserFactory()
    mixin = _make_table_mixin(event, user, request_get=request_get)
    mixin.max_page_size = max_page_size

    assert mixin.get_paginate_by() == expected
    assert dict(mixin.request.session) == {}


def test_orga_table_mixin_get_paginate_by_prefers_table_page_size(event, settings):
    settings.MAX_PAGINATION_LIMIT = 100
    user = UserFactory()
    mixin = _make_table_mixin(event, user)

    mixin.table_class = "SomeTable"
    assert mixin.get_paginate_by() is None

    mixin._table_page_size = 15
    assert mixin.get_paginate_by() == 15

    mixin._table_page_size = 250
    assert mixin.get_paginate_by() == 100


@pytest.mark.parametrize("table_event", ("event", None))
def test_orga_table_mixin_get_table_pagination_stores_page_size(event, table_event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user, request_get="page_size=9999")
    mixin.max_page_size = 100
    table_event = event if table_event else None
    table = SimpleNamespace(data=[], name="test_table", event=table_event)

    assert mixin.get_table_pagination(table)["per_page"] == 100
    assert (
        user.get_event_preferences(table_event).get("tables.test_table.page_size")
        == 100
    )


def test_orga_table_mixin_get_table_pagination_unpaginated_does_not_store(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user, request_get="page_size=20")
    mixin.table_pagination = False
    table = SimpleNamespace(data=[], name="test_table", event=event)

    assert mixin.get_table_pagination(table) is False
    assert user.get_event_preferences(event).get("tables.test_table.page_size") is None


def test_orga_table_mixin_get_table_pagination_anonymous_skips_preferences(event):
    mixin = _make_table_mixin(event, None, request_get="page_size=20")
    table = SimpleNamespace(data=[], name="test_table", event=event)

    assert mixin.get_table_pagination(table)["per_page"] == 20


@pytest.mark.parametrize(
    ("request_get", "headers", "expect_disabled"),
    (
        pytest.param(
            "paginate=0",
            {"HX-Pretalx-Print": "1"},
            True,
            id="header-and-paginate-zero-disables",
        ),
        pytest.param(
            "paginate=0", None, False, id="paginate-zero-without-header-ignored"
        ),
        pytest.param(None, {"HX-Pretalx-Print": "1"}, False, id="header-alone-no-op"),
        pytest.param(None, None, False, id="default"),
    ),
)
def test_orga_table_mixin_get_table_pagination_print_gate(
    event, request_get, headers, expect_disabled
):
    user = UserFactory()
    mixin = _make_table_mixin(
        event, user, request_get=request_get, request_headers=headers
    )
    result = mixin.get_table_pagination(table=SimpleNamespace(data=[]))
    assert (result is False) is expect_disabled


def test_orga_table_mixin_get_table_pagination_disabled_for_dragsort(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user)

    dragsort_table = SimpleNamespace(data=[], is_dragsort=True)
    plain_table = SimpleNamespace(data=[])

    assert mixin.get_table_pagination(table=dragsort_table) is False

    plain_pagination = mixin.get_table_pagination(table=plain_table)
    assert isinstance(plain_pagination, dict)
    assert plain_pagination


def test_orga_table_mixin_get_context_data_marks_pagination_from_table_page(event):
    fake_paginator = SimpleNamespace(count=10)
    fake_page = SimpleNamespace(paginator=fake_paginator, has_other_pages=lambda: True)
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    mixin.object_list = []

    assert mixin.get_table() is None
    assert mixin.get_table_kwargs() == {"event": event, "user": user}

    mixin.get_table = lambda *a, **kw: SimpleNamespace(page=None, paginator=None)
    assert mixin.get_context_data().get("is_paginated") is not True

    mixin.get_table = lambda *a, **kw: SimpleNamespace(
        page=fake_page, paginator=fake_paginator
    )
    context = mixin.get_context_data()
    assert context["page_obj"] is fake_page
    assert context["paginator"] is fake_paginator
    assert context["is_paginated"] is True


def test_orga_table_mixin_get_template_names_returns_htmx_partial_only_for_htmx(event):
    user = UserFactory()
    mixin = _make_table_mixin(event, user)
    mixin.table_class = "SomeTable"
    assert mixin.get_template_names() == ["test/template.html"]

    mixin = _make_table_mixin(
        event,
        user,
        table_class="SomeTable",
        request_headers={"HX-Request": "true", "HX-Target": "table-content-main"},
    )
    assert mixin.get_template_names() == ["django_tables2/table.html#table-content"]


def test_orga_table_mixin_dispatch_sets_hx_push_url_for_htmx(event):
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


def test_orga_crud_view_with_event(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    view.form_class = forms.Form

    assert view.event is event
    assert view.get_generic_permission_object() is event
    assert view.get_reverse_kwargs("list") == {"event": event.slug}
    assert view.get_form_kwargs()["event"] is event
    assert view.get_log_kwargs()["orga"] is True
    assert view.get_template_names()[-1] == "orga/generic/list.html"
    assert view.get_table_kwargs() == {
        "event": event,
        "user": user,
        "has_update_permission": True,
        "has_delete_permission": True,
    }


def test_orga_crud_view_with_organiser_only(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    view.form_class = forms.Form
    del view.request.event
    view.request.organiser = event.organiser

    assert view.event is None
    assert view.organiser is event.organiser
    assert view.get_generic_permission_object() is event.organiser
    assert view.get_reverse_kwargs("list") == {"organiser": event.organiser.slug}
    assert view.get_form_kwargs()["organiser"] is event.organiser
    assert "event" not in view.get_form_kwargs()


def test_orga_crud_view_without_event_or_organiser(event):
    user = make_orga_user(event)
    view = _make_orga_crud_view(event, user)
    view.form_class = forms.Form
    del view.request.event

    assert view.get_reverse_kwargs("list") == {}
    assert not {"event", "organiser"} & set(view.get_form_kwargs())


def test_orga_crud_view_form_valid_without_event_skips_event_assignment(event):
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
