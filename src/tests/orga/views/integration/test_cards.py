import pytest
from django_scopes import scopes_disabled

from pretalx.submission.models import SubmissionStates
from tests.factories import SpeakerFactory, SubmissionFactory
from tests.utils import make_orga_user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.django_db
def test_submission_cards_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        for _ in range(item_count):
            submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
            speaker = SpeakerFactory(event=event)
            submission.speakers.add(speaker)
    client.force_login(user)

    with django_assert_num_queries(11):
        response = client.get(event.orga_urls.submission_cards)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


@pytest.mark.django_db
def test_submission_cards_with_null_abstract_and_notes(client, event):
    """Cards render even when submissions have no abstract or notes."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.CONFIRMED, abstract=None, notes=None
        )
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.get(event.orga_urls.submission_cards)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


@pytest.mark.django_db
def test_submission_cards_empty_queryset_redirects(client, event):
    """When no submissions match, user is redirected to submissions list."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.submission_cards)

    assert response.status_code == 302
    assert response.url == event.orga_urls.submissions


@pytest.mark.django_db
def test_submission_cards_anonymous_redirects_to_login(client, event):
    """Anonymous user is redirected to login."""
    response = client.get(event.orga_urls.submission_cards)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_submission_cards_user_without_permission_gets_404(client, event):
    """User without submission permissions cannot access cards."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=False)
    client.force_login(user)

    response = client.get(event.orga_urls.submission_cards)

    assert response.status_code == 404
