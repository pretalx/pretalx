# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest
from i18nfield.strings import LazyI18nString

from pretalx.cfp.flow import BaseCfPStep, CfPFlow
from pretalx.cfp.signals import cfp_steps
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_cfp_flow_defaults():
    event = EventFactory()

    flow = CfPFlow(event)
    steps = flow.steps

    assert [step.identifier for step in steps] == [
        "info",
        "questions",
        "user",
        "profile",
    ]
    assert [step.priority for step in steps] == sorted(step.priority for step in steps)
    assert steps[0]._previous is None
    assert steps[0]._next is steps[1]
    assert steps[1]._previous is steps[0]
    assert steps[1]._next is steps[2]
    assert not hasattr(steps[-1], "_next")
    assert flow.config == {"steps": {}}
    assert json.loads(flow.get_config_json()) == {"steps": {}}
    assert flow.get_step_config("nonexistent") == {}
    assert flow.get_field_config("info", "nonexistent") == {}
    assert flow.get_field_config("nonexistent", "title") == {}


def test_cfp_flow_get_config_normalises_input():
    flow = CfPFlow(EventFactory())
    data = {
        "steps": {
            "info": {
                "icon": "star",
                "title": "Hello",
                "text": "World",
                "fields": [
                    {
                        "key": "title",
                        "label": "Custom Title",
                        "help_text": "Enter title",
                        "required": True,
                        "request": True,
                        "widget": "fancy",
                    }
                ],
            }
        }
    }

    result = flow.get_config(data)

    assert result == {
        "steps": {
            "info": {
                "icon": "star",
                "title": LazyI18nString({"en": "Hello"}),
                "text": LazyI18nString({"en": "World"}),
                "fields": [
                    {
                        "key": "title",
                        "label": LazyI18nString({"en": "Custom Title"}),
                        "help_text": LazyI18nString({"en": "Enter title"}),
                        "required": True,
                        "request": True,
                    }
                ],
            }
        }
    }
    assert flow.get_config(json.dumps(data)) == result
    assert flow.get_config(data, json_compat=True)["steps"]["info"]["title"] == {
        "en": "Hello"
    }
    assert [flow.get_config(value) for value in (42, None, "", [])] == [{}] * 4


def test_cfp_flow_save_config_normalises_and_persists():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.save_config([{"title": "test"}])
    event.cfp.refresh_from_db()
    assert event.cfp.settings["flow"] == {"steps": {}}

    flow.save_config({"info": {"icon": "star"}})
    event.cfp.refresh_from_db()
    assert event.cfp.settings["flow"] == {
        "steps": {"info": {"icon": "star", "fields": []}}
    }

    flow.save_config(
        {
            "steps": {
                "info": {
                    "title": "Hello",
                    "fields": [{"key": "title", "label": "Custom Title"}],
                }
            }
        }
    )
    flow = CfPFlow(event)
    assert flow.get_step_config("info")["title"] == LazyI18nString({"en": "Hello"})
    assert flow.get_field_config("info", "title") == {
        "key": "title",
        "label": LazyI18nString({"en": "Custom Title"}),
    }
    assert json.loads(flow.get_config_json()) == {
        "steps": {
            "info": {
                "title": {"en": "Hello"},
                "fields": [{"key": "title", "label": {"en": "Custom Title"}}],
            }
        }
    }

    flow.reset()
    event.cfp.refresh_from_db()
    assert event.cfp.settings["flow"] == {}


def test_cfp_flow_update_step_header_creates_step_if_missing():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.update_step_header("info", title="New Title", text="New Text")
    flow.update_step_header("new_step", title="Title", text="Text")

    flow = CfPFlow(event)
    assert flow.get_step_config("info")["title"] == LazyI18nString({"en": "New Title"})
    assert flow.get_step_config("info")["text"] == LazyI18nString({"en": "New Text"})
    assert flow.get_step_config("new_step")["title"] == LazyI18nString({"en": "Title"})


