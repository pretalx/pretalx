# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from tests.factories import MailTemplateFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_mail_template_list_requires_auth(client, event):
    response = client.get(event.api_urls.mail_templates, follow=True)

    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_mail_template_list_with_orga_read_token(
    client, event, orga_read_token, item_count, django_assert_num_queries
):
    with scopes_disabled():
        MailTemplateFactory.create_batch(item_count, event=event, role=None)

    with django_assert_num_queries(10):
        response = client.get(
            event.api_urls.mail_templates,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    result = data["results"][0]
    assert "id" in result
    assert "subject" in result
    assert "text" in result


def test_mail_template_detail_with_orga_read_token(client, event, orga_read_token):
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    response = client.get(
        event.api_urls.mail_templates + f"{template.pk}/", follow=True, headers=headers
    )
    localised = client.get(
        event.api_urls.mail_templates + f"{template.pk}/?lang=en",
        follow=True,
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": template.pk,
        "role": None,
        "subject": {"en": str(template.subject)},
        "text": {"en": str(template.text)},
        "reply_to": template.reply_to,
        "bcc": template.bcc,
    }
    assert localised.status_code == 200
    assert localised.json()["subject"] == str(template.subject)
    assert localised.json()["text"] == str(template.text)


def test_mail_template_create_with_write_token(client, event, orga_write_token):
    response = client.post(
        event.api_urls.mail_templates,
        follow=True,
        data={
            "subject": {"en": "Test Subject"},
            "text": {"en": "Hello {event_name}"},
            "role": "submission.state.accepted",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["subject"]["en"] == "Test Subject"
    with scopes_disabled():
        template = event.mail_templates.get(pk=data["id"])
        assert not template.role
        assert (
            template.logged_actions()
            .filter(action_type="pretalx.mail_template.create")
            .exists()
        )


def test_mail_template_create_rejected_with_read_token(client, event, orga_read_token):
    with scopes_disabled():
        initial_count = event.mail_templates.count()

    response = client.post(
        event.api_urls.mail_templates,
        follow=True,
        data={"subject": {"en": "Forbidden"}, "text": {"en": "No"}},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert event.mail_templates.count() == initial_count


@pytest.mark.parametrize(
    ("field", "value"),
    (("subject", "test {invalidplaceholder}"), ("text", "{invalid placeholder}")),
)
def test_mail_template_create_validates_placeholders(
    client, event, orga_write_token, field, value
):
    data = {"subject": {"en": "Valid Subject"}, "text": {"en": "Valid text"}}
    data[field] = {"en": value}

    response = client.post(
        event.api_urls.mail_templates,
        follow=True,
        data=data,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert list(response.json()) == [field]


def test_mail_template_update_log_and_delete_with_write_token(
    client, event, orga_write_token
):
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)
    url = event.api_urls.mail_templates + f"{template.pk}/"
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.patch(
        url,
        follow=True,
        data={"subject": {"en": "Updated Subject"}},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        template.refresh_from_db()
        assert str(template.subject) == "Updated Subject"

    log = client.get(url + "log/", follow=True, headers=headers)

    assert log.status_code == 200
    data = log.json()
    assert data["count"] == 1
    assert data["results"][0]["action_type"] == "pretalx.mail_template.update"

    response = client.delete(url, follow=True, headers=headers)

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.mail_templates.filter(pk=template.pk).exists()
        assert (
            event.logged_actions()
            .filter(action_type="pretalx.mail_template.delete")
            .exists()
        )
