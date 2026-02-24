import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import override_settings

from pretalx.person.forms.user import UserForm
from pretalx.person.models import User
from tests.factories import UserFactory

pytestmark = pytest.mark.unit


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


@override_settings(HAS_REDIS=False)
def test_user_form_ratelimit_key_none_without_redis(rf):
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"
    form = UserForm(request=request)

    assert form.ratelimit_key is None


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
@override_settings(HAS_REDIS=True)
def test_user_form_ratelimit_key_none_for_non_ratelimitable_ip(rf, remote_addr):
    request = rf.post("/login/")
    if remote_addr is not None:
        request.META["REMOTE_ADDR"] = remote_addr
    else:
        request.META.pop("REMOTE_ADDR", None)
    form = UserForm(request=request)

    assert form.ratelimit_key is None


@override_settings(HAS_REDIS=True)
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
@pytest.mark.django_db
def test_user_form_clean_login_succeeds(rf, login_email):
    user = UserFactory(email="test@example.com", password="Str0ngP@ss!")
    form = UserForm(
        data={"login_email": login_email, "login_password": "Str0ngP@ss!"},
        request=rf.post("/login/"),
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["user_id"] == user.pk


@pytest.mark.django_db
def test_user_form_clean_login_fails_with_wrong_password(rf):
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "wrongpassword"},
        request=rf.post("/login/"),
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.django_db
def test_user_form_clean_login_fails_with_nonexistent_email(rf):
    """Login with a non-existent email fails without revealing whether the
    account exists (timing attack prevention)."""
    form = UserForm(
        data={"login_email": "nobody@example.com", "login_password": "anypassword"},
        request=rf.post("/login/"),
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.django_db
def test_user_form_clean_login_fails_for_inactive_user(rf):
    UserFactory(email="test@example.com", password="Str0ngP@ss!", is_active=False)
    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
        request=rf.post("/login/"),
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.django_db
@pytest.mark.usefixtures("locmem_cache")
@override_settings(HAS_REDIS=True)
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


@pytest.mark.django_db
@pytest.mark.usefixtures("locmem_cache")
@override_settings(HAS_REDIS=True)
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


@pytest.mark.django_db
@pytest.mark.usefixtures("locmem_cache")
@override_settings(HAS_REDIS=True)
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


@pytest.mark.django_db
@pytest.mark.usefixtures("locmem_cache")
@override_settings(HAS_REDIS=True)
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


@pytest.mark.django_db
@pytest.mark.usefixtures("locmem_cache")
@override_settings(HAS_REDIS=True)
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


@pytest.mark.django_db
@pytest.mark.usefixtures("locmem_cache")
@override_settings(HAS_REDIS=True)
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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
@pytest.mark.django_db
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


@pytest.mark.django_db
def test_user_form_save_returns_user_id_for_login(rf):
    user = UserFactory(email="test@example.com", password="Str0ngP@ss!")
    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
        request=rf.post("/login/"),
    )
    assert form.is_valid(), form.errors

    result = form.save()

    assert result == user.pk


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_user_form_save_sets_locale_and_timezone(rf):
    """save() sets the user's locale and timezone from the current context."""
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


@pytest.mark.django_db
def test_user_form_save_raises_on_empty_registration_data(rf):
    """save() raises ValidationError when registration data is unexpectedly
    empty despite having passed clean()."""
    form = UserForm(
        data={
            "register_name": "Test",
            "register_email": "test@example.com",
            "register_password": "Str0ngP@ss!",
            "register_password_repeat": "Str0ngP@ss!",
        },
        request=rf.post("/register/"),
    )
    assert form.is_valid(), form.errors
    # Simulate the edge case where cleaned_data loses registration fields
    form.cleaned_data["register_email"] = ""

    with pytest.raises(ValidationError):
        form.save()
