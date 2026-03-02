# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from io import BytesIO
from types import SimpleNamespace
from urllib.parse import quote

import celery.result
import pytest
from django.conf import settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import Http404, QueryDict
from django.test import RequestFactory
from django.utils.module_loading import import_string
from django.views.generic import ListView
from django.views.generic.edit import FormMixin

from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.views.mixins import (
    ActionConfirmMixin,
    AsyncFileDownloadMixin,
    EventPermissionRequired,
    Filterable,
    OrderActionMixin,
    PaginationMixin,
    PermissionRequired,
    SensibleBackWizardMixin,
    SocialMediaCardMixin,
    reorder_queryset,
)
from pretalx.submission.models import Submission, Track
from tests.factories import (
    CachedFileFactory,
    EventFactory,
    SubmissionFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import SimpleSession, make_orga_user, make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _qd(**kwargs):
    """Build an immutable QueryDict from keyword arguments."""
    qd = QueryDict(mutable=True)
    for key, value in kwargs.items():
        qd[key] = value
    qd._mutable = False
    return qd


class ConcreteFilterable(Filterable):
    filter_fields = ["state"]
    default_filters = ["title__icontains"]
    model = None

    def __init__(self, request, *, filter_fields=None, default_filters=None):
        self.request = request
        if filter_fields is not None:
            self.filter_fields = filter_fields
        if default_filters is not None:
            self.default_filters = default_filters


def test_filterable_get_default_filters():
    request = SimpleNamespace(GET={})
    f = ConcreteFilterable(request, default_filters=["name__icontains"])
    assert f.get_default_filters() == ["name__icontains"]


def test_filterable_handle_search_multiple_filters_ors(event):
    """handle_search with more than one filter field ORs them together."""
    sub_title = SubmissionFactory(event=event, title="submitted", state="accepted")
    sub_state = SubmissionFactory(event=event, title="Other Talk", state="submitted")
    SubmissionFactory(event=event, title="Unrelated", state="accepted")

    result = Filterable.handle_search(
        event.submissions.all(), "submitted", ["title__icontains", "state__icontains"]
    )
    assert set(result) == {sub_title, sub_state}


def test_filterable_handle_search_single_filter(event):
    """handle_search with exactly one filter field applies it directly."""
    sub = SubmissionFactory(event=event, title="Finding Nemo")
    SubmissionFactory(event=event, title="The Matrix")

    result = Filterable.handle_search(
        event.submissions.all(), "Finding", ["title__icontains"]
    )
    assert list(result) == [sub]


def test_filterable_handle_search_no_filters(event):
    """handle_search with no filter fields returns the queryset unchanged."""
    sub = SubmissionFactory(event=event)

    result = Filterable.handle_search(event.submissions.all(), "anything", [])
    assert list(result) == [sub]


def test_filterable_handle_filter_basic(event):
    """_handle_filter applies simple key=value filters from GET params."""
    sub1 = SubmissionFactory(event=event, state="submitted")
    SubmissionFactory(event=event, state="accepted")

    request = make_request(event)
    request.GET = _qd(state="submitted")
    f = ConcreteFilterable(request)
    result = f._handle_filter(event.submissions.all())
    assert list(result) == [sub1]


def test_filterable_handle_filter_or_lookup(event):
    """_handle_filter supports value__key OR lookups via __ in values."""
    sub1 = SubmissionFactory(event=event, state="submitted")
    sub2 = SubmissionFactory(event=event, state="accepted")
    SubmissionFactory(event=event, state="rejected")

    qd = QueryDict(mutable=True)
    qd.setlist("filter", ["state__submitted", "state__accepted"])
    request = make_request(event)
    request.GET = qd
    f = ConcreteFilterable(request, filter_fields=["state"])
    result = f._handle_filter(event.submissions.all())
    assert set(result) == {sub1, sub2}


def test_filterable_handle_filter_isnull(event):
    """_handle_filter handles __isnull lookups as boolean, not list."""
    track = TrackFactory(event=event, name="Test Track", color="#000000")
    SubmissionFactory(event=event, track=track)  # must exist for filter test
    sub_without_track = SubmissionFactory(event=event)

    request = make_request(event)
    request.GET = _qd(track__isnull="on")
    f = ConcreteFilterable(request, filter_fields=["track__isnull"])
    result = f._handle_filter(event.submissions.all())
    assert list(result) == [sub_without_track]


def test_filterable_handle_filter_ignores_empty_values(event):
    """_handle_filter skips empty values in filter fields."""
    sub = SubmissionFactory(event=event, state="submitted")

    request = make_request(event)
    request.GET = _qd(state="")
    f = ConcreteFilterable(request)
    result = f._handle_filter(event.submissions.all())
    assert list(result) == [sub]


def test_filterable_handle_filter_ignores_non_filter_fields(event):
    """_handle_filter ignores GET params not in filter_fields."""
    sub = SubmissionFactory(event=event, state="submitted")

    request = make_request(event)
    request.GET = _qd(title="test")
    f = ConcreteFilterable(request, filter_fields=["state"])
    result = f._handle_filter(event.submissions.all())
    assert list(result) == [sub]


def test_filterable_filter_queryset_with_search(event):
    """filter_queryset applies text search when 'q' is in GET params."""
    sub1 = SubmissionFactory(event=event, title="Finding Nemo")
    SubmissionFactory(event=event, title="The Matrix")

    request = make_request(event)
    request.GET = _qd(q="Finding Nemo")
    f = ConcreteFilterable(
        request, filter_fields=[], default_filters=["title__icontains"]
    )
    result = f.filter_queryset(event.submissions.all())
    assert list(result) == [sub1]


def test_filterable_filter_queryset_with_filter_fields_and_search(event):
    """filter_queryset applies both _handle_filter and search together."""
    sub1 = SubmissionFactory(event=event, title="Finding Nemo", state="submitted")
    SubmissionFactory(event=event, title="Finding Dory", state="accepted")
    SubmissionFactory(event=event, title="The Matrix", state="submitted")

    request = make_request(event)
    qd = QueryDict(mutable=True)
    qd["state"] = "submitted"
    qd["q"] = "Finding"
    request.GET = qd

    class FilterableNoForm(ConcreteFilterable):
        @property
        def filter_form(self):
            return None

    f = FilterableNoForm(
        request, filter_fields=["state"], default_filters=["title__icontains"]
    )
    result = f.filter_queryset(event.submissions.all())
    assert list(result) == [sub1]


def test_filterable_filter_queryset_with_filter_form(event):
    """filter_queryset calls filter_form.filter_queryset when the form
    is valid and has that method."""
    SubmissionFactory(event=event)

    request = make_request(event)
    request.GET = _qd()

    class FakeFilterForm:
        def is_valid(self):
            return True

        def filter_queryset(self, qs):
            return qs.none()

    class FilterableWithForm(ConcreteFilterable):
        @property
        def filter_form(self):
            return FakeFilterForm()

    f = FilterableWithForm(request, filter_fields=[])
    result = f.filter_queryset(event.submissions.all())
    assert list(result) == []


def test_filterable_search_form_with_q():
    """search_form is populated when 'q' is in GET."""
    request = SimpleNamespace(GET={"q": "django"})
    f = ConcreteFilterable(request, filter_fields=[])
    assert f.search_form.data.get("q") == "django"


def test_filterable_search_form_without_q():
    """search_form is unbound when 'q' is not in GET."""
    request = SimpleNamespace(GET={})
    f = ConcreteFilterable(request, filter_fields=[])
    assert not f.search_form.is_bound


def test_filterable_filter_form_with_filter_form_class(event):
    """filter_form uses filter_form_class when defined."""
    request = make_request(event)

    class FakeForm:
        def __init__(self, data, event):
            self.data = data
            self.event = event

    f = ConcreteFilterable(request, filter_fields=[])
    f.filter_form_class = FakeForm
    assert isinstance(f.filter_form, FakeForm)
    assert f.filter_form.event is event


def test_filterable_filter_form_with_get_filter_form(event):
    """filter_form uses get_filter_form when defined."""
    request = make_request(event)
    sentinel = object()

    f = ConcreteFilterable(request, filter_fields=[])
    f.get_filter_form = lambda: sentinel
    assert f.filter_form is sentinel


def test_filterable_filter_form_from_filter_fields(event):
    """filter_form auto-generates a form from filter_fields when no
    filter_form_class or get_filter_form is present."""
    request = make_request(event)
    f = ConcreteFilterable(request, filter_fields=["state"])
    f.model = Submission
    form = f.filter_form
    assert form is not None
    assert "state" in form.fields
    assert form.fields["state"].required is False


def test_filterable_filter_form_fk_queryset_filtered_by_event(event):
    """filter_form auto-generated from filter_fields filters FK querysets
    by event, excluding tracks from other events."""
    TrackFactory(event=event, name="Mine")
    other_event = EventFactory()
    TrackFactory(event=other_event, name="Theirs")

    request = make_request(event)
    f = ConcreteFilterable(request, filter_fields=["track"])
    f.model = Submission
    form = f.filter_form
    assert form is not None
    assert form.fields["track"].required is False
    tracks = list(form.fields["track"].queryset)
    assert len(tracks) == 1
    assert tracks[0].event == event


def test_filterable_filter_form_returns_none_when_no_fields():
    """filter_form returns None when filter_fields is empty and no
    custom form class/method is defined."""
    request = SimpleNamespace(GET={})
    f = ConcreteFilterable(request, filter_fields=[])
    assert f.filter_form is None


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


def test_permission_required_permission_object_delegates_to_get_permission_object(
    event,
):
    """permission_object delegates to get_permission_object."""
    obj = FakePermissionObject()
    request = make_request(event)
    view = ConcretePermissionRequired(request, obj=obj)
    result = PermissionRequired.permission_object.__get__(view)
    assert result is obj


def test_permission_required_object_cached_property(event):
    """object cached_property delegates to get_object."""
    obj = FakePermissionObject()
    request = make_request(event)
    view = ConcretePermissionRequired(request, obj=obj)
    assert PermissionRequired.object.__get__(view) is obj


def test_permission_required_permission_action_edit_with_write_perm(event):
    """permission_action returns 'edit' when user has write permission and
    pk is in kwargs."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = ConcretePermissionRequired(request, obj=event, pk=1)
    view.write_permission_required = "orga.change_settings"
    result = PermissionRequired.permission_action.__get__(view)
    assert result == "edit"


def test_permission_required_permission_action_view_without_write_perm(event):
    """permission_action returns 'view' when user lacks write permission
    and pk is in kwargs."""
    user = UserFactory()
    request = make_request(event, user=user)
    view = ConcretePermissionRequired(request, obj=event, pk=1)
    result = PermissionRequired.permission_action.__get__(view)
    assert result == "view"


def test_permission_required_permission_action_create_with_create_perm(event):
    """permission_action returns 'create' when no pk/code in kwargs and
    create_permission_required is set and the user has it."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    # Non-empty kwargs without pk/code triggers the create branch
    view = ConcretePermissionRequired(request, obj=event, event="test")
    view.create_permission_required = "orga.change_settings"
    result = PermissionRequired.permission_action.__get__(view)
    assert result == "create"


def test_permission_required_permission_action_create_raises_404_without_perm(event):
    """permission_action raises Http404 when create_permission_required is set
    but the user lacks the permission."""
    user = UserFactory()
    request = make_request(event, user=user)
    view = ConcretePermissionRequired(request, obj=event, event="test")
    view.create_permission_required = "orga.change_settings"
    with pytest.raises(Http404):
        PermissionRequired.permission_action.__get__(view)


def test_permission_required_permission_action_create_fallback(event):
    """permission_action returns 'create' when no pk/code in kwargs and no
    create_permission but the user has write_permission."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = ConcretePermissionRequired(request, obj=event, event="test")
    view.create_permission_required = None
    view.write_permission_required = "orga.change_settings"
    result = PermissionRequired.permission_action.__get__(view)
    assert result == "create"


def test_permission_required_permission_action_view_when_no_create_no_write(event):
    """permission_action returns 'view' when no pk/code, no create perm,
    and no write perm."""
    user = UserFactory()
    request = make_request(event, user=user)
    view = ConcretePermissionRequired(request, obj=event, event="test")
    view.create_permission_required = None
    result = PermissionRequired.permission_action.__get__(view)
    assert result == "view"


def test_permission_required_get_login_url_raises_404(event):
    """get_login_url raises Http404 to avoid leaking page existence."""
    request = make_request(event)
    view = ConcretePermissionRequired(request, obj=None)
    with pytest.raises(Http404):
        view.get_login_url()


def test_permission_required_handle_no_permission_raises_404(event):
    """handle_no_permission raises Http404 for authenticated users."""
    user = UserFactory.build()
    request = make_request(event, user=user)
    request.resolver_match = SimpleNamespace(namespaces=["orga"])
    view = ConcretePermissionRequired(request, obj=None)
    with pytest.raises(Http404):
        view.handle_no_permission()


def test_permission_required_handle_no_permission_redirects_anonymous_cfp(event):
    """handle_no_permission redirects anonymous users in the cfp namespace
    to the login page with a next parameter."""
    request = make_request(event, path="/test/cfp/submit/")
    request.resolver_match = SimpleNamespace(namespaces=["cfp"])
    view = ConcretePermissionRequired(request, obj=None)
    response = view.handle_no_permission()
    expected_url = event.urls.login + f"?next={quote('/test/cfp/submit/')}"
    assert response.status_code == 302
    assert response.url == expected_url


def test_permission_required_handle_no_permission_anonymous_cfp_with_params(event):
    """handle_no_permission preserves GET parameters when redirecting
    anonymous cfp users."""
    request = make_request(event, path="/test/cfp/submit/")
    request.resolver_match = SimpleNamespace(namespaces=["cfp"])
    request.GET = _qd(token="abc123")
    view = ConcretePermissionRequired(request, obj=None)
    response = view.handle_no_permission()
    assert response.status_code == 302
    assert "token=abc123" in response.url


def test_permission_required_has_permission_via_session_event_access(event):
    """has_permission returns True when the parent session contains
    'event_access' data."""
    session_store = import_string(f"{settings.SESSION_ENGINE}.SessionStore")
    parent_session = session_store()
    parent_session["event_access"] = True
    parent_session.create()

    request = make_request(event)
    session = SimpleSession()
    session[f"pretalx_event_access_{event.pk}"] = parent_session.session_key
    request.session = session

    view = ConcretePermissionRequired(request, obj=event)
    assert view.has_permission() is True


def test_permission_required_has_permission_returns_false_without_access(event):
    """has_permission returns False when session has no event_access."""
    user = UserFactory()
    request = make_request(event, user=user)
    view = ConcretePermissionRequired(request, obj=event)
    assert view.has_permission() is False


def test_permission_required_has_permission_no_event_on_request(event):
    """has_permission skips session check when request has no event attribute."""
    user = UserFactory()
    request = make_request(event, user=user)
    del request.event
    view = ConcretePermissionRequired(request, obj=event)
    assert view.has_permission() is False


def test_permission_required_has_permission_returns_true_via_super(event):
    """has_permission returns True when the parent mixin grants access."""
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)

    class PermWithRealPerm(PermissionRequired):
        permission_required = "orga.change_settings"

        def get_object(self):
            return self._obj

    view = PermWithRealPerm()
    view.request = request
    view.kwargs = {}
    view._obj = event
    assert view.has_permission() is True


def test_permission_required_get_form_kwargs_read_only(event):
    """get_form_kwargs includes read_only=True when permission_action is 'view'
    and the form class uses ReadOnlyFlag."""

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
    """EventPermissionRequired.get_permission_object returns request.event."""

    class ConcreteEventPerm(EventPermissionRequired):
        permission_required = "test.view"

    request = make_request(event)
    view = ConcreteEventPerm()
    view.request = request
    view.kwargs = {}
    assert view.get_permission_object() is event


def test_permission_required_get_form_kwargs_locales_for_i18n(event):
    """get_form_kwargs includes locales for PretalxI18nModelForm subclasses."""
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
    def __init__(self, current, last):
        self.current = current
        self.last = last


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


def test_sensible_back_wizard_post_valid_form_next_step():
    """post proceeds to next step when form is valid and not last step."""
    request = _wizard_post_data("step1")
    view = ConcreteWizard(request, steps_current="step1", steps_last="step2")

    class FakeForm:
        cleaned_data = {"field": "value"}

        def is_valid(self):
            return True

    view._form = FakeForm()
    result = view.post()
    assert result == "next"
    assert view.storage.step_data["step1"] == {"field": "value"}


def test_sensible_back_wizard_post_valid_form_last_step():
    """post calls render_done when form is valid and it's the last step."""
    request = _wizard_post_data("step2")
    view = ConcreteWizard(request, steps_current="step2", steps_last="step2")

    class FakeForm:
        cleaned_data = {"field": "done"}

        def is_valid(self):
            return True

    view._form = FakeForm()
    result = view.post()
    assert result == "done"


def test_sensible_back_wizard_post_valid_form_goto_step():
    """post saves data and goes to requested step when wizard_goto_step is set."""
    request = _wizard_post_data("step2", wizard_goto_step="step1")
    view = ConcreteWizard(request, steps_current="step2", steps_last="step2")

    class FakeForm:
        cleaned_data = {"field": "saved"}

        def is_valid(self):
            return True

    view._form = FakeForm()
    result = view.post()
    assert result == "goto:step1"
    assert view.storage.step_data["step2"] == {"field": "saved"}


def test_sensible_back_wizard_post_invalid_form():
    """post re-renders when form is invalid."""
    request = _wizard_post_data("step1")
    view = ConcreteWizard(request, steps_current="step1", steps_last="step2")

    class FakeForm:
        def is_valid(self):
            return False

    view._form = FakeForm()
    result = view.post()
    assert result == "invalid"


def test_sensible_back_wizard_post_invalid_management_form():
    """post raises ValidationError when management form is invalid."""
    rf = RequestFactory()
    request = rf.post("/wizard/", data={})
    view = ConcreteWizard(request, steps_current="step1", steps_last="step2")
    with pytest.raises(ValidationError):
        view.post()


def test_sensible_back_wizard_post_step_mismatch():
    """post updates storage.current_step when form step differs from steps.current."""
    request = _wizard_post_data("step2")
    view = ConcreteWizard(request, steps_current="step1", steps_last="step2")
    view.storage.current_step = "step1"

    class FakeForm:
        cleaned_data = {"field": "value"}

        def is_valid(self):
            return True

    view._form = FakeForm()
    view.post()
    assert view.storage.current_step == "step2"


@pytest.mark.parametrize(
    ("image_field", "expect_404"),
    ((None, True), ("og_image", False), ("logo", False), ("header_image", False)),
    ids=["no_images", "og_image", "logo", "header_image"],
)
def test_social_media_card_get_fallback(event, make_image, image_field, expect_404):
    """SocialMediaCardMixin.get falls through og_image → logo → header_image → 404."""
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
    """SocialMediaCardMixin.get returns get_image result when available."""

    class ConcreteCard(SocialMediaCardMixin):
        def get_image(self):
            return BytesIO(b"fake-image-data")

    view = ConcreteCard()
    request = make_request(event)
    view.request = request
    response = view.get(request)
    assert response.status_code == 200


class ConcretePagination(PaginationMixin):
    def __init__(self, request):
        self.request = request


def test_pagination_get_paginate_by_default(event):
    """get_paginate_by returns DEFAULT_PAGINATION when no custom size is set."""
    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    view = ConcretePagination(request)
    assert view.get_paginate_by() == 50


def test_pagination_get_paginate_by_from_session(event):
    """get_paginate_by returns stored session value when available."""
    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    request.session["stored_page_size_test_list"] = 25
    view = ConcretePagination(request)
    assert view.get_paginate_by() == 25


def test_pagination_get_paginate_by_from_class_attribute(event):
    """get_paginate_by uses the view's paginate_by attribute as fallback."""
    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    view = ConcretePagination(request)
    view.paginate_by = 10
    assert view.get_paginate_by() == 10


@pytest.mark.parametrize(
    ("page_size", "expected"), (("20", 20), ("100", 100), ("250", 250))
)
def test_pagination_get_paginate_by_from_get_param(event, page_size, expected):
    """get_paginate_by uses page_size GET parameter and stores it in session."""
    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    request.GET = {"page_size": page_size}
    view = ConcretePagination(request)
    result = view.get_paginate_by()
    assert result == expected
    assert request.session["stored_page_size_test_list"] == expected


def test_pagination_get_paginate_by_respects_max_page_size(event, settings):
    """get_paginate_by caps page_size at MAX_PAGINATION_LIMIT."""
    settings.MAX_PAGINATION_LIMIT = 100
    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    request.GET = {"page_size": "200"}
    view = ConcretePagination(request)
    result = view.get_paginate_by()
    assert result == 100


def test_pagination_get_paginate_by_no_max_limit(event, settings):
    """get_paginate_by allows unlimited page sizes when max_page_size is 0/None."""
    settings.MAX_PAGINATION_LIMIT = 0
    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    request.GET = {"page_size": "9999"}
    view = ConcretePagination(request)
    view.max_page_size = 0
    result = view.get_paginate_by()
    assert result == 9999


def test_pagination_get_paginate_by_invalid_page_size(event):
    """get_paginate_by returns default when page_size is not a valid integer."""
    request = make_request(event)
    request.resolver_match = SimpleNamespace(url_name="test_list")
    request.GET = {"page_size": "abc"}
    view = ConcretePagination(request)
    assert view.get_paginate_by() == 50


def test_pagination_get_context_data_non_crud(event):
    """get_context_data passes through for non-CRUDView subclasses."""

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
    """Minimal base class providing get_context_data for MRO."""

    def get_context_data(self, **kwargs):
        return kwargs


class ConcreteActionConfirm(ActionConfirmMixin, _BaseContext):
    def __init__(self, request):
        self.request = request


def test_action_confirm_action_back_url_from_next_param(event):
    """action_back_url reads from the 'next' GET parameter."""
    request = make_request(event, path="/orga/event/delete/")
    request.GET = {"next": "/orga/event/"}
    view = ConcreteActionConfirm(request)
    assert view.action_back_url == "/orga/event/"


def test_action_confirm_action_back_url_from_back_param(event):
    """action_back_url reads from the 'back' GET parameter as fallback."""
    request = make_request(event, path="/orga/event/delete/")
    request.GET = {"back": "/orga/speakers/"}
    view = ConcreteActionConfirm(request)
    assert view.action_back_url == "/orga/speakers/"


def test_action_confirm_action_back_url_fallback(event):
    """action_back_url falls back to two levels up when no GET param."""
    request = make_request(event, path="/orga/event/delete/")
    request.GET = {}
    view = ConcreteActionConfirm(request)
    assert view.action_back_url == "/orga/event"


def test_action_confirm_get_context_data(event):
    """get_context_data provides action template variables and buttons."""
    request = make_request(event, path="/orga/event/delete/")
    request.GET = {"next": "/orga/"}
    view = ConcreteActionConfirm(request)
    ctx = view.get_context_data()
    assert ctx["action_title"] is not None
    assert ctx["action_text"] is not None
    assert len(ctx["submit_buttons"]) == 1
    assert ctx["submit_buttons"][0].icon == "trash"
    assert len(ctx["submit_buttons_extra"]) == 1


def test_reorder_queryset_updates_positions(event):
    """reorder_queryset updates position fields based on the given ID order."""
    t1 = TrackFactory(event=event, name="First", position=0, color="#111111")
    t2 = TrackFactory(event=event, name="Second", position=1, color="#222222")
    t3 = TrackFactory(event=event, name="Third", position=2, color="#333333")

    reorder_queryset(
        Track.objects.filter(event=event), [str(t3.pk), str(t1.pk), str(t2.pk)]
    )

    t1.refresh_from_db()
    t2.refresh_from_db()
    t3.refresh_from_db()
    assert t3.position == 0
    assert t1.position == 1
    assert t2.position == 2


def test_reorder_queryset_raises_404_for_unknown_pk(event):
    """reorder_queryset raises Http404 when a PK is not in the queryset."""
    TrackFactory(event=event, name="First", position=0, color="#111111")
    with pytest.raises(Http404):
        reorder_queryset(Track.objects.filter(event=event), ["99999"])


def test_order_action_mixin_order_handler(event):
    """order_handler calls reorder_queryset with the posted order."""
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
    result = view.order_handler(request)
    assert result == "list_response"

    t1.refresh_from_db()
    t2.refresh_from_db()
    assert t2.position == 0
    assert t1.position == 1


def test_order_action_mixin_order_handler_empty_order(event):
    """order_handler does nothing when order is empty."""
    TrackFactory(event=event, name="A", position=0, color="#111111")

    class ConcreteOrderView(OrderActionMixin):
        def __init__(self, request, _event):
            self.request = request
            self._event = _event

        def list(self, request, *args, **kwargs):
            return "ok"

    request = make_request(event, method="post", path="/order/")
    request.POST = {"order": ""}
    view = ConcreteOrderView(request, event)
    assert view.order_handler(request) == "ok"


def _add_messages(request):
    """Attach a message storage backend to a RequestFactory request so
    that django.contrib.messages calls don't fail."""
    request._messages = FallbackStorage(request)
    return request


class _FakeAsyncResult:
    """Lightweight stand-in for celery.result.AsyncResult, injected via
    the overridable _get_async_result hook instead of monkeypatching."""

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


def test_async_download_get_context_returns_empty_dict():
    view = AsyncFileDownloadMixin()
    assert view.get_async_download_context() == {}


def test_async_download_get_waiting_template():
    view = AsyncFileDownloadMixin()
    assert (
        view.get_async_waiting_template() == "orga/includes/async_download_waiting.html"
    )


def test_async_download_get_async_result_returns_celery_result(event):
    """The base _get_async_result returns a Celery AsyncResult."""
    request = make_request(event, path="/export/")
    view = ConcreteAsyncDownload(request)
    result = view._get_async_result("test-task-id")
    assert isinstance(result, celery.result.AsyncResult)
    assert result.id == "test-task-id"


def test_async_download_handle_cached_file_serves_file(event):
    """handle_async_download serves the file when cached_file param points
    to a file with content."""
    cf = CachedFileFactory()
    cf.file.save("test.zip", ContentFile(b"zipdata"))

    request = make_request(event, path="/export/")
    request.GET = {"cached_file": str(cf.id)}
    view = ConcreteAsyncDownload(request)
    response = view.handle_async_download(request)
    assert "attachment" in response["Content-Disposition"]


def test_async_download_handle_cached_file_missing_redirects(event):
    """handle_async_download redirects to error URL when cached_file has no file."""
    cf = CachedFileFactory()

    request = make_request(event, path="/export/")
    request.GET = {"cached_file": str(cf.id)}
    view = ConcreteAsyncDownload(request)
    response = view.handle_async_download(request)
    assert response.status_code == 302
    assert response.url == "/error/"


def test_async_download_handle_invalid_cached_file_id(event):
    """handle_async_download redirects to error URL for invalid UUID."""
    request = make_request(event, path="/export/")
    request.GET = {"cached_file": "not-a-uuid"}
    view = ConcreteAsyncDownload(request)
    response = view.handle_async_download(request)
    assert response.status_code == 302
    assert response.url == "/error/"


def test_async_download_start_task_eager_mode(event, settings):
    """_start_task in eager mode serves the file directly."""
    settings.CELERY_TASK_ALWAYS_EAGER = True

    class EagerDownload(AsyncFileDownloadMixin):
        def get_async_download_filename(self):
            return "eager.zip"

        def start_async_task(self, cached_file):
            cached_file.file.save("eager.zip", ContentFile(b"data"))
            return SimpleNamespace(id="fake")

    request = make_request(event, path="/export/")
    request.GET = {}
    view = EagerDownload()
    view.request = request
    response = view._start_task(request)
    assert "attachment" in response["Content-Disposition"]


def test_async_download_start_task_non_eager_redirects(event, settings):
    """_start_task redirects to async polling URL in non-eager mode."""
    settings.CELERY_TASK_ALWAYS_EAGER = False

    request = make_request(event, path="/export/")
    request.GET = {}
    view = ConcreteAsyncDownload(request)
    response = view._start_task(request)
    assert response.status_code == 302
    assert "async_id=fake-task-id" in response.url


def test_async_download_check_task_ready_success_htmx(event):
    """_check_task_status returns success template for ready+successful HTMX request."""
    cf = CachedFileFactory()
    cf.file.save("export.zip", ContentFile(b"zipdata"))

    request = make_request(event, path="/export/", headers={"HX-Request": "true"})
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(
        ready=True, successful=True, result=str(cf.id)
    )
    response = view._check_task_status(request, "test-id")
    content = response.content.decode()
    assert f"cached_file={cf.id}" in content


def test_async_download_check_task_ready_failed_htmx(event):
    """_check_task_status returns error template for ready+failed HTMX request."""
    request = make_request(event, path="/export/", headers={"HX-Request": "true"})
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(ready=True, successful=False)
    response = view._check_task_status(request, "test-id")
    content = response.content.decode()
    assert "/error/" in content


def test_async_download_check_task_pending_htmx(event):
    """_check_task_status returns waiting spinner for pending HTMX request."""
    request = make_request(event, path="/export/", headers={"HX-Request": "true"})
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(ready=False, successful=False)
    response = view._check_task_status(request, "test-id")
    assert response.status_code == 200


def test_async_download_check_task_ready_success_non_htmx(event):
    """_check_task_status serves the file directly for non-HTMX ready+success."""
    cf = CachedFileFactory()
    cf.file.save("export.zip", ContentFile(b"zipdata"))

    request = make_request(event, path="/export/")
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(
        ready=True, successful=True, result=str(cf.id)
    )
    response = view._check_task_status(request, "test-id")
    assert "attachment" in response["Content-Disposition"]


def test_async_download_check_task_ready_failed_non_htmx(event):
    """_check_task_status redirects to error URL for non-HTMX ready+failed."""
    request = make_request(event, path="/export/")
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(ready=True, successful=False)
    response = view._check_task_status(request, "test-id")
    assert response.status_code == 302
    assert response.url == "/error/"


def test_async_download_check_task_pending_non_htmx(event):
    """_check_task_status renders waiting template for non-HTMX pending request."""
    request = make_request(event, path="/export/")
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(ready=False, successful=False)
    response = view._check_task_status(request, "test-id")
    assert response.status_code == 200


def test_async_download_serve_cached_file_missing_file(event):
    """_serve_cached_file redirects to error URL when the file is missing
    from storage."""
    cf = CachedFileFactory()
    cf.file.name = "nonexistent/path.zip"
    cf.save()

    request = make_request(event, path="/export/")
    view = ConcreteAsyncDownload(request)
    response = view._serve_cached_file(request, cf)
    assert response.status_code == 302
    assert response.url == "/error/"


def test_async_download_check_task_result_invalid_uuid(event):
    """_check_task_status handles result being an invalid UUID gracefully."""
    request = make_request(event, path="/export/")
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(
        ready=True, successful=True, result="not-a-valid-uuid"
    )
    response = view._check_task_status(request, "test-id")
    assert response.status_code == 302
    assert response.url == "/error/"


def test_async_download_handle_routes_to_check_task(event):
    """handle_async_download routes to _check_task_status when async_id is present."""
    request = make_request(event, path="/export/")
    request.GET = {"async_id": "some-id"}
    view = ConcreteAsyncDownload(request)
    view._async_result = _FakeAsyncResult(ready=True, successful=False)
    response = view.handle_async_download(request)
    assert response.status_code == 302
    assert response.url == "/error/"


def test_async_download_handle_starts_task_when_no_params(event, settings):
    """handle_async_download starts a new task when neither cached_file
    nor async_id is in GET params."""
    settings.CELERY_TASK_ALWAYS_EAGER = False

    request = make_request(event, path="/export/")
    request.GET = {}
    view = ConcreteAsyncDownload(request)
    response = view.handle_async_download(request)
    assert response.status_code == 302
    assert "async_id=fake-task-id" in response.url
