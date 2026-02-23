from django.apps import AppConfig


class PluginApp(AppConfig):
    name = "tests.dummy_app_no_hooks"
    verbose_name = "Test Dummy Plugin (No Hooks)"

    class PretalxPluginMeta:
        name = "Test Dummy Plugin (No Hooks)"
        author = "Test"
        description = "Dummy plugin without installed/uninstalled hooks"
        visible = True
        version = "0.0.0"
        category = "OTHER"
