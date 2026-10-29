# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import time
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import celery.result
import pytest
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse, QueryDict
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.test import RequestFactory, override_settings
from django.utils.module_loading import import_string
from django.views.generic import ListView, TemplateView, View
from django.views.generic.edit import FormMixin
from kombu.exceptions import OperationalError

from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.models.file import CachedFile
from pretalx.common.tables.filters import BooleanFilter
from pretalx.common.views.mixins import (
    ActionConfirmMixin,
    AsyncFileDownloadMixin,
    AsyncTaskProgressMixin,
    ConfirmDialogMixin,
    EventPermissionRequired,
    Filterable,
    OrderActionMixin,
    PaginationMixin,
    PermissionRequired,
    ReadOnlySessionData,
    SensibleBackWizardMixin,
    SocialMediaCardMixin,
    reorder_queryset,
)
from pretalx.submission.models import Track
from tests.factories import (
    CachedFileFactory,
    SubmissionFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import DIALOG_HEADERS, make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _qd(**kwargs):
    qd = QueryDict(mutable=True)
    for key, value in kwargs.items():
        qd[key] = value
    qd._mutable = False
    return qd


class ConcreteFilterable(Filterable):
    model = None

    def __init__(self, request, filters=None):
        self.request = request
        if filters is not None:
            self.filters = filters


def test_filterable_without_filters_returns_queryset_unchanged(event):
    sub = SubmissionFactory(event=event)

    request = make_request(event)
    request.GET = _qd(is_featured="true")
    f = ConcreteFilterable(request)

    assert f.filterset is None
    assert list(f.filter_queryset(event.submissions.all())) == [sub]


def test_filterable_builds_filterset_from_filter_factory(event):
    featured = SubmissionFactory(event=event, is_featured=True)
    SubmissionFactory(event=event, is_featured=False)

    request = make_request(event)
    request.GET = _qd(is_featured="true")
    f = ConcreteFilterable(
        request, filters=lambda context: [BooleanFilter(name="is_featured")]
    )

    assert list(f.filter_queryset(event.submissions.all())) == [featured]


class FakePermissionObject:
    pass


class ConcretePermissionRequired(PermissionRequired):
    permission_required = "test.view_thing"
    write_permission_required = "test.change_thing"
    create_permission_required = None

    def __init__(self, request, obj=None, **kwargs):
        self.request = request
        self._obj = obj
        self.kwargs = kwargs
        super().__init__()

    def get_object(self):
        return self._obj


def test_permission_required_permission_object_delegates_to_get_object(event):
    obj = FakePermissionObject()
    request = make_request(event)
    view = ConcretePermissionRequired(request, obj=obj)

    assert PermissionRequired.permission_object.__get__(view) is obj
    assert PermissionRequired.object.__get__(view) is obj


@pytest.mark.parametrize(
    ("is_orga", "kwargs", "create_perm", "write_perm", "expected"),
    (
        pytest.param(True, {"pk": 1}, None, "event.update_event", "edit", id="edit"),
        pytest.param(False, {"pk": 1}, None, "test.change_thing", "view", id="view"),
        pytest.param(
            True,
            {"event": "test"},
            "event.update_event",
            "test.change_thing",
            "create",
            id="create_with_create_perm",
        ),
        pytest.param(
            True,
            {"event": "test"},
            None,
            "event.update_event",
            "create",
            id="create_falls_back_to_write_perm",
        ),
        pytest.param(
            False,
            {"event": "test"},
            None,
            "test.change_thing",
            "view",
            id="view_without_create_or_write_perm",
        ),
    ),
)
def test_permission_required_permission_action(
    event, is_orga, kwargs, create_perm, write_perm, expected
):
    user = (
        make_orga_user(event, can_change_event_settings=True)
        if is_orga
        else UserFactory()
    )
    request = make_request(event, user=user)
    view = ConcretePermissionRequired(request, obj=event, **kwargs)
    view.create_permission_required = create_perm
    view.write_permission_required = write_perm

    assert PermissionRequired.permission_action.__get__(view) == expected


def test_permission_required_permission_action_create_raises_404_without_perm(event):
    user = UserFactory()
    request = make_request(event, user=user)
    view = ConcretePermissionRequired(request, obj=event, event="test")
    view.create_permission_required = "event.update_event"
    with pytest.raises(Http404):
        PermissionRequired.permission_action.__get__(view)


def test_permission_required_handle_no_permission_raises_404_outside_cfp(event):
    user = UserFactory.build()
    request = make_request(event, user=user)
    request.resolver_match = SimpleNamespace(namespaces=["orga"])
    view = ConcretePermissionRequired(request, obj=None)

    with pytest.raises(Http404):
        view.get_login_url()
    with pytest.raises(Http404):
        view.handle_no_permission()


def test_permission_required_handle_no_permission_redirects_anonymous_cfp(event):
    request = make_request(event, path="/test/cfp/submit/")
    request.resolver_match = SimpleNamespace(namespaces=["cfp"])
    request.GET = _qd(token="abc123")
    view = ConcretePermissionRequired(request, obj=None)

    response = view.handle_no_permission()

    assert response.status_code == 302
    assert response.url == (
        f"{event.urls.login.full()}?next={quote('/test/cfp/submit/')}&token=abc123"
    )


class EventSettingsPermissionRequired(ConcretePermissionRequired):
    permission_required = "event.update_event"


def _make_parent_session(user=None, **session_data):
    session_store = import_string(f"{settings.SESSION_ENGINE}.SessionStore")
    parent_session = session_store()
    if user:
        parent_session[SESSION_KEY] = str(user.pk)
        parent_session[BACKEND_SESSION_KEY] = (
            "django.contrib.auth.backends.ModelBackend"
        )
        parent_session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        parent_session["pretalx_auth_login_time"] = int(time.time())
        parent_session["pretalx_auth_last_used"] = int(time.time())
    parent_session.update(session_data)
    parent_session.create()
    return parent_session


def _make_event_access_request(
    event, user=None, view_name="agenda:talk", **session_data
):
    request = make_request(event, resolver_match=SimpleNamespace(view_name=view_name))
    request.session[f"pretalx_event_access_{event.pk}"] = _make_parent_session(
        user, **session_data
    ).session_key
    return request


def test_read_only_session_data_ignores_writes():
    session = ReadOnlySessionData({"key": "value"})

    session.cycle_key()
    session["key"] = "other"

    assert session == {"key": "value"}


@pytest.mark.parametrize(
    ("view_name", "expected"),
    (("agenda:talk", True), ("agenda:schedule.changelog", False)),
)
def test_permission_required_has_permission_via_session_event_access(
    event, view_name, expected
):
    user = make_orga_user(event, can_change_event_settings=True)
    request = _make_event_access_request(event, user, view_name=view_name)

    view = EventSettingsPermissionRequired(request, obj=event)
    assert view.has_permission() is expected


def test_permission_required_session_event_access_denies_unusable_parent_sessions(
    event,
):
    unprivileged = make_orga_user(event, can_change_event_settings=False)
    unknown = make_request(event)
    unknown.session[f"pretalx_event_access_{event.pk}"] = "nosuchsessionkey"
    requests = (
        _make_event_access_request(event, unprivileged),
        _make_event_access_request(event),
        unknown,
    )

    for request in requests:
        view = EventSettingsPermissionRequired(request, obj=event)
        assert view.has_permission() is False


@override_settings(
    PRETALX_SESSION_TIMEOUT_RELATIVE=100, PRETALX_SESSION_TIMEOUT_ABSOLUTE=200
)
@pytest.mark.parametrize(
    ("login_age", "idle_age", "long_session", "expected"),
    (
        (10, 10, False, True),
        (10, 150, False, False),
        (300, 10, False, False),
        (300, 300, True, True),
    ),
    ids=("fresh", "idle_timeout", "absolute_timeout", "long_session"),
)
def test_permission_required_session_event_access_honours_parent_session_timeouts(
    event, login_age, idle_age, long_session, expected
):
    user = make_orga_user(event, can_change_event_settings=True)
    request = _make_event_access_request(
        event,
        user,
        pretalx_auth_login_time=int(time.time()) - login_age,
        pretalx_auth_last_used=int(time.time()) - idle_age,
        pretalx_auth_long_session=long_session,
    )

    view = EventSettingsPermissionRequired(request, obj=event)
    assert view.has_permission() is expected


@override_settings(
    PRETALX_SESSION_TIMEOUT_RELATIVE=100, PRETALX_SESSION_TIMEOUT_ABSOLUTE=200
)
def test_permission_required_session_event_access_does_not_refresh_parent_session(
    event,
):
    user = make_orga_user(event, can_change_event_settings=True)
    last_used = int(time.time()) - 10
    request = _make_event_access_request(
        event, user, pretalx_auth_login_time=last_used, pretalx_auth_last_used=last_used
    )

    view = EventSettingsPermissionRequired(request, obj=event)

    assert view.has_permission() is True
    session_store = import_string(f"{settings.SESSION_ENGINE}.SessionStore")
    parent_key = request.session[f"pretalx_event_access_{event.pk}"]
    assert session_store(parent_key).load()["pretalx_auth_last_used"] == last_used


def test_permission_required_has_permission_returns_false_without_access(event):
    user = UserFactory()
    request = make_request(event, user=user)
    view = ConcretePermissionRequired(request, obj=event)

    assert view.has_permission() is False

    del request.event
    assert view.has_permission() is False


def test_permission_required_has_permission_returns_true_via_super(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)

    class PermWithRealPerm(PermissionRequired):
        permission_required = "event.update_event"

        def get_object(self):
            return self._obj

    view = PermWithRealPerm()
    view.request = request
    view.kwargs = {}
    view._obj = event
    assert view.has_permission() is True


def test_permission_required_get_form_kwargs_read_only(event):
    user = UserFactory()
    request = make_request(event, user=user)

    class DummyForm(ReadOnlyFlag):
        pass

    class ViewWithForm(PermissionRequired, FormMixin):
        permission_required = "test.view"
        write_permission_required = "test.change"
        form_class = DummyForm

        def get_object(self):
            return self._obj

    view = ViewWithForm()
    view.request = request
    view.kwargs = {"pk": 1}
    view._obj = event
    kwargs = view.get_form_kwargs()
    assert kwargs["read_only"] is True


def test_event_permission_required_permission_object_is_event(event):
    class ConcreteEventPerm(EventPermissionRequired):
        permission_required = "test.view"

    request = make_request(event)
    view = ConcreteEventPerm()
    view.request = request
    view.kwargs = {}
    assert view.get_permission_object() is event


def test_permission_required_get_form_kwargs_locales_for_i18n(event):
    user = UserFactory()
    request = make_request(event, user=user)

    class ViewWithI18nForm(PermissionRequired, FormMixin):
        permission_required = "test.view"
        write_permission_required = "test.change"
        form_class = PretalxI18nModelForm

    view = ViewWithI18nForm()
    view.request = request
    view.kwargs = {"pk": 1}
    view._obj = event
    kwargs = view.get_form_kwargs()
    assert kwargs["locales"] == event.locales


class _FakeSteps:
    def __init__(self, current, last, first="step1"):
        self.current = current
        self.last = last
        self.first = first


class _FakeStorage:
    def __init__(self):
        self.current_step = None
        self.step_data = {}
        self.step_files = {}

    def set_step_data(self, step, data):
        self.step_data[step] = data

    def set_step_files(self, step, files):
        self.step_files[step] = files


class ConcreteWizard(SensibleBackWizardMixin):
    prefix = "event_wizard"

    def __init__(self, request, *, steps_current="step1", steps_last="step2"):
        self.request = request
        self.steps = _FakeSteps(steps_current, steps_last)
        self.storage = _FakeStorage()

    def get_form(self, **kwargs):
        return self._form

    def process_step(self, form):
        return form.cleaned_data

    def process_step_files(self, form):
        return {}

    def get_form_list(self):
        return {"step1": None, "step2": None}

    def render_goto_step(self, step):
        return f"goto:{step}"

    def render_done(self, form, **kwargs):
        return "done"

    def render_next_step(self, form):
        return "next"

    def render(self, form):
        return "invalid"


def _wizard_post_data(current_step="step1", **extra):
    data = {"event_wizard-current_step": current_step}
    data.update(extra)
    rf = RequestFactory()
    return rf.post("/wizard/", data=data)


class _FakeForm:
    def __init__(self, valid=True, **cleaned_data):
        self.valid = valid
        self.cleaned_data = cleaned_data

    def is_valid(self):
        return self.valid


@pytest.mark.parametrize(
    ("current_step", "post_step", "extra", "form", "expected", "expected_step_data"),
    (
        pytest.param(
            "step1",
            "step1",
            {},
            _FakeForm(field="value"),
            "next",
            {"step1": {"field": "value"}},
            id="next_step",
        ),
        pytest.param(
            "step2",
            "step2",
            {},
            _FakeForm(field="done"),
            "done",
            {"step2": {"field": "done"}},
            id="last_step",
        ),
        pytest.param(
            "step2",
            "step2",
            {"wizard_goto_step": "step1"},
            _FakeForm(field="saved"),
            "goto:step1",
            {"step2": {"field": "saved"}},
            id="goto_step",
        ),
        pytest.param(
            "step1",
            "step1",
            {},
            _FakeForm(valid=False),
            "invalid",
            {},
            id="invalid_form",
        ),
        pytest.param(
            "step3",
            "step3",
            {},
            _FakeForm(),
            "goto:step1",
            {},
            id="unknown_step_restarts",
        ),
    ),
)
def test_sensible_back_wizard_post(
    current_step, post_step, extra, form, expected, expected_step_data
):
    request = _wizard_post_data(post_step, **extra)
    view = ConcreteWizard(request, steps_current=current_step, steps_last="step2")
    view._form = form

    assert view.post() == expected
    assert view.storage.step_data == expected_step_data


def test_sensible_back_wizard_post_invalid_management_form():
    rf = RequestFactory()
    request = rf.post("/wizard/", data={})
    view = ConcreteWizard(request, steps_current="step1", steps_last="step2")
    with pytest.raises(ValidationError):
        view.post()


def test_sensible_back_wizard_post_step_mismatch():
    request = _wizard_post_data("step2")
    view = ConcreteWizard(request, steps_current="step1", steps_last="step2")
    view.storage.current_step = "step1"
    view._form = _FakeForm(field="value")

    view.post()

    assert view.storage.current_step == "step2"


def test_sensible_back_wizard_post_aborts_on_failed_prerequisites():
    class GuardedWizard(ConcreteWizard):
        def check_step_prerequisites(self):
            return "goto:step1"

    request = _wizard_post_data("step2")
    view = GuardedWizard(request, steps_current="step2", steps_last="step2")

    result = view.post()

    assert result == "goto:step1"
    assert view.storage.step_data == {}


@pytest.mark.parametrize(
    ("image_field", "expect_404"),
    ((None, True), ("og_image", False), ("logo", False), ("header_image", False)),
    ids=["no_images", "og_image", "logo", "header_image"],
)
def test_social_media_card_get_fallback(event, make_image, image_field, expect_404):
    if image_field:
        getattr(event, image_field).save(f"{image_field}.png", make_image(), save=True)

    class ConcreteCard(SocialMediaCardMixin):
        def get_image(self):
            return None

    view = ConcreteCard()
    request = make_request(event)
    view.request = request

    if expect_404:
        with pytest.raises(Http404):
            view.get(request)
    else:
        response = view.get(request)
        assert response.status_code == 200


def test_social_media_card_get_returns_get_image_result(event):
    class ConcreteCard(SocialMediaCardMixin):
        def get_image(self):
            return BytesIO(b"fake-image-data")

    view = ConcreteCard()
    request = make_request(event)
    view.request = request
    response = view.get(request)
    assert response.status_code == 200


def test_social_media_card_get_skips_missing_files(event, make_image):
    event.og_image.save("og.png", make_image("og.png", width=2, height=2), save=True)
    event.logo.save("logo.png", make_image("logo.png", width=3, height=3), save=True)
    Path(event.og_image.path).unlink()
    expected = Path(event.logo.path).read_bytes()

    class ConcreteCard(SocialMediaCardMixin):
        def get_image(self):
            return None

    view = ConcreteCard()
    request = make_request(event)
    view.request = request
    response = view.get(request)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == expected


def test_social_media_card_get_404_when_all_files_missing(event, make_image):
    event.og_image.save("og.png", make_image(), save=True)
    Path(event.og_image.path).unlink()

    class ConcreteCard(SocialMediaCardMixin):
        def get_image(self):
            return None

    view = ConcreteCard()
    request = make_request(event)
    view.request = request
    with pytest.raises(Http404):
        view.get(request)


class ConcretePagination(PaginationMixin):
    def __init__(self, request):
        self.request = request


def test_pagination_get_paginate_by_without_query_param(event):
    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    view = ConcretePagination(request)

    assert view.get_paginate_by() == 50

    view.paginate_by = 10
    assert view.get_paginate_by() == 10

    request.session["stored_page_size_test_list"] = 25
    assert view.get_paginate_by() == 25


@pytest.mark.parametrize(
    ("page_size", "max_limit", "expected", "stored"),
    (
        ("20", 100, 20, 20),
        ("250", 0, 250, 250),
        ("200", 100, 100, 100),
        ("9999", 0, 9999, 9999),
        ("abc", 100, 50, None),
    ),
    ids=("explicit", "large_without_limit", "clamped", "unclamped", "invalid"),
)
def test_pagination_get_paginate_by_from_get_param(
    event, settings, page_size, max_limit, expected, stored
):
    settings.MAX_PAGINATION_LIMIT = max_limit
    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    request.GET = {"page_size": page_size}
    view = ConcretePagination(request)

    assert view.get_paginate_by() == expected
    assert request.session.get("stored_page_size_test_list") == stored


def test_pagination_get_context_data_non_crud(event):
    class PaginatedList(PaginationMixin, ListView):
        model = None
        paginate_by = 10

    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    view = PaginatedList()
    view.request = request
    view.kwargs = {}
    view.object_list = []
    ctx = view.get_context_data()
    assert "paginator" in ctx


class _BaseContext:
    def get_context_data(self, **kwargs):
        return kwargs


class ConcreteActionConfirm(ActionConfirmMixin, _BaseContext):
    def __init__(self, request):
        self.request = request


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ({"next": "/orga/event/"}, "/orga/event/"),
        ({"next": "http://evil.example.com/"}, "/orga/event"),
        ({"back": "/orga/speakers/"}, "/orga/speakers/"),
        ({}, "/orga/event"),
    ),
    ids=("next", "rejects_external_next", "back", "fallback"),
)
def test_action_confirm_action_back_url(event, query, expected):
    request = make_request(event, path="/orga/event/delete/")
    request.GET = _qd(**query)
    view = ConcreteActionConfirm(request)

    assert view.action_back_url == expected


