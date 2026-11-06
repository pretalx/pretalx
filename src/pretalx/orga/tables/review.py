# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.tables import (
    Column,
    DateTimeColumn,
    IndependentScoreColumn,
    PretalxTable,
    QuestionColumnMixin,
)
from pretalx.common.tables.filters import MultiChoiceFilter
from pretalx.common.text.phrases import phrases
from pretalx.submission.domain.queries.submission import submissions_for_user
from pretalx.submission.enums import QuestionTarget, SubmissionStates
from pretalx.submission.models import Review, Submission


def review_export_filters(context):
    return [
        MultiChoiceFilter(
            name="state",
            field="submission__state",
            label=_("State"),
            choices=[
                (state, str(label).capitalize())
                for state, label in SubmissionStates.choices
                if state
                in (
                    SubmissionStates.SUBMITTED,
                    SubmissionStates.ACCEPTED,
                    SubmissionStates.CONFIRMED,
                    SubmissionStates.REJECTED,
                )
            ],
        )
    ]


class ReviewExportTable(QuestionColumnMixin, PretalxTable):
    """One row per review. Export only."""

    printable = False
    filters = staticmethod(review_export_filters)
    question_target = QuestionTarget.REVIEWER
    update_permission = None
    delete_permission = None
    export_name = _("Reviews")
    export_permission = "submission.list_review"
    default_columns = (
        "submission_code",
        "submission_title",
        "user_name",
        "score",
        "text",
        "created",
    )

    submission_code = Column(verbose_name=_("Proposal ID"), accessor="submission__code")
    submission_title = Column(
        verbose_name=Submission._meta.get_field("title").verbose_name,
        accessor="submission__title",
    )
    user_name = Column(verbose_name=_("Reviewer name"), accessor="user__name")
    user_email = Column(
        verbose_name=pgettext_lazy("field: reviewer's email address", "Reviewer email"),
        accessor="user__email",
    )
    score = Column()
    text = Column(verbose_name=phrases.base.text_body)
    created = DateTimeColumn()

    @classmethod
    def base_queryset(cls, event, user):
        reviews = Review.objects.filter(
            submission__in=submissions_for_user(event, user)
        ).exclude(submission__speakers__user=user)
        if not user.has_perm("submission.list_all_review", event):
            reviews = reviews.filter(user=user)
        return (
            reviews.select_related("submission", "user")
            .prefetch_related("scores", "scores__category")
            .order_by("submission__code", "pk")
            .distinct()
        )

    updated = DateTimeColumn()

    def __init__(self, *args, **kwargs):
        event = kwargs.get("event")
        self.score_categories = list(self.get_score_categories(event))
        extra_columns = [
            (
                f"score_{category.pk}",
                IndependentScoreColumn(
                    verbose_name=_("Score in “{score_category}”").format(
                        score_category=category.name
                    ),
                    category=category,
                ),
            )
            for category in self.score_categories
        ]
        kwargs.setdefault("extra_columns", []).extend(extra_columns)
        super().__init__(*args, **kwargs)
        self.exclude = list(self.exclude)
        if not self.has_event_permission("list_reviewers"):
            self.exclude += ["user_name", "user_email"]
        self.can_view_speakers = self.has_event_permission(
            "person.orga_list_speakerprofile"
        )

    def value_submission_title(self, record):
        submission = record.submission
        if not self.can_view_speakers and submission.is_anonymised:
            return submission.get_anonymised("title")
        return submission.title

    @classmethod
    def get_score_categories(cls, event):
        if not event:
            return []
        categories = list(event.score_categories.filter(active=True))
        if len(categories) == 1:
            return []
        return categories

    def get_independent_score(self, review, category_id):
        for score in review.scores.all():
            if score.category_id == category_id:
                return score.value
        return None

    class Meta:
        model = Review
        fields = ()
