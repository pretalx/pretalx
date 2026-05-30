# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.person.models import User
from pretalx.person.models.user import validate_username
from tests.factories import (
    EventFactory,
    ProfilePictureFactory,
    SpeakerFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("name", "expected"),
    (("Alice", "Alice"), ("", "Unnamed user")),
    ids=["with_name", "empty_name"],
)
def test_user_str(name, expected):
    user = User(name=name)
    assert str(user) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    (("Bob", "Bob"), ("", "Unnamed user")),
    ids=["with_name", "empty_name"],
)
def test_user_get_display_name(name, expected):
    user = User(name=name)
    assert user.get_display_name() == expected


def test_user_init_caches():
    user = User()
    assert user.permission_cache == {}
    assert user.speaker_cache == {}
    assert user.event_permission_cache == {}
    assert user.event_preferences_cache == {}


def test_user_email_unique_constraint_is_case_insensitive():
    UserFactory(email="taken@example.com")
    user = UserFactory(email="mine@example.com")
    user.email = "Taken@Example.com"
    with pytest.raises(ValidationError, match="different email address"):
        user.validate_constraints()


def test_user_clean_rejects_taken_email_for_new_user():
    UserFactory(email="taken@example.com")
    user = User(email="taken@example.com", name="New")
    with pytest.raises(ValidationError) as info:
        user.clean()
    assert "email" in info.value.message_dict


def test_user_clean_allows_own_email_when_editing():
    user = UserFactory(email="me@example.com")
    user.clean()


@pytest.mark.parametrize(
    ("input_email", "expected"),
    (
        ("TEST@Example.COM", "test@example.com"),
        ("  test@example.com  ", "test@example.com"),
    ),
    ids=["lowercases", "strips_whitespace"],
)
def test_user_clean_normalizes_email(input_email, expected):
    """``clean`` is the only place email normalization happens — every
    creation path (create_user, ModelForms, serializer base) routes
    through it."""
    user = User(email=input_email, name="New")
    user.clean()
    assert user.email == expected


def test_user_clean_accepts_empty_email():
    """A blank email skips normalization (no ``.lower()`` on ``""``) and
    is left for the field-level validator to reject; callers that need
    ``EMAIL_FIELD`` to be required must run ``full_clean``."""
    user = User(email="", name="New")
    user.clean()
    assert user.email == ""


@pytest.mark.parametrize(
    "username",
    ("Alice", "Bob Smith", "user123", "Ülrich", "name with <", "a > b"),
    ids=["plain", "with_space", "with_numbers", "unicode", "lt_char", "gt_char"],
)
def test_validate_username_accepts_plain_text(username):
    validate_username(username)


@pytest.mark.parametrize(
    "username",
    ("<script>alert(1)</script>", "**bold**", "[link](http://evil.com)"),
    ids=["script_tag", "markdown_bold", "markdown_link"],
)
def test_validate_username_rejects_markup(username):
    with pytest.raises(ValidationError):
        validate_username(username)


def test_user_manager_create_superuser():
    user = User.objects.create_superuser(
        email="admin@example.com", name="Admin", password="admin123!"
    )
    assert user.is_staff is True
    assert user.is_administrator is True
    assert user.is_superuser is False


def test_user_created_is_set_on_save():
    user = User.objects.create_user(email="created-test@example.com", password="x")
    assert user.created is not None


def test_user_has_perm_caches_result(event):
    user = UserFactory()
    user.is_administrator = True

    user.has_perm("person.administrator", event)

    assert ("person.administrator", event) in user.permission_cache


def test_user_has_perm_returns_cached():
    user = UserFactory()
    event = EventFactory()
    user.permission_cache[("fake.perm", event)] = True

    assert user.has_perm("fake.perm", event) is True


def test_user_has_perm_no_pk():
    """has_perm bypasses cache when obj has no pk."""
    user = UserFactory()

    class FakeObj:
        pk = None

    result = user.has_perm("person.administrator", FakeObj())
    assert result is False


def test_user_get_speaker_creates_profile(event):
    user = UserFactory()

    speaker = user.get_speaker(event)

    assert speaker.event == event
    assert speaker.user == user
    assert speaker.pk is not None


def test_user_get_speaker_returns_existing(event):
    speaker = SpeakerFactory(event=event)

    result = speaker.user.get_speaker(event)

    assert result.pk == speaker.pk


def test_user_get_speaker_uses_cache(event):
    user = UserFactory()

    speaker = user.get_speaker(event)
    cached = user.get_speaker(event)

    assert speaker is cached


