# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json
import uuid

from django.utils.translation import gettext_noop
from hierarkey.models import GlobalSettingsBase, Hierarkey
from i18nfield.strings import LazyI18nString

hierarkey = Hierarkey(attribute_name="settings")


INSTANCE_IDENTIFIER = None


@hierarkey.set_global()
class GlobalSettings(GlobalSettingsBase):
    def get_instance_identifier(self):
        global INSTANCE_IDENTIFIER  # noqa: PLW0603 -- module-level cache for instance identifier

        if INSTANCE_IDENTIFIER:
            return INSTANCE_IDENTIFIER

        try:
            INSTANCE_IDENTIFIER = uuid.UUID(self.settings.get("instance_identifier"))
        except (TypeError, ValueError):
            INSTANCE_IDENTIFIER = uuid.uuid4()
            self.settings.set("instance_identifier", str(INSTANCE_IDENTIFIER))
        return INSTANCE_IDENTIFIER


def i18n_unserialise(value):
    try:
        return LazyI18nString(json.loads(value))
    except ValueError:
        return LazyI18nString(str(value))


def i18n_serialise(value):
    return json.dumps(value.data)


hierarkey.add_type(
    LazyI18nString, serialize=i18n_serialise, unserialize=i18n_unserialise
)


hierarkey.add_default("update_check_ack", "False", bool)
hierarkey.add_default("update_check_email", "", str)
hierarkey.add_default("update_check_enabled", "True", bool)
hierarkey.add_default("update_check_result", None, dict)
hierarkey.add_default("update_check_result_warning", "False", bool)
hierarkey.add_default("update_check_last", None, dt.datetime)
hierarkey.add_default("update_check_id", None, str)

hierarkey.add_default("sent_mail_cfp_closed", "False", bool)
hierarkey.add_default("sent_mail_event_over", "False", bool)

hierarkey.add_default(
    "review_help_text",
    LazyI18nString.from_gettext(
        gettext_noop(
            "Please give a fair review on why you’d like to see this proposal at the conference, or why you think it would not be a good fit."
        )
    ),
    LazyI18nString,
)
