import uuid

import pytest
from django.core import mail as djmail
from django.core.exceptions import ValidationError
from django_scopes import scopes_disabled
from rest_framework.authtoken.models import Token

from pretalx.common.exceptions import UserDeletionError
from pretalx.common.models import ActivityLog
from pretalx.common.urls import build_absolute_uri
from pretalx.person.models import User
from pretalx.person.models.picture import ProfilePicture
from pretalx.person.models.user import validate_username
from pretalx.person.signals import delete_user as delete_user_signal
from pretalx.submission.models import Answer
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


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


@pytest.mark.parametrize(
    ("input_email", "expected"),
    (
        ("TEST@Example.COM", "test@example.com"),
        ("  test@example.com  ", "test@example.com"),
    ),
    ids=["lowercases", "strips_whitespace"],
)
@pytest.mark.django_db
def test_user_save_normalizes_email(input_email, expected):
    user = UserFactory(email=input_email)
    user.refresh_from_db()
    assert user.email == expected


def test_user_guid_deterministic():
    user = User(email="test@example.com")
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, "acct:test@example.com"))
    assert user.guid == expected


def test_user_guid_different_emails():
    user1 = User(email="a@example.com")
    user2 = User(email="b@example.com")
    assert user1.guid != user2.guid


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


@pytest.mark.django_db
def test_user_manager_create_user():
    user = User.objects.create_user(
        email="new@example.com", name="New User", password="secret123!"
    )
    assert user.pk is not None
    assert user.email == "new@example.com"
    assert user.check_password("secret123!")


@pytest.mark.django_db
def test_user_manager_create_user_no_password():
    user = User.objects.create_user(email="nopass@example.com", name="No Pass")
    assert user.pk is not None
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_user_manager_create_superuser():
    user = User.objects.create_superuser(
        email="admin@example.com", name="Admin", password="admin123!"
    )
    assert user.is_staff is True
    assert user.is_administrator is True
    assert user.is_superuser is False


@pytest.mark.django_db
def test_user_has_perm_caches_result(event):
    user = UserFactory()
    user.is_administrator = True

    user.has_perm("person.administrator", event)

    assert ("person.administrator", event) in user.permission_cache


@pytest.mark.django_db
def test_user_has_perm_returns_cached():
    user = UserFactory()
    event = EventFactory()
    user.permission_cache[("fake.perm", event)] = True

    assert user.has_perm("fake.perm", event) is True


@pytest.mark.django_db
def test_user_has_perm_no_pk():
    """has_perm bypasses cache when obj has no pk."""
    user = UserFactory()

    class FakeObj:
        pk = None

    result = user.has_perm("person.administrator", FakeObj())
    assert result is False


@pytest.mark.django_db
def test_user_get_speaker_creates_profile(event):
    user = UserFactory()

    with scopes_disabled():
        speaker = user.get_speaker(event)

    assert speaker.event == event
    assert speaker.user == user
    assert speaker.pk is not None


@pytest.mark.django_db
def test_user_get_speaker_returns_existing(event):
    speaker = SpeakerFactory(event=event)

    with scopes_disabled():
        result = speaker.user.get_speaker(event)

    assert result.pk == speaker.pk


@pytest.mark.django_db
def test_user_get_speaker_uses_cache(event):
    user = UserFactory()

    with scopes_disabled():
        speaker = user.get_speaker(event)
        cached = user.get_speaker(event)

    assert speaker is cached


@pytest.mark.django_db
def test_user_get_speaker_prefetched(event, django_assert_num_queries):
    """get_speaker uses _speakers attr when available from prefetch."""
    speaker = SpeakerFactory(event=event)

    with scopes_disabled():
        users = list(User.objects.with_profiles(event).filter(pk=speaker.user.pk))
    user = users[0]

    with django_assert_num_queries(0):
        result = user.get_speaker(event)

    assert result.pk == speaker.pk


