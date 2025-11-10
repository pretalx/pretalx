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


@pytest.mark.django_db
def test_get_instance_data(submission):
    with scope(event=submission.event):
        data = submission._get_instance_data()
        assert data["title"] == submission.title
        assert data["state"] == submission.state
        assert data["submission_type"] == submission.submission_type.pk
        assert "created" not in data
        assert "updated" not in data


@pytest.mark.django_db
def test_compute_changes(submission):
    old_data = {"title": "Old Title", "state": "submitted", "track": None}
    new_data = {"title": "New Title", "state": "submitted", "track": 1}

    changes = submission._compute_changes(old_data, new_data)

    assert changes["title"]["old"] == "Old Title"
    assert changes["title"]["new"] == "New Title"
    assert "state" not in changes
    assert "track" in changes
    assert changes["track"]["old"] is None
    assert changes["track"]["new"] == 1


@pytest.mark.django_db
def test_compute_changes_no_changes(submission):
    data = {"title": "Same Title", "state": "submitted"}
    changes = submission._compute_changes(data, data)
    assert changes == {}


@pytest.mark.django_db
def test_log_action_with_changes(submission):
    with scope(event=submission.event):
        old_data = {"title": "Old Title", "state": "submitted"}
        new_data = {"title": "New Title", "state": "submitted"}

        submission.log_action("test.update", old_data=old_data, new_data=new_data)

        log = submission.logged_actions().get(action_type="test.update")
        assert "changes" in log.json_data
        assert "title" in log.json_data["changes"]
        assert log.json_data["changes"]["title"]["old"] == "Old Title"
        assert log.json_data["changes"]["title"]["new"] == "New Title"
        assert "state" not in log.json_data["changes"]


@pytest.mark.django_db
def test_log_action_no_changes_skips_log(submission):
    with scope(event=submission.event):
        initial_count = submission.logged_actions().count()
        data = {"title": "Same Title", "state": "submitted"}
        submission.log_action("test.update", old_data=data, new_data=data)
        assert submission.logged_actions().count() == initial_count


@pytest.mark.django_db
def test_log_action_no_changes_with_explicit_data_still_logs(submission):
    with scope(event=submission.event):
        data = {"title": "Same Title", "state": "submitted"}
        submission.log_action(
            "test.update", data={"custom": "info"}, old_data=data, new_data=data
        )

        log = submission.logged_actions().get(action_type="test.update")
        assert log.json_data["custom"] == "info"
        assert "changes" not in log.json_data


@pytest.mark.django_db
def test_log_action_changes_with_additional_data(submission):
    with scope(event=submission.event):
        old_data = {"title": "Old Title"}
        new_data = {"title": "New Title"}

        submission.log_action(
            "test.update",
            data={"reason": "user requested"},
            old_data=old_data,
            new_data=new_data,
        )

        log = submission.logged_actions().get(action_type="test.update")
        assert "changes" in log.json_data
        assert "reason" in log.json_data
        assert log.json_data["reason"] == "user requested"
        assert log.json_data["changes"]["title"]["old"] == "Old Title"
