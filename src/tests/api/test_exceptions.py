import json
import logging

import pytest
from rest_framework import exceptions

from pretalx.api.exceptions import api_exception_handler

pytestmark = pytest.mark.unit


def test_api_exception_handler_api_exception(caplog):
    """API exceptions are logged at debug level and produce a DRF Response."""
    exc = exceptions.NotFound("Not found.")

    with caplog.at_level(logging.DEBUG, logger="pretalx.api.exceptions"):
        response = api_exception_handler(exc, context={})

    assert response is not None
    assert response.status_code == 404
    assert len(caplog.records) == 1
    assert "404" in caplog.records[0].message
    assert json.dumps(exc.detail) in caplog.records[0].message


def test_api_exception_handler_non_api_exception(caplog):
    """Non-API exceptions return None and are not logged, matching DRF convention."""
    exc = ValueError("something broke")

    with caplog.at_level(logging.DEBUG, logger="pretalx.api.exceptions"):
        response = api_exception_handler(exc, context={})

    assert response is None
    assert len(caplog.records) == 0
