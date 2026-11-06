# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models import (
    BooleanField,
    Case,
    F,
    Prefetch,
    Value,
    When,
    prefetch_related_objects,
)
from django.db.models.functions import Coalesce, Lower, NullIf
from django.utils.formats import date_format
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretalx.common.db import Translate
from pretalx.common.tables import (
    ActionsColumn,
    Column,
    PretalxTable,
    QuestionColumnMixin,
    SortableBooleanColumn,
    SortableColumn,
    SortableTemplateColumn,
    TemplateColumn,
)
from pretalx.common.text.phrases import phrases
from pretalx.person.domain.queries.profile import (
    REACHABLE_SPEAKER_FILTER,
    annotate_speaker_submission_counts,
)
from pretalx.person.interfaces.filters import speaker_list_filters, user_speaker_filters
from pretalx.person.models import SpeakerInformation, SpeakerProfile, User
from pretalx.submission.domain.queries.speaker import speakers_for_user
from pretalx.submission.domain.queries.submission import submissions_for_user
from pretalx.submission.enums import QuestionTarget


class SpeakerInformationTable(PretalxTable):
    primary_column = "title"
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
    primary_column = "name"
    filters = staticmethod(speaker_list_filters)
    question_target = QuestionTarget.SPEAKER
    # Only offered to users who may edit speakers; reviewers never see them.
    sensitive_columns = ("email", "has_email", "submission_ids", "submission_titles")
    export_name = phrases.schedule.speakers
    export_permission = "person.orga_list_speakerprofile"

    default_columns = ("name", "submissions", "has_arrived")

    @classmethod
    def base_queryset(cls, event, user):
        # Reviewers do not need speakers without submissions
        include_bare = user.has_perm("submission.orga_update_submission", event)
        submissions = submissions_for_user(event, user)
        return annotate_speaker_submission_counts(
            speakers_for_user(
                event, user, submissions=submissions, include_bare=include_bare
            ),
            event=event,
            submissions=submissions,
        )

    name = SortableTemplateColumn(
        verbose_name=_("Name"),
        accessor="name",
        empty_values=[""],
        order_by={"name": Lower("effective_name")},
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
        order_by={"email": F("effective_email")},
        linkify=lambda record: record.orga_urls.send_mail,
    )
    submission_count = tables.Column(
        verbose_name=_("Proposal count"),
        initial_sort_descending=True,
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    accepted_submission_count = tables.Column(
        verbose_name=_("Accepted proposal count"),
        initial_sort_descending=True,
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    submissions = TemplateColumn(
        verbose_name=_("Proposals"),
        template_name="orga/tables/columns/speaker_submissions.html",
        template_context={
            "submissions": lambda record, table: table.get_visible_submissions(record)
        },
        orderable=False,
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
        exclude_from_export=True,
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
    biography = Column(export_only=True)
    avatar = Column(
        verbose_name=_("Picture"),
        accessor="get_avatar_url",
        orderable=False,
        export_only=True,
    )
    submission_ids = Column(
        verbose_name=_("Proposal IDs"),
        orderable=False,
        export_only=True,
        empty_values=(),
    )
    submission_titles = Column(
        verbose_name=_("Proposal titles"),
        orderable=False,
        export_only=True,
        empty_values=(),
    )
    actions = ActionsColumn(
        actions={
            "edit": {"url": "orga_urls.base"},
            "email": {
                "title": phrases.orga.send_email,
                "icon": "envelope",
                "url": "orga_urls.send_mail",
                "permission": "mail.send_queuedmail",
                "condition": lambda record: bool(record.effective_email),
                "as_button": False,
            },
            # The delete permission only ever matches managed profiles
            # without submissions, so the button appears on exactly those rows.
            "delete": {
                "url": "orga_urls.delete",
                "permission": "person.delete_speakerprofile",
            },
        }
    )

    def __init__(self, *args, has_arrived_permission=None, **kwargs):
        super().__init__(*args, **kwargs)
        if has_arrived_permission is None:
            has_arrived_permission = self.has_event_permission("mark_arrived")
        self.has_arrived_permission = has_arrived_permission
        self.exclude = list(self.exclude)
        if not self.has_update_permission:
            self.exclude += list(self.sensitive_columns)

    @classmethod
    def get_filter_options(cls, event, user):
        options = super().get_filter_options(event, user)
        options["filter_arrival"] = bool(
            event and event.submitters.filter(has_arrived=True).exists()
        )
        return options

    def value_name(self, record):
        return record.get_display_name()

    def value_has_arrived(self, record):
        if not record.accepted_submission_count:
            return None
        return record.has_arrived

    def column_prefetches(self, columns):
        if columns & {"submission_ids", "submission_titles"}:
            return ["submissions"]
        return []

    def value_submissions(self, record):
        return [submission.title for submission in self.get_visible_submissions(record)]

    def value_submission_ids(self, record):
        return [submission.code for submission in record.submissions.all()]

    def value_submission_titles(self, record):
        return [submission.title for submission in record.submissions.all()]

    def render_invite_status(self, record, value):
        if not record.has_pending_invitation:
            return "—"
        if not value:
            return _("Invited")
        if self.event:
            value = value.astimezone(self.event.tz)
        return _("Invited {date}").format(date=date_format(value, "SHORT_DATE_FORMAT"))

    def value_invite_status(self, record, value):
        if not record.has_pending_invitation:
            return None
        return value

    def render_speaker_type(self, record):
        if record.is_managed:
            return _("Managed")
        return _("Self-managed")

    def get_visible_submissions(self, record):
        if not hasattr(record, "visible_submissions"):
            prefetch_related_objects(
                [row.record for row in self.paginated_rows],
                Prefetch(
                    "submissions",
                    queryset=submissions_for_user(self.event, self.user).order_by(
                        "title"
                    ),
                    to_attr="visible_submissions",
                ),
            )
        return record.visible_submissions

    class Meta:
        model = SpeakerProfile
        fields = (
            "name",
            "code",
            "email",
            "submission_count",
            "accepted_submission_count",
            "submissions",
            "locale",
            "has_arrived",
        )


class SpeakerOrgaTable(SpeakerTable):
    filters = staticmethod(user_speaker_filters)
    sensitive_columns = ()
    export_permission = None

    name = SortableTemplateColumn(
        verbose_name=_("Name"),
        order_by=Lower("name"),
        template_name="orga/includes/user_name.html",
        context_object_name="user",
    )
    email = tables.Column(linkify=lambda record: f"mailto:{record.email}")

    configurable = False  # Has no event, so can't save preferences
    # Unavailable columns are set to `None`.
    locale = None
    code = None
    submissions = None
    has_arrived = None
    invite_status = None
    speaker_type = None
    has_email = None
    biography = None
    avatar = None
    submission_ids = None
    submission_titles = None
    actions = None
    default_columns = ("name", "email", "submission_count", "accepted_submission_count")

    @classmethod
    def get_filter_options(cls, event, user):
        return {}

    class Meta:
        model = User
        fields = ("name", "email", "submission_count", "accepted_submission_count")
