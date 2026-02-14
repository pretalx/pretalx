# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_filters

from pretalx.submission.models import Answer


class AnswerFilterSet(django_filters.FilterSet):
    question = django_filters.NumberFilter(field_name="question_id")
    submission = django_filters.CharFilter(
        field_name="submission__code",
        lookup_expr="iexact",
    )
    speaker = django_filters.CharFilter(
        field_name="speaker__code",
        lookup_expr="iexact",
    )
    review = django_filters.NumberFilter(field_name="review_id")

    class Meta:
        model = Answer
        fields = ("question", "submission", "speaker", "review")
