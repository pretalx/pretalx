import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pretalx_fixed_sessions", "0001_initial"),
        ("submission", "0108_alter_resource_description"),
    ]

    operations = [
        migrations.CreateModel(
            name="FixedAnswer",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("answer", models.TextField(blank=True)),
                (
                    "fixed_session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="answers",
                        to="pretalx_fixed_sessions.fixedsession",
                    ),
                ),
                (
                    "options",
                    models.ManyToManyField(
                        blank=True, related_name="+", to="submission.answeroption"
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="submission.question",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("fixed_session", "question"),
                        name="fixed_sessions_unique_answer",
                    )
                ]
            },
        )
    ]
