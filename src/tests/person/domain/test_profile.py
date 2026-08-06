# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core import mail as djmail
from django_scopes import scope, scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.enums import MailTemplateRoles, QueuedMailStates
from pretalx.person.domain.profile import (
    apply_speaker_profile_changes,
    claim_speaker_profile,
    create_speaker_profile,
    merge_speaker_profiles,
    profile_deletable_after_removal,
    retract_speaker_invite,
    send_speaker_invite,
    shred_speaker_profile,
)
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import Answer, SpeakerRole
from tests.factories import (
    AnswerFactory,
    AvailabilityFactory,
    EventFactory,
    FeedbackFactory,
    ProfilePictureFactory,
    QuestionFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

INVITE_KWARGS = {
    "subject": "Claim your speaker profile",
    "text": "Please claim your profile: {invitation_link}",
}


def test_apply_speaker_profile_changes_never_touches_account_email():
    profile = SpeakerFactory(
        user=UserFactory(email="old@example.com"), email="contact@example.com"
    )

    apply_speaker_profile_changes(profile, ["email"])
    profile.user.refresh_from_db()

    assert profile.user.email == "old@example.com"


def test_apply_speaker_profile_changes_managed_profile_is_noop():
    profile = SpeakerFactory(user=None, name="Managed Name")

    apply_speaker_profile_changes(profile, ["name", "email"])

    profile.refresh_from_db()
    assert profile.user is None
    assert profile.email is None


def test_apply_speaker_profile_changes_syncs_name_to_empty_user():
    user = UserFactory(name="")
    profile = SpeakerFactory(user=user, name="Fresh Name")

    apply_speaker_profile_changes(profile, ["name"])
    user.refresh_from_db()

    assert user.name == "Fresh Name"


def test_apply_speaker_profile_changes_does_not_overwrite_existing_user_name():
    user = UserFactory(name="Existing Name")
    profile = SpeakerFactory(user=user, name="Profile Name")

    apply_speaker_profile_changes(profile, ["name"])
    user.refresh_from_db()

    assert user.name == "Existing Name"


def test_apply_speaker_profile_changes_skips_name_not_in_changed_fields():
    user = UserFactory(name="")
    profile = SpeakerFactory(user=user, name="Profile Name")

    apply_speaker_profile_changes(profile, [])
    user.refresh_from_db()

    assert user.name == ""


def test_send_speaker_invite_mints_token_and_sends_directly():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=profile.event, speaker=profile)
    djmail.outbox = []

    with scope(event=profile.event):
        send_speaker_invite(profile, **INVITE_KWARGS)

    profile.refresh_from_db()
    assert profile.invitation_token
    assert profile.invitation_sent is not None
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["managed@example.com"]
    assert profile.invitation_token in djmail.outbox[0].body
    with scope(event=profile.event):
        mail = profile.mails.get()
        assert mail.state == QueuedMailStates.SENT


def test_send_speaker_invite_resend_rotates_token():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=profile.event, speaker=profile)
    djmail.outbox = []

    with scope(event=profile.event):
        send_speaker_invite(profile, **INVITE_KWARGS)
        profile.refresh_from_db()
        old_token = profile.invitation_token
        send_speaker_invite(profile, **INVITE_KWARGS)

    profile.refresh_from_db()
    assert profile.invitation_token != old_token
    assert len(djmail.outbox) == 2
    assert profile.invitation_token in djmail.outbox[1].body


def test_send_speaker_invite_uses_edited_subject_and_text():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    djmail.outbox = []

    with scope(event=profile.event):
        send_speaker_invite(
            profile,
            subject="Custom invite subject",
            text="Please claim your profile: {invitation_link}",
        )

    profile.refresh_from_db()
    assert len(djmail.outbox) == 1
    assert "Custom invite subject" in djmail.outbox[0].subject
    assert profile.invitation_token in djmail.outbox[0].body
    with scope(event=profile.event):
        template = profile.event.mail_templates.get(
            role=MailTemplateRoles.NEW_SPEAKER_INVITE
        )
        assert "Custom invite subject" not in str(template.subject)


@pytest.mark.parametrize(
    "profile_kwargs",
    ({"user": None, "email": None}, {}),
    ids=["without_email", "with_account"],
)
def test_send_speaker_invite_rejects_uninvitable_profiles(profile_kwargs):
    profile = SpeakerFactory(**profile_kwargs)

    with scope(event=profile.event), pytest.raises(SendMailException):
        send_speaker_invite(profile, **INVITE_KWARGS)

    profile.refresh_from_db()
    assert profile.invitation_token is None