def test_user_get_speaker_prefetched(event, django_assert_num_queries):
    """get_speaker uses _speakers attr when available from prefetch."""
    speaker = SpeakerFactory(event=event)

    users = list(User.objects.with_profiles(event).filter(pk=speaker.user.pk))
    user = users[0]

    with django_assert_num_queries(0):
        result = user.get_speaker(event)

    assert result.pk == speaker.pk


def test_user_get_event_preferences_creates(event):
    user = UserFactory()

    prefs = user.get_event_preferences(event)

    assert prefs.event == event
    assert prefs.user == user
    assert prefs.pk is not None


def test_user_get_event_preferences_caches(event):
    user = UserFactory()

    prefs1 = user.get_event_preferences(event)
    prefs2 = user.get_event_preferences(event)

    assert prefs1 is prefs2


@pytest.mark.parametrize(
    ("user_locale", "event_locales", "expected"),
    (("de", ["en", "de"], "de"), ("fr", ["en", "de"], "en")),
    ids=["locale_in_event", "locale_not_in_event"],
)
def test_user_get_locale_for_event(user_locale, event_locales, expected):
    user = User(locale=user_locale)
    event = EventFactory()
    event.locale_array = ",".join(event_locales)
    event.locale = event_locales[0]
    assert user.get_locale_for_event(event) == expected


def test_user_log_action_defaults_to_self():
    user = UserFactory()
    log = user.log_action("pretalx.user.test")
    assert log.person == user


def test_user_get_permissions_for_event_administrator(event):
    user = UserFactory()
    user.is_administrator = True

    permissions = user.get_permissions_for_event(event)

    expected = {
        "can_create_events",
        "can_change_teams",
        "can_change_organiser_settings",
        "can_change_event_settings",
        "can_change_submissions",
    }
    assert permissions == expected


def test_user_get_permissions_for_event_team_member(event):
    user = UserFactory()
    blanket_reviewer = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    blanket_reviewer.members.add(user)
    organiser_team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=False,
        can_change_submissions=True,
    )
    organiser_team.members.add(user)

    permissions = user.get_permissions_for_event(event)

    assert permissions == {"can_change_submissions", "is_reviewer"}


def test_user_get_permissions_for_event_no_team(event):
    user = UserFactory()
    permissions = user.get_permissions_for_event(event)
    assert permissions == set()


def test_user_get_permissions_for_event_caches(event):
    user = UserFactory()
    user.is_administrator = True

    user.get_permissions_for_event(event)
    cached = user.event_permission_cache.get(event.pk)

    assert "permissions" in cached


def test_user_get_events_with_any_permission_administrator():
    user = UserFactory()
    user.is_administrator = True
    event = EventFactory()

    events = list(user.get_events_with_any_permission())

    assert events == [event]


def test_user_get_events_with_any_permission_team_all_events():
    user = UserFactory()
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True)
    team.members.add(user)

    events = list(user.get_events_with_any_permission())

    assert events == [event]


def test_user_get_events_with_any_permission_team_limited():
    user = UserFactory()
    event = EventFactory()
    EventFactory(organiser=event.organiser)
    team = TeamFactory(organiser=event.organiser, all_events=False)
    team.limit_events.add(event)
    team.members.add(user)

    events = list(user.get_events_with_any_permission())

    assert events == [event]


def test_user_get_events_with_any_permission_no_teams():
    user = UserFactory()
    EventFactory()

    events = list(user.get_events_with_any_permission())

    assert events == []


def test_user_get_events_with_any_permission_prefetched_teams(
    django_assert_num_queries,
):
    """When teams are prefetched, get_events_with_any_permission uses
    the prefetch cache rather than issuing a DB query."""
    user = UserFactory()
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True)
    team.members.add(user)

    user = User.objects.prefetch_related(
        "teams__organiser__events", "teams__limit_events"
    ).get(pk=user.pk)

    with django_assert_num_queries(0):
        events = list(user.get_events_with_any_permission())

    assert events == [event]


def test_user_get_events_with_any_permission_prefetched_limited(
    django_assert_num_queries,
):
    """Prefetched path with limit_events (not all_events) returns only
    the limited events."""
    user = UserFactory()
    event = EventFactory()
    EventFactory(organiser=event.organiser)
    team = TeamFactory(organiser=event.organiser, all_events=False)
    team.limit_events.add(event)
    team.members.add(user)

    user = User.objects.prefetch_related(
        "teams__organiser__events", "teams__limit_events"
    ).get(pk=user.pk)

    with django_assert_num_queries(0):
        events = list(user.get_events_with_any_permission())

    assert events == [event]


def test_user_get_events_for_permission_filters_by_permission():
    user = UserFactory()
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_submissions=True,
        is_reviewer=False,
    )
    team.members.add(user)

    with_perm = list(user.get_events_for_permission(can_change_submissions=True))
    without_perm = list(user.get_events_for_permission(is_reviewer=True))

    assert with_perm == [event]
    assert without_perm == []


