# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils.timezone import now

from pretalx.person.rules import (
    can_mark_speakers_arrived,
    can_view_information,
    is_administrator,
    is_only_reviewer,
    is_reviewer,
)
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("is_admin", "expected"), ((True, True), (False, False)), ids=["admin", "non_admin"]
)
def test_is_administrator_matches_admin_flag(is_admin, expected):
    user = UserFactory(is_administrator=is_admin)
    assert is_administrator(user, None) is expected


def test_is_administrator_returns_false_for_none():
    assert is_administrator(None, None) is False


def test_is_reviewer_returns_true_for_reviewer():
    event = EventFactory()
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    info = SpeakerInformationFactory(event=event)

    assert is_reviewer(user, info) is True


def test_is_reviewer_returns_false_for_non_reviewer():
    event = EventFactory()
    user = UserFactory()

    info = SpeakerInformationFactory(event=event)

    assert is_reviewer(user, info) is False


@pytest.mark.parametrize("user", (None, AnonymousUser()), ids=["none", "anonymous"])
def test_is_reviewer_returns_false_for_invalid_user(user):
    event = EventFactory()
    info = SpeakerInformationFactory(event=event)
    assert is_reviewer(user, info) is False


@pytest.mark.parametrize("obj", (None, object()), ids=["none_obj", "obj_without_event"])
def test_is_reviewer_returns_false_for_invalid_obj(obj):
    user = UserFactory()
    assert is_reviewer(user, obj) is False


@pytest.mark.parametrize(
    ("team_kwargs", "expected"),
    (
        ({"is_reviewer": True, "can_change_submissions": False}, True),
        (
            {
                "is_reviewer": True,
                "can_change_submissions": False,
                "can_change_event_settings": True,
            },
            True,
        ),
        ({"is_reviewer": True, "can_change_submissions": True}, False),
        ({"is_reviewer": False, "can_change_submissions": True}, False),
    ),
    ids=[
        "only_reviewer",
        "reviewer_with_unrelated_permission",
        "can_change_submissions",
        "not_reviewer",
    ],
)
def test_is_only_reviewer(team_kwargs, expected):
    event = EventFactory()
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, **team_kwargs)
    team.members.add(user)

    info = SpeakerInformationFactory(event=event)

    assert is_only_reviewer(user, info) is expected


def test_is_only_reviewer_returns_false_for_anonymous():
    event = EventFactory()
    info = SpeakerInformationFactory(event=event)

    assert is_only_reviewer(AnonymousUser(), info) is False


@pytest.mark.parametrize(
    ("from_delta", "to_delta", "expected"),
    ((0, 2, True), (10, 12, False), (-10, -5, False)),
    ids=["within_window", "before_window", "after_window"],
)
def test_can_mark_speakers_arrived_respects_event_window(
    from_delta, to_delta, expected
):
    """Window is (date_from - 3 days) through date_to."""
    today = now().date()
    event = EventFactory(
        date_from=today + dt.timedelta(days=from_delta),
        date_to=today + dt.timedelta(days=to_delta),
    )
    info = SpeakerInformationFactory(event=event)

    assert can_mark_speakers_arrived(None, info) is expected


def test_can_view_information_delegates_to_information_for_user():
    """The rule is a thin wrapper; full coverage lives with ``information_for_user``."""
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    visible = SpeakerInformationFactory(event=event, target_group="submitters")
    hidden = SpeakerInformationFactory(event=event, target_group="confirmed")

    assert can_view_information(speaker.user, visible) is True
    assert can_view_information(speaker.user, hidden) is False