@pytest.mark.parametrize(
    ("subject", "text"),
    (("", "Some text"), ("Some subject", "")),
    ids=["empty_subject", "empty_text"],
)
def test_send_speaker_invite_requires_subject_and_text(subject, text):
    profile = SpeakerFactory(user=None, email="managed@example.com")

    with (
        scope(event=profile.event),
        pytest.raises(ValueError, match="subject and text"),
    ):
        send_speaker_invite(profile, subject=subject, text=text)

    profile.refresh_from_db()
    assert profile.invitation_token is None


def test_send_speaker_invite_render_failure_does_not_rotate_token():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    djmail.outbox = []

    with scope(event=profile.event), pytest.raises(SendMailException):
        send_speaker_invite(
            profile, subject="Hello", text="About {proposal_title}: {invitation_link}"
        )

    profile.refresh_from_db()
    assert profile.invitation_token is None
    assert profile.invitation_sent is None
    assert len(djmail.outbox) == 0


def test_send_speaker_invite_malformed_text_raises_send_mail_exception():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    djmail.outbox = []

    with (
        scope(event=profile.event),
        pytest.raises(SendMailException, match="Invalid invitation text"),
    ):
        send_speaker_invite(profile, subject="Hello", text="Broken { {invitation_link}")

    profile.refresh_from_db()
    assert profile.invitation_token is None
    assert len(djmail.outbox) == 0


def test_retract_speaker_invite_clears_token_keeps_sent_time():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=profile.event, speaker=profile)
    with scope(event=profile.event):
        send_speaker_invite(profile, **INVITE_KWARGS)
        profile.refresh_from_db()
        sent = profile.invitation_sent

        retract_speaker_invite(profile)

    profile.refresh_from_db()
    assert profile.invitation_token is None
    assert profile.invitation_sent == sent


def test_retract_speaker_invite_without_token_is_noop():
    profile = SpeakerFactory(user=None, email="managed@example.com")

    retract_speaker_invite(profile)

    profile.refresh_from_db()
    assert profile.invitation_token is None
    assert profile.logged_actions().count() == 0


def test_claim_speaker_profile_links_user_and_keeps_identity():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=profile.event, speaker=profile)
    with scope(event=profile.event):
        send_speaker_invite(profile, **INVITE_KWARGS)
    profile.refresh_from_db()
    old_code = profile.code
    old_guid = profile.guid
    user = UserFactory()

    with scope(event=profile.event):
        claim_speaker_profile(profile, user)

    profile.refresh_from_db()
    assert profile.user == user
    assert profile.invitation_token is None
    assert profile.code == old_code
    assert profile.guid == old_guid


def test_claim_speaker_profile_adopts_picture_and_seeds_account():
    picture = ProfilePictureFactory(user=None)
    profile = SpeakerFactory(user=None, profile_picture=picture)
    user = UserFactory()
    assert user.profile_picture is None

    with scope(event=profile.event):
        claim_speaker_profile(profile, user)

    picture.refresh_from_db()
    user.refresh_from_db()
    assert picture.user == user
    assert user.profile_picture == picture


def test_claim_speaker_profile_adopts_already_owned_picture():
    # An already-owned picture (e.g. re-adopted after a partial earlier
    # claim) is not reassigned, but still seeds the empty account slot.
    owner = UserFactory()
    picture = ProfilePictureFactory(user=owner)
    profile = SpeakerFactory(user=None, profile_picture=picture)

    with scope(event=profile.event):
        claim_speaker_profile(profile, owner)

    picture.refresh_from_db()
    owner.refresh_from_db()
    assert picture.user == owner
    assert owner.profile_picture == picture


def test_claim_speaker_profile_keeps_existing_account_picture():
    account_picture = ProfilePictureFactory()
    user = account_picture.user
    user.profile_picture = account_picture
    user.save()
    adopted_picture = ProfilePictureFactory(user=None)
    profile = SpeakerFactory(user=None, profile_picture=adopted_picture)

    with scope(event=profile.event):
        claim_speaker_profile(profile, user)

    adopted_picture.refresh_from_db()
    user.refresh_from_db()
    assert adopted_picture.user == user
    assert user.profile_picture == account_picture


