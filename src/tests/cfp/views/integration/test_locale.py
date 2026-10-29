# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings
from django.urls import reverse
from django_scopes import scopes_disabled

from tests.factories import SpeakerFactory, UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_locale_set_sets_cookie_and_redirects_to_next(client, event):
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    response = client.get(f"{url}?locale=de&next=/{event.slug}/cfp")

    assert response.status_code == 302
    assert response.url == f"/{event.slug}/cfp"
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"


def test_locale_set_ignores_unknown_locale(client, event):
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    response = client.get(f"{url}?locale=xx")

    assert response.status_code == 302
    assert response.url == "/"
    assert settings.LANGUAGE_COOKIE_NAME not in response.cookies


def test_locale_set_updates_account_and_profile_locale(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    user = speaker.user
    client.force_login(user)
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    response = client.get(f"{url}?locale=de")

    assert response.status_code == 302
    user.refresh_from_db()
    with scopes_disabled():
        speaker.refresh_from_db()
    assert user.locale == "de"
    assert speaker.locale == "de"


def test_locale_set_without_profile_only_updates_account(client, event):
    user = UserFactory()
    client.force_login(user)
    url = reverse("cfp:locale.set", kwargs={"event": event.slug})

    response = client.get(f"{url}?locale=de")

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.locale == "de"
    with scopes_disabled():
        assert user.profiles.count() == 0


def test_locale_set_global_leaves_profile_locale(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    user = speaker.user
    client.force_login(user)

    response = client.get("/locale/set?locale=de")

    assert response.status_code == 302
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "de"
    user.refresh_from_db()
    with scopes_disabled():
        speaker.refresh_from_db()
    assert user.locale == "de"
    assert speaker.locale is None
