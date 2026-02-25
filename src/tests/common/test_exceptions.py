import logging
import sys

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core import mail as djmail
from django.test import RequestFactory, override_settings

from pretalx.common.exceptions import (
    PretalxAdminEmailHandler,
    PretalxCeleryExceptionReporter,
    PretalxExceptionReporter,
    SendMailException,
    SubmissionError,
    UserDeletionError,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.unit


def _make_reporter(request=None, is_email=False, exc_cls=ValueError, exc_msg="test"):
    try:
        raise exc_cls(exc_msg)
    except exc_cls:
        exc_type, exc_value, tb = sys.exc_info()
    return PretalxExceptionReporter(request, exc_type, exc_value, tb, is_email=is_email)


@pytest.mark.parametrize(
    "exc_cls", (SendMailException, SubmissionError, UserDeletionError)
)
def test_custom_exception_is_raisable(exc_cls):
    with pytest.raises(exc_cls):
        raise exc_cls("test")


@override_settings(DEBUG=True)
def test_reporter_get_traceback_text_returns_plain_in_debug():
    reporter = _make_reporter(is_email=True)

    text = reporter.get_traceback_text()

    assert "You are receiving this email" not in text
    assert "ValueError" in text


def test_reporter_get_traceback_text_returns_plain_when_not_email():
    reporter = _make_reporter(is_email=False)

    text = reporter.get_traceback_text()

    assert "You are receiving this email" not in text


@override_settings(DEBUG=False, SITE_URL="https://example.com")
def test_reporter_get_traceback_text_adds_intro_for_email():
    rf = RequestFactory()
    request = rf.get("/some/path")
    request.user = AnonymousUser()
    reporter = _make_reporter(request=request, is_email=True)

    text = reporter.get_traceback_text()

    assert "You are receiving this email" in text
    assert "https://example.com" in text
    assert "ValueError (test)" in text
    assert "test_exceptions.py" in text


@override_settings(DEBUG=False, SITE_URL="https://example.com")
def test_reporter_get_traceback_text_without_exc_type():
    """When exc_type is None, falls back to 'Exception'."""
    rf = RequestFactory()
    request = rf.get("/test")
    request.user = AnonymousUser()
    reporter = PretalxExceptionReporter(request, None, None, None, is_email=True)

    text = reporter.get_traceback_text()

    assert "The error was Exception at" in text


def test_reporter_user_no_request():
    reporter = _make_reporter(request=None)

    assert reporter.user == ""


def test_reporter_user_anonymous():
    rf = RequestFactory()
    request = rf.get("/")
    request.user = AnonymousUser()
    reporter = _make_reporter(request=request)

    assert reporter.user == "an anonymous user"


@pytest.mark.django_db
def test_reporter_user_authenticated():
    rf = RequestFactory()
    request = rf.get("/")
    user = UserFactory(name="Ada Lovelace", email="ada@example.com")
    request.user = user
    reporter = _make_reporter(request=request)

    assert reporter.user == "Ada Lovelace <ada@example.com>"


def test_reporter_get_tldr_no_request():
    reporter = _make_reporter(request=None)

    assert reporter.get_tldr() == ""


def test_reporter_get_tldr_without_event():
    rf = RequestFactory()
    request = rf.get("/some/path")
    request.user = AnonymousUser()
    reporter = _make_reporter(request=request)

    tldr = reporter.get_tldr()

    assert (
        tldr
        == "tl;dr: An exception occurred when an anonymous user accessed /some/path"
    )


@pytest.mark.django_db
def test_reporter_get_tldr_with_event(event):
    rf = RequestFactory()
    request = rf.get("/event/page")
    request.user = AnonymousUser()
    request.event = event
    reporter = _make_reporter(request=request)

    tldr = reporter.get_tldr()

    assert (
        tldr
        == f"tl;dr: An exception occurred when an anonymous user accessed /event/page, an event page of {event.name}."
    )


def test_reporter_get_extra_intro_no_request():
    reporter = _make_reporter(request=None)

    assert reporter.get_extra_intro() == ""


def test_reporter_get_extra_intro_without_event():
    rf = RequestFactory()
    request = rf.get("/page")
    request.user = AnonymousUser()
    reporter = _make_reporter(request=request)

    intro = reporter.get_extra_intro()

    assert intro == "\nIt occurred when an anonymous user accessed /page."


@pytest.mark.django_db
def test_reporter_get_extra_intro_with_event(event):
    rf = RequestFactory()
    request = rf.get("/event/page")
    request.user = AnonymousUser()
    request.event = event
    reporter = _make_reporter(request=request)

    intro = reporter.get_extra_intro()

    expected = (
        f"\nIt occurred when an anonymous user accessed /event/page."
        f"\nThis page belongs to {event.name} <{event.orga_urls.base.full()}>."
    )
    assert intro == expected


def test_celery_reporter_get_tldr():
    reporter = PretalxCeleryExceptionReporter(None, None, None, None, task_id="abc-123")

    assert reporter.get_tldr() == "tl;dr: An exception occurred in task abc-123"


@pytest.mark.parametrize(
    ("celery_args", "expected"),
    (
        pytest.param(None, "", id="no_args"),
        pytest.param(("only_one",), "", id="wrong_length"),
        pytest.param(
            (["arg1", "arg2"], {"key": "val"}),
            "\nTask args: arg1, arg2\nTask kwargs: {'key': 'val'}",
            id="args_and_kwargs",
        ),
        pytest.param((["arg1"], {}), "\nTask args: arg1", id="args_only"),
        pytest.param(
            ([], {"key": "val"}), "\nTask kwargs: {'key': 'val'}", id="kwargs_only"
        ),
        pytest.param((42, None), "\nTask args: 42", id="non_iterable_args"),
    ),
)
def test_celery_reporter_get_extra_intro(celery_args, expected):
    reporter = PretalxCeleryExceptionReporter(
        None, None, None, None, task_id="t1", celery_args=celery_args
    )

    assert reporter.get_extra_intro() == expected


@override_settings(EMAIL_SUBJECT_PREFIX="[Django] ")
def test_admin_email_handler_format_subject_removes_prefix():
    handler = PretalxAdminEmailHandler()

    result = handler.format_subject("Test error")

    assert result == "Test error"


def test_admin_email_handler_emit_skips_500_path():
    djmail.outbox = []
    handler = PretalxAdminEmailHandler()
    rf = RequestFactory()
    request = rf.get("/500")
    record = logging.LogRecord(
        name="django.request",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Internal Server Error",
        args=(),
        exc_info=None,
    )
    record.request = request

    result = handler.emit(record)

    assert result is None
    assert len(djmail.outbox) == 0


@override_settings(
    ADMINS=[("Admin", "admin@example.com")], DEBUG=False, SITE_URL="https://example.com"
)
def test_admin_email_handler_emit_sends_for_non_500():
    djmail.outbox = []
    handler = PretalxAdminEmailHandler()
    rf = RequestFactory()
    request = rf.get("/other")
    try:
        raise ValueError("test error")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="django.request",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Internal Server Error: %s",
        args=("/other",),
        exc_info=exc_info,
    )
    record.request = request
    record.status_code = 500

    handler.emit(record)

    assert len(djmail.outbox) == 1
    email = djmail.outbox[0]
    assert email.to == ["admin@example.com"]
    assert (
        email.subject == "[pretalx] ERROR (EXTERNAL IP): Internal Server Error: /other"
    )
    assert "You are receiving this email" in email.body
    assert "https://example.com" in email.body
    assert "ValueError" in email.body
