# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from django.db import models

from pretalx.common.models.mixins import TimestampedModel


class UserEventPreferences(TimestampedModel, models.Model):
    user = models.ForeignKey(
        to="User",
        on_delete=models.CASCADE,
        related_name="event_preferences",
    )
    event = models.ForeignKey(
        to="event.Event",
        on_delete=models.CASCADE,
        related_name="user_preferences",
    )
    preferences = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        unique_together = (("user", "event"),)

    def __str__(self):
        return f"Preferences for {self.user} and {self.event}"

    def _retrieve_parent(self, path, create=False):
        """Retrieve the parent dictionary for a given dotted path.

        Returns (parent_dict, final_key) tuple.
        If create=True, intermediate dicts will be created.
        Raises TypeError if encountering non-dict intermediate values when create=True.
        """
        keys = path.split(".")
        value = self.preferences

        for i, key in enumerate(keys[:-1]):
            if key in value and type(value[key]) is dict:
                value = value[key]
            elif key in value:
                if create:
                    err_path = ".".join(keys[: i + 1])
                    raise TypeError(
                        f"Key '{err_path}' is a leaf node; cannot assign new keys"
                    )
                else:
                    return None, keys[-1]
            else:
                if create:
                    value = value.setdefault(key, {})
                else:
                    return None, keys[-1]

        return value, keys[-1]

    def get(self, path):
        """Retrieve a preference parameter specified by its dotted path.

        For example, ``preferences.get('tables.SubmissionTable.columns')`` returns
        ``self.preferences["tables"]["SubmissionTable"]["columns"]``.
        Returns ``None`` if the key does not exist.
        """
        with suppress(TypeError, KeyError, AttributeError):
            parent, key = self._retrieve_parent(path)
            return parent.get(key)

    def set(self, path, value, commit=False):
        """Define or overwrite a preference parameter.

        Usage: ``preferences.set('tables.SubmissionTable.columns', ['title', 'state'])``

        Leaf nodes CAN be overridden with dicts, changing the data structure. Setting
        a branch node to a new dict will override the branch, NOT merge it.
        Branch nodes cannot be overwritten as single values, the existing key must
        first be cleared.
        """
        parent, key = self._retrieve_parent(path, create=True)

        # Set a key based on the last item in the path.
        # Raise TypeError if attempting to overwrite a non-leaf node.
        if (
            key in parent
            and isinstance(parent[key], dict)
            and not isinstance(value, dict)
        ):
            raise TypeError(
                f"Key '{path}' is a dictionary; cannot assign a non-dictionary value"
            )
        else:
            parent[key] = value

        if commit:
            self.save()

    def clear(self, path, commit=False):
        """Delete a preference parameter specified by its dotted path.

        The key and any child keys will be deleted. Invalid keys will be ignored
        silently.
        """
        parent, key = self._retrieve_parent(path, create=False)

        if isinstance(parent, dict):
            parent.pop(key, None)

        if commit:
            self.save()