def test_user_get_events_for_permission_administrator():
    user = UserFactory()
    user.is_administrator = True
    event = EventFactory()

    events = list(user.get_events_for_permission(is_reviewer=True))

    assert events == [event]


def test_user_get_events_for_permission_limited_events():
    user = UserFactory()
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=False, can_change_submissions=True
    )
    team.limit_events.add(event)
    team.members.add(user)

    events = list(user.get_events_for_permission(can_change_submissions=True))

    assert events == [event]


def test_user_get_reviewer_tracks_no_reviewer():
    user = UserFactory()
    event = EventFactory()

    with pytest.raises(ValueError, match="is not a reviewer"):
        user.get_reviewer_tracks(event)


def test_user_get_reviewer_tracks_unrestricted():
    user = UserFactory()
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    tracks = user.get_reviewer_tracks(event)

    assert tracks is None


def test_user_get_reviewer_tracks_restricted():
    user = UserFactory()
    event = EventFactory()
    track = TrackFactory(event=event)
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)
    track.limit_teams.add(team)

    tracks = user.get_reviewer_tracks(event)

    assert tracks == frozenset({track.pk})


def test_user_get_reviewer_tracks_blanket_team_overrides_restricted():
    user = UserFactory()
    event = EventFactory()
    track = TrackFactory(event=event)
    blanket = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_event_settings=True,
    )
    blanket.members.add(user)
    restricted = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=True,
        can_change_event_settings=False,
    )
    restricted.members.add(user)
    track.limit_teams.add(restricted)

    tracks = user.get_reviewer_tracks(event)

    assert tracks is None
    assert user.get_permissions_for_event(event) == {
        "is_reviewer",
        "can_change_submissions",
        "can_change_event_settings",
    }


def test_user_get_reviewer_tracks_unions_restricted_teams():
    user = UserFactory()
    event = EventFactory()
    track1 = TrackFactory(event=event)
    track2 = TrackFactory(event=event)
    team1 = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=True,
        can_change_event_settings=False,
    )
    team1.members.add(user)
    track1.limit_teams.add(team1)
    team2 = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_event_settings=True,
    )
    team2.members.add(user)
    track2.limit_teams.add(team2)

    tracks = user.get_reviewer_tracks(event)

    assert tracks == frozenset({track1.pk, track2.pk})
    assert user.get_permissions_for_event(event) == {
        "is_reviewer",
        "can_change_submissions",
        "can_change_event_settings",
    }


def test_user_get_reviewer_tracks_caches(event):
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    user.get_reviewer_tracks(event)
    cached = user.event_permission_cache[event.pk]

    assert "reviewer_tracks" in cached


def test_user_code_auto_generated():
    user1 = UserFactory()
    user2 = UserFactory()
    assert 1 <= len(user1.code) <= 16
    assert user1.code != user2.code


def test_user_get_speaker_prefetched_wrong_event():
    """When _speakers has a profile for a different event, get_speaker falls
    through to the database query."""
    event1 = EventFactory()
    event2 = EventFactory()
    speaker1 = SpeakerFactory(event=event1)
    SpeakerFactory(event=event2, user=speaker1.user)

    users = list(User.objects.with_profiles(event1).filter(pk=speaker1.user.pk))
    user = users[0]

    result = user.get_speaker(event2)

    assert result.event == event2


def test_user_get_permissions_for_event_returns_from_cache(event):
    user = UserFactory()
    expected = {"can_change_submissions"}
    user.event_permission_cache[event.pk] = {
        "permissions": expected,
        "reviewer_tracks": frozenset(),
    }

    result = user.get_permissions_for_event(event)

    assert result is expected


def test_user_get_reviewer_tracks_returns_from_cache(event):
    user = UserFactory()
    cached_tracks = frozenset()
    user.event_permission_cache[event.pk] = {
        "permissions": {"is_reviewer"},
        "reviewer_tracks": cached_tracks,
    }

    result = user.get_reviewer_tracks(event)

    assert result is cached_tracks


def test_user_delete_files_deletes_pictures():
    user = UserFactory()
    ProfilePictureFactory(user=user)
    assert user.pictures.count() == 1

    user.delete_files()

    assert user.pictures.count() == 0


def test_user_get_permissions_for_event_non_reviewer_team(event):
    """A team without is_reviewer leaves reviewer_team_pks empty."""
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_submissions=True,
        is_reviewer=False,
    )
    team.members.add(user)

    user.get_permissions_for_event(event)

    cached = user.event_permission_cache[event.pk]
    assert cached["reviewer_team_pks"] == set()
    assert "is_reviewer" not in cached["permissions"]
    assert "can_change_submissions" in cached["permissions"]
