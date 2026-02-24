import pytest

from pretalx.person.models.information import SpeakerInformation, resource_path
from tests.factories import SpeakerInformationFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("has_pk", (True, False), ids=["with_pk", "without_pk"])
@pytest.mark.django_db
def test_speaker_information_resource_path(has_pk):
    info = SpeakerInformationFactory()
    saved_pk = info.pk
    if not has_pk:
        info.pk = None
    path = resource_path(info, "slides.pdf")

    assert path.endswith(".pdf")
    if has_pk:
        assert f"/info_{saved_pk}_" in path
    else:
        assert f"/info_{saved_pk}_" not in path


@pytest.mark.django_db
def test_speaker_information_log_parent_is_event():
    info = SpeakerInformationFactory()
    assert info.log_parent == info.event


def test_speaker_information_target_group_choices():
    valid_choices = {"submitters", "accepted", "confirmed"}
    field = SpeakerInformation._meta.get_field("target_group")
    actual_choices = {choice[0] for choice in field.choices}
    assert actual_choices == valid_choices
