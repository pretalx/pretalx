import pytest
from django_scopes import scope, scopes_disabled

from pretalx.common.models.log import ActivityLog
from pretalx.orga.views.event import (
    EventDelete,
    EventDetail,
    EventHistory,
    EventHistoryDetail,
    EventLive,
    EventMailSettings,
    EventReviewSettings,
    InvitationView,
    PhaseActivate,
    WidgetSettings,
    condition_plugins,
)
from tests.factories import (
    EventFactory,
    QuestionFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TeamFactory,
    TeamInviteFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_event_detail_object_prefetches_extra_links(event, django_assert_num_queries):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)

    with scopes_disabled():
        obj = view.object

    assert obj.pk == event.pk
    with django_assert_num_queries(0):
        list(obj.extra_links.all())


@pytest.mark.django_db
def test_event_detail_get_object_returns_cached_object(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)

    with scopes_disabled():
        assert view.get_object() is view.object


@pytest.mark.django_db
@pytest.mark.parametrize("is_admin", (True, False))
def test_event_detail_get_form_kwargs_is_administrator(event, is_admin):
    user = make_orga_user(event)
    if is_admin:
        user.is_administrator = True
        user.save()
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)
    with scopes_disabled():
        view.object  # noqa: B018 -- force cached_property

    kwargs = view.get_form_kwargs()

    assert kwargs["is_administrator"] is is_admin


@pytest.mark.django_db
def test_event_detail_tablist(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)

    tabs = view.tablist()

    assert set(tabs.keys()) == {"general", "localisation", "display", "texts"}


@pytest.mark.django_db
def test_event_detail_get_success_url(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)
    with scopes_disabled():
        view.object  # noqa: B018

    assert view.get_success_url() == event.orga_urls.settings


@pytest.mark.django_db
@pytest.mark.parametrize("is_admin", (True, False))
def test_event_detail_context_delete_link_requires_admin(event, is_admin):
    user = make_orga_user(event)
    if is_admin:
        user.is_administrator = True
        user.save()
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)
    with scopes_disabled():
        view.object  # noqa: B018
        context = view.get_context_data()

    assert ("submit_buttons_extra" in context) is is_admin
    assert "submit_buttons" in context


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("formset_attr", "expected_prefix"),
    (
        ("header_links_formset", "header-links"),
        ("footer_links_formset", "footer-links"),
    ),
)
def test_event_detail_links_formset(event, formset_attr, expected_prefix):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)
    with scopes_disabled():
        view.object  # noqa: B018
        formset = getattr(view, formset_attr)

    assert formset.prefix == expected_prefix


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_public", "expected_value"), ((False, "activate"), (True, "deactivate"))
)
def test_event_live_context_submit_button_value(event, is_public, expected_value):
    event.is_public = is_public
    event.save()
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventLive, request)

    with scopes_disabled():
        context = view.get_context_data()

    buttons = context["submit_buttons"]
    assert len(buttons) == 1
    assert buttons[0].value == expected_value


@pytest.mark.django_db
def test_event_live_context_warnings_for_short_cfp_text(event):
    with scopes_disabled():
        event.cfp.text = "Short"
        event.cfp.save()
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventLive, request)

    with scopes_disabled():
        context = view.get_context_data()

    assert len(context["warnings"]) >= 1
    warning_texts = [w["text"] for w in context["warnings"]]
    assert any("CfP" in str(t) for t in warning_texts)


@pytest.mark.django_db
def test_event_live_context_warnings_for_short_landing_page(event):
    event.landing_page_text = "Short"
    event.save()
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventLive, request)

    with scopes_disabled():
        context = view.get_context_data()

    warning_texts = [str(w["text"]) for w in context["warnings"]]
    assert any("landing page" in t for t in warning_texts)


@pytest.mark.django_db
def test_event_live_context_suggestion_single_submission_type(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventLive, request)

    with scopes_disabled():
        assert event.submission_types.count() == 1
        context = view.get_context_data()

    suggestion_texts = [str(s["text"]) for s in context["suggestions"]]
    assert any("session type" in t for t in suggestion_texts)


