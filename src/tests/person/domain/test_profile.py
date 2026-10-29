# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
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
from pretalx.submission.models import Answer, Feedback, SpeakerRole
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
    "subject": "Custom invite subject",
    "text": "Please claim your profile: {invitation_link}",
}
MANAGED = {"user": None, "email": "managed@example.com"}


@pytest.mark.parametrize(
    ("user_name", "changed_fields", "expected_name"),
    (
        ("", ["name", "email"], "Profile Name"),
        ("Existing Name", ["name"], "Existing Name"),
        ("", ["email"], ""),
    ),
    ids=("fills_empty_user_name", "keeps_existing_user_name", "name_unchanged"),
)
def test_apply_speaker_profile_changes_syncs_name_but_never_account_email(
    user_name, changed_fields, expected_name
):
    user = UserFactory(name=user_name, email="old@example.com")
    profile = SpeakerFactory(
        user=user, name="Profile Name", email="contact@example.com"
    )

    apply_speaker_profile_changes(profile, changed_fields)
    user.refresh_from_db()

    assert user.name == expected_name
    assert user.email == "old@example.com"


def test_apply_speaker_profile_changes_managed_profile_is_noop():
    profile = SpeakerFactory(user=None, name="Managed Name")

    apply_speaker_profile_changes(profile, ["name", "email"])

    profile.refresh_from_db()
    assert profile.user is None
    assert profile.email is None
    assert profile.logged_actions().count() == 0


@pytest.mark.parametrize(
    ("new_email", "changed_fields", "expected_token", "expected_logs"),
    (
        (
            "changed@example.com",
            ["email"],
            None,
            [
                (
                    "pretalx.speaker.invite.invalidate",
                    {
                        "email": "invited@example.com",
                        "new_email": "changed@example.com",
                    },
                )
            ],
        ),
        (
            None,
            ["email"],
            None,
            [
                (
                    "pretalx.speaker.invite.invalidate",
                    {"email": "invited@example.com", "new_email": None},
                )
            ],
        ),
        ("invited@example.com", ["name"], "invite-token", []),
    ),
    ids=["new_address", "cleared", "other_change_keeps_invite"],
)
def test_apply_speaker_profile_changes_email_change_invalidates_invite(
    new_email, changed_fields, expected_token, expected_logs
):
    sent = now()
    profile = SpeakerFactory(
        user=None,
        email="invited@example.com",
        invitation_token="invite-token",
        invitation_sent=sent,
    )
    profile.email = new_email
    profile.save(update_fields=["email"])

    with scope(event=profile.event):
        apply_speaker_profile_changes(
            profile, changed_fields, old_email="invited@example.com"
        )

    profile.refresh_from_db()
    assert profile.invitation_token == expected_token
    assert profile.invitation_sent == (sent if expected_token else None)
    assert [
        (log.action_type, log.data) for log in profile.logged_actions()
    ] == expected_logs


def test_send_speaker_invite_mints_rotates_and_retracts_token():
    profile = SpeakerFactory(user=None, email="managed@example.com")
    event = profile.event
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=event, speaker=profile)
    djmail.outbox = []

    with scope(event=event):
        send_speaker_invite(profile, **INVITE_KWARGS)
        profile = SpeakerProfile.objects.select_related("event__cfp").get(pk=profile.pk)
        first_token = profile.invitation_token
        first_sent = profile.invitation_sent
        assert first_token
        assert first_sent is not None
        assert [m.to for m in djmail.outbox] == [["managed@example.com"]]
        assert "Custom invite subject" in djmail.outbox[0].subject
        assert first_token in djmail.outbox[0].body
        assert profile.mails.get().state == QueuedMailStates.SENT
        template = event.mail_templates.get(role=MailTemplateRoles.NEW_SPEAKER_INVITE)
        assert "Custom invite subject" not in str(template.subject)

        send_speaker_invite(profile, **INVITE_KWARGS)
        profile = SpeakerProfile.objects.select_related("event__cfp").get(pk=profile.pk)
        assert profile.invitation_token != first_token
        assert len(djmail.outbox) == 2
        assert profile.invitation_token in djmail.outbox[1].body
        sent = profile.invitation_sent

        retract_speaker_invite(profile)
        profile.refresh_from_db(fields=["invitation_token", "invitation_sent"])
        assert profile.invitation_token is None
        assert profile.invitation_sent == sent
        log_count = profile.logged_actions().count()

        retract_speaker_invite(profile)
        profile.refresh_from_db(fields=["invitation_token"])
        assert profile.invitation_token is None
        assert profile.logged_actions().count() == log_count