def test_create_speaker_profile_creates_managed_profile_and_logs():
    event = EventFactory()
    djmail.outbox = []

    with scope(event=event):
        profile = create_speaker_profile(
            event,
            email="newperson@example.com",
            name="New Person",
            locale="de",
            log_user=UserFactory(),
        )

        assert profile.event == event
        assert profile.user is None
        assert profile.email == "newperson@example.com"
        assert profile.locale == "de"
        assert profile.origin == SpeakerProfileOrigin.ORGA
        assert list(profile.submissions.all()) == []
        assert profile.invitation_token is None
        assert len(djmail.outbox) == 0
        assert (
            profile.logged_actions()
            .filter(action_type="pretalx.speaker.create")
            .count()
            == 1
        )


def test_create_speaker_profile_never_links_matching_account():
    event = EventFactory()
    account = UserFactory(email="account@example.com")

    with scope(event=event):
        profile = create_speaker_profile(event, email="account@example.com")

        assert profile.user is None
        assert profile.user != account
        assert profile.email == "account@example.com"


def test_create_speaker_profile_requires_email_or_name():
    event = EventFactory()

    with scope(event=event), pytest.raises(ValueError, match="an email or a name"):
        create_speaker_profile(event)


def _merge_pair(**managed_kwargs):
    managed = SpeakerFactory(user=None, email="managed@example.com", **managed_kwargs)
    survivor = SpeakerFactory(event=managed.event)
    return managed, survivor


def test_merge_applies_field_choices():
    managed, survivor = _merge_pair(name="Orga Name", biography="Orga bio")
    survivor.name = "Own Name"
    survivor.biography = "Own bio"
    survivor.save()

    with scope(event=managed.event):
        merge_speaker_profiles(
            managed,
            survivor,
            choices={"name": "merged", "biography": "survivor"},
            user=survivor.user,
        )

    survivor.refresh_from_db()
    assert survivor.name == "Orga Name"
    assert survivor.biography == "Own bio"
    assert not SpeakerProfile.objects.filter(pk=managed.pk).exists()


def test_merge_repoints_submissions_preserving_position():
    managed, survivor = _merge_pair()
    with scopes_disabled():
        role = SpeakerRoleFactory(
            submission__event=managed.event, speaker=managed, position=2
        )

    with scope(event=managed.event):
        merge_speaker_profiles(managed, survivor, choices={}, user=survivor.user)

        role.refresh_from_db()
        assert role.speaker == survivor
        assert role.position == 2
        assert list(role.submission.speakers.all()) == [survivor]


def test_merge_same_submission_keeps_survivor_role():
    managed, survivor = _merge_pair()
    with scopes_disabled():
        submission = SubmissionFactory(event=managed.event)
        SpeakerRoleFactory(submission=submission, speaker=survivor, position=0)
        SpeakerRoleFactory(submission=submission, speaker=managed, position=1)

    with scope(event=managed.event):
        merge_speaker_profiles(managed, survivor, choices={}, user=survivor.user)

        roles = list(SpeakerRole.objects.filter(submission=submission))
        assert len(roles) == 1
        assert roles[0].speaker == survivor
        assert roles[0].position == 0


def test_merge_repoints_protected_feedback():
    managed, survivor = _merge_pair()
    with scopes_disabled():
        role = SpeakerRoleFactory(submission__event=managed.event, speaker=managed)
        feedback = FeedbackFactory(talk=role.submission, speaker=managed)

    with scope(event=managed.event):
        merge_speaker_profiles(managed, survivor, choices={}, user=survivor.user)

    feedback.refresh_from_db()
    assert feedback.speaker == survivor
    assert not SpeakerProfile.objects.filter(pk=managed.pk).exists()


def test_merge_answers_chosen_and_unchosen():
    managed, survivor = _merge_pair()
    event = managed.event
    with scopes_disabled():
        question_keep_merged = QuestionFactory(event=event, target="speaker")
        question_keep_survivor = QuestionFactory(event=event, target="speaker")
        question_transfer = QuestionFactory(event=event, target="speaker")
        merged_answer_1 = AnswerFactory(
            question=question_keep_merged, speaker=managed, submission=None
        )
        survivor_answer_1 = AnswerFactory(
            question=question_keep_merged, speaker=survivor, submission=None
        )
        merged_answer_2 = AnswerFactory(
            question=question_keep_survivor, speaker=managed, submission=None
        )
        survivor_answer_2 = AnswerFactory(
            question=question_keep_survivor, speaker=survivor, submission=None
        )
        merged_answer_3 = AnswerFactory(
            question=question_transfer, speaker=managed, submission=None
        )

    with scope(event=event):
        merge_speaker_profiles(
            managed,
            survivor,
            choices={
                f"question_{question_keep_merged.pk}": "merged",
                f"question_{question_keep_survivor.pk}": "survivor",
            },
            user=survivor.user,
        )

    with scopes_disabled():
        assert set(Answer.objects.filter(speaker=survivor)) == {
            merged_answer_1,
            survivor_answer_2,
            merged_answer_3,
        }
        assert not Answer.objects.filter(pk=survivor_answer_1.pk).exists()
        assert not Answer.objects.filter(pk=merged_answer_2.pk).exists()


