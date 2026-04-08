# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.text.phrases import Phrases


class OrgaPhrases(Phrases, app="orga"):
    event_date_start_invalid = _("The event end cannot be before the start.")

    event_header_pattern_label = _("Frontpage header pattern")
    event_header_pattern_help_text = _(
        'Choose how the frontpage header banner will be styled. Pattern source: <a href="http://www.heropatterns.com/">heropatterns.com</a>, CC BY 4.0.'
    )
    event_schedule_format_label = _("Schedule display format")
    proposal_id_help_text = _(
        "The unique ID of a proposal is used in the proposal URL and in exports"
    )
    password_reset_success = _("The password was reset and the user was notified.")
    password_reset_fail = (
        _("The password reset email could not be sent, so the password was not reset."),
    )
    mails_in_outbox = _(
        "{count} emails have been saved to the outbox – you can make individual changes there or just send them all."
    )

    team = pgettext_lazy("organiser team", "Team")
    send_email = pgettext_lazy("action: send email to speaker(s)", "Send email")
    apply_pending_changes = _("Apply pending changes")
    no_data_to_export = _("No data to be exported")
    api_export_hint = _("You can also use the API to export or use data.")
    export_organiser_access = _(
        "Some of the general exports are only accessible for organisers, or include more information when accessed with your organiser account. If you want to access the organiser version in automatic integrations, you'll have to provide your authentication token just like in the API, like this:"
    )
    export_api_note = _(
        'Your token needs "action" permissions to access the predefined schedule exports via the API.'
    )
    export_custom_hint = _(
        "Build your own custom export here, by selecting all the data you need, and the export format. CSV exports can be opened with Excel and similar applications, while JSON exports are often used for integration with other tools."
    )
    export_plugin_hint = _(
        "pretalx provides a range of exports. If none of these match what you are looking for, you can also provide a custom plugin to export the data – please ask your administrator to install the plugin."
    )
    export_cross_link = _(
        "If you are looking for exports of proposals, sessions or schedule data, please head here:"
    )

    custom_field_active = _(
        "This field is currently active, it will be asked during submission."
    )
    custom_field_inactive = _(
        "This field is currently inactive, and will not be asked during submission."
    )
