import pytest
from django.core import mail as djmail
from django.urls import reverse

from tests.factories import UserFactory

pytestmark = pytest.mark.e2e


@pytest.fixture
def user_with_password():
    return UserFactory(password="testpassword!")


@pytest.mark.django_db
def test_full_password_reset_flow(client, user_with_password):
    """End-to-end: request reset, use token, login with new password."""
    djmail.outbox = []

    # Step 1: Request reset
    client.post(reverse("orga:auth.reset"), {"login_email": user_with_password.email})
    user_with_password.refresh_from_db()
    assert user_with_password.pw_reset_token is not None
    assert len(djmail.outbox) == 1

    # Step 2: Use token to set new password
    response = client.post(
        f"/orga/reset/{user_with_password.pw_reset_token}",
        {"password": "brandnewpassword1!", "password_repeat": "brandnewpassword1!"},
    )
    assert response.status_code == 302
    user_with_password.refresh_from_db()
    assert user_with_password.pw_reset_token is None

    # Step 3: Login with new password
    response = client.post(
        reverse("orga:login"),
        {
            "login_email": user_with_password.email,
            "login_password": "brandnewpassword1!",
        },
        follow=True,
    )
    assert response.status_code == 200
    assert response.redirect_chain[-1][0] == "/orga/event/"
