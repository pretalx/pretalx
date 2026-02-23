# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from pretalx.common.language import LANGUAGE_NAMES
from pretalx.common.tables import (
    ActionsColumn,
    DateTimeColumn,
    PretalxTable,
    SortableColumn,
    SortableTemplateColumn,
    TemplateColumn,
)
from pretalx.mail.models import MailTemplate, QueuedMail
from pretalx.orga.utils.i18n import Translate


class MailTemplateTable(PretalxTable):
    default_columns = ("role", "subject")

    role = TemplateColumn(
        linkify=lambda record: record.urls.edit,
        template_name="orga/includes/mail_template_role.html",
        context_object_name="template",
        extra_context={"show_custom": True},
        verbose_name=_("Template"),
    )
    subject = SortableColumn(order_by=Lower(Translate("subject")))
    actions = ActionsColumn(
        actions={
            "send": {
                "label": _("Send mails"),
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

    class Meta:
        model = MailTemplate
        fields = ("role", "subject", "reply_to", "bcc", "actions")


class OutboxMailTable(PretalxTable):
    exempt_columns = ("pk", "actions", "status_display")
    default_columns = ("subject", "to_recipients", "submissions", "template_info")

    status_display = SortableTemplateColumn(
        template_name="orga/tables/columns/queued_mail_status.html",
        verbose_name=_("Status"),
        order_by=("computed_state",),
    )
    subject = SortableColumn(
        linkify=lambda record: record.urls.edit, verbose_name=_("Subject")
    )
    to_recipients = SortableTemplateColumn(
        template_name="orga/tables/columns/queued_mail_recipients.html",
        verbose_name=_("To"),
        order_by=Lower("to_users__name"),
    )
    submissions = TemplateColumn(
        template_name="orga/tables/columns/queued_mail_submissions.html",
        verbose_name=_("Proposals"),
        orderable=False,
    )
    template_info = TemplateColumn(
        template_name="orga/tables/columns/queued_mail_template_info.html",
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
        self.sequence.remove("status_display")
        self.sequence.insert(0, "status_display")

    def render_locale(self, value):
        if not value:
            return ""
        return LANGUAGE_NAMES.get(value, value)

    class Meta:
        model = QueuedMail
        fields = (
            "status_display",
            "subject",
            "to_recipients",
            "reply_to",
            "cc",
            "bcc",
            "submissions",
            "template_info",
            "locale",
            "actions",
        )


class SentMailTable(OutboxMailTable):
    default_columns = (
        "sent",
        "subject",
        "to_recipients",
        "submissions",
        "template_info",
    )

    status_display = SortableTemplateColumn(
        template_name="orga/tables/columns/sent_mail_status.html",
        verbose_name=_("Status"),
        order_by=("computed_state",),
    )
    sent = DateTimeColumn()
    actions = None

    class Meta(OutboxMailTable.Meta):
        fields = (
            "sent",
            "status_display",
            "subject",
            "to_recipients",
            "reply_to",
            "cc",
            "bcc",
            "submissions",
            "template_info",
            "locale",
        )
