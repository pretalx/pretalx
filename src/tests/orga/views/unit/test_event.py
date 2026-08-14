# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.common.signals import register_fonts
from pretalx.orga.views.event import (
    EventDetail,
    EventHistory,
    EventHistoryDetail,
    EventReviewSettings,
    FontPreviewCSS,
    InvitationView,
    PhaseActivate,
)
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    QuestionFactory,
    SubmissionFactory,
    TeamFactory,
    TeamInviteFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_event_detail_object_prefetches_extra_links(event, django_assert_num_queries):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)

    obj = view.object

    assert obj.pk == event.pk
    with django_assert_num_queries(0):
        list(obj.extra_links.all())


@pytest.mark.parametrize("is_admin", (True, False))
def test_event_detail_get_form_kwargs_is_administrator(is_admin):
    event = EventFactory()
    user = UserFactory(is_administrator=is_admin)
    TeamFactory(organiser=event.organiser, all_events=True).members.add(user)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)
    view.object  # noqa: B018 -- force cached_property

    kwargs = view.get_form_kwargs()

    assert kwargs["is_administrator"] is is_admin


@pytest.mark.parametrize("is_admin", (True, False))
def test_event_detail_context_delete_link_requires_admin(is_admin):
    event = EventFactory()
    user = UserFactory(is_administrator=is_admin)
    TeamFactory(organiser=event.organiser, all_events=True).members.add(user)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)
    view.object  # noqa: B018 -- force cached_property
    context = view.get_context_data()

    assert ("submit_buttons_extra" in context) is is_admin
    assert "submit_buttons" in context


def test_event_history_get_queryset(event):
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    ActivityLogFactory(
        event=event,
        person=user,
        content_object=submission,
        action_type="pretalx.submission.create",
    )
    request = make_request(event, user=user)
    view = make_view(EventHistory, request)

    qs = view.get_queryset()

    assert qs.count() == 1
    assert qs.first().event == event


def test_event_history_get_queryset_excludes_other_events(event):
    other_event = EventFactory()
    user = UserFactory()
    ActivityLogFactory(
        event=other_event,
        person=user,
        content_object=other_event,
        action_type="pretalx.event.update",
    )
    request = make_request(event, user=user)
    view = make_view(EventHistory, request)

    qs = view.get_queryset()

    assert qs.count() == 0


def test_event_history_detail_get_queryset_scoped_to_event(event):
    user = UserFactory()
    log = ActivityLogFactory(
        event=event,
        person=user,
        content_object=event,
        action_type="pretalx.event.update",
    )
    request = make_request(event, user=user)
    view = make_view(EventHistoryDetail, request, pk=log.pk)

    qs = view.get_queryset()

    assert list(qs) == [log]


@pytest.mark.parametrize(
    ("htmx_headers", "expected"), ((None, False), ({"HX-Request": "true"}, True))
)
def test_event_history_detail_is_htmx(event, htmx_headers, expected):
    user = make_orga_user(event)
    request = make_request(
        event, user=user, **({"headers": htmx_headers} if htmx_headers else {})
    )
    view = make_view(EventHistoryDetail, request)

    assert view.is_htmx is expected


@pytest.mark.parametrize(
    ("htmx_headers", "expected_template"),
    (
        (None, "orga/event/history_detail.html"),
        ({"HX-Request": "true"}, "orga/event/history_detail_content.html"),
    ),
)
def test_event_history_detail_get_template_names(
    event, htmx_headers, expected_template
):
    user = make_orga_user(event)
    request = make_request(
        event, user=user, **({"headers": htmx_headers} if htmx_headers else {})
    )
    view = make_view(EventHistoryDetail, request)

    assert view.get_template_names() == [expected_template]


def test_event_review_settings_question_table(event):
    user = make_orga_user(event, can_change_event_settings=True)
    with scope(event=event):
        reviewer_question = QuestionFactory(event=event, target="reviewer")
        QuestionFactory(event=event, target="submission")
    request = make_request(event, user=user)
    view = make_view(EventReviewSettings, request)

    table = view.table

    assert [row.record for row in table.rows] == [reviewer_question]
    assert table.name == "QuestionTable-reviews"
    assert (
        table.attrs["dragsort-url"]
        == f"{event.orga_urls.review_questions}?target=reviews"
    )


def test_phase_activate_get_object(event):
    with scope(event=event):
        phase = event.active_review_phase
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(PhaseActivate, request, pk=phase.pk)

    obj = view.get_object()

    assert obj == phase


def test_invitation_view_invitation_property(event):
    team = TeamFactory(organiser=event.organiser, all_events=True)
    invite = TeamInviteFactory(team=team, email="test@example.com")
    request = make_request(event)
    view = make_view(InvitationView, request, code=invite.token)

    result = view.invitation

    assert result == invite


def test_event_detail_context_includes_font_preview_url_when_fonts_available(
    register_signal_handler,
):
    event = EventFactory()

    def handler(signal, sender, **kwargs):
        return {"PluginFont": {"regular": {"woff2": "fonts/plugin.woff2"}}}

    register_signal_handler(register_fonts, handler)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)

    context = view.get_context_data()

    assert "font_preview_url" in context
    assert "font-preview.css" in context["font_preview_url"]


def test_event_detail_context_no_font_preview_url_without_fonts():
    event = EventFactory()
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)

    context = view.get_context_data()

    assert "font_preview_url" not in context


def test_font_preview_css_returns_empty_when_no_fonts():
    event = EventFactory()
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(FontPreviewCSS, request)

    response = view.get(request)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/css"
    assert response.content == b""


def test_font_preview_css_returns_font_face_rules(register_signal_handler):
    event = EventFactory()

    def handler(signal, sender, **kwargs):
        return {
            "PluginFont": {
                "regular": {"woff2": "fonts/plugin.woff2"},
                "bold": {"woff2": "fonts/plugin-bold.woff2"},
            }
        }

    register_signal_handler(register_fonts, handler)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(FontPreviewCSS, request)

    response = view.get(request)

    assert response.status_code == 200
    content = response.content.decode()
    assert "@font-face {" in content
    assert '"PluginFont"' in content
