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
   :members: periodic_task, register_locales

.. automodule:: pretalx.submission.signals
   :members: submission_state_change

.. automodule:: pretalx.schedule.signals
   :members: schedule_release

.. automodule:: pretalx.mail.signals
   :members: register_mail_placeholders

Exporters
---------

.. automodule:: pretalx.common.signals
   :members: register_data_exporters


Organiser area
--------------

.. automodule:: pretalx.orga.signals
   :members: nav_event, nav_global, activate_event, nav_event_settings, event_copy_data

.. automodule:: pretalx.common.signals
   :members: activitylog_display

Display
-------

.. automodule:: pretalx.cfp.signals
   :members: cfp_steps, footer_link, html_above_submission_list, html_above_profile_page, html_head

.. automodule:: pretalx.agenda.signals
   :members: register_recording_providers
