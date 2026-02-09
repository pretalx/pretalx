# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: fkusei

import logging

from django.core.files import File
from django.core.files.temp import NamedTemporaryFile
from django.dispatch import receiver
from django.utils.timezone import now
from requests import get

from pretalx.celery_app import app
from pretalx.common.signals import minimum_interval, periodic_task
from pretalx.person.models import UserApiToken
from pretalx.person.models.picture import ProfilePicture

logger = logging.getLogger(__name__)


@app.task(name="pretalx.person.gravatar_cache")
def gravatar_cache(profile_picture_id: int):
    picture = (
        ProfilePicture.objects.filter(pk=profile_picture_id, get_gravatar=True)
        .select_related("user")
        .first()
    )

    if not picture:
        return

    response = get(
        f"https://www.gravatar.com/avatar/{picture.gravatar_parameter}?s=512",
        timeout=10,
    )

    logger.info(
        "gravatar returned http %s when getting avatar for user %s",
        response.status_code,
        user.name,
    )

    if 400 <= response.status_code <= 499:
        picture.delete()
        return
    if response.status_code != 200:
        return

    with NamedTemporaryFile(delete=True) as tmp_img:
        for chunk in response:
            tmp_img.write(chunk)
        tmp_img.flush()

        content_type = response.headers.get("Content-Type")
        if content_type == "image/png":
            extension = "png"
        elif content_type == "image/gif":
            extension = "gif"
        else:
            extension = "jpg"

        picture.get_gravatar = False
        picture.save(update_fields=["get_gravatar"])
        picture.avatar.save(f"{picture.gravatar_parameter}.{extension}", File(tmp_img))
        logger.info("set avatar for user %s to %s", picture.user.name, picture.avatar.url)

    picture.process_image("avatar", generate_thumbnail=True)


@receiver(periodic_task)
def refetch_gravatars(sender, **kwargs):
    pictures_with_gravatar = ProfilePicture.objects.filter(get_gravatar=True)

    for picture in pictures_with_gravatar:
        gravatar_cache.apply_async(args=(picture.pk,), ignore_result=True)


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=60)
def run_update_check(sender, **kwargs):
    UserApiToken.objects.filter(expires__lt=now()).delete()