def test_merge_availability_chooser():
    managed, survivor = _merge_pair()
    event = managed.event
    with scopes_disabled():
        merged_availability = AvailabilityFactory(event=event, person=managed)
        AvailabilityFactory(event=event, person=survivor)

    with scope(event=event):
        merge_speaker_profiles(
            managed, survivor, choices={"availability": "merged"}, user=survivor.user
        )

        assert [availability.pk for availability in survivor.availabilities.all()] == [
            merged_availability.pk
        ]


def test_merge_repoints_mail_history():
    managed, survivor = _merge_pair()
    event = managed.event
    with scopes_disabled():
        mail = QueuedMailFactory(event=event)
        mail.to_speakers.add(managed)

    with scope(event=event):
        merge_speaker_profiles(managed, survivor, choices={}, user=survivor.user)

        assert list(mail.to_speakers.all()) == [survivor]


@pytest.mark.parametrize(
    ("survivor_notes", "expected_notes"),
    (("Survivor note", "Survivor note\n\nManaged note"), (None, "Managed note")),
    ids=["appended", "taken_over"],
)
def test_merge_internal_notes_append_and_arrival_or(survivor_notes, expected_notes):
    managed, survivor = _merge_pair(internal_notes="Managed note", has_arrived=True)
    survivor.internal_notes = survivor_notes
    survivor.save()
    assert not survivor.has_arrived

    with scope(event=managed.event):
        merge_speaker_profiles(managed, survivor, choices={}, user=survivor.user)

    survivor.refresh_from_db()
    assert survivor.internal_notes == expected_notes
    assert survivor.has_arrived


def test_merge_picture_choices():
    managed, survivor = _merge_pair()
    managed_picture = ProfilePictureFactory(user=None)
    managed.profile_picture = managed_picture
    managed.save()

    with scope(event=managed.event):
        merge_speaker_profiles(
            managed, survivor, choices={"picture": "merged"}, user=survivor.user
        )

    survivor.refresh_from_db()
    managed_picture.refresh_from_db()
    assert survivor.profile_picture == managed_picture
    assert managed_picture.user == survivor.user


def test_merge_discards_managed_picture_when_survivor_keeps_own():
    managed, survivor = _merge_pair()
    managed_picture = ProfilePictureFactory(user=None)
    managed.profile_picture = managed_picture
    managed.save()
    survivor_picture = ProfilePictureFactory(user=survivor.user)
    survivor.profile_picture = survivor_picture
    survivor.save()
    old_updated = managed_picture.updated

    with scope(event=managed.event):
        merge_speaker_profiles(
            managed, survivor, choices={"picture": "survivor"}, user=survivor.user
        )

    survivor.refresh_from_db()
    managed_picture.refresh_from_db()
    assert survivor.profile_picture == survivor_picture
    # The discarded picture is bumped for the regular file cleanup.
    assert managed_picture.updated > old_updated


def test_shred_speaker_profile_removes_profile_and_logs_event_audit():
    event = EventFactory()
    profile = SpeakerFactory(event=event, user=None, email="gone@example.com")
    AvailabilityFactory(event=event, person=profile)
    orga_user = UserFactory()

    with scope(event=event):
        shred_speaker_profile(profile, user=orga_user)

    with scopes_disabled():
        assert not SpeakerProfile.objects.filter(pk=profile.pk).exists()
        log = event.logged_actions().filter(action_type="pretalx.speaker.delete")
        assert log.count() == 1
        assert log.first().data["email"] == "gone@example.com"


