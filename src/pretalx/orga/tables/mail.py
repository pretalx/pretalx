# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.db import Translate
from pretalx.common.language import LANGUAGE_NAMES
from pretalx.common.tables import (
    ActionsColumn,
    DateTimeColumn,
    PretalxTable,
    SortableColumn,
    SortableTemplateColumn,
    TemplateColumn,
)
from pretalx.mail.domain.queries import outbox_mails, sent_mails
from pretalx.mail.interfaces.filters import queued_mail_filters
from pretalx.mail.models import MailTemplate, QueuedMail


class MailTemplateTable(PretalxTable):
    primary_column = "subject"
    default_columns = ("role", "subject")
    filter_options = {}

    role = TemplateColumn(
        linkify=lambda record: record.urls.edit,
        template_name="orga/includes/mail_template_role.html",
        context_object_name="template",
        verbose_name=_("Template"),
    )
    subject = SortableColumn(order_by=Lower(Translate("subject")))
    actions = ActionsColumn(
        actions={
            "send": {
                "label": _("Send emails"),
                "condition": lambda record: not record.role,
                "color": "primary",
                "icon": None,
                "url": lambda record: (
                    f"{record.event.orga_urls.compose_mails_sessions}?template={record.pk}"
                ),
            },
            "delete": {"condition": lambda record: not record.role},
            "edit": {},
        }
    )

    @classmethod
    def base_queryset(cls, event, user):
        return event.mail_templates.exclude(is_auto_created=True).order_by("role", "pk")

    class Meta:
        model = MailTemplate
        fields = ("role", "subject", "reply_to", "bcc", "actions")


class OutboxMailTable(PretalxTable):
    filters = staticmethod(queued_mail_filters)
    filter_options = {"sent": False}
    update_permission = "send"
    delete_permission = "send"
    primary_column = "subject"
    exempt_columns = ("pk", "actions", "state")
    default_columns = ("subject", "to_recipients", "submissions", "template_role")

    @classmethod
    def base_queryset(cls, event, user):
        return outbox_mails(event)

    state = SortableTemplateColumn(
        template_name="orga/tables/columns/queued_mail_status.html",
        verbose_name=pgettext_lazy("email delivery status", "Status"),
        order_by=("computed_state",),
    )
    subject = SortableColumn(
        linkify=lambda record: record.urls.edit,
        verbose_name=pgettext_lazy("email subject", "Subject"),
    )
    to_recipients = SortableTemplateColumn(
        template_name="orga/tables/columns/queued_mail_recipients.html",
        verbose_name=_("To"),
        order_by=(Lower("to_speakers__name"),),
    )
    submissions = TemplateColumn(
        template_name="orga/tables/columns/queued_mail_submissions.html",
        verbose_name=_("Proposals"),
        orderable=False,
    )
    template_role = TemplateColumn(
        template_name="orga/tables/columns/queued_mail_template_role.html",
        verbose_name=_("Template"),
        order_by=("template__role",),
    )
    locale = tables.Column(verbose_name=_("Language"))
    actions = ActionsColumn(
        verbose_name="",
        actions={
            "send": {
                "url": "urls.send",
                "color": "success",
                "icon": "mail-forward",
                "condition": lambda record: not record.has_error,
                "extra_attrs": lambda record: (
                    f'hx-post="{record.urls.send}" hx-target="closest tr" hx-swap="delete"'
                ),
            },
            "retry": {
                "url": "urls.send",
                "color": "danger",
                "icon": "refresh",
                "title": _("Retry"),
                "condition": lambda record: record.has_error,
                "extra_attrs": lambda record: (
                    f'hx-post="{record.urls.send}" hx-target="closest tr" hx-swap="delete"'
                ),
            },
            "edit": {"url": "urls.edit"},
            "delete": {"url": "urls.delete"},
        },
    )

    def _set_columns(self, selected_columns):
        super()._set_columns(selected_columns)
        self.sequence.remove("state")
        self.sequence.insert(0, "state")

    def render_locale(self, value):
        if not value:
            return ""
        return LANGUAGE_NAMES.get(value, value)

    class Meta:
        model = QueuedMail
        fields = (
            "state",
            "subject",
            "to_recipients",
            "reply_to",
            "cc",
            "bcc",
            "submissions",
            "template_role",
            "locale",
            "actions",
        )


class SentMailTable(OutboxMailTable):
    filter_options = {"sent": True}
    default_columns = (
        "sent",
        "subject",
        "to_recipients",
        "submissions",
        "template_role",
    )

    @classmethod
    def base_queryset(cls, event, user):
        return sent_mails(event)

    state = SortableTemplateColumn(
        template_name="orga/tables/columns/sent_mail_status.html",
        verbose_name=pgettext_lazy("email delivery status", "Status"),
        order_by=("computed_state",),
    )
    sent = DateTimeColumn()
    actions = None

    class Meta(OutboxMailTable.Meta):
        fields = (
            "sent",
            "state",
            "subject",
            "to_recipients",
            "reply_to",
            "cc",
            "bcc",
            "submissions",
            "template_role",
            "locale",
        )
