# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, models, transaction
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager, scopes_disabled
from i18nfield.strings import LazyI18nString
from rules.contrib.models import RulesModelBase, RulesModelMixin

from pretalx.common.text.serialize import json_roundtrip

SENSITIVE_KEYS = ["password", "secret", "api_key"]


class TimestampedModel(models.Model):
    created = models.DateTimeField(
        verbose_name=_("Created"), auto_now_add=True, blank=True, null=True
    )
    updated = models.DateTimeField(
        verbose_name=_("Updated"), auto_now=True, blank=True, null=True
    )

    class Meta:
        abstract = True


class LogMixin:
    log_prefix = None
    log_parent = None

    def log_action(
        self,
        action,
        data=None,
        person=None,
        orga=False,
        content_object=None,
        old_data=None,
        new_data=None,
    ):
        if not self.pk or not isinstance(self.pk, int):
            return

        if action.startswith("."):
            if self.log_prefix:
                action = f"{self.log_prefix}{action}"
            else:
                return

        if old_data is not None or new_data is not None:
            changes = self._compute_changes(old_data, new_data)
            if not changes and not data:
                return
            if changes:
                if data is None:
                    data = {}
                data["changes"] = changes

        if data:
            if not isinstance(data, dict):
                raise TypeError(
                    f"Logged data should always be a dictionary, not {type(data)}."
                )
            for key in data:
                if any(sensitive_key in key for sensitive_key in SENSITIVE_KEYS):
                    data[key] = "********" if data[key] else data[key]
            data = json_roundtrip(data)

        from pretalx.common.models import ActivityLog  # noqa: PLC0415

        return ActivityLog.objects.create(
            event=getattr(self, "event", None),
            person=person,
            content_object=content_object or self,
            action_type=action,
            data=data,
            is_orga_action=orga,
        )

    def _compute_changes(self, old_data, new_data):
        old_data = old_data or {}
        new_data = new_data or {}
        all_keys = set(old_data.keys()) | set(new_data.keys())
        changes = {}

        for key in all_keys:
            old_value = old_data.get(key)
            new_value = new_data.get(key)
            if (old_value or new_value) and (old_value != new_value):
                changes[key] = {"old": old_value, "new": new_value}

        return changes

    def get_instance_data(self):
        """Get a dictionary of field values for this instance.

        Used for change tracking in log_action. Excludes auto-updated
        fields like timestamps and sensitive data.
        Does not handle many-to-many fields.
        """
        excluded_fields = {
            "created",
            "updated",
            "is_active",
            "last_login",
            "user",
            "event",
            "code",
        }
        data = {}

        for field in self._meta.fields:
            if (
                field.name in excluded_fields
                or field.name in SENSITIVE_KEYS
                or "thumbnail" in field.name
            ):
                continue

            if getattr(field, "auto_now", False) or getattr(
                field, "auto_now_add", False
            ):
                continue

            value = getattr(self, field.name, None)

            if isinstance(field, models.ForeignKey):
                data[field.name] = value.pk if value else None
            elif isinstance(field, models.FileField):
                data[field.name] = value.name if value else None
            elif isinstance(field, models.UUIDField):
                data[field.name] = str(value) if value else None
            elif isinstance(value, LazyI18nString):
                if isinstance(getattr(value, "data", None), dict):
                    data[field.name] = {k: v for k, v in value.data.items() if v}
                else:
                    data[field.name] = str(value)
            else:
                data[field.name] = json_roundtrip(value)
        return data

    def logged_actions(self):
        from pretalx.common.models import ActivityLog  # noqa: PLC0415

        return (
            ActivityLog.objects.filter(
                content_type=ContentType.objects.get_for_model(type(self)),
                object_id=self.pk,
            )
            .select_related("event", "person")
            .prefetch_related("content_object")
        )

    def delete(self, *args, log_kwargs=None, skip_log=False, **kwargs):
        parent = self.log_parent
        result = super().delete(*args, **kwargs)
        if (
            not skip_log
            and parent
            and getattr(parent, "log_action", None)
            and self.log_prefix
        ):
            log_kwargs = log_kwargs or {}
            parent.log_action(f"{self.log_prefix}.delete", **log_kwargs)
        return result


class FileCleanupMixin:
    """Deletes all uploaded files when object is deleted."""

    @cached_property
    def _file_fields(self):
        return [
            field.name
            for field in self._meta.fields
            if isinstance(field, models.FileField)
        ]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if not self.pk or (
            update_fields and not set(self._file_fields) & set(update_fields)
        ):
            return super().save(*args, **kwargs)

        try:
            pre_save_instance = self.__class__.objects.get(pk=self.pk)
        except ObjectDoesNotExist:
            return super().save(*args, **kwargs)

        # Collect old file paths before save
        old_files = {}
        for field in self._file_fields:
            if old_value := getattr(pre_save_instance, field):
                new_value = getattr(self, field)
                if new_value and old_value.path != new_value.path:
                    old_files[field] = old_value.path

        result = super().save(*args, **kwargs)

        # Schedule cleanup after save, so the database has the new path when
        # the task runs (important for eager mode).
        for field, path in old_files.items():
            from pretalx.common.tasks import task_cleanup_file  # noqa: PLC0415

            task_cleanup_file.apply_async(
                kwargs={
                    "model": str(self._meta.model_name.capitalize()),
                    "pk": self.pk,
                    "field": field,
                    "path": path,
                },
                countdown=10,
            )
        return result

    def _delete_files(self):
        for field in self._file_fields:
            value = getattr(self, field, None)
            if value:
                with suppress(Exception):
                    value.delete(save=False)

    def delete(self, *args, **kwargs):
        self._delete_files()
        return super().delete(*args, **kwargs)

    def process_image(self, field, generate_thumbnail=False):
        from pretalx.common.tasks import task_process_image  # noqa: PLC0415

        task_process_image.apply_async(
            kwargs={
                "field": field,
                "model": str(self._meta.model_name.capitalize()),
                "pk": self.pk,
                "generate_thumbnail": generate_thumbnail,
            },
            countdown=10,
        )