@pytest.mark.django_db
def test_user_get_event_preferences_creates(event):
    user = UserFactory()

    with scopes_disabled():
        prefs = user.get_event_preferences(event)

    assert prefs.event == event
    assert prefs.user == user
    assert prefs.pk is not None


@pytest.mark.django_db
def test_user_get_event_preferences_caches(event):
    user = UserFactory()

    with scopes_disabled():
        prefs1 = user.get_event_preferences(event)
        prefs2 = user.get_event_preferences(event)

    assert prefs1 is prefs2


@pytest.mark.parametrize(
    ("user_locale", "event_locales", "expected"),
    (("de", ["en", "de"], "de"), ("fr", ["en", "de"], "en")),
    ids=["locale_in_event", "locale_not_in_event"],
)
@pytest.mark.django_db
def test_user_get_locale_for_event(user_locale, event_locales, expected):
    user = User(locale=user_locale)
    event = EventFactory()
    event.locales = event_locales
    event.locale = event_locales[0]
    assert user.get_locale_for_event(event) == expected


@pytest.mark.django_db
def test_user_log_action_defaults_to_self():
    user = UserFactory()
    log = user.log_action("pretalx.user.test")
    assert log.person == user


@pytest.mark.django_db
def test_user_own_actions_filters_by_person():
    user = UserFactory()
    user.log_action("pretalx.user.test_action")

    with scopes_disabled():
        actions = user.own_actions()
        assert actions.count() == 1
        assert actions.first().person == user


@pytest.mark.django_db
def test_user_deactivate_clears_personal_data():
    user = UserFactory(name="Real Name", email="real@example.com")

    with scopes_disabled():
        user.deactivate()
    user.refresh_from_db()

    assert user.name == "Deleted User"
    assert user.is_active is False
    assert user.is_superuser is False
    assert user.is_administrator is False
    assert user.locale == "en"
    assert user.timezone == "UTC"
    assert not user.has_usable_password()
    assert user.pw_reset_token is None
    assert user.pw_reset_time is None
    assert "deleted_user_" in user.email


@pytest.mark.django_db
def test_user_deactivate_clears_biography():
    speaker = SpeakerFactory()

    with scopes_disabled():
        speaker.biography = "My bio"
        speaker.save()
        speaker.user.deactivate()
        speaker.refresh_from_db()

    assert speaker.biography == ""


@pytest.mark.django_db
def test_user_deactivate_deletes_personal_answers():
    speaker = SpeakerFactory()
    submission = SubmissionFactory(event=speaker.event)
    with scopes_disabled():
        submission.speakers.add(speaker)

    personal_q = QuestionFactory(
        event=speaker.event, target="submission", contains_personal_data=True
    )
    impersonal_q = QuestionFactory(
        event=speaker.event, target="submission", contains_personal_data=False
    )
    AnswerFactory(question=personal_q, submission=submission, speaker=None)
    impersonal = AnswerFactory(
        question=impersonal_q, submission=submission, speaker=None
    )

    with scopes_disabled():
        speaker.user.deactivate()

        remaining = list(Answer.objects.all())
    assert remaining == [impersonal]


@pytest.mark.django_db
def test_user_deactivate_removes_from_teams():
    user = UserFactory()
    team = TeamFactory()
    team.members.add(user)
    assert team.members.count() == 1

    with scopes_disabled():
        user.deactivate()

    assert team.members.count() == 0


@pytest.mark.django_db
def test_user_deactivate_sends_signal():
    user = UserFactory()
    received = []

    def handler(sender, **kwargs):
        received.append(kwargs["user"])

    delete_user_signal.connect(handler)
    try:
        with scopes_disabled():
            user.deactivate()
    finally:
        delete_user_signal.disconnect(handler)

    assert received == [user]


