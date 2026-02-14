# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("person", "0039_remove_user_avatar_fields"),
        ("submission", "0096_speakerrole_drop_user_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="answer",
            name="speaker",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="answers",
                to="person.speakerprofile",
            ),
        ),
    ]
