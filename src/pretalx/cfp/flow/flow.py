# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Jahongir
# SPDX-FileContributor: Laura Klünder

import json
import logging
from collections import OrderedDict

from i18nfield.utils import I18nJSONEncoder

from pretalx.cfp.flow.steps import DEFAULT_STEPS
from pretalx.cfp.flow.utils import i18n_string
from pretalx.cfp.signals import cfp_steps
from pretalx.common.text.serialize import json_roundtrip

LOGGER = logging.getLogger(__name__)


class CfPFlow:
    """An event's CfPFlow contains the list of CfP steps.

    The ``event`` attribute contains the related event and is the only one required
    for instantiation.
    The ``steps`` attribute contains a (linked) list of BaseCfPStep instances.
    The ``steps_dict`` attribute contains an OrderedDict of the same steps.
    The ``config`` attribute contains the additional user configuration, primarily
    from the CfP editor.

    When instantiated with a request during submission time, it will only show
    the forms relevant to the current request. When instantiated without a
    request, for the CfP editor, it will contain all steps.
    """

    STEP_INFO = "info"
    STEP_QUESTIONS = "questions"
    STEP_USER = "user"
    STEP_PROFILE = "profile"
    # Virtual step IDs for question reordering in the CfP editor
    STEP_QUESTIONS_SUBMISSION = "questions_submission"
    STEP_QUESTIONS_SPEAKER = "questions_speaker"

    def __init__(self, event):
        self.event = event
        data = event.cfp.settings["flow"]
        self.config = self.get_config(data)

        steps = [step(event=event) for step in DEFAULT_STEPS]
        for __, response in cfp_steps.send_robust(self.event):
            if isinstance(response, Exception):
                LOGGER.warning(str(response))
                continue
            steps.extend(step_class(event=event) for step_class in response)
        steps = sorted(steps, key=lambda step: step.priority)
        self.steps_dict = OrderedDict()
        for step in steps:
            self.steps_dict[step.identifier] = step
        previous_step = None
        for step in steps:
            step._previous = previous_step  # noqa: SLF001  -- building linked list within same module
            if previous_step:
                previous_step._next = step  # noqa: SLF001  -- building linked list within same module
            previous_step = step

    def get_config(self, data, json_compat=False):
        if isinstance(data, str) and data:
            data = json.loads(data)
        if not isinstance(data, dict):
            return {}

        config = {"steps": {}}
        steps = data.get("steps", {})
        if isinstance(steps, dict):
            for key, value in steps.items():
                config["steps"][key] = self._get_step_config_from_data(value)
        if json_compat:
            config = json_roundtrip(config)
        return config

    def get_config_json(self):
        return json.dumps(self.config, cls=I18nJSONEncoder)

    def save_config(self, data):
        if isinstance(data, list) or (isinstance(data, dict) and "steps" not in data):
            data = {"steps": data}
        data = self.get_config(data, json_compat=True)
        self.event.cfp.settings["flow"] = data
        self.event.cfp.save()

    def reset(self):
        self.save_config(data=None)

    def _get_step_config_from_data(self, data):
        step_config = {}
        locales = self.event.locales
        for i18n_configurable in ("title", "text", "label"):
            if i18n_configurable in data:
                step_config[i18n_configurable] = i18n_string(
                    data[i18n_configurable], locales
                )
        for configurable in ("icon",):
            if configurable in data:
                step_config[configurable] = data[configurable]

        step_config["fields"] = []
        for config_field in data.get("fields", []):
            field = {}
            for key in ("help_text", "request", "required", "key", "label"):
                if key in config_field:
                    field[key] = (
                        i18n_string(config_field[key], locales)
                        if key in ("help_text", "label")
                        else config_field[key]
                    )
            step_config["fields"].append(field)
        return step_config

    @property
    def steps(self):
        return list(self.steps_dict.values())

    def get_step_config(self, step_id):
        return self.config.get("steps", {}).get(step_id, {})

    def get_field_config(self, step_id, field_key):
        step_config = self.get_step_config(step_id)
        for field in step_config.get("fields", []):
            if field.get("key") == field_key:
                return field
        return {}

    def _ensure_step_config(self, config, step_id):
        if "steps" not in config:
            config["steps"] = {}
        if step_id not in config["steps"]:
            config["steps"][step_id] = {"fields": []}
        if "fields" not in config["steps"][step_id]:
            config["steps"][step_id]["fields"] = []

    def update_step_header(self, step_id, title, text):
        config = self.config.copy()
        self._ensure_step_config(config, step_id)
        config["steps"][step_id]["title"] = title
        config["steps"][step_id]["text"] = text
        self.save_config(config)

    def update_field_config(self, step_id, field_key, label=None, help_text=None):
        config = self.config.copy()
        self._ensure_step_config(config, step_id)
        fields = config["steps"][step_id]["fields"]
        field_config = next((f for f in fields if f.get("key") == field_key), None)

        if field_config:
            if label:
                field_config["label"] = label
            if help_text:
                field_config["help_text"] = help_text
        else:
            new_config = {"key": field_key}
            if label:
                new_config["label"] = label
            if help_text:
                new_config["help_text"] = help_text
            fields.append(new_config)

        self.save_config(config)

    def update_field_order(self, step_id, field_order):
        config = self.config.copy()
        self._ensure_step_config(config, step_id)
        existing_fields = config["steps"][step_id].get("fields", [])
        existing_by_key = {f.get("key"): f for f in existing_fields}

        new_fields = []
        for key in field_order:
            if key in existing_by_key:
                new_fields.append(existing_by_key[key])
            else:
                new_fields.append({"key": key})

        config["steps"][step_id]["fields"] = new_fields
        self.save_config(config)
