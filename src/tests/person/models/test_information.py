# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.person.models.information import SpeakerInformation, resource_path
from tests.factories import SpeakerInformationFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("adding", (True, False), ids=["adding", "saved"])
@pytest.mark.django_db
def test_speaker_information_resource_path(adding):
    info = SpeakerInformationFactory()
    saved_pk = info.pk
    info._state.adding = adding
    path = resource_path(info, "slides.pdf")

    assert path.endswith(".pdf")
    if adding:
        assert f"/info_{saved_pk}_" not in path
    else:
        assert f"/info_{saved_pk}_" in path


@pytest.mark.django_db
def test_speaker_information_log_parent_is_event():
    info = SpeakerInformationFactory()
    assert info.log_parent == info.event


def test_speaker_information_target_group_choices():
    valid_choices = {"submitters", "accepted", "confirmed"}
    field = SpeakerInformation._meta.get_field("target_group")
    actual_choices = {choice[0] for choice in field.choices}
    assert actual_choices == valid_choices
