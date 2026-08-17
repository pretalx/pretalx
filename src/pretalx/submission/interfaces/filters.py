# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Count, Q
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables.filters import (
    BOOLEAN,
    EMPTY_VALUE,
    MULTI,
    RANGE,
    BooleanFilter,
    ChoiceFilter,
    FilterChoice,
    FilterPill,
    ModelChoiceFilter,
    ModelMultiChoiceFilter,
    MultiChoiceFilter,
    SearchFilter,
    TableFilter,
    segmented_widget,
)
from pretalx.common.text.phrases import phrases
from pretalx.submission.domain.queries.question import (
    filter_submissions_by_speaker_role,
    questions_for_user,
)
from pretalx.submission.domain.queries.submission import (
    annotate_requires_signup,
    annotate_submission_count,
    filter_submissions_by_state,
    search_submissions,
    submission_field_counts,
    submission_state_facets,
)
from pretalx.submission.enums import (
    AttendeeSignupStates,
    QuestionTarget,
    SubmissionStates,
)
from pretalx.submission.models import Answer

PENDING_PREFIX = "pending_state__"

ANSWERED = "__answered__"
UNANSWERED = "__unanswered__"
CUSTOM_FIELD_SECTION = _("Custom fields")


class QuestionAnswerFilter(MultiChoiceFilter):
    def __init__(self, *, question, answer_field="submission_id", **kwargs):
        kwargs.setdefault("name", f"question_{question.pk}")
        kwargs.setdefault("label", question.question)
        kwargs.setdefault("section", CUSTOM_FIELD_SECTION)
        super().__init__(**kwargs)
        self.question = question
        self.answer_field = answer_field

    @cached_property
    def options(self):
        return list(self.question.options.all())

    @property
    def is_boolean(self):
        return self.question.variant == "boolean"

    @property
    def allows_free_text(self):
        return not self.options and not self.is_boolean

    @property
    def control(self):
        return BOOLEAN if self.allows_free_text else MULTI

    def get_widget(self):
        if not self.allows_free_text:
            return super().get_widget()
        return segmented_widget(
            self.label, [(ANSWERED, _("Answered")), (UNANSWERED, _("Not answered"))]
        )

    def selected_values(self, value):
        if not self.allows_free_text:
            return super().selected_values(value)
        chosen = {str(entry) for entry in value or []}
        if not chosen:
            return [EMPTY_VALUE]
        return [entry for entry in (ANSWERED, UNANSWERED) if entry in chosen]

    def get_choices(self):
        if self.is_boolean:
            choices = [FilterChoice("True", _("Yes")), FilterChoice("False", _("No"))]
        else:
            choices = [
                FilterChoice(str(option.pk), option.answer) for option in self.options
            ]
        return [
            *choices,
            FilterChoice(ANSWERED, _("Answered")),
            FilterChoice(UNANSWERED, _("Not answered")),
        ]

    def parse(self, data):
        return [
            value
            for value in data.getlist(self.param)
            if value in self.choices_by_value or (self.allows_free_text and value)
        ]

    def _answers(self):
        return Answer.objects.filter(question_id=self.question.pk)

    def _keys(self, queryset):
        return queryset.filter(**{f"{self.answer_field}__isnull": False}).values_list(
            self.answer_field, flat=True
        )

    def filter(self, qs, value):
        sentinels = {entry for entry in value if entry in (ANSWERED, UNANSWERED)}
        concrete = [entry for entry in value if entry not in sentinels]
        base = self._answers()
        query = Q()
        if concrete:
            if self.options:
                matching = base.filter(options__pk__in=concrete)
            else:
                matching = base.filter(answer__in=concrete)
            query |= Q(pk__in=self._keys(matching))
        if ANSWERED in sentinels:
            answered = base.filter(Q(options__isnull=False) | ~Q(answer=""))
            query |= Q(pk__in=self._keys(answered))
        if UNANSWERED in sentinels:
            query |= ~Q(pk__in=self._keys(base))
        return qs.filter(query)

    def get_pills(self, value):
        known = self.choices_by_value
        pills = [
            FilterPill(
                param=pill.param,
                value=pill.value,
                label=f"{self.question.question}: {pill.label}",
            )
            for pill in super().get_pills(value)
        ]
        pills.extend(
            FilterPill(
                param=self.param,
                value=str(entry),
                label=f"{self.question.question}: {entry}",
            )
            for entry in value
            if str(entry) not in known
        )
        return pills


