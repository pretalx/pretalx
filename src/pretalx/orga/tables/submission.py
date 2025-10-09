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
from pretalx.orga.utils.i18n import Translate
from pretalx.submission.models import Submission, Tag


class SubmissionTable(PretalxTable):
    indicator = SortableTemplateColumn(
        template_name="orga/submission/table/submission_side_indicator.html",
        order_by=Lower(Translate("track__name")),
        verbose_name="",
        exclude_from_export=True,
    )
    title = tables.Column(
        linkify=lambda record: record.orga_urls.base,
        verbose_name=_("Title"),
    )
    speakers = tables.TemplateColumn(
        template_name="orga/submission/table/submission_speakers.html",
        verbose_name=_("Speakers"),
        order_by=("speakers__name"),
    )
    submission_type = SortableColumn(
        verbose_name=_("Type"),
        linkify=lambda record: record.submission_type.urls.base,
        accessor="submission_type.name",
        order_by=Lower(Translate("submission_type__name")),
    )
    state = ContextTemplateColumn(
        template_name="orga/submission/state_dropdown.html",
        verbose_name=_("State"),
        context_object_name="submission",
    )
    is_featured = ContextTemplateColumn(
        template_name="orga/submission/table/submission_is_featured.html",
        verbose_name=_("Featured"),
    )
    actions = ActionsColumn(
        actions={
            "edit": {"url": "orga_urls.edit"},
            "delete": {"url": "orga_urls.delete"},
        }
    )

    def __init__(
        self,
        *args,
        can_view_speakers=False,
        show_tracks=False,
        show_submission_types=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.exclude = list(self.exclude)  # Make sure we can add fields
        if not show_submission_types:
            self.exclude += ["submission_type"]
        if not can_view_speakers:
            self.exclude += ["speakers"]
        if not show_tracks:
            self.exclude += ["track"]
        if not kwargs.get("has_update_permission"):
            self.exclude += ["is_featured", "actions"]

        # These values are only for exports
        # self.columns.hide("code")
        # self.columns.hide("track")
        # self.columns.hide("is_anonymised")

    class Meta:
        model = Submission
        fields = (
            # "code",
            # "is_anonymised",
        )


class TagTable(PretalxTable):
    tag = tables.Column(
        linkify=lambda record: record.urls.edit,
        verbose_name=_("Tag"),
    )
    color = tables.TemplateColumn(
        verbose_name=_("Colour"),
        template_code='<div class="color-square" style="background: {{ record.color }}"></div>',
    )
    proposals = tables.Column(
        verbose_name=_("Proposals"),
        accessor="submission_count",
    )
    actions = ActionsColumn(actions={"edit": {}, "delete": {}})

    class Meta:
        model = Tag
        fields = (
            "tag",
            "color",
            "proposals",
            "actions",
        )
