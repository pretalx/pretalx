# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations
from django.db.models import Exists, OuterRef, Subquery


def populate_speaker_profile(apps, schema_editor):
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


def reverse_speaker_profile(apps, schema_editor):
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
        ("submission", "0100_feedback_add_speaker_profile_fk"),
    ]

    operations = [
        migrations.RunPython(populate_speaker_profile, reverse_speaker_profile),
    ]
