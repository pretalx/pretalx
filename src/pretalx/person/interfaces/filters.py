# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables.filters import (
    BooleanFilter,
    ChoiceFilter,
    FilterChoice,
    ModelMultiChoiceFilter,
    SearchFilter,
)
from pretalx.common.text.phrases import phrases
from pretalx.person.domain.queries.profile import filter_by_accepted_role
from pretalx.submission.domain.queries.submission import speaker_search_q
from pretalx.submission.enums import QuestionTarget
from pretalx.submission.interfaces.filters import question_filters

ROLE_CHOICES = (
    FilterChoice("speaker", phrases.schedule.speakers),
    FilterChoice("submitter", _("Non-accepted submitters")),
)


class RoleFilter(ChoiceFilter):
    def filter(self, qs, value):
        return filter_by_accepted_role(qs, value)


class ManagedFilter(ChoiceFilter):
    def filter(self, qs, value):
        return qs.filter(user__isnull=(value == "managed"))


class SessionsFilter(ChoiceFilter):
    def get_choices(self):
        return [
            FilterChoice("without", _("Only without sessions")),
            FilterChoice("all", _("With and without sessions")),
        ]

    def parse(self, data):
        value = data.get(self.param) or ""
        if value in ("on", "true", "1"):
            return "all"
        if value in self.choices_by_value:
            return value
        return "with"

    def has_value(self, value):
        return value in ("with", "without")

    def is_default(self, value):
        return value == "with"

    def filter(self, qs, value):
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
        RoleFilter(
            name="role",
            label=_("Role"),
            choices=list(ROLE_CHOICES),
            empty_label=_("Submitters and speakers"),
        ),
        SessionsFilter(
            name="sessionless", label=_("Sessions"), empty_label=_("Only with sessions")
        ),
        ArrivedFilter(
            name="arrived",
            field="has_arrived",
            label=_("Arrival"),
            yes_label=_("Marked as arrived"),
            no_label=_("Not yet arrived"),
        ),
        ManagedFilter(
            name="managed",
            label=_("Account"),
            choices=[
                FilterChoice("managed", _("Managed speakers only")),
                FilterChoice("self-managed", _("Self-managed speakers only")),
            ],
            empty_label=_("Managed and self-managed"),
        ),
    ]


def speaker_list_filters(context):
    return [*speaker_filters(context), *speaker_question_filters(context)]


class UserRoleFilter(RoleFilter):
    def parse(self, data):
        value = data.get(self.param) or ""
        if value == "speaker" or value in self.choices_by_value:
            return value
        return "speaker"

    def has_value(self, value):
        return value in ("speaker", "submitter")

    def is_default(self, value):
        return value == "speaker"


def user_speaker_filters(context):
    return [
        SearchFilter(search=user_search),
        UserRoleFilter(
            name="role",
            label=_("Role"),
            choices=[
                FilterChoice("submitter", _("Non-accepted submitters")),
                FilterChoice("all", phrases.base.all_choices),
            ],
            empty_label=phrases.schedule.speakers,
        ),
        ModelMultiChoiceFilter(
            name="events",
            label=_("Events"),
            field="profiles__event",
            min_choices=2,
            color_field="",
            queryset=lambda bound: bound.context.get("events") or [],
        ),
    ]
