# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core import mail as djmail
from django.core.cache import cache
from django.test import RequestFactory, override_settings
from django.utils.timezone import now

from pretalx.common.domain.queries.log import actions_by
from pretalx.person.domain.verification import request_email_change
from pretalx.person.enums import EmailVerificationState
from pretalx.person.interfaces.forms import (
    EmailCorrectionForm,
    LoginInfoForm,
    ReauthForm,
    RecoverForm,
    ResetForm,
    SpeakerLoginInfoForm,
    UserForm,
)
from pretalx.person.interfaces.forms.auth import get_client_ip
from pretalx.person.models import User
from tests.factories import SpeakerFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

LOGIN_INFO_DATA = {
    "email": "mine@example.com",
    "old_password": "correcthorse",
    "password": "",
    "password_repeat": "",
}
REGISTER_DATA = {
    "register_name": "New User",
    "register_email": "new@example.com",
    "register_password": "Str0ngP@ss!",
    "register_password_repeat": "Str0ngP@ss!",
}


def _ip_request(forwarded_for=None, remote_addr="203.0.113.7"):
    request = RequestFactory().post("/login/")
    if remote_addr is not None:
        request.META["REMOTE_ADDR"] = remote_addr
    else:
        request.META.pop("REMOTE_ADDR", None)
    if forwarded_for is not None:
        request.META["HTTP_X_FORWARDED_FOR"] = forwarded_for
    else:
        request.META.pop("HTTP_X_FORWARDED_FOR", None)
    return request


def _error_codes(form):
    return {
        field: [error.code for error in errors]
        for field, errors in form.errors.as_data().items()
    }


@pytest.mark.parametrize(
    ("proxy_count", "forwarded_for", "expected"),
    (
        (1, "8.8.8.8", "8.8.8.8"),
        (1, "  8.8.8.8  ", "8.8.8.8"),
        (1, "1.2.3.4, 8.8.8.8", "8.8.8.8"),
        (1, "10.0.0.1, 1.2.3.4, 8.8.8.8", "8.8.8.8"),
        (2, "1.2.3.4, 9.9.9.9", "1.2.3.4"),
        (2, "junk, 1.2.3.4, 9.9.9.9", "1.2.3.4"),
        (2, "  8.8.8.8 , 1.2.3.4 , 9.9.9.9 ", "1.2.3.4"),
        (2, "8.8.8.8", "203.0.113.7"),
        (0, "1.2.3.4, 8.8.8.8", "203.0.113.7"),
        (1, None, "203.0.113.7"),
        (1, "", "203.0.113.7"),
        (1, "   ", "203.0.113.7"),
        (1, " , ", "203.0.113.7"),
    ),
)
def test_get_client_ip_counts_trusted_proxies_from_the_right(
    settings, proxy_count, forwarded_for, expected
):
    settings.TRUSTED_PROXY_COUNT = proxy_count

    assert get_client_ip(_ip_request(forwarded_for)) == expected


def test_login_info_form_init_sets_initial_email():
    user = UserFactory(email="test@example.com")

    form = LoginInfoForm(user=user)

    assert form.user == user
    assert form.initial["email"] == "test@example.com"


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        ({}, {}),
        ({"old_password": "wrongpassword"}, {"old_password": ["pw_current_wrong"]}),
        ({"email": "unique@example.com"}, {}),
        ({"email": "taken@example.com"}, {"email": [None]}),
        ({"email": "Taken@Example.com"}, {"email": [None]}),
        ({"email": "not-an-email"}, {"email": ["invalid"]}),
        (
            {"password": "NewStr0ngP@ss!", "password_repeat": "DifferentP@ss!"},
            {"password_repeat": [None]},
        ),
        (
            {
                "email": "taken@example.com",
                "password": "NewStr0ngP@ss!",
                "password_repeat": "DifferentP@ss!",
            },
            {"email": [None], "password_repeat": [None]},
        ),
        ({"password": "NewStr0ngP@ss!", "password_repeat": "NewStr0ngP@ss!"}, {}),
    ),
    ids=(
        "unchanged",
        "wrong_password",
        "unique_email",
        "taken_email",
        "taken_email_mixed_case",
        "invalid_email",
        "password_mismatch",
        "taken_email_and_password_mismatch",
        "matching_passwords",
    ),
)
def test_login_info_form_clean(data, errors):
    UserFactory(email="taken@example.com")
    user = UserFactory(email="mine@example.com", password="correcthorse")
    data = LOGIN_INFO_DATA | data

    form = LoginInfoForm(user=user, data=data)

    assert form.is_valid() == (not errors), form.errors
    assert _error_codes(form) == errors
    assert form.cleaned_data.get("email") == (
        None if "email" in errors else data["email"]
    )


