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

.. automodule:: pretalx.person.signals
   :members: html_above_person_form, html_below_person_form
   
.. automodule:: pretalx.submission.signals
   :members: html_above_submission_form, html_below_submission_form, html_below_submission_link, submission_state_change

.. automodule:: pretalx.schedule.signals
   :members: schedule_release

.. automodule:: pretalx.mail.signals
   :members: html_after_mail_badge, html_below_mail_subject, register_mail_placeholders, queuedmail_post_send, queuedmail_pre_send

Exporters
---------

.. automodule:: pretalx.common.signals
   :no-index:
   :members: register_data_exporters


Organiser area
--------------

.. automodule:: pretalx.orga.signals
   :members: nav_event, nav_global, html_head, activate_event, nav_event_settings, event_copy_data

.. automodule:: pretalx.common.signals
   :no-index:
   :members: activitylog_display, activitylog_object_link

Display
-------

.. automodule:: pretalx.cfp.signals
   :members: cfp_steps, footer_link, html_above_submission_list, html_above_profile_page, html_head

.. automodule:: pretalx.agenda.signals
   :members: register_recording_providers, html_above_session_pages, html_below_session_pages
