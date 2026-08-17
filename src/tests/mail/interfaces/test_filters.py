# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import QueryDict

from pretalx.common.tables.filters import FilterContext, TableFilterSet
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.interfaces.filters import queued_mail_filters
from tests.factories.event import EventFactory
from tests.factories.mail import QueuedMailFactory
from tests.factories.submission import SubmissionFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def build(event, sent=False, query=""):
    context = FilterContext(event=event, sent=sent)
    return TableFilterSet(
        queued_mail_filters(context), data=QueryDict(query), context=context
    )


def facet_names(filterset):
    return [f.name for f in filterset.facets]


def test_sent_list_has_no_status_filter():
    filterset = build(EventFactory(), sent=True)

    assert "status" not in filterset.filters


def test_status_filter_dropped_without_failures():
    filterset = build(EventFactory(), sent=False)

    assert "status" not in facet_names(filterset)


def test_status_filter_offers_pending_and_failed():
    event = EventFactory()
    QueuedMailFactory(
        event=event,
        state=QueuedMailStates.DRAFT,
        error_data={"error": "SMTP failed", "type": "Exception"},
    )
    QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)

    filterset = build(event, sent=False)

    assert [c.value for c in filterset.filters["status"].choices] == ["draft", "failed"]


def test_track_filter_dropped_without_tracks():
    event = EventFactory(feature_flags={"use_tracks": False})

    assert "track" not in facet_names(build(event, sent=False))


def test_track_filter_offers_event_tracks():
    event = EventFactory()
    track = TrackFactory(event=event)

    filterset = build(event, sent=False)

    assert [c.value for c in filterset.filters["track"].choices] == [str(track.pk)]


def test_filter_by_status():
    event = EventFactory()
    failed = QueuedMailFactory(
        event=event,
        state=QueuedMailStates.DRAFT,
        error_data={"error": "fail", "type": "Exception"},
    )
    QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)

    filterset = build(event, sent=False, query="status=failed")
    qs = event.queued_mails.filter(state=QueuedMailStates.DRAFT).with_computed_state()

    assert list(filterset.filter(qs)) == [failed]


def test_filter_by_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    mail_with_track = QueuedMailFactory(event=event)
    mail_with_track.submissions.add(submission)
    QueuedMailFactory(event=event)

    filterset = build(event, sent=False, query=f"track={track.pk}")

    assert list(filterset.filter(event.queued_mails.all())) == [mail_with_track]


def test_no_filters_leaves_queryset_alone():
    event = EventFactory()
    mail = QueuedMailFactory(event=event)

    filterset = build(event, sent=True)

    assert list(filterset.filter(event.queued_mails.all())) == [mail]


def test_track_counts_only_sent_mails():
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    sent_mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    sent_mail.submissions.add(submission)
    draft_mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    draft_mail.submissions.add(SubmissionFactory(event=event, track=other_track))

    filterset = build(event, sent=True)
    counts = {t.pk: t.mail_count for t in filterset.filters["track"].get_queryset()}

    assert counts[track.pk] == 1
    assert counts[other_track.pk] == 0


def test_search_matches_subject_and_recipient():
    event = EventFactory()
    match = QueuedMailFactory(event=event, subject="Room change")
    QueuedMailFactory(event=event, subject="Unrelated")

    filterset = build(event, sent=False, query="q=room")

    assert list(filterset.filter(event.queued_mails.all())) == [match]


def test_filters_are_empty_without_an_event():
    filterset = build(None, sent=False)

    assert facet_names(filterset) == []
    assert filterset.search is not None
