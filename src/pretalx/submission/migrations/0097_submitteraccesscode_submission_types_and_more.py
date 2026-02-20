# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0096_speakerprofile_finalize"),
    ]

    operations = [
        migrations.AddField(
            model_name="submitteraccesscode",
            name="submission_types",
            field=models.ManyToManyField(
                related_name="m2m_submitter_access_codes",
                to="submission.submissiontype",
            ),
        ),
        migrations.AddField(
            model_name="submitteraccesscode",
            name="tracks",
            field=models.ManyToManyField(
                related_name="m2m_submitter_access_codes", to="submission.track"
            ),
        ),
    ]
