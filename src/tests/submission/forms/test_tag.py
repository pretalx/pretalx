import pytest
from django_scopes import scopes_disabled

from pretalx.submission.forms.tag import TagForm
from tests.factories import EventFactory, TagFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_tag_form_valid_with_unique_tag():
    with scopes_disabled():
        event = EventFactory()

        form = TagForm(
            data={
                "tag": "python",
                "description_0": "",
                "color": "#ff0000",
                "is_public": False,
            },
            event=event,
        )

        assert form.is_valid(), form.errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    "tag_input", ("python", "  python  "), ids=("exact", "with_whitespace")
)
def test_tag_form_clean_tag_rejects_duplicate(tag_input):
    with scopes_disabled():
        tag = TagFactory(tag="python")

        form = TagForm(
            data={
                "tag": tag_input,
                "description_0": "",
                "color": "#00ff00",
                "is_public": False,
            },
            event=tag.event,
        )

        assert not form.is_valid()
        assert "tag" in form.errors


@pytest.mark.django_db
def test_tag_form_clean_tag_allows_editing_own_tag():
    """Editing an existing tag should not conflict with itself."""
    with scopes_disabled():
        tag = TagFactory(tag="python")

        form = TagForm(
            data={
                "tag": "python",
                "description_0": "",
                "color": "#ff0000",
                "is_public": True,
            },
            event=tag.event,
            instance=tag,
        )

        assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_tag_form_clean_tag_rejects_duplicate_when_editing_different_tag():
    with scopes_disabled():
        event = EventFactory()
        TagFactory(event=event, tag="python")
        other_tag = TagFactory(event=event, tag="django")

        form = TagForm(
            data={
                "tag": "python",
                "description_0": "",
                "color": "#0000ff",
                "is_public": False,
            },
            event=event,
            instance=other_tag,
        )

        assert not form.is_valid()
        assert "tag" in form.errors


@pytest.mark.django_db
def test_tag_form_read_only_rejects_changes():
    with scopes_disabled():
        tag = TagFactory(tag="python")

        form = TagForm(
            data={
                "tag": "changed",
                "description_0": "",
                "color": "#ff0000",
                "is_public": False,
            },
            event=tag.event,
            instance=tag,
            read_only=True,
        )

        assert not form.is_valid()
        assert "__all__" in form.errors


@pytest.mark.django_db
def test_tag_form_read_only_disables_all_fields():
    with scopes_disabled():
        tag = TagFactory(tag="python")

    form = TagForm(event=tag.event, instance=tag, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True
