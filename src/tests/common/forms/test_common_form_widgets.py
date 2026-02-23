# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django import forms
from django_scopes import scope

from pretalx.common.forms.fields import HoneypotField
from pretalx.common.forms.widgets import BiographyWidget, MarkdownWidget
from pretalx.submission.forms.question import QuestionsForm
from pretalx.submission.forms.submission import InfoForm
from pretalx.submission.models import QuestionVariant


@pytest.mark.django_db
def test_character_limit_data_attributes_added(event):
    with scope(event=event):
        event.cfp.fields["abstract"] = {
            "visibility": "required",
            "min_length": 10,
            "max_length": 500,
        }
        event.cfp.save()


        form = InfoForm(event=event)

        assert form.fields["abstract"].widget.attrs.get("data-minlength") == 10
        assert form.fields["abstract"].widget.attrs.get("data-maxlength") == 500
        assert "maxlength" not in form.fields["abstract"].widget.attrs


@pytest.mark.django_db
def test_character_limit_only_for_chars_mode(event):
    with scope(event=event):
        event.cfp.settings["count_length_in"] = "words"
        event.cfp.fields["abstract"] = {
            "visibility": "required",
            "min_length": 10,
            "max_length": 500,
        }
        event.cfp.save()


        form = InfoForm(event=event)
        assert "data-minlength" not in form.fields["abstract"].widget.attrs
        assert "data-maxlength" not in form.fields["abstract"].widget.attrs


@pytest.mark.django_db
def test_question_field_data_attributes(event, question):
    with scope(event=event):
        question.variant = QuestionVariant.TEXT
        question.min_length = 20
        question.max_length = 1000
        question.save()


        form = QuestionsForm(event=event)
        field_name = f"question_{question.pk}"
        assert field_name in form.fields
        assert form.fields[field_name].widget.attrs.get("data-minlength") == 20
        assert form.fields[field_name].widget.attrs.get("data-maxlength") == 1000


class HoneypotTestForm(forms.Form):
    honeypot = HoneypotField()
    content = forms.CharField()


def test_honeypot_field_rejects_checked_value():
    form = HoneypotTestForm(data={"honeypot": "on", "content": "test"})
    assert not form.is_valid()
    assert "honeypot" in form.errors


def test_honeypot_field_accepts_unchecked_value():
    form = HoneypotTestForm(data={"content": "test"})
    assert form.is_valid()


def test_honeypot_field_accepts_empty_string():
    form = HoneypotTestForm(data={"honeypot": "", "content": "test"})
    assert form.is_valid()


def test_biography_widget_without_suggestions():
    widget = BiographyWidget()
    ctx = widget.get_context("biography", "", {})
    assert ctx["suggestions"] == []
    assert ctx["biographies"] == {}
    assert isinstance(widget, MarkdownWidget)


def test_biography_widget_with_suggestions():
    suggestions = [
        {"id": 1, "event_name": "PyCon", "biography": "I am a **Python** developer."},
        {"id": 2, "event_name": "JSConf", "biography": "I do JavaScript too."},
    ]
    widget = BiographyWidget(suggestions=suggestions)
    ctx = widget.get_context("biography", "", {})
    assert len(ctx["suggestions"]) == 2
    assert ctx["suggestions"][0]["event_name"] == "PyCon"
    assert ctx["suggestions"][0]["id"] == "1"
    assert "biography" not in ctx["suggestions"][0]
    assert "Python" in ctx["suggestions"][0]["preview"]
    assert "**" not in ctx["suggestions"][0]["preview"]
    assert ctx["biographies"]["1"] == "I am a **Python** developer."
    assert ctx["biographies"]["2"] == "I do JavaScript too."


def test_biography_widget_truncates_long_preview():
    long_bio = "A" * 300
    widget = BiographyWidget(
        suggestions=[{"id": 1, "event_name": "Conf", "biography": long_bio}]
    )
    ctx = widget.get_context("biography", "", {})
    preview = ctx["suggestions"][0]["preview"]
    assert len(preview) == 201  # 200 chars + ellipsis
    assert preview.endswith("…")


def test_biography_widget_no_ellipsis_for_short_preview():
    short_bio = "Short bio."
    widget = BiographyWidget(
        suggestions=[{"id": 1, "event_name": "Conf", "biography": short_bio}]
    )
    ctx = widget.get_context("biography", "", {})
    preview = ctx["suggestions"][0]["preview"]
    assert "…" not in preview
