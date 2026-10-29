# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.db import connection

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


def test_tag_form_creates_and_rejects_duplicates_and_read_only_changes():
    event = EventFactory()

    form = TagForm(data=_data(tag="python"), event=event)
    assert form.is_valid(), form.errors
    tag = form.save()

    assert tag.event == event
    assert tag.tag == "python"

    for tag_input in ("python", "  python  ", "Python"):
        form = TagForm(data=_data(tag=tag_input), event=event)
        assert not form.is_valid(), tag_input
        assert list(form.errors) == ["tag"]
        assert "already have a tag by this name" in str(form.errors["tag"])

    assert TagForm(data=_data(tag="python"), event=event, instance=tag).is_valid()

    other = TagFactory(event=event, tag="django")
    form = TagForm(data=_data(tag="python"), event=event, instance=other)

    assert not form.is_valid()
    assert list(form.errors) == ["tag"]

    form = TagForm(data=_data(tag="changed"), event=event, instance=tag, read_only=True)

    assert not form.is_valid()
    assert list(form.errors) == ["__all__"]

    form = TagForm(event=event, instance=tag, read_only=True)

    assert all(field.disabled for field in form.fields.values())


@pytest.mark.parametrize(
    ("existing_tag", "tag_input"), (("ß", "ẞ"), ("i", "İ")), ids=("sharp_s", "dotted_i")
)
def test_tag_form_folds_unicode_case_like_the_database(existing_tag, tag_input):
    tag = TagFactory(tag=existing_tag)
    with connection.cursor() as cursor:
        cursor.execute("SELECT LOWER(%s) = LOWER(%s)", [existing_tag, tag_input])
        (collides,) = cursor.fetchone()

    form = TagForm(data=_data(tag=tag_input), event=tag.event)

    assert form.is_valid() is not bool(collides)
    assert form.errors.keys() == ({"tag"} if collides else set())


def test_tags_form_offers_event_tags_and_saves():
    event = EventFactory()
    submission = SubmissionFactory(event=event)

    form = TagsForm(event=event, instance=submission)

    assert "tags" not in form.fields

    tag1 = TagFactory(event=event)
    tag2 = TagFactory(event=event)
    TagFactory()

    form = TagsForm(event=event, instance=submission)

    assert set(form.fields["tags"].queryset) == {tag1, tag2}
    assert form.fields["tags"].required is False

    form = TagsForm(event=event, instance=submission, data={"tags": [tag1.pk]})

    assert form.is_valid()
    form.save()
    assert list(submission.tags.all()) == [tag1]

    form = TagsForm(event=event, instance=submission, read_only=True, data={})

    assert form.fields["tags"].disabled is True
    assert form.is_valid() is False
