.. SPDX-FileCopyrightText: 2019-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

Data models
===========

The following are all of the relevant pretalx database models, including their
interfaces. All non-documented methods and properties should be considered
private and unstable. All methods and properties documented here may change
between releases, but any change will be mentioned in the :ref:`changelog`.

All event related objects have an ``event`` property. It always returns the
event this object belongs to, to ease permission checks and reduce the need for
duplicate lookups.

Events and organisers
---------------------

.. autoclass:: pretalx.event.models.event.Event(*args, **kwargs)
   :members: cache,locales,is_multilingual,named_locales,plugin_list,pending_mails,wip_schedule,current_schedule,teams,datetime_from,datetime_to,talks,speakers,submitters,get_date_range_display

.. autofunction:: pretalx.event.domain.plugins.enable_plugin

.. autofunction:: pretalx.event.domain.plugins.disable_plugin

.. autoclass:: pretalx.event.models.organiser.Organiser(*args, **kwargs)

.. autofunction:: pretalx.event.domain.organiser.shred_organiser

.. autoclass:: pretalx.event.models.organiser.Team(*args, **kwargs)
   :members: permission_set

.. autoclass:: pretalx.submission.models.cfp.CfP(*args, **kwargs)
   :members: max_deadline,is_open

.. autoclass:: pretalx.submission.models.review.ReviewPhase(*args, **kwargs)

.. autofunction:: pretalx.submission.domain.review.activate_review_phase

Users and profiles
------------------

.. autoclass:: pretalx.person.models.user.User(*args, **kwargs)
   :members: get_display_name,get_speaker,log_action,get_events_with_any_permission,get_events_for_permission,get_permissions_for_event

.. autoclass:: pretalx.person.models.profile.SpeakerProfile(*args, **kwargs)
   :members: submissions,talks,answers

.. autoclass:: pretalx.person.models.information.SpeakerInformation(*args, **kwargs)
   :members: id

Submissions
-----------

Submissions are the most central model to pretalx, and everything else is
connected to submissions.

.. autoclass:: pretalx.submission.models.submission.Submission(*args, **kwargs)
   :members: editable,is_anonymised,get_duration,accept,confirm,reject,cancel,withdraw,slot,public_slots,display_speaker_names,availabilities

.. autofunction:: pretalx.submission.domain.submission.submit_draft

.. autofunction:: pretalx.submission.domain.submission.set_submission_state

.. autofunction:: pretalx.submission.domain.submission.update_duration

.. autofunction:: pretalx.submission.domain.submission.update_talk_slots

.. autofunction:: pretalx.submission.domain.submission.add_speaker

.. autoclass:: pretalx.submission.models.review.Review(*args, **kwargs)
   :members: display_score

.. autofunction:: pretalx.submission.domain.review.update_review_score

.. autofunction:: pretalx.submission.domain.review.recalculate_submission_scores

.. autoclass:: pretalx.submission.models.feedback.Feedback(*args, **kwargs)
   :members: id

.. autoclass:: pretalx.submission.models.track.Track(*args, **kwargs)
   :members: slug

.. autoclass:: pretalx.submission.models.type.SubmissionType(*args, **kwargs)
   :members: slug

.. autofunction:: pretalx.submission.domain.submission_type.propagate_default_duration

.. autoclass:: pretalx.submission.models.resource.Resource(*args, **kwargs)
   :members: id

Questions and answers
---------------------

.. autoclass:: pretalx.submission.models.question.Question(*args, **kwargs)

.. autofunction:: pretalx.submission.domain.queries.question.count_missing_answers

.. autoclass:: pretalx.submission.models.question.AnswerOption(*args, **kwargs)
   :members: id

.. autoclass:: pretalx.submission.models.question.Answer(*args, **kwargs)

Schedules and talk slots
------------------------

.. autoclass:: pretalx.schedule.models.schedule.Schedule(*args, **kwargs)
   :members: scheduled_talks,slots,previous_schedule,changes,warnings,speakers_concerned

.. autofunction:: pretalx.schedule.domain.release.freeze_schedule

.. autofunction:: pretalx.schedule.domain.release.unfreeze_schedule

.. autoclass:: pretalx.schedule.models.slot.TalkSlot(*args, **kwargs)
   :members: duration,real_end,as_availability,is_same_slot

.. autoclass:: pretalx.schedule.models.availability.Availability(*args, **kwargs)
   :members: __eq__,all_day,overlaps,contains,merge_with,__or__,intersect_with,__and__,union,intersection

.. autoclass:: pretalx.schedule.models.room.Room(*args, **kwargs)
   :members: id

Emails and templates
--------------------

.. autoclass:: pretalx.mail.models.MailTemplate

.. autoclass:: pretalx.mail.models.QueuedMail
   :members: send

Email construction and dispatch
-------------------------------

The mail pipeline is split across three modules under
``pretalx.mail.domain``: ``render`` constructs an unsaved
:class:`~pretalx.mail.models.QueuedMail`, ``queue`` persists it (or
manipulates outbox rows), and ``send`` hands a mail to the worker for
delivery. Plugins should always go through these helpers rather than
calling ``mail.save()`` or ``backend.send_messages()`` directly.

Rendering
~~~~~~~~~

.. autofunction:: pretalx.mail.domain.render.render_template_to_mail

.. autofunction:: pretalx.mail.domain.render.render_to_mail

.. autofunction:: pretalx.mail.domain.render.build_trusted_mail

Outbox persistence
~~~~~~~~~~~~~~~~~~

.. autofunction:: pretalx.mail.domain.queue.save_draft

.. autofunction:: pretalx.mail.domain.queue.copy_to_draft

Dispatch
~~~~~~~~

.. autofunction:: pretalx.mail.domain.send.send_draft

.. autofunction:: pretalx.mail.domain.send.send_transient

.. autofunction:: pretalx.mail.domain.send.send_system_mail

.. autofunction:: pretalx.event.domain.mail.send_orga_mail

Utility models
--------------

.. autoclass:: pretalx.common.models.log.ActivityLog
   :members: display
