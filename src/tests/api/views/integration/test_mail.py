import json

import pytest
from django_scopes import scopes_disabled

from tests.factories import MailTemplateFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db
@pytest.mark.parametrize("is_public", (True, False))
def test_mail_template_list_requires_auth(client, event, is_public):
    """Unauthenticated mail template list returns 401 regardless of event visibility."""
    event.is_public = is_public
    event.save()

    response = client.get(event.api_urls.mail_templates, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_mail_template_list_with_orga_read_token(client, event, orga_read_token):
    """Organiser with read token can list mail templates."""
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


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_mail_template_list_query_count(
    client, event, orga_read_token, item_count, django_assert_num_queries
):
    """Query count for mail template list is constant regardless of item count."""
    with scopes_disabled():
        for _ in range(item_count):
            MailTemplateFactory(event=event, role=None)

    with django_assert_num_queries(11):
        response = client.get(
            event.api_urls.mail_templates,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200


@pytest.mark.django_db
def test_mail_template_detail_with_orga_read_token(client, event, orga_read_token):
    """Organiser can retrieve a single mail template."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)

    response = client.get(
        event.api_urls.mail_templates + f"{template.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == template.pk
    assert isinstance(data["subject"], dict)
    assert isinstance(data["text"], dict)


@pytest.mark.django_db
def test_mail_template_detail_locale_override(client, event, orga_read_token):
    """The ?lang= parameter makes i18n fields return plain strings."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)

    response = client.get(
        event.api_urls.mail_templates + f"{template.pk}/?lang=en",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["subject"], str)
    assert isinstance(data["text"], str)


@pytest.mark.django_db
def test_mail_template_create_with_write_token(client, event, orga_write_token):
    """POST with a write token creates a new mail template."""
    response = client.post(
        event.api_urls.mail_templates,
        follow=True,
        data=json.dumps(
            {"subject": {"en": "Test Subject"}, "text": {"en": "Hello {event_name}"}}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["subject"]["en"] == "Test Subject"
    with scopes_disabled():
        assert event.mail_templates.filter(pk=data["id"]).exists()
        template = event.mail_templates.get(pk=data["id"])
        assert (
            template.logged_actions()
            .filter(action_type="pretalx.mail_template.create")
            .exists()
        )


@pytest.mark.django_db
def test_mail_template_create_rejected_with_read_token(client, event, orga_read_token):
    """POST with a read-only token returns 403."""
    with scopes_disabled():
        initial_count = event.mail_templates.count()

    response = client.post(
        event.api_urls.mail_templates,
        follow=True,
        data=json.dumps({"subject": {"en": "Forbidden"}, "text": {"en": "No"}}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert event.mail_templates.count() == initial_count


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("subject", "test {invalidplaceholder}"),
        ("subject", "{invalid placeholder}"),
        ("text", "test {invalidplaceholder}"),
        ("text", "{invalid placeholder}"),
    ),
)
def test_mail_template_create_validates_placeholders(
    client, event, orga_write_token, field, value
):
    """Creating a template with invalid placeholders returns 400."""
    data = {"subject": {"en": "Valid Subject"}, "text": {"en": "Valid text"}}
    data[field] = {"en": value}

    response = client.post(
        event.api_urls.mail_templates,
        follow=True,
        data=json.dumps(data),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_mail_template_update_with_write_token(client, event, orga_write_token):
    """PATCH with a write token updates the mail template."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)

    response = client.patch(
        event.api_urls.mail_templates + f"{template.pk}/",
        follow=True,
        data=json.dumps({"subject": {"en": "Updated Subject"}}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        template.refresh_from_db()
        assert str(template.subject) == "Updated Subject"
        assert (
            template.logged_actions()
            .filter(action_type="pretalx.mail_template.update")
            .exists()
        )


@pytest.mark.django_db
def test_mail_template_update_rejected_with_read_token(client, event, orga_read_token):
    """PATCH with a read-only token returns 403."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)
        original_subject = str(template.subject)

    response = client.patch(
        event.api_urls.mail_templates + f"{template.pk}/",
        follow=True,
        data=json.dumps({"subject": {"en": "Changed"}}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        template.refresh_from_db()
        assert str(template.subject) == original_subject


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("subject", "test {invalidplaceholder}"),
        ("subject", "{invalid placeholder}"),
        ("text", "test {invalidplaceholder}"),
        ("text", "{invalid placeholder}"),
    ),
)
def test_mail_template_update_validates_placeholders(
    client, event, orga_write_token, field, value
):
    """Updating a template with invalid placeholders returns 400."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)

    response = client.patch(
        event.api_urls.mail_templates + f"{template.pk}/",
        follow=True,
        data=json.dumps({field: {"en": value}}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    with scopes_disabled():
        template.refresh_from_db()
        assert str(getattr(template, field)) != value


@pytest.mark.django_db
def test_mail_template_delete_with_write_token(client, event, orga_write_token):
    """DELETE with a write token removes the mail template."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)
        template_pk = template.pk

    response = client.delete(
        event.api_urls.mail_templates + f"{template_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.mail_templates.filter(pk=template_pk).exists()


@pytest.mark.django_db
def test_mail_template_delete_rejected_with_read_token(client, event, orga_read_token):
    """DELETE with a read-only token returns 403."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)

    response = client.delete(
        event.api_urls.mail_templates + f"{template.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert event.mail_templates.filter(pk=template.pk).exists()


@pytest.mark.django_db
def test_mail_template_log_endpoint(client, event, orga_read_token, orga_user):
    """The /log/ sub-endpoint returns logged actions for a mail template."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)
        template.log_action(
            "pretalx.mail_template.update", data={"key": "val"}, person=orga_user
        )

    response = client.get(
        event.api_urls.mail_templates + f"{template.pk}/log/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["action_type"] == "pretalx.mail_template.update"


@pytest.mark.django_db
def test_mail_template_list_rejects_legacy_version(client, event, orga_read_token):
    """GET with Pretalx-Version: LEGACY returns 400."""
    response = client.get(
        event.api_urls.mail_templates,
        follow=True,
        headers={
            "Authorization": f"Token {orga_read_token.token}",
            "Pretalx-Version": "LEGACY",
        },
    )

    assert response.status_code == 400
    assert "not supported" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_mail_template_create_ignores_role_field(client, event, orga_write_token):
    """POST with a role field is silently ignored because role is not editable."""
    response = client.post(
        event.api_urls.mail_templates,
        follow=True,
        data=json.dumps(
            {
                "subject": {"en": "With Role"},
                "text": {"en": "Body text"},
                "role": "submission.state.accepted",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    with scopes_disabled():
        template = event.mail_templates.get(pk=response.json()["id"])
        assert not template.role


@pytest.mark.django_db
def test_mail_template_update_ignores_role_field(client, event, orga_write_token):
    """PATCH with a role field is silently ignored because role is not editable."""
    with scopes_disabled():
        template = event.mail_templates.filter(role="submission.state.accepted").first()

    response = client.patch(
        event.api_urls.mail_templates + f"{template.pk}/",
        follow=True,
        data=json.dumps({"role": "submission.state.rejected"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        template.refresh_from_db()
        assert template.role == "submission.state.accepted"


@pytest.mark.django_db
def test_mail_template_delete_creates_log_entry(client, event, orga_write_token):
    """DELETE with a write token creates a logged action for the deletion."""
    with scopes_disabled():
        template = MailTemplateFactory(event=event, role=None)
        template_pk = template.pk

    response = client.delete(
        event.api_urls.mail_templates + f"{template_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert (
            event.logged_actions()
            .filter(action_type="pretalx.mail_template.delete")
            .exists()
        )
