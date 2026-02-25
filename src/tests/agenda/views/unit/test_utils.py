import pytest
from django.http import HttpResponse, HttpResponseNotModified
from django.urls import resolve
from django_scopes import scope, scopes_disabled

from pretalx.agenda.views.utils import (
    find_schedule_exporter,
    get_schedule_exporter_content,
    get_schedule_exporters,
    is_visible,
)
from pretalx.common.exporter import BaseExporter
from pretalx.common.signals import register_data_exporters
from tests.factories import EventFactory, TeamFactory, UserFactory
from tests.utils import make_request

pytestmark = pytest.mark.unit


class PublicExporter(BaseExporter):
    identifier = "test-public"
    verbose_name = "Test Public"
    public = True
    cors = None
    filename_identifier = "test-public"
    extension = "txt"
    content_type = "text/plain"
    icon = "fa-file"

    def get_data(self, request, **kwargs):
        return "public data"


class PrivateExporter(BaseExporter):
    identifier = "test-private"
    verbose_name = "Test Private"
    public = False
    cors = None
    filename_identifier = "test-private"
    extension = "txt"
    content_type = "text/plain"
    icon = "fa-file"


class CorsExporter(BaseExporter):
    identifier = "test-cors"
    verbose_name = "Test CORS"
    public = True
    cors = "*"
    filename_identifier = "test-cors"
    extension = "json"
    content_type = "application/json"
    icon = "fa-file"

    def get_data(self, request, **kwargs):
        return '{"data": "test"}'


class IsPublicMethodExporter(BaseExporter):
    identifier = "test-is-public-method"
    verbose_name = "Test Is Public Method"
    public = False
    cors = None
    filename_identifier = "test-is-public"
    extension = "txt"
    content_type = "text/plain"
    icon = "fa-file"
    _is_public_result = True

    def is_public(self, request):
        return self._is_public_result


class IsPublicMethodRaisingExporter(BaseExporter):
    """Exporter whose is_public raises, causing fallback to .public attribute."""

    identifier = "test-is-public-raising"
    verbose_name = "Test Is Public Raising"
    public = True
    cors = None
    filename_identifier = "test-raising"
    extension = "txt"
    content_type = "text/plain"
    icon = "fa-file"

    def is_public(self, request):
        raise ValueError("broken")


class FailingExporter(BaseExporter):
    identifier = "test-failing"
    verbose_name = "Test Failing"
    public = True
    cors = None
    filename_identifier = "test-failing"
    extension = "txt"
    content_type = "text/plain"
    icon = "fa-file"

    def render(self, **kwargs):
        raise RuntimeError("render failed")


class XmlExporter(BaseExporter):
    identifier = "test-xml"
    verbose_name = "Test XML"
    public = True
    cors = None
    filename_identifier = "test-xml"
    extension = "xml"
    content_type = "text/xml"
    icon = "fa-file"

    def get_data(self, request, **kwargs):
        return "<root/>"


def _make_schedule_request(event, user=None, query_params=None, headers=None):
    """Thin wrapper around ``make_request`` that sets the schedule path and
    ``resolver_match`` needed by the exporter visibility helpers."""
    path = f"/{event.slug}/schedule/"
    if query_params:
        path += "?" + "&".join(f"{k}={v}" for k, v in query_params.items())
    return make_request(
        event,
        user=user,
        path=path,
        headers=headers,
        resolver_match=resolve(f"/{event.slug}/schedule/"),
    )


@pytest.fixture
def orga_event():
    """An event with an organiser user who has can_change_submissions permission."""
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    return event, user


@pytest.fixture
def public_event_with_schedule():
    """A public event with a released schedule (making list_schedule pass for anon)."""
    event = EventFactory(is_public=True)
    event.feature_flags["show_schedule"] = True
    event.save()
    with scope(event=event):
        event.release_schedule("v1")
    return event


@pytest.mark.django_db
def test_is_visible_private_organiser_has_access(orga_event, django_assert_num_queries):
    """Organisers can see non-public exports."""
    event, user = orga_event
    exporter = PrivateExporter(event)
    request = _make_schedule_request(event, user=user)

    with django_assert_num_queries(1):
        result = is_visible(exporter, request, public=False)

    assert result is True


@pytest.mark.django_db
def test_is_visible_private_anonymous_denied(event, django_assert_num_queries):
    """Anonymous users cannot see non-public exports."""
    exporter = PrivateExporter(event)
    request = _make_schedule_request(event)

    with django_assert_num_queries(0):
        result = is_visible(exporter, request, public=False)

    assert result is False


@pytest.mark.django_db
def test_is_visible_public_without_list_schedule_permission(event):
    """Public visibility requires schedule.list_schedule; non-public event fails."""
    exporter = PublicExporter(event)
    request = _make_schedule_request(event)

    with scope(event=event):
        result = is_visible(exporter, request, public=True)

    assert result is False


