"""Registration is only possible through pretix on SSO-enabled events.

These go through the full request stack (middleware, pretalx views, templates),
because they depend on how pretalx renders and handles its own forms."""

import re

import pytest
from django.test import Client

from pretalx.event.domain.plugins import disable_plugin
from pretalx.person.models import User

REGISTRATION = {
    "register_name": "Someone",
    "register_email": "someone@example.invalid",
    "register_password": "A-long-test-passphrase-123",
    "register_password_repeat": "A-long-test-passphrase-123",
}


@pytest.fixture
def client(event):
    event.is_public = True
    event.save()
    return Client(HTTP_HOST="pretalx.example.invalid")


def _sso_mode(html):
    # pretalx minifies its HTML, which reorders attributes and drops quotes
    tag = re.search(r'<meta[^>]*name="?pretix-sso-login[">\s][^>]*>', html)
    match = tag and re.search(r'data-exclusive="?(\w*)', tag.group(0))
    return match.group(1) if match else None


def _wizard_user_step(client, event):
    start = client.get(f"/{event.slug}/submit/", secure=True, follow=True)
    tmpid = start.redirect_chain[-1][0].split("/")[3]
    return f"/{event.slug}/submit/{tmpid}/user/"


def test_login_page_offers_pretix_and_hides_registration(client, event):
    html = client.get(f"/{event.slug}/login/", secure=True).content.decode()
    assert _sso_mode(html) == "register"


def test_wizard_account_step_is_pretix_only(client, event):
    url = _wizard_user_step(client, event)
    html = client.get(url, secure=True).content.decode()
    assert _sso_mode(html) == "all"
    assert "next=" in html  # comes back to the wizard after logging in


def test_no_sso_button_on_other_pages(client, event):
    html = client.get(f"/{event.slug}/", secure=True).content.decode()
    assert _sso_mode(html) is None


def test_registration_on_login_page_is_refused(client, event):
    response = client.post(f"/{event.slug}/login/", REGISTRATION, secure=True)
    assert response.status_code == 302
    assert not User.objects.filter(email="someone@example.invalid").exists()


def test_password_login_still_works(client, event, make_speaker):
    make_speaker("speaker@example.invalid", password="speaker-pw")
    response = client.post(
        f"/{event.slug}/login/",
        {"login_email": "speaker@example.invalid", "login_password": "speaker-pw"},
        secure=True,
    )
    assert response.status_code == 302
    assert client.session.get("_auth_user_id")


def test_registration_in_wizard_is_refused(client, event):
    url = _wizard_user_step(client, event)
    client.post(url, REGISTRATION, secure=True)
    assert not User.objects.filter(email="someone@example.invalid").exists()
    assert not client.session.get("_auth_user_id")


def test_registration_allowed_when_plugin_disabled(client, event):
    disable_plugin(event, "pretalx_pretix_sso")
    html = client.get(f"/{event.slug}/login/", secure=True).content.decode()
    assert _sso_mode(html) is None
    client.post(f"/{event.slug}/login/", REGISTRATION, secure=True)
    assert User.objects.filter(email="someone@example.invalid").exists()


def test_migrations_are_up_to_date():
    from django.core.management import call_command

    call_command("makemigrations", "pretalx_pretix_sso", "--check", "--dry-run", verbosity=0)


def test_plugin_version_comes_from_pyproject():
    import re
    from pathlib import Path

    from pretalx_pretix_sso.apps import PluginApp

    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text()
    expected = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M).group(1)
    assert PluginApp.PretalxPluginMeta.version == expected


def test_installed_pretalx_is_in_supported_range():
    import re
    from importlib import metadata
    from pathlib import Path

    from packaging.requirements import Requirement

    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text()
    deps = re.search(r"^dependencies\s*=\s*\[(.*?)\]", pyproject, re.M | re.S).group(1)
    pretalx = next(
        Requirement(dep) for dep in re.findall(r'"([^"]+)"', deps) if dep.startswith("pretalx")
    )
    installed = metadata.version("pretalx")
    assert pretalx.specifier.contains(installed), (
        f"pretalx {installed} is outside the supported range {pretalx.specifier}: "
        "check restrict.py and the wizard step workaround, then widen the range"
    )
