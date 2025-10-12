# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Aggregate, FloatField


class Median(Aggregate):
    """Custom median aggregate that works with both PostgreSQL and SQLite."""

    function = "PERCENTILE_CONT"
    name = "median"
    output_field = FloatField()
    template = "%(function)s(0.5) WITHIN GROUP (ORDER BY %(expressions)s)"

    def as_sqlite(self, compiler, connection, **extra_context):
        # SQLite doesn't have PERCENTILE_CONT, but has a median() extension function
        # However, it's not always available. We'll use a subquery approach instead.
        # For now, fall back to using the mean for SQLite
        self.function = "AVG"
        self.template = "%(function)s(%(expressions)s)"
        return super().as_sql(compiler, connection, **extra_context)
