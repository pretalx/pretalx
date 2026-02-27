import pytest
from django_scopes import scopes_disabled

from tests.factories import (
    EventFactory,
    OrganiserFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_nav_typeahead_unauthenticated_returns_empty(client):
    """Anonymous users are redirected by the login_required middleware."""
    response = client.get("/orga/nav/typeahead/")

    assert response.status_code == 302


@pytest.mark.django_db
def test_nav_typeahead_organiser_sees_user_orga_and_event(
    client, event, organiser_user
):
    """An organiser with no query sees themselves, their organiser, and their event."""
    client.force_login(organiser_user)

    response = client.get("/orga/nav/typeahead/")

    assert response.status_code == 200
    data = response.json()
    results = data["results"]
    assert len(results) == 3
    assert results[0]["type"] == "user"
    assert results[0]["name"] == str(organiser_user)
    assert results[1]["type"] == "organiser"
    assert results[1]["name"] == str(event.organiser.name)
    assert results[2]["type"] == "event"
    assert results[2]["name"] == str(event.name)


@pytest.mark.django_db
def test_nav_typeahead_no_permissions_only_sees_self(client, event):
    """A user without any team membership only sees themselves."""
    user = UserFactory()
    client.force_login(user)

    response = client.get("/orga/nav/typeahead/")

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["type"] == "user"


@pytest.mark.django_db
def test_nav_typeahead_query_filters_events_by_name(client, event, organiser_user):
    """Searching by event slug filters to matching events only."""
    with scopes_disabled():
        EventFactory(organiser=event.organiser)
    client.force_login(organiser_user)

    response = client.get(f"/orga/nav/typeahead/?query={event.slug}")

    results = response.json()["results"]
    event_results = [r for r in results if r["type"] == "event"]
    assert len(event_results) == 1
    assert event_results[0]["name"] == str(event.name)


@pytest.mark.django_db
def test_nav_typeahead_query_filters_by_organiser_name(client, event, organiser_user):
    """Searching by organiser name returns matching organisers."""
    client.force_login(organiser_user)
    orga_name = str(event.organiser.name)

    response = client.get(f"/orga/nav/typeahead/?query={orga_name}")

    results = response.json()["results"]
    orga_results = [r for r in results if r["type"] == "organiser"]
    assert len(orga_results) == 1
    assert orga_results[0]["name"] == orga_name


@pytest.mark.django_db
def test_nav_typeahead_query_matching_user_shows_user(client, event, organiser_user):
    """When query matches the current user's name, the user entry is shown."""
    client.force_login(organiser_user)
    query = organiser_user.name[:5]

    response = client.get(f"/orga/nav/typeahead/?query={query}")

    results = response.json()["results"]
    user_results = [r for r in results if r["type"] == "user"]
    assert len(user_results) == 1
    assert user_results[0]["name"] == str(organiser_user)


@pytest.mark.django_db
def test_nav_typeahead_query_not_matching_user_hides_user(
    client, event, organiser_user
):
    """When query doesn't match the current user, no user entry is shown."""
    client.force_login(organiser_user)

    response = client.get("/orga/nav/typeahead/?query=zzznomatchzzz")

    results = response.json()["results"]
    assert not any(r["type"] == "user" for r in results)


@pytest.mark.django_db
def test_nav_typeahead_short_query_excludes_submissions(client, event):
    """Queries shorter than 3 characters do not search submissions."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        SubmissionFactory(event=event, title="AB special talk")
    client.force_login(user)

    response = client.get("/orga/nav/typeahead/?query=AB")

    results = response.json()["results"]
    assert not any(r["type"] == "submission" for r in results)


@pytest.mark.django_db
def test_nav_typeahead_query_searches_submissions(client, event):
    """Queries of 3+ characters search submissions for users with can_change_submissions."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event, title="Kubernetes deep dive")
    client.force_login(user)

    response = client.get("/orga/nav/typeahead/?query=Kubernetes")

    results = response.json()["results"]
    submission_results = [r for r in results if r["type"] == "submission"]
    assert len(submission_results) == 1
    assert submission.title in submission_results[0]["name"]


@pytest.mark.django_db
def test_nav_typeahead_query_searches_speakers(client, event):
    """Queries of 3+ characters search speakers with submissions."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event, name="Guido van Rossum")
        submission = SubmissionFactory(event=event)
        submission.speakers.add(speaker)
    client.force_login(user)

    response = client.get("/orga/nav/typeahead/?query=Guido")

    results = response.json()["results"]
    speaker_results = [r for r in results if r["type"] == "speaker"]
    assert len(speaker_results) == 1
    assert "Guido van Rossum" in speaker_results[0]["name"]


@pytest.mark.django_db
def test_nav_typeahead_speaker_without_submission_excluded(client, event):
    """Speaker profiles without submissions are not returned."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        SpeakerFactory(event=event, name="Lonely Speaker")
    client.force_login(user)

    response = client.get("/orga/nav/typeahead/?query=Lonely")

    results = response.json()["results"]
    assert not any(r["type"] == "speaker" for r in results)


@pytest.mark.django_db
def test_nav_typeahead_admin_user_sees_admin_results(client, event):
    """Administrators see user.admin results in typeahead."""
    with scopes_disabled():
        admin = make_orga_user(event)
        admin.is_administrator = True
        admin.save()
        target_user = UserFactory(name="Findable Admin Target")
    client.force_login(admin)

    response = client.get("/orga/nav/typeahead/?query=Findable")

    results = response.json()["results"]
    admin_results = [r for r in results if r["type"] == "user.admin"]
    assert len(admin_results) == 1
    assert admin_results[0]["email"] == target_user.email


@pytest.mark.django_db
def test_nav_typeahead_non_admin_no_admin_results(client, event, organiser_user):
    """Non-administrators do not see user.admin results."""
    UserFactory(name="Some Admin Target")
    client.force_login(organiser_user)

    response = client.get("/orga/nav/typeahead/?query=Admin+Target")

    results = response.json()["results"]
    assert not any(r["type"] == "user.admin" for r in results)


@pytest.mark.django_db
def test_nav_typeahead_organiser_param_pins_organiser(client, event, organiser_user):
    """The organiser query param pins the matching organiser after the user entry."""
    client.force_login(organiser_user)

    response = client.get(f"/orga/nav/typeahead/?organiser={event.organiser.pk}")

    results = response.json()["results"]
    assert results[0]["type"] == "user"
    assert results[1]["type"] == "organiser"
    assert results[1]["name"] == str(event.organiser.name)


@pytest.mark.django_db
def test_nav_typeahead_pagination_more_flag(client, event):
    """The pagination.more flag indicates when there are more results."""
    with scopes_disabled():
        user = make_orga_user(event)
        for i in range(25):
            EventFactory(organiser=event.organiser, slug=f"evt{i:03d}")
    client.force_login(user)

    response = client.get("/orga/nav/typeahead/?query=evt")

    data = response.json()
    assert data["pagination"]["more"] is True


@pytest.mark.django_db
def test_nav_typeahead_page_param(client, event):
    """The page parameter offsets results so pages don't overlap."""
    with scopes_disabled():
        user = make_orga_user(event)
        for i in range(25):
            EventFactory(organiser=event.organiser, slug=f"pg{i:03d}")
    client.force_login(user)

    response_p1 = client.get("/orga/nav/typeahead/?query=pg&page=1")
    response_p2 = client.get("/orga/nav/typeahead/?query=pg&page=2")

    results_p1 = response_p1.json()["results"]
    results_p2 = response_p2.json()["results"]
    names_p1 = {r["name"] for r in results_p1}
    names_p2 = {r["name"] for r in results_p2}
    assert names_p1.isdisjoint(names_p2)


@pytest.mark.django_db
def test_nav_typeahead_invalid_page_defaults_to_one(client, event, organiser_user):
    """An invalid page parameter defaults to page 1, returning the same results."""
    client.force_login(organiser_user)

    response_invalid = client.get("/orga/nav/typeahead/?page=notanumber")
    response_default = client.get("/orga/nav/typeahead/")

    assert response_invalid.json() == response_default.json()


@pytest.mark.django_db
def test_nav_typeahead_submissions_not_searched_without_permission(client, event):
    """Users without can_change_submissions don't get submission results even with query >= 3."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=False)
        SubmissionFactory(event=event, title="Secret submission data")
    client.force_login(user)

    response = client.get("/orga/nav/typeahead/?query=Secret")

    results = response.json()["results"]
    assert not any(r["type"] == "submission" for r in results)


@pytest.mark.django_db
def test_nav_typeahead_query_with_organiser_and_matching_user(client, event):
    """When query matches the user name AND an organiser param is given,
    the organiser filter includes Q(pk=organiser) to keep it in results."""
    with scopes_disabled():
        user = make_orga_user(event)
    client.force_login(user)
    query = user.name[:5]

    response = client.get(
        f"/orga/nav/typeahead/?query={query}&organiser={event.organiser.pk}"
    )

    results = response.json()["results"]
    user_results = [r for r in results if r["type"] == "user"]
    assert len(user_results) == 1
    orga_results = [r for r in results if r["type"] == "organiser"]
    assert len(orga_results) == 1
    assert orga_results[0]["name"] == str(event.organiser.name)


@pytest.mark.django_db
def test_nav_typeahead_organiser_not_in_initial_slice_still_pinned(client):
    """When the organiser param refers to an organiser not in the initial
    top-5 slice (no query), it is still inserted at position 1."""
    with scopes_disabled():
        user = UserFactory()
        # Create 6 organisers, each with a team for this user.
        # Give the first 5 more events so they rank higher.
        organisers = []
        for i in range(6):
            orga = OrganiserFactory()
            team = TeamFactory(organiser=orga, all_events=True)
            team.members.add(user)
            # Create events to boost ranking for the first 5
            if i < 5:
                for _ in range(3):
                    EventFactory(organiser=orga)
            organisers.append(orga)
        # The 6th organiser (index 5) has 0 events, so it's ranked last
        target_orga = organisers[5]
    client.force_login(user)

    response = client.get(f"/orga/nav/typeahead/?organiser={target_orga.pk}")

    results = response.json()["results"]
    assert results[0]["type"] == "user"
    assert results[1]["type"] == "organiser"
    assert results[1]["name"] == str(target_orga.name)


@pytest.mark.django_db
def test_nav_typeahead_submission_by_code(client, event):
    """Submissions can be found by their code prefix."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        submission = SubmissionFactory(event=event)
    client.force_login(user)

    response = client.get(f"/orga/nav/typeahead/?query={submission.code}")

    results = response.json()["results"]
    submission_results = [r for r in results if r["type"] == "submission"]
    assert len(submission_results) == 1
    assert submission.title in submission_results[0]["name"]


@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.django_db
def test_nav_typeahead_query_count_no_query(
    client, event, item_count, django_assert_num_queries
):
    """Query count is constant regardless of the number of events."""
    with scopes_disabled():
        user = make_orga_user(event)
        for _ in range(item_count - 1):
            EventFactory(organiser=event.organiser)
    client.force_login(user)

    with django_assert_num_queries(6):
        response = client.get("/orga/nav/typeahead/")

    assert response.status_code == 200
    results = response.json()["results"]
    event_results = [r for r in results if r["type"] == "event"]
    assert len(event_results) == item_count


@pytest.mark.parametrize("item_count", (1, 3))
@pytest.mark.django_db
def test_nav_typeahead_query_count_with_submissions(
    client, event, item_count, django_assert_num_queries
):
    """Query count is constant regardless of the number of submissions matched."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        for i in range(item_count):
            sub = SubmissionFactory(event=event, title=f"Kubernetes talk {i}")
            speaker = SpeakerFactory(event=event, name=f"K8s Speaker {i}")
            sub.speakers.add(speaker)
    client.force_login(user)

    with django_assert_num_queries(11):
        response = client.get("/orga/nav/typeahead/?query=Kubernetes")

    assert response.status_code == 200
    results = response.json()["results"]
    submission_results = [r for r in results if r["type"] == "submission"]
    assert len(submission_results) == item_count
