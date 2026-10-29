# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.submission.domain.resource import create_resource, delete_resource
from tests.factories import EventFactory, SubmissionFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_and_delete_resource_log_and_clear_prefetch_cache():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()

    with scope(event=event):
        submission._prefetched_objects_cache = {  # noqa: SLF001 -- mimic Django prefetch
            "resources": list(submission.resources.all())
        }
        resource = create_resource(
            submission, user=user, description="docs", link="https://example.com"
        )

        assert resource.description == "docs"
        assert resource.link == "https://example.com"
        assert list(submission.resources.all()) == [resource]
        assert "resources" not in submission._prefetched_objects_cache  # noqa: SLF001
        assert (
            submission.logged_actions().filter(action_type__endswith=".update").count()
            == 1
        )

        submission._prefetched_objects_cache["resources"] = [resource]  # noqa: SLF001
        delete_resource(resource, user=user)

        assert list(submission.resources.all()) == []
        assert "resources" not in submission._prefetched_objects_cache  # noqa: SLF001
        assert (
            submission.logged_actions().filter(action_type__endswith=".update").count()
            == 2
        )
