# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.contrib.auth.models import AnonymousUser

from pretalx.event.domain.queries.event import (
    events_for_custom_domain,
    events_for_user,
    speaker_events_for_user,
)
from pretalx.event.models import Event
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_events_for_user_anonymous_returns_only_public_events():
    public_event = EventFactory(is_public=True)
    EventFactory(is_public=False)
    user = AnonymousUser()

    result = list(events_for_user(user))

    assert result == [public_event]


def test_events_for_user_authenticated_returns_public_and_permitted():
    organiser = OrganiserFactory()
    public_event = EventFactory(is_public=True, organiser=organiser)
    private_event = EventFactory(is_public=False, organiser=organiser)
    EventFactory(is_public=False)  # no access
    user = UserFactory()
    team = TeamFactory(organiser=organiser, all_events=True)
    team.members.add(user)

    result = set(events_for_user(user))

    assert result == {public_event, private_event}


def test_events_for_user_uses_provided_queryset():
    organiser = OrganiserFactory()
    EventFactory(is_public=True, organiser=organiser)
    other_event = EventFactory(is_public=True)
    user = AnonymousUser()

    queryset = Event.objects.filter(organiser=other_event.organiser)
    result = list(events_for_user(user, queryset=queryset))

    assert result == [other_event]


def test_events_for_user_orders_by_date_from_descending():
    e_old = EventFactory(is_public=True, date_from=dt.date(2020, 1, 1))
    e_new = EventFactory(is_public=True, date_from=dt.date(2025, 6, 1))
    user = AnonymousUser()

    result = list(events_for_user(user))

    assert result == [e_new, e_old]


def test_speaker_events_for_user_returns_only_speaker_events():
    speaker_event = EventFactory()
    EventFactory()  # event without speakers
    user = UserFactory()
    speaker = SpeakerFactory(event=speaker_event, user=user)
    submission = SubmissionFactory(event=speaker_event)
    submission.speakers.add(speaker)

    result = list(speaker_events_for_user(user))

    assert result == [speaker_event]


def test_speaker_events_for_user_deduplicates_multiple_submissions():
    """A user with multiple submissions on the same event appears only once."""
    event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    SubmissionFactory(event=event).speakers.add(speaker)
    SubmissionFactory(event=event).speakers.add(speaker)

    result = list(speaker_events_for_user(user))

    assert result == [event]


def test_speaker_events_for_user_orders_by_date_from_descending():
    e_old = EventFactory(date_from=dt.date(2020, 1, 1))
    e_new = EventFactory(date_from=dt.date(2025, 6, 1))
    user = UserFactory()
    for ev in (e_old, e_new):
        speaker = SpeakerFactory(event=ev, user=user)
        SubmissionFactory(event=ev).speakers.add(speaker)

    result = list(speaker_events_for_user(user))

    assert result == [e_new, e_old]


def test_speaker_events_for_user_empty_when_user_has_no_submissions():
    EventFactory()
    user = UserFactory()

    assert list(speaker_events_for_user(user)) == []


def test_events_for_custom_domain_matches_exact_host():
    matching = EventFactory(custom_domain="https://custom.example.com")
    EventFactory(custom_domain="https://other.example.com")
    EventFactory(custom_domain=None)

    result = list(events_for_custom_domain("https", "custom.example.com"))

    assert result == [matching]


def test_events_for_custom_domain_no_match_returns_empty_queryset():
    EventFactory(custom_domain="https://other.example.com")

    result = list(events_for_custom_domain("https", "missing.example.com"))

    assert result == []


def test_events_for_custom_domain_scheme_matters():
    """A http custom_domain does not match an https request and vice versa."""
    EventFactory(custom_domain="https://custom.example.com")

    result = list(events_for_custom_domain("http", "custom.example.com"))

    assert result == []


def test_events_for_custom_domain_matches_either_with_or_without_port():
    """When ``host`` has a port, events stored with just the bare domain
    also match (and the other way around)."""
    bare = EventFactory(custom_domain="https://custom.example.com")
    with_port = EventFactory(custom_domain="https://custom.example.com:8443")

    result = set(
        events_for_custom_domain(
            "https", "custom.example.com:8443", domain="custom.example.com"
        )
    )

    assert result == {bare, with_port}


def test_events_for_custom_domain_ignores_domain_when_equal_to_host():
    """``domain == host`` (no port) does not add a duplicate filter clause."""
    matching = EventFactory(custom_domain="https://custom.example.com")

    result = list(
        events_for_custom_domain(
            "https", "custom.example.com", domain="custom.example.com"
        )
    )

    assert result == [matching]


def test_events_for_custom_domain_orders_by_date_from_descending():
    e_old = EventFactory(
        custom_domain="https://custom.example.com", date_from=dt.date(2020, 1, 1)
    )
    e_new = EventFactory(
        custom_domain="https://custom.example.com", date_from=dt.date(2025, 6, 1)
    )

    result = list(events_for_custom_domain("https", "custom.example.com"))

    assert result == [e_new, e_old]
