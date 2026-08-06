# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models import BooleanField, Case, F, Value, When
from django.db.models.functions import Coalesce, Lower, NullIf
from django.utils.formats import date_format
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretalx.common.db import Translate
from pretalx.common.tables import (
    ActionsColumn,
    PretalxTable,
    QuestionColumnMixin,
    SortableBooleanColumn,
    SortableColumn,
    SortableTemplateColumn,
    TemplateColumn,
)
from pretalx.person.domain.queries.profile import (
    REACHABLE_SPEAKER_FILTER,
    speaker_name_expression,
)
from pretalx.person.models import SpeakerInformation, SpeakerProfile, User


class SpeakerInformationTable(PretalxTable):
    title = SortableColumn(
        linkify=lambda record: record.orga_urls.edit,
        verbose_name=_("Title"),
        order_by=Lower(Translate("title")),
    )
    resource = tables.Column(
        linkify=lambda record: record.resource.url if record.resource else None
    )
    actions = ActionsColumn(
        actions={
            "edit": {"url": "orga_urls.edit"},
            "delete": {"url": "orga_urls.delete"},
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exclude = list(self.exclude)
        if not self.event.has_active_tracks:
            self.exclude.append("limit_tracks")

    def render_resource(self, record):
        return mark_safe('<i class="fa fa-file-o"></i>')

    @property
    def default_columns(self):
        columns = ["title", "limit_types", "limit_tracks", "resource"]
        if not self.event or not self.event.has_active_tracks:
            columns.remove("limit_tracks")
        return columns

    class Meta:
        model = SpeakerInformation
        fields = ("title", "target_group", "limit_tracks", "limit_types", "resource")


class SpeakerTable(QuestionColumnMixin, PretalxTable):
    default_columns = (
        "name",
        "submission_count",
        "accepted_submission_count",
        "has_arrived",
    )

    name = SortableTemplateColumn(
        verbose_name=_("Name"),
        accessor="name",
        empty_values=[""],
        order_by={"name": Lower(speaker_name_expression())},
        template_name="orga/includes/speaker_name.html",
        template_context={
            "speaker": lambda record, table: record,
            "link_url": lambda record, table: record.orga_urls.base,
        },
    )
    code = tables.Column(verbose_name=_("ID"), accessor="code")
    email = SortableColumn(
        verbose_name=_("Email"),
        accessor="effective_email",
        order_by={"email": Coalesce(NullIf("email", Value("")), "user__email")},
        linkify=lambda record: record.orga_urls.send_mail,
    )
    submission_count = tables.Column(
        verbose_name=_("Proposals"),
        initial_sort_descending=True,
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    accepted_submission_count = tables.Column(
        verbose_name=_("Accepted Proposals"),
        initial_sort_descending=True,
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    locale = SortableColumn(
        verbose_name=_("Language"),
        accessor="effective_locale",
        order_by={
            "locale": Coalesce(
                NullIf("locale", Value("")), "user__locale", "event__locale"
            )
        },
    )
    has_arrived = TemplateColumn(
        verbose_name=_("Arrived"),
        template_name="orga/tables/columns/speaker_arrived.html",
    )
    invite_status = SortableColumn(
        verbose_name=_("Invite status"),
        accessor="invitation_sent",
        empty_values=(),
        order_by={
            "invite_status": Case(
                When(
                    user__isnull=True,
                    invitation_token__gt="",
                    then=F("invitation_sent"),
                )
            )
        },
    )
    speaker_type = SortableColumn(
        verbose_name=_("Speaker type"),
        accessor="is_managed",
        empty_values=(),
        order_by={
            "speaker_type": Case(
                When(user__isnull=True, then=Value(0)), default=Value(1)
            )
        },
    )
    has_email = SortableBooleanColumn(
        verbose_name=_("Can receive emails"),
        accessor="effective_email",
        empty_values=(),
        order_by={
            "has_email": Case(
                When(REACHABLE_SPEAKER_FILTER, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        },
    )
    actions = ActionsColumn(
        actions={
            # The delete permission only ever matches managed profiles
            # without submissions, so the button appears on exactly those rows.
            "delete": {
                "url": "orga_urls.delete",
                "permission": "person.delete_speakerprofile",
            }
        }
    )

    def __init__(
        self, *args, has_arrived_permission=False, short_questions=None, **kwargs
    ):
        self.short_questions = short_questions or []
        kwargs.setdefault("extra_columns", []).extend(self._get_question_columns())
        super().__init__(*args, **kwargs)
        self.has_arrived_permission = has_arrived_permission

    def render_invite_status(self, record, value):
        if not record.has_pending_invitation:
            return "—"
        if not value:
            return _("Invited")
        if self.event:
            value = value.astimezone(self.event.tz)
        return _("Invited {date}").format(date=date_format(value, "SHORT_DATE_FORMAT"))

    def render_speaker_type(self, record):
        if record.is_managed:
            return _("Managed")
        return _("Self-managed")

    class Meta:
        model = SpeakerProfile
        fields = (
            "name",
            "code",
            "email",
            "submission_count",
            "accepted_submission_count",
            "locale",
            "has_arrived",
        )


class SpeakerOrgaTable(SpeakerTable):
    name = SortableTemplateColumn(
        verbose_name=_("Name"),
        order_by=Lower("name"),
        template_name="orga/includes/user_name.html",
        context_object_name="user",
    )
    email = tables.Column(linkify=lambda record: f"mailto:{record.email}")

    # Set unavailable columns to `None` so that the configuration form
    # won’t show up
    locale = None
    code = None
    has_arrived = None
    invite_status = None
    speaker_type = None
    has_email = None
    actions = None
    default_columns = None

    class Meta:
        model = User
        fields = ("name", "email", "submission_count", "accepted_submission_count")
