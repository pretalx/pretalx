# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.upload import UploadView

pytestmark = pytest.mark.unit


def test_upload_view_allowed_types():
    assert UploadView.allowed_types == {
        "image/png": [".png"],
        "image/jpeg": [".jpg", ".jpeg"],
        "image/gif": [".gif"],
        "application/pdf": [".pdf"],
    }
