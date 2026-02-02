# SPDX-FileCopyrightText: 2020-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.person.models.information import resource_path


@pytest.mark.django_db
def test_information_resource_path(information):
    path = resource_path(information, "foo.pdf")
    assert path.startswith(f"{information.event.slug}/speaker_information/info_")
    assert path.endswith(".pdf")
