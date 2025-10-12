# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.common.exporter import BaseExporter


def test_common_base_exporter_raises_proper_exceptions():
    exporter = BaseExporter(None)
    with pytest.raises(NotImplementedError):
        exporter.identifier
    with pytest.raises(NotImplementedError):
        exporter.verbose_name
    with pytest.raises(NotImplementedError):
        exporter.public
    with pytest.raises(NotImplementedError):
        exporter.icon
    with pytest.raises(NotImplementedError):
        exporter.render(None)
    with pytest.raises(NotImplementedError):
        str(exporter)
    assert exporter.cors is None
    assert exporter.group == "submission"
