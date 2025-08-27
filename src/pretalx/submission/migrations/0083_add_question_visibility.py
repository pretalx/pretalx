from django.db import migrations, models


def convert_fields_to_visibility(apps, schema_editor):
    """Convert is_public and active fields to visibility choices field."""
    Question = apps.get_model("submission", "Question")
    Question.objects.filter(active=False).update(visibility="hidden")
    Question.objects.filter(active=True, is_public=True).update(visibility="public")
    Question.objects.filter(active=True, is_public=False).update(
        visibility="speakers_organisers"
    )


def reverse_visibility_to_fields(apps, schema_editor):
    """Reverse migration: convert visibility back to is_public and active."""
    Question = apps.get_model("submission", "Question")
    Question.objects.filter(visibility="hidden").update(active=False, is_public=False)
    Question.objects.filter(visibility="public").update(active=True, is_public=True)
    Question.objects.exclude(visibility__in=["hidden", "public"]).update(
        active=True, is_public=False
    )


class Migration(migrations.Migration):

    dependencies = [
        ("submission", "0082_question_icon"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="visibility",
            field=models.CharField(
                choices=[
                    ("public", "Public"),
                    ("speakers_organisers", "Speakers and organisers"),
                    ("organisers_only", "Organisers only"),
                    ("hidden", "Hidden"),
                ],
                default="speakers_organisers",
                max_length=20,
                null=True,
                blank=True,
                help_text=(
                    "Who can see the responses to this question: "
                    "Public means responses are shown on session or speaker pages; "
                    "Speakers and organisers means only speakers and event organisers can see responses; "
                    "Organisers only means only event organisers can see responses; "
                    "Hidden means the question is completely hidden (soft deleted). "
                    "Please note that you cannot make a question more public after answers have been given, "
                    "to allow speakers explicit consent before publishing information."
                ),
                verbose_name="Visibility",
            ),
        ),
        migrations.RunPython(
            convert_fields_to_visibility, reverse_visibility_to_fields
        ),
        migrations.RemoveField(
            model_name="question",
            name="is_public",
        ),
        migrations.RemoveField(
            model_name="question",
            name="active",
        ),
        migrations.AlterField(
            model_name="question",
            name="visibility",
            field=models.CharField(
                choices=[
                    ("public", "Public"),
                    ("speakers_organisers", "Speakers and organisers"),
                    ("organisers_only", "Organisers only"),
                    ("hidden", "Hidden"),
                ],
                default="speakers_organisers",
                max_length=20,
                help_text=(
                    "Who can see the responses to this question: "
                    "Public means responses are shown on session or speaker pages; "
                    "Speakers and organisers means only speakers and event organisers can see responses; "
                    "Organisers only means only event organisers can see responses; "
                    "Hidden means the question is completely hidden (soft deleted). "
                    "Please note that you cannot make a question more public after answers have been given, "
                    "to allow speakers explicit consent before publishing information."
                ),
                verbose_name="Visibility",
            ),
        ),
    ]
