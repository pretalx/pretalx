# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json

import pytest
from i18nfield.strings import LazyI18nString

from pretalx.cfp.flow import BaseCfPStep, CfPFlow
from pretalx.cfp.signals import cfp_steps
from tests.factories import EventFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_cfp_flow_has_default_steps():
    event = EventFactory()

    flow = CfPFlow(event)

    assert [s.identifier for s in flow.steps] == [
        "info",
        "questions",
        "user",
        "profile",
    ]


@pytest.mark.django_db
def test_cfp_flow_steps_sorted_by_priority():
    event = EventFactory()

    flow = CfPFlow(event)

    priorities = [s.priority for s in flow.steps]
    assert priorities == sorted(priorities)


@pytest.mark.django_db
def test_cfp_flow_steps_linked_list():
    event = EventFactory()
    flow = CfPFlow(event)
    steps = flow.steps

    assert steps[0]._previous is None
    assert steps[0]._next is steps[1]
    assert steps[1]._previous is steps[0]
    assert steps[1]._next is steps[2]
    assert not hasattr(steps[-1], "_next")


@pytest.mark.django_db
def test_cfp_flow_steps_dict_is_ordered():
    event = EventFactory()

    flow = CfPFlow(event)

    assert list(flow.steps_dict.keys()) == ["info", "questions", "user", "profile"]


@pytest.mark.django_db
def test_cfp_flow_default_config_is_empty():
    event = EventFactory()

    assert CfPFlow(event).config == {"steps": {}}


@pytest.mark.django_db
def test_cfp_flow_steps_property_returns_list():
    event = EventFactory()

    flow = CfPFlow(event)

    assert isinstance(flow.steps, list)
    assert len(flow.steps) == 4


