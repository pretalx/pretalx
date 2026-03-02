# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest
from django.db.models import Count, Q

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

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_get_email_address_error():
    result = get_email_address_error()
    assert isinstance(result, str)
    assert len(result) > 0


def test_speaker_profile_form_init_creates_profile_for_user():
    """When a user has no profile for the event yet, get_speaker creates one."""
    event = EventFactory()
    user = UserFactory()

    form = SpeakerProfileForm(event=event, user=user)

    assert form.instance is not None
    assert form.instance.event == event
    assert form.instance.user == user


def test_speaker_profile_form_init_uses_existing_profile():
    speaker = SpeakerFactory(biography="Existing bio")
    event = speaker.event
    user = speaker.user

    form = SpeakerProfileForm(event=event, user=user)

    assert form.instance == speaker


def test_speaker_profile_form_init_name_from_profile():
    speaker = SpeakerFactory(name="Profile Name")

    form = SpeakerProfileForm(event=speaker.event, user=speaker.user)

    assert form.fields["name"].initial == "Profile Name"


def test_speaker_profile_form_init_name_falls_back_to_user():
    event = EventFactory()
    user = UserFactory(name="User Name")

    form = SpeakerProfileForm(event=event, user=user)

    assert form.fields["name"].initial == "User Name"


def test_speaker_profile_form_init_name_falls_back_to_kwarg():
    event = EventFactory()

    form = SpeakerProfileForm(event=event, user=None, name="Given Name")

    assert form.fields["name"].initial == "Given Name"


@pytest.mark.parametrize(
    ("with_email", "expect_present"), ((True, True), (False, False))
)
def test_speaker_profile_form_init_email_field_presence(with_email, expect_present):
    event = EventFactory()
    user = UserFactory(email="speaker@test.com")

    form = SpeakerProfileForm(event=event, user=user, with_email=with_email)

    assert ("email" in form.fields) is expect_present
    if expect_present:
        assert form.fields["email"].initial == "speaker@test.com"


def test_speaker_profile_form_init_without_user_excludes_first_time_fields():
    """Without a user, FIRST_TIME_EXCLUDE fields (email) are excluded."""
    event = EventFactory()

    form = SpeakerProfileForm(event=event, user=None)

    assert "email" not in form.fields


def test_speaker_profile_form_user_fields_with_essential_only():
    """essential_only=True behaves like no-user: excludes FIRST_TIME_EXCLUDE fields."""
    event = EventFactory()
    user = UserFactory()

    form = SpeakerProfileForm(event=event, user=user, essential_only=True)

    assert "email" not in form.fields


