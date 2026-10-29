# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.event import EventViewSet
from tests.factories import EventFactory, TeamFactory, UserFactory
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_event_viewset_get_queryset_hides_private_events_from_anonymous():
    public_event = EventFactory(is_public=True)
    private_event = EventFactory(is_public=False)
    user = UserFactory()
    team = TeamFactory(organiser=private_event.organiser, all_events=True)
    team.members.add(user)

    anonymous_view = make_view(EventViewSet, make_api_request())
    orga_view = make_view(EventViewSet, make_api_request(user=user))

    assert list(anonymous_view.get_queryset()) == [public_event]
    assert set(orga_view.get_queryset()) == {public_event, private_event}
