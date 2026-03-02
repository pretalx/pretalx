# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import types

import pytest

from pretalx.event.models import Event
from pretalx.orga.rules import can_view_speaker_names
from tests.factories import EventFactory, ReviewPhaseFactory, TeamFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _make_obj(event):
    """Build a minimal object with a fresh .event (no cached_property stale data)."""
    fresh_event = Event.objects.get(pk=event.pk)
    return types.SimpleNamespace(event=fresh_event)


def test_can_view_speaker_names_true_when_phase_allows():
    """Reviewer can see names when active phase allows it and team doesn't force-hide."""
    event = EventFactory()
    user = UserFactory()
    event.review_phases.all().delete()
    ReviewPhaseFactory(event=event, is_active=True, can_see_speaker_names=True)
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        force_hide_speaker_names=False,
    )
    team.members.add(user)

    obj = _make_obj(event)
    assert can_view_speaker_names(user, obj) is True


def test_can_view_speaker_names_false_when_team_forces_hide():
    """All reviewer teams force-hiding speaker names overrides the phase setting."""
    event = EventFactory()
    user = UserFactory()
    event.review_phases.all().delete()
    ReviewPhaseFactory(event=event, is_active=True, can_see_speaker_names=True)
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        force_hide_speaker_names=True,
    )
    team.members.add(user)

    obj = _make_obj(event)
    assert can_view_speaker_names(user, obj) is False


def test_can_view_speaker_names_false_when_phase_disallows():
    """Even without team hiding, the phase setting is respected."""
    event = EventFactory()
    user = UserFactory()
    event.review_phases.all().delete()
    ReviewPhaseFactory(event=event, is_active=True, can_see_speaker_names=False)
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        force_hide_speaker_names=False,
    )
    team.members.add(user)

    obj = _make_obj(event)
    assert can_view_speaker_names(user, obj) is False


def test_can_view_speaker_names_false_when_no_active_phase():
    """Without an active review phase, speaker names are not visible."""
    event = EventFactory()
    user = UserFactory()
    event.review_phases.all().delete()
    ReviewPhaseFactory(event=event, is_active=False)
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        force_hide_speaker_names=False,
    )
    team.members.add(user)

    obj = _make_obj(event)
    assert can_view_speaker_names(user, obj) is False


def test_can_view_speaker_names_true_when_not_all_teams_hide():
    """If at least one reviewer team doesn't force-hide, names are visible
    (assuming the phase allows it)."""
    event = EventFactory()
    user = UserFactory()
    event.review_phases.all().delete()
    ReviewPhaseFactory(event=event, is_active=True, can_see_speaker_names=True)
    team_hide = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        force_hide_speaker_names=True,
    )
    team_show = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        force_hide_speaker_names=False,
    )
    team_hide.members.add(user)
    team_show.members.add(user)

    obj = _make_obj(event)
    assert can_view_speaker_names(user, obj) is True


def test_can_view_speaker_names_true_when_user_not_on_reviewer_team():
    """A user not on any reviewer team can see names if phase allows."""
    event = EventFactory()
    user = UserFactory()
    event.review_phases.all().delete()
    ReviewPhaseFactory(event=event, is_active=True, can_see_speaker_names=True)

    obj = _make_obj(event)
    assert can_view_speaker_names(user, obj) is True
