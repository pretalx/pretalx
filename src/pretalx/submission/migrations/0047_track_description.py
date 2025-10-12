# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import i18nfield.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("submission", "0046_question_submission_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="track",
            name="description",
            field=i18nfield.fields.I18nTextField(blank=True),
        ),
    ]
