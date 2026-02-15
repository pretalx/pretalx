# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0098_populate_answer_speaker"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="answer",
            name="person",
        ),
    ]