@pytest.mark.django_db
def test_is_visible_public_with_schedule_uses_public_attribute(
    public_event_with_schedule,
):
    """When schedule is visible and exporter has no is_public method, uses .public."""
    event = public_event_with_schedule
    exporter = PublicExporter(event)
    request = _make_schedule_request(event)

    with scope(event=event):
        result = is_visible(exporter, request, public=True)

    assert result is True


@pytest.mark.parametrize(
    ("is_public_result", "expected"),
    ((True, True), (False, False)),
    ids=["is_public_returns_true", "is_public_returns_false"],
)
@pytest.mark.django_db
def test_is_visible_public_delegates_to_is_public_method(
    public_event_with_schedule, is_public_result, expected
):
    """When exporter has is_public method, its return value determines visibility."""
    event = public_event_with_schedule
    exporter = IsPublicMethodExporter(event)
    exporter._is_public_result = is_public_result
    request = _make_schedule_request(event)

    with scope(event=event):
        result = is_visible(exporter, request, public=True)

    assert result is expected


@pytest.mark.django_db
def test_is_visible_public_is_public_method_raising_falls_back_to_attribute(
    public_event_with_schedule,
):
    """When is_public raises, falls back to .public attribute."""
    event = public_event_with_schedule
    exporter = IsPublicMethodRaisingExporter(event)
    request = _make_schedule_request(event)

    with scope(event=event):
        result = is_visible(exporter, request, public=True)

    assert result is True


@pytest.mark.django_db
def test_is_visible_public_private_exporter_hidden(public_event_with_schedule):
    """Exporter with public=False is not visible publicly."""
    event = public_event_with_schedule
    exporter = PrivateExporter(event)
    request = _make_schedule_request(event)

    with scope(event=event):
        result = is_visible(exporter, request, public=True)

    assert result is False


@pytest.mark.django_db
def test_get_schedule_exporters_returns_visible(
    public_event_with_schedule, register_signal_handler, django_assert_num_queries
):
    """Registered exporters that pass visibility checks are returned."""
    event = public_event_with_schedule

    def handler(signal, sender, **kwargs):
        return PublicExporter

    register_signal_handler(register_data_exporters, handler)
    request = _make_schedule_request(event)

    with scope(event=event), django_assert_num_queries(1):
        exporters = get_schedule_exporters(request, public=True)

    test_exporters = [e for e in exporters if isinstance(e, PublicExporter)]
    assert len(test_exporters) == 1
    assert all(not isinstance(e, Exception) for e in exporters)


@pytest.mark.django_db
def test_get_schedule_exporters_excludes_exceptions(
    public_event_with_schedule, register_signal_handler
):
    """Exceptions from signal handlers are filtered out."""
    event = public_event_with_schedule

    def handler(signal, sender, **kwargs):
        raise RuntimeError("broken plugin")

    register_signal_handler(register_data_exporters, handler)
    request = _make_schedule_request(event)

    with scope(event=event):
        exporters = get_schedule_exporters(request, public=True)

    assert all(not isinstance(e, RuntimeError) for e in exporters)


@pytest.mark.django_db
def test_get_schedule_exporters_excludes_invisible(
    public_event_with_schedule, register_signal_handler
):
    """Exporters that fail visibility checks are excluded."""
    event = public_event_with_schedule

    def handler(signal, sender, **kwargs):
        return PrivateExporter

    register_signal_handler(register_data_exporters, handler)
    request = _make_schedule_request(event)

    with scope(event=event):
        exporters = get_schedule_exporters(request, public=True)

    assert all(not isinstance(e, PrivateExporter) for e in exporters)


@pytest.mark.django_db
def test_find_schedule_exporter_returns_matching(
    public_event_with_schedule, register_signal_handler
):
    """Finding by identifier returns the matching exporter."""
    event = public_event_with_schedule

    def handler(signal, sender, **kwargs):
        return PublicExporter

    register_signal_handler(register_data_exporters, handler)
    request = _make_schedule_request(event)

    with scope(event=event):
        exporter = find_schedule_exporter(request, "test-public", public=True)

    assert isinstance(exporter, PublicExporter)


@pytest.mark.django_db
def test_find_schedule_exporter_returns_none_when_not_found(
    public_event_with_schedule, register_signal_handler
):
    """Non-existent identifier returns None."""
    event = public_event_with_schedule

    def handler(signal, sender, **kwargs):
        return PublicExporter

    register_signal_handler(register_data_exporters, handler)
    request = _make_schedule_request(event)

    with scope(event=event):
        exporter = find_schedule_exporter(request, "nonexistent", public=True)

    assert exporter is None


