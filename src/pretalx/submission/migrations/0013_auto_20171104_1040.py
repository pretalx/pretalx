# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-11-04 15:40
from __future__ import unicode_literals

from django.db import migrations, models
import pretalx.submission.models.question


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0012_question_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='answer',
            name='answer_file',
            field=models.FileField(blank=True, null=True, upload_to=pretalx.submission.models.question.answer_file_path),
        ),
        migrations.AlterField(
            model_name='question',
            name='variant',
            field=models.CharField(choices=[('number', 'Number'), ('string', 'Text (one-line)'), ('text', 'Multi-line text'), ('boolean', 'Yes/No'), ('file', 'File upload'), ('choices', 'Choose one from a list'), ('multiple_choice', 'Choose multiple from a list')], default='string', max_length=15),
        ),
    ]
