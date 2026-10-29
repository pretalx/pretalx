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
from pretalx.person.models import SpeakerProfile
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


def test_speaker_profile_form_init_uses_instance_and_its_name():
    speaker = SpeakerFactory(name="Profile Name", biography="Existing bio")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert form.instance == speaker
    assert form.user == speaker.user
    assert form.fields["name"].initial == "Profile Name"


def test_speaker_profile_form_init_name_falls_back_to_user():
    speaker = SpeakerFactory(name="", user__name="User Name")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert form.fields["name"].initial == "User Name"


def test_speaker_profile_form_init_name_falls_back_to_kwarg():
    event = EventFactory()

    form = SpeakerProfileForm(event=event, name="Given Name")

    assert form.fields["name"].initial == "Given Name"


def test_speaker_profile_form_managed_speaker_shows_and_saves_contact_email():
    speaker = SpeakerFactory(user=None, name="Managed", biography="Managed bio")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert form.instance == speaker
    assert form.user is None
    assert form.fields["name"].initial == "Managed"
    assert "email" in form.fields
    assert "placeholder" not in form.fields["email"].widget.attrs

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


def test_speaker_profile_form_email_field_shows_contact_initial_and_account_placeholder():
    speaker = SpeakerFactory(email="contact@test.com", user__email="account@test.com")

    form = SpeakerProfileForm(event=speaker.event, instance=speaker)

    assert form.initial["email"] == "contact@test.com"
    assert form.fields["email"].widget.attrs["placeholder"] == "account@test.com"
    assert "account email address (account@test.com)" in str(
        form.fields["email"].help_text
    )


@pytest.mark.parametrize(
    "kwargs",
    ({"with_email": False}, {"essential_only": True}, {"instance": None}),
    ids=("without_email", "essential_only", "without_instance"),
)
def test_speaker_profile_form_excludes_email_field(kwargs):
    speaker = SpeakerFactory(user__email="speaker@test.com")

    form = SpeakerProfileForm(**{"event": speaker.event, "instance": speaker} | kwargs)

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


@pytest.mark.parametrize(
    ("own_biography", "other_biography", "is_orga", "widget_class"),
    (
        ("", "I speak at many conferences.", False, BiographyWidget),
        ("", "", False, MarkdownWidget),
        ("I have a bio already.", "Other bio", False, MarkdownWidget),
        ("", "I speak at many conferences.", True, MarkdownWidget),
    ),
    ids=("suggestions", "no_other_biography", "own_biography", "orga"),
)
def test_speaker_profile_form_biography_suggestions(
    own_biography, other_biography, is_orga, widget_class
):
    user = UserFactory()
    speaker = SpeakerFactory(user=user, biography=own_biography)
    SpeakerFactory(user=user, event=EventFactory(), biography=other_biography)

    form = SpeakerProfileForm(event=speaker.event, instance=speaker, is_orga=is_orga)

    assert type(form.fields["biography"].widget) is widget_class


def test_speaker_profile_form_save_sets_profile_email_not_account_email():
    UserFactory(email="taken@example.com")
    speaker = SpeakerFactory(name="Old Name", user__email="old@example.com")
    user = speaker.user

    form = SpeakerProfileForm(
        data={
            "email": "taken@example.com",
            "name": "New Speaker",
            "biography": "A bio",
        },
        event=speaker.event,
        instance=speaker,
    )
    assert form.is_valid(), form.errors
    result = form.save()

    user.refresh_from_db()
    assert result.pk == speaker.pk
    assert result.event == speaker.event
    assert result.user == user
    assert result.name == "New Speaker"
    assert result.email == "taken@example.com"
    assert result.effective_email == "taken@example.com"
    assert user.email == "old@example.com"

    form = SpeakerProfileForm(
        data={"email": "", "name": "New Speaker", "biography": "A bio"},
        event=speaker.event,
        instance=result,
    )
    assert form.is_valid(), form.errors
    form.save()

    speaker = SpeakerProfile.objects.select_related("user").get(pk=speaker.pk)
    assert speaker.email is None
    assert speaker.effective_email == "old@example.com"


def test_speaker_profile_form_locale_choices_limited_to_event_locales():
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event, user__locale="fr")

    form = SpeakerProfileForm(event=event, instance=speaker, is_orga=True)

    assert [code for code, _ in form.fields["locale"].choices if code] == ["en", "de"]
    assert form.fields["locale"].choices[0][0] == ""
    assert "English" in str(form.fields["locale"].choices[0][1])


