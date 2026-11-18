import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("submission", "0108_alter_resource_description"),
    ]

    operations = [
        migrations.CreateModel(
            name="FixedSession",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200, verbose_name="Session title")),
                ("abstract", models.TextField(blank=True, verbose_name="Abstract")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("do_not_record", models.BooleanField(blank=True, help_text="Leave empty to let the speaker choose.", null=True, verbose_name="Don't record")),
                ("updated", models.DateTimeField(auto_now=True)),
                ("submission_type", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="fixed_session", to="submission.submissiontype")),
                ("track", models.ForeignKey(blank=True, help_text="Leave empty to let the speaker choose.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="submission.track", verbose_name="Track")),
            ],
        ),
    ]
