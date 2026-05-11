# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.submission.domain.resource import create_resource, delete_resource
from tests.factories import (
    EventFactory,
    ResourceFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_resource_persists_and_logs():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()

    with scope(event=event):
        resource = create_resource(
            submission, user=user, description="docs", link="https://example.com"
        )

        assert resource.pk is not None
        assert resource.description == "docs"
        assert resource.link == "https://example.com"
        assert submission.resources.filter(pk=resource.pk).exists()
        assert (
            submission.logged_actions().filter(action_type__endswith=".update").exists()
        )


def test_create_resource_clears_prefetched_cache():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()

    with scope(event=event):
        # Prime the prefetch cache so the diff logic would normally see
        # stale data; create_resource must invalidate the cache.
        submission._prefetched_objects_cache = {  # noqa: SLF001 -- mimic Django prefetch
            "resources": list(submission.resources.all())
        }
        create_resource(
            submission, user=user, description="link", link="https://x.test"
        )
        # After the call the cache no longer carries the stale `resources` entry.
        assert "resources" not in submission._prefetched_objects_cache  # noqa: SLF001


def test_delete_resource_removes_and_logs():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()

    with scope(event=event):
        resource = ResourceFactory(submission=submission)
        assert submission.resources.filter(pk=resource.pk).exists()

        delete_resource(resource, user=user)

        assert not submission.resources.filter(pk=resource.pk).exists()
        assert (
            submission.logged_actions().filter(action_type__endswith=".update").exists()
        )