@pytest.mark.django_db
def test_event_live_context_suggestion_no_questions(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventLive, request)

    with scopes_disabled():
        context = view.get_context_data()

    suggestion_texts = [str(s["text"]) for s in context["suggestions"]]
    assert any("custom field" in t for t in suggestion_texts)


@pytest.mark.django_db
def test_event_history_get_queryset(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        user = UserFactory()
        ActivityLog.objects.create(
            event=event,
            person=user,
            content_object=submission,
            action_type="pretalx.submission.create",
        )
    request = make_request(event, user=user)
    view = make_view(EventHistory, request)

    with scopes_disabled():
        qs = view.get_queryset()

    assert qs.count() == 1
    assert qs.first().event == event


@pytest.mark.django_db
def test_event_history_get_queryset_excludes_other_events(event):
    with scopes_disabled():
        other_event = EventFactory()
        user = UserFactory()
        ActivityLog.objects.create(
            event=other_event,
            person=user,
            content_object=other_event,
            action_type="pretalx.event.update",
        )
    request = make_request(event, user=user)
    view = make_view(EventHistory, request)

    with scopes_disabled():
        qs = view.get_queryset()

    assert qs.count() == 0


@pytest.mark.django_db
def test_event_history_detail_get_queryset_scoped_to_event(event):
    with scopes_disabled():
        user = UserFactory()
        log = ActivityLog.objects.create(
            event=event,
            person=user,
            content_object=event,
            action_type="pretalx.event.update",
        )
    request = make_request(event, user=user)
    view = make_view(EventHistoryDetail, request, pk=log.pk)

    with scopes_disabled():
        qs = view.get_queryset()

    assert list(qs) == [log]


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_event_history_detail_context_includes_htmx_flag(event):
    with scopes_disabled():
        user = UserFactory()
        log = ActivityLog.objects.create(
            event=event,
            person=user,
            content_object=event,
            action_type="pretalx.event.update",
        )
    request = make_request(event, user=user)
    view = make_view(EventHistoryDetail, request, pk=log.pk)
    view.object = log

    with scopes_disabled():
        context = view.get_context_data()

    assert context["is_htmx_request"] is False


@pytest.mark.django_db
def test_event_review_settings_tablist(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventReviewSettings, request)

    tabs = view.tablist()

    assert set(tabs.keys()) == {"general", "scores", "phases"}


@pytest.mark.django_db
def test_event_review_settings_get_success_url(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventReviewSettings, request)

    assert view.get_success_url() == event.orga_urls.review_settings


@pytest.mark.django_db
def test_event_review_settings_get_form_kwargs(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventReviewSettings, request)

    kwargs = view.get_form_kwargs()

    assert kwargs["obj"] == event
    assert kwargs["attribute_name"] == "settings"
    assert kwargs["locales"] == event.locales


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("formset_attr", "expected_prefix"),
    (("phases_formset", "phase"), ("scores_formset", "scores")),
)
def test_event_review_settings_formset(event, formset_attr, expected_prefix):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventReviewSettings, request)

    with scopes_disabled():
        formset = getattr(view, formset_attr)

    assert formset.prefix == expected_prefix


@pytest.mark.django_db
def test_phase_activate_get_object(event):
    with scope(event=event):
        phase = event.active_review_phase
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(PhaseActivate, request, pk=phase.pk)

    with scopes_disabled():
        obj = view.get_object()

    assert obj == phase


@pytest.mark.django_db
def test_event_mail_settings_get_success_url(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventMailSettings, request)

    assert view.get_success_url() == event.orga_urls.mail_settings


@pytest.mark.django_db
def test_event_mail_settings_get_form_kwargs(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventMailSettings, request)

    kwargs = view.get_form_kwargs()

    assert kwargs["obj"] == event
    assert kwargs["locales"] == event.locales


@pytest.mark.django_db
def test_event_mail_settings_submit_buttons(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventMailSettings, request)

    buttons = view.submit_buttons()

    assert len(buttons) == 2
    assert buttons[0].name == "test"


@pytest.mark.django_db
def test_invitation_view_invitation_property(event):
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email="test@example.com")
    request = make_request(event)
    view = make_view(InvitationView, request, code=invite.token)

    with scopes_disabled():
        result = view.invitation

    assert result == invite


