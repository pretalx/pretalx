# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import uuid

from django.db import migrations, models

from pretalx.common.models.settings import GlobalSettings

BATCH_SIZE = 1000


def backfill_speaker_guids(apps, schema_editor):
    # Save the current guid to every speaker profile so that it remains
    # stable even when claimed.
    SpeakerProfile = apps.get_model("person", "SpeakerProfile")
    if not SpeakerProfile.objects.exists():
        return
    namespace = GlobalSettings().get_instance_identifier()
    batch = []
    for profile in (
        SpeakerProfile.objects.select_related("user")
        .only("guid", "code", "user__code")
        .iterator()
    ):
        code = profile.user.code if profile.user_id else None
        prefix = "user" if code else "speaker"
        code = code or profile.code
        profile.guid = str(uuid.uuid5(namespace, f"{prefix}:{code}"))
        batch.append(profile)
        if len(batch) >= BATCH_SIZE:
            SpeakerProfile.objects.bulk_update(batch, ["guid"])
            batch = []
    if batch:
        SpeakerProfile.objects.bulk_update(batch, ["guid"])


class Migration(migrations.Migration):
    dependencies = [("person", "0045_speakerprofile_identity_fields")]

    operations = [
        migrations.RunPython(backfill_speaker_guids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="speakerprofile",
            name="guid",
            field=models.CharField(max_length=36),
        ),
    ]