def test_speaker_profile_form_init_read_only_disables_fields():
    event = EventFactory()
    user = UserFactory()

    form = SpeakerProfileForm(event=event, user=user, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_speaker_profile_form_reorders_fields_with_field_configuration():
    event = EventFactory()
    user = UserFactory()
    field_config = [{"key": "biography"}, {"key": "name"}, {"key": "avatar"}]

    form = SpeakerProfileForm(event=event, user=user, field_configuration=field_config)

    keys = list(form.fields.keys())
    assert keys.index("biography") < keys.index("name")


def test_speaker_profile_form_biography_suggestions_shown_when_other_profiles_exist():
    """When the user has bios on other events, the BiographyWidget is used."""
    event = EventFactory()
    other_event = EventFactory()
    user = UserFactory()
    SpeakerFactory(user=user, event=event, biography="")
    SpeakerFactory(
        user=user, event=other_event, biography="I speak at many conferences."
    )

    form = SpeakerProfileForm(event=event, user=user)

    assert isinstance(form.fields["biography"].widget, BiographyWidget)


def test_speaker_profile_form_no_suggestions_when_biography_already_exists():
    other_event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(user=user, biography="I have a bio already.")
    SpeakerFactory(user=user, event=other_event, biography="Other bio")

    form = SpeakerProfileForm(event=speaker.event, user=user)

    assert isinstance(form.fields["biography"].widget, MarkdownWidget)
    assert not isinstance(form.fields["biography"].widget, BiographyWidget)


def test_speaker_profile_form_no_suggestions_without_other_profiles():
    event = EventFactory()
    user = UserFactory()
    SpeakerFactory(user=user, event=event, biography="")

    form = SpeakerProfileForm(event=event, user=user)

    assert isinstance(form.fields["biography"].widget, MarkdownWidget)
    assert not isinstance(form.fields["biography"].widget, BiographyWidget)


def test_speaker_profile_form_no_suggestions_for_orga():
    """Orga users don't see biography suggestions from other events."""
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
def test_speaker_profile_form_clean_email_rejects_duplicate(input_email):
    event = EventFactory()
    UserFactory(email="taken@example.com")
    user = UserFactory()
    data = {"email": input_email, "name": "Test", "biography": ""}

    form = SpeakerProfileForm(data=data, event=event, user=user)

    assert not form.is_valid()
    assert "email" in form.errors


def test_speaker_profile_form_clean_email_allows_own_email():
    event = EventFactory()
    user = UserFactory(email="me@example.com")
    data = {"email": "me@example.com", "name": "Test", "biography": "A biography"}

    form = SpeakerProfileForm(data=data, event=event, user=user)

    assert form.is_valid(), form.errors


def test_speaker_profile_form_save_updates_user_email():
    event = EventFactory()
    user = UserFactory(email="old@example.com")
    data = {"email": "new@example.com", "name": "Speaker", "biography": "A bio"}

    form = SpeakerProfileForm(data=data, event=event, user=user)
    assert form.is_valid(), form.errors
    form.save()

    user.refresh_from_db()
    assert user.email == "new@example.com"


def test_speaker_profile_form_save_creates_speaker_profile():
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


def test_speaker_profile_form_save_syncs_name_to_user_if_user_has_no_name():
    event = EventFactory()
    user = UserFactory(name="")
    data = {"email": user.email, "name": "Brand New Name", "biography": "A biography"}

    form = SpeakerProfileForm(data=data, event=event, user=user)
    assert form.is_valid(), form.errors
    form.save()

    user.refresh_from_db()
    assert user.name == "Brand New Name"


def test_speaker_profile_form_save_does_not_overwrite_existing_user_name():
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
def test_speaker_profile_form_avatar_required_matches_cfp(visibility, expect_required):
    event = EventFactory(cfp__fields={"avatar": {"visibility": visibility}})
    user = UserFactory()

    form = SpeakerProfileForm(event=event, user=user)

    assert form.fields["avatar"].required is expect_required


def test_speaker_profile_form_hides_field_when_do_not_ask():
    event = EventFactory(cfp__fields={"biography": {"visibility": "do_not_ask"}})
    user = UserFactory()

    form = SpeakerProfileForm(event=event, user=user)

    assert "biography" not in form.fields


def test_speaker_profile_form_init_availabilities_when_enabled():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "optional"}})
    user = UserFactory()

    form = SpeakerProfileForm(event=event, user=user)

    assert "availabilities" in form.fields
    assert form.fields["availabilities"].event == event


def test_speaker_profile_form_availability_error_fallback():
    """When bound form has availability errors, data is restored from initial."""
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "required"}})
    user = UserFactory()
    data = {
        "email": user.email,
        "name": "Test",
        "biography": "A bio",
        "availabilities": "invalid json!!!",
    }

    form = SpeakerProfileForm(data=data, event=event, user=user)

    assert not form.is_valid()
    assert "availabilities" in form.errors


def test_speaker_profile_form_save_with_availabilities():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "optional"}})
    user = UserFactory()
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

    assert result.availabilities.count() == 1


