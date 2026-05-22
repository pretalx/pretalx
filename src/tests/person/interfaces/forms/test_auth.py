# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django.core import mail as djmail
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from pretalx.person.interfaces.forms import (
    LoginInfoForm,
    RecoverForm,
    ResetForm,
    UserForm,
)
from pretalx.person.interfaces.forms.auth import get_client_ip
from pretalx.person.models import User
from tests.factories import UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("forwarded_for", "expected"),
    (
        ("10.0.0.1, 10.0.0.2", "10.0.0.1"),
        ("10.0.0.1", "10.0.0.1"),
        ("  10.0.0.1  , 10.0.0.2", "10.0.0.1"),
    ),
)
def test_get_client_ip_from_x_forwarded_for(forwarded_for, expected):
    request = RequestFactory().get("/")
    request.META["HTTP_X_FORWARDED_FOR"] = forwarded_for

    assert get_client_ip(request) == expected


def test_get_client_ip_no_forwarded_for_falls_back_to_remote_addr():
    request = RequestFactory().get("/")
    request.META.pop("HTTP_X_FORWARDED_FOR", None)
    request.META["REMOTE_ADDR"] = "127.0.0.1"

    assert get_client_ip(request) == "127.0.0.1"


def test_login_info_form_init_sets_initial_email():
    user = UserFactory(email="test@example.com")

    form = LoginInfoForm(user=user)

    assert form.user == user
    assert form.initial["email"] == "test@example.com"


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


@pytest.mark.parametrize(
    ("existing_email", "submitted_email"),
    (
        ("taken@example.com", "taken@example.com"),
        ("taken@example.com", "Taken@Example.com"),
    ),
    ids=("exact_match", "submitted_mixed_case"),
)
def test_login_info_form_rejects_email_taken_by_other_user(
    existing_email, submitted_email
):
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


def test_login_info_form_allows_own_email():
    user = UserFactory(email="mine@example.com")
    data = {
        "email": "mine@example.com",
        "old_password": "testpassword!",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)

    assert form.is_valid(), form.errors


def test_login_info_form_skips_uniqueness_check_when_email_invalid():
    """When the email field fails its own validation (e.g. malformed input),
    cleaned_data has no ``email`` key, so the uniqueness probe is skipped."""
    user = UserFactory()
    data = {
        "email": "not-an-email",
        "old_password": "testpassword!",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)

    assert not form.is_valid()
    assert "email" in form.errors
    assert "email" not in form.cleaned_data


def test_login_info_form_surfaces_email_and_password_errors_together():
    """Email validation must not short-circuit password mismatch reporting."""
    UserFactory(email="taken@example.com")
    user = UserFactory()
    data = {
        "email": "taken@example.com",
        "old_password": "testpassword!",
        "password": "NewStr0ngP@ss!",
        "password_repeat": "DifferentP@ss!",
    }

    form = LoginInfoForm(user=user, data=data)

    assert not form.is_valid()
    assert "email" in form.errors
    assert "password_repeat" in form.errors


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


def test_user_form_get_context_includes_display_options(rf):
    request = rf.get("/")
    form = UserForm(
        request=request,
        hide_login=True,
        hide_register=True,
        no_buttons=True,
        password_reset_link="/reset",
        success_url="/done",
    )

    context = form.get_context()

    assert context["hide_login"] is True
    assert context["hide_register"] is True
    assert context["no_buttons"] is True
    assert context["password_reset_link"] == "/reset"
    assert context["success_url"] == "/done"


def test_user_form_render_includes_form_fields(rf):
    request = rf.get("/")
    request.user = AnonymousUser()
    form = UserForm(request=request)
    renderer = form.default_renderer()

    html = form.render(renderer=renderer)

    assert "login_email" in html
    assert "login_password" in html


def test_user_form_ratelimit_key_none_without_request():
    form = UserForm()

    assert form.ratelimit_key is None


@pytest.mark.parametrize(
    "remote_addr",
    (
        pytest.param("192.168.1.1", id="private_ip"),
        pytest.param("not-an-ip", id="invalid_ip"),
        pytest.param(None, id="no_ip"),
    ),
)
def test_user_form_ratelimit_key_none_for_non_ratelimitable_ip(rf, remote_addr):
    request = rf.post("/login/")
    if remote_addr is not None:
        request.META["REMOTE_ADDR"] = remote_addr
    else:
        request.META.pop("REMOTE_ADDR", None)
    form = UserForm(request=request)

    assert form.ratelimit_key is None


