import json

import pytest
from django.db.models import Count, Q
from django_scopes import scopes_disabled

from pretalx.common.forms.widgets import BiographyWidget, MarkdownWidget
from pretalx.person.forms.profile import (
    OrgaProfileForm,
    SpeakerAvailabilityForm,
    SpeakerFilterForm,
    SpeakerProfileForm,
    UserSpeakerFilterForm,
    get_email_address_error,
)
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.models.submission import SubmissionStates
from tests.factories import (
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


def test_get_email_address_error():
    result = get_email_address_error()
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.django_db
def test_speaker_profile_form_init_creates_profile_for_user():
    """When a user has no profile for the event yet, get_speaker creates one."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()

        form = SpeakerProfileForm(event=event, user=user)

    assert form.instance is not None
    assert form.instance.event == event
    assert form.instance.user == user


@pytest.mark.django_db
def test_speaker_profile_form_init_uses_existing_profile():
    with scopes_disabled():
        speaker = SpeakerFactory(biography="Existing bio")
        event = speaker.event
        user = speaker.user

        form = SpeakerProfileForm(event=event, user=user)

    assert form.instance == speaker


@pytest.mark.django_db
def test_speaker_profile_form_init_name_from_profile():
    """When the profile already has a name, that name is used as initial."""
    with scopes_disabled():
        speaker = SpeakerFactory(name="Profile Name")

        form = SpeakerProfileForm(event=speaker.event, user=speaker.user)

    assert form.fields["name"].initial == "Profile Name"


@pytest.mark.django_db
def test_speaker_profile_form_init_name_falls_back_to_user():
    """When the profile has no name, user.name is used as initial."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory(name="User Name")

        form = SpeakerProfileForm(event=event, user=user)

    assert form.fields["name"].initial == "User Name"


@pytest.mark.django_db
def test_speaker_profile_form_init_name_falls_back_to_kwarg():
    """When the profile has no name and no user, the name kwarg is used."""
    with scopes_disabled():
        event = EventFactory()

        form = SpeakerProfileForm(event=event, user=None, name="Given Name")

    assert form.fields["name"].initial == "Given Name"


@pytest.mark.parametrize(
    ("with_email", "expect_present"), ((True, True), (False, False))
)
@pytest.mark.django_db
def test_speaker_profile_form_init_email_field_presence(with_email, expect_present):
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory(email="speaker@test.com")

        form = SpeakerProfileForm(event=event, user=user, with_email=with_email)

    assert ("email" in form.fields) is expect_present
    if expect_present:
        assert form.fields["email"].initial == "speaker@test.com"


@pytest.mark.django_db
def test_speaker_profile_form_init_without_user_excludes_first_time_fields():
    """Without a user, FIRST_TIME_EXCLUDE fields (email) are excluded."""
    with scopes_disabled():
        event = EventFactory()

        form = SpeakerProfileForm(event=event, user=None)

    assert "email" not in form.fields


@pytest.mark.django_db
def test_speaker_profile_form_user_fields_with_essential_only():
    """essential_only=True behaves like no-user: excludes FIRST_TIME_EXCLUDE fields."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()

        form = SpeakerProfileForm(event=event, user=user, essential_only=True)

    assert "email" not in form.fields


@pytest.mark.django_db
def test_speaker_profile_form_init_read_only_disables_fields():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()

        form = SpeakerProfileForm(event=event, user=user, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


@pytest.mark.django_db
def test_speaker_profile_form_reorders_fields_with_field_configuration():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        field_config = [{"key": "biography"}, {"key": "name"}, {"key": "avatar"}]

        form = SpeakerProfileForm(
            event=event, user=user, field_configuration=field_config
        )

    keys = list(form.fields.keys())
    assert keys.index("biography") < keys.index("name")


@pytest.mark.django_db
def test_speaker_profile_form_biography_suggestions_shown_when_other_profiles_exist():
    """When the user has bios on other events, the BiographyWidget is used."""
    with scopes_disabled():
        event = EventFactory()
        other_event = EventFactory()
        user = UserFactory()
        SpeakerFactory(user=user, event=event, biography="")
        SpeakerFactory(
            user=user, event=other_event, biography="I speak at many conferences."
        )

        form = SpeakerProfileForm(event=event, user=user)

    assert isinstance(form.fields["biography"].widget, BiographyWidget)


@pytest.mark.django_db
def test_speaker_profile_form_no_suggestions_when_biography_already_exists():
    with scopes_disabled():
        other_event = EventFactory()
        user = UserFactory()
        speaker = SpeakerFactory(user=user, biography="I have a bio already.")
        SpeakerFactory(user=user, event=other_event, biography="Other bio")

        form = SpeakerProfileForm(event=speaker.event, user=user)

    assert isinstance(form.fields["biography"].widget, MarkdownWidget)
    assert not isinstance(form.fields["biography"].widget, BiographyWidget)


@pytest.mark.django_db
def test_speaker_profile_form_no_suggestions_without_other_profiles():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        SpeakerFactory(user=user, event=event, biography="")

        form = SpeakerProfileForm(event=event, user=user)

    assert isinstance(form.fields["biography"].widget, MarkdownWidget)
    assert not isinstance(form.fields["biography"].widget, BiographyWidget)


@pytest.mark.django_db
def test_speaker_profile_form_no_suggestions_for_orga():
    """Orga users don't see biography suggestions from other events."""
    with scopes_disabled():
        event = EventFactory()
        other_event = EventFactory()
        user = UserFactory()
        SpeakerFactory(user=user, event=event, biography="")
        SpeakerFactory(
            user=user, event=other_event, biography="I speak at many conferences."
        )

        form = SpeakerProfileForm(event=event, user=user, is_orga=True)

    assert isinstance(form.fields["biography"].widget, MarkdownWidget)
    assert not isinstance(form.fields["biography"].widget, BiographyWidget)


@pytest.mark.parametrize("input_email", ("taken@example.com", "TAKEN@example.com"))
@pytest.mark.django_db
def test_speaker_profile_form_clean_email_rejects_duplicate(input_email):
    with scopes_disabled():
        event = EventFactory()
        UserFactory(email="taken@example.com")
        user = UserFactory()
        data = {"email": input_email, "name": "Test", "biography": ""}

        form = SpeakerProfileForm(data=data, event=event, user=user)

    assert not form.is_valid()
    assert "email" in form.errors


@pytest.mark.django_db
def test_speaker_profile_form_clean_email_allows_own_email():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory(email="me@example.com")
        data = {"email": "me@example.com", "name": "Test", "biography": "A biography"}

        form = SpeakerProfileForm(data=data, event=event, user=user)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_speaker_profile_form_save_updates_user_email():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory(email="old@example.com")
        data = {"email": "new@example.com", "name": "Speaker", "biography": "A bio"}

        form = SpeakerProfileForm(data=data, event=event, user=user)
        assert form.is_valid(), form.errors
        form.save()

        user.refresh_from_db()
        assert user.email == "new@example.com"


@pytest.mark.django_db
def test_speaker_profile_form_save_creates_speaker_profile():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        data = {"email": user.email, "name": "New Speaker", "biography": "My bio"}

        form = SpeakerProfileForm(data=data, event=event, user=user)
        assert form.is_valid(), form.errors
        result = form.save()

    assert result.pk is not None
    assert result.event == event
    assert result.user == user
    assert result.name == "New Speaker"


@pytest.mark.django_db
def test_speaker_profile_form_save_syncs_name_to_user_if_user_has_no_name():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory(name="")
        data = {
            "email": user.email,
            "name": "Brand New Name",
            "biography": "A biography",
        }

        form = SpeakerProfileForm(data=data, event=event, user=user)
        assert form.is_valid(), form.errors
        form.save()

        user.refresh_from_db()
        assert user.name == "Brand New Name"


@pytest.mark.django_db
def test_speaker_profile_form_save_does_not_overwrite_existing_user_name():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory(name="Existing Name")
        data = {
            "email": user.email,
            "name": "Different Profile Name",
            "biography": "A biography",
        }

        form = SpeakerProfileForm(data=data, event=event, user=user)
        assert form.is_valid(), form.errors
        form.save()

        user.refresh_from_db()
        assert user.name == "Existing Name"


@pytest.mark.parametrize(
    ("visibility", "expect_required"), (("required", True), ("optional", False))
)
@pytest.mark.django_db
def test_speaker_profile_form_avatar_required_matches_cfp(visibility, expect_required):
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        event.cfp.fields["avatar"] = {"visibility": visibility}
        event.cfp.save()

        form = SpeakerProfileForm(event=event, user=user)

    assert form.fields["avatar"].required is expect_required


@pytest.mark.django_db
def test_speaker_profile_form_hides_field_when_do_not_ask():
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        event.cfp.fields["biography"] = {"visibility": "do_not_ask"}
        event.cfp.save()

        form = SpeakerProfileForm(event=event, user=user)

    assert "biography" not in form.fields


@pytest.mark.django_db
def test_speaker_profile_form_init_availabilities_when_enabled():
    """When availabilities are enabled in CfP, the field gets event and instance set."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        event.cfp.fields["availabilities"] = {"visibility": "optional"}
        event.cfp.save()

        form = SpeakerProfileForm(event=event, user=user)

    assert "availabilities" in form.fields
    assert form.fields["availabilities"].event == event


@pytest.mark.django_db
def test_speaker_profile_form_availability_error_fallback():
    """When bound form has availability errors, data is restored from initial."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        event.cfp.fields["availabilities"] = {"visibility": "required"}
        event.cfp.save()
        data = {
            "email": user.email,
            "name": "Test",
            "biography": "A bio",
            "availabilities": "invalid json!!!",
        }

        form = SpeakerProfileForm(data=data, event=event, user=user)

    assert not form.is_valid()
    assert "availabilities" in form.errors


@pytest.mark.django_db
def test_speaker_profile_form_save_with_availabilities():
    """save() replaces availabilities when provided."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        event.cfp.fields["availabilities"] = {"visibility": "optional"}
        event.cfp.save()
        avail_data = {
            "availabilities": [
                {
                    "start": event.date_from.isoformat() + " 10:00:00+00:00",
                    "end": event.date_from.isoformat() + " 18:00:00+00:00",
                }
            ]
        }
        data = {
            "email": user.email,
            "name": "Test",
            "biography": "A bio",
            "availabilities": json.dumps(avail_data),
        }

        form = SpeakerProfileForm(data=data, event=event, user=user)
        assert form.is_valid(), form.errors
        result = form.save()

    with scopes_disabled():
        assert result.availabilities.count() == 1


@pytest.mark.django_db
def test_speaker_profile_form_init_without_avatar_when_do_not_ask():
    """Avatar field is removed when CfP sets it to do_not_ask."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        event.cfp.fields["avatar"] = {"visibility": "do_not_ask"}
        event.cfp.save()

        form = SpeakerProfileForm(event=event, user=user)

    assert "avatar" not in form.fields


@pytest.mark.django_db
def test_speaker_profile_form_save_without_avatar():
    """save() works when avatar field was removed by do_not_ask."""
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        event.cfp.fields["avatar"] = {"visibility": "do_not_ask"}
        event.cfp.save()
        data = {"email": user.email, "name": "Test", "biography": "A bio"}

        form = SpeakerProfileForm(data=data, event=event, user=user)
        assert form.is_valid(), form.errors
        result = form.save()

    assert result.pk is not None
    assert result.name == "Test"


@pytest.mark.django_db
def test_speaker_availability_form_init_creates_field_when_event_and_speaker():
    with scopes_disabled():
        speaker = SpeakerFactory()

        form = SpeakerAvailabilityForm(event=speaker.event, speaker=speaker)

    assert "availabilities" in form.fields


def test_speaker_availability_form_init_no_field_without_event_and_speaker():
    form = SpeakerAvailabilityForm()

    assert "availabilities" not in form.fields


def test_speaker_availability_form_save_returns_none_without_cleaned_data():
    form = SpeakerAvailabilityForm()

    assert form.save() is None


def test_speaker_availability_form_save_skips_replace_without_availabilities_field():
    """save() returns speaker (None) when no availabilities field was created."""
    form = SpeakerAvailabilityForm(data={})
    assert form.is_valid()

    assert form.save() is None


@pytest.mark.django_db
def test_speaker_availability_form_save_replaces_availabilities():
    with scopes_disabled():
        speaker = SpeakerFactory()
        event = speaker.event
        avail_data = {
            "availabilities": [
                {
                    "start": event.date_from.isoformat() + " 10:00:00+00:00",
                    "end": event.date_from.isoformat() + " 18:00:00+00:00",
                }
            ]
        }
        data = {"availabilities": json.dumps(avail_data)}

        form = SpeakerAvailabilityForm(data=data, event=event, speaker=speaker)
        assert form.is_valid(), form.errors
        result = form.save()

    with scopes_disabled():
        assert result == speaker
        assert speaker.availabilities.count() == 1


@pytest.mark.django_db
def test_orga_profile_form_has_name_and_locale_fields():
    user = UserFactory()

    form = OrgaProfileForm(instance=user)

    assert set(form.fields.keys()) == {"name", "locale"}


@pytest.mark.django_db
def test_orga_profile_form_save_updates_user():
    user = UserFactory(name="Old Name", locale="en")
    data = {"name": "New Name", "locale": "de"}

    form = OrgaProfileForm(data=data, instance=user)
    assert form.is_valid(), form.errors
    form.save()

    user.refresh_from_db()
    assert user.name == "New Name"
    assert user.locale == "de"


@pytest.mark.django_db
def test_speaker_filter_form_init_sets_question_queryset():
    with scopes_disabled():
        event = EventFactory()
        question = QuestionFactory(event=event)
        QuestionFactory()  # different event

        form = SpeakerFilterForm(event=event)

    assert list(form.fields["question"].queryset) == [question]


@pytest.mark.parametrize(
    ("filter_arrival", "expect_present"), ((False, False), (True, True))
)
@pytest.mark.django_db
def test_speaker_filter_form_init_arrived_field_presence(
    filter_arrival, expect_present
):
    with scopes_disabled():
        event = EventFactory()

        form = SpeakerFilterForm(event=event, filter_arrival=filter_arrival)

    assert ("arrived" in form.fields) is expect_present


@pytest.mark.django_db
def test_speaker_filter_form_filter_queryset_role_true_filters_accepted():
    """role='true' filters to speakers with accepted/confirmed submissions."""
    with scopes_disabled():
        event = EventFactory()
        speaker_with_accepted = SpeakerFactory(event=event)
        accepted_sub = SubmissionFactory(event=event, state="accepted")
        accepted_sub.speakers.add(speaker_with_accepted)
        speaker_without = SpeakerFactory(event=event)
        rejected_sub = SubmissionFactory(event=event, state="rejected")
        rejected_sub.speakers.add(speaker_without)

        form = SpeakerFilterForm(data={"role": "true"}, event=event)
        assert form.is_valid(), form.errors

        qs = SpeakerProfile.objects.filter(event=event)
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {speaker_with_accepted}


@pytest.mark.django_db
def test_speaker_filter_form_filter_queryset_role_false_excludes_accepted():
    """role='false' filters to non-accepted submitters."""
    with scopes_disabled():
        event = EventFactory()
        speaker_accepted = SpeakerFactory(event=event)
        accepted_sub = SubmissionFactory(event=event, state="accepted")
        accepted_sub.speakers.add(speaker_accepted)
        speaker_rejected = SpeakerFactory(event=event)
        rejected_sub = SubmissionFactory(event=event, state="rejected")
        rejected_sub.speakers.add(speaker_rejected)

        form = SpeakerFilterForm(data={"role": "false"}, event=event)
        assert form.is_valid(), form.errors

        qs = SpeakerProfile.objects.filter(event=event)
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {speaker_rejected}


@pytest.mark.parametrize(
    ("filter_value", "expect_arrived"), (("true", True), ("false", False))
)
@pytest.mark.django_db
def test_speaker_filter_form_filter_queryset_arrived(filter_value, expect_arrived):
    with scopes_disabled():
        event = EventFactory()
        arrived = SpeakerFactory(event=event, has_arrived=True)
        not_arrived = SpeakerFactory(event=event, has_arrived=False)

        form = SpeakerFilterForm(
            data={"arrived": filter_value}, event=event, filter_arrival=True
        )
        assert form.is_valid(), form.errors

        qs = SpeakerProfile.objects.filter(event=event)
        filtered = form.filter_queryset(qs)

    expected = {arrived} if expect_arrived else {not_arrived}
    assert set(filtered) == expected


@pytest.mark.django_db
def test_speaker_filter_form_filter_queryset_no_filters():
    """With no filters set, all profiles are returned."""
    with scopes_disabled():
        event = EventFactory()
        speaker1 = SpeakerFactory(event=event)
        speaker2 = SpeakerFactory(event=event)

        form = SpeakerFilterForm(data={}, event=event)
        assert form.is_valid(), form.errors

        qs = SpeakerProfile.objects.filter(event=event)
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {speaker1, speaker2}


@pytest.mark.django_db
def test_user_speaker_filter_form_init_shows_events_field_for_multiple_events():
    with scopes_disabled():
        event1 = EventFactory()
        event2 = EventFactory()
        events = EventFactory._meta.model.objects.filter(pk__in=[event1.pk, event2.pk])

        form = UserSpeakerFilterForm(events=events)

    assert "events" in form.fields


@pytest.mark.django_db
def test_user_speaker_filter_form_init_hides_events_field_for_single_event():
    with scopes_disabled():
        event = EventFactory()
        events = EventFactory._meta.model.objects.filter(pk=event.pk)

        form = UserSpeakerFilterForm(events=events)

    assert "events" not in form.fields


@pytest.mark.parametrize(
    ("role", "expect_speaker", "expect_submitter"),
    (("speaker", True, False), ("submitter", False, True)),
)
@pytest.mark.django_db
def test_user_speaker_filter_form_filter_queryset_by_role(
    role, expect_speaker, expect_submitter
):
    with scopes_disabled():
        event = EventFactory()
        speaker_user = UserFactory()
        SpeakerFactory(user=speaker_user, event=event)
        accepted_sub = SubmissionFactory(event=event, state="accepted")
        accepted_sub.speakers.add(speaker_user.profiles.first())

        submitter_user = UserFactory()
        SpeakerFactory(user=submitter_user, event=event)
        rejected_sub = SubmissionFactory(event=event, state="rejected")
        rejected_sub.speakers.add(submitter_user.profiles.first())

        events = EventFactory._meta.model.objects.filter(pk=event.pk)
        form = UserSpeakerFilterForm(data={"role": role}, events=events)
        assert form.is_valid(), form.errors

        qs = User.objects.filter(profiles__event=event).annotate(
            accepted_submission_count=_accepted_submission_count(event)
        )
        filtered = form.filter_queryset(qs)

    expected = set()
    if expect_speaker:
        expected.add(speaker_user)
    if expect_submitter:
        expected.add(submitter_user)
    assert set(filtered) == expected


@pytest.mark.django_db
def test_user_speaker_filter_form_filter_queryset_all_role():
    """role='all' returns all users regardless of submission state."""
    with scopes_disabled():
        event = EventFactory()
        speaker_user = UserFactory()
        SpeakerFactory(user=speaker_user, event=event)
        accepted_sub = SubmissionFactory(event=event, state="accepted")
        accepted_sub.speakers.add(speaker_user.profiles.first())

        submitter_user = UserFactory()
        SpeakerFactory(user=submitter_user, event=event)

        events = EventFactory._meta.model.objects.filter(pk=event.pk)
        form = UserSpeakerFilterForm(data={"role": "all"}, events=events)
        assert form.is_valid(), form.errors

        qs = User.objects.filter(profiles__event=event).annotate(
            accepted_submission_count=_accepted_submission_count(event)
        )
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {speaker_user, submitter_user}


@pytest.mark.django_db
def test_user_speaker_filter_form_filter_queryset_filters_by_events():
    with scopes_disabled():
        event1 = EventFactory()
        event2 = EventFactory()
        user1 = UserFactory()
        SpeakerFactory(user=user1, event=event1)
        user2 = UserFactory()
        SpeakerFactory(user=user2, event=event2)

        events = EventFactory._meta.model.objects.filter(pk__in=[event1.pk, event2.pk])
        form = UserSpeakerFilterForm(
            data={"role": "all", "events": [event1.pk]}, events=events
        )
        assert form.is_valid(), form.errors

        qs = User.objects.filter(profiles__event__in=[event1, event2]).annotate(
            accepted_submission_count=_accepted_submission_count(event1)
        )
        filtered = form.filter_queryset(qs)

    assert set(filtered) == {user1}


def _accepted_submission_count(event):
    """Helper to annotate users with accepted submission count for an event."""
    return Count(
        "profiles__submissions",
        filter=Q(
            profiles__event=event,
            profiles__submissions__state__in=SubmissionStates.accepted_states,
        ),
    )