def test_speaker_profile_form_locale_saves_profile_override_not_user():
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event, user__locale="en")
    data = {"name": "Speaker", "biography": "A bio"}

    form = SpeakerProfileForm(
        data=data | {"locale": "de"}, event=event, instance=speaker, is_orga=True
    )
    assert form.is_valid(), form.errors
    form.save()
    speaker = SpeakerProfile.objects.select_related("user", "event").get(pk=speaker.pk)
    assert speaker.locale == "de"
    assert speaker.user.locale == "en"
    assert speaker.effective_locale == "de"

    form = SpeakerProfileForm(
        data=data | {"locale": "fr"}, event=event, instance=speaker, is_orga=True
    )
    assert not form.is_valid()
    assert list(form.errors) == ["locale"]

    form = SpeakerProfileForm(
        data=data | {"locale": ""}, event=event, instance=speaker, is_orga=True
    )
    assert form.is_valid(), form.errors
    form.save()
    speaker.refresh_from_db(fields=["locale"])
    assert speaker.locale is None


def test_speaker_profile_form_email_help_text_from_cfp_config_wins():
    speaker = SpeakerFactory(user__email="account@test.com")
    field_config = [{"key": "email", "help_text": "Custom email help"}]

    form = SpeakerProfileForm(
        event=speaker.event, instance=speaker, field_configuration=field_config
    )

    assert "Custom email help" in str(form.fields["email"].help_text)
    assert "account email address" not in str(form.fields["email"].help_text)
    assert form.fields["email"].widget.attrs["placeholder"] == "account@test.com"
    assert not form.initial.get("email")


@pytest.mark.parametrize(
    ("locales", "is_orga"),
    ((["en", "de"], False), (["en"], True)),
    ids=("speaker_facing", "single_locale"),
)
def test_speaker_profile_form_locale_hidden(locales, is_orga):
    event = EventFactory(locales=locales, locale="en")
    speaker = SpeakerFactory(event=event)

    form = SpeakerProfileForm(event=event, instance=speaker, is_orga=is_orga)

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


@pytest.mark.parametrize(
    ("field", "visibility", "required"),
    (
        ("avatar", "required", True),
        ("avatar", "optional", False),
        ("biography", "do_not_ask", None),
    ),
)
def test_speaker_profile_form_field_follows_cfp_visibility(field, visibility, required):
    event = EventFactory(cfp__fields={field: {"visibility": visibility}})

    form = SpeakerProfileForm(event=event)

    assert getattr(form.fields.get(field), "required", None) == required


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
    assert form.fields["availabilities"].event == event
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.availabilities.count() == 1


def test_speaker_profile_form_save_without_avatar():
    event = EventFactory(cfp__fields={"avatar": {"visibility": "do_not_ask"}})
    speaker = SpeakerFactory(event=event)

    form = SpeakerProfileForm(
        data={"email": speaker.user.email, "name": "Test", "biography": "A bio"},
        event=event,
        instance=speaker,
    )
    assert "avatar" not in form.fields
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.pk == speaker.pk
    assert result.name == "Test"


@pytest.mark.parametrize(
    ("visibility", "required"),
    (("optional", False), ("required", True), ("do_not_ask", None)),
)
def test_speaker_availability_form_field_follows_cfp_visibility(visibility, required):
    event = EventFactory(cfp__fields={"availabilities": {"visibility": visibility}})
    speaker = SpeakerFactory(event=event)

    form = SpeakerAvailabilityForm(event=event, speaker=speaker)

    assert getattr(form.fields.get("availabilities"), "required", None) == required


def test_speaker_availability_form_without_event_and_speaker_has_no_field_and_saves_nothing():
    unbound = SpeakerAvailabilityForm()
    bound = SpeakerAvailabilityForm(data={})

    assert "availabilities" not in unbound.fields
    assert unbound.save() is None
    assert bound.is_valid()
    assert bound.save() is None


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


def test_orga_profile_form_save_updates_user():
    user = UserFactory(name="Old Name", locale="en")

    form = OrgaProfileForm(data={"name": "New Name", "locale": "de"}, instance=user)
    assert form.is_valid(), form.errors
    form.save()

    user.refresh_from_db()
    assert user.name == "New Name"
    assert user.locale == "de"


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        (
            {
                "subject": "Claim your profile",
                "text": "Please claim it: {invitation_link}",
            },
            [],
        ),
        ({"subject": "Claim your profile", "text": "No link in here."}, ["text"]),
        ({"subject": "", "text": "Please claim it: {invitation_link}"}, ["subject"]),
    ),
    ids=("valid", "missing_invitation_link", "empty_subject"),
)
def test_speaker_invite_form_clean(data, errors):
    speaker = SpeakerFactory(user=None, email="managed@example.com")

    with scope(event=speaker.event):
        form = SpeakerInviteForm(profile=speaker, data=data)
        valid = form.is_valid()

    assert valid == (not errors), form.errors
    assert list(form.errors) == errors


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