@pytest.mark.django_db
def test_user_shred_deletes_user():
    user = UserFactory()
    pk = user.pk
    user.shred()
    assert not User.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_user_shred_raises_with_submissions():
    speaker = SpeakerFactory()
    submission = SubmissionFactory(event=speaker.event)
    with scopes_disabled():
        submission.speakers.add(speaker)

    with pytest.raises(UserDeletionError):
        speaker.user.shred()


@pytest.mark.django_db
def test_user_shred_raises_with_teams():
    user = UserFactory()
    team = TeamFactory()
    team.members.add(user)

    with pytest.raises(UserDeletionError):
        user.shred()


@pytest.mark.django_db
def test_user_shred_raises_with_answers():
    """Users with answers (as speaker or submission speaker) cannot be shredded."""
    speaker = SpeakerFactory()
    question = QuestionFactory(event=speaker.event, target="speaker")
    AnswerFactory(question=question, speaker=speaker, submission=None)

    with pytest.raises(UserDeletionError):
        speaker.user.shred()


@pytest.mark.django_db
def test_user_shred_sends_signal():
    user = UserFactory()
    received = []

    def handler(sender, **kwargs):
        received.append(kwargs["user"])

    delete_user_signal.connect(handler)
    try:
        user.shred()
    finally:
        delete_user_signal.disconnect(handler)

    assert received == [user]


@pytest.mark.django_db
def test_user_shred_cleans_own_actions():
    """Shredding nullifies person references in the shredded user's own actions."""
    user = UserFactory()
    other_user = UserFactory()
    other_user.log_action("pretalx.user.test", person=user)

    with scopes_disabled():
        action_pk = ActivityLog.objects.filter(person=user).first().pk

    user.shred()

    with scopes_disabled():
        action = ActivityLog.objects.get(pk=action_pk)
    assert action.person is None


@pytest.mark.django_db
def test_user_shred_deletes_logged_actions():
    user = UserFactory()
    user.log_action("pretalx.user.test")

    with scopes_disabled():
        assert user.logged_actions().count() == 1

    user.shred()

    with scopes_disabled():
        assert not ActivityLog.objects.filter(object_id=user.pk).exists()


@pytest.mark.django_db
def test_user_regenerate_token():
    user = UserFactory()

    token = user.regenerate_token()

    assert isinstance(token, Token)
    assert token.user == user


@pytest.mark.django_db
def test_user_regenerate_token_replaces_old():
    user = UserFactory()
    old_token = user.regenerate_token()
    new_token = user.regenerate_token()

    assert old_token.key != new_token.key
    assert Token.objects.filter(user=user).count() == 1


@pytest.mark.parametrize(
    ("use_event", "orga", "expected_urlname"),
    (
        (True, False, "cfp:event.recover"),
        (True, True, "orga:event.auth.recover"),
        (False, False, "orga:auth.recover"),
    ),
    ids=["cfp_with_event", "orga_with_event", "without_event"],
)
@pytest.mark.django_db
def test_user_get_password_reset_url(use_event, orga, expected_urlname, event):
    user = UserFactory(pw_reset_token="abc123")

    kwargs = {"event": event, "orga": orga} if use_event else {}
    url = user.get_password_reset_url(**kwargs)

    expected_kwargs = {"token": "abc123"}
    if use_event:
        expected_kwargs["event"] = event.slug
    assert url == build_absolute_uri(expected_urlname, kwargs=expected_kwargs)


@pytest.mark.django_db
def test_user_reset_password(event):
    user = UserFactory()
    assert user.pw_reset_token is None
    djmail.outbox = []

    user.reset_password(event)
    user.refresh_from_db()

    assert len(user.pw_reset_token) == 32
    assert user.pw_reset_time is not None
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    with scopes_disabled():
        actions = list(
            user.own_actions().filter(action_type="pretalx.user.password.reset")
        )
    assert len(actions) == 1


@pytest.mark.django_db
def test_user_reset_password_custom_text(event):
    user = UserFactory()
    djmail.outbox = []

    user.reset_password(event, mail_text="Custom {name} {url}")

    assert len(djmail.outbox) == 1
    expected_url = user.get_password_reset_url(event=event)
    assert djmail.outbox[0].body == f"Custom {user.name} {expected_url}"


