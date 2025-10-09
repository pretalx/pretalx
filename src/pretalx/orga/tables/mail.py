import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import (
    ActionsColumn,
    ContextTemplateColumn,
    PretalxTable,
    SortableColumn,
    SortableTemplateColumn,
)
from pretalx.mail.models import MailTemplate, QueuedMail
from pretalx.orga.utils.i18n import Translate


class MailTemplateTable(PretalxTable):
    role = ContextTemplateColumn(
        linkify=lambda record: record.urls.edit,
        template_name="orga/includes/mail_template_role.html",
        context_object_name="template",
        extra_context={"show_custom": True},
        verbose_name=_("Template"),
    )
    subject = SortableColumn(order_by=Lower(Translate(("subject"))))
    actions = ActionsColumn(
        actions={
            "send": {
                "label": _("Send mails"),
                "condition": lambda record: not record.role,
                "color": "primary",
                "icon": None,
                "url": lambda record: f"{record.event.orga_urls.compose_mails_sessions}?template={record.pk}",
            },
            "delete": {
                "condition": lambda record: not record.role,
            },
            "edit": {},
        }
    )

    class Meta:
        model = MailTemplate
        fields = (
            "role",
            "subject",
            "actions",
        )


class OutboxMailTable(PretalxTable):
    subject = SortableColumn(
        linkify=lambda record: record.urls.edit,
        verbose_name=_("Subject"),
    )
    to_recipients = SortableTemplateColumn(
        template_name="orga/tables/columns/queued_mail_recipients.html",
        verbose_name=_("To"),
        order_by=Lower("to_users__name"),
    )
    submissions = tables.TemplateColumn(
        template_name="orga/tables/columns/queued_mail_submissions.html",
        verbose_name="",
        orderable=False,
    )
    template_info = tables.TemplateColumn(
        template_name="orga/tables/columns/queued_mail_template_info.html",
        verbose_name="",
        order_by=("template__role",),
    )
    actions = ActionsColumn(
        verbose_name="",
        actions={
            "send": {
                "url": "urls.send",
                "color": "success",
                "icon": "mail-forward",
            },
            "edit": {
                "url": "urls.edit",
            },
            "delete": {
                "url": "urls.delete",
            },
        },
    )

    class Meta:
        model = QueuedMail
        fields = (
            "subject",
            "to_recipients",
            "submissions",
            "template_info",
            "actions",
        )


class SentMailTable(OutboxMailTable):
    sent = tables.DateTimeColumn(
        verbose_name=_("Sent"),
        format="SHORT_DATETIME_FORMAT",
    )
    actions = None

    class Meta(OutboxMailTable.Meta):
        fields = (
            "sent",
            "subject",
            "to_recipients",
            "submissions",
            "template_info",
        )
