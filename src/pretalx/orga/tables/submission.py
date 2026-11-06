# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import statistics
from collections import defaultdict

import django_tables2 as tables
from django.db.models import Count, F, Max, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce, Lower
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.db import Translate
from pretalx.common.tables import (
    ActionsColumn,
    BooleanColumn,
    ColourColumn,
    Column,
    DateTimeColumn,
    IndependentScoreColumn,
    PretalxTable,
    QuestionColumnMixin,
    SortableColumn,
    SortableTemplateColumn,
    TemplateColumn,
)
from pretalx.common.text.phrases import phrases
from pretalx.common.urls import get_base_url
from pretalx.person.models.profile import speaker_name_expression
from pretalx.person.rules import is_only_reviewer
from pretalx.schedule.models import TalkSlot
from pretalx.submission.domain.queries.review import (
    annotate_aggregate_scores,
    annotate_review_count,
    annotate_scored_review_count,
    annotate_state_rank,
    annotate_user_review_score,
)
from pretalx.submission.domain.queries.submission import (
    annotate_assigned_reviews,
    annotate_confirmed_signup_count,
    annotate_requires_signup,
    annotate_submission_count,
    current_slots_prefetch,
    submissions_for_user,
)
from pretalx.submission.enums import SubmissionStates
from pretalx.submission.interfaces.filters import (
    review_list_filters,
    submission_list_filters,
)
from pretalx.submission.models import Review, SpeakerRole, Submission, Tag
from pretalx.submission.models.resource import active_resource_filter


class SpeakersColumn(TemplateColumn):
    def apply_custom_ordering(self, queryset, is_descending):
        # Sort by the first speaker name, sessions without speakers always last
        first_speaker = (
            SpeakerRole.objects.filter(submission=OuterRef("pk"))
            .order_by("position", "pk")
            .values(name=speaker_name_expression(prefix="speaker__"))[:1]
        )
        queryset = queryset.annotate(_sort_speakers=Lower(Subquery(first_speaker)))
        if is_descending:
            order = F("_sort_speakers").desc(nulls_last=True)
        else:
            order = F("_sort_speakers").asc(nulls_last=True)
        return queryset, [order]


def _split_label(field, part):
    label = TalkSlot._meta.get_field(field).verbose_name
    if part == "date":
        part_label = pgettext_lazy("date as in calendar date", "date")
    else:
        part_label = _("time")
    return format_lazy("{} ({})", label, part_label)


class SubmissionValuesMixin:
    """Export values for the templated columns shared by submission-row tables."""

    def __init__(
        self,
        *args,
        show_tracks=None,
        show_submission_types=None,
        show_tags=None,
        **kwargs,
    ):
        event = kwargs.get("event")
        if show_tracks is None:
            show_tracks = bool(event and event.has_active_tracks)
        if show_submission_types is None:
            show_submission_types = bool(event and event.submission_types.count() > 1)
        if show_tags is None:
            show_tags = bool(event and event.tags.exists())
        self.show_tracks = show_tracks
        self.show_submission_types = show_submission_types
        self.show_tags = show_tags
        super().__init__(*args, **kwargs)
        self.exclude = list(self.exclude)
        if not show_tracks:
            self.exclude.append("track")
        if not show_submission_types:
            self.exclude.append("submission_type")
        if not show_tags:
            self.exclude.append("tags")

    def column_prefetches(self, columns):
        lookups = [name for name in ("tags", "resources") if name in columns]
        slot_columns = {
            "room",
            "start",
            "start_date",
            "start_time",
            "end",
            "end_date",
            "end_time",
        }
        if self.event and columns & slot_columns:
            lookups.append(current_slots_prefetch(self.event))
        return lookups

    def _anonymisable(self, record, attribute):
        if not self.can_view_speakers and record.is_anonymised:
            return record.get_anonymised(attribute)
        return getattr(record, attribute)

    def value_title(self, record):
        return self._anonymisable(record, "title")

    def value_abstract(self, record):
        return self._anonymisable(record, "abstract")

    def value_description(self, record):
        return self._anonymisable(record, "description")

    def value_notes(self, record):
        return self._anonymisable(record, "notes")

    def value_speakers(self, record):
        return [speaker.get_display_name() for speaker in record.sorted_speakers]

    def value_state(self, record):
        return record.state

    def value_pending_state(self, record):
        return record.pending_state

    def value_content_locale(self, record):
        return record.content_locale

    def value_duration(self, record):
        return record.get_duration()

    def value_submission_type(self, record):
        return record.submission_type.name

    def value_tags(self, record):
        return [tag.tag for tag in record.tags.all()]

    @classmethod
    def get_can_view_speakers(cls, event, user):
        if not event or not user or not user.pk:
            return False
        return user.has_perm("person.orga_list_speakerprofile", event) or user.has_perm(
            "person.reviewer_list_speakerprofile", event
        )

    @classmethod
    def get_filter_options(cls, event, user):
        options = super().get_filter_options(event, user)
        options["can_view_speakers"] = cls.get_can_view_speakers(event, user)
        if user and user.pk and is_only_reviewer(user, event):
            options["limit_tracks"] = user.get_reviewer_tracks(event)
        return options


