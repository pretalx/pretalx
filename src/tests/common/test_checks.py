import pytest
from django.core.checks import ERROR, INFO, WARNING
from django.test import override_settings

from pretalx.common.checks import (
    check_admin_email,
    check_caches,
    check_celery,
    check_debug,
    check_sqlite_in_production,
    check_system_email,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "check_fn",
    (
        check_admin_email,
        check_caches,
        check_celery,
        check_debug,
        check_sqlite_in_production,
        check_system_email,
    ),
    ids=(
        "admin_email",
        "caches",
        "celery",
        "debug",
        "sqlite_in_production",
        "system_email",
    ),
)
def test_check_skips_when_app_configs_given(check_fn):
    assert check_fn(app_configs=["something"]) == []


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, DEBUG=True)
def test_check_celery_eager_debug_no_warning():
    assert check_celery(app_configs=None) == []


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, DEBUG=False)
def test_check_celery_eager_production_warns():
    errors = check_celery(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W001"
    assert errors[0].level == WARNING


@override_settings(CELERY_TASK_ALWAYS_EAGER=False, CELERY_RESULT_BACKEND=None)
def test_check_celery_no_result_backend_errors():
    errors = check_celery(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.E001"
    assert errors[0].level == ERROR


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=False, CELERY_RESULT_BACKEND="redis://localhost:6379/0"
)
def test_check_celery_broker_connection_failure():
    """When the result backend is configured but the broker is unreachable,
    a warning is emitted."""
    errors = check_celery(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W002"
    assert errors[0].level == WARNING


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}})
def test_check_sqlite_in_production_warns():
    errors = check_sqlite_in_production(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.I001"
    assert errors[0].level == INFO


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}})
def test_check_sqlite_in_production_ok_for_postgresql():
    assert check_sqlite_in_production(app_configs=None) == []


@override_settings(ADMINS=[])
def test_check_admin_email_no_admins_informs():
    errors = check_admin_email(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.I002"
    assert errors[0].level == INFO


@override_settings(ADMINS=[("Admin", "admin@example.com")])
def test_check_admin_email_configured_ok():
    assert check_admin_email(app_configs=None) == []


@override_settings(EMAIL_HOST="", EMAIL_PORT=0, MAIL_FROM="")
def test_check_system_email_missing_fields():
    errors = check_system_email(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W003"
    assert errors[0].level == WARNING
    assert "EMAIL_HOST" in errors[0].msg
    assert "EMAIL_PORT" in errors[0].msg
    assert "MAIL_FROM" in errors[0].msg


@override_settings(
    EMAIL_HOST="smtp.example.com",
    EMAIL_PORT=587,
    MAIL_FROM="noreply@example.com",
    EMAIL_USE_TLS=True,
    EMAIL_USE_SSL=True,
)
def test_check_system_email_tls_and_ssl_both_set():
    errors = check_system_email(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.E002"
    assert errors[0].level == ERROR


@pytest.mark.parametrize("mail_from", ("not-an-email", "Just A Name"))
@override_settings(
    EMAIL_HOST="smtp.example.com",
    EMAIL_PORT=587,
    EMAIL_USE_TLS=False,
    EMAIL_USE_SSL=False,
)
def test_check_system_email_invalid_mail_from(settings, mail_from):
    settings.MAIL_FROM = mail_from
    errors = check_system_email(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.E003"
    assert errors[0].level == ERROR


@pytest.mark.parametrize(
    "mail_from", ("noreply@example.com", "Custom Sender <orga@example.com>")
)
@override_settings(
    EMAIL_HOST="smtp.example.com",
    EMAIL_PORT=587,
    EMAIL_USE_TLS=False,
    EMAIL_USE_SSL=False,
)
def test_check_system_email_all_valid(settings, mail_from):
    settings.MAIL_FROM = mail_from
    assert check_system_email(app_configs=None) == []


@override_settings(HAS_REDIS=False)
def test_check_caches_no_redis_informs():
    errors = check_caches(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.I003"
    assert errors[0].level == INFO


@override_settings(HAS_REDIS=True)
def test_check_caches_redis_ok():
    assert check_caches(app_configs=None) == []


@override_settings(SITE_URL="http://example.com", DEBUG=False)
def test_check_debug_http_site_warns():
    errors = check_debug(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W004"
    assert errors[0].level == WARNING


@override_settings(SITE_URL="https://example.com", DEBUG=True)
def test_check_debug_debug_mode_errors():
    errors = check_debug(app_configs=None)

    assert len(errors) == 1
    assert errors[0].level == ERROR


@override_settings(SITE_URL="http://example.com", DEBUG=True)
def test_check_debug_http_and_debug_both_report():
    errors = check_debug(app_configs=None)

    assert len(errors) == 2
    levels = {e.level for e in errors}
    assert levels == {WARNING, ERROR}


@override_settings(SITE_URL="https://example.com", DEBUG=False)
def test_check_debug_all_ok():
    assert check_debug(app_configs=None) == []