def test_shred_speaker_profile_deletes_mails_even_with_other_recipients():
    event = EventFactory()
    profile = SpeakerFactory(event=event, user=None)
    other = SpeakerFactory(event=event)
    own_mail = QueuedMailFactory(event=event)
    own_mail.to_speakers.add(profile)
    shared_mail = QueuedMailFactory(event=event)
    shared_mail.to_speakers.add(profile, other)
    unrelated_mail = QueuedMailFactory(event=event)
    unrelated_mail.to_speakers.add(other)

    with scope(event=event):
        shred_speaker_profile(profile)

    with scopes_disabled():
        assert not event.queued_mails.filter(pk=own_mail.pk).exists()
        assert not event.queued_mails.filter(pk=shared_mail.pk).exists()
        assert event.queued_mails.filter(pk=unrelated_mail.pk).exists()


@pytest.mark.parametrize("history", ("feedback", "answer"))
def test_shred_speaker_profile_deletes_protected_relations(history):
    event = EventFactory()
    profile = SpeakerFactory(event=event, user=None)
    with scopes_disabled():
        if history == "feedback":
            related = FeedbackFactory(
                talk=SubmissionFactory(event=event), speaker=profile
            )
        else:
            related = AnswerFactory(
                question=QuestionFactory(event=event), submission=None, speaker=profile
            )

    with scope(event=event):
        shred_speaker_profile(profile)

    with scopes_disabled():
        assert not SpeakerProfile.objects.filter(pk=profile.pk).exists()
        assert not type(related).objects.filter(pk=related.pk).exists()


def test_profile_deletable_after_removal():
    admin = UserFactory(is_administrator=True)
    event = EventFactory()
    with scope(event=event):
        sole = SpeakerFactory(event=event, user=None)
        submission = SubmissionFactory(event=event)
        submission.speakers.add(sole)

        busy = SpeakerFactory(event=event, user=None)
        submission.speakers.add(busy)
        SubmissionFactory(event=event).speakers.add(busy)

        account_backed = SpeakerFactory(event=event)
        submission.speakers.add(account_backed)

        assert profile_deletable_after_removal(sole, submission, user=admin) is True
        assert profile_deletable_after_removal(busy, submission, user=admin) is False
        assert (
            profile_deletable_after_removal(account_backed, submission, user=admin)
            is False
        )


def test_shred_speaker_profile_deletes_logged_actions_and_invite_token():
    event = EventFactory()
    profile = SpeakerFactory(event=event, user=None, email="invited@example.com")

    with scope(event=event):
        send_speaker_invite(profile, **INVITE_KWARGS)
        profile.refresh_from_db()
        assert profile.invitation_token
        assert profile.logged_actions().exists()
        actions = profile.logged_actions()

        shred_speaker_profile(profile)

        assert not actions.exists()
    with scopes_disabled():
        assert not SpeakerProfile.objects.filter(
            invitation_token__isnull=False
        ).exists()


def test_shred_speaker_profile_bumps_picture_for_cleanup():
    event = EventFactory()
    picture = ProfilePictureFactory(user=None)
    profile = SpeakerFactory(event=event, user=None, profile_picture=picture)
    old_updated = picture.updated

    with scope(event=event):
        shred_speaker_profile(profile)

    picture.refresh_from_db()
    assert picture.updated > old_updated


def test_shred_speaker_profile_refuses_account_backed_profile():
    profile = SpeakerFactory()

    with scope(event=profile.event), pytest.raises(ValueError, match="managed"):
        shred_speaker_profile(profile)

    with scopes_disabled():
        assert SpeakerProfile.objects.filter(pk=profile.pk).exists()


def test_shred_speaker_profile_refuses_profile_with_submissions():
    profile = SpeakerFactory(user=None)
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=profile.event, speaker=profile)

    with scope(event=profile.event), pytest.raises(ValueError, match="submissions"):
        shred_speaker_profile(profile)

    with scopes_disabled():
        assert SpeakerProfile.objects.filter(pk=profile.pk).exists()


def test_merge_handles_every_core_relation_to_speaker_profile():
    handled = {
        "mail.QueuedMail.to_speakers",
        "schedule.Availability.person",
        "submission.Answer.speaker",
        "submission.Feedback.speaker",
        "submission.SpeakerRole.speaker",
        "submission.Submission.speakers",
    }
    incoming = {
        f"{relation.related_model._meta.label}.{relation.field.name}"
        for relation in SpeakerProfile._meta.get_fields()
        if relation.is_relation and relation.auto_created and not relation.concrete
    }
    assert incoming == handled, (
        "A relation to SpeakerProfile changed. Handle it explicitly in "
        "merge_speaker_profiles (and shred_speaker_profile), then "
        "update this list."
    )
