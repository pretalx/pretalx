# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.conf import settings
from django.db import models
from django_scopes import ScopedManager as BaseScopedManager


class FetchModeMixin:
    # In development and testing, we raise on lazy related-object fetched
    # so we add the corresponding guards or add explicit exceptions.
    # Never active in prod.
    def get_queryset(self):
        qs = super().get_queryset()
        if settings.FETCH_MODE_RAISE:
            qs = qs.fetch_mode(models.FETCH_RAISE)
        return qs


class PretalxManager(FetchModeMixin, models.Manager):
    pass


_wrapped_classes = {}


def wrap_manager_class(manager_class):
    if issubclass(manager_class, FetchModeMixin):
        return manager_class
    if manager_class not in _wrapped_classes:
        _wrapped_classes[manager_class] = type(
            manager_class.__name__, (FetchModeMixin, manager_class), {}
        )
    return _wrapped_classes[manager_class]


def ScopedManager(_manager_class=models.Manager, **scopes):  # noqa: N802 -- django_scopes API
    return BaseScopedManager(
        _manager_class=wrap_manager_class(_manager_class), **scopes
    )
