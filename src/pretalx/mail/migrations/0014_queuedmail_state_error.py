from django.db import migrations, models


def populate_state(apps, schema_editor):
    QueuedMail = apps.get_model("mail", "QueuedMail")
    QueuedMail.objects.filter(sent__isnull=True).update(state="draft")
    QueuedMail.objects.filter(sent__isnull=False).update(state="sent")


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0013_mailtemplate_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="queuedmail",
            name="state",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("sending", "Sending"),
                    ("sent", "Sent"),
                ],
                db_index=True,
                default="draft",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="queuedmail",
            name="error_data",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="queuedmail",
            name="error_timestamp",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(populate_state, migrations.RunPython.noop),
    ]
