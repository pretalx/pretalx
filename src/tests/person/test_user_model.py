# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope, scopes_disabled

from pretalx.person.models.picture import ProfilePicture, picture_path
from pretalx.person.models.user import User
from pretalx.submission.models.question import Answer


@pytest.mark.django_db
def test_user_deactivate(speaker, personal_answer, impersonal_answer, other_speaker):
    with scopes_disabled():
        assert Answer.objects.count() == 2
        count = speaker.own_actions().count()
        name = speaker.name
        email = speaker.email
        organiser = speaker.profiles.first().submissions.first().event.organiser
        team = organiser.teams.first()
        team.members.add(speaker)
        team.save()
        team_members = team.members.count()
        speaker.deactivate()
        speaker.refresh_from_db()
        assert speaker.own_actions().count() == count
        assert speaker.profiles.first().biography == ""
        assert speaker.name != name
        assert speaker.email != email
        assert Answer.objects.count() == 1
        assert Answer.objects.first().question.contains_personal_data is False
        assert team.members.count() == team_members - 1
        assert "deleted" in str(speaker).lower()
        assert speaker.get_permissions_for_event(Answer.objects.first().event) == set()


@pytest.mark.django_db
def test_administrator_permissions(event):
    user = User(email="one@two.com", is_administrator=True)
    permission_set = {
        "can_create_events",
        "can_change_teams",
        "can_change_organiser_settings",
        "can_change_event_settings",
        "can_change_submissions",
        "is_reviewer",
    }
    assert user.get_permissions_for_event(event) == permission_set
    assert list(user.get_events_for_permission(can_change_submissions=True)) == [event]
    assert event in user.get_events_with_any_permission()


@pytest.mark.django_db
def test_organizer_permissions(event, orga_user):
    assert list(orga_user.get_events_with_any_permission()) == [event]
    assert list(orga_user.get_events_for_permission(can_change_submissions=True)) == [
        event
    ]
    permission_set = {
        "can_create_events",
        "can_change_teams",
        "can_change_organiser_settings",
        "can_change_event_settings",
        "can_change_submissions",
    }
    assert orga_user.get_permissions_for_event(event) == permission_set


@pytest.mark.django_db
def test_do_not_shred_user_with_teams(orga_user):
    assert User.objects.count() == 1
    with pytest.raises(Exception):  # noqa: B017, PT011
        orga_user.shred()
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_shred_user(user):
    assert User.objects.count() == 1
    user.shred()
    assert User.objects.count() == 0


@pytest.mark.parametrize(
    ("code", "filename", "expected_start", "expected_end"),
    (
        ("ABCDEF", "foo.jpg", "avatars/ABCDEF_", ".jpg"),
        (None, "foo.jpg", "avatars/avatar_", ".jpg"),
        ("ABCDEF", "foo.jpeg", "avatars/ABCDEF_", ".jpeg"),
    ),
)
def test_picture_path(code, filename, expected_start, expected_end):
    user = User()
    user.code = code
    picture = ProfilePicture(user=user)
    ap = picture_path(picture, filename)
    assert ap.startswith(expected_start)
    assert ap.endswith(expected_end)


@pytest.mark.django_db
def test_user_profile_picture(orga_user):
    assert not orga_user.profile_picture_id


@pytest.mark.django_db
def test_user_reset_password_without_text(orga_user, event):
    with scope(event=event):
        assert not orga_user.pw_reset_token
        orga_user.reset_password(event)
        orga_user.refresh_from_db()
        assert orga_user.pw_reset_token
