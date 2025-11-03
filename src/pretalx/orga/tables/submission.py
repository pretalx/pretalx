# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import statistics
from collections import defaultdict
from functools import partial

import django_tables2 as tables
from django.db.models.functions import Lower
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import (
    ActionsColumn,
    BooleanColumn,
    DateTimeColumn,
    PretalxTable,
    SortableColumn,
    SortableTemplateColumn,
    TemplateColumn,
)
from pretalx.orga.utils.i18n import Translate
from pretalx.submission.models import Submission, Tag


def render_independent_score(record, table, category_id):
    if not hasattr(record, "_independent_scores_cache"):
        record._independent_scores_cache = table.get_independent_scores_for_submission(
            record
        )
    score = record._independent_scores_cache.get(category_id)
    return score if score is not None else "-"


def render_question_answer(record, table, question_id):
    if not hasattr(record, "_short_answers_cache"):
        record._short_answers_cache = table.get_short_answers_for_submission(record)
    return record._short_answers_cache.get(question_id, "")


class CallableColumn(tables.Column):
    """Column that renders using a callable function.

    To avoid pickling issues, stores the callable directly without binding to self.
    The callable should accept (record, column) as arguments, where column has
    a table_ref attribute set after initialization.
    """

    def __init__(self, *args, callable_func=None, **kwargs):
        self.callable_func = callable_func
        self.table_ref = None
        super().__init__(*args, **kwargs)

    def render(self, record):
        return self.callable_func(record, self.table_ref)


