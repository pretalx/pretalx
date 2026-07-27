# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.forms.renderers import InlineFormLabelRenderer
from pretalx.common.forms.widgets import UserSearchSelect
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
    event = EventFactory(locales=["en", "de"])

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


def test_add_speaker_form_email_uses_user_search_select_widget(event):
    form = AddSpeakerForm(event=event)

    assert isinstance(form.fields["email"].widget, UserSearchSelect)
    assert "<option" not in str(form["email"])


@pytest.mark.parametrize(
    ("prefix", "data", "select_name"),
    (
        pytest.param(None, {"email": "speaker@example.com"}, "email", id="email"),
        pytest.param(
            "speaker",
            {"speaker-email": "speaker@example.com"},
            "speaker-email",
            id="prefixed-email",
        ),
    ),
)
def test_add_speaker_form_bound_email_rendered_as_selected_option(
    event, prefix, data, select_name
):
    form = AddSpeakerForm(event=event, prefix=prefix, data=data)

    html = str(form["email"])
    assert f'<select name="{select_name}"' in html
    assert (
        '<option value="speaker@example.com" selected>speaker@example.com</option>'
        in html
    )


def test_add_speaker_form_bound_without_email_renders_no_options(event):
    form = AddSpeakerForm(event=event, data={"name": "Speaker Name"})

    assert "<option" not in str(form["email"])


def test_add_speaker_inline_form_uses_inline_renderer(event):

    form = AddSpeakerInlineForm(event=event)

    assert form.default_renderer is InlineFormLabelRenderer
