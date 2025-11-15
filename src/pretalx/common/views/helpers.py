# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import FileResponse, Http404


def is_form_bound(request, form_name, form_param="form"):
    return request.method == "POST" and request.POST.get(form_param) == form_name


def get_static(
    path, content_type, as_attachment=False, filename=None
):  # pragma: no cover
    try:
        return FileResponse(
            staticfiles_storage.open(path),
            content_type=content_type,
            as_attachment=as_attachment,
            filename=filename,
        )
    except Exception:
        raise Http404()


def is_htmx(request):
    return bool(request.headers.get("HX-Request"))
