# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.utils.timezone import now

from pretalx.submission.interfaces.forms import (
    AccessCodeSendForm,
    SubmitterAccessCodeForm,
)
from tests.factories import (
    EventFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_access_code_form_generates_code_for_new_instance():
    event = EventFactory()

    form = SubmitterAccessCodeForm(event=event)

    assert len(form.initial["code"]) > 0


def test_access_code_form_does_not_overwrite_existing_code():
    event = EventFactory()
    access_code = SubmitterAccessCodeFactory(event=event)

    form = SubmitterAccessCodeForm(instance=access_code, event=event)

    assert form.instance.code == access_code.code


def test_access_code_form_filters_submission_types_by_event():
    event = EventFactory()
    other_event = EventFactory()
    our_type = SubmissionTypeFactory(event=event)
    other_type = SubmissionTypeFactory(event=other_event)

    form = SubmitterAccessCodeForm(event=event)

    assert our_type in form.fields["submission_types"].queryset
    assert other_type not in form.fields["submission_types"].queryset


def test_access_code_form_shows_tracks_when_enabled():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)

    form = SubmitterAccessCodeForm(event=event)

    assert "tracks" in form.fields
    assert track in form.fields["tracks"].queryset


def test_access_code_form_hides_tracks_when_disabled():
    event = EventFactory(feature_flags={"use_tracks": False})

    form = SubmitterAccessCodeForm(event=event)

    assert "tracks" not in form.fields


def test_access_code_send_form_init_populates_subject_and_text():
    event = EventFactory()
    access_code = SubmitterAccessCodeFactory(event=event)
    user = UserFactory()

    form = AccessCodeSendForm(instance=access_code, user=user)

    assert str(event.name) in form.initial["subject"]
    assert str(event.name) in form.initial["text"]


def test_access_code_send_form_includes_tracks_in_text():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event, name="Security")
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.tracks.add(track)
    user = UserFactory()

    form = AccessCodeSendForm(instance=access_code, user=user)

    assert "Security" in form.initial["text"]


def test_access_code_send_form_includes_submission_types_in_text():
    event = EventFactory()
    stype = SubmissionTypeFactory(event=event, name="Lightning Talk")
    access_code = SubmitterAccessCodeFactory(event=event)
    access_code.submission_types.add(stype)
    user = UserFactory()

    form = AccessCodeSendForm(instance=access_code, user=user)

    assert "Lightning Talk" in form.initial["text"]


def test_access_code_send_form_includes_valid_until_in_text():
    event = EventFactory()
    valid_until = now()
    access_code = SubmitterAccessCodeFactory(event=event, valid_until=valid_until)
    user = UserFactory()

    form = AccessCodeSendForm(instance=access_code, user=user)

    assert valid_until.strftime("%Y-%m-%d") in form.initial["text"]


def test_access_code_send_form_generic_text_without_restrictions():
    """When no tracks or types are set, the text has a generic CfP message."""
    event = EventFactory()
    access_code = SubmitterAccessCodeFactory(event=event)
    user = UserFactory()

    form = AccessCodeSendForm(instance=access_code, user=user)

    assert "submit a proposal" in form.initial["text"].lower()
