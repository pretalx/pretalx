# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import configparser
import importlib
import os
from contextlib import suppress
from pathlib import Path

import pytest
import urllib3
from django.conf import settings
from django.dispatch import Signal

here = Path(__file__).parent
doc_dir = here / "../../../doc"
base_dir = here / "../../pretalx"
fixtures_dir = here / "../fixtures"

plugin_docs = (doc_dir / "developer/plugins/general.rst").read_text()
command_docs = (doc_dir / "administrator/commands.rst").read_text()


def test_documentation_includes_config_options():
    doc_text = (doc_dir / "administrator/configure.rst").read_text()
    config = configparser.RawConfigParser()
    config.read(here / "../../pretalx.example.cfg")

    for category in config:
        for key in category:
            assert key in doc_text, f"{category}:{key} is missing in config docs"


@pytest.mark.parametrize("app", settings.LOCAL_APPS)
def test_documentation_includes_signals(app):
    with suppress(ImportError):
        module = importlib.import_module(app + ".signals")
        for key in dir(module):
            attrib = getattr(module, key)
            if isinstance(attrib, Signal):
                assert key in plugin_docs


@pytest.mark.parametrize("app", settings.LOCAL_APPS)
def test_documentation_includes_management_commands(app):
    # devserver is not relevant for administrators, and spectacular is a
    # third-party command for API doc generation that we only have as a
    # local command in order to wrap it in scopes_disabled()
    excluded_commands = (
        "__init__.py",
        "devserver.py",
        "spectacular.py",
        "update_translation_percentages.py",
    )
    with suppress(ImportError):
        importlib.import_module(app + ".management.commands")
        path = base_dir / app.partition(".")[-1] / "management/commands"
        for python_file in path.glob("*.py"):
            file_name = python_file.name
            if file_name not in excluded_commands:
                assert f"``{file_name[:-3]}``" in command_docs


@pytest.mark.skipif(
    "CI" not in os.environ or not os.environ["CI"],
    reason="No need to bother with this outside of CI.",
)
def test_schedule_xsd_is_up_to_date():
    """If this test fails:

    http -d https://raw.githubusercontent.com/voc/schedule/master/validator/xsd/schedule.xml.xsd >! src/tests/fixtures/schedule.xsd
    """
    http = urllib3.PoolManager()
    response = http.request(
        "GET",
        "https://raw.githubusercontent.com/voc/schedule/master/validator/xsd/schedule.xml.xsd",
    )
    if response.status == 429:
        # don't fail tests on rate limits
        return
    assert response.status == 200
    schema_content = (fixtures_dir / "schedule.xsd").read_text()
    assert response.data.decode() == schema_content


@pytest.mark.skipif(
    "CI" not in os.environ or not os.environ["CI"],
    reason="No need to bother with this outside of CI.",
)
def test_schedule_json_schema_is_up_to_date():
    """If this test fails:

    http -d https://raw.githubusercontent.com/voc/schedule/master/validator/json/schema.json >! src/tests/fixtures/schedule.json
    """
    http = urllib3.PoolManager()
    response = http.request(
        "GET",
        "https://raw.githubusercontent.com/voc/schedule/master/validator/json/schema.json",
    )
    if response.status == 429:
        # don't fail tests on rate limits
        return
    assert response.status == 200
    schema_content = (fixtures_dir / "schedule.json").read_text()
    assert response.data.decode() == schema_content
