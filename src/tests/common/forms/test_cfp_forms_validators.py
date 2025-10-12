# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.exceptions import ValidationError

from pretalx.common.forms.validators import ZXCVBNValidator


@pytest.mark.parametrize(
    "score,works",
    (
        (-1, False),
        (0, True),
        (2, True),
        (4, True),
        (5, False),
    ),
)
def test_zxcvbn_validator_init_works(score, works):
    if works:
        ZXCVBNValidator(min_score=score)
    else:
        with pytest.raises(Exception):  # noqa: it really is an Exception
            ZXCVBNValidator(min_score=score)


@pytest.mark.parametrize(
    "password,works",
    (
        ("password", False),
        ("theMightyPassword", True),
    ),
)
def test_password_validation(password, works):
    if works:
        ZXCVBNValidator()(password)
    else:
        with pytest.raises(ValidationError):  # noqa: it really is an Exception
            ZXCVBNValidator()(password)
