import pytest

from pretalx.cfp.forms.auth import RecoverForm, ResetForm
from tests.factories import UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "email",
    ("speaker@example.com", "SPEAKER@example.com"),
    ids=["exact", "case_insensitive"],
)
@pytest.mark.django_db
def test_reset_form_clean_sets_user_when_email_exists(email):
    user = UserFactory(email="speaker@example.com")

    form = ResetForm(data={"login_email": email})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["user"] == user


@pytest.mark.django_db
def test_reset_form_clean_sets_user_none_when_email_not_found():
    UserFactory(email="other@example.com")

    form = ResetForm(data={"login_email": "nonexistent@example.com"})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["user"] is None


@pytest.mark.parametrize("email", ("not-an-email", ""))
@pytest.mark.django_db
def test_reset_form_rejects_invalid_email(email):
    form = ResetForm(data={"login_email": email})

    assert not form.is_valid()
    assert "login_email" in form.errors


def test_recover_form_valid_matching_passwords():
    form = RecoverForm(
        data={"password": "mysecurepassword1!", "password_repeat": "mysecurepassword1!"}
    )

    assert form.is_valid(), form.errors


def test_recover_form_rejects_mismatched_passwords():
    form = RecoverForm(
        data={
            "password": "mysecurepassword1!",
            "password_repeat": "differentpassword1!",
        }
    )

    assert not form.is_valid()
    assert "password_repeat" in form.errors


def test_recover_form_accepts_empty_passwords():
    """Both password fields are required=False, so empty values are allowed."""
    form = RecoverForm(data={"password": "", "password_repeat": ""})

    assert form.is_valid(), form.errors


def test_recover_form_rejects_common_password():
    """Django's password validators reject common passwords."""
    form = RecoverForm(data={"password": "password", "password_repeat": "password"})

    assert not form.is_valid()
    assert "password" in form.errors
