import pytest

from tests.factories import TagFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_tag_str():
    tag = TagFactory(tag="keynote")
    assert str(tag) == "keynote"


@pytest.mark.django_db
def test_tag_log_parent_is_event():
    tag = TagFactory()
    assert tag.log_parent == tag.event


@pytest.mark.django_db
def test_tag_log_prefix():
    tag = TagFactory()
    assert tag.log_prefix == "pretalx.tag"