@pytest.mark.parametrize(
    ("profile_kwargs", "subject", "text", "exception", "match"),
    (
        (
            {"user": None, "email": None},
            "Hello",
            "{invitation_link}",
            SendMailException,
            "contact email",
        ),
        (
            {"email": "managed@example.com"},
            "Hello",
            "{invitation_link}",
            SendMailException,
            "account",
        ),
        (MANAGED, "", "{invitation_link}", ValueError, "subject and text"),
        (MANAGED, "Hello", "", ValueError, "subject and text"),
        (
            MANAGED,
            "Hello",
            "About {proposal_title}: {invitation_link}",
            SendMailException,
            None,
        ),
        (
            MANAGED,
            "Hello",
            "Broken { {invitation_link}",
            SendMailException,
            "Invalid invitation text",
        ),
    ),
    ids=(
        "without_email",
        "with_account",
        "empty_subject",
        "empty_text",
        "unknown_placeholder",
        "malformed_text",
    ),
)
def test_send_speaker_invite_rejects_without_touching_token(
    profile_kwargs, subject, text, exception, match
):
    profile = SpeakerFactory(**profile_kwargs)
    djmail.outbox = []

    with scope(event=profile.event), pytest.raises(exception, match=match):
        send_speaker_invite(profile, subject=subject, text=text)

    profile.refresh_from_db()
    assert profile.invitation_token is None
    assert profile.invitation_sent is None
    assert djmail.outbox == []


def test_claim_speaker_profile_links_user_adopts_picture_and_keeps_identity():
    picture = ProfilePictureFactory(user=None)
    profile = SpeakerFactory(
        user=None, email="managed@example.com", profile_picture=picture
    )
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=profile.event, speaker=profile)
    with scope(event=profile.event):
        send_speaker_invite(profile, **INVITE_KWARGS)
    profile = SpeakerProfile.objects.select_related("event", "profile_picture").get(
        pk=profile.pk
    )
    old_code = profile.code
    old_guid = profile.guid
    user = UserFactory()
    assert user.profile_picture is None

    with scope(event=profile.event):
        claim_speaker_profile(profile, user)

    profile.refresh_from_db()
    picture.refresh_from_db()
    user.refresh_from_db()
    assert profile.user_id == user.pk
    assert profile.invitation_token is None
    assert profile.code == old_code
    assert profile.guid == old_guid
    assert picture.user_id == user.pk
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
    assert picture.user_id == owner.pk
    assert owner.profile_picture == picture


def test_claim_speaker_profile_keeps_existing_account_picture():
    account_picture = ProfilePictureFactory()
    user = account_picture.user
    user.profile_picture = account_picture
    user.save()
    adopted_picture = ProfilePictureFactory(user=None)
    profile = SpeakerFactory(user=None, profile_picture=adopted_picture)
    pictureless = SpeakerFactory(user=None)

    with scope(event=profile.event):
        claim_speaker_profile(profile, user)
    with scope(event=pictureless.event):
        claim_speaker_profile(pictureless, user)

    adopted_picture.refresh_from_db()
    user.refresh_from_db()
    pictureless.refresh_from_db()
    assert adopted_picture.user_id == user.pk
    assert user.profile_picture == account_picture
    assert pictureless.user_id == user.pk
    assert pictureless.profile_picture_id is None


def test_create_speaker_profile_creates_managed_profile_without_linking_account():
    event = EventFactory()
    UserFactory(email="newperson@example.com")
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
        assert djmail.outbox == []
        assert [log.action_type for log in profile.logged_actions()] == [
            "pretalx.speaker.create"
        ]


def test_create_speaker_profile_requires_email_or_name():
    event = EventFactory()

    with scope(event=event), pytest.raises(ValueError, match="an email or a name"):
        create_speaker_profile(event)


def _merge_pair(**managed_kwargs):
    managed = SpeakerFactory(user=None, email="managed@example.com", **managed_kwargs)
    survivor = SpeakerFactory(event=managed.event)
    return managed, survivor


