# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms

from pretalx.common.forms.renderers import InlineFormLabelRenderer
from pretalx.orga.forms.submission import (
    AddSpeakerForm,
    AddSpeakerInlineForm,
    SubmissionStateChangeForm,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_submission_state_change_form_pending_field():
    form = SubmissionStateChangeForm()

    assert "pending" in form.fields
    assert form.fields["pending"].required is False
    assert form.fields["pending"].initial is False


def test_submission_state_change_form_valid_with_pending_true():
    form = SubmissionStateChangeForm(data={"pending": True})

    assert form.is_valid()
    assert form.cleaned_data["pending"] is True


def test_submission_state_change_form_valid_without_data():
    form = SubmissionStateChangeForm(data={})

    assert form.is_valid()
    assert form.cleaned_data["pending"] is False


def test_add_speaker_form_init_removes_locale_for_single_locale(event):
    form = AddSpeakerForm(event=event)

    assert "locale" not in form.fields


def test_add_speaker_form_init_keeps_locale_for_multiple_locales():
    event = EventFactory(locale_array="en,de")

    form = AddSpeakerForm(event=event)

    assert "locale" in form.fields
    locale_codes = [code for code, _ in form.fields["locale"].choices]
    assert "en" in locale_codes
    assert "de" in locale_codes
    assert form.fields["locale"].initial == event.locale


def test_add_speaker_form_clean_name_without_email_raises_error(event):
    form = AddSpeakerForm(event=event, data={"name": "Speaker Name"})

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_add_speaker_form_clean_email_only_is_valid(event):
    form = AddSpeakerForm(event=event, data={"email": "speaker@example.com"})

    assert form.is_valid(), form.errors


def test_add_speaker_form_clean_both_name_and_email_is_valid(event):
    form = AddSpeakerForm(
        event=event, data={"email": "speaker@example.com", "name": "Speaker Name"}
    )

    assert form.is_valid(), form.errors


def test_add_speaker_form_clean_empty_is_valid(event):
    """Both email and name empty is valid (form allows optional submission)."""
    form = AddSpeakerForm(event=event, data={})

    assert form.is_valid(), form.errors


def test_add_speaker_form_email_uses_select_widget(event):
    form = AddSpeakerForm(event=event)

    assert isinstance(form.fields["email"].widget, forms.Select)


def test_add_speaker_inline_form_uses_inline_renderer(event):

    form = AddSpeakerInlineForm(event=event)

    assert form.default_renderer is InlineFormLabelRenderer