@pytest.mark.django_db
def test_user_change_password():
    user = UserFactory()
    djmail.outbox = []

    user.change_password("newpassword123!")

    user.refresh_from_db()
    assert user.check_password("newpassword123!")
    assert user.pw_reset_token is None
    assert user.pw_reset_time is None
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [user.email]
    with scopes_disabled():
        actions = list(
            user.own_actions().filter(action_type="pretalx.user.password.changed")
        )
    assert len(actions) == 1


@pytest.mark.django_db
def test_user_change_email():
    user = UserFactory(email="old@example.com")
    djmail.outbox = []

    user.change_email("NEW@Example.COM")

    user.refresh_from_db()
    assert user.email == "new@example.com"
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["old@example.com"]
    with scopes_disabled():
        action = (
            user.own_actions().filter(action_type="pretalx.user.email.update").first()
        )
    assert action.data == {
        "old_email": "old@example.com",
        "new_email": "new@example.com",
    }


@pytest.mark.django_db
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
        "is_reviewer",
    }
    assert permissions == expected


@pytest.mark.django_db
def test_user_get_permissions_for_event_team_member(event):
    user = UserFactory()
    team = TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_submissions=True,
        is_reviewer=True,
    )
    team.members.add(user)

    permissions = user.get_permissions_for_event(event)

    assert permissions == {"can_change_submissions", "is_reviewer"}


@pytest.mark.django_db
def test_user_get_permissions_for_event_no_team(event):
    user = UserFactory()
    permissions = user.get_permissions_for_event(event)
    assert permissions == set()


@pytest.mark.django_db
def test_user_get_permissions_for_event_caches(event):
    user = UserFactory()
    user.is_administrator = True

    user.get_permissions_for_event(event)
    cached = user.event_permission_cache.get(event.pk)

    assert "permissions" in cached


@pytest.mark.django_db
def test_user_get_permissions_for_event_updates_existing_cache(event):
    """When there's already partial cache data, get_permissions_for_event
    updates the existing dict rather than replacing it."""
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    user.event_permission_cache[event.pk] = {"some_key": "some_value"}
    user.get_permissions_for_event(event)

    cached = user.event_permission_cache[event.pk]
    assert "some_key" in cached
    assert "permissions" in cached


@pytest.mark.django_db
def test_user_get_events_with_any_permission_administrator():
    user = UserFactory()
    user.is_administrator = True
    event = EventFactory()

    events = list(user.get_events_with_any_permission())

    assert events == [event]


@pytest.mark.django_db
def test_user_get_events_with_any_permission_team_all_events():
    user = UserFactory()
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True)
    team.members.add(user)

    events = list(user.get_events_with_any_permission())

    assert events == [event]


@pytest.mark.django_db
def test_user_get_events_with_any_permission_team_limited():
    user = UserFactory()
    event = EventFactory()
    EventFactory(organiser=event.organiser)
    team = TeamFactory(organiser=event.organiser, all_events=False)
    team.limit_events.add(event)
    team.members.add(user)

    events = list(user.get_events_with_any_permission())

    assert events == [event]


@pytest.mark.django_db
def test_user_get_events_with_any_permission_no_teams():
    user = UserFactory()
    EventFactory()

    events = list(user.get_events_with_any_permission())

    assert events == []


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_user_get_events_for_permission_administrator():
    user = UserFactory()
    user.is_administrator = True
    event = EventFactory()

    events = list(user.get_events_for_permission(is_reviewer=True))

    assert events == [event]


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_user_get_reviewer_tracks_no_reviewer():
    user = UserFactory()
    event = EventFactory()

    tracks = user.get_reviewer_tracks(event)

    assert tracks == frozenset()


@pytest.mark.django_db
def test_user_get_reviewer_tracks_unrestricted():
    user = UserFactory()
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    with scopes_disabled():
        tracks = user.get_reviewer_tracks(event)

    assert tracks is None


