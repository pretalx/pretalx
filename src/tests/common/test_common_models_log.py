# SPDX-FileCopyrightText: 2022-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope


@pytest.mark.django_db
def test_log_hides_password(submission):
    with scope(event=submission.event):
        submission.log_action(
            "test.hide", data={"password": "12345", "non-sensitive": "foo"}
        )
        log = submission.logged_actions().get(action_type="test.hide")
        assert log.json_data["password"] != "12345"
        assert log.json_data["non-sensitive"] == "foo"


@pytest.mark.django_db
def test_log_wrong_data(submission):
    with scope(event=submission.event), pytest.raises(TypeError):
        submission.log_action(
            "test.hide", data=[{"password": "12345", "non-sensitive": "foo"}]
        )
