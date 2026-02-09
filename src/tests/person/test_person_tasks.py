# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.person import tasks
from pretalx.person.models.picture import ProfilePicture


def mock_get_404(*args, **kwargs):
    class MockResponse:
        def __init__(self):
            self.status_code = 404

    return MockResponse()


@pytest.mark.django_db
def test_gravatar_refetch_called(user, caplog, mocker, event):
    picture = ProfilePicture.objects.create(user=user, get_gravatar=True)

    mocker.patch("pretalx.person.tasks.get", mock_get_404)
    mocker.patch("requests.get", mock_get_404)

    tasks.refetch_gravatars(sender=event)

    picture.refresh_from_db()
    assert picture.get_gravatar is False
    assert (
        f"gravatar returned http 404 when getting avatar for user {user.name}"
        in caplog.text
    )


@pytest.mark.django_db
def test_gravatar_refetch_via_task(user, caplog, mocker):
    picture = ProfilePicture.objects.create(user=user, get_gravatar=True)

    mocker.patch("pretalx.person.tasks.get", mock_get_404)
    mocker.patch("requests.get", mock_get_404)

    tasks.gravatar_cache(picture.pk)

    picture.refresh_from_db()
    assert picture.get_gravatar is False

    assert (
        f"gravatar returned http 404 when getting avatar for user {user.name}"
        in caplog.text
    )


@pytest.mark.django_db
def test_gravatar_refetch_on_picture_without_gravatar(user):
    picture = ProfilePicture.objects.create(user=user, get_gravatar=False)
    tasks.gravatar_cache(picture.pk)
    picture.refresh_from_db()
    assert picture.get_gravatar is False


@pytest.mark.django_db
def test_gravatar_refetch_on_missing_picture():
    tasks.gravatar_cache(99999)