def test_login_info_form_save_changes_password_then_defers_email_change():
    djmail.outbox = []
    user = UserFactory(email="mine@example.com", password="correcthorse")
    original_password = user.password

    unchanged = LoginInfoForm(user=user, data=LOGIN_INFO_DATA)
    assert unchanged.is_valid(), unchanged.errors
    unchanged.save()
    user.refresh_from_db()
    assert user.email == "mine@example.com"
    assert user.pending_email is None
    assert user.password == original_password
    assert unchanged.email_change_requested is False
    assert djmail.outbox == []

    new_pw = "NewStr0ngP@ss!"
    password_form = LoginInfoForm(
        user=user,
        data=LOGIN_INFO_DATA | {"password": new_pw, "password_repeat": new_pw},
    )
    assert password_form.is_valid(), password_form.errors
    password_form.save()
    user.refresh_from_db()
    assert user.check_password(new_pw)
    assert [(m.to, "password" in m.subject.lower()) for m in djmail.outbox] == [
        (["mine@example.com"], True)
    ]

    djmail.outbox = []
    email_form = LoginInfoForm(
        user=user,
        data=LOGIN_INFO_DATA | {"old_password": new_pw, "email": "new@example.com"},
    )
    assert email_form.is_valid(), email_form.errors
    email_form.save()
    user.refresh_from_db()
    assert user.email == "mine@example.com"
    assert user.pending_email == "new@example.com"
    assert user.pending_email_sent is not None
    assert email_form.email_change_requested is True
    assert [m.to for m in djmail.outbox] == [["new@example.com"], ["mine@example.com"]]
    assert "/orga/verify/" in djmail.outbox[0].body
    assert "new@example.com" in djmail.outbox[1].body
    action = (
        actions_by(user).filter(action_type="pretalx.user.email.change.request").get()
    )
    assert action.data == {"pending_email": "new@example.com"}


def test_login_info_form_send_cooldown_blocks_email_change_not_password_change():
    user = UserFactory(email="mine@example.com", password="correcthorse")
    request_email_change(user, "first@example.com")
    djmail.outbox = []
    new_pw = "NewStr0ngP@ss!"

    email_form = LoginInfoForm(
        user=user, data=LOGIN_INFO_DATA | {"email": "second@example.com"}
    )
    password_form = LoginInfoForm(
        user=user,
        data=LOGIN_INFO_DATA | {"password": new_pw, "password_repeat": new_pw},
    )

    assert not email_form.is_valid()
    assert _error_codes(email_form) == {"email": ["email_send_cooldown"]}
    assert password_form.is_valid(), password_form.errors
    user.refresh_from_db()
    assert user.pending_email == "first@example.com"
    assert djmail.outbox == []


def test_login_info_form_unverified_user_email_read_only():
    djmail.outbox = []
    user = UserFactory(
        email="unproven@example.com",
        email_verification_state=EmailVerificationState.UNVERIFIED,
    )
    data = {
        "email": "sneaky@example.com",
        "old_password": "testpassword!",
        "password": "",
        "password_repeat": "",
    }

    form = LoginInfoForm(user=user, data=data)

    assert form.fields["email"].disabled
    assert "/orga/verify/" in form.fields["email"].help_text
    assert form.is_valid(), form.errors
    form.save()
    user.refresh_from_db()
    assert user.email == "unproven@example.com"
    assert user.pending_email is None
    assert djmail.outbox == []


def test_login_info_form_pending_email_expired_property():
    user = UserFactory()
    user.pending_email = "pending@example.com"
    user.pending_email_sent = now() - dt.timedelta(hours=25)
    user.save()

    form = LoginInfoForm(user=user)

    assert form.pending_email_expired is True