@pytest.mark.django_db
def test_cfp_flow_get_config_parses_json_string():
    event = EventFactory()
    flow = CfPFlow(event)

    result = flow.get_config(json.dumps({"steps": {"info": {"icon": "star"}}}))

    assert result["steps"]["info"]["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_get_config_handles_dict():
    event = EventFactory()
    flow = CfPFlow(event)

    result = flow.get_config({"steps": {"info": {"icon": "star"}}})

    assert result["steps"]["info"]["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_get_config_returns_empty_for_non_dict():
    event = EventFactory()
    flow = CfPFlow(event)

    assert flow.get_config(42) == {}
    assert flow.get_config(None) == {}
    assert flow.get_config("") == {}
    assert flow.get_config([]) == {}


@pytest.mark.django_db
def test_cfp_flow_get_config_processes_i18n_fields():
    event = EventFactory()
    flow = CfPFlow(event)

    result = flow.get_config({"steps": {"info": {"title": "Hello", "text": "World"}}})

    assert isinstance(result["steps"]["info"]["title"], LazyI18nString)
    assert result["steps"]["info"]["title"].data["en"] == "Hello"
    assert isinstance(result["steps"]["info"]["text"], LazyI18nString)
    assert result["steps"]["info"]["text"].data["en"] == "World"


@pytest.mark.django_db
def test_cfp_flow_get_config_processes_field_configs():
    event = EventFactory()
    flow = CfPFlow(event)
    data = {
        "steps": {
            "info": {
                "fields": [
                    {
                        "key": "title",
                        "label": "Custom Title",
                        "help_text": "Enter title",
                    }
                ]
            }
        }
    }

    result = flow.get_config(data)

    field = result["steps"]["info"]["fields"][0]
    assert field["key"] == "title"
    assert field["label"].data["en"] == "Custom Title"
    assert field["help_text"].data["en"] == "Enter title"


@pytest.mark.django_db
def test_cfp_flow_get_config_preserves_non_i18n_field_keys():
    event = EventFactory()
    flow = CfPFlow(event)
    data = {
        "steps": {
            "info": {"fields": [{"key": "title", "required": True, "request": True}]}
        }
    }

    result = flow.get_config(data)

    field = result["steps"]["info"]["fields"][0]
    assert field["required"] is True
    assert field["request"] is True


@pytest.mark.django_db
def test_cfp_flow_get_config_ignores_unknown_field_keys():
    event = EventFactory()
    flow = CfPFlow(event)
    data = {"steps": {"info": {"fields": [{"key": "title", "widget": "fancy"}]}}}

    result = flow.get_config(data)

    assert "widget" not in result["steps"]["info"]["fields"][0]


@pytest.mark.django_db
def test_cfp_flow_get_config_json_compat_mode():
    event = EventFactory()
    flow = CfPFlow(event)

    result = flow.get_config({"steps": {"info": {"title": "Hello"}}}, json_compat=True)

    assert isinstance(result["steps"]["info"]["title"], dict)


@pytest.mark.django_db
def test_cfp_flow_save_config_stores_in_settings():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.save_config({"steps": {"info": {"icon": "star"}}})
    event.cfp.refresh_from_db()

    assert event.cfp.settings["flow"]["steps"]["info"]["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_save_config_normalises_list_input():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.save_config([{"title": "test"}])
    event.cfp.refresh_from_db()

    assert "steps" in event.cfp.settings["flow"]


@pytest.mark.django_db
def test_cfp_flow_save_config_normalises_bare_dict():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.save_config({"info": {"icon": "star"}})
    event.cfp.refresh_from_db()

    assert "steps" in event.cfp.settings["flow"]


@pytest.mark.django_db
def test_cfp_flow_reset_clears_config():
    event = EventFactory()
    flow = CfPFlow(event)
    flow.save_config({"steps": {"info": {"icon": "star"}}})

    flow.reset()

    event.cfp.refresh_from_db()
    assert event.cfp.settings["flow"] == {}


@pytest.mark.django_db
def test_cfp_flow_get_config_json_returns_valid_json():
    event = EventFactory()
    flow = CfPFlow(event)
    flow.save_config({"steps": {"info": {"title": "Hello"}}})
    flow = CfPFlow(event)

    result = flow.get_config_json()

    assert "steps" in json.loads(result)


@pytest.mark.django_db
def test_cfp_flow_get_config_json_empty_config():
    event = EventFactory()

    assert json.loads(CfPFlow(event).get_config_json()) == {"steps": {}}


@pytest.mark.django_db
def test_cfp_flow_get_step_config_returns_config():
    event = EventFactory()
    flow = CfPFlow(event)
    flow.save_config({"steps": {"info": {"icon": "star"}}})
    flow = CfPFlow(event)

    assert flow.get_step_config("info")["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_get_step_config_returns_empty_for_missing():
    event = EventFactory()

    assert CfPFlow(event).get_step_config("nonexistent") == {}


@pytest.mark.django_db
def test_cfp_flow_get_field_config_returns_field():
    event = EventFactory()
    flow = CfPFlow(event)
    flow.save_config(
        {
            "steps": {
                "info": {
                    "fields": [
                        {"key": "title", "label": "Custom Title"},
                        {"key": "abstract"},
                    ]
                }
            }
        }
    )
    flow = CfPFlow(event)

    result = flow.get_field_config("info", "title")

    assert result["key"] == "title"
    assert result["label"].data["en"] == "Custom Title"


@pytest.mark.django_db
def test_cfp_flow_get_field_config_returns_empty_for_missing_field():
    event = EventFactory()

    assert CfPFlow(event).get_field_config("info", "nonexistent") == {}


@pytest.mark.django_db
def test_cfp_flow_get_field_config_returns_empty_for_missing_step():
    event = EventFactory()

    assert CfPFlow(event).get_field_config("nonexistent", "title") == {}


@pytest.mark.django_db
def test_cfp_flow_update_step_header():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.update_step_header("info", title="New Title", text="New Text")

    flow = CfPFlow(event)
    step_config = flow.get_step_config("info")
    assert step_config["title"].data["en"] == "New Title"
    assert step_config["text"].data["en"] == "New Text"


@pytest.mark.django_db
def test_cfp_flow_update_step_header_creates_step_if_missing():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.update_step_header("new_step", title="Title", text="Text")

    assert CfPFlow(event).get_step_config("new_step") != {}


@pytest.mark.django_db
def test_cfp_flow_update_field_config_creates_new_field():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.update_field_config("info", "title", label="Custom Title")

    flow = CfPFlow(event)
    field = flow.get_field_config("info", "title")
    assert field["key"] == "title"
    assert field["label"].data["en"] == "Custom Title"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_updates_existing_field():
    event = EventFactory()
    flow = CfPFlow(event)
    flow.update_field_config("info", "title", label="Original", help_text="Help")
    flow = CfPFlow(event)

    flow.update_field_config("info", "title", label="Updated")

    flow = CfPFlow(event)
    field = flow.get_field_config("info", "title")
    assert field["label"].data["en"] == "Updated"
    # help_text is preserved from original save
    assert field["help_text"].data["en"] == "Help"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_creates_step_if_missing():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.update_field_config("new_step", "new_field", label="Label")

    field = CfPFlow(event).get_field_config("new_step", "new_field")
    assert field["key"] == "new_field"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_with_help_text_only():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.update_field_config("info", "title", help_text="Some help")

    field = CfPFlow(event).get_field_config("info", "title")
    assert field["help_text"].data["en"] == "Some help"
    assert "label" not in field


@pytest.mark.django_db
def test_cfp_flow_update_field_config_updates_help_text_on_existing():
    """Updating only help_text on an existing field preserves the label."""
    event = EventFactory()
    flow = CfPFlow(event)
    flow.update_field_config("info", "title", label="Custom")
    flow = CfPFlow(event)

    flow.update_field_config("info", "title", help_text="Updated help")

    field = CfPFlow(event).get_field_config("info", "title")
    assert field["help_text"].data["en"] == "Updated help"
    assert field["label"].data["en"] == "Custom"


@pytest.mark.django_db
def test_cfp_flow_update_field_order_reorders_fields():
    event = EventFactory()
    flow = CfPFlow(event)
    flow.save_config(
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
    flow = CfPFlow(event)

    flow.update_field_order("info", ["description", "title", "abstract"])

    fields = CfPFlow(event).get_step_config("info")["fields"]
    assert [f["key"] for f in fields] == ["description", "title", "abstract"]


@pytest.mark.django_db
def test_cfp_flow_update_field_order_preserves_metadata():
    event = EventFactory()
    flow = CfPFlow(event)
    flow.save_config(
        {"steps": {"info": {"fields": [{"key": "title", "label": "Custom Title"}]}}}
    )
    flow = CfPFlow(event)

    flow.update_field_order("info", ["title"])

    field = CfPFlow(event).get_field_config("info", "title")
    assert field["label"].data["en"] == "Custom Title"


@pytest.mark.django_db
def test_cfp_flow_update_field_order_creates_new_field_stubs():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.update_field_order("info", ["title", "new_field"])

    assert CfPFlow(event).get_field_config("info", "new_field") == {"key": "new_field"}


@pytest.mark.django_db
def test_cfp_flow_update_field_order_creates_step_if_missing():
    event = EventFactory()
    flow = CfPFlow(event)

    flow.update_field_order("new_step", ["field_a", "field_b"])

    fields = CfPFlow(event).get_step_config("new_step")["fields"]
    assert [f["key"] for f in fields] == ["field_a", "field_b"]


@pytest.mark.django_db
def test_cfp_flow_ensure_step_config_creates_structure():
    event = EventFactory()
    flow = CfPFlow(event)
    config = {}

    flow._ensure_step_config(config, "info")

    assert config == {"steps": {"info": {"fields": []}}}


@pytest.mark.django_db
def test_cfp_flow_ensure_step_config_preserves_existing():
    event = EventFactory()
    flow = CfPFlow(event)
    config = {"steps": {"info": {"fields": [{"key": "title"}], "icon": "star"}}}

    flow._ensure_step_config(config, "info")

    assert config["steps"]["info"]["icon"] == "star"
    assert len(config["steps"]["info"]["fields"]) == 1


@pytest.mark.django_db
def test_cfp_flow_ensure_step_config_adds_missing_fields_key():
    event = EventFactory()
    flow = CfPFlow(event)
    config = {"steps": {"info": {"icon": "star"}}}

    flow._ensure_step_config(config, "info")

    assert config["steps"]["info"]["fields"] == []
    assert config["steps"]["info"]["icon"] == "star"


@pytest.mark.django_db
def test_cfp_flow_handles_exception_from_signal(register_signal_handler):
    event = EventFactory()

    def bad_handler(signal, sender, **kwargs):
        raise RuntimeError("Plugin broke")

    register_signal_handler(cfp_steps, bad_handler)

    flow = CfPFlow(event)

    assert len(flow.steps) == 4


@pytest.mark.django_db
def test_cfp_flow_integrates_plugin_steps(register_signal_handler):
    event = EventFactory()

    class PluginStep(BaseCfPStep):
        identifier = "plugin_step"
        label = "Plugin"
        priority = 50

        def is_completed(self, request):
            return True

    def handler(signal, sender, **kwargs):
        return [PluginStep]

    register_signal_handler(cfp_steps, handler)

    flow = CfPFlow(event)

    assert len(flow.steps) == 5
    identifiers = [s.identifier for s in flow.steps]
    assert "plugin_step" in identifiers
    plugin_idx = identifiers.index("plugin_step")
    assert identifiers[plugin_idx - 1] == "user"
    assert identifiers[plugin_idx + 1] == "profile"
    assert flow.steps_dict["plugin_step"].is_completed(request=None) is True
