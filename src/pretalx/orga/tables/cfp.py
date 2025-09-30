import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn
from pretalx.submission.models import SubmitterAccessCode


class SubmitterAccessCodeTable(tables.Table):
    code = tables.TemplateColumn(
        template_code="{% load copyable %}{{ record.code|copyable }}",
        verbose_name=_("Code"),
    )
    track = tables.Column(
        linkify=lambda record: record.track and record.track.urls.base,
        verbose_name=_("Track"),
        order_by="track__name",
    )
    submission_type = tables.Column(
        linkify=lambda record: record.submission_type
        and record.submission_type.urls.base,
        verbose_name=_("Session type"),
        order_by="submission_type__name",
    )
    uses = tables.TemplateColumn(
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        template_code="{{ record.redeemed|default:0 }} / {{ record.maximum_uses|default:'∞ '}}",
        order_by="redeemed",
    )
    actions = ActionsColumn(
        actions={
            "copy": {
                "extra_attrs": lambda record: f'role="button" data-destination="{record.urls.cfp_url.full()}"',
                "title": _("Copy access code link"),
            },
            "send": {
                "title": _("Send access code as email"),
            },
            "edit": {},
            "delete": {
                "condition": lambda record: not record.submissions.exists(),
            },
        }
    )
    empty_text = _("Please add at least one place in which sessions can take place.")

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not event.get_feature_flag("use_tracks"):
            self.columns["track"].hide()

    class Meta:
        model = SubmitterAccessCode
        fields = (
            "code",
            "track",
            "submission_type",
            "uses",
            "actions",
        )