class SubmissionStateFilter(MultiChoiceFilter):
    def _base_choices(self):
        usable_states = self.context.get("usable_states")
        return [
            (state, label)
            for state, label in SubmissionStates.choices
            if state != SubmissionStates.DRAFT
            and (not usable_states or state in usable_states)
        ]

    def get_initial(self):
        return self.context.get("default_states")

    def parse(self, data):
        # We validate against _base_choices so we don't trigger the count queries
        valid = {state for state, label in self._base_choices()}
        valid |= {f"{PENDING_PREFIX}{state}" for state in valid}
        return [value for value in data.getlist(self.param) if value in valid]

    def get_choices(self):
        counts = submission_state_facets(
            self.event, usable_states=self.context.get("usable_states")
        )
        base = self._base_choices()
        choices = [
            FilterChoice(
                value=state,
                label=str(label).capitalize(),
                color=SubmissionStates.get_color(state),
                count=counts.get(state, 0),
                css_class=f"submission-state-{state}",
            )
            for state, label in base
        ]
        choices += [
            FilterChoice(
                value=f"{PENDING_PREFIX}{state}",
                label=_("Pending {state}").format(state=label),
                color=SubmissionStates.get_color(state),
                count=counts.get(f"{PENDING_PREFIX}{state}", 0),
                css_class=f"submission-state-{state}",
            )
            for state, label in base
        ]
        return choices

    def filter(self, qs, value):
        return filter_submissions_by_state(qs, value)


class TrackFilter(ModelMultiChoiceFilter):
    def get_queryset(self):
        limit_tracks = self.context.get("limit_tracks")
        if limit_tracks and isinstance(limit_tracks, (list, tuple, set, frozenset)):
            tracks = self.event.tracks.filter(pk__in=limit_tracks)
        else:
            tracks = self.event.tracks.all()
        return annotate_submission_count(tracks).order_by("-submission_count")

    def is_available(self):
        if len(self.choices) <= 1 and self.event and self.event.cfp.require_track:
            return False
        return bool(self.choices)


def submission_search(qs, query, fulltext=False, context=None):
    return search_submissions(
        qs,
        query,
        can_view_speakers=context.get("can_view_speakers", True),
        fulltext=fulltext,
    )


def question_filters(context, *, target, answer_field):
    """One QuestionAnswerFilter per question."""
    event, user = context.event, context.user
    if not event or not user:
        return []
    questions = (
        questions_for_user(event, user)
        .filter(target=target)
        .prefetch_related("options")
    )
    return [
        QuestionAnswerFilter(question=question, answer_field=answer_field)
        for question in questions
    ]


def submission_question_filters(context):
    return question_filters(
        context, target=QuestionTarget.SUBMISSION, answer_field="submission_id"
    )


class QuestionRoleFilter(ChoiceFilter):
    def filter(self, qs, value):
        return filter_submissions_by_speaker_role(qs, value)


def question_scope_filters(context):
    return [
        QuestionRoleFilter(
            name="role",
            label=_("Recipients"),
            choices=[
                FilterChoice("accepted", _("Accepted or confirmed speakers")),
                FilterChoice("confirmed", _("Confirmed speakers")),
            ],
            empty_label=phrases.base.all_choices,
        ),
        ModelChoiceFilter(
            name="track",
            label=_("Track"),
            empty_label=_("All tracks"),
            queryset=lambda bound: (
                bound.event.tracks.all() if bound.event.has_active_tracks else []
            ),
        ),
        ModelChoiceFilter(
            name="submission_type",
            label=_("Session type"),
            empty_label=_("All session types"),
            color_field="",
            queryset=lambda bound: bound.event.submission_types.all(),
        ),
    ]


class SignupStateFilter(MultiChoiceFilter):
    def get_choices(self):
        submission = self.context.get("submission")
        counts = (
            dict(
                submission.attendee_signups.values("state")
                .annotate(count=Count("state"))
                .values_list("state", "count")
            )
            if submission
            else {}
        )
        return [
            FilterChoice(
                value=state, label=str(label).capitalize(), count=counts.get(state, 0)
            )
            for state, label in AttendeeSignupStates.choices
        ]


