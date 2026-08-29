# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress
from pathlib import Path

from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.common.models.managers import ScopedManager
from pretalx.common.models.mixins import PretalxModel
from pretalx.common.text.path import hashed_path, safe_filename
from pretalx.common.urls import get_base_url
from pretalx.submission.validators.resource import validate_resource_link_xor_file


def resource_path(instance, filename):
    return hashed_path(
        filename,
        target_name=safe_filename(Path(filename).stem),
        upload_dir=f"{instance.submission.event.slug}/submissions/{instance.submission.code}/resources/",
    )


def active_resource_filter(prefix: str = "") -> models.Q:
    resource = f"{prefix}resource"
    link = f"{prefix}link"
    return models.Q(  # either the resource exists
        models.Q(**{f"{resource}__isnull": False})
        & ~models.Q(**{resource: ""})
        & ~models.Q(**{resource: "None"})
    ) | models.Q(  # or the link exists
        models.Q(**{f"{link}__isnull": False}) & ~models.Q(**{link: ""})
    )


class ResourceQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active_resource_filter())


class ResourceManager(models.Manager.from_queryset(ResourceQuerySet)):
    pass


class Resource(PretalxModel):
    """Resources are file uploads or links belonging to a
    :class:`~pretalx.submission.models.submission.Submission`."""

    log_prefix = "pretalx.submission.resource"

    submission = models.ForeignKey(
        to="submission.Submission", related_name="resources", on_delete=models.PROTECT
    )
    resource = models.FileField(
        verbose_name=_("File"), upload_to=resource_path, null=True, blank=True
    )
    link = models.URLField(max_length=400, verbose_name=_("URL"), null=True, blank=True)
    description = models.CharField(max_length=1000, verbose_name=_("Description"))
    is_public = models.BooleanField(
        default=True, verbose_name=_("Publicly visible resource")
    )

    objects = ScopedManager(event="submission__event", _manager_class=ResourceManager)

    class Meta:
        verbose_name_plural = _("Resources")

    def __str__(self):
        return f"Resource(submission_id={self.submission_id}, description={self.description})"

    def clean(self):
        super().clean()
        validate_resource_link_xor_file(link=self.link, resource=self.resource)

    @cached_property
    def url(self):
        if self.link:
            return self.link
        with suppress(ValueError):
            base_url = get_base_url(self.submission.event)
            return base_url + self.resource.url

    @cached_property
    def size(self):
        with suppress(OSError, ValueError):
            return self.resource.size

    @cached_property
    def filename(self):
        with suppress(ValueError):
            if self.resource:
                return Path(self.resource.name).name

    @property
    def as_markdown(self):
        """Markdown line summarising this resource, used for log diffs on the
        parent submission."""
        if self.link:
            return (
                f"[{self.description}]({self.link})" if self.description else self.link
            )
        if label := self.description or self.filename:
            return f"{_('File')}: {label}"
        return None
