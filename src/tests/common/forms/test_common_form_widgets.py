# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.submission.forms.question import QuestionsForm
from pretalx.submission.forms.submission import InfoForm
from pretalx.submission.models import QuestionVariant


@pytest.mark.django_db
def test_character_limit_data_attributes_added(event):
    event.cfp.fields["abstract"] = {
        "visibility": "required",
        "min_length": 10,
        "max_length": 500,
    }
    event.cfp.save()

    with scope(event=event):
        form = InfoForm(event=event)

        assert form.fields["abstract"].widget.attrs.get("data-minlength") == 10
        assert form.fields["abstract"].widget.attrs.get("data-maxlength") == 500
        assert "maxlength" not in form.fields["abstract"].widget.attrs


@pytest.mark.django_db
def test_character_limit_only_for_chars_mode(event):
    event.cfp.settings["count_length_in"] = "words"
    event.cfp.fields["abstract"] = {
        "visibility": "required",
        "min_length": 10,
        "max_length": 500,
    }
    event.cfp.save()

    with scope(event=event):
        form = InfoForm(event=event)
        assert "data-minlength" not in form.fields["abstract"].widget.attrs
        assert "data-maxlength" not in form.fields["abstract"].widget.attrs


@pytest.mark.django_db
def test_question_field_data_attributes(event, question):
    question.variant = QuestionVariant.TEXT
    question.min_length = 20
    question.max_length = 1000
    question.save()

    with scope(event=event):
        form = QuestionsForm(event=event)
        field_name = f"question_{question.pk}"
        assert field_name in form.fields
        assert form.fields[field_name].widget.attrs.get("data-minlength") == 20
        assert form.fields[field_name].widget.attrs.get("data-maxlength") == 1000
