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


@pytest.mark.parametrize(
    ("eager", "expected"),
    ((True, [("pretalx.E004", ERROR)]), (False, [])),
    ids=("eager_errors", "async_ok"),
)
def test_check_celery_required(settings, eager, expected):
    settings.CELERY_TASK_ALWAYS_EAGER = eager

    errors = check_celery_required(app_configs=None)

    assert [(e.id, e.level) for e in errors] == expected


@pytest.mark.parametrize(
    ("overrides", "expected"),
    (
        ({"CELERY_TASK_ALWAYS_EAGER": True}, []),
        (
            {"CELERY_TASK_ALWAYS_EAGER": False, "CELERY_RESULT_BACKEND": None},
            [("pretalx.E001", ERROR)],
        ),
    ),
    ids=("eager_no_runtime_message", "no_result_backend_errors"),
)
def test_check_celery(settings, overrides, expected):
    for key, value in overrides.items():
        setattr(settings, key, value)

    errors = check_celery(app_configs=None)

    assert [(e.id, e.level) for e in errors] == expected


@pytest.mark.slow
@override_settings(
    CELERY_TASK_ALWAYS_EAGER=False, CELERY_RESULT_BACKEND="redis://localhost:6379/0"
)
def test_check_celery_broker_connection_failure():
    errors = check_celery(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W002"
    assert errors[0].level == WARNING


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")
@pytest.mark.parametrize(
    ("engine", "expected"),
    (
        ("django.db.backends.sqlite3", [("pretalx.I001", INFO)]),
        ("django.db.backends.postgresql", []),
    ),
    ids=("sqlite_informs", "postgresql_ok"),
)
def test_check_sqlite_in_production(settings, engine, expected):
    settings.DATABASES = {"default": {"ENGINE": engine}}

    errors = check_sqlite_in_production(app_configs=None)

    assert [(e.id, e.level) for e in errors] == expected


@pytest.mark.parametrize(
    ("admins", "expected"),
    (([], [("pretalx.I002", INFO)]), (["admin@example.com"], [])),
    ids=("no_admins_informs", "configured_ok"),
)
def test_check_admin_email(settings, admins, expected):
    settings.ADMINS = admins

    errors = check_admin_email(app_configs=None)

    assert [(e.id, e.level) for e in errors] == expected


@override_settings(
    MAILERS={"default": {"OPTIONS": {"host": "", "port": 0}}}, MAIL_FROM=""
)
def test_check_system_email_missing_fields():
    errors = check_system_email(app_configs=None)

    assert len(errors) == 1
    assert errors[0].id == "pretalx.W003"
    assert errors[0].level == WARNING
    assert "mail.host" in errors[0].msg
    assert "mail.port" in errors[0].msg
    assert "mail.from" in errors[0].msg


SMTP = {"default": {"OPTIONS": {"host": "smtp.example.com", "port": 587}}}


@pytest.mark.parametrize(
    ("mailers", "mail_from", "expected"),
    (
        (
            {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}},
            "noreply@example.com",
            [],
        ),
        ({}, "noreply@example.com", []),
        (
            {
                "default": {
                    "OPTIONS": {
                        "host": "smtp.example.com",
                        "port": 587,
                        "use_tls": True,
                        "use_ssl": True,
                    }
                }
            },
            "noreply@example.com",
            [("pretalx.E002", ERROR)],
        ),
        (SMTP, "not-an-email", [("pretalx.E003", ERROR)]),
        (SMTP, "Just A Name", [("pretalx.E003", ERROR)]),
        (SMTP, "noreply@example.com", []),
        (SMTP, "Custom Sender <orga@example.com>", []),
    ),
    ids=(
        "non_smtp_backend_needs_no_host",
        "no_default_mailer_needs_no_host",
        "tls_and_ssl_both_set",
        "invalid_mail_from",
        "mail_from_without_address",
        "valid",
        "valid_with_name",
    ),
)
def test_check_system_email(settings, mailers, mail_from, expected):
    settings.MAILERS = mailers
    settings.MAIL_FROM = mail_from

    errors = check_system_email(app_configs=None)

    assert [(e.id, e.level) for e in errors] == expected


def test_check_caches_probe_succeeds():
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


@pytest.mark.parametrize(
    ("site_url", "debug", "expected"),
    (
        ("http://example.com", False, [("pretalx.W004", WARNING)]),
        ("https://example.com", True, [("pretalx.W004", ERROR)]),
        (
            "http://example.com",
            True,
            [("pretalx.W004", WARNING), ("pretalx.W004", ERROR)],
        ),
        ("https://example.com", False, []),
    ),
    ids=("http_warns", "debug_errors", "both_report", "all_ok"),
)
def test_check_debug(settings, site_url, debug, expected):
    settings.SITE_URL = site_url
    settings.DEBUG = debug

    errors = check_debug(app_configs=None)

    assert [(e.id, e.level) for e in errors] == expected


def test_check_pillow_webp_ok():
    assert check_pillow_webp(app_configs=None) == []


def test_check_python_version_supported_ok():
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


def _raise_not_found(name):
    raise pretalx.common.checks.PackageNotFoundError(name)


@pytest.mark.parametrize(
    "metadata_lookup",
    (_raise_not_found, lambda name: {"Requires-Python": None}),
    ids=("without_package_metadata", "without_requires_python"),
)
def test_check_python_version_skips_without_requirement(monkeypatch, metadata_lookup):
    monkeypatch.setattr(pretalx.common.checks, "metadata", metadata_lookup)

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


def _raise_operational_error():
    raise OperationalError("connection refused")


@pytest.mark.parametrize(
    ("get_database_version", "expected"),
    (
        (lambda: (pretalx.common.checks.POSTGRES_MIN_VERSION, 1), []),
        (lambda: (15, 4), [("pretalx.W007", WARNING)]),
        (_raise_operational_error, []),
    ),
    ids=("supported_ok", "too_old_warns", "unreachable_skips"),
)
def test_check_postgres_version(monkeypatch, get_database_version, expected):
    connection = connections["default"]
    monkeypatch.setattr(connection, "vendor", "postgresql")
    monkeypatch.setattr(connection, "get_database_version", get_database_version)

    errors = check_postgres_version(app_configs=None, databases=["default"])

    assert [(e.id, e.level) for e in errors] == expected
    assert all("15" in e.msg for e in errors)


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