def test_merge_applies_field_choices_and_repoints_relations():
    managed, survivor = _merge_pair(name="Orga Name", biography="Orga bio")
    survivor.name = "Own Name"
    survivor.biography = "Own bio"
    survivor.save()
    event = managed.event
    with scopes_disabled():
        role = SpeakerRoleFactory(submission__event=event, speaker=managed, position=2)
        submission = role.submission
        feedback = FeedbackFactory(talk=submission, speaker=managed)
        merged_availability = AvailabilityFactory(event=event, person=managed)
        AvailabilityFactory(event=event, person=survivor)
        mail = QueuedMailFactory(event=event)
        mail.to_speakers.add(managed)

    with scope(event=event):
        merge_speaker_profiles(
            managed,
            survivor,
            choices={
                "name": "merged",
                "biography": "survivor",
                "availability": "merged",
            },
            user=survivor.user,
        )

        survivor.refresh_from_db()
        role.refresh_from_db()
        feedback.refresh_from_db()
        assert survivor.name == "Orga Name"
        assert survivor.biography == "Own bio"
        assert not SpeakerProfile.objects.filter(pk=managed.pk).exists()
        assert (role.speaker_id, role.position) == (survivor.pk, 2)
        assert list(submission.speakers.all()) == [survivor]
        assert feedback.speaker_id == survivor.pk
        assert list(survivor.availabilities.values_list("pk", flat=True)) == [
            merged_availability.pk
        ]
        assert list(mail.to_speakers.all()) == [survivor]


def test_merge_same_submission_keeps_survivor_role():
    managed, survivor = _merge_pair()
    with scopes_disabled():
        submission = SubmissionFactory(event=managed.event)
        SpeakerRoleFactory(submission=submission, speaker=survivor, position=0)
        SpeakerRoleFactory(submission=submission, speaker=managed, position=1)

    with scope(event=managed.event):
        merge_speaker_profiles(managed, survivor, choices={}, user=survivor.user)

        assert [
            (role.speaker_id, role.position)
            for role in SpeakerRole.objects.filter(submission=submission)
        ] == [(survivor.pk, 0)]


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
    assert survivor.profile_picture_id == managed_picture.pk
    assert managed_picture.user_id == survivor.user_id


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
    assert survivor.profile_picture_id == survivor_picture.pk
    # The discarded picture is bumped for the regular file cleanup.
    assert managed_picture.updated > old_updated


def test_shred_speaker_profile_removes_profile_history_and_logs_event_audit():
    event = EventFactory()
    picture = ProfilePictureFactory(user=None)
    profile = SpeakerFactory(
        event=event, user=None, email="gone@example.com", profile_picture=picture
    )
    other = SpeakerFactory(event=event)
    AvailabilityFactory(event=event, person=profile)
    own_mail = QueuedMailFactory(event=event)
    own_mail.to_speakers.add(profile)
    shared_mail = QueuedMailFactory(event=event)
    shared_mail.to_speakers.add(profile, other)
    unrelated_mail = QueuedMailFactory(event=event)
    unrelated_mail.to_speakers.add(other)
    with scopes_disabled():
        feedback = FeedbackFactory(talk=SubmissionFactory(event=event), speaker=profile)
        answer = AnswerFactory(
            question=QuestionFactory(event=event), submission=None, speaker=profile
        )
    orga_user = UserFactory()
    old_updated = picture.updated

    with scope(event=event):
        send_speaker_invite(profile, **INVITE_KWARGS)
        profile = SpeakerProfile.objects.select_related("event", "profile_picture").get(
            pk=profile.pk
        )
        assert profile.invitation_token
        actions = profile.logged_actions()
        assert actions.exists()

        shred_speaker_profile(profile, user=orga_user)

        assert not actions.exists()
    picture.refresh_from_db()
    with scopes_disabled():
        assert not SpeakerProfile.objects.filter(pk=profile.pk).exists()
        assert not SpeakerProfile.objects.filter(
            invitation_token__isnull=False
        ).exists()
        assert list(event.queued_mails.all()) == [unrelated_mail]
        assert not Feedback.objects.filter(pk=feedback.pk).exists()
        assert not Answer.objects.filter(pk=answer.pk).exists()
        assert picture.updated > old_updated
        log = event.logged_actions().filter(action_type="pretalx.speaker.delete").get()
        assert log.data["email"] == "gone@example.com"
        assert log.person == orga_user


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


def test_shred_speaker_profile_refuses_until_profile_is_managed_and_unused():
    account_backed = SpeakerFactory()
    speaking = SpeakerFactory(user=None, event=account_backed.event)
    with scopes_disabled():
        SpeakerRoleFactory(submission__event=speaking.event, speaker=speaking)

    with scope(event=account_backed.event):
        with pytest.raises(ValueError, match="managed"):
            shred_speaker_profile(account_backed)
        with pytest.raises(ValueError, match="submissions"):
            shred_speaker_profile(speaking)
        assert (
            SpeakerProfile.objects.filter(
                pk__in=[account_backed.pk, speaking.pk]
            ).count()
            == 2
        )

        speaking.submissions.clear()
        shred_speaker_profile(speaking)

        assert list(SpeakerProfile.objects.all()) == [account_backed]


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