def test_speaker_login_info_form_contact_email_changes_need_no_password():
    speaker = SpeakerFactory()
    data = {
        "email": speaker.user.email,
        "contact_email": "",
        "old_password": "",
        "password": "",
        "password_repeat": "",
    }

    set_form = SpeakerLoginInfoForm(
        speaker=speaker, data=data | {"contact_email": "contact@example.com"}
    )
    assert set_form.is_valid(), set_form.errors
    set_form.save()
    speaker.refresh_from_db(fields=["email"])
    assert speaker.email == "contact@example.com"

    unchanged = SpeakerLoginInfoForm(
        speaker=speaker, data=data | {"contact_email": "contact@example.com"}
    )
    assert unchanged.is_valid(), unchanged.errors
    assert unchanged.changed_data == []

    clear_form = SpeakerLoginInfoForm(speaker=speaker, data=data)
    assert clear_form.is_valid(), clear_form.errors
    clear_form.save()
    speaker.refresh_from_db(fields=["email"])
    assert speaker.email is None


@pytest.mark.parametrize(
    ("data", "code"),
    (
        ({"email": "new@example.com"}, "pw_current_required"),
        (
            {"password": "newpassword!!", "password_repeat": "newpassword!!"},
            "pw_current_required",
        ),
        (
            {"email": "new@example.com", "old_password": "wrongpassword"},
            "pw_current_wrong",
        ),
    ),
    ids=("email_without_password", "password_without_password", "wrong_password"),
)
def test_speaker_login_info_form_login_data_change_requires_current_password(
    data, code
):
    speaker = SpeakerFactory(user__password="correcthorse")
    data = {
        "email": speaker.user.email,
        "contact_email": "",
        "old_password": "",
        "password": "",
        "password_repeat": "",
    } | data

    form = SpeakerLoginInfoForm(speaker=speaker, data=data)

    assert not form.is_valid()
    assert _error_codes(form) == {"old_password": [code]}


def test_speaker_login_info_form_login_data_change_with_correct_password():
    djmail.outbox = []
    speaker = SpeakerFactory(user__password="correcthorse")
    original_email = speaker.user.email
    data = {
        "email": "new@example.com",
        "contact_email": "",
        "old_password": "correcthorse",
        "password": "",
        "password_repeat": "",
    }

    form = SpeakerLoginInfoForm(speaker=speaker, data=data)
    assert form.is_valid(), form.errors
    form.save()

    speaker.user.refresh_from_db()
    assert speaker.user.email == original_email
    assert speaker.user.pending_email == "new@example.com"
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].to == ["new@example.com"]
    assert f"/{speaker.event.slug}/verify/" in djmail.outbox[0].body


def test_speaker_login_info_form_unverified_user_keeps_verification_pointer():
    speaker = SpeakerFactory(
        user__email_verification_state=EmailVerificationState.UNVERIFIED
    )

    form = SpeakerLoginInfoForm(speaker=speaker)

    assert form.fields["email"].disabled
    assert f"/{speaker.event.slug}/verify/" in form.fields["email"].help_text


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

    assert context["request"] is request
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
    ("remote_addr", "forwarded_for", "expected"),
    (
        ("8.8.8.8", None, "pretalx_login_8.8.8.8"),
        ("127.0.0.1", "1.1.1.1, 8.8.8.8", "pretalx_login_8.8.8.8"),
        ("192.168.1.1", None, None),
        ("not-an-ip", None, None),
        (None, None, None),
    ),
    ids=("public_ip", "forwarded_public_ip", "private_ip", "invalid_ip", "no_ip"),
)
def test_user_form_ratelimit_key(remote_addr, forwarded_for, expected):
    form = UserForm(request=_ip_request(forwarded_for, remote_addr=remote_addr))

    assert form.ratelimit_key == expected


