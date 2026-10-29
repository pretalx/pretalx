# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import QueryDict

from pretalx.common.tables.filters import FilterContext, TableFilterSet
from pretalx.person.domain.queries.profile import (
    annotate_speaker_submission_counts,
    annotate_user_submission_counts,
)
from pretalx.person.interfaces.filters import (
    speaker_filters,
    speaker_question_filters,
    user_speaker_filters,
)
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.enums import SubmissionStates
from tests.factories.event import EventFactory
from tests.factories.person import SpeakerFactory
from tests.factories.submission import SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def build(filters, query="", **options):
    context = FilterContext(**options)
    return TableFilterSet(filters(context), data=QueryDict(query), context=context)


def profiles(event):
    return annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(event=event),
        event=event,
        submissions=event.submissions.all(),
    )


def speakers_with_and_without_sessions(event):
    with_session = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(with_session)
    return with_session, SpeakerFactory(event=event)


@pytest.mark.parametrize(
    ("query", "is_active", "pills"),
    (("", False, []), ("managed=false", True, ["Account: Self-managed"])),
    ids=("pristine", "other_filter"),
)
def test_sessionless_speakers_are_hidden_by_default_without_claiming_a_filter(
    query, is_active, pills
):
    event = EventFactory()
    with_session, _without = speakers_with_and_without_sessions(event)

    filterset = build(speaker_filters, query, event=event)

    assert list(filterset.filter(profiles(event))) == [with_session]
    assert filterset.is_active is is_active
    assert [pill.label for pill in filterset.pills] == pills


@pytest.mark.parametrize(
    ("query", "expected", "pills"),
    (
        ("sessionless=without", {"without"}, ["Sessions: Without"]),
        ("sessionless=all", {"with", "without"}, ["Sessions: All"]),
        ("sessionless=on", {"with", "without"}, ["Sessions: All"]),
    ),
    ids=("without", "all", "legacy_on"),
)
def test_sessionless_filter_values(query, expected, pills):
    event = EventFactory()
    with_session, without = speakers_with_and_without_sessions(event)
    speakers = {"with": with_session, "without": without}

    filterset = build(speaker_filters, query, event=event)

    assert set(filterset.filter(profiles(event))) == {speakers[n] for n in expected}
    assert [pill.label for pill in filterset.pills] == pills


def test_arrival_filter_only_appears_where_arrivals_are_tracked():
    event = EventFactory()

    def facet_names(filterset):
        return [f.name for f in filterset.facets]

    assert "arrived" not in facet_names(build(speaker_filters, event=event))
    assert "arrived" in facet_names(
        build(speaker_filters, event=event, filter_arrival=True)
    )


def test_managed_filter_splits_by_account():
    event = EventFactory()
    managed = SpeakerFactory(event=event, user=None)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(managed)
    self_managed = SpeakerFactory(event=event)
    other = SubmissionFactory(event=event)
    other.speakers.add(self_managed)

    filterset = build(speaker_filters, "managed=true", event=event)
    assert list(filterset.filter(profiles(event))) == [managed]

    filterset = build(speaker_filters, "managed=false", event=event)
    assert list(filterset.filter(profiles(event))) == [self_managed]


def test_cross_event_search_and_role_filters():
    event = EventFactory()
    accepted = SpeakerFactory(event=event, user__name="Needle Speaker")
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    submission.speakers.add(accepted)
    submitter = SpeakerFactory(event=event, user__name="Needle Submitter")
    SpeakerFactory(event=event, user__name="Someone Else")

    def filtered(query):
        users = annotate_user_submission_counts(
            User.objects.filter(profiles__event=event).order_by("name"), events=[event]
        )
        return list(build(user_speaker_filters, query, events=[event]).filter(users))

    assert filtered("q=needle") == [accepted.user, submitter.user]
    assert filtered("q=needle&role=speaker") == [accepted.user]
    assert filtered("q=needle&role=submitter") == [submitter.user]


def test_question_filters_need_an_event_and_a_user():
    assert speaker_question_filters(FilterContext()) == []
