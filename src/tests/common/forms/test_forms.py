# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.forms.models import BaseModelFormSet, inlineformset_factory
from django_scopes import scope

from pretalx.common.forms import save_related_formset
from pretalx.submission.interfaces.forms import ResourceForm
from pretalx.submission.models import Resource, Submission
from tests.factories import EventFactory, ResourceFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def make_resource_formset(submission, data):
    formset_class = inlineformset_factory(
        Submission,
        Resource,
        form=ResourceForm,
        formset=BaseModelFormSet,
        can_delete=True,
        extra=0,
    )
    return formset_class(
        data=data, queryset=submission.resources.all(), prefix="resource"
    )


def test_save_related_formset_saves_new_with_fk():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    formset = make_resource_formset(
        submission,
        data={
            "resource-TOTAL_FORMS": "1",
            "resource-INITIAL_FORMS": "0",
            "resource-MIN_NUM_FORMS": "0",
            "resource-MAX_NUM_FORMS": "1000",
            "resource-0-description": "Slides",
            "resource-0-link": "https://example.com/slides",
            "resource-0-resource": "",
        },
    )

    with scope(event=event):
        assert formset.is_valid()
        save_related_formset(formset, parent=submission, fk_field="submission")

        assert submission.resources.count() == 1
        assert submission.resources.first().description == "Slides"


def test_save_related_formset_handles_deleted_unsaved_form():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    formset = make_resource_formset(
        submission,
        data={
            "resource-TOTAL_FORMS": "1",
            "resource-INITIAL_FORMS": "0",
            "resource-MIN_NUM_FORMS": "0",
            "resource-MAX_NUM_FORMS": "1000",
            "resource-0-description": "",
            "resource-0-link": "",
            "resource-0-resource": "",
            "resource-0-DELETE": "on",
        },
    )

    with scope(event=event):
        assert formset.is_valid()
        save_related_formset(formset, parent=submission, fk_field="submission")

        assert submission.resources.count() == 0


def test_save_related_formset_deletes_marked_forms():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        resource = ResourceFactory(submission=submission)

    formset = make_resource_formset(
        submission,
        data={
            "resource-TOTAL_FORMS": "1",
            "resource-INITIAL_FORMS": "1",
            "resource-MIN_NUM_FORMS": "0",
            "resource-MAX_NUM_FORMS": "1000",
            "resource-0-id": str(resource.pk),
            "resource-0-description": resource.description,
            "resource-0-link": resource.link or "",
            "resource-0-resource": "",
            "resource-0-DELETE": "on",
        },
    )

    with scope(event=event):
        assert formset.is_valid()
        save_related_formset(formset, parent=submission, fk_field="submission")

        assert submission.resources.count() == 0


def test_save_related_formset_skips_delete_when_initial_pk_missing():
    """Guard against a delete on an initial form whose instance lost its pk
    (e.g. a concurrent delete between formset build and save)."""
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        resource = ResourceFactory(submission=submission)

    formset = make_resource_formset(
        submission,
        data={
            "resource-TOTAL_FORMS": "1",
            "resource-INITIAL_FORMS": "1",
            "resource-MIN_NUM_FORMS": "0",
            "resource-MAX_NUM_FORMS": "1000",
            "resource-0-id": str(resource.pk),
            "resource-0-description": resource.description,
            "resource-0-link": resource.link or "",
            "resource-0-resource": "",
            "resource-0-DELETE": "on",
        },
    )

    with scope(event=event):
        assert formset.is_valid()
        formset.initial_forms[0].instance.pk = None
        save_related_formset(formset, parent=submission, fk_field="submission")

        assert Resource.objects.filter(pk=resource.pk).exists()


def test_save_related_formset_skips_unchanged_extra_form():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    formset = make_resource_formset(
        submission,
        data={
            "resource-TOTAL_FORMS": "2",
            "resource-INITIAL_FORMS": "0",
            "resource-MIN_NUM_FORMS": "0",
            "resource-MAX_NUM_FORMS": "1000",
            "resource-0-description": "Filled",
            "resource-0-link": "https://example.com/filled",
            "resource-0-resource": "",
            "resource-1-description": "",
            "resource-1-link": "",
            "resource-1-resource": "",
            "resource-1-is_public": "on",
        },
    )

    with scope(event=event):
        assert formset.is_valid()
        save_related_formset(formset, parent=submission, fk_field="submission")

        assert submission.resources.count() == 1