def test_user_form_ratelimit_key_for_public_ip(rf):
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"
    form = UserForm(request=request)

    assert form.ratelimit_key == "pretalx_login_8.8.8.8"


@pytest.mark.parametrize(
    "login_email",
    (
        pytest.param("test@example.com", id="exact_match"),
        pytest.param("TEST@EXAMPLE.COM", id="case_insensitive"),
    ),
)
def test_user_form_clean_login_succeeds(rf, login_email):
    user = UserFactory(email="test@example.com", password="Str0ngP@ss!")
    form = UserForm(
        data={"login_email": login_email, "login_password": "Str0ngP@ss!"},
        request=rf.post("/login/"),
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["user_id"] == user.pk


def test_user_form_clean_login_fails_with_wrong_password(rf):
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "wrongpassword"},
        request=rf.post("/login/"),
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_user_form_clean_login_fails_with_nonexistent_email(rf):
    """Login with a non-existent email fails without revealing whether the
    account exists (timing attack prevention)."""
    form = UserForm(
        data={"login_email": "nobody@example.com", "login_password": "anypassword"},
        request=rf.post("/login/"),
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_user_form_clean_login_fails_for_inactive_user(rf):
    UserFactory(email="test@example.com", password="Str0ngP@ss!", is_active=False)
    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
        request=rf.post("/login/"),
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.usefixtures("locmem_cache")
def test_user_form_clean_rate_limit_blocks_over_threshold(rf):
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"
    cache.set("pretalx_login_8.8.8.8", 11, 300)

    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "wrongpwd"},
        request=request,
    )

    assert not form.is_valid()
    assert form.errors.as_data()["__all__"][0].code == "rate_limit"


@pytest.mark.usefixtures("locmem_cache")
def test_user_form_clean_rate_limit_allows_under_threshold(rf):
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"
    cache.set("pretalx_login_8.8.8.8", 5, 300)

    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
        request=request,
    )

    assert form.is_valid(), form.errors


@pytest.mark.usefixtures("locmem_cache")
def test_user_form_clean_no_rate_limit_for_private_ip(rf):
    """Private IPs are not rate-limited even when the counter is high,
    to avoid blocking users behind a misconfigured reverse proxy."""
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "192.168.1.1"
    cache.set("pretalx_login_192.168.1.1", 99, 300)

    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "wrongpwd"},
        request=request,
    )
    form.is_valid()

    assert not any(
        e.code == "rate_limit" for e in form.errors.as_data().get("__all__", [])
    )


@pytest.mark.usefixtures("locmem_cache")
def test_user_form_clean_login_failure_increments_rate_limit_counter(rf):
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"
    cache.set("pretalx_login_8.8.8.8", 2, 300)

    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "wrongpwd"},
        request=request,
    )
    assert not form.is_valid()

    assert cache.get("pretalx_login_8.8.8.8") == 3


@pytest.mark.usefixtures("locmem_cache")
def test_user_form_clean_login_failure_initialises_counter(rf):
    """When no rate limit key exists yet, a failed login creates one."""
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"
    cache.delete("pretalx_login_8.8.8.8")

    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "wrongpwd"},
        request=request,
    )
    assert not form.is_valid()

    assert cache.get("pretalx_login_8.8.8.8") == 1


@pytest.mark.usefixtures("locmem_cache")
def test_user_form_clean_login_success_does_not_increment_counter(rf):
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"
    cache.set("pretalx_login_8.8.8.8", 5, 300)

    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
        request=request,
    )
    assert form.is_valid(), form.errors

    assert cache.get("pretalx_login_8.8.8.8") == 5


@override_settings(
    AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.AllowAllUsersModelBackend"]
)
def test_user_form_clean_login_rejects_inactive_user_with_permissive_backend(rf):
    """When the auth backend allows inactive users to authenticate,
    the form still rejects them."""
    UserFactory(email="test@example.com", password="Str0ngP@ss!", is_active=False)
    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
        request=rf.post("/login/"),
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_user_form_clean_register_succeeds_with_valid_data(rf):
    form = UserForm(
        data={
            "register_name": "New User",
            "register_email": "new@example.com",
            "register_password": "Str0ngP@ss!",
            "register_password_repeat": "Str0ngP@ss!",
        },
        request=rf.post("/register/"),
    )

    assert form.is_valid(), form.errors


