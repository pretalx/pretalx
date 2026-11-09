# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.submission import SubmissionTable
from tests.factories import TableExportFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_table_export_config_table_class_and_urls(event):
    export = TableExportFactory(
        event=event,
        name="Talks",
        columns=["title"],
        ordering=["-title"],
        filters={"state": ["accepted"]},
        serializer_options={"list_delimiter": "comma"},
    )
    stale = TableExportFactory(event=event, table="GoneTable")

    assert str(export) == "Talks"
    assert export.table_class is SubmissionTable
    assert export.log_parent == event
    assert export.config == {
        "table": "SubmissionTable",
        "columns": ["title"],
        "ordering": ["-title"],
        "filters": {"state": ["accepted"]},
        "serializer": "csv",
        "serializer_options": {"list_delimiter": "comma"},
    }
    assert export.urls.edit == f"{event.orga_urls.exports}{export.pk}/"
    assert export.urls.delete == f"{event.orga_urls.exports}{export.pk}/delete/"
    assert export.urls.run == f"{event.orga_urls.exports}{export.pk}/run/"
    assert export.urls.view == f"{event.orga_urls.exports}{export.pk}/view/"
    assert stale.table_class is None


def test_table_export_view_data_url_only_for_tables_with_a_list(event):
    orga = event.orga_urls
    cfp = event.cfp.urls
    expected = {
        "SubmissionTable": orga.submissions,
        "ReviewTable": orga.reviews,
        "ReviewExportTable": None,
        "SpeakerTable": orga.speakers,
        "OutboxMailTable": orga.outbox,
        "SentMailTable": orga.sent_mails,
        "MailTemplateTable": orga.mail_templates,
        "FeedbackTable": orga.feedback,
        "SubmitterAccessCodeTable": cfp.access_codes,
        "TrackTable": cfp.tracks,
        "SubmissionTypeTable": cfp.types,
        "TagTable": orga.tags,
        "RoomTable": orga.room_settings,
        "SubmissionQuestionTable": cfp.questions,
        "SpeakerQuestionTable": cfp.questions,
        "ReviewerQuestionTable": None,
        "SpeakerInformationTable": orga.information,
        "GoneTable": None,
    }
    exports = {
        table: TableExportFactory(event=event, table=table) for table in expected
    }

    assert {
        table: export.table_class and export.table_class.get_list_url(event)
        for table, export in exports.items()
    } == expected
    assert {table: export.view_data_url for table, export in exports.items()} == {
        table: url and exports[table].urls.view for table, url in expected.items()
    }
