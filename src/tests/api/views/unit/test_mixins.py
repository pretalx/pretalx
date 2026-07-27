# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.versions import CURRENT_VERSION
from pretalx.api.views.mixins import ApiVersionException
from pretalx.api.views.room import RoomViewSet
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


def test_get_versioned_serializer_rejects_unregistered_serializer():
    view = make_view(RoomViewSet, make_api_request())
    view.api_version = CURRENT_VERSION

    with pytest.raises(ApiVersionException):
        view.get_versioned_serializer("NoSuchSerializer")
