# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

from contextlib import suppress
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.urls import resolve, reverse
from urlman import Urls


def get_base_url(event=None, url=None):
    if url and url.startswith("/orga"):
        return settings.SITE_URL
    if event:
        if event.display_settings["html_export_url"] and url:
            with suppress(Exception):
                resolved = resolve(url)
                if "agenda" in resolved.namespaces:
                    return event.display_settings["html_export_url"]
        if event.custom_domain:
            return event.custom_domain
    return settings.SITE_URL


def build_absolute_uri(urlname, event=None, args=None, kwargs=None):
    url = get_base_url(event)
    return urljoin(url, reverse(urlname, args=args, kwargs=kwargs))


def get_netloc(event, url=None):
    return urlparse(get_base_url(event, url)).netloc


class EventUrls(Urls):
    def get_hostname(self, url):
        return get_netloc(self.instance.event, url)

    def get_scheme(self, url):
        url = get_base_url(self.instance.event, url)
        return urlparse(url).scheme