@pytest.mark.django_db
def test_get_schedule_exporter_content_returns_none_when_no_exporter(orga_event):
    """Returns None when no exporter matches the name."""
    event, user = orga_event
    request = _make_schedule_request(event, user=user)

    with scopes_disabled():
        schedule = event.wip_schedule

    result = get_schedule_exporter_content(request, "nonexistent", schedule)

    assert result is None


@pytest.mark.django_db
def test_get_schedule_exporter_content_returns_response(
    orga_event, register_signal_handler, django_assert_num_queries
):
    """Returns HttpResponse with correct content type and data."""
    event, user = orga_event

    def handler(signal, sender, **kwargs):
        return PublicExporter

    register_signal_handler(register_data_exporters, handler)
    request = _make_schedule_request(event, user=user)

    with scopes_disabled():
        schedule = event.wip_schedule

    with django_assert_num_queries(1):
        result = get_schedule_exporter_content(request, "test-public", schedule)

    assert isinstance(result, HttpResponse)
    assert result["Content-Type"] == "text/plain"
    assert b"public data" in result.content
    assert "Content-Disposition" in result
    assert "ETag" in result


@pytest.mark.django_db
def test_get_schedule_exporter_content_etag_match_returns_not_modified(
    orga_event, register_signal_handler, django_assert_num_queries
):
    """Matching If-None-Match ETag returns 304 Not Modified."""
    event, user = orga_event

    def handler(signal, sender, **kwargs):
        return PublicExporter

    register_signal_handler(register_data_exporters, handler)

    with scopes_disabled():
        schedule = event.wip_schedule

    request = _make_schedule_request(event, user=user)
    response = get_schedule_exporter_content(request, "test-public", schedule)
    etag = response["ETag"].strip('"')

    request = _make_schedule_request(event, user=user, headers={"If-None-Match": etag})
    with django_assert_num_queries(0):
        result = get_schedule_exporter_content(request, "test-public", schedule)

    assert isinstance(result, HttpResponseNotModified)


@pytest.mark.parametrize(
    ("exporter_class", "identifier"),
    ((CorsExporter, "test-cors"), (XmlExporter, "test-xml")),
    ids=["json", "xml"],
)
@pytest.mark.django_db
def test_get_schedule_exporter_content_no_content_disposition_for_browsable_types(
    orga_event, register_signal_handler, exporter_class, identifier
):
    """JSON and XML content types omit Content-Disposition header."""
    event, user = orga_event

    def handler(signal, sender, **kwargs):
        return exporter_class

    register_signal_handler(register_data_exporters, handler)
    request = _make_schedule_request(event, user=user)

    with scopes_disabled():
        schedule = event.wip_schedule

    result = get_schedule_exporter_content(request, identifier, schedule)

    assert isinstance(result, HttpResponse)
    assert "Content-Disposition" not in result


@pytest.mark.django_db
def test_get_schedule_exporter_content_sets_cors_header(
    orga_event, register_signal_handler
):
    """Exporter with cors attribute sets Access-Control-Allow-Origin header."""
    event, user = orga_event

    def handler(signal, sender, **kwargs):
        return CorsExporter

    register_signal_handler(register_data_exporters, handler)
    request = _make_schedule_request(event, user=user)

    with scopes_disabled():
        schedule = event.wip_schedule

    result = get_schedule_exporter_content(request, "test-cors", schedule)

    assert result["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_get_schedule_exporter_content_returns_none_on_render_failure(
    orga_event, register_signal_handler
):
    """Returns None when exporter.render() raises an exception."""
    event, user = orga_event

    def handler(signal, sender, **kwargs):
        return FailingExporter

    register_signal_handler(register_data_exporters, handler)
    request = _make_schedule_request(event, user=user)

    with scopes_disabled():
        schedule = event.wip_schedule

    result = get_schedule_exporter_content(request, "test-failing", schedule)

    assert result is None


@pytest.mark.parametrize(
    "lang", ("valid", "nonexistent-lang"), ids=["valid_lang", "invalid_lang_falls_back"]
)
@pytest.mark.django_db
def test_get_schedule_exporter_content_lang_handling(
    orga_event, register_signal_handler, lang
):
    """Valid lang activates that language; invalid lang falls back to event locale."""
    event, user = orga_event

    def handler(signal, sender, **kwargs):
        return PublicExporter

    register_signal_handler(register_data_exporters, handler)
    lang_value = event.locale if lang == "valid" else lang
    request = _make_schedule_request(
        event, user=user, query_params={"lang": lang_value}
    )

    with scopes_disabled():
        schedule = event.wip_schedule

    result = get_schedule_exporter_content(request, "test-public", schedule)

    assert isinstance(result, HttpResponse)
