# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy as _n

from pretalx.common.tables import DateTimeColumn, PretalxTable, SortableColumn
from pretalx.common.templatetags.rich_text import render_markdown
from pretalx.person.models.profile import speaker_name_expression
from pretalx.submission.domain.queries.submission import submissions_for_user
from pretalx.submission.models import Feedback


class FeedbackTable(PretalxTable):
    primary_column = "talk"

    talk = SortableColumn(
        verbose_name=_n("Session", "Sessions", 1),
        accessor="talk__title",
        order_by=Lower("talk__title"),
        linkify=lambda record: record.talk.orga_urls.feedback,
    )
    review = tables.Column(verbose_name=_("Feedback"), orderable=False)
    speaker = SortableColumn(
        verbose_name=_("Speaker"),
        order_by={"speaker": Lower(speaker_name_expression(prefix="speaker__"))},
    )
    rating = tables.Column(
        verbose_name=_("Rating"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric text-center"}},
        initial_sort_descending=True,
    )
    created = DateTimeColumn()

    default_columns = ("talk", "review", "speaker")

    def __init__(self, *args, include_talk=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.exclude = list(self.exclude)
        if not include_talk:
            self.exclude.append("talk")

    @classmethod
    def base_queryset(cls, event, user):
        return (
            Feedback.objects.filter(talk__in=submissions_for_user(event, user))
            .select_related("talk__event", "speaker", "speaker__user")
            .order_by("-created", "-pk")
        )

    class Meta:
        model = Feedback
        fields = ()

    def render_review(self, record):
        return render_markdown(record.review or "")

    def render_speaker(self, value):
        return value.get_display_name()


class SubmissionFeedbackTable(FeedbackTable):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("include_talk", False)
        super().__init__(*args, **kwargs)
