from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import (
    ActionsColumn,
    ContextTemplateColumn,
    PretalxTable,
    SortableColumn,
)
from pretalx.mail.models import MailTemplate
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