class SubmissionTable(SubmissionValuesMixin, QuestionColumnMixin, PretalxTable):
    primary_column = "title"
    exempt_columns = ("pk", "actions", "indicator")
    filters = staticmethod(submission_list_filters)
    filter_options = {"default_states": SubmissionStates.active_states}
    update_permission = "orga_update"
    delete_permission = "orga_update"
    export_name = phrases.schedule.sessions
    export_permission = "submission.orga_list_submission"

    indicator = TemplateColumn(
        verbose_name="",
        template_name="orga/tables/columns/submission_side_indicator.html",
        orderable=False,
        exclude_from_export=True,
        placeholder="",
        attrs={"th": {"class": "d-print-none"}, "td": {"class": "d-print-none"}},
    )
    code = tables.Column(
        verbose_name=_("ID"),
        accessor="code",
        linkify=lambda record: record.orga_urls.base,
    )
    title = SortableTemplateColumn(
        verbose_name=_("Title"),
        template_name="orga/tables/columns/submission_title.html",
        order_by=Lower("title"),
        linkify=lambda record: record.orga_urls.base,
    )
    speakers = SpeakersColumn(
        template_name="orga/tables/columns/submission_speakers.html"
    )
    speaker_count = tables.Column(
        verbose_name=_("Number of speakers"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric text-center"}},
        initial_sort_descending=True,
    )
    invitation_count = tables.Column(
        verbose_name=_("Pending invitations"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric text-center"}},
        initial_sort_descending=True,
    )
    submission_type = SortableColumn(
        linkify=lambda record: record.submission_type.urls.base,
        order_by=Lower(Translate("submission_type__name")),
    )
    duration = tables.Column(
        verbose_name=_("Duration"),
        accessor="duration_display",
        orderable=False,
        attrs={"td": {"class": "nowrap"}},
    )
    track = ColourColumn(
        order_by=Lower(Translate("track__name")),
        linkify=lambda record: record.track.urls.base if record.track else None,
    )
    state = TemplateColumn(
        template_name="orga/submission/state_dropdown.html",
        verbose_name=phrases.submission.state,
        context_object_name="submission",
    )
    pending_state = SortableTemplateColumn(
        verbose_name=_("Pending state"),
        template_name="cfp/event/fragment_state.html",
        template_context={
            "state": lambda record, table: record.pending_state,
            "as_badge": True,
        },
    )
    created = DateTimeColumn()
    is_featured = TemplateColumn(
        template_name="orga/tables/columns/submission_is_featured.html",
        verbose_name=_("Featured"),
    )
    do_not_record = BooleanColumn(verbose_name=_("Do not record"))
    requires_signup = BooleanColumn(
        verbose_name=_("Requires signup"),
        accessor="requires_signup",
        order_by=("_annotated_requires_signup",),
    )
    attendee_signup_count = tables.Column(
        verbose_name=_("Number of attendees"),
        accessor="confirmed_signup_count",
        order_by=("_annotated_confirmed_signup_count",),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric text-center"}},
        initial_sort_descending=True,
    )
    content_locale = tables.Column(verbose_name=_("Language"))
    resource_count = tables.Column(
        verbose_name=_("Number of resources"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric text-center"}},
    )
    slot_count = Column()
    tags = TemplateColumn(
        template_name="orga/tables/columns/review_tags.html",
        verbose_name=_("Tags"),
        orderable=False,
        attrs={"td": {"class": "nowrap"}},
    )
    room = Column(accessor="slot__room__name", orderable=False)
    start = DateTimeColumn(accessor="slot__local_start", orderable=False)
    start_date = DateTimeColumn(
        accessor="slot__local_start",
        part="date",
        verbose_name=_split_label("start", "date"),
        orderable=False,
    )
    start_time = DateTimeColumn(
        accessor="slot__local_start",
        part="time",
        verbose_name=_split_label("start", "time"),
        orderable=False,
    )
    end = DateTimeColumn(accessor="slot__local_end", orderable=False)
    end_date = DateTimeColumn(
        accessor="slot__local_end",
        part="date",
        verbose_name=_split_label("end", "date"),
        orderable=False,
    )
    end_time = DateTimeColumn(
        accessor="slot__local_end",
        part="time",
        verbose_name=_split_label("end", "time"),
        orderable=False,
    )
    abstract = Column(export_only=True)
    description = Column(export_only=True)
    notes = Column(export_only=True)
    internal_notes = Column(export_only=True)
    image = Column(
        verbose_name=_("Image"), accessor="image_url", orderable=False, export_only=True
    )
    speaker_ids = Column(
        verbose_name=_("Speaker IDs"),
        orderable=False,
        export_only=True,
        empty_values=(),
    )
    speaker_emails = Column(
        verbose_name=_("Speaker emails"),
        orderable=False,
        export_only=True,
        empty_values=(),
    )
    resources = Column(verbose_name=_("Resources"), orderable=False, export_only=True)
    actions = ActionsColumn(
        actions={
            "edit": {"url": "orga_urls.edit"},
            "email": {
                "title": _("Send email to speakers"),
                "icon": "envelope",
                "url": lambda record: (
                    f"{record.event.orga_urls.compose_mails_sessions}"
                    f"?submissions={record.code}"
                ),
                "permission": "mail.send_queuedmail",
                "as_button": False,
            },
            "delete": {"url": "orga_urls.delete"},
        }
    )

    def __init__(self, *args, can_view_speakers=None, **kwargs):
        super().__init__(*args, **kwargs)

        if can_view_speakers is None:
            can_view_speakers = self.has_event_permission(
                "person.orga_list_speakerprofile"
            )
        self.can_view_speakers = can_view_speakers
        self.exclude = list(self.exclude)

        if not can_view_speakers:
            self.exclude += ["speakers", "speaker_ids"]
        if not self.has_update_permission:
            self.exclude += ["is_featured", "actions", "internal_notes"]
        if not (self.has_update_permission and can_view_speakers):
            self.exclude += ["speaker_emails"]
        if not (self.event and self.event.get_feature_flag("attendee_signup")):
            self.exclude += ["requires_signup", "attendee_signup_count"]

    @classmethod
    def base_queryset(cls, event, user):
        queryset = (
            submissions_for_user(event, user)
            .select_related(
                "track__event",
                "track__event__cfp",
                "submission_type__event",
                "submission_type__event__cfp",
            )
            .with_sorted_speakers()
        )
        return annotate_assigned_reviews(queryset, event, user)

    @classmethod
    def augment_queryset(cls, queryset, *, event, user):
        # We have to count via subqueries to avoid only counting speakers
        # matched by the search terms
        speaker_count = (
            SpeakerRole.objects.filter(submission=OuterRef("pk"))
            .order_by()
            .values("submission")
            .annotate(count=Count("pk"))
            .values("count")
        )
        queryset = (
            queryset.distinct()
            .select_related("event", "event__cfp")
            .annotate(
                speaker_count=Coalesce(Subquery(speaker_count), Value(0)),
                invitation_count=Count("invitations", distinct=True),
                resource_count=Count(
                    "resources",
                    filter=active_resource_filter("resources__"),
                    distinct=True,
                ),
            )
        )
        if event.get_feature_flag("attendee_signup"):
            queryset = annotate_confirmed_signup_count(
                annotate_requires_signup(queryset)
            )
        return queryset

    def value_speaker_ids(self, record):
        return [speaker.code for speaker in record.sorted_speakers]

    def value_speaker_emails(self, record):
        return [
            speaker.effective_email
            for speaker in record.sorted_speakers
            if speaker.effective_email
        ]

    def value_image(self, value):
        return get_base_url(self.event) + value

    def value_resources(self, record):
        return [resource.url for resource in record.public_resources if resource.url]

    def value_is_featured(self, record):
        return record.is_featured

    @property
    def default_columns(self):
        columns = [
            "indicator",
            "title",
            "speakers",
            "submission_type",
            "state",
            "is_featured",
        ]
        if self.show_tracks:
            columns.insert(3, "track")
        return columns

    def _set_columns(self, selected_columns):
        # Override set_columns to make sure the indicator stays on the left
        super()._set_columns(selected_columns)
        self.sequence.remove("indicator")
        self.sequence.insert(0, "indicator")

    def render_content_locale(self, record):
        return record.get_content_locale_display()

    class Meta:
        model = Submission
        fields = ()


class ReviewTable(SubmissionValuesMixin, QuestionColumnMixin, PretalxTable):
    primary_column = "title"
    filters = staticmethod(review_list_filters)
    usable_states = (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CONFIRMED,
    )
    filter_options = {"usable_states": usable_states}
    update_permission = "orga_update"
    delete_permission = "orga_update"
    export_name = _("Review dashboard")
    export_permission = "submission.list_review"

    median_score = tables.Column(
        verbose_name=_("Median"),
        order_by=("median_score",),
        initial_sort_descending=True,
        attrs={"td": {"class": "text-center numeric"}},
    )
    mean_score = tables.Column(
        verbose_name=_("Average"),
        order_by=("mean_score",),
        initial_sort_descending=True,
        attrs={"td": {"class": "text-center numeric"}},
    )
    user_score = tables.Column(
        verbose_name=_("Your score"),
        order_by=("user_score",),
        initial_sort_descending=True,
        attrs={"td": {"class": "text-center numeric"}},
    )

    def render_median_score(self, value):
        return f"{value:.1f}"

    def render_mean_score(self, value):
        return f"{value:.1f}"

    def render_user_score(self, value):
        return f"{value:.1f}"

    def _raw_score(self, value):
        return value

    value_median_score = value_mean_score = value_user_score = _raw_score

    def render_content_locale(self, record):
        return record.get_content_locale_display()

    review_count = TemplateColumn(
        verbose_name=_("Reviews"),
        template_name="orga/tables/columns/review_count.html",
        order_by=("review_nonnull_count",),
        initial_sort_descending=True,
        attrs={"td": {"class": "text-center numeric nowrap"}},
    )
    title = SortableTemplateColumn(
        verbose_name=_("Title"),
        template_name="orga/tables/columns/submission_title.html",
        order_by=Lower("title"),
        attrs={"td": {"class": "w-75"}},
        linkify=lambda record: record.orga_urls.reviews,
    )
    speakers = SpeakersColumn(
        template_name="orga/tables/columns/submission_speakers.html",
        verbose_name=_("Speakers"),
        attrs={"td": {"class": "w-25 nowrap"}},
    )
    code = tables.Column(
        verbose_name=_("ID"), linkify=lambda record: record.orga_urls.reviews
    )
    track = ColourColumn(
        order_by=Lower(Translate("track__name")),
        attrs={"td": {"class": "nowrap"}},
        linkify=lambda record: record.track.urls.base if record.track else None,
    )
    tags = TemplateColumn(
        template_name="orga/tables/columns/review_tags.html",
        orderable=False,
        attrs={"td": {"class": "nowrap"}},
    )
    duration = tables.Column(
        verbose_name=_("Duration"),
        accessor="duration_display",
        orderable=False,
        attrs={"td": {"class": "nowrap"}},
    )
    submission_type = SortableColumn(
        order_by=Lower(Translate("submission_type__name")),
        linkify=lambda record: record.submission_type.urls.base,
    )
    state = TemplateColumn(
        template_name="cfp/event/fragment_state.html",
        template_context={
            "state": lambda record, table: record.state,
            "pending_state": lambda record, table: record.pending_state,
            "as_badge": True,
            "with_pending": True,
        },
        verbose_name=phrases.submission.state,
        initial_sort_descending=True,
        attrs={"td": {"class": "nowrap"}},
    )
    pending_state = SortableTemplateColumn(
        verbose_name=_("Pending state"),
        template_name="cfp/event/fragment_state.html",
        template_context={
            "state": lambda record, table: record.pending_state,
            "as_badge": True,
        },
    )
    created = DateTimeColumn()
    do_not_record = BooleanColumn(verbose_name=_("Do not record"))
    content_locale = tables.Column(verbose_name=_("Language"))
    abstract = Column(export_only=True)
    description = Column(export_only=True)
    notes = Column(export_only=True)

    @property
    def default_columns(self):
        columns = []
        if self.can_see_all_reviews:
            if self.aggregate_method == "median":
                columns.append("median_score")
            else:
                columns.append("mean_score")
            if self.independent_categories:
                columns.extend(
                    f"independent_score_{category.pk}"
                    for category in self.independent_categories
                )
        if self.is_reviewer:
            columns.append("user_score")
        columns.extend(["review_count", "title"])
        if self.can_view_speakers:
            columns.append("speakers")
        if self.show_tracks:
            columns.append("track")
        columns.append("state")
        return columns

    def __init__(
        self,
        *args,
        can_see_all_reviews=None,
        is_reviewer=None,
        can_view_speakers=None,
        can_accept_submissions=None,
        independent_categories=None,
        aggregate_method=None,
        request_user=None,
        **kwargs,
    ):
        event = kwargs.get("event")
        user = kwargs.get("user")
        self.request_user = request_user or user
        has_user = bool(event and user and user.pk)
        if aggregate_method is None:
            aggregate_method = (
                event.review_settings["aggregate_method"] if event else "mean"
            )
        if can_see_all_reviews is None:
            can_see_all_reviews = self.get_can_see_all_reviews(event, user)
        if is_reviewer is None:
            is_reviewer = has_user and (
                user.has_perm("submission.create_review", event)
                or Review.objects.filter(user=user, submission__event=event).exists()
            )
        if can_view_speakers is None:
            can_view_speakers = has_user and user.has_perm(
                "person.reviewer_list_speakerprofile", event
            )
        if can_accept_submissions is None:
            can_accept_submissions = (
                has_user
                and user.has_perm("submission.accept_or_reject_submission", event)
                and event.submissions.filter(state=SubmissionStates.SUBMITTED).exists()
            )
        if independent_categories is None:
            independent_categories = (
                event.score_categories.filter(is_independent=True, active=True)
                if event
                else []
            )
        self.aggregate_method = aggregate_method
        self.can_see_all_reviews = can_see_all_reviews
        self.is_reviewer = is_reviewer
        self.can_view_speakers = can_view_speakers
        self.can_accept_submissions = can_accept_submissions
        self.independent_categories = list(independent_categories)

        extra_columns = []
        for category in self.independent_categories:
            column_name = f"independent_score_{category.pk}"
            extra_columns.append(
                (
                    column_name,
                    IndependentScoreColumn(
                        verbose_name=category.name,
                        category=category,
                        attrs={"td": {"class": "numeric text-center"}},
                    ),
                )
            )

        if self.can_accept_submissions:
            header_html = render_to_string(
                "orga/tables/columns/review_actions_header.html", {"table": self}
            )
            extra_columns.append(
                (
                    "actions",
                    TemplateColumn(
                        template_name="orga/tables/columns/review_actions.html",
                        verbose_name=mark_safe(header_html),  # noqa: S308  -- static icon markup
                        orderable=False,
                        exclude_from_export=True,
                        attrs={"td": {"class": "nowrap"}},
                    ),
                )
            )

        kwargs.setdefault("extra_columns", []).extend(extra_columns)
        super().__init__(*args, **kwargs)

        if self.can_see_all_reviews:
            if aggregate_method == "median":
                self.exclude.append("mean_score")
            else:
                self.exclude.append("median_score")
        else:
            self.exclude.extend(["median_score", "mean_score"])

        if not self.is_reviewer:
            self.exclude.append("user_score")

        if not self.can_view_speakers:
            self.exclude.append("speakers")

        if (
            "tags" not in self.exclude
            and not self.for_export
            and not (self.filterset and self.filterset.is_set("tags"))
        ):
            self.exclude.append("tags")

    @classmethod
    def get_can_see_all_reviews(cls, event, user):
        if not event or not user or not user.pk:
            return False
        return user.has_perm("submission.list_all_review", event)

    @classmethod
    def get_filter_options(cls, event, user):
        options = super().get_filter_options(event, user)
        if event:
            options["max_review_count"] = (
                event.submissions.all()
                .annotate(review_count=Count("reviews", distinct=True))
                .aggregate(Max("review_count"))
                .get("review_count__max")
            )
        return options

    @classmethod
    def base_queryset(cls, event, user):
        return SubmissionTable.base_queryset(event, user).filter(
            state__in=cls.usable_states
        )

    @classmethod
    def prepare_queryset(cls, queryset, *, event, user):
        return annotate_review_count(queryset)

    @classmethod
    def augment_queryset(cls, queryset, *, event, user):
        queryset = annotate_scored_review_count(queryset)
        queryset = annotate_state_rank(queryset)
        queryset = annotate_user_review_score(queryset, user)
        if cls.get_can_see_all_reviews(event, user):
            queryset = annotate_aggregate_scores(queryset)
        return queryset.select_related("track", "submission_type")

    @cached_property
    def submissions_reviewed(self):
        if not self.request_user or not self.request_user.pk:
            return Review.objects.none()
        return Review.objects.filter(
            user=self.request_user, submission__event=self.event
        ).values_list("submission_id", flat=True)

    def value_review_count(self, record):
        return record.review_nonnull_count

    def get_independent_score(self, submission, category_id):
        if not self.independent_categories:
            return None
        if not hasattr(self, "_scores_cache"):
            self._load_all_scores()
        return self._scores_cache.get(submission.pk, {}).get(category_id)

    def _load_all_scores(self):
        try:
            submission_ids = [row.record.pk for row in self.rows]
        except (
            AttributeError,
            TypeError,
        ):  # pragma: no cover -- defensive fallback for partially-initialised tables
            submission_ids = [submission.pk for submission in self.data]

        if not submission_ids:
            self._scores_cache = {}
            return

        independent_ids = [cat.pk for cat in self.independent_categories]
        reviews = Review.objects.filter(
            submission_id__in=submission_ids
        ).prefetch_related("scores")

        # Build cache: {submission_id: {category_id: score}}
        self._scores_cache = {}

        if self.can_see_all_reviews:
            mapping = defaultdict(lambda: defaultdict(list))
            for review in reviews:
                for score in review.scores.all():
                    if score.category_id in independent_ids:
                        mapping[review.submission_id][score.category_id].append(
                            score.value
                        )

            aggregate = (
                statistics.median
                if self.aggregate_method == "median"
                else statistics.fmean
            )
            for submission_id, categories in mapping.items():
                self._scores_cache[submission_id] = {
                    cat_id: round(aggregate(values), 1)
                    for cat_id, values in categories.items()
                }
        else:
            for review in reviews:
                if review.user_id == self.request_user.pk:
                    self._scores_cache[review.submission_id] = {
                        score.category_id: score.value
                        for score in review.scores.all()
                        if score.category_id in independent_ids
                    }

    class Meta:
        model = Submission
        fields = ()
        row_attrs = {"class": lambda record: record.state}
        template_name = "orga/tables/review_table.html"


class TagTable(PretalxTable):
    primary_column = "tag"
    default_columns = ("tag", "proposals")
    export_name = _("Tags")
    export_permission = "submission.list_tag"

    tag = ColourColumn(linkify=lambda record: record.urls.edit)
    color = ColourColumn()
    proposals = tables.Column(
        verbose_name=_("Proposals"),
        accessor="submission_count",
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        linkify=lambda record: (
            record.event.orga_urls.submissions + f"?tags={record.pk}"
        ),
        initial_sort_descending=True,
    )
    is_public = BooleanColumn()
    actions = ActionsColumn(actions={"edit": {}, "delete": {}})

    @classmethod
    def base_queryset(cls, event, user):
        return annotate_submission_count(event.tags.order_by("tag", "pk"))

    class Meta:
        model = Tag
        fields = ("tag", "color", "proposals", "is_public", "actions")
