# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import csv
from io import StringIO

import pytest
from django_scopes import scope

from pretalx.person.interfaces.exporters import CSVSpeakerExporter
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def exporter(event):
    return CSVSpeakerExporter(ScheduleFactory.build(event=event))


def _parse_csv(csv_text):
    # CSV exports are prefixed with a UTF-8 BOM so Excel detects the
    # encoding; strip it before parsing so the first column name stays clean.
    csv_text = csv_text.removeprefix("﻿")
    reader = csv.DictReader(StringIO(csv_text))
    return list(reader)


def test_csv_speaker_exporter_empty_event(event, exporter):
    with scope(event=event):
        fieldnames, data = exporter.get_csv_data(request=None)
        csv_output = exporter.get_data(request=None)
        filename, content_type, rendered = exporter.render(request=None)

    assert fieldnames == ["name", "email", "confirmed"]
    assert data == []
    assert _parse_csv(csv_output) == []
    assert "name,email,confirmed" in csv_output
    assert filename.startswith(f"{event.slug}-speakers-")
    assert filename.endswith(".csv")
    assert content_type == "text/plain"
    assert "name,email,confirmed" in rendered


def test_csv_speaker_exporter_lists_accepted_and_standalone_speakers(event, exporter):
    accepted = SpeakerFactory(event=event, user__email="accepted@example.com")
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED).speakers.add(
        accepted
    )
    confirmed = SpeakerFactory(event=event, user__email="confirmed@example.com")
    SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED).speakers.add(
        confirmed
    )
    mixed = SpeakerFactory(event=event, user__email="mixed@example.com")
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED).speakers.add(mixed)
    SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED).speakers.add(mixed)
    SpeakerFactory(
        event=event,
        user=None,
        origin="orga",
        name="Standalone",
        email="standalone@example.com",
    )
    SpeakerFactory(event=event, origin="cfp")
    for state in (
        SubmissionStates.SUBMITTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
        SubmissionStates.DRAFT,
    ):
        SubmissionFactory(event=event, state=state).speakers.add(
            SpeakerFactory(event=event)
        )
    other_event = EventFactory()
    SubmissionFactory(event=other_event, state=SubmissionStates.ACCEPTED).speakers.add(
        SpeakerFactory(event=other_event)
    )

    with scope(event=event):
        _, data = exporter.get_csv_data(request=None)
        rows = _parse_csv(exporter.get_data(request=None))

    expected = [
        {
            "name": accepted.get_display_name(),
            "email": "accepted@example.com",
            "confirmed": "False",
        },
        {
            "name": confirmed.get_display_name(),
            "email": "confirmed@example.com",
            "confirmed": "True",
        },
        {
            "name": mixed.get_display_name(),
            "email": "mixed@example.com",
            "confirmed": "True",
        },
        {"name": "Standalone", "email": "standalone@example.com", "confirmed": "False"},
    ]
    assert sorted(data, key=lambda row: row["email"]) == expected
    assert sorted(rows, key=lambda row: row["email"]) == expected