def test_speaker_profile_form_init_without_avatar_when_do_not_ask():
    event = EventFactory(cfp__fields={"avatar": {"visibility": "do_not_ask"}})
    user = UserFactory()

    form = SpeakerProfileForm(event=event, user=user)

    assert "avatar" not in form.fields


def test_speaker_profile_form_save_without_avatar():
    """save() works when avatar field was removed by do_not_ask."""
    event = EventFactory(cfp__fields={"avatar": {"visibility": "do_not_ask"}})
    user = UserFactory()
    data = {"email": user.email, "name": "Test", "biography": "A bio"}

    form = SpeakerProfileForm(data=data, event=event, user=user)
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.pk is not None
    assert result.name == "Test"


def test_speaker_availability_form_init_creates_field_when_event_and_speaker():
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


def test_speaker_availability_form_save_replaces_availabilities():
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

    assert result == speaker
    assert speaker.availabilities.count() == 1


def test_orga_profile_form_has_name_and_locale_fields():
    user = UserFactory()

    form = OrgaProfileForm(instance=user)

    assert set(form.fields.keys()) == {"name", "locale"}


def test_orga_profile_form_save_updates_user():
    user = UserFactory(name="Old Name", locale="en")
    data = {"name": "New Name", "locale": "de"}

    form = OrgaProfileForm(data=data, instance=user)
    assert form.is_valid(), form.errors
    form.save()

    user.refresh_from_db()
    assert user.name == "New Name"
    assert user.locale == "de"


def test_speaker_filter_form_init_sets_question_queryset():
    event = EventFactory()
    question = QuestionFactory(event=event)
    QuestionFactory()  # different event

    form = SpeakerFilterForm(event=event)

    assert list(form.fields["question"].queryset) == [question]


@pytest.mark.parametrize(
    ("filter_arrival", "expect_present"), ((False, False), (True, True))
)
def test_speaker_filter_form_init_arrived_field_presence(
    filter_arrival, expect_present
):
    event = EventFactory()

    form = SpeakerFilterForm(event=event, filter_arrival=filter_arrival)

    assert ("arrived" in form.fields) is expect_present


def test_speaker_filter_form_filter_queryset_role_true_filters_accepted():
    """role='true' filters to speakers with accepted/confirmed submissions."""
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


def test_speaker_filter_form_filter_queryset_role_false_excludes_accepted():
    """role='false' filters to non-accepted submitters."""
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
def test_speaker_filter_form_filter_queryset_arrived(filter_value, expect_arrived):
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


def test_speaker_filter_form_filter_queryset_no_filters():
    event = EventFactory()
    speaker1 = SpeakerFactory(event=event)
    speaker2 = SpeakerFactory(event=event)

    form = SpeakerFilterForm(data={}, event=event)
    assert form.is_valid(), form.errors

    qs = SpeakerProfile.objects.filter(event=event)
    filtered = form.filter_queryset(qs)

    assert set(filtered) == {speaker1, speaker2}


def test_user_speaker_filter_form_init_shows_events_field_for_multiple_events():
    event1 = EventFactory()
    event2 = EventFactory()
    events = EventFactory._meta.model.objects.filter(pk__in=[event1.pk, event2.pk])

    form = UserSpeakerFilterForm(events=events)

    assert "events" in form.fields


def test_user_speaker_filter_form_init_hides_events_field_for_single_event():
    event = EventFactory()
    events = EventFactory._meta.model.objects.filter(pk=event.pk)

    form = UserSpeakerFilterForm(events=events)

    assert "events" not in form.fields


@pytest.mark.parametrize(
    ("role", "expect_speaker", "expect_submitter"),
    (("speaker", True, False), ("submitter", False, True)),
)
def test_user_speaker_filter_form_filter_queryset_by_role(
    role, expect_speaker, expect_submitter
):
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


def test_user_speaker_filter_form_filter_queryset_all_role():
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


def test_user_speaker_filter_form_filter_queryset_filters_by_events():
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
