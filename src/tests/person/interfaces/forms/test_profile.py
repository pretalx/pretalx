# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest

from pretalx.common.forms.widgets import MarkdownWidget
from pretalx.person.interfaces.forms import (
    OrgaProfileForm,
    SpeakerAvailabilityForm,
    SpeakerProfileForm,
)
from pretalx.person.interfaces.forms.widgets import BiographyWidget
from tests.factories import EventFactory, SpeakerFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_speaker_profile_form_init_uses_given_instance():
    speaker = SpeakerFactory(biography="Existing bio")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert form.instance == speaker
    assert form.user == speaker.user


def test_speaker_profile_form_init_keeps_instance_for_managed_profile():
    speaker = SpeakerFactory(user=None, name="Managed", biography="Managed bio")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert form.instance == speaker
    assert form.user is None
    assert form.fields["name"].initial == "Managed"


def test_speaker_profile_form_init_name_from_profile():
    speaker = SpeakerFactory(name="Profile Name")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert form.fields["name"].initial == "Profile Name"


def test_speaker_profile_form_init_name_falls_back_to_user():
    speaker = SpeakerFactory(name="", user__name="User Name")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert form.fields["name"].initial == "User Name"


def test_speaker_profile_form_init_name_falls_back_to_kwarg():
    event = EventFactory()

    form = SpeakerProfileForm(event=event, name="Given Name")

    assert form.fields["name"].initial == "Given Name"


@pytest.mark.parametrize(
    ("with_email", "expect_present"), ((True, True), (False, False))
)
def test_speaker_profile_form_init_email_field_presence(with_email, expect_present):
    speaker = SpeakerFactory(user__email="speaker@test.com")

    form = SpeakerProfileForm(
        event=speaker.event, instance=speaker, with_email=with_email
    )

    assert ("email" in form.fields) is expect_present
    if expect_present:
        assert not form.initial.get("email")
        assert form.fields["email"].widget.attrs["placeholder"] == "speaker@test.com"


def test_speaker_profile_form_email_initial_from_profile_override():
    speaker = SpeakerFactory(email="contact@test.com", user__email="account@test.com")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert form.initial["email"] == "contact@test.com"


def test_speaker_profile_form_email_field_shown_for_managed_speaker():
    speaker = SpeakerFactory(user=None, name="Managed")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert "email" in form.fields
    assert "placeholder" not in form.fields["email"].widget.attrs


def test_speaker_profile_form_init_without_instance_excludes_email_field():
    event = EventFactory()

    form = SpeakerProfileForm(event=event)

    assert "email" not in form.fields


def test_speaker_profile_form_essential_only_excludes_email_field():
    speaker = SpeakerFactory()

    form = SpeakerProfileForm(
        event=speaker.event, instance=speaker, essential_only=True
    )

    assert "email" not in form.fields


