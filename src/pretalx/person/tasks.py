import logging

from django.core.files import File
from django.core.files.temp import NamedTemporaryFile
from requests import get

from pretalx.celery_app import app
from pretalx.person.models.user import User

logger = logging.getLogger(__name__)


@app.task()
def gravatar_cache(*args, **kwargs):
    users_with_gravatar = User.objects.filter(get_gravatar=True)

    for user in users_with_gravatar:
        r = get(f"https://www.gravatar.com/avatar/{user.gravatar_parameter}?s=512")

        logger.info(
            f"gravatar returned http {r.status_code} when getting avatar for user {user.name}"
        )

        if 400 <= r.status_code <= 499:
            # avatar not found.
            user.get_gravatar = False
            user.save()
            continue
        elif r.status_code != 200:
            continue

        with NamedTemporaryFile(delete=True) as tmp_img:
            for chunk in r:
                tmp_img.write(chunk)
            tmp_img.flush()

            user.avatar.save(f"{user.gravatar_parameter}.jpg", File(tmp_img))
            user.get_gravatar = False
            user.save()

            logger.info(f"set avatar for user {user.name} to {user.avatar.url}")
