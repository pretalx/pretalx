# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2017-04-29 15:18
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('object_id', models.PositiveIntegerField(db_index=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('action_type', models.CharField(max_length=200)),
                ('data', models.TextField(blank=True, null=True)),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
            ],
            options={
                'ordering': ('-timestamp',),
            },
        ),
        migrations.CreateModel(
            name='GlobalSettings_SettingsStore',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField()),
            ],
        ),
    ]