def test_speaker_profile_form_init_read_only_disables_fields():
    speaker = SpeakerFactory()

    form = SpeakerProfileForm(event=speaker.event, instance=speaker, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_speaker_profile_form_reorders_fields_with_field_configuration():
    event = EventFactory()
    field_config = [{"key": "biography"}, {"key": "name"}, {"key": "avatar"}]

    form = SpeakerProfileForm(event=event, field_configuration=field_config)

    keys = list(form.fields.keys())
    assert keys.index("biography") < keys.index("name")


def test_speaker_profile_form_biography_suggestions_shown_when_other_profiles_exist():
    event = EventFactory()
    other_event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(user=user, event=event, biography="")
    SpeakerFactory(
        user=user, event=other_event, biography="I speak at many conferences."
    )

    form = SpeakerProfileForm(event=event, instance=speaker)

    assert isinstance(form.fields["biography"].widget, BiographyWidget)


def test_speaker_profile_form_no_suggestions_without_other_profiles():
    event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(user=user, event=event, biography="")

    form = SpeakerProfileForm(event=event, instance=speaker)

    assert isinstance(form.fields["biography"].widget, MarkdownWidget)
    assert not isinstance(form.fields["biography"].widget, BiographyWidget)


def test_speaker_profile_form_no_suggestions_when_biography_already_exists():
    other_event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(user=user, biography="I have a bio already.")
    SpeakerFactory(user=user, event=other_event, biography="Other bio")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert isinstance(form.fields["biography"].widget, MarkdownWidget)
    assert not isinstance(form.fields["biography"].widget, BiographyWidget)


def test_speaker_profile_form_no_suggestions_for_orga():
    event = EventFactory()
    other_event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(user=user, event=event, biography="")
    SpeakerFactory(
        user=user, event=other_event, biography="I speak at many conferences."
    )

    form = SpeakerProfileForm(event=event, instance=speaker, is_orga=True)

    assert isinstance(form.fields["biography"].widget, MarkdownWidget)
    assert not isinstance(form.fields["biography"].widget, BiographyWidget)


def test_speaker_profile_form_accepts_contact_email_of_other_account():
    UserFactory(email="taken@example.com")
    speaker = SpeakerFactory()

    form = SpeakerProfileForm(
        data={"email": "taken@example.com", "name": "Test", "biography": "A bio"},
        event=speaker.event,
        instance=speaker,
    )
    assert form.is_valid(), form.errors
    form.save()

    speaker.refresh_from_db()
    assert speaker.email == "taken@example.com"


def test_speaker_profile_form_save_sets_profile_email_not_account_email():
    speaker = SpeakerFactory(user__email="old@example.com")
    user = speaker.user

    form = SpeakerProfileForm(
        data={"email": "new@example.com", "name": "Speaker", "biography": "A bio"},
        event=speaker.event,
        instance=speaker,
    )
    assert form.is_valid(), form.errors
    form.save()

    speaker.refresh_from_db()
    user.refresh_from_db()
    assert speaker.email == "new@example.com"
    assert user.email == "old@example.com"
    assert speaker.effective_email == "new@example.com"


def test_speaker_profile_form_clearing_email_falls_back_to_account():
    speaker = SpeakerFactory(
        email="contact@example.com", user__email="account@example.com"
    )

    form = SpeakerProfileForm(
        data={"email": "", "name": "Speaker", "biography": "A bio"},
        event=speaker.event,
        instance=speaker,
    )
    assert form.is_valid(), form.errors
    form.save()

    speaker.refresh_from_db()
    assert speaker.email is None
    assert speaker.effective_email == "account@example.com"


def test_speaker_profile_form_saves_email_for_managed_speaker():
    speaker = SpeakerFactory(user=None, name="Managed")

    form = SpeakerProfileForm(
        data={"email": "contact@example.com", "name": "Managed", "biography": "Bio"},
        event=speaker.event,
        instance=speaker,
    )
    assert form.is_valid(), form.errors
    form.save()

    speaker.refresh_from_db()
    assert speaker.email == "contact@example.com"
    assert speaker.effective_email == "contact@example.com"


def test_speaker_profile_form_save_updates_profile_in_place():
    speaker = SpeakerFactory(name="Old Name")

    form = SpeakerProfileForm(
        data={
            "email": speaker.user.email,
            "name": "New Speaker",
            "biography": "My bio",
        },
        event=speaker.event,
        instance=speaker,
    )
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.pk == speaker.pk
    assert result.event == speaker.event
    assert result.user == speaker.user
    assert result.name == "New Speaker"


@pytest.mark.parametrize(
    ("visibility", "expect_required"), (("required", True), ("optional", False))
)
def test_speaker_profile_form_avatar_required_matches_cfp(visibility, expect_required):
    event = EventFactory(cfp__fields={"avatar": {"visibility": visibility}})

    form = SpeakerProfileForm(event=event)

    assert form.fields["avatar"].required is expect_required


def test_speaker_profile_form_hides_field_when_do_not_ask():
    event = EventFactory(cfp__fields={"biography": {"visibility": "do_not_ask"}})

    form = SpeakerProfileForm(event=event)

    assert "biography" not in form.fields


def test_speaker_profile_form_init_availabilities_when_enabled():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "optional"}})

    form = SpeakerProfileForm(event=event)

    assert "availabilities" in form.fields
    assert form.fields["availabilities"].event == event


