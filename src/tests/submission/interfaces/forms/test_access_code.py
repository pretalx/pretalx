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


def test_access_code_form_init_scopes_choices_and_generates_code():
    event = EventFactory(feature_flags={"use_tracks": True})
    our_type = SubmissionTypeFactory(event=event)
    SubmissionTypeFactory(event=EventFactory())
    track = TrackFactory(event=event)
    access_code = SubmitterAccessCodeFactory(event=event)

    form = SubmitterAccessCodeForm(event=event)

    assert len(form.initial["code"]) > 0
    assert set(form.fields["submission_types"].queryset) == {
        event.cfp.default_type,
        our_type,
    }
    assert list(form.fields["tracks"].queryset) == [track]

    form = SubmitterAccessCodeForm(instance=access_code, event=event)

    assert form.instance.code == access_code.code

    form = SubmitterAccessCodeForm(
        event=EventFactory(feature_flags={"use_tracks": False})
    )

    assert "tracks" not in form.fields


def test_access_code_send_form_describes_restrictions():
    event = EventFactory(feature_flags={"use_tracks": True})
    event.mail_settings["subject_prefix"] = "TestConf"
    valid_until = now()
    access_code = SubmitterAccessCodeFactory(event=event, valid_until=valid_until)
    access_code.tracks.add(TrackFactory(event=event, name="Security"))
    access_code.submission_types.add(
        SubmissionTypeFactory(event=event, name="Lightning Talk")
    )

    form = AccessCodeSendForm(instance=access_code, user=UserFactory())

    assert str(event.name) in form.initial["subject"]
    assert "[TestConf]" not in form.initial["subject"]
    assert str(event.name) in form.initial["text"]
    assert "Security" in form.initial["text"]
    assert "Lightning Talk" in form.initial["text"]
    assert valid_until.strftime("%Y-%m-%d") in form.initial["text"]
    assert "submit a proposal to our CfP" not in form.initial["text"]


def test_access_code_send_form_generic_text_validates_for_long_event_name():
    event = EventFactory(name="E" * 200)
    access_code = SubmitterAccessCodeFactory(event=event)
    user = UserFactory()

    initial = AccessCodeSendForm(instance=access_code, user=user).initial
    form = AccessCodeSendForm(
        data={
            "to": "a@example.com",
            "subject": initial["subject"],
            "text": initial["text"],
        },
        instance=access_code,
        user=user,
    )

    assert "submit a proposal to our CfP" in initial["text"]
    assert len(initial["subject"]) <= 200
    assert form.is_valid()
    assert form.cleaned_data["subject"] == initial["subject"]
