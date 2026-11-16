import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('submission', '0108_alter_resource_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='Resubmission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('source', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='submission.submission')),
                ('submission', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='resubmitted_from', to='submission.submission')),
            ],
        ),
    ]
