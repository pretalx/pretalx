# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_lazy as _

# Allow-lists of uploadable file types, shared by the frontend and API.
FILE_TYPE_GROUPS = {
    "image/*": {
        "image/png": [".png"],
        "image/jpeg": [".jpg", ".jpeg"],
        "image/gif": [".gif"],
        "image/webp": [".webp"],
    },
    "document/*": {
        "application/pdf": [".pdf"],
        "text/plain": [".txt"],
        "application/rtf": [".rtf"],
        "application/msword": [".doc"],
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
            ".docx"
        ],
        "application/vnd.oasis.opendocument.text": [".odt"],
    },
    "presentation/*": {
        "application/vnd.ms-powerpoint": [".ppt"],
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": [
            ".pptx"
        ],
        "application/vnd.oasis.opendocument.presentation": [".odp"],
    },
    "spreadsheet/*": {
        "text/csv": [".csv"],
        "application/vnd.ms-excel": [".xls"],
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
        "application/vnd.oasis.opendocument.spreadsheet": [".ods"],
    },
    "archive/*": {"application/zip": [".zip"]},
}
FILE_TYPE_GROUP_LABELS = {
    "image/*": _("Images"),
    "document/*": _("Documents"),
    "presentation/*": _("Presentations"),
    "spreadsheet/*": _("Spreadsheets"),
    "archive/*": _("Archives"),
}
IMAGE_UPLOAD_TYPES = FILE_TYPE_GROUPS["image/*"]
DOCUMENT_UPLOAD_TYPES = {
    content_type: extensions
    for group in FILE_TYPE_GROUPS.values()
    for content_type, extensions in group.items()
}
FILE_TYPE_TOKENS = [*FILE_TYPE_GROUPS, *DOCUMENT_UPLOAD_TYPES]


def extensions_from_types(upload_types):
    """Derive a form ``extensions`` mapping from a content-type allow-list.

    Maps each permitted file extension to the values fed into a file input's
    ``accept`` attribute as a client-side hint: its content type and the
    extension itself. The keys (extensions) are what the form layer validates
    server-side; see pretalx.common.forms.fields.ExtensionFileInput.validate.
    """
    extensions = {}
    for content_type, exts in upload_types.items():
        for ext in exts:
            extensions[ext] = [content_type, ext]
    return extensions


IMAGE_EXTENSIONS = extensions_from_types(IMAGE_UPLOAD_TYPES)
FILE_EXTENSIONS = extensions_from_types(DOCUMENT_UPLOAD_TYPES)


def resolve_file_types(tokens):
    if not tokens:
        return DOCUMENT_UPLOAD_TYPES
    content_types = set()
    for token in tokens:
        if token in FILE_TYPE_GROUPS:
            content_types.update(FILE_TYPE_GROUPS[token])
        elif token in DOCUMENT_UPLOAD_TYPES:
            content_types.add(token)
        else:
            raise KeyError(token)
    return {
        content_type: extensions
        for content_type, extensions in DOCUMENT_UPLOAD_TYPES.items()
        if content_type in content_types
    }


def is_image_only(upload_types):
    return upload_types.keys() <= IMAGE_UPLOAD_TYPES.keys()
