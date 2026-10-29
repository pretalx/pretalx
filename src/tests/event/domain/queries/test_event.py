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


def test_events_for_user_anonymous_returns_public_events_newest_first():
    organiser = OrganiserFactory()
    e_old = EventFactory(
        is_public=True, organiser=organiser, date_from=dt.date(2020, 1, 1)
    )
    e_new = EventFactory(
        is_public=True, organiser=organiser, date_from=dt.date(2025, 6, 1)
    )
    EventFactory(is_public=False, organiser=organiser)
    other_event = EventFactory(is_public=True, date_from=dt.date(2010, 1, 1))
    user = AnonymousUser()

    assert list(events_for_user(user)) == [e_new, e_old, other_event]
    assert list(
        events_for_user(
            user, queryset=Event.objects.filter(organiser=other_event.organiser)
        )
    ) == [other_event]


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


def test_speaker_events_for_user_returns_distinct_speaker_events_newest_first():
    e_old = EventFactory(date_from=dt.date(2020, 1, 1))
    e_new = EventFactory(date_from=dt.date(2025, 6, 1))
    EventFactory()  # event without speakers
    user = UserFactory()
    for ev in (e_old, e_new):
        speaker = SpeakerFactory(event=ev, user=user)
        SubmissionFactory(event=ev).speakers.add(speaker)
        SubmissionFactory(event=ev).speakers.add(speaker)

    assert list(speaker_events_for_user(user)) == [e_new, e_old]
    assert list(speaker_events_for_user(UserFactory())) == []


def test_events_for_custom_domain_matches_scheme_and_host_newest_first():
    e_old = EventFactory(
        custom_domain="https://custom.example.com", date_from=dt.date(2020, 1, 1)
    )
    e_new = EventFactory(
        custom_domain="https://custom.example.com", date_from=dt.date(2025, 6, 1)
    )
    EventFactory(custom_domain="https://other.example.com")
    EventFactory(custom_domain=None)

    assert list(events_for_custom_domain("https", "custom.example.com")) == [
        e_new,
        e_old,
    ]
    assert list(events_for_custom_domain("http", "custom.example.com")) == []
    assert list(events_for_custom_domain("https", "missing.example.com")) == []


def test_events_for_custom_domain_matches_with_or_without_port():
    bare = EventFactory(custom_domain="https://custom.example.com")
    with_port = EventFactory(custom_domain="https://custom.example.com:8443")

    assert set(
        events_for_custom_domain(
            "https", "custom.example.com:8443", domain="custom.example.com"
        )
    ) == {bare, with_port}
    assert list(
        events_for_custom_domain(
            "https", "custom.example.com", domain="custom.example.com"
        )
    ) == [bare]
