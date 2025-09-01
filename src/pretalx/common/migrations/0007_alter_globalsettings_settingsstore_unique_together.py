from django.db import migrations
from hierarkey.utils import CleanHierarkeyDuplicates


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0006_cachedfile"),
    ]

    operations = [
        CleanHierarkeyDuplicates("GlobalSettings_SettingsStore"),
        migrations.AlterUniqueTogether(
            name="globalsettings_settingsstore",
            unique_together={("key",)},
        ),
    ]