def signup_filters(context):
    return [SignupStateFilter(name="state", label=_("Signup state"), with_counts=True)]


class ReviewCountFilter(TableFilter):
    control = RANGE
    multiple = False

    @property
    def max_count(self):
        return self.context.get("max_review_count") or 0

    def is_available(self):
        return self.max_count > 1

    def parse(self, data):
        raw = data.get(self.param) or ""
        if "," not in raw:
            return None
        return tuple(_as_count(part) for part in raw.split(",", maxsplit=1))

    def has_value(self, value):
        if not value:
            return False
        low, high = value
        return (low or 0) > 0 or (high is not None and high < self.max_count)

    def selected_values(self, value):
        low, high = value or (None, None)
        return [
            f"{low if low is not None else 0},{high if high is not None else self.max_count}"
        ]

    def filter(self, qs, value):
        low, high = value
        if low:
            qs = qs.filter(review_count__gte=low)
        if high is not None and high < self.max_count:
            qs = qs.filter(review_count__lte=high)
        return qs

    def get_pills(self, value):
        low, high = value
        return [
            FilterPill(
                param=self.param,
                value=self.selected_values(value)[0],
                label=_("Reviews: {low}–{high}").format(
                    low=low or 0, high=high if high is not None else self.max_count
                ),
            )
        ]


def _as_count(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def review_filters(context):
    return [ReviewCountFilter(name="review-count", label=_("Number of reviews"))]


class RequiresSignupFilter(BooleanFilter):
    def is_available(self):
        return bool(self.event and self.event.get_feature_flag("attendee_signup"))

    def filter(self, qs, value):
        return annotate_requires_signup(qs).filter(_annotated_requires_signup=value)


class PendingInvitationsFilter(BooleanFilter):
    def filter(self, qs, value):
        return qs.filter(invitations__isnull=not value).distinct()


def _scoped_submissions(bound):
    submissions = bound.event.submissions.all()
    if usable_states := bound.context.get("usable_states"):
        submissions = submissions.filter(state__in=usable_states)
    return submissions


def _locale_choices(bound):
    counts = submission_field_counts(_scoped_submissions(bound), "content_locale")
    return [
        FilterChoice(code, name, count=counts.get(code, 0))
        for code, name in bound.event.named_content_locales
    ]


def submission_filters(context):
    return [
        SearchFilter(search=submission_search, fulltext=True),
        SubmissionStateFilter(name="state", label=_("State"), with_counts=True),
        BooleanFilter(
            name="pending_state__isnull",
            label=_("Pending state changes"),
            yes_label=_("Without"),
            no_label=_("With"),
        ),
        ModelMultiChoiceFilter(
            name="submission_type",
            label=_("Session type"),
            min_choices=2,
            color_field="",
            with_counts=True,
            count_attr="submission_count",
            queryset=lambda bound: annotate_submission_count(
                bound.event.submission_types.all(),
                states=bound.context.get("usable_states"),
            ),
        ),
        TrackFilter(
            name="track",
            label=_("Track"),
            with_counts=True,
            count_attr="submission_count",
        ),
        ModelMultiChoiceFilter(
            name="tags",
            label=_("Tags"),
            with_counts=True,
            count_attr="submission_count",
            distinct=True,
            queryset=lambda bound: annotate_submission_count(bound.event.tags.all()),
        ),
        MultiChoiceFilter(
            name="content_locale",
            label=_("Language"),
            min_choices=2,
            with_counts=True,
            choices=_locale_choices,
        ),
        BooleanFilter(name="is_featured", label=_("Featured")),
        BooleanFilter(name="do_not_record", label=_("Do not record")),
        RequiresSignupFilter(name="requires_signup", label=_("Requires signup")),
        PendingInvitationsFilter(
            name="has_pending_invitations", label=_("Pending invitations")
        ),
    ]


def submission_list_filters(context):
    return [*submission_filters(context), *submission_question_filters(context)]


def review_list_filters(context):
    return [
        *submission_filters(context),
        *review_filters(context),
        *submission_question_filters(context),
    ]
