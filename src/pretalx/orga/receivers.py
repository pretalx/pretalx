# SPDX-FileCopyrightText: 2022-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.dispatch import receiver

from pretalx.agenda.signals import html_above_session_pages, html_below_session_pages
from pretalx.common.signals import register_exportable_tables
from pretalx.orga.tables.cfp import (
    ReviewerQuestionTable,
    SpeakerQuestionTable,
    SubmissionQuestionTable,
    SubmissionTypeTable,
    SubmitterAccessCodeTable,
    TrackTable,
)
from pretalx.orga.tables.feedback import FeedbackTable
from pretalx.orga.tables.mail import MailTemplateTable, OutboxMailTable, SentMailTable
from pretalx.orga.tables.review import ReviewExportTable
from pretalx.orga.tables.schedule import RoomTable
from pretalx.orga.tables.speaker import SpeakerInformationTable, SpeakerTable
from pretalx.orga.tables.submission import ReviewTable, SubmissionTable, TagTable


@receiver(html_above_session_pages, dispatch_uid="html_above_sessions_settings")
def add_html_above_session_pages(sender, request, submission, **kwargs):
    from pretalx.common.templatetags.rich_text import rich_text  # noqa: PLC0415 -- receiver

    text = request.event.display_settings.get("texts", {}).get(
        "agenda_session_above", ""
    )
    if text:
        return rich_text(text)
    return ""


@receiver(html_below_session_pages, dispatch_uid="html_above_sessions_settings")
def add_html_below_session_pages(sender, request, submission, **kwargs):
    from pretalx.common.templatetags.rich_text import rich_text  # noqa: PLC0415 -- receiver

    text = request.event.display_settings.get("texts", {}).get(
        "agenda_session_below", ""
    )
    if text:
        return rich_text(text)
    return ""


@receiver(register_exportable_tables, dispatch_uid="exportable_tables_core")
def register_core_exportable_tables(sender, **kwargs):
    return [
        SubmissionTable,
        ReviewTable,
        ReviewExportTable,
        SpeakerTable,
        OutboxMailTable,
        SentMailTable,
        MailTemplateTable,
        FeedbackTable,
        SubmitterAccessCodeTable,
        TrackTable,
        SubmissionTypeTable,
        TagTable,
        RoomTable,
        SubmissionQuestionTable,
        SpeakerQuestionTable,
        ReviewerQuestionTable,
        SpeakerInformationTable,
    ]
