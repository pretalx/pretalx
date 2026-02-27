# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.models import MailTemplateRoles, QueuedMailStates
from pretalx.mail.signals import request_pre_send
from pretalx.orga.views.mails import (
    ComposeDraftReminders,
    ComposeMailChoice,
    ComposeSessionMail,
    ComposeTeamsMail,
    MailCopy,
    MailDelete,
    MailDetail,
    MailPreview,
    MailSendingStatus,
    MailSidebarCount,
    MailTemplateView,
    OutboxList,
    OutboxPurge,
    OutboxSend,
    SentMail,
    get_send_mail_exceptions,
)
from tests.factories import (
    MailTemplateFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SubmissionFactory,
)
from tests.utils import make_orga_user, make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_get_send_mail_exceptions_returns_none_without_handlers(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)

    result = get_send_mail_exceptions(request)

    assert result is None


@pytest.mark.django_db
def test_get_send_mail_exceptions_returns_errors(event, register_signal_handler):
    def raise_exception(signal, sender, **kwargs):
        raise SendMailException("Blocked!")

    register_signal_handler(request_pre_send, raise_exception)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)

    result = get_send_mail_exceptions(request)

    assert result == ["Blocked!"]


@pytest.mark.parametrize(
    ("view_class", "expected"),
    (
        (OutboxList, "mail.list_queuedmail"),
        (SentMail, "mail.list_queuedmail"),
        (OutboxSend, "mail.send_queuedmail"),
        (MailDelete, "mail.delete_queuedmail"),
        (OutboxPurge, "mail.delete_queuedmail"),
        (MailCopy, "mail.send_queuedmail"),
        (MailPreview, "mail.send_queuedmail"),
        (ComposeMailChoice, "mail.send_queuedmail"),
        (ComposeSessionMail, "mail.send_queuedmail"),
        (ComposeTeamsMail, "event.update_team"),
        (ComposeDraftReminders, "mail.send_queuedmail"),
        (MailSendingStatus, "mail.list_queuedmail"),
        (MailSidebarCount, "mail.list_queuedmail"),
    ),
)
def test_view_permission_required(view_class, expected):
    assert view_class.permission_required == expected


def test_mail_detail_view_permissions():
    assert MailDetail.permission_required == "mail.view_queuedmail"
    assert MailDetail.write_permission_required == "mail.update_queuedmail"


