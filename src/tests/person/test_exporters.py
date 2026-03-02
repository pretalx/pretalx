# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import csv
from io import StringIO

import pytest
from django_scopes import scope

from pretalx.person.exporters import CSVSpeakerExporter
from pretalx.submission.models import SubmissionStates
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def exporter(event):
    return CSVSpeakerExporter(event)


def _parse_csv(csv_text):
    reader = csv.DictReader(StringIO(csv_text))
    return list(reader)


def test_csv_speaker_exporter_class_attributes(exporter):
    assert str(exporter.verbose_name) == "Speaker CSV"
    assert exporter.public is False
    assert exporter.icon == "fa-users"
    assert exporter.identifier == "speakers.csv"
    assert exporter.cors == "*"
    assert exporter.group == "speaker"


def test_csv_speaker_exporter_get_csv_data_fieldnames(event, exporter):
    with scope(event=event):
        fieldnames, _ = exporter.get_csv_data(request=None)

    assert fieldnames == ["name", "email", "confirmed"]


def test_csv_speaker_exporter_get_csv_data_empty_when_no_submissions(event, exporter):
    with scope(event=event):
        _, data = exporter.get_csv_data(request=None)

    assert data == []


@pytest.mark.parametrize(
    ("state", "expected_confirmed"),
    ((SubmissionStates.ACCEPTED, "False"), (SubmissionStates.CONFIRMED, "True")),
    ids=("accepted", "confirmed"),
)
def test_csv_speaker_exporter_get_csv_data_includes_speaker(
    event, exporter, state, expected_confirmed
):
    """Speakers with accepted or confirmed submissions appear in the export."""
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=state)
    submission.speakers.add(speaker)

    with scope(event=event):
        _, data = exporter.get_csv_data(request=None)

    assert len(data) == 1
    assert data[0]["name"] == speaker.get_display_name()
    assert data[0]["email"] == speaker.user.email
    assert data[0]["confirmed"] == expected_confirmed


@pytest.mark.parametrize(
    "state",
    (
        SubmissionStates.SUBMITTED,
        SubmissionStates.REJECTED,
        SubmissionStates.CANCELED,
        SubmissionStates.WITHDRAWN,
        SubmissionStates.DRAFT,
    ),
)
def test_csv_speaker_exporter_get_csv_data_excludes_non_accepted_states(
    event, exporter, state
):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=state)
    submission.speakers.add(speaker)

    with scope(event=event):
        _, data = exporter.get_csv_data(request=None)

    assert data == []


def test_csv_speaker_exporter_get_csv_data_confirmed_true_with_mixed_states(
    event, exporter
):
    """A speaker with both accepted and confirmed submissions shows confirmed=True."""
    speaker = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    accepted.speakers.add(speaker)
    confirmed.speakers.add(speaker)

    with scope(event=event):
        _, data = exporter.get_csv_data(request=None)

    assert len(data) == 1
    assert data[0]["confirmed"] == "True"


def test_csv_speaker_exporter_get_csv_data_multiple_speakers(event, exporter):
    speaker1 = SpeakerFactory(event=event)
    speaker2 = SpeakerFactory(event=event)
    sub1 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    sub1.speakers.add(speaker1)
    sub2.speakers.add(speaker2)

    with scope(event=event):
        _, data = exporter.get_csv_data(request=None)

    assert len(data) == 2
    exported_emails = {row["email"] for row in data}
    assert exported_emails == {speaker1.user.email, speaker2.user.email}


def test_csv_speaker_exporter_get_csv_data_excludes_other_event_speakers(
    event, exporter
):
    """Speakers from a different event are not included."""
    other_event = EventFactory()
    other_speaker = SpeakerFactory(event=other_event)
    other_sub = SubmissionFactory(event=other_event, state=SubmissionStates.ACCEPTED)
    other_sub.speakers.add(other_speaker)

    with scope(event=event):
        _, data = exporter.get_csv_data(request=None)

    assert data == []


def test_csv_speaker_exporter_get_data_returns_valid_csv(event, exporter):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    submission.speakers.add(speaker)

    with scope(event=event):
        csv_output = exporter.get_data(request=None)

    rows = _parse_csv(csv_output)
    assert len(rows) == 1
    assert rows[0]["name"] == speaker.get_display_name()
    assert rows[0]["email"] == speaker.user.email
    assert rows[0]["confirmed"] == "False"


def test_csv_speaker_exporter_get_data_empty_has_header_only(event, exporter):
    """Even with no data, get_data returns a CSV with a header row."""
    with scope(event=event):
        csv_output = exporter.get_data(request=None)

    rows = _parse_csv(csv_output)
    assert rows == []
    assert "name,email,confirmed" in csv_output


def test_csv_speaker_exporter_render_returns_tuple(event, exporter):
    with scope(event=event):
        filename, content_type, data = exporter.render(request=None)

    assert filename.startswith(f"{event.slug}-speakers-")
    assert filename.endswith(".csv")
    assert content_type == "text/plain"
    assert "name,email,confirmed" in data
