# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.formats import date_format
from django.utils.timezone import get_current_timezone


class MinDateValidator(MinValueValidator):
    def __call__(self, value):
        try:
            return super().__call__(value)
        except forms.ValidationError as e:
            e.params["limit_value"] = date_format(
                e.params["limit_value"], "SHORT_DATE_FORMAT"
            )
            raise


class MinDateTimeValidator(MinValueValidator):
    def __call__(self, value):
        try:
            return super().__call__(value)
        except forms.ValidationError as e:
            e.params["limit_value"] = date_format(
                e.params["limit_value"].astimezone(get_current_timezone()),
                "SHORT_DATETIME_FORMAT",
            )
            raise


class MaxDateValidator(MaxValueValidator):
    def __call__(self, value):
        try:
            return super().__call__(value)
        except forms.ValidationError as e:
            e.params["limit_value"] = date_format(
                e.params["limit_value"], "SHORT_DATE_FORMAT"
            )
            raise


class MaxDateTimeValidator(MaxValueValidator):
    def __call__(self, value):
        try:
            return super().__call__(value)
        except forms.ValidationError as e:
            e.params["limit_value"] = date_format(
                e.params["limit_value"].astimezone(get_current_timezone()),
                "SHORT_DATETIME_FORMAT",
            )
            raise