class PretalxModel(
    LogMixin,
    TimestampedModel,
    FileCleanupMixin,
    RulesModelMixin,
    models.Model,
    metaclass=RulesModelBase,
):
    """
    Base model for most pretalx models. Suitable for plugins.
    """

    objects = ScopedManager(event="event")

    class Meta:
        abstract = True


class GenerateCode:
    """Generates a random code on first save.

    Omits some character pairs because they are hard to
    read/differentiate: 1/I, O/0, 2/Z, 4/A, 5/S, 6/G.

    Configure via class attributes:
    - code_length: Length of generated code (default: 6)
    - code_charset: Characters to use (default: ABCDEFGHJKLMNPQRSTUVWXYZ3789)
    - code_property: Field name to store code (default: "code")
    - code_scope: Tuple of field names for scoped uniqueness (default: () for global)
      Example: ("event",) or ("event", "question")
    """

    code_length = 6
    code_charset = list("ABCDEFGHJKLMNPQRSTUVWXYZ3789")
    code_property = "code"
    code_scope = ()

    @classmethod
    def generate_code(cls, length=None):
        length = length or cls.code_length
        return get_random_string(length=length, allowed_chars=cls.code_charset)

    @classmethod
    def generate_unique_codes(cls, count, length=None, **scope_kwargs):
        """Generate `count` unique codes efficiently for bulk operations.

        Args:
            count: Number of unique codes to generate
            length: Code length (uses code_length if not specified)
            **scope_kwargs: Scope field values (e.g., question=question_instance)

        Returns:
            List of unique code strings
        """
        length = length or cls.code_length

        # Build filter for existing codes in scope
        filter_kwargs = {}
        for field in cls.code_scope:
            if field not in scope_kwargs:
                raise ValueError(f"Missing required scope field: {field}")
            filter_kwargs[field] = scope_kwargs[field]

        # Fetch existing codes (1 query)
        with scopes_disabled():
            existing_codes = set(
                cls.objects.filter(**filter_kwargs).values_list(
                    cls.code_property, flat=True
                )
            )

        # Generate unique codes without additional queries
        new_codes = []
        all_codes = {c.upper() for c in existing_codes}  # Case-insensitive

        while len(new_codes) < count:
            code = cls.generate_code(length=length)
            if code.upper() not in all_codes:
                new_codes.append(code)
                all_codes.add(code.upper())

        return new_codes

    def assign_code(self, length=None):
        length = length or self.code_length
        while True:
            code = self.generate_code(length=length)
            filter_kwargs = {f"{self.code_property}__iexact": code}
            for field in self.code_scope:
                filter_kwargs[field] = getattr(self, field)
            with scopes_disabled():
                if not self.__class__.objects.filter(**filter_kwargs).exists():
                    setattr(self, self.code_property, code)
                    return

    def save(self, *args, **kwargs):
        if getattr(self, self.code_property, None):
            return super().save(*args, **kwargs)

        # Auto-generate code with retry loop to handle unlikely race conditions
        if "update_fields" in kwargs:
            kwargs["update_fields"] = {self.code_property}.union(
                kwargs["update_fields"]
            )
        for attempt in range(3):
            self.assign_code()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if attempt == 2:
                    raise
                setattr(self, self.code_property, None)


class OrderedModel:
    """Provides methods to move a model up and down in a queryset.

    Implement the `get_order_queryset` method as a classmethod or staticmethod
    to provide the queryset to order.
    """

    order_field = "position"
    order_up_url = "urls.up"
    order_down_url = "urls.down"

    @staticmethod
    def get_order_queryset(**kwargs):
        raise NotImplementedError

    def _get_attribute(self, attribute):
        result = self
        for part in attribute.split("."):
            result = getattr(result, part)
        return result

    def get_down_url(self):
        return self._get_attribute(self.order_down_url)

    def get_up_url(self):
        return self._get_attribute(self.order_up_url)

    def up(self):
        return self._move(up=True)

    def down(self):
        return self._move(up=False)

    @property
    def order_queryset(self):
        return self.get_order_queryset(event=self.event)

    def move(self, up=True):
        queryset = list(self.order_queryset.order_by(self.order_field))
        index = queryset.index(self)
        if index != 0 and up:
            queryset[index - 1], queryset[index] = queryset[index], queryset[index - 1]
        elif index != len(queryset) - 1 and not up:
            queryset[index + 1], queryset[index] = queryset[index], queryset[index + 1]

        for index, element in enumerate(queryset):
            if element.position != index:
                element.position = index
                element.save()

    move.alters_data = True
