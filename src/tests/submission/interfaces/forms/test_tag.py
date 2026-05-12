# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.interfaces.forms import TagForm, TagsForm
from tests.factories import EventFactory, SubmissionFactory, TagFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _data(**overrides):
    base = {
        "tag": "python",
        "description_0": "",
        "color": "#ff0000",
        "is_public": False,
    }
    return {**base, **overrides}


def test_tag_form_save_creates_tag():
    event = EventFactory()

    form = TagForm(data=_data(tag="python"), event=event)
    assert form.is_valid(), form.errors
    tag = form.save()

    assert tag.pk is not None
    assert tag.event == event
    assert tag.tag == "python"


@pytest.mark.parametrize(
    "tag_input", ("python", "  python  "), ids=("exact", "with_whitespace")
)
def test_tag_form_rejects_duplicate(tag_input):
    tag = TagFactory(tag="python")

    form = TagForm(data=_data(tag=tag_input), event=tag.event)

    assert not form.is_valid()
    assert "tag" in form.errors
    assert "already have a tag by this name" in str(form.errors["tag"])


def test_tag_form_allows_editing_own_tag():
    tag = TagFactory(tag="python")

    form = TagForm(data=_data(tag="python"), event=tag.event, instance=tag)

    assert form.is_valid(), form.errors


def test_tag_form_rejects_renaming_to_existing_tag():
    event = EventFactory()
    TagFactory(event=event, tag="python")
    other = TagFactory(event=event, tag="django")

    form = TagForm(data=_data(tag="python"), event=event, instance=other)

    assert not form.is_valid()
    assert "tag" in form.errors


def test_tag_form_read_only_rejects_changes():
    tag = TagFactory(tag="python")

    form = TagForm(
        data=_data(tag="changed"), event=tag.event, instance=tag, read_only=True
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_tag_form_read_only_disables_all_fields():
    tag = TagFactory(tag="python")

    form = TagForm(event=tag.event, instance=tag, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_tags_form_init_with_tags():
    """When the event has tags, the tags field is present with the correct queryset."""
    event = EventFactory()
    tag1 = TagFactory(event=event)
    tag2 = TagFactory(event=event)
    TagFactory()  # different event, should not appear

    submission = SubmissionFactory(event=event)
    form = TagsForm(event=event, instance=submission)

    assert "tags" in form.fields
    assert set(form.fields["tags"].queryset) == {tag1, tag2}
    assert form.fields["tags"].required is False


def test_tags_form_init_without_tags():
    """When the event has no tags, the tags field is removed."""
    event = EventFactory()
    submission = SubmissionFactory(event=event)

    form = TagsForm(event=event, instance=submission)

    assert "tags" not in form.fields


def test_tags_form_save():
    event = EventFactory()
    tag = TagFactory(event=event)
    submission = SubmissionFactory(event=event)

    form = TagsForm(event=event, instance=submission, data={"tags": [tag.pk]})

    assert form.is_valid()
    form.save()
    assert list(submission.tags.all()) == [tag]


def test_tags_form_read_only():
    """In read-only mode, all fields are disabled and clean raises an error."""
    event = EventFactory()
    TagFactory(event=event)
    submission = SubmissionFactory(event=event)

    form = TagsForm(event=event, instance=submission, read_only=True, data={})

    assert form.fields["tags"].disabled is True
    assert form.is_valid() is False
