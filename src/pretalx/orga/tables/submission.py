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
    ContextTemplateColumn,
    PretalxTable,
    SortableColumn,
    SortableTemplateColumn,
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
    indicator = SortableTemplateColumn(
        template_name="orga/tables/columns/submission_side_indicator.html",
        order_by=Lower(Translate("track__name")),
        verbose_name="",
        exclude_from_export=True,
    )
    title = SortableTemplateColumn(
        verbose_name=_("Title"),
        template_name="orga/tables/columns/submission_title.html",
        order_by=Lower("title"),
        linkify=lambda record: record.orga_urls.base,
    )
    speakers = tables.TemplateColumn(
        template_name="orga/tables/columns/submission_speakers.html",
        verbose_name=_("Speakers"),
        orderable=False,
    )
    submission_type = SortableColumn(
        verbose_name=_("Type"),
        linkify=lambda record: record.submission_type.urls.base,
        accessor="submission_type__name",
        order_by=Lower(Translate("submission_type__name")),
    )
    state = ContextTemplateColumn(
        template_name="orga/submission/state_dropdown.html",
        verbose_name=_("State"),
        context_object_name="submission",
    )
    is_featured = ContextTemplateColumn(
        template_name="orga/tables/columns/submission_is_featured.html",
        verbose_name=_("Featured"),
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

    review_count = tables.TemplateColumn(
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
    speakers = tables.TemplateColumn(
        template_name="orga/tables/columns/submission_speakers.html",
        verbose_name=_("Speakers"),
        orderable=False,
        attrs={"td": {"class": "w-25 nowrap"}},
    )
    track = SortableColumn(
        verbose_name=_("Track"),
        accessor="track__name",
        order_by=Lower(Translate("track__name")),
        attrs={"td": {"class": "nowrap"}},
    )
    tags = tables.TemplateColumn(
        template_name="orga/tables/columns/review_tags.html",
        verbose_name=_("Tags"),
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
        verbose_name=_("Type"),
        accessor="submission_type__name",
        order_by=Lower(Translate("submission_type__name")),
        attrs={"td": {"class": "nowrap"}},
    )
    state = tables.TemplateColumn(
        template_name="orga/tables/columns/review_state.html",
        verbose_name=_("State"),
        initial_sort_descending=True,
        attrs={"td": {"class": "nowrap"}},
    )

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
        self.can_see_all_reviews = can_see_all_reviews
        self.is_reviewer = is_reviewer
        self.can_view_speakers = can_view_speakers
        self.can_accept_submissions = can_accept_submissions
        self.independent_categories = independent_categories or []
        self.short_questions = short_questions or []
        self.aggregate_method = aggregate_method
        self.request_user = request_user

        default_sequence = ["median_score", "mean_score"]
        if self.independent_categories:
            for category in self.independent_categories:
                column_name = f"independent_score_{category.pk}"
                default_sequence.append(column_name)

                self.base_columns[column_name] = CallableColumn(
                    verbose_name=category.name,
                    accessor="pk",
                    orderable=False,
                    callable_func=partial(
                        render_independent_score, category_id=category.pk
                    ),
                    attrs={"td": {"class": "numeric text-center"}},
                )

        default_sequence += ["user_score", "review_count", "title"]
        if self.short_questions:
            for question in self.short_questions:
                column_name = f"question_{question.id}"
                default_sequence.append(column_name)

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
            self.base_columns["actions"] = tables.TemplateColumn(
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

        self.columns.hide("duration")
        self.columns.hide("submission_type")
        self.columns.hide("tags")
        for question in self.short_questions:
            self.columns.hide(f"question_{question.id}")
        self.sequence = default_sequence

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
    tag = tables.Column(
        linkify=lambda record: record.urls.edit,
        verbose_name=_("Tag"),
    )
    color = tables.TemplateColumn(
        verbose_name=_("Colour"),
        template_name="orga/tables/columns/color_square.html",
    )
    proposals = tables.Column(
        verbose_name=_("Proposals"),
        accessor="submission_count",
        initial_sort_descending=True,
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