def test_cfp_flow_update_field_config_merges_into_existing_field():
    event = EventFactory()

    CfPFlow(event).update_field_config("info", "title", help_text="Some help")
    assert CfPFlow(event).get_field_config("info", "title") == {
        "key": "title",
        "help_text": LazyI18nString({"en": "Some help"}),
    }

    CfPFlow(event).update_field_config("info", "title", label="Original")
    CfPFlow(event).update_field_config("info", "title", label="Updated")
    assert CfPFlow(event).get_field_config("info", "title") == {
        "key": "title",
        "help_text": LazyI18nString({"en": "Some help"}),
        "label": LazyI18nString({"en": "Updated"}),
    }

    CfPFlow(event).update_field_config("info", "title", help_text="Updated help")
    assert CfPFlow(event).get_field_config("info", "title") == {
        "key": "title",
        "help_text": LazyI18nString({"en": "Updated help"}),
        "label": LazyI18nString({"en": "Updated"}),
    }

    CfPFlow(event).update_field_config("new_step", "new_field", label="Label")
    assert CfPFlow(event).get_field_config("new_step", "new_field") == {
        "key": "new_field",
        "label": LazyI18nString({"en": "Label"}),
    }


def test_cfp_flow_update_field_order_keeps_metadata_and_stubs_new_fields():
    event = EventFactory()
    CfPFlow(event).save_config(
        {
            "steps": {
                "info": {
                    "fields": [
                        {"key": "title", "label": "Title"},
                        {"key": "abstract", "label": "Abstract"},
                        {"key": "description"},
                    ]
                }
            }
        }
    )

    CfPFlow(event).update_field_order(
        "info", ["description", "title", "abstract", "new_field"]
    )
    CfPFlow(event).update_field_order("new_step", ["field_a", "field_b"])

    flow = CfPFlow(event)
    assert flow.get_step_config("info")["fields"] == [
        {"key": "description"},
        {"key": "title", "label": LazyI18nString({"en": "Title"})},
        {"key": "abstract", "label": LazyI18nString({"en": "Abstract"})},
        {"key": "new_field"},
    ]
    assert flow.get_step_config("new_step")["fields"] == [
        {"key": "field_a"},
        {"key": "field_b"},
    ]
    assert flow.get_field_config("info", "abstract") == {
        "key": "abstract",
        "label": LazyI18nString({"en": "Abstract"}),
    }
    assert flow.get_field_config("info", "nonexistent") == {}


@pytest.mark.parametrize(
    ("config", "expected"),
    (
        ({}, {"steps": {"info": {"fields": []}}}),
        (
            {"steps": {"info": {"fields": [{"key": "title"}], "icon": "star"}}},
            {"steps": {"info": {"fields": [{"key": "title"}], "icon": "star"}}},
        ),
        (
            {"steps": {"info": {"icon": "star"}}},
            {"steps": {"info": {"icon": "star", "fields": []}}},
        ),
    ),
    ids=["creates_structure", "preserves_existing", "adds_missing_fields_key"],
)
def test_cfp_flow_ensure_step_config(config, expected):
    CfPFlow(EventFactory())._ensure_step_config(config, "info")

    assert config == expected


def test_cfp_flow_handles_exception_from_signal(register_signal_handler):
    event = EventFactory()

    def bad_handler(signal, sender, **kwargs):
        raise RuntimeError("Plugin broke")

    register_signal_handler(cfp_steps, bad_handler)

    flow = CfPFlow(event)

    assert len(flow.steps) == 4


class PluginStep(BaseCfPStep):
    identifier = "plugin_step"
    label = "Plugin"

    def is_completed(self, request):
        return True


def test_cfp_flow_integrates_plugin_steps(register_signal_handler):
    event = EventFactory()

    class PrioritisedStep(PluginStep):
        priority = 50

    def handler(signal, sender, **kwargs):
        return [PrioritisedStep]

    register_signal_handler(cfp_steps, handler)

    flow = CfPFlow(event)

    assert [s.identifier for s in flow.steps] == [
        "info",
        "questions",
        "user",
        "plugin_step",
        "profile",
    ]
    assert flow.steps_dict["plugin_step"].is_completed(request=None) is True


def test_cfp_flow_plugin_step_without_priority_sorts_last(register_signal_handler):
    event = EventFactory()

    class UnprioritisedStep(PluginStep):
        identifier = "unprioritised_step"

    def handler(signal, sender, **kwargs):
        return [UnprioritisedStep]

    register_signal_handler(cfp_steps, handler)

    flow = CfPFlow(event)

    assert [s.identifier for s in flow.steps] == [
        "info",
        "questions",
        "user",
        "profile",
        "unprioritised_step",
    ]
    assert flow.steps[-1]._previous.identifier == "profile"
