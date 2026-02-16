# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations
from django.db.models import Exists, OuterRef, Subquery


def populate_speakerrole_speaker(apps, schema_editor):
    SpeakerRole = apps.get_model("submission", "SpeakerRole")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    User = apps.get_model("person", "User")
    Event = apps.get_model("event", "Event")

    # Step 1: Create missing SpeakerProfiles (safety net)
    roles_without_profile = (
        SpeakerRole.objects.annotate(
            has_profile=Exists(
                SpeakerProfile.objects.filter(
                    user_id=OuterRef("user_id"),
                    event_id=OuterRef("submission__event_id"),
                )
            )
        )
        .filter(has_profile=False)
        .values_list("user_id", "submission__event_id")
        .distinct()
    )

    missing_pairs = list(roles_without_profile)
    if missing_pairs:
        user_ids = {pair[0] for pair in missing_pairs}
        user_data = dict(User.objects.filter(pk__in=user_ids).values_list("pk", "code"))
        user_names = dict(
            User.objects.filter(pk__in=user_ids).values_list("pk", "name")
        )
        SpeakerProfile.objects.bulk_create(
            [
                SpeakerProfile(
                    user_id=user_id,
                    event_id=event_id,
                    code=user_data[user_id],
                    name=user_names.get(user_id) or "",
                )
                for user_id, event_id in missing_pairs
            ],
            ignore_conflicts=True,
        )

    # Step 2: Bulk populate speaker FK, per-event to avoid joined OuterRef
    for event in Event.objects.all():
        SpeakerRole.objects.filter(submission__event=event).update(
            speaker_id=Subquery(
                SpeakerProfile.objects.filter(
                    user_id=OuterRef("user_id"),
                    event_id=event.pk,
                ).values("id")[:1]
            )
        )


def reverse_speakerrole_speaker(apps, schema_editor):
    SpeakerRole = apps.get_model("submission", "SpeakerRole")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")

    SpeakerRole.objects.filter(speaker__isnull=False).update(
        user_id=Subquery(
            SpeakerProfile.objects.filter(
                pk=OuterRef("speaker_id"),
            ).values("user_id")[:1]
        )
    )


def populate_answer_speaker(apps, schema_editor):
    Answer = apps.get_model("submission", "Answer")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    User = apps.get_model("person", "User")
    Event = apps.get_model("event", "Event")

    # Step 1: Create missing SpeakerProfiles (safety net)
    answers_needing_profile = (
        Answer.objects.filter(person__isnull=False)
        .annotate(
            has_profile=Exists(
                SpeakerProfile.objects.filter(
                    user_id=OuterRef("person_id"),
                    event_id=OuterRef("question__event_id"),
                )
            )
        )
        .filter(has_profile=False)
        .values_list("person_id", "question__event_id")
        .distinct()
    )

    missing_pairs = list(answers_needing_profile)
    if missing_pairs:
        user_ids = {pair[0] for pair in missing_pairs}
        user_data = dict(User.objects.filter(pk__in=user_ids).values_list("pk", "code"))
        user_names = dict(
            User.objects.filter(pk__in=user_ids).values_list("pk", "name")
        )
        SpeakerProfile.objects.bulk_create(
            [
                SpeakerProfile(
                    user_id=user_id,
                    event_id=event_id,
                    code=user_data[user_id],
                    name=user_names.get(user_id) or "",
                )
                for user_id, event_id in missing_pairs
            ],
            ignore_conflicts=True,
        )

    # Step 2: Bulk populate speaker FK, per-event to avoid joined OuterRef
    for event in Event.objects.all():
        Answer.objects.filter(question__event=event, person__isnull=False).update(
            speaker_id=Subquery(
                SpeakerProfile.objects.filter(
                    user_id=OuterRef("person_id"),
                    event_id=event.pk,
                ).values("id")[:1]
            )
        )


def reverse_answer_speaker(apps, schema_editor):
    Answer = apps.get_model("submission", "Answer")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")

    Answer.objects.filter(speaker__isnull=False).update(
        person_id=Subquery(
            SpeakerProfile.objects.filter(
                pk=OuterRef("speaker_id"),
            ).values("user_id")[:1]
        )
    )


def populate_feedback_speaker(apps, schema_editor):
    Feedback = apps.get_model("submission", "Feedback")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    User = apps.get_model("person", "User")
    Event = apps.get_model("event", "Event")

    # Step 1: Create missing SpeakerProfiles (safety net)
    feedback_needing_profile = (
        Feedback.objects.filter(speaker__isnull=False)
        .annotate(
            has_profile=Exists(
                SpeakerProfile.objects.filter(
                    user_id=OuterRef("speaker_id"),
                    event_id=OuterRef("talk__event_id"),
                )
            )
        )
        .filter(has_profile=False)
        .values_list("speaker_id", "talk__event_id")
        .distinct()
    )

    missing_pairs = list(feedback_needing_profile)
    if missing_pairs:
        user_ids = {pair[0] for pair in missing_pairs}
        user_data = dict(User.objects.filter(pk__in=user_ids).values_list("pk", "code"))
        user_names = dict(
            User.objects.filter(pk__in=user_ids).values_list("pk", "name")
        )
        SpeakerProfile.objects.bulk_create(
            [
                SpeakerProfile(
                    user_id=user_id,
                    event_id=event_id,
                    code=user_data[user_id],
                    name=user_names.get(user_id) or "",
                )
                for user_id, event_id in missing_pairs
            ],
            ignore_conflicts=True,
        )

    # Step 2: Bulk populate speaker_profile FK, per-event
    for event in Event.objects.all():
        Feedback.objects.filter(talk__event=event, speaker__isnull=False).update(
            speaker_profile_id=Subquery(
                SpeakerProfile.objects.filter(
                    user_id=OuterRef("speaker_id"),
                    event_id=event.pk,
                ).values("id")[:1]
            )
        )


def reverse_feedback_speaker(apps, schema_editor):
    Feedback = apps.get_model("submission", "Feedback")
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")

    Feedback.objects.filter(speaker_profile__isnull=False).update(
        speaker_id=Subquery(
            SpeakerProfile.objects.filter(
                pk=OuterRef("speaker_profile_id"),
            ).values("user_id")[:1]
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0094_migrate_to_speakerprofile"),
    ]

    operations = [
        migrations.RunPython(populate_speakerrole_speaker, reverse_speakerrole_speaker),
        migrations.RunPython(populate_answer_speaker, reverse_answer_speaker),
        migrations.RunPython(populate_feedback_speaker, reverse_feedback_speaker),
    ]
