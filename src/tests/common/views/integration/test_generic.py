# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.submission.models import Tag
from tests.factories import EventFactory, TagFactory, UserFactory
from tests.utils import DIALOG_HEADERS, make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


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


@pytest.mark.parametrize(
    ("role", "expected_status"),
    (
        pytest.param("anonymous", 302, id="anonymous-redirects-to-login"),
        pytest.param("unrelated", 404, id="unrelated-user"),
        pytest.param("other_organiser", 404, id="organiser-of-other-event"),
        pytest.param("no_submission_access", 404, id="organiser-without-access"),
        pytest.param("reviewer", 200, id="reviewer"),
        pytest.param("submission_orga", 200, id="organiser-with-access"),
    ),
)
def test_crud_list_permissions_by_role(client, event, role, expected_status):
    with scopes_disabled():
        tag = TagFactory(event=event, tag="SecretTag")
        match role:
            case "anonymous":
                user = None
            case "unrelated":
                user = UserFactory()
            case "other_organiser":
                user = make_orga_user(EventFactory(), can_change_submissions=True)
            case "no_submission_access":
                user = make_orga_user(
                    event, can_change_submissions=False, can_change_event_settings=True
                )
            case "reviewer":
                user = make_orga_user(
                    event, is_reviewer=True, can_change_submissions=False
                )
            case _:
                user = make_orga_user(event, can_change_submissions=True)
    if user:
        client.force_login(user)

    response = client.get(_tag_list_url(event))

    assert response.status_code == expected_status
    if expected_status == 200:
        assert tag.tag in response.content.decode()
    if expected_status == 302:
        assert "/login/" in response.url


@pytest.mark.parametrize("item_count", (1, 3))
def test_crud_list_query_count(
    client, orga_user_and_event, item_count, django_assert_num_queries
):
    user, event = orga_user_and_event
    with scopes_disabled():
        tags = TagFactory.create_batch(item_count, event=event)
    client.force_login(user)

    with django_assert_num_queries(14):
        response = client.get(_tag_list_url(event))

    assert response.status_code == 200
    assert "table" in response.context
    content = response.content.decode()
    assert all(tag.tag in content for tag in tags)


def test_crud_list_persists_only_valid_page_sizes(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        TagFactory.create_batch(5, event=event)
    client.force_login(user)

    response = client.get(_tag_list_url(event) + "?page_size=2")

    assert response.status_code == 200
    assert response.context["is_paginated"]
    assert response.context["paginator"].per_page == 2

    for page_size in ("0", "-3", "abc"):
        response = client.get(_tag_list_url(event) + f"?page_size={page_size}")
        assert response.status_code == 200
        assert response.context["paginator"].per_page == 2
        response = client.get(_tag_list_url(event))
        assert response.context["paginator"].per_page == 2


@pytest.mark.parametrize(
    ("with_header", "expect_paginated"),
    (
        pytest.param(True, False, id="header-bypasses-pagination"),
        pytest.param(False, True, id="no-header-still-paginated"),
    ),
)
def test_crud_list_print_pagination_gate(
    client, orga_user_and_event, with_header, expect_paginated
):
    user, event = orga_user_and_event
    with scopes_disabled():
        TagFactory.create_batch(5, event=event)
    client.force_login(user)

    extra = {"HTTP_HX_PRETALX_PRINT": "1"} if with_header else {}
    response = client.get(_tag_list_url(event) + "?page_size=2&paginate=0", **extra)

    assert response.status_code == 200
    assert bool(response.context.get("is_paginated")) is expect_paginated


def test_crud_create_via_post(client, orga_user_and_event):
    user, event = orga_user_and_event
    client.force_login(user)
    next_url = _tag_list_url(event)

    response = client.post(_tag_create_url(event), {"tag": "", "color": ""})

    assert response.status_code == 200
    assert response.context["form"].errors

    response = client.post(
        _tag_create_url(event),
        {"tag": "NewTag", "description_0": "", "color": "#aabbcc"},
    )

    assert response.status_code == 302
    with scopes_disabled():
        tag = Tag.objects.select_related("event").get(event=event, tag="NewTag")
        assert tag.event == event
        assert tag.logged_actions().exists()

    response = client.post(
        _tag_create_url(event) + f"?next={next_url}",
        {"tag": "WithNext", "description_0": "", "color": "#112233"},
    )

    assert response.status_code == 302
    assert response.url == next_url
    with scopes_disabled():
        assert Tag.objects.filter(event=event, tag="WithNext").exists()


def test_crud_update_via_post_logs_only_changes(client, orga_user_and_event):
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event, tag="OldName")
        initial_log_count = tag.logged_actions().count()
    client.force_login(user)

    response = client.get(_tag_update_url(event, tag))

    assert response.status_code == 200
    assert response.context["form"].instance == tag

    client.post(
        _tag_update_url(event, tag),
        {"tag": "OldName", "description_0": "", "color": tag.color},
        follow=True,
    )

    with scopes_disabled():
        assert tag.logged_actions().count() == initial_log_count

    response = client.post(
        _tag_update_url(event, tag),
        {"tag": "NewName", "description_0": "", "color": tag.color},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        tag.refresh_from_db()
        log = tag.logged_actions().order_by("-pk").first()
        assert tag.logged_actions().count() == initial_log_count + 1
    assert tag.tag == "NewName"
    assert log.json_data["changes"]["tag"] == {"old": "OldName", "new": "NewName"}


@pytest.mark.parametrize(
    ("headers", "template", "status", "redirect_header"),
    (
        pytest.param(None, "orga/generic/delete.html", 302, "Location", id="plain"),
        pytest.param(
            DIALOG_HEADERS,
            "common/includes/action_confirm.html#dialog",
            286,
            "HX-Redirect",
            id="dialog",
        ),
    ),
)
def test_crud_delete_confirms_then_removes_and_redirects(
    client, orga_user_and_event, headers, template, status, redirect_header
):
    user, event = orga_user_and_event
    with scopes_disabled():
        tag = TagFactory(event=event)
        tag_pk = tag.pk
    client.force_login(user)

    response = client.get(_tag_delete_url(event, tag), headers=headers)

    assert response.status_code == 200
    assert response.template_name[-1] == template
    assert tag.tag in response.content.decode()
    assert "submit_buttons" in response.context
    assert "submit_buttons_extra" in response.context

    response = client.post(_tag_delete_url(event, tag), headers=headers)

    assert response.status_code == status
    assert response[redirect_header] == _tag_list_url(event)
    with scopes_disabled():
        assert not Tag.objects.filter(pk=tag_pk).exists()


def test_crud_htmx_table_request(client, orga_user_and_event):
    user, event = orga_user_and_event
    client.force_login(user)
    url = _tag_list_url(event) + "?page=1"

    response = client.get(
        url, headers={"HX-Request": "true", "HX-Target": "table-content-main"}
    )

    assert response.status_code == 200
    assert response["HX-Push-Url"] == url
