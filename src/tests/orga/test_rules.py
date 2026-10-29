# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import types

import pytest

from pretalx.event.models import Event
from pretalx.orga.rules import can_view_speaker_names
from tests.factories import EventFactory, ReviewPhaseFactory, TeamFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("phase_kwargs", "team_hide_flags", "expected"),
    (
        ({"is_active": True, "can_see_speaker_names": True}, [False], True),
        ({"is_active": True, "can_see_speaker_names": True}, [True], False),
        ({"is_active": True, "can_see_speaker_names": False}, [False], False),
        ({"is_active": False}, [False], False),
        ({"is_active": True, "can_see_speaker_names": True}, [True, False], True),
        ({"is_active": True, "can_see_speaker_names": True}, [], True),
    ),
    ids=(
        "phase-allows",
        "team-forces-hide",
        "phase-disallows",
        "no-active-phase",
        "not-all-teams-hide",
        "not-on-reviewer-team",
    ),
)
def test_can_view_speaker_names(
    django_assert_num_queries, phase_kwargs, team_hide_flags, expected
):
    event = EventFactory()
    user = UserFactory()
    event.review_phases.all().delete()
    ReviewPhaseFactory(event=event, **phase_kwargs)
    for force_hide in team_hide_flags:
        team = TeamFactory(
            organiser=event.organiser,
            all_events=True,
            is_reviewer=True,
            force_hide_speaker_names=force_hide,
        )
        team.members.add(user)
    obj = types.SimpleNamespace(event=Event.objects.get(pk=event.pk))

    assert can_view_speaker_names(user, obj) is expected
    with django_assert_num_queries(0):
        assert can_view_speaker_names(user, obj) is expected
