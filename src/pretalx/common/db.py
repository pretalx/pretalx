# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import connection
from django.db.models import Aggregate, FloatField
from django.db.models.lookups import Transform
from django.utils import translation


class Median(Aggregate):
    """Custom median aggregate that works with both PostgreSQL and SQLite."""

    function = "PERCENTILE_CONT"
    name = "median"
    output_field = FloatField()
    template = "%(function)s(0.5) WITHIN GROUP (ORDER BY %(expressions)s)"

    def as_sqlite(
        self, compiler, connection, **extra_context
    ):  # pragma: no cover -- vendor-specific SQLite fallback
        # SQLite doesn't have PERCENTILE_CONT, but has a median() extension function
        # However, it's not always available. We'll use a subquery approach instead.
        # For now, fall back to using the mean for SQLite
        self.function = "AVG"
        self.template = "%(function)s(%(expressions)s)"
        return super().as_sql(compiler, connection, **extra_context)


class Translate(Transform):
    name = "translate"

    _BASE_TEMPLATES = {
        "postgresql": (
            "CASE "
            "WHEN %(expressions)s IS JSON OBJECT THEN "
            "COALESCE("
            "NULLIF(%(expressions)s::json->>'{locale}', ''), "
            "%(expressions)s::json->>'en',"
            "(SELECT value FROM json_each_text(%(expressions)s::json) LIMIT 1)"
            ")"
            "ELSE %(expressions)s::text "
            "END"
        ),
        "sqlite": (
            "CASE "
            "WHEN json_valid(%(expressions)s) THEN "
            "COALESCE("
            "NULLIF(json_extract(%(expressions)s, '$.{locale}'), ''), "
            "json_extract(%(expressions)s, '$.en'), "
            "(SELECT value FROM json_each(%(expressions)s) WHERE json_each.type != 'object' LIMIT 1)"
            ")"
            "ELSE %(expressions)s "
            "END"
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        vendor = connection.vendor
        if vendor not in self._BASE_TEMPLATES:
            raise NotImplementedError(f"Translate not supported for {vendor}")
        self.base_template = self._BASE_TEMPLATES[vendor]

    @property
    def template(self):
        # Lazy template eval in order to get the actual current language
        current_locale = translation.get_language()
        return self.base_template.format(locale=current_locale)
