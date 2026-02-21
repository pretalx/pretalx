# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import (
    DateTimeColumn,
    PretalxTable,
    SortableColumn,
)
from pretalx.common.templatetags.rich_text import render_markdown
from pretalx.submission.models import Feedback


class FeedbackTable(PretalxTable):
    talk = SortableColumn(
        verbose_name=_("Session"),
        accessor="talk__title",
        order_by=Lower("talk__title"),
        linkify=lambda record: record.talk.orga_urls.feedback,
    )
    review = tables.Column(
        verbose_name=_("Feedback"),
        orderable=False,
    )
    speaker = tables.Column(
        verbose_name=_("Speaker"),
        accessor="speaker__user__name",
        orderable=False,
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
            self.empty_text = _("There has been no feedback for this session yet.")
        else:
            self.empty_text = _(
                "There has been no feedback for sessions in this event yet."
            )

    class Meta:
        model = Feedback
        fields = ()

    def render_review(self, record):
        return render_markdown(record.review or "")
