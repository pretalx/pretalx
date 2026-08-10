# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import migrations


def backfill_legacy_verification_state(apps, schema_editor):
    User = apps.get_model("person", "User")
    User.objects.update(email_verification_state="legacy")


class Migration(migrations.Migration):
    dependencies = [("person", "0047_user_email_verification_fields")]

    operations = [
        migrations.RunPython(
            backfill_legacy_verification_state, migrations.RunPython.noop
        )
    ]
