# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.submission.models import SubmissionStates
from tests.factories import SpeakerFactory, SubmissionFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("item_count", (1, 3))
def test_submission_cards_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submissions = SubmissionFactory.create_batch(
            item_count,
            event=event,
            state=SubmissionStates.ACCEPTED,
            abstract=None,
            notes=None,
        )
        for submission in submissions:
            speaker = SpeakerFactory(event=event)
            submission.speakers.add(speaker)
    client.force_login(user)

    with django_assert_num_queries(7):
        response = client.get(event.orga_urls.submission_cards)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


def test_submission_cards_empty_queryset_redirects_and_permission_required(
    client, event
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.submission_cards)

    assert response.status_code == 302
    assert response.url == event.orga_urls.submissions

    with scopes_disabled():
        client.force_login(make_orga_user(event, can_change_submissions=False))

    assert client.get(event.orga_urls.submission_cards).status_code == 404
