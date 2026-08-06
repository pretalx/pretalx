# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest
from django_scopes import scope, scopes_disabled

from pretalx.common.forms.widgets import MarkdownWidget
from pretalx.person.interfaces.forms import (
    OrgaProfileForm,
    SpeakerAvailabilityForm,
    SpeakerInviteForm,
    SpeakerMergeForm,
    SpeakerProfileForm,
)
from pretalx.person.interfaces.forms.widgets import BiographyWidget
from tests.factories import (
    AnswerFactory,
    AvailabilityFactory,
    EventFactory,
    ProfilePictureFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

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


def test_speaker_profile_form_locale_choices_limited_to_event_locales():
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event)

    form = SpeakerProfileForm(event=event, instance=speaker, is_orga=True)

    assert [code for code, _ in form.fields["locale"].choices if code] == ["en", "de"]
    assert form.fields["locale"].choices[0][0] == ""


def test_speaker_profile_form_locale_saves_profile_not_user():
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event, user__locale="en")

    form = SpeakerProfileForm(
        data={"name": "Speaker", "biography": "A bio", "locale": "de"},
        event=event,
        instance=speaker,
        is_orga=True,
    )
    assert form.is_valid(), form.errors
    form.save()

    speaker.refresh_from_db()
    speaker.user.refresh_from_db()
    assert speaker.locale == "de"
    assert speaker.user.locale == "en"
    assert speaker.effective_locale == "de"


def test_speaker_profile_form_locale_rejects_unoffered_language():
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event)

    form = SpeakerProfileForm(
        data={"name": "Speaker", "biography": "A bio", "locale": "fr"},
        event=event,
        instance=speaker,
        is_orga=True,
    )

    assert not form.is_valid()
    assert "locale" in form.errors


def test_speaker_profile_form_locale_optional_clears_override():
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event, locale="de")

    form = SpeakerProfileForm(
        data={"name": "Speaker", "biography": "A bio", "locale": ""},
        event=event,
        instance=speaker,
        is_orga=True,
    )
    assert form.is_valid(), form.errors
    form.save()

    speaker.refresh_from_db()
    assert speaker.locale is None


def test_speaker_profile_form_locale_fallback_label_ignores_unoffered_user_locale():
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event, user__locale="fr")

    form = SpeakerProfileForm(event=event, instance=speaker, is_orga=True)

    assert "English" in str(form.fields["locale"].choices[0][1])


def test_speaker_profile_form_email_help_text_from_cfp_config_wins():
    speaker = SpeakerFactory(user__email="account@test.com")
    field_config = [{"key": "email", "help_text": "Custom email help"}]

    form = SpeakerProfileForm(
        event=speaker.event, instance=speaker, field_configuration=field_config
    )

    assert "Custom email help" in str(form.fields["email"].help_text)
    assert "account email address" not in str(form.fields["email"].help_text)
    assert form.fields["email"].widget.attrs["placeholder"] == "account@test.com"


def test_speaker_profile_form_locale_hidden_for_speaker_facing_form():
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event)

    form = SpeakerProfileForm(event=event, instance=speaker)

    assert "locale" not in form.fields


def test_speaker_profile_form_applies_cfp_labels_without_field_configuration():
    event = EventFactory()
    event.cfp.settings["flow"] = {
        "steps": {"profile": {"fields": [{"key": "biography", "label": "Custom Bio"}]}}
    }
    event.cfp.save()
    speaker = SpeakerFactory(event=event)

    form = SpeakerProfileForm(event=event, instance=speaker, is_orga=True)

    assert str(form.fields["biography"].label) == "Custom Bio"


def test_speaker_profile_form_locale_hidden_for_single_locale_event():
    speaker = SpeakerFactory()

    form = SpeakerProfileForm(event=speaker.event, instance=speaker, is_orga=True)

    assert "locale" not in form.fields


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


def test_speaker_invite_form_requires_invitation_link():
    speaker = SpeakerFactory(user=None, email="managed@example.com")

    with scope(event=speaker.event):
        form = SpeakerInviteForm(
            profile=speaker,
            data={"subject": "Claim your profile", "text": "No link in here."},
        )
        valid = form.is_valid()

    assert not valid
    assert "text" in form.errors


def test_speaker_invite_form_accepts_text_with_invitation_link():
    speaker = SpeakerFactory(user=None, email="managed@example.com")

    with scope(event=speaker.event):
        form = SpeakerInviteForm(
            profile=speaker,
            data={
                "subject": "Claim your profile",
                "text": "Please claim it: {invitation_link}",
            },
        )
        valid = form.is_valid()

    assert valid, form.errors


def test_speaker_invite_form_empty_subject_skips_placeholder_validation():
    speaker = SpeakerFactory(user=None, email="managed@example.com")

    with scope(event=speaker.event):
        form = SpeakerInviteForm(
            profile=speaker,
            data={"subject": "", "text": "Please claim it: {invitation_link}"},
        )
        valid = form.is_valid()

    assert not valid
    assert list(form.errors) == ["subject"]


@pytest.mark.parametrize("with_submission", (False, True))
def test_speaker_invite_form_always_uses_standalone_template(with_submission):
    speaker = SpeakerFactory(user=None, email="managed@example.com")

    with scope(event=speaker.event):
        if with_submission:
            SubmissionFactory(event=speaker.event).speakers.add(speaker)
        form = SpeakerInviteForm(profile=speaker)

    assert "{proposal_title}" not in form.initial["text"]
    assert "{invitation_link}" in form.initial["text"]


def test_speaker_merge_form_builds_items_for_all_kinds():
    with scopes_disabled():
        event = EventFactory()
        merged = SpeakerFactory(
            event=event,
            user=None,
            name="Managed",
            email="managed@example.com",
            biography="A **bold** biography",
            profile_picture=ProfilePictureFactory(user=None),
        )
        survivor = SpeakerFactory(event=event, name="Own Name")
        AvailabilityFactory(event=event, person=merged)
        answered = QuestionFactory(event=event, target="speaker")
        unanswered = QuestionFactory(event=event, target="speaker")
        AnswerFactory(
            question=answered, speaker=merged, submission=None, answer="Merged answer"
        )

    with scope(event=event):
        form = SpeakerMergeForm(merged=merged, survivor=survivor)

    field_names = set(form.fields)
    assert field_names == {
        "name",
        "biography",
        "email",
        "picture",
        "availability",
        f"question_{answered.pk}",
    }
    # Questions neither profile answered get no chooser item.
    assert f"question_{unanswered.pk}" not in field_names
    items = {item["field"].name: item for item in form.items}
    assert items["name"]["merged"] == "Managed"
    assert items["name"]["survivor"] == "Own Name"
    assert items["name"]["kind"] == "text"
    assert items["biography"]["kind"] == "markdown"
    assert items[f"question_{answered.pk}"]["merged"] == "Merged answer"
    assert items[f"question_{answered.pk}"]["survivor"] == ""
    assert items["picture"]["kind"] == "picture"
    assert items["availability"]["kind"] == "availability"


def test_speaker_merge_form_defaults_to_non_empty_side():
    with scopes_disabled():
        event = EventFactory()
        merged = SpeakerFactory(
            event=event, user=None, name="Managed", email="managed@example.com"
        )
        survivor = SpeakerFactory(event=event, name="Own Name", email=None)
        survivor.user.email = "account@example.com"
        survivor.user.save()

    with scope(event=event):
        form = SpeakerMergeForm(merged=merged, survivor=survivor)

    assert form.fields["name"].initial == "survivor"
    # Only the merged side has a contact email set.
    assert form.fields["email"].initial == "merged"
