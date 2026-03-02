# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.serializers.log import ActivityLogSerializer, UserSerializer
from tests.factories import ActivityLogFactory, UserFactory
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_user_serializer_includes_code_and_name():
    user = UserFactory()
    serializer = UserSerializer(user, context={"request": make_api_request()})

    assert serializer.data == {"code": user.code, "name": user.name}


def test_activity_log_serializer_data():
    log = ActivityLogFactory(
        data={"changes": {"title": {"old": "A", "new": "B"}}}, is_orga_action=True
    )
    serializer = ActivityLogSerializer(
        log, context={"request": make_api_request(event=log.event)}
    )

    data = serializer.data
    assert set(data.keys()) == {
        "id",
        "timestamp",
        "action_type",
        "is_orga_action",
        "person",
        "display",
        "data",
    }
    assert data["person"] == {"code": log.person.code, "name": log.person.name}
    assert data["action_type"] == "pretalx.submission.create"
    assert data["is_orga_action"] is True
    assert data["data"] == {"changes": {"title": {"old": "A", "new": "B"}}}
