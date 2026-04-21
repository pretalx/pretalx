# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from types import SimpleNamespace

import pytest

from pretalx.common.templatetags.thumbnail import thumbnail
from tests.factories import ProfilePictureFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_thumbnail_returns_url_for_valid_image(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())

    result = thumbnail(pic.avatar, "default")

    assert result == pic.avatar.url


@pytest.mark.parametrize("value", (None, "not-a-field"))
def test_thumbnail_returns_none_for_invalid_input(value):
    """Invalid inputs (None, plain string) have no .url fallback, so None is returned."""
    assert thumbnail(value, "default") is None


def test_thumbnail_falls_back_to_field_url_on_error():
    """When get_thumbnail raises but the field itself has a .url attribute
    (e.g. a bare ImageFieldFile without a resolvable instance), we return
    that url so the image still renders."""
    fake_field = SimpleNamespace(url="/media/fallback.png")

    assert thumbnail(fake_field, "default") == "/media/fallback.png"
