# SPDX-FileCopyrightText: 2025-present Sungjoon Moon
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import Resource


@pytest.mark.django_db
def test_resource_without_hide_until_event_day_is_always_available(
    submission, resource
):
    """Resources without hide_until_event_day should always be available."""
    with scope(event=submission.event):
        assert resource.is_available is True


@pytest.mark.django_db
def test_resource_not_available_before_session(submission):
    """Resources with hide_until_event_day are hidden before session start."""
    with scope(event=submission.event):
        TalkSlot.objects.create(
            submission=submission,
            schedule=submission.event.wip_schedule,
            start=now() + timedelta(hours=1),
        )
        resource = Resource.objects.create(
            submission=submission, link="https://example.com", hide_until_event_day=True
        )
        assert resource.is_available is False


@pytest.mark.django_db
def test_resource_available_after_session(submission):
    """Resources with hide_until_event_day are visible after session start."""
    with scope(event=submission.event):
        TalkSlot.objects.create(
            submission=submission,
            schedule=submission.event.wip_schedule,
            start=now() - timedelta(hours=1),
        )
        resource = Resource.objects.create(
            submission=submission, link="https://example.com", hide_until_event_day=True
        )
        assert resource.is_available is True


@pytest.mark.django_db
def test_available_public_resources_filters_by_availability(submission):
    """available_public_resources filters by both is_public and availability."""
    with scope(event=submission.event):
        TalkSlot.objects.create(
            submission=submission,
            schedule=submission.event.wip_schedule,
            start=now() + timedelta(hours=1),
        )
        hidden = Resource.objects.create(
            submission=submission,
            link="https://example.com/hidden",
            is_public=True,
            hide_until_event_day=True,
        )
        visible = Resource.objects.create(
            submission=submission,
            link="https://example.com/visible",
            is_public=True,
        )
        available = submission.available_public_resources
        assert len(available) == 1
        assert visible in available
        assert hidden not in available