def test_speaker_profile_form_availability_error_fallback():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "required"}})
    speaker = SpeakerFactory(event=event)

    form = SpeakerProfileForm(
        data={
            "email": speaker.user.email,
            "name": "Test",
            "biography": "A bio",
            "availabilities": "invalid json!!!",
        },
        event=event,
        instance=speaker,
    )

    assert not form.is_valid()
    assert "availabilities" in form.errors


def test_speaker_profile_form_save_with_availabilities():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "optional"}})
    speaker = SpeakerFactory(event=event)
    avail_data = {
        "availabilities": [
            {
                "start": event.date_from.isoformat() + " 10:00:00+00:00",
                "end": event.date_from.isoformat() + " 18:00:00+00:00",
            }
        ]
    }

    form = SpeakerProfileForm(
        data={
            "email": speaker.user.email,
            "name": "Test",
            "biography": "A bio",
            "availabilities": json.dumps(avail_data),
        },
        event=event,
        instance=speaker,
    )
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.availabilities.count() == 1


def test_speaker_profile_form_init_without_avatar_when_do_not_ask():
    event = EventFactory(cfp__fields={"avatar": {"visibility": "do_not_ask"}})

    form = SpeakerProfileForm(event=event)

    assert "avatar" not in form.fields


def test_speaker_profile_form_save_without_avatar():
    event = EventFactory(cfp__fields={"avatar": {"visibility": "do_not_ask"}})
    speaker = SpeakerFactory(event=event)

    form = SpeakerProfileForm(
        data={"email": speaker.user.email, "name": "Test", "biography": "A bio"},
        event=event,
        instance=speaker,
    )
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.pk == speaker.pk
    assert result.name == "Test"


def test_speaker_availability_form_init_creates_field_when_event_and_speaker():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "optional"}})
    speaker = SpeakerFactory(event=event)

    form = SpeakerAvailabilityForm(event=event, speaker=speaker)

    assert "availabilities" in form.fields
    assert form.fields["availabilities"].required is False


def test_speaker_availability_form_init_marks_field_required_when_required():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "required"}})
    speaker = SpeakerFactory(event=event)

    form = SpeakerAvailabilityForm(event=event, speaker=speaker)

    assert form.fields["availabilities"].required is True


def test_speaker_availability_form_init_no_field_when_availabilities_not_requested():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "do_not_ask"}})
    speaker = SpeakerFactory(event=event)

    form = SpeakerAvailabilityForm(event=event, speaker=speaker)

    assert "availabilities" not in form.fields


def test_speaker_availability_form_init_no_field_without_event_and_speaker():
    form = SpeakerAvailabilityForm()

    assert "availabilities" not in form.fields


def test_speaker_availability_form_save_returns_none_without_cleaned_data():
    form = SpeakerAvailabilityForm()

    assert form.save() is None


def test_speaker_availability_form_save_skips_replace_without_availabilities_field():
    form = SpeakerAvailabilityForm(data={})
    assert form.is_valid()

    assert form.save() is None


def test_speaker_availability_form_save_replaces_availabilities():
    event = EventFactory(cfp__fields={"availabilities": {"visibility": "optional"}})
    speaker = SpeakerFactory(event=event)
    avail_data = {
        "availabilities": [
            {
                "start": event.date_from.isoformat() + " 10:00:00+00:00",
                "end": event.date_from.isoformat() + " 18:00:00+00:00",
            }
        ]
    }

    form = SpeakerAvailabilityForm(
        data={"availabilities": json.dumps(avail_data)}, event=event, speaker=speaker
    )
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

    form = OrgaProfileForm(data={"name": "New Name", "locale": "de"}, instance=user)
    assert form.is_valid(), form.errors
    form.save()

    user.refresh_from_db()
    assert user.name == "New Name"
    assert user.locale == "de"
