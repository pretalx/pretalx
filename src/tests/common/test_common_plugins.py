import pytest
from tests.dummy_app import PluginApp

from pretalx.common.plugins import get_all_plugins


@pytest.mark.django_db
def test_get_all_plugins():
    assert PluginApp.PretalxPluginMeta in get_all_plugins(), get_all_plugins()
