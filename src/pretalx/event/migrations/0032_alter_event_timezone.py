# Generated by Django 4.0 on 2023-06-03 21:21

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0031_initial_content_locale"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="timezone",
            field=models.CharField(default="UTC", max_length=32),
        ),
    ]