class SubmissionTable(PretalxTable):
    exempt_columns = ("pk", "actions", "indicator")

    indicator = TemplateColumn(
        verbose_name="",
        template_name="orga/tables/columns/submission_side_indicator.html",
        orderable=False,
        exclude_from_export=True,
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
    speakers = TemplateColumn(
        template_name="orga/tables/columns/submission_speakers.html",
        orderable=False,
    )
    submission_type = SortableColumn(
        linkify=lambda record: record.submission_type.urls.base,
        order_by=Lower(Translate("submission_type__name")),
    )
    track = SortableColumn(
        order_by=Lower(Translate("track__name")),
        linkify=lambda record: record.track.urls.base if record.track else None,
    )
    state = TemplateColumn(
        template_name="orga/submission/state_dropdown.html",
        verbose_name=_("State"),
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
    do_not_record = BooleanColumn(
        verbose_name=_("Do not record"),
    )
    actions = ActionsColumn(
        actions={
            "edit": {"url": "orga_urls.edit"},
            "delete": {"url": "orga_urls.delete"},
        }
    )

    def __init__(self, *args, can_view_speakers=False, **kwargs):
        super().__init__(*args, **kwargs)

        self.exclude = list(self.exclude)
        self.can_view_speakers = can_view_speakers

        if not can_view_speakers:
            self.exclude += ["speakers"]
        if not kwargs.get("has_update_permission"):
            self.exclude += ["is_featured", "actions"]

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
        if self.event and self.event.feature_flags.get("use_tracks"):
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


class ReviewTable(PretalxTable):
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
    speakers = TemplateColumn(
        template_name="orga/tables/columns/submission_speakers.html",
        verbose_name=_("Speakers"),
        orderable=False,
        attrs={"td": {"class": "w-25 nowrap"}},
    )
    code = tables.Column(
        verbose_name=_("ID"),
        linkify=lambda record: record.orga_urls.reviews,
    )
    track = SortableColumn(
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
        accessor="export_duration",
        orderable=False,
        attrs={"td": {"class": "nowrap"}},
    )
    submission_type = SortableColumn(
        order_by=Lower(Translate("submission_type__name")),
        linkify=lambda record: record.submission_type.urls.base,
    )
    state = TemplateColumn(
        template_name="orga/tables/columns/review_state.html",
        verbose_name=_("State"),
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

    @property
    def default_columns(self):
        columns = []
        if self.can_see_all_reviews:
            if self.aggregate_method == "median":
                columns.append("median_score")
            else:
                columns.append("mean_score")
            if self.independent_categories:
                for category in self.independent_categories:
                    columns.append(f"independent_score_{category.pk}")
        if self.is_reviewer:
            columns.append("user_score")
        columns.extend(["review_count", "title"])
        if self.can_view_speakers:
            columns.append("speakers")
        if self.event and self.event.feature_flags.get("use_tracks"):
            columns.append("track")
        columns.append("state")
        return columns

    def __init__(
        self,
        *args,
        can_see_all_reviews=False,
        is_reviewer=False,
        can_view_speakers=False,
        can_accept_submissions=False,
        independent_categories=None,
        short_questions=None,
        aggregate_method="mean",
        request_user=None,
        **kwargs,
    ):
        self.aggregate_method = aggregate_method
        self.can_see_all_reviews = can_see_all_reviews
        self.is_reviewer = is_reviewer
        self.can_view_speakers = can_view_speakers
        self.can_accept_submissions = can_accept_submissions
        self.independent_categories = independent_categories or []
        self.short_questions = short_questions or []
        self.request_user = request_user

        if self.independent_categories:
            for category in self.independent_categories:
                column_name = f"independent_score_{category.pk}"
                self.base_columns[column_name] = CallableColumn(
                    verbose_name=category.name,
                    accessor="pk",
                    orderable=False,
                    callable_func=partial(
                        render_independent_score, category_id=category.pk
                    ),
                    attrs={"td": {"class": "numeric text-center"}},
                )

        if self.short_questions:
            for question in self.short_questions:
                column_name = f"question_{question.id}"
                self.base_columns[column_name] = CallableColumn(
                    verbose_name=question.question,
                    accessor="pk",
                    orderable=False,
                    callable_func=partial(
                        render_question_answer, question_id=question.pk
                    ),
                )

        if self.can_accept_submissions:
            header_html = render_to_string(
                "orga/tables/columns/review_actions_header.html", {"table": self}
            )
            self.base_columns["actions"] = TemplateColumn(
                template_name="orga/tables/columns/review_actions.html",
                verbose_name=mark_safe(header_html),
                orderable=False,
                attrs={"td": {"class": "nowrap"}},
            )

        super().__init__(*args, **kwargs)

        for bound_column in self.columns:
            if isinstance(bound_column.column, CallableColumn):
                bound_column.column.table_ref = self

        self.exclude = list(self.exclude) if hasattr(self, "exclude") else []

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

    def get_independent_scores_for_submission(self, submission):
        if not self.independent_categories:
            return {}

        independent_ids = [cat.pk for cat in self.independent_categories]

        if self.can_see_all_reviews:
            mapping = defaultdict(list)
            for review in submission.reviews.all():
                for score in review.scores.all():
                    if score.category_id in independent_ids:
                        mapping[score.category_id].append(score.value)
            return {
                key: round(statistics.fmean(value), 1) for key, value in mapping.items()
            }
        else:
            reviews = [
                review
                for review in submission.reviews.all()
                if review.user == self.request_user
            ]
            if reviews:
                review = reviews[0]
                return {
                    score.category_id: score.value
                    for score in review.scores.all()
                    if score.category_id in independent_ids
                }
            return {}

    def get_short_answers_for_submission(self, submission):
        if not self.short_questions:
            return {}

        return {
            answer.question_id: answer.answer_string
            for answer in submission.answers.all()
            if answer.question in self.short_questions
        }

    def get_independent_score(self, record, category_id):
        if not hasattr(record, "_independent_scores_cache"):
            record._independent_scores_cache = (
                self.get_independent_scores_for_submission(record)
            )
        score = record._independent_scores_cache.get(category_id)
        return score if score is not None else "-"

    def get_question_answer(self, record, question_id):
        if not hasattr(record, "_short_answers_cache"):
            record._short_answers_cache = self.get_short_answers_for_submission(record)
        return record._short_answers_cache.get(question_id, "")

    class Meta:
        model = Submission
        fields = ()
        row_attrs = {"class": lambda record: record.state}


class TagTable(PretalxTable):
    default_columns = (
        "tag",
        "color",
        "proposals",
    )

    tag = tables.Column(
        linkify=lambda record: record.urls.edit,
    )
    color = TemplateColumn(
        template_name="orga/tables/columns/color_square.html",
    )
    proposals = tables.Column(
        verbose_name=_("Proposals"),
        accessor="submission_count",
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
        linkify=lambda record: record.event.orga_urls.submissions
        + f"?tags={record.pk}",
        initial_sort_descending=True,
    )
    is_public = BooleanColumn()
    actions = ActionsColumn(actions={"edit": {}, "delete": {}})

    class Meta:
        model = Tag
        fields = (
            "tag",
            "color",
            "proposals",
            "is_public",
            "actions",
        )
