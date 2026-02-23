from django.apps import AppConfig

installed_events = []
uninstalled_events = []


class PluginApp(AppConfig):
    name = "tests.dummy_app"
    verbose_name = "Test Dummy Plugin"

    class PretalxPluginMeta:
        name = "Test Dummy Plugin"
        author = "Test"
        description = "Dummy plugin for tests"
        visible = True
        version = "0.0.0"
        category = "OTHER"

    def installed(self, event):
        installed_events.append(event.slug)

    def uninstalled(self, event):
        uninstalled_events.append(event.slug)
