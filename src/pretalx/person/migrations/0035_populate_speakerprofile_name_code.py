# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations
from django.db.models import Count, Max, OuterRef, Subquery


def deduplicate_speaker_profiles(apps, schema_editor):
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    # Find (user, event) pairs with duplicates
    dupes = (
        SpeakerProfile.objects.values("user", "event")
        .annotate(count=Count("id"), max_id=Max("id"))
        .filter(count__gt=1)
    )
    for dupe in dupes:
        # Keep the profile with the highest ID, delete the rest
        SpeakerProfile.objects.filter(
            user_id=dupe["user"], event_id=dupe["event"]
        ).exclude(id=dupe["max_id"]).delete()


def populate_speaker_profile_fields(apps, schema_editor):
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    User = apps.get_model("person", "User")
    user_qs = User.objects.filter(pk=OuterRef("user_id"))
    SpeakerProfile.objects.update(
        code=Subquery(user_qs.values("code")[:1]),
        name=Subquery(user_qs.values("name")[:1]),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("person", "0034_speakerprofile_code_speakerprofile_name_and_more"),
    ]

    operations = [
        migrations.RunPython(
            deduplicate_speaker_profiles,
            migrations.RunPython.noop,
            elidable=True,
        ),
        migrations.RunPython(
            populate_speaker_profile_fields,
            migrations.RunPython.noop,
            elidable=True,
        ),
    ]