@pytest.mark.django_db
def test_outbox_list_get_queryset_returns_drafts(event):
    with scopes_disabled():
        draft = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
        QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(OutboxList, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [draft]


@pytest.mark.django_db
@pytest.mark.parametrize("view_class", (OutboxList, SentMail))
@pytest.mark.parametrize("flag_value", (True, False))
def test_show_tracks_reflects_feature_flag(event, view_class, flag_value):
    event.feature_flags["use_tracks"] = flag_value
    event.save()
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(view_class, request)

    assert view.show_tracks is flag_value


@pytest.mark.django_db
def test_outbox_list_get_table_kwargs_with_send_permission(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(OutboxList, request)
    view.object_list = []

    kwargs = view.get_table_kwargs()

    assert kwargs["has_update_permission"] is True
    assert kwargs["has_delete_permission"] is True


@pytest.mark.django_db
def test_sent_mail_get_queryset_returns_sent(event):
    with scopes_disabled():
        QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
        sent = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(SentMail, request)

    with scopes_disabled():
        result = list(view.get_queryset())

    assert result == [sent]


@pytest.mark.django_db
def test_outbox_send_action_back_url(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(OutboxSend, request)

    assert view.action_back_url == event.orga_urls.outbox


@pytest.mark.django_db
def test_outbox_send_queryset_filters_by_pks(event):
    with scopes_disabled():
        mail1 = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
        QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, path=f"/?pks={mail1.pk}")
    request.GET = {"pks": str(mail1.pk)}
    view = make_view(OutboxSend, request)

    with scopes_disabled():
        result = list(view.queryset)

    assert result == [mail1]


@pytest.mark.django_db
def test_outbox_send_queryset_filters_failed_only(event):
    with scopes_disabled():
        failed = QueuedMailFactory(
            event=event, state=QueuedMailStates.DRAFT, error_data={"error": "fail"}
        )
        QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = {"failed_only": "1"}
    view = make_view(OutboxSend, request)

    with scopes_disabled():
        result = list(view.queryset)

    assert result == [failed]


@pytest.mark.django_db
def test_mail_delete_queryset_single(event):
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(MailDelete, request, pk=mail.pk)

    with scopes_disabled():
        result = list(view.queryset)

    assert result == [mail]


@pytest.mark.django_db
def test_mail_delete_queryset_all_by_template(event):
    """When ?all is set, all drafts from the same template are returned."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event)
        mail1 = QueuedMailFactory(
            event=event, state=QueuedMailStates.DRAFT, template=template
        )
        mail2 = QueuedMailFactory(
            event=event, state=QueuedMailStates.DRAFT, template=template
        )
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = {"all": "true"}
    view = make_view(MailDelete, request, pk=mail1.pk)

    with scopes_disabled():
        result = set(view.queryset)

    assert result == {mail1, mail2}


@pytest.mark.django_db
def test_mail_delete_action_back_url(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = {}
    view = make_view(MailDelete, request, pk=1)

    assert view.action_back_url == event.orga_urls.outbox


@pytest.mark.django_db
def test_outbox_purge_action_back_url(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(OutboxPurge, request)

    assert view.action_back_url == event.orga_urls.outbox


@pytest.mark.django_db
def test_mail_detail_get_object(event):
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailDetail, request, pk=mail.pk)

    with scopes_disabled():
        result = view.get_object()

    assert result == mail


@pytest.mark.django_db
def test_mail_detail_get_object_returns_none_for_missing(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailDetail, request, pk=99999)

    with scopes_disabled():
        result = view.get_object()

    assert result is None


@pytest.mark.django_db
def test_mail_detail_get_success_url(event):
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailDetail, request, pk=mail.pk)
    view.object = mail

    assert view.get_success_url() == event.orga_urls.outbox


@pytest.mark.django_db
def test_mail_detail_get_context_data_draft_view_only_has_no_buttons(event):
    """When a user has view-only permission on a DRAFT mail, get_context_data
    adds no extra buttons.  This branch is unreachable with current permissions
    (DRAFT mails always grant edit) but the view handles it defensively."""
    with scopes_disabled():
        mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailDetail, request, pk=mail.pk)
    view.object = mail
    # Force view-only permission to exercise the defensive branch
    view.__dict__["permission_action"] = "view"

    with scopes_disabled():
        ctx = view.get_context_data()

    assert "submit_buttons" not in ctx
    assert "submit_buttons_extra" not in ctx


@pytest.mark.django_db
def test_compose_session_mail_get_form_kwargs_with_submissions(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = {"submissions": submission.code}
    view = make_view(ComposeSessionMail, request)

    with scopes_disabled():
        kwargs = view.get_form_kwargs()

    assert kwargs["initial"]["submissions"] == [submission.code]


@pytest.mark.django_db
def test_compose_session_mail_get_form_kwargs_with_speakers(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    request.GET = {"speakers": speaker.code}
    view = make_view(ComposeSessionMail, request)

    with scopes_disabled():
        kwargs = view.get_form_kwargs()

    assert list(kwargs["initial"]["speakers"]) == [speaker]


@pytest.mark.django_db
def test_compose_draft_reminders_draft_reminder_template(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(ComposeDraftReminders, request)

    with scopes_disabled():
        template = view.draft_reminder_template
        expected = event.get_mail_template(MailTemplateRoles.DRAFT_REMINDER)

    assert template == expected


@pytest.mark.django_db
def test_mail_template_view_get_queryset_excludes_auto_created(event):
    with scopes_disabled():
        custom = MailTemplateFactory(event=event)
        auto_created = MailTemplateFactory(event=event, is_auto_created=True)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailTemplateView, request)
    view.action = "list"

    with scopes_disabled():
        result = list(view.get_queryset())

    assert custom in result
    assert auto_created not in result


@pytest.mark.django_db
def test_mail_template_view_get_generic_title_custom_template(event):
    with scopes_disabled():
        template = MailTemplateFactory(event=event, subject="My Subject")
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailTemplateView, request)

    assert (
        str(view.get_generic_title(instance=template)) == "Email template: My Subject"
    )


@pytest.mark.django_db
def test_mail_template_view_get_generic_title_role_template(event):
    with scopes_disabled():
        template = event.get_mail_template(MailTemplateRoles.NEW_SUBMISSION)
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailTemplateView, request)

    assert (
        str(view.get_generic_title(instance=template))
        == f"Email template: {template.get_role_display()}"
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected_text"),
    (("create", "New email template"), ("list", "Email templates")),
)
def test_mail_template_view_get_generic_title_without_instance(
    event, action, expected_text
):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user)
    view = make_view(MailTemplateView, request)
    view.action = action

    title = view.get_generic_title()

    assert str(title) == expected_text