@pytest.mark.django_db
def test_invitation_view_get_form_kwargs(event):
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team)
    request = make_request(event)
    view = make_view(InvitationView, request, code=invite.token)

    kwargs = view.get_form_kwargs()

    assert kwargs["request"] == request
    assert "password_reset_link" in kwargs


@pytest.mark.django_db
def test_event_delete_get_object(event):
    user = UserFactory(is_administrator=True)
    request = make_request(event, user=user)
    view = make_view(EventDelete, request)

    assert view.get_object() == event


@pytest.mark.django_db
def test_event_delete_action_object_name(event):
    user = UserFactory(is_administrator=True)
    request = make_request(event, user=user)
    view = make_view(EventDelete, request)

    name = view.action_object_name()

    assert str(event.name) in name


@pytest.mark.django_db
def test_event_delete_action_back_url(event):
    user = UserFactory(is_administrator=True)
    request = make_request(event, user=user)
    view = make_view(EventDelete, request)

    assert view.action_back_url == event.orga_urls.settings


@pytest.mark.django_db
def test_widget_settings_get_success_url(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(WidgetSettings, request)

    assert view.get_success_url() == event.orga_urls.widget_settings


@pytest.mark.django_db
def test_widget_settings_get_form_kwargs(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(WidgetSettings, request)

    kwargs = view.get_form_kwargs()

    assert kwargs["obj"] == event


@pytest.mark.django_db
def test_widget_settings_context_includes_extra_form(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(WidgetSettings, request)
    view.object = event

    with scopes_disabled():
        context = view.get_context_data()

    assert "extra_form" in context
    assert "generate_submit" in context


@pytest.mark.django_db
def test_condition_plugins_returns_bool():
    result = condition_plugins(None)
    assert isinstance(result, bool)


@pytest.mark.django_db
def test_event_settings_permission_object(event):
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventDetail, request)

    assert view.permission_object == event


@pytest.mark.django_db
def test_event_live_context_no_warning_when_cfp_text_sufficient(event):
    """When cfp.text is >= 50 chars, no CfP warning is shown."""
    with scopes_disabled():
        event.cfp.text = "A" * 60
        event.cfp.save()
    event.landing_page_text = "B" * 60
    event.save()
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventLive, request)

    with scopes_disabled():
        context = view.get_context_data()

    warning_texts = [str(w["text"]) for w in context["warnings"]]
    assert not any("CfP" in t for t in warning_texts)
    assert not any("landing page" in t for t in warning_texts)


@pytest.mark.django_db
def test_event_live_context_suggestion_tracks_use_tracks_enabled(event):
    """When use_tracks and request_track are enabled but fewer than 2 tracks exist,
    a suggestion to add tracks is shown."""
    with scopes_disabled():
        event.feature_flags["use_tracks"] = True
        event.save()
        event.cfp.fields["track"]["visibility"] = "optional"
        event.cfp.save()
        TrackFactory(event=event)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventLive, request)

    with scopes_disabled():
        context = view.get_context_data()

    suggestion_texts = [str(s["text"]) for s in context["suggestions"]]
    assert any("track" in t.lower() for t in suggestion_texts)


@pytest.mark.django_db
def test_event_live_context_no_suggestion_multiple_submission_types(event):
    """When more than one submission type exists, no 'only one session type' suggestion."""
    with scopes_disabled():
        SubmissionTypeFactory(event=event)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventLive, request)

    with scopes_disabled():
        assert event.submission_types.count() > 1
        context = view.get_context_data()

    suggestion_texts = [str(s["text"]) for s in context["suggestions"]]
    assert not any("session type" in t for t in suggestion_texts)


@pytest.mark.django_db
def test_event_live_context_no_suggestion_when_questions_exist(event):
    """When custom questions exist, no 'no custom fields' suggestion."""
    with scopes_disabled():
        QuestionFactory(event=event)
    user = make_orga_user(event)
    request = make_request(event, user=user)
    view = make_view(EventLive, request)

    with scopes_disabled():
        context = view.get_context_data()

    suggestion_texts = [str(s["text"]) for s in context["suggestions"]]
    assert not any("custom field" in t for t in suggestion_texts)
