import pytest
from django.core import mail as djmail

from pretalx.person.forms import LoginInfoForm
from tests.factories import UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_login_info_form_init_sets_initial_email():
    user = UserFactory(email="test@example.com")

    form = LoginInfoForm(user=user)

    assert form.user == user
    assert form.initial["email"] == "test@example.com"


@pytest.mark.django_db
def test_login_info_form_clean_old_password_accepts_correct_password():
    user = UserFactory(password="correcthorse")
    data = {
        "email": user.email,
        "old_password": "correcthorse",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_login_info_form_clean_old_password_rejects_wrong_password():
    user = UserFactory(password="correcthorse")
    data = {
        "email": user.email,
        "old_password": "wrongpassword",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)

    assert not form.is_valid()
    assert "old_password" in form.errors
    assert form.errors.as_data()["old_password"][0].code == "pw_current_wrong"


@pytest.mark.django_db
def test_login_info_form_clean_email_accepts_unique_email():
    user = UserFactory()
    data = {
        "email": "unique@example.com",
        "old_password": "testpassword!",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["email"] == "unique@example.com"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("existing_email", "submitted_email"),
    (
        ("taken@example.com", "taken@example.com"),
        ("Taken@Example.com", "taken@example.com"),
    ),
    ids=("exact_match", "case_insensitive"),
)
def test_login_info_form_clean_email_rejects_duplicate_email(
    existing_email, submitted_email
):
    """clean_email raises a validation error when another user has the same
    email, including case-insensitive matches."""
    UserFactory(email=existing_email)
    user = UserFactory()
    data = {
        "email": submitted_email,
        "old_password": "testpassword!",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)

    assert not form.is_valid()
    assert "email" in form.errors


@pytest.mark.django_db
def test_login_info_form_clean_email_allows_own_email():
    """A user can keep their own email address."""
    user = UserFactory(email="mine@example.com")
    data = {
        "email": "mine@example.com",
        "old_password": "testpassword!",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_login_info_form_clean_rejects_mismatched_passwords():
    user = UserFactory()
    data = {
        "email": user.email,
        "old_password": "testpassword!",
        "password": "NewStr0ngP@ss!",
        "password_repeat": "DifferentP@ss!",
    }

    form = LoginInfoForm(user=user, data=data)

    assert not form.is_valid()
    assert "password_repeat" in form.errors


@pytest.mark.django_db
def test_login_info_form_clean_accepts_matching_passwords():
    user = UserFactory()
    new_pw = "NewStr0ngP@ss!"
    data = {
        "email": user.email,
        "old_password": "testpassword!",
        "password": new_pw,
        "password_repeat": new_pw,
    }

    form = LoginInfoForm(user=user, data=data)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_login_info_form_save_changes_email():
    djmail.outbox = []
    user = UserFactory(email="old@example.com")
    data = {
        "email": "new@example.com",
        "old_password": "testpassword!",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)
    assert form.is_valid(), form.errors
    form.save()

    user.refresh_from_db()
    assert user.email == "new@example.com"
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["old@example.com"]
    assert "old@example.com" in djmail.outbox[0].body
    assert "new@example.com" in djmail.outbox[0].body


@pytest.mark.django_db
def test_login_info_form_save_changes_password():
    djmail.outbox = []
    user = UserFactory()
    new_pw = "NewStr0ngP@ss!"
    data = {
        "email": user.email,
        "old_password": "testpassword!",
        "password": new_pw,
        "password_repeat": new_pw,
    }

    form = LoginInfoForm(user=user, data=data)
    assert form.is_valid(), form.errors
    form.save()

    user.refresh_from_db()
    assert user.check_password(new_pw)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    assert "password" in djmail.outbox[0].subject.lower()


@pytest.mark.django_db
def test_login_info_form_save_no_changes_when_only_old_password():
    """save() does not change email or password when neither is modified."""
    djmail.outbox = []
    user = UserFactory(email="keep@example.com")
    original_password = user.password
    data = {
        "email": "keep@example.com",
        "old_password": "testpassword!",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)
    assert form.is_valid(), form.errors
    form.save()

    user.refresh_from_db()
    assert user.email == "keep@example.com"
    assert user.password == original_password
    assert len(djmail.outbox) == 0
