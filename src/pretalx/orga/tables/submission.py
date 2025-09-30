import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn, ContextTemplateColumn
from pretalx.submission.models import Submission


class SubmissionTable(tables.Table):
    indicator = tables.TemplateColumn(
        template_name="orga/submission/table/submission_side_indicator.html",
        order_by="track__name",
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
    submission_type = tables.Column(
        verbose_name=_("Type"),
        linkify=lambda record: record.submission_type.urls.base,
        accessor="submission_type.name",
        order_by=("submission_type__name"),
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
        event,
        can_view_speakers=False,
        can_change_submission=False,
        show_tracks=False,
        show_submission_types=False,
        limit_tracks=None,
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
        if not can_change_submission:
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
