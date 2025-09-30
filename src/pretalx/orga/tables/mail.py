import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn, ContextTemplateColumn
from pretalx.mail.models import MailTemplate


class MailTemplateTable(tables.Table):
    role = ContextTemplateColumn(
        linkify=lambda record: record.urls.edit,
        template_name="orga/includes/mail_template_role.html",
        context_object_name="template",
        extra_context={"show_custom": True},
        verbose_name=_("Template"),
    )
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
    empty_text = _("Please add at least one place in which sessions can take place.")

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = MailTemplate
        fields = (
            "role",
            "subject",
            "actions",
        )
