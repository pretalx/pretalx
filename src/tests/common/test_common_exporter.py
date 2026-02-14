# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.common.exporter import BaseExporter


def test_common_base_exporter_raises_proper_exceptions():
    exporter = BaseExporter(None)
    with pytest.raises(NotImplementedError):
        exporter.identifier  # noqa: B018
    with pytest.raises(NotImplementedError):
        exporter.verbose_name  # noqa: B018
    with pytest.raises(NotImplementedError):
        exporter.public  # noqa: B018
    with pytest.raises(NotImplementedError):
        exporter.icon  # noqa: B018
    with pytest.raises(NotImplementedError):
        exporter.render(None)
    with pytest.raises(NotImplementedError):
        str(exporter)  # noqa: B018
    assert exporter.cors is None
    assert exporter.group == "submission"
