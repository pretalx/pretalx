.. SPDX-FileCopyrightText: 2018-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. highlight:: python
   :linenothreshold: 5

.. _`pluginsignals`:

General APIs
============

This page lists some general signals and hooks which do not belong to a
specific plugin but might come in handy for all sorts of plugin.

Core
----

.. automodule:: pretalx.common.signals
   :members: periodic_task, register_locales, auth_html

.. automodule:: pretalx.submission.signals
   :members: before_submission_state_change, submission_state_change

.. automodule:: pretalx.schedule.signals
   :members: schedule_release

.. automodule:: pretalx.mail.signals
   :members: register_mail_placeholders, queuedmail_post_send, queuedmail_pre_send, request_pre_send

.. automodule:: pretalx.person.signals
   :members: delete_user

Exporters
---------

.. automodule:: pretalx.common.signals
   :no-index:
   :members: register_data_exporters


Organiser area
--------------

.. automodule:: pretalx.orga.signals
   :members: nav_event, nav_global, html_head, html_above_orga_page, html_below_orga_page, activate_event, nav_event_settings, event_copy_data, extra_form, speaker_form, submission_form, review_form, mail_form, dashboard_tile

.. automodule:: pretalx.common.signals
   :no-index:
   :members: activitylog_display, activitylog_object_link

Display
-------

.. automodule:: pretalx.cfp.signals
   :members: cfp_steps, footer_link, html_above_submission_list, html_above_profile_page, html_head

.. automodule:: pretalx.agenda.signals
   :members: register_recording_provider, html_above_session_pages, html_below_session_pages

.. automodule:: pretalx.common.signals
   :no-index:
   :members: profile_bottom_html