@pytest.mark.parametrize(
    ("data", "is_active", "valid"),
    (
        (
            {"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
            True,
            True,
        ),
        (
            {"login_email": "TEST@EXAMPLE.COM", "login_password": "Str0ngP@ss!"},
            True,
            True,
        ),
        (
            {"login_email": "test@example.com", "login_password": "wrongpassword"},
            True,
            False,
        ),
        (
            {"login_email": "nobody@example.com", "login_password": "anypassword"},
            True,
            False,
        ),
        (
            {"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
            False,
            False,
        ),
        ({"login_email": "test@example.com"}, True, False),
        ({}, True, False),
    ),
    ids=(
        "exact_match",
        "case_insensitive",
        "wrong_password",
        "nonexistent_email",
        "inactive_user",
        "incomplete",
        "empty",
    ),
)
def test_user_form_clean_login(rf, data, is_active, valid):
    user = UserFactory(
        email="test@example.com", password="Str0ngP@ss!", is_active=is_active
    )

    form = UserForm(data=data, request=rf.post("/login/"))

    assert form.is_valid() is valid, form.errors
    assert list(form.errors) == ([] if valid else ["__all__"])
    assert form.cleaned_data.get("user_id") == (user.pk if valid else None)
    assert form.is_registration is False


@override_settings(
    AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.AllowAllUsersModelBackend"]
)
def test_user_form_clean_login_rejects_inactive_user_with_permissive_backend(rf):
    UserFactory(email="test@example.com", password="Str0ngP@ss!", is_active=False)
    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "Str0ngP@ss!"},
        request=rf.post("/login/"),
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.parametrize(
    ("remote_addr", "count", "password", "errors", "expected_count"),
    (
        ("8.8.8.8", 11, "wrongpwd", {"__all__": ["rate_limit"]}, 11),
        ("8.8.8.8", 5, "Str0ngP@ss!", {}, 5),
        ("8.8.8.8", 2, "wrongpwd", {"__all__": [None]}, 3),
        ("192.168.1.1", 99, "wrongpwd", {"__all__": [None]}, 99),
    ),
    ids=("over_threshold", "success_keeps_count", "failure_increments", "private_ip"),
)
def test_user_form_login_rate_limit(
    rf, remote_addr, count, password, errors, expected_count
):
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    key = f"pretalx_login_{remote_addr}"
    cache.set(key, count, 300)

    form = UserForm(
        data={"login_email": "test@example.com", "login_password": password},
        request=_ip_request(remote_addr=remote_addr),
    )

    assert form.is_valid() == (not errors), form.errors
    assert _error_codes(form) == errors
    assert cache.get(key) == expected_count


def test_user_form_clean_login_failure_initialises_counter():
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    cache.delete("pretalx_login_8.8.8.8")

    form = UserForm(
        data={"login_email": "test@example.com", "login_password": "wrongpwd"},
        request=_ip_request(remote_addr="8.8.8.8"),
    )
    assert not form.is_valid()

    assert cache.get("pretalx_login_8.8.8.8") == 1


@pytest.mark.parametrize(
    ("data", "count", "errors", "expected_count"),
    (
        ({}, 2, {}, 2),
        (
            {"register_password_repeat": "DifferentP@ss!"},
            2,
            {"register_password_repeat": [None]},
            2,
        ),
        ({"register_email": "taken@example.com"}, 2, {"register_email": [None]}, 3),
        ({"register_email": "Taken@Example.com"}, 2, {"register_email": [None]}, 3),
        ({"register_email": "taken@example.com"}, 11, {"__all__": ["rate_limit"]}, 11),
    ),
    ids=(
        "valid",
        "password_mismatch",
        "taken_email_increments",
        "taken_email_mixed_case_increments",
        "rate_limited",
    ),
)
def test_user_form_clean_register(data, count, errors, expected_count):
    UserFactory(email="taken@example.com")
    cache.set("pretalx_login_8.8.8.8", count, 300)

    form = UserForm(
        data=REGISTER_DATA | data, request=_ip_request(remote_addr="8.8.8.8")
    )

    assert form.is_valid() == (not errors), form.errors
    assert _error_codes(form) == errors
    assert cache.get("pretalx_login_8.8.8.8") == expected_count


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        pytest.param(
            {
                "login_email": "test@example.com",
                "login_password": "Str0ngP@ss!",
                "register_email": "test@example.com",
            },
            False,
            id="login_with_autofilled_register_email",
        ),
        pytest.param(REGISTER_DATA, True, id="register"),
    ),
)
def test_user_form_is_registration_marks_only_the_register_branch(rf, data, expected):
    UserFactory(email="test@example.com", password="Str0ngP@ss!")
    form = UserForm(data=data, request=rf.post("/login/"))

    assert form.is_valid(), form.errors

    assert form.is_registration is expected


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
        data=REGISTER_DATA
        | {"register_name": "  Padded Name  ", "register_email": "UPPER@Example.COM"},
        request=rf.post("/register/"),
    )
    assert form.is_valid(), form.errors

    result = form.save()

    user = User.objects.get(pk=result)
    assert user.name == "Padded Name"
    assert user.email == "upper@example.com"
    assert user.check_password("Str0ngP@ss!")
    assert user.locale == "en"
    assert user.timezone == "UTC"


