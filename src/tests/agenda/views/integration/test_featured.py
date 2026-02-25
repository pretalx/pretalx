import pytest
from django_scopes import scope, scopes_disabled

from pretalx.submission.models import SubmissionStates
from tests.factories import SubmissionFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("show_featured", "expected_status"),
    (("always", 200), ("never", 404), ("pre_schedule", 200)),
    ids=["always_visible", "never_visible", "pre_schedule_visible"],
)
def test_featured_view_visibility_by_setting(
    client, event, show_featured, expected_status
):
    """Featured page visibility depends on the show_featured feature flag."""
    with scopes_disabled():
        SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )
    event.is_public = True
    event.feature_flags["show_featured"] = show_featured
    event.save()

    response = client.get(event.urls.featured, follow=True)

    assert response.status_code == expected_status


@pytest.mark.django_db
def test_featured_view_shows_featured_talks(client, event):
    """Featured page displays featured submissions and excludes non-featured ones."""
    with scopes_disabled():
        featured = SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )
        not_featured = SubmissionFactory(
            event=event, is_featured=False, state=SubmissionStates.CONFIRMED
        )
    event.is_public = True
    event.feature_flags["show_featured"] = "always"
    event.save()

    response = client.get(event.urls.featured, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert featured.title in content
    assert not_featured.title not in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("show_featured", "expected_status"),
    (("always", 200), ("never", 302), ("pre_schedule", 302)),
    ids=["always_stays", "never_redirects", "pre_schedule_redirects"],
)
def test_featured_view_redirects_to_schedule_when_released(
    client, event, show_featured, expected_status
):
    """When a schedule is released, non-always settings redirect to the schedule."""
    event.is_public = True
    event.feature_flags["show_featured"] = show_featured
    event.save()
    with scope(event=event):
        event.release_schedule("v1")

    response = client.get(event.urls.featured)

    assert response.status_code == expected_status
    if expected_status == 302:
        assert response.url == event.urls.schedule


@pytest.mark.django_db
@pytest.mark.parametrize(
    "show_featured", ("always", "pre_schedule"), ids=["always", "pre_schedule"]
)
def test_featured_view_visible_when_schedule_hidden(client, event, show_featured):
    """Featured page is accessible when schedule exists but show_schedule is disabled."""
    event.is_public = True
    event.feature_flags["show_featured"] = show_featured
    event.feature_flags["show_schedule"] = False
    event.save()
    with scope(event=event):
        event.release_schedule("v1")

    response = client.get(event.urls.featured, follow=True)

    assert response.status_code == 200
    assert "featured" in response.content.decode()


@pytest.mark.django_db
def test_sneakpeek_redirect_to_featured(client, event):
    """The old /sneak/ URL permanently redirects to /featured/."""
    url = str(event.urls.featured).replace("featured", "sneak")

    response = client.get(url)

    assert response.status_code == 301
    assert response.url == event.urls.featured


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_featured_view_query_count(
    client, event, item_count, django_assert_num_queries
):
    """Query count is constant regardless of the number of featured talks."""
    with scopes_disabled():
        submissions = [
            SubmissionFactory(
                event=event, is_featured=True, state=SubmissionStates.CONFIRMED
            )
            for _ in range(item_count)
        ]
    event.is_public = True
    event.feature_flags["show_featured"] = "always"
    event.save()

    with django_assert_num_queries(8):
        response = client.get(event.urls.featured, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)
