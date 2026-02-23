# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations


def copy_fk_to_m2m(apps, schema_editor):
    SubmitterAccessCode = apps.get_model("submission", "SubmitterAccessCode")
    track_through = SubmitterAccessCode.tracks.through
    type_through = SubmitterAccessCode.submission_types.through
    track_through.objects.bulk_create(
        track_through(submitteraccesscode_id=ac["pk"], track_id=ac["track_id"])
        for ac in SubmitterAccessCode.objects.filter(track__isnull=False)
        .values("pk", "track_id")
        .iterator()
    )
    type_through.objects.bulk_create(
        type_through(
            submitteraccesscode_id=ac["pk"], submissiontype_id=ac["submission_type_id"]
        )
        for ac in SubmitterAccessCode.objects.filter(submission_type__isnull=False)
        .values("pk", "submission_type_id")
        .iterator()
    )


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0097_submitteraccesscode_submission_types_and_more")
    ]

    operations = [migrations.RunPython(copy_fk_to_m2m, migrations.RunPython.noop)]