@pytest.mark.parametrize(
    ("email", "errors", "found"),
    (
        ("speaker@example.com", {}, True),
        ("SPEAKER@example.com", {}, True),
        ("nonexistent@example.com", {}, False),
        ("not-an-email", {"login_email": ["invalid"]}, False),
        ("", {"login_email": ["required"]}, False),
    ),
)
def test_reset_form_clean_looks_up_user_case_insensitively(email, errors, found):
    user = UserFactory(email="speaker@example.com")

    form = ResetForm(data={"login_email": email})

    assert form.is_valid() == (not errors), form.errors
    assert _error_codes(form) == errors
    assert form.cleaned_data.get("user") == (user if found else None)


def test_recover_form_prefills_email_from_user():
    user = UserFactory(email="speaker@example.com")

    form = RecoverForm(user=user)

    assert form.initial["email"] == "speaker@example.com"
    assert form.fields["email"].widget.attrs["autocomplete"] == "username"
    assert form.fields["email"].widget.attrs["readonly"] == "readonly"


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        (
            {"password": "mysecurepassword1!", "password_repeat": "mysecurepassword1!"},
            {},
        ),
        (
            {
                "password": "mysecurepassword1!",
                "password_repeat": "differentpassword1!",
            },
            {"password_repeat": [None]},
        ),
        (
            {"password": "", "password_repeat": ""},
            {"password": ["required"], "password_repeat": ["required"]},
        ),
        ({}, {"password": ["required"], "password_repeat": ["required"]}),
        (
            {"password": "mysecurepassword1!", "password_repeat": ""},
            {"password_repeat": ["required"]},
        ),
        (
            {"password": "password", "password_repeat": "password"},
            {"password": ["password_too_common"]},
        ),
    ),
    ids=("matching", "mismatch", "empty", "missing", "empty_repeat", "common_password"),
)
def test_recover_form_clean(data, errors):
    form = RecoverForm(data=data)

    assert form.is_valid() == (not errors), form.errors
    assert _error_codes(form) == errors


@pytest.mark.parametrize(
    ("data", "errors", "email"),
    (
        (
            {"email": " Fixed@Example.COM ", "password": "testpassword!"},
            {},
            "fixed@example.com",
        ),
        (
            {"email": "fixed@example.com", "password": "wrongpassword!"},
            {"password": ["pw_current_wrong"]},
            "fixed@example.com",
        ),
        ({"email": "", "password": "testpassword!"}, {"email": ["required"]}, None),
        (
            {"email": "taken@example.com", "password": "testpassword!"},
            {"email": [None]},
            None,
        ),
    ),
    ids=("normalises", "wrong_password", "missing_email", "taken_email"),
)
def test_email_correction_form_clean(data, errors, email):
    user = UserFactory(password="testpassword!")
    UserFactory(email="taken@example.com")

    form = EmailCorrectionForm(data, user=user)

    assert form.is_valid() == (not errors), form.errors
    assert _error_codes(form) == errors
    assert form.cleaned_data.get("email") == email


@pytest.mark.parametrize("orga", (True, False))
def test_user_form_keep_logged_in_field_only_on_orga_login(orga):
    form = UserForm(orga=orga)

    assert ("keep_logged_in" in form.fields) is orga


@pytest.mark.parametrize(
    ("password", "errors"),
    (
        ("correcthorse!", {}),
        ("wrong", {"password": ["The current password you entered was not correct."]}),
    ),
)
def test_reauth_form_checks_current_password(password, errors):
    user = UserFactory(password="correcthorse!")

    form = ReauthForm(data={"password": password}, user=user)

    assert form.is_valid() == (not errors)
    assert form.errors == errors
