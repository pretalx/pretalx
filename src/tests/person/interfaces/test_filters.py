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
        SpeakerProfile.objects.filter(event=event), event=event
    )


def speakers_with_and_without_sessions(event):
    with_session = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(with_session)
    return with_session, SpeakerFactory(event=event)


def test_sessionless_speakers_are_hidden_by_default():
    event = EventFactory()
    with_session, _without = speakers_with_and_without_sessions(event)

    filterset = build(speaker_filters, event=event)

    assert list(filterset.filter(profiles(event))) == [with_session]


def test_the_default_survives_another_filter_being_set():
    event = EventFactory()
    with_session, _without = speakers_with_and_without_sessions(event)

    filterset = build(speaker_filters, "managed=false", event=event)

    assert list(filterset.filter(profiles(event))) == [with_session]


def test_sessionless_speakers_can_be_shown_on_their_own():
    event = EventFactory()
    _with_session, without = speakers_with_and_without_sessions(event)

    filterset = build(speaker_filters, "sessionless=without", event=event)

    assert list(filterset.filter(profiles(event))) == [without]
    assert [pill.label for pill in filterset.pills] == ["Sessions: Without"]


def test_sessionless_speakers_can_be_shown_alongside_the_rest():
    event = EventFactory()
    with_session, without = speakers_with_and_without_sessions(event)

    filterset = build(speaker_filters, "sessionless=all", event=event)

    assert set(filterset.filter(profiles(event))) == {with_session, without}
    assert [pill.label for pill in filterset.pills] == ["Sessions: Any"]


def test_a_legacy_link_still_means_show_them_all():
    event = EventFactory()
    with_session, without = speakers_with_and_without_sessions(event)

    filterset = build(speaker_filters, "sessionless=on", event=event)

    assert set(filterset.filter(profiles(event))) == {with_session, without}


def test_arrival_filter_only_appears_where_arrivals_are_tracked():
    event = EventFactory()

    def facet_names(filterset):
        return [f.name for f in filterset.facets]

    assert "arrived" not in facet_names(build(speaker_filters, event=event))
    assert "arrived" in facet_names(
        build(speaker_filters, event=event, filter_arrival=True)
    )


def test_the_default_does_not_claim_active_filtering():
    event = EventFactory()
    speakers_with_and_without_sessions(event)

    pristine = build(speaker_filters, event=event)
    pristine.filter(profiles(event))

    assert pristine.is_active is False
    assert pristine.total_count is None
    assert pristine.pills == []


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


def test_cross_event_search_matches_name_and_email():
    event = EventFactory()
    speaker = SpeakerFactory(event=event, user__name="Needle Person")
    SpeakerFactory(event=event, user__name="Someone Else")

    filterset = build(user_speaker_filters, "q=needle", events=[event])
    users = annotate_user_submission_counts(
        User.objects.filter(profiles__event=event), events=[event]
    )

    assert list(filterset.filter(users)) == [speaker.user]


def test_cross_event_role_filters_like_the_event_level_list():
    event = EventFactory()
    accepted = SpeakerFactory(event=event, user__name="Needle Speaker")
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    submission.speakers.add(accepted)
    submitter = SpeakerFactory(event=event, user__name="Needle Submitter")

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
