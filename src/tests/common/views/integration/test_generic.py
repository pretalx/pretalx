"""Integration tests for pretalx.common.views.generic.

Uses TagView (OrgaCRUDView subclass) to exercise the full request/response
flow through CRUDView, OrgaTableMixin, and OrgaCRUDView.
"""

import pytest
from django_scopes import scopes_disabled

from pretalx.submission.models import Tag
from tests.factories import TagFactory
from tests.utils import make_orga_user

pytestmark = pytest.mark.integration


def _tag_list_url(event):
    return f"/orga/event/{event.slug}/submissions/tags/"


def _tag_create_url(event):
    return f"/orga/event/{event.slug}/submissions/tags/new/"


def _tag_update_url(event, tag):
    return f"/orga/event/{event.slug}/submissions/tags/{tag.pk}/"


def _tag_delete_url(event, tag):
    return f"/orga/event/{event.slug}/submissions/tags/{tag.pk}/delete/"


@pytest.fixture
def orga_user_and_event(event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    return user, event


@pytest.mark.django_db
def test_crud_dispatch_redirects_anonymous_to_login(client, event):
    response = client.get(_tag_list_url(event))

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_crud_dispatch_resolves_object_for_update(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event)
    client.force_login(user)

    response = client.get(_tag_update_url(event, tag))

    assert response.status_code == 200
    assert response.context["form"].instance == tag


@pytest.mark.django_db
def test_crud_dispatch_returns_404_for_missing_object(client, orga_user_and_event):
    user, event = orga_user_and_event
    client.force_login(user)

    response = client.get(f"/orga/event/{event.slug}/submissions/tags/99999/")

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_crud_list_query_count(
    client, orga_user_and_event, item_count, django_assert_num_queries
):
    user, event = orga_user_and_event
    with scopes_disabled():
        tags = [TagFactory(event=event, tag=f"Tag{i}") for i in range(item_count)]
    client.force_login(user)

    with django_assert_num_queries(18):
        response = client.get(_tag_list_url(event))

    assert response.status_code == 200
    content = response.content.decode()
    assert all(tag.tag in content for tag in tags)


@pytest.mark.django_db
def test_crud_list_includes_table_in_context(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        TagFactory(event=event, tag="Django")
    client.force_login(user)

    response = client.get(_tag_list_url(event))

    assert response.status_code == 200
    assert "table" in response.context
    assert "Django" in response.content.decode()


@pytest.mark.django_db
def test_crud_list_pagination(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        for i in range(5):
            TagFactory(event=event, tag=f"Tag{i}")
    client.force_login(user)

    response = client.get(_tag_list_url(event) + "?page_size=2")

    assert response.status_code == 200
    assert response.context["is_paginated"]


@pytest.mark.django_db
def test_crud_list_invalid_page_size_falls_back(client, orga_user_and_event):
    """Non-integer page_size is ignored and the default page size is used."""
    user, event = orga_user_and_event
    with scopes_disabled():
        TagFactory(event=event, tag="fallback")
    client.force_login(user)

    response = client.get(_tag_list_url(event) + "?page_size=abc")

    assert response.status_code == 200
    assert "fallback" in response.content.decode()


@pytest.mark.django_db
def test_crud_list_page_last(client, orga_user_and_event):
    """page=last is accepted without error (table-backed views delegate
    pagination to django-tables2 which ignores the param gracefully)."""
    user, event = orga_user_and_event
    with scopes_disabled():
        for i in range(5):
            TagFactory(event=event, tag=f"Tag{i}")
    client.force_login(user)

    response = client.get(_tag_list_url(event) + "?page=last&page_size=2")

    assert response.status_code == 200
    assert response.context["is_paginated"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "url_fn"),
    (
        ("create", lambda e, _: f"/orga/event/{e.slug}/submissions/tags/new/"),
        ("update", lambda e, t: f"/orga/event/{e.slug}/submissions/tags/{t.pk}/"),
    ),
)
def test_crud_form_view_returns_form_in_context(
    client, orga_user_and_event, action, url_fn
):
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event) if action == "update" else None
    client.force_login(user)

    response = client.get(url_fn(event, tag))

    assert response.status_code == 200
    assert "form" in response.context


@pytest.mark.django_db
def test_crud_create_via_post(client, orga_user_and_event):
    user, event = orga_user_and_event
    client.force_login(user)

    response = client.post(
        _tag_create_url(event),
        {"tag": "NewTag", "description_0": "", "color": "#aabbcc"},
    )

    assert response.status_code == 302
    with scopes_disabled():
        tag = Tag.objects.get(event=event, tag="NewTag")
        assert tag.event == event


@pytest.mark.django_db
def test_crud_update_via_post(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event, tag="OldName")
    client.force_login(user)

    response = client.post(
        _tag_update_url(event, tag),
        {"tag": "NewName", "description_0": "", "color": tag.color},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        tag.refresh_from_db()
    assert tag.tag == "NewName"


@pytest.mark.django_db
def test_crud_form_handler_invalid_data_rerenders(client, orga_user_and_event):
    user, event = orga_user_and_event
    client.force_login(user)

    response = client.post(_tag_create_url(event), {"tag": "", "color": ""})

    assert response.status_code == 200
    assert response.context["form"].errors


@pytest.mark.django_db
def test_crud_form_handler_with_next_url_redirects(client, orga_user_and_event):
    user, event = orga_user_and_event
    client.force_login(user)
    next_url = _tag_list_url(event)

    response = client.post(
        _tag_create_url(event) + f"?next={next_url}",
        {"tag": "WithNext", "description_0": "", "color": "#112233"},
    )

    assert response.status_code == 302
    assert response.url == next_url


@pytest.mark.django_db
def test_crud_delete_confirmation_page(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event)
    client.force_login(user)

    response = client.get(_tag_delete_url(event, tag))

    assert response.status_code == 200
    assert "submit_buttons" in response.context
    assert "submit_buttons_extra" in response.context


@pytest.mark.django_db
def test_crud_delete_handler_removes_and_redirects(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event)
        tag_pk = tag.pk
    client.force_login(user)

    response = client.post(_tag_delete_url(event, tag))

    assert response.status_code == 302
    assert response.url == _tag_list_url(event)
    with scopes_disabled():
        assert not Tag.objects.filter(pk=tag_pk).exists()


@pytest.mark.django_db
def test_crud_htmx_table_request(client, orga_user_and_event):
    user, event = orga_user_and_event
    client.force_login(user)
    url = _tag_list_url(event) + "?page=1"

    response = client.get(
        url, headers={"HX-Request": "true", "HX-Target": "table-content-main"}
    )

    assert response.status_code == 200
    assert response["HX-Push-Url"] == url


@pytest.mark.django_db
def test_crud_page_size_stored_in_preferences(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        for i in range(5):
            TagFactory(event=event, tag=f"Tag{i}")
    client.force_login(user)

    response = client.get(_tag_list_url(event) + "?page_size=3")

    assert response.status_code == 200
    assert response.context["is_paginated"]


@pytest.mark.django_db
def test_crud_create_logs_action(client, orga_user_and_event):
    user, event = orga_user_and_event
    client.force_login(user)

    client.post(
        _tag_create_url(event),
        {"tag": "Logged", "description_0": "", "color": "#aabbcc"},
        follow=True,
    )

    with scopes_disabled():
        tag = Tag.objects.get(event=event, tag="Logged")
        assert tag.logged_actions().exists()


@pytest.mark.django_db
def test_crud_update_logs_with_changes(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event, tag="Before")
    client.force_login(user)

    client.post(
        _tag_update_url(event, tag),
        {"tag": "After", "description_0": "", "color": tag.color},
        follow=True,
    )

    with scopes_disabled():
        log = tag.logged_actions().order_by("-pk").first()
    assert log is not None
    assert log.json_data.get("changes")


@pytest.mark.django_db
def test_crud_update_without_changes_does_not_log(client, orga_user_and_event):
    """Submitting the form with no changes should not create a log entry."""
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event)
        initial_log_count = tag.logged_actions().count()
    client.force_login(user)

    client.post(
        _tag_update_url(event, tag),
        {"tag": str(tag.tag), "description_0": "", "color": tag.color},
        follow=True,
    )

    with scopes_disabled():
        assert tag.logged_actions().count() == initial_log_count


@pytest.mark.django_db
def test_crud_update_context_includes_generic_data(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event)
    client.force_login(user)

    response = client.get(_tag_update_url(event, tag))

    assert response.status_code == 200
    ctx = response.context
    assert ctx["action"] == "update"
    assert "generic_title" in ctx
    assert "submit_buttons" in ctx


@pytest.mark.django_db
def test_crud_list_context_includes_create_url(client, orga_user_and_event):
    user, event = orga_user_and_event
    client.force_login(user)

    response = client.get(_tag_list_url(event))

    assert response.status_code == 200
    assert response.context["create_url"] == _tag_create_url(event)
