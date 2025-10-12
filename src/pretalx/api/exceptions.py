# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
import logging

from rest_framework import exceptions
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    if isinstance(exc, exceptions.APIException):
        logger.debug(f"API Exception [{exc.status_code}]: {json.dumps(exc.detail)}")

    return exception_handler(exc, context)