def test_user_form_clean_register_rejects_password_mismatch(rf):
    form = UserForm(
        data={
            "register_name": "New User",
            "register_email": "new@example.com",
            "register_password": "Str0ngP@ss!",
            "register_password_repeat": "DifferentP@ss!",
        },
        request=rf.post("/register/"),
    )

    assert not form.is_valid()
    assert "register_password_repeat" in form.errors


@pytest.mark.parametrize(
    "existing_email",
    (
        pytest.param("existing@example.com", id="exact_match"),
        pytest.param("Existing@Example.com", id="case_insensitive"),
    ),
)
def test_user_form_clean_register_rejects_duplicate_email(rf, existing_email):
    UserFactory(email=existing_email)
    form = UserForm(
        data={
            "register_name": "New User",
            "register_email": "existing@example.com",
            "register_password": "Str0ngP@ss!",
            "register_password_repeat": "Str0ngP@ss!",
        },
        request=rf.post("/register/"),
    )

    assert not form.is_valid()
    assert "register_email" in form.errors


@pytest.mark.parametrize(
    "data",
    (
        pytest.param({"login_email": "test@example.com"}, id="incomplete"),
        pytest.param({}, id="empty"),
    ),
)
def test_user_form_clean_rejects_insufficient_data(rf, data):
    """Neither login nor register fields are fully filled."""
    form = UserForm(data=data, request=rf.post("/login/"))

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_user_form_save_returns_user_id_for_login(rf):
    user = UserFactory(email="test@example.com", password="Str0ngP@ss!")
    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
        request=rf.post("/login/"),
    )
    assert form.is_valid(), form.errors

    result = form.save()

    assert result == user.pk


def test_user_form_save_creates_user_for_registration(rf):
    form = UserForm(
        data={
            "register_name": "New Speaker",
            "register_email": "speaker@example.com",
            "register_password": "Str0ngP@ss!",
            "register_password_repeat": "Str0ngP@ss!",
        },
        request=rf.post("/register/"),
    )
    assert form.is_valid(), form.errors

    result = form.save()

    user = User.objects.get(pk=result)
    assert user.name == "New Speaker"
    assert user.email == "speaker@example.com"
    assert user.check_password("Str0ngP@ss!")


def test_user_form_save_strips_registration_fields(rf):
    """Name is stripped and email is lowercased and stripped on save."""
    form = UserForm(
        data={
            "register_name": "  Padded Name  ",
            "register_email": "UPPER@Example.COM",
            "register_password": "Str0ngP@ss!",
            "register_password_repeat": "Str0ngP@ss!",
        },
        request=rf.post("/register/"),
    )
    assert form.is_valid(), form.errors

    result = form.save()

    user = User.objects.get(pk=result)
    assert user.name == "Padded Name"
    assert user.email == "upper@example.com"


def test_user_form_save_sets_locale_and_timezone(rf):
    form = UserForm(
        data={
            "register_name": "New User",
            "register_email": "new@example.com",
            "register_password": "Str0ngP@ss!",
            "register_password_repeat": "Str0ngP@ss!",
        },
        request=rf.post("/register/"),
    )
    assert form.is_valid(), form.errors

    result = form.save()

    user = User.objects.get(pk=result)
    assert user.locale == "en"
    assert user.timezone == "UTC"


@pytest.mark.parametrize(
    "email",
    ("speaker@example.com", "SPEAKER@example.com"),
    ids=["exact", "case_insensitive"],
)
def test_reset_form_clean_sets_user_when_email_exists(email):
    user = UserFactory(email="speaker@example.com")

    form = ResetForm(data={"login_email": email})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["user"] == user


def test_reset_form_clean_sets_user_none_when_email_not_found():
    UserFactory(email="other@example.com")

    form = ResetForm(data={"login_email": "nonexistent@example.com"})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["user"] is None


@pytest.mark.parametrize("email", ("not-an-email", ""))
def test_reset_form_rejects_invalid_email(email):
    form = ResetForm(data={"login_email": email})

    assert not form.is_valid()
    assert "login_email" in form.errors


def test_recover_form_prefills_email_from_user():
    user = UserFactory(email="speaker@example.com")

    form = RecoverForm(user=user)

    assert form.initial["email"] == "speaker@example.com"
    assert form.fields["email"].widget.attrs["autocomplete"] == "username"
    assert form.fields["email"].widget.attrs["readonly"] == "readonly"


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
