# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables.filters import (
    BooleanFilter,
    FilterChoice,
    ModelMultiChoiceFilter,
    SearchFilter,
    SegmentedChoiceFilter,
)
from pretalx.common.text.phrases import phrases
from pretalx.person.domain.queries.profile import filter_by_accepted_role
from pretalx.submission.domain.queries.submission import speaker_search_q
from pretalx.submission.enums import QuestionTarget
from pretalx.submission.interfaces.filters import question_filters


class RoleFilter(SegmentedChoiceFilter):
    def __init__(self, **kwargs):
        kwargs.setdefault("name", "role")
        kwargs.setdefault("label", _("Role"))
        kwargs.setdefault(
            "choices",
            [
                FilterChoice("speaker", phrases.schedule.speakers),
                FilterChoice("submitter", _("Submitters")),
            ],
        )
        kwargs.setdefault("empty_label", _("Any"))
        super().__init__(**kwargs)

    def filter(self, qs, value):
        return filter_by_accepted_role(qs, value)


class SessionsFilter(SegmentedChoiceFilter):
    def get_choices(self):
        return [FilterChoice("without", _("Without")), FilterChoice("all", _("Any"))]

    def parse(self, data):
        value = data.get(self.param) or ""
        if value in ("on", "true", "1"):
            return "all"
        if value in self.choices_by_value:
            return value
        return "with"

    def has_value(self, value):
        return bool(value)

    def is_default(self, value):
        return value == "with"

    def filter(self, qs, value):
        if value == "all":
            return qs
        if value == "without":
            return qs.filter(submission_count=0)
        return qs.filter(submission_count__gt=0)


class ArrivedFilter(BooleanFilter):
    def is_available(self):
        return bool(self.context.get("filter_arrival"))


def speaker_search(qs, query, fulltext=False, context=None):
    search = speaker_search_q(query)
    if fulltext:
        search |= Q(biography__icontains=query)
    return qs.filter(search)


def user_search(qs, query, fulltext=False, context=None):
    return qs.filter(Q(name__icontains=query) | Q(email__icontains=query))


def speaker_question_filters(context):
    return question_filters(
        context, target=QuestionTarget.SPEAKER, answer_field="speaker_id"
    )


def speaker_filters(context):
    return [
        SearchFilter(search=speaker_search, fulltext=True),
        RoleFilter(),
        SessionsFilter(name="sessionless", label=_("Sessions"), empty_label=_("With")),
        ArrivedFilter(
            name="arrived",
            field="has_arrived",
            label=_("Arrival"),
            yes_label=_("Marked as arrived"),
            no_label=_("Not yet arrived"),
        ),
        BooleanFilter(
            name="managed",
            field="user__isnull",
            label=_("Account"),
            yes_label=_("Managed"),
            no_label=_("Self-managed"),
        ),
    ]


def speaker_list_filters(context):
    return [*speaker_filters(context), *speaker_question_filters(context)]


def user_speaker_filters(context):
    return [
        SearchFilter(search=user_search),
        RoleFilter(),
        ModelMultiChoiceFilter(
            name="events",
            label=_("Events"),
            field="profiles__event",
            min_choices=2,
            color_field="",
            queryset=lambda bound: bound.context.get("events") or [],
        ),
    ]