def test_action_confirm_get_context_data(event):
    request = make_request(event, path="/orga/event/delete/")
    request.GET = {"next": "/orga/"}
    view = ConcreteActionConfirm(request)

    ctx = view.get_context_data()

    assert ctx["action_title"] is not None
    assert ctx["action_text"] is not None
    assert len(ctx["submit_buttons"]) == 1
    assert len(ctx["submit_buttons_extra"]) == 1


class ConcreteActionConfirmView(ActionConfirmMixin, TemplateView):
    pass


class RedirectingActionConfirmView(ActionConfirmMixin, View):
    def get(self, request, *args, **kwargs):
        return redirect("/orga/event/")


class PlainResponseConfirmView(ConfirmDialogMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("ok")


class StringTemplateConfirmView(ConfirmDialogMixin, View):
    def get(self, request, *args, **kwargs):
        return TemplateResponse(request, "common/action_confirm.html")


@pytest.mark.parametrize(
    ("headers", "expected", "dialog_header"),
    (
        pytest.param(None, ["common/action_confirm.html"], None, id="plain"),
        pytest.param(
            DIALOG_HEADERS,
            [
                "common/action_confirm.html#dialog",
                "common/includes/action_confirm.html#dialog",
            ],
            "1",
            id="dialog",
        ),
        pytest.param(
            {"HX-Request": "true", "HX-Target": "table-content"},
            ["common/action_confirm.html"],
            None,
            id="other-htmx-target",
        ),
    ),
)
def test_action_confirm_template_names(event, headers, expected, dialog_header):
    request = make_request(event, path="/orga/event/delete/", headers=headers)
    view = make_view(ConcreteActionConfirmView, request)

    response = view.dispatch(request)

    assert response.template_name == expected
    assert response.headers.get("Pretalx-Dialog") == dialog_header


@pytest.mark.parametrize(
    ("headers", "status", "redirect_header"),
    (
        pytest.param(None, 302, "Location", id="plain"),
        pytest.param(DIALOG_HEADERS, 286, "HX-Redirect", id="dialog"),
        pytest.param(
            {"HX-Request": "true", "HX-Target": "table-content"},
            302,
            "Location",
            id="other-htmx-target",
        ),
    ),
)
def test_action_confirm_redirect_handling(event, headers, status, redirect_header):
    request = make_request(event, path="/orga/event/delete/", headers=headers)
    view = make_view(RedirectingActionConfirmView, request)

    response = view.dispatch(request)

    assert response.status_code == status
    assert response[redirect_header] == "/orga/event/"


def test_confirm_dialog_leaves_rendered_response_alone(event):
    request = make_request(event, path="/orga/event/delete/", headers=DIALOG_HEADERS)
    view = make_view(PlainResponseConfirmView, request)

    response = view.dispatch(request)

    assert response.status_code == 200
    assert "Pretalx-Dialog" not in response.headers


def test_confirm_dialog_patches_string_template_name(event):
    request = make_request(event, path="/orga/event/delete/", headers=DIALOG_HEADERS)
    view = make_view(StringTemplateConfirmView, request)

    response = view.dispatch(request)

    assert response.template_name == [
        "common/action_confirm.html#dialog",
        "common/includes/action_confirm.html#dialog",
    ]
    assert response.headers["Pretalx-Dialog"] == "1"


def test_reorder_queryset_updates_positions_and_rejects_unknown_pks(event):
    t1 = TrackFactory(event=event, name="First", position=0, color="#111111")
    t2 = TrackFactory(event=event, name="Second", position=1, color="#222222")
    t3 = TrackFactory(event=event, name="Third", position=2, color="#333333")

    reorder_queryset(
        Track.objects.filter(event=event), [str(t3.pk), str(t1.pk), str(t2.pk)]
    )

    assert list(
        Track.objects.filter(event=event)
        .order_by("position")
        .values_list("pk", flat=True)
    ) == [t3.pk, t1.pk, t2.pk]

    with pytest.raises(Http404):
        reorder_queryset(Track.objects.filter(event=event), ["99999"])


def test_order_action_mixin_order_handler(event):
    t1 = TrackFactory(event=event, name="A", position=0, color="#111111")
    t2 = TrackFactory(event=event, name="B", position=1, color="#222222")

    class ConcreteOrderView(OrderActionMixin):
        def __init__(self, request, _event):
            self.request = request
            self._event = _event

        def get_queryset(self):
            return Track.objects.filter(event=self._event)

        def list(self, request, *args, **kwargs):
            return "list_response"

    request = make_request(event, method="post", path="/order/")
    request.POST = {"order": f"{t2.pk},{t1.pk}"}
    view = ConcreteOrderView(request, event)

    assert view.order_handler(request) == "list_response"
    t1.refresh_from_db()
    t2.refresh_from_db()
    assert (t2.position, t1.position) == (0, 1)

    request.POST = {"order": ""}
    assert view.order_handler(request) == "list_response"
    t1.refresh_from_db()
    t2.refresh_from_db()
    assert (t2.position, t1.position) == (0, 1)


def _add_messages(request):
    request._messages = FallbackStorage(request)
    return request


class _FakeAsyncResult:
    def __init__(self, *, ready, successful, result=None):
        self.id = "fake-task-id"
        self.result = result
        self._ready = ready
        self._successful = successful

    def ready(self):
        return self._ready

    def successful(self):
        return self._successful


class ConcreteAsyncDownload(AsyncFileDownloadMixin):
    _async_result = None

    def __init__(self, request):
        self.request = _add_messages(request)

    def get_error_redirect_url(self):
        return "/error/"

    def get_async_download_filename(self):
        return "test-export.zip"

    def start_async_task(self, cached_file):
        return SimpleNamespace(id="fake-task-id")

    def _get_async_result(self, async_id):
        if self._async_result is not None:
            return self._async_result
        return super()._get_async_result(async_id)


def test_async_download_get_async_result_returns_celery_result(event):
    request = make_request(event, path="/orga/export/")
    view = ConcreteAsyncDownload(request)
    result = view._get_async_result("test-task-id")
    assert isinstance(result, celery.result.AsyncResult)
    assert result.id == "test-task-id"


def test_async_download_handle_cached_file_serves_file(event):
    request = make_request(event, path="/orga/export/")
    view = ConcreteAsyncDownload(request)
    cf = CachedFileFactory()
    cf.bind_to_session(request, view.async_download_salt)
    cf.file.save("test.zip", ContentFile(b"zipdata"))

    request.GET = {"cached_file": str(cf.id)}
    response = view.handle_async_download(request)
    assert "attachment" in response["Content-Disposition"]


@pytest.mark.parametrize(
    "session_key", ("somebody-elses-session", None), ids=("other-session", "unbound")
)
def test_async_download_handle_cached_file_of_foreign_session_redirects(
    event, session_key
):
    cf = CachedFileFactory(session_key=session_key)
    cf.file.save("test.zip", ContentFile(b"zipdata"))

    request = make_request(event, path="/orga/export/")
    request.GET = {"cached_file": str(cf.id)}
    view = ConcreteAsyncDownload(request)
    response = view.handle_async_download(request)
    assert response.status_code == 302
    assert response.url == "/error/"


def test_async_download_handle_unusable_cached_file_param_redirects(event):
    cf = CachedFileFactory()
    request = make_request(event, path="/orga/export/")
    view = ConcreteAsyncDownload(request)

    for value in (str(cf.id), "not-a-uuid"):
        request.GET = {"cached_file": value}
        response = view.handle_async_download(request)
        assert response.status_code == 302
        assert response.url == "/error/"


def test_async_download_start_task_eager_mode(event, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    class EagerDownload(AsyncFileDownloadMixin):
        def get_async_download_filename(self):
            return "eager.zip"

        def start_async_task(self, cached_file):
            cached_file.file.save("eager.zip", ContentFile(b"data"))
            return SimpleNamespace(id="fake")

    request = make_request(event, path="/orga/export/")
    request.GET = {}
    view = EagerDownload()
    view.request = request
    response = view._start_task(request)
    assert "attachment" in response["Content-Disposition"]


def test_async_download_start_task_non_eager_binds_file_and_redirects(event, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False

    request = make_request(event, path="/orga/export/")
    request.GET = {}
    view = ConcreteAsyncDownload(request)
    response = view.handle_async_download(request)

    cached_file = CachedFile.objects.get()
    assert cached_file.filename == "test-export.zip"
    assert cached_file.allowed_for_session(request, view.async_download_salt)
    assert not cached_file.allowed_for_session(request, "other.DownloadView")
    assert response.status_code == 302
    assert "async_id=fake-task-id" in response.url


def test_async_download_check_task_success_serves_file(event):
    request = make_request(event, path="/orga/export/")
    view = ConcreteAsyncDownload(request)
    cf = CachedFileFactory()
    cf.bind_to_session(request, view.async_download_salt)
    cf.file.save("export.zip", ContentFile(b"zipdata"))
    view._async_result = _FakeAsyncResult(
        ready=True, successful=True, result=str(cf.id)
    )

    response = view._check_task_status(request, "test-id")
    assert "attachment" in response["Content-Disposition"]

    htmx_request = make_request(
        event, path="/orga/export/", headers={"HX-Request": "true"}
    )
    htmx_request.session = request.session
    response = view._check_task_status(htmx_request, "test-id")
    assert f"cached_file={cf.id}" in response.content.decode()


@pytest.mark.parametrize(
    "result",
    (
        _FakeAsyncResult(ready=True, successful=False),
        _FakeAsyncResult(ready=True, successful=True, result=None),
        _FakeAsyncResult(ready=True, successful=True, result="not-a-valid-uuid"),
    ),
    ids=("failed", "no_result", "invalid_uuid"),
)
def test_async_download_check_task_failure_redirects_to_error(event, result):
    request = make_request(event, path="/orga/export/")
    view = ConcreteAsyncDownload(request)
    view._async_result = result
    response = view._check_task_status(request, "test-id")
    assert response.status_code == 302
    assert response.url == "/error/"

    htmx_request = make_request(
        event, path="/orga/export/", headers={"HX-Request": "true"}
    )
    response = view._check_task_status(htmx_request, "test-id")
    assert "/error/" in response.content.decode()


def test_async_download_check_task_pending(event):
    request = make_request(event, path="/orga/export/")
    htmx_request = make_request(
        event, path="/orga/export/", headers={"HX-Request": "true"}
    )
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(ready=False, successful=False)

    assert view._check_task_status(request, "test-id").status_code == 200
    assert view._check_task_status(htmx_request, "test-id").status_code == 200


def test_async_download_check_task_result_of_other_session_redirects(event):
    cf = CachedFileFactory(session_key="somebody-elses-session")
    cf.file.save("export.zip", ContentFile(b"zipdata"))

    request = make_request(event, path="/orga/export/")
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(
        ready=True, successful=True, result=str(cf.id)
    )
    response = view._check_task_status(request, "test-id")
    assert response.status_code == 302
    assert response.url == "/error/"


def test_async_download_serve_cached_file_missing_file(event):
    cf = CachedFileFactory()
    cf.file.name = "nonexistent/path.zip"
    cf.save()

    request = make_request(event, path="/orga/export/")
    view = ConcreteAsyncDownload(request)
    response = view._serve_cached_file(request, cf)
    assert response.status_code == 302
    assert response.url == "/error/"


def test_async_download_handle_routes_to_check_task(event):
    request = make_request(event, path="/orga/export/")
    request.GET = {"async_id": "some-id"}
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(ready=True, successful=False)
    response = view.handle_async_download(request)
    assert response.status_code == 302
    assert response.url == "/error/"


class _FakeTaskAsyncResult:
    def __init__(self, *, ready, successful, result=None, state="PENDING", info=None):
        self.id = "fake-task-id"
        self.result = result
        self.state = state
        self.info = info
        self._ready = ready
        self._successful = successful

    def ready(self):
        return self._ready

    def successful(self):
        return self._successful


class ConcreteTaskProgress(AsyncTaskProgressMixin, View):
    _async_result = None

    def __init__(self, request):
        self.request = _add_messages(request)

    def get_task_success_url(self, result):
        return "/success/"

    def get_task_error_url(self):
        return "/error/"

    def get_task_success_message(self, result):
        return "Done"

    def _get_async_result(self, async_id):
        if self._async_result is not None:
            return self._async_result
        return super()._get_async_result(async_id)


def test_async_task_progress_get_async_result_returns_celery_result(event):
    request = make_request(event, path="/orga/test/")
    view = ConcreteTaskProgress(request)

    result = view._get_async_result("test-task-id")

    assert isinstance(result, celery.result.AsyncResult)
    assert result.id == "test-task-id"
    assert (
        str(AsyncTaskProgressMixin().get_task_success_message(None))
        == "The task has been completed."
    )


def test_async_task_progress_get_checks_progress_only_with_async_id(event):
    request = make_request(event, path="/orga/test/")
    view = ConcreteTaskProgress(request)

    with pytest.raises(AttributeError):
        view.get(request)

    request.GET = {"async_id": "some-id"}
    view._async_result = _FakeTaskAsyncResult(ready=True, successful=True, result={})
    response = view.get(request)

    assert response.status_code == 302
    assert response.url == "/success/"


def test_async_task_progress_dispatch_async_task_eager_success(event, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    request = make_request(event, path="/orga/test/")
    view = ConcreteTaskProgress(request)

    fake_result = _FakeTaskAsyncResult(ready=True, successful=True, result={"count": 5})
    task = SimpleNamespace(apply_async=lambda **kw: fake_result)

    response = view.dispatch_async_task(request, task, event_id=1)
    assert response.status_code == 302
    assert response.url == "/success/"
    msgs = list(request._messages)
    assert len(msgs) == 1
    assert str(msgs[0]) == "Done"


def test_async_task_progress_dispatch_async_task_eager_failure(event, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    request = make_request(event, path="/orga/test/")
    view = ConcreteTaskProgress(request)

    fake_result = _FakeTaskAsyncResult(ready=True, successful=False)
    task = SimpleNamespace(apply_async=lambda **kw: fake_result)

    response = view.dispatch_async_task(request, task, event_id=1)
    assert response.status_code == 302
    assert response.url == "/error/"
    msgs = list(request._messages)
    assert len(msgs) == 1
    assert str(msgs[0]) == "An error occurred. Please try again."


def test_async_task_progress_dispatch_async_task_non_eager_redirects(event, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False

    request = make_request(event, path="/orga/test/")
    view = ConcreteTaskProgress(request)

    fake_result = SimpleNamespace(id="task-uuid-123")
    task = SimpleNamespace(apply_async=lambda **kw: fake_result)

    response = view.dispatch_async_task(request, task, event_id=1)
    assert response.status_code == 302
    assert "async_id=task-uuid-123" in response.url


@pytest.mark.parametrize(
    "error", (OSError("Connection refused"), OperationalError("broker down"))
)
def test_async_task_progress_dispatch_async_task_broker_error(event, settings, error):
    settings.CELERY_TASK_ALWAYS_EAGER = False

    request = make_request(event, path="/orga/test/")
    view = ConcreteTaskProgress(request)

    def raise_error(**kw):
        raise error

    task = SimpleNamespace(apply_async=raise_error)

    response = view.dispatch_async_task(request, task, event_id=1)
    assert response.status_code == 302
    assert response.url == "/error/"
    assert [str(m) for m in request._messages] == [
        "Could not start background task. Please try again."
    ]


@pytest.mark.parametrize(
    ("headers", "successful", "status", "redirect_header", "url", "message"),
    (
        pytest.param(
            {"HX-Request": "true"},
            True,
            286,
            "HX-Redirect",
            "/success/",
            "Done",
            id="htmx_success",
        ),
        pytest.param(
            {"HX-Request": "true"},
            False,
            286,
            "HX-Redirect",
            "/error/",
            "An error occurred. Please try again.",
            id="htmx_failure",
        ),
        pytest.param(None, True, 302, "Location", "/success/", "Done", id="success"),
        pytest.param(
            None,
            False,
            302,
            "Location",
            "/error/",
            "An error occurred. Please try again.",
            id="failure",
        ),
    ),
)
def test_async_task_progress_check_progress_complete(
    event, headers, successful, status, redirect_header, url, message
):
    request = make_request(event, path="/orga/test/", headers=headers)
    request.GET = {"async_id": "done-id"}
    view = ConcreteTaskProgress(request)
    view._async_result = _FakeTaskAsyncResult(
        ready=True, successful=successful, result={"count": 3}
    )

    response = view._check_task_progress(request)

    assert response.status_code == status
    assert response[redirect_header] == url
    assert [str(m) for m in request._messages] == [message]


def test_async_task_progress_check_progress_htmx_in_progress(event):
    request = make_request(event, path="/orga/test/", headers={"HX-Request": "true"})
    request.GET = {"async_id": "running-id"}
    view = ConcreteTaskProgress(request)
    view._async_result = _FakeTaskAsyncResult(
        ready=False,
        successful=False,
        state="PROGRESS",
        info={"value": 50, "current": 5, "total": 10},
    )

    response = view._check_task_progress(request)
    assert response.status_code == 200
    content = response.content.decode()
    assert "5" in content
    assert "10" in content


def test_async_task_progress_check_progress_htmx_pending_no_info(event):
    request = make_request(event, path="/orga/test/", headers={"HX-Request": "true"})
    request.GET = {"async_id": "pending-id"}
    view = ConcreteTaskProgress(request)
    view._async_result = _FakeTaskAsyncResult(
        ready=False, successful=False, state="PENDING"
    )

    response = view._check_task_progress(request)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Processing" in content
    assert "/error/" in content


def test_async_task_progress_check_progress_non_htmx_pending(event):
    request = make_request(event, path="/orga/test/")
    request.GET = {"async_id": "pending-id"}
    view = ConcreteTaskProgress(request)
    view._async_result = _FakeTaskAsyncResult(
        ready=False, successful=False, state="PENDING"
    )

    response = view._check_task_progress(request)
    assert response.status_code == 200
    content = response.content.decode()
    assert "pending-id" in content
    assert "/error/" in content