@pytest.mark.django_db
def test_user_get_reviewer_tracks_restricted():
    user = UserFactory()
    event = EventFactory()
    track = TrackFactory(event=event)
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)
    track.limit_teams.add(team)

    with scopes_disabled():
        tracks = user.get_reviewer_tracks(event)

    assert set(tracks) == {track}


@pytest.mark.django_db
def test_user_get_reviewer_tracks_caches(event):
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    with scopes_disabled():
        user.get_reviewer_tracks(event)
    cached = user.event_permission_cache[event.pk]

    assert "reviewer_tracks" in cached


@pytest.mark.django_db
def test_user_queryset_with_profiles_prefetches_speakers(
    event, django_assert_num_queries
):
    speaker = SpeakerFactory(event=event)

    with scopes_disabled():
        users = list(User.objects.with_profiles(event).filter(pk=speaker.user.pk))

    assert len(users) == 1
    with django_assert_num_queries(0):
        speakers = users[0]._speakers
    assert speakers[0].pk == speaker.pk


@pytest.mark.django_db
def test_user_queryset_with_speaker_code_annotates_code(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)

        users = list(User.objects.with_speaker_code(event).filter(pk=speaker.user.pk))

    assert len(users) == 1
    assert users[0].speaker_code == speaker.code


@pytest.mark.django_db
def test_user_queryset_with_speaker_code_no_submissions(event):
    speaker = SpeakerFactory(event=event)

    with scopes_disabled():
        users = list(User.objects.with_speaker_code(event).filter(pk=speaker.user.pk))

    assert len(users) == 1
    assert users[0].speaker_code is None


@pytest.mark.django_db
def test_user_code_auto_generated():
    user1 = UserFactory()
    user2 = UserFactory()
    assert 1 <= len(user1.code) <= 16
    assert user1.code != user2.code


@pytest.mark.django_db
def test_user_get_speaker_prefetched_wrong_event():
    """When _speakers has a profile for a different event, get_speaker falls
    through to the database query."""
    event1 = EventFactory()
    event2 = EventFactory()
    speaker1 = SpeakerFactory(event=event1)
    SpeakerFactory(event=event2, user=speaker1.user)

    with scopes_disabled():
        users = list(User.objects.with_profiles(event1).filter(pk=speaker1.user.pk))
    user = users[0]

    with scopes_disabled():
        result = user.get_speaker(event2)

    assert result.event == event2


@pytest.mark.django_db
def test_user_get_permissions_for_event_returns_from_cache(event):
    user = UserFactory()
    expected = {"can_change_submissions"}
    user.event_permission_cache[event.pk] = {"permissions": expected}

    result = user.get_permissions_for_event(event)

    assert result is expected


@pytest.mark.django_db
def test_user_get_reviewer_tracks_returns_from_cache(event):
    user = UserFactory()
    cached_tracks = frozenset()
    user.event_permission_cache[event.pk] = {"reviewer_tracks": cached_tracks}

    result = user.get_reviewer_tracks(event)

    assert result is cached_tracks


@pytest.mark.django_db
def test_user_delete_files_deletes_pictures():
    user = UserFactory()
    ProfilePicture.objects.create(user=user)
    assert user.pictures.count() == 1

    user._delete_files()

    assert user.pictures.count() == 0


@pytest.mark.django_db
def test_user_get_permissions_for_event_tracks_reviewer_team_pks(event):
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    user.get_permissions_for_event(event)

    cached = user.event_permission_cache[event.pk]
    assert cached["reviewer_team_pks"] == [team.pk]


@pytest.mark.django_db
def test_user_get_permissions_for_event_non_reviewer_team(event):
    """A team without is_reviewer does not add to reviewer_team_pks."""
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
    assert cached["reviewer_team_pks"] == []
    assert "can_change_submissions" in cached["permissions"]
