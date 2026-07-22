# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import sys
import tomllib
from importlib.metadata import metadata
from pathlib import Path

import pytest
from django.core.checks import ERROR, INFO, WARNING
from django.db import OperationalError, connections
from django.test import override_settings

import pretalx.common.checks
from pretalx.common.checks import (
    check_admin_email,
    check_caches,
    check_celery,
    check_celery_required,
    check_debug,
    check_pillow_webp,
    check_postgres_version,
    check_postgres_version_deploy,
    check_python_version,
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
        check_celery_required,
        check_debug,
        check_pillow_webp,
        check_postgres_version,
        check_postgres_version_deploy,
        check_python_version,
        check_sqlite_in_production,
        check_system_email,
    ),
    ids=(
        "admin_email",
        "caches",
        "celery",
        "celery_required",
        "debug",
        "pillow_webp",
        "postgres_version",
        "postgres_version_deploy",
        "python_version",
        "sqlite_in_production",
        "system_email",
    ),
)
def test_check_skips_when_app_configs_given(check_fn):
    assert check_fn(app_configs=["something"]) == []


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_check_celery_eager_no_runtime_message():
    assert check_celery(app_configs=None) == []


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_check_celery_required_eager_errors():
    errors = check_celery_required(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.E004"
    assert errors[0].level == ERROR


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_check_celery_required_async_ok():
    assert check_celery_required(app_configs=None) == []


@override_settings(CELERY_TASK_ALWAYS_EAGER=False, CELERY_RESULT_BACKEND=None)
def test_check_celery_no_result_backend_errors():
    errors = check_celery(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.E001"
    assert errors[0].level == ERROR


@pytest.mark.slow
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


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")
@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}})
def test_check_sqlite_in_production_warns():
    errors = check_sqlite_in_production(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.I001"
    assert errors[0].level == INFO


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")
@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}})
def test_check_sqlite_in_production_ok_for_postgresql():
    assert check_sqlite_in_production(app_configs=None) == []


@override_settings(ADMINS=[])
def test_check_admin_email_no_admins_informs():
    errors = check_admin_email(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.I002"
    assert errors[0].level == INFO


@override_settings(ADMINS=["admin@example.com"])
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


def test_check_caches_probe_succeeds():
    """When ``cache.set`` succeeds (DummyCache in the test settings, a real
    reachable redis in production), the check reports no errors."""
    assert check_caches(app_configs=None) == []


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://127.0.0.1:1/0",
        }
    }
)
def test_check_caches_unreachable_redis_errors():
    errors = check_caches(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.E005"
    assert errors[0].level == ERROR


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


def test_check_pillow_webp_ok():
    """The test environment has libwebp available, so the check passes."""
    assert check_pillow_webp(app_configs=None) == []


def test_check_python_version_supported_ok():
    """The test environment always runs a supported Python version."""
    assert check_python_version(app_configs=None) == []


def test_check_python_version_too_old_warns(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))

    errors = check_python_version(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W006"
    assert errors[0].level == WARNING
    assert "3.12" in errors[0].msg


def test_requires_python_metadata_matches_pyproject():
    pyproject = Path(__file__).parents[3] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())

    assert metadata("pretalx")["Requires-Python"] == data["project"]["requires-python"]


def test_check_python_version_without_package_metadata_skips(monkeypatch):
    def raise_not_found(name):
        raise pretalx.common.checks.PackageNotFoundError(name)

    monkeypatch.setattr(pretalx.common.checks, "metadata", raise_not_found)

    assert check_python_version(app_configs=None) == []


def test_check_python_version_without_requires_python_skips(monkeypatch):
    monkeypatch.setattr(
        pretalx.common.checks, "metadata", lambda name: {"Requires-Python": None}
    )

    assert check_python_version(app_configs=None) == []


def test_check_postgres_version_matches_documentation():
    installation = (
        Path(__file__).parents[3] / "doc" / "administrator" / "installation.rst"
    )

    assert (
        f"`PostgreSQL`_ {pretalx.common.checks.POSTGRES_MIN_VERSION}+"
        in installation.read_text()
    )


def test_check_postgres_version_skips_other_databases(monkeypatch):
    monkeypatch.setattr(connections["default"], "vendor", "sqlite")

    assert check_postgres_version(app_configs=None, databases=["default"]) == []


@pytest.mark.parametrize("databases", (None, ["other"]))
def test_check_postgres_version_skips_without_default_database(databases):
    assert check_postgres_version(app_configs=None, databases=databases) == []


def test_check_postgres_version_supported_ok(monkeypatch):
    connection = connections["default"]
    monkeypatch.setattr(connection, "vendor", "postgresql")
    monkeypatch.setattr(
        connection,
        "get_database_version",
        lambda: (pretalx.common.checks.POSTGRES_MIN_VERSION, 1),
    )

    assert check_postgres_version(app_configs=None, databases=["default"]) == []


def test_check_postgres_version_too_old_warns(monkeypatch):
    connection = connections["default"]
    monkeypatch.setattr(connection, "vendor", "postgresql")
    monkeypatch.setattr(connection, "get_database_version", lambda: (15, 4))

    errors = check_postgres_version(app_configs=None, databases=["default"])

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W007"
    assert errors[0].level == WARNING
    assert "15" in errors[0].msg


def test_check_postgres_version_unreachable_database_skips(monkeypatch):
    def raise_operational_error():
        raise OperationalError("connection refused")

    connection = connections["default"]
    monkeypatch.setattr(connection, "vendor", "postgresql")
    monkeypatch.setattr(connection, "get_database_version", raise_operational_error)

    assert check_postgres_version(app_configs=None, databases=["default"]) == []


def test_check_postgres_version_deploy_reports_same_messages(monkeypatch):
    connection = connections["default"]
    monkeypatch.setattr(connection, "vendor", "postgresql")
    monkeypatch.setattr(connection, "get_database_version", lambda: (15, 4))

    errors = check_postgres_version_deploy(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W007"


def test_check_pillow_webp_missing_warns(monkeypatch):
    from PIL import features  # noqa: PLC0415 -- features is mocked for this test only

    monkeypatch.setattr(features, "check", lambda _: False)

    errors = check_pillow_webp(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W005"
    assert errors[0].level == WARNING
