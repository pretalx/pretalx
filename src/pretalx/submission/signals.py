# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.dispatch import receiver

from pretalx.common.signals import EventPluginSignal, register_data_exporters

before_submission_state_change = EventPluginSignal()
"""
This signal is fired before a submission's state is changed, allowing plugins to
prevent the transition. Receivers get the submission (with its current state still
intact), the intended new state, and the user triggering the change.

This signal is **not** fired for the initial submission (draft/new to submitted),
only for subsequent state changes.

Raising :class:`~pretalx.common.exceptions.SubmissionError` will cancel the state
change. Any other exceptions are ignored.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, you will receive the keyword arguments ``submission``, ``new_state``,
and ``user`` (which may be ``None``).
"""

submission_state_change = EventPluginSignal()
"""
This signal allows you to trigger additional events when a submission changes
its state. You will receive the submission after it has been saved, the previous
state, and the user triggering the change if available.
Any exceptions raised will be ignored.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, you will receive the keyword arguments ``submission``, ``old_state``,
and ``user`` (which may be ``None``).
When the submission is created or submitted from a draft state, ``old_state`` will be
``None``.
"""


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_speaker_question")
def register_speaker_question_exporter(sender, **kwargs):
    from pretalx.submission.interfaces.exporters import (  # noqa: PLC0415 -- avoid circular import
        SpeakerQuestionData,
    )

    return SpeakerQuestionData


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_submission_question")
def register_submission_question_exporter(sender, **kwargs):
    from pretalx.submission.interfaces.exporters import (  # noqa: PLC0415 -- avoid circular import
        SubmissionQuestionData,
    )

    return SubmissionQuestionData
