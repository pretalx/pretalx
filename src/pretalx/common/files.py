# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

# Canonical allow-lists of uploadable file types, shared by the web form layer
# (pretalx.common.forms.fields) and the API upload layer
# (pretalx.api.serializers.fields). Restricting uploads to these known-safe
# types keeps user-uploaded files from being served same-origin as text/html,
# image/svg+xml, etc., which would otherwise enable XSS.
#
# Each mapping is content-type -> list of permitted file extensions (lower-cased,
# with a leading dot). The API enforces the browser-reported content type
# against these keys; the form layer enforces the uploaded file's extension
# against the extension set derived via extensions_from_types().
IMAGE_UPLOAD_TYPES = {
    "image/png": [".png"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/gif": [".gif"],
    "image/webp": [".webp"],
}
DOCUMENT_UPLOAD_TYPES = {
    # All image types are also valid documents, so spread them in rather than
    # repeating them (and risk the two lists drifting apart).
    **IMAGE_UPLOAD_TYPES,
    "image/bmp": [".bmp"],
    "image/tiff": [".tif", ".tiff"],
    "application/pdf": [".pdf"],
    "text/plain": [".txt"],
    "text/csv": [".csv"],
    "application/zip": [".zip"],
    "application/msword": [".doc"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
        ".docx"
    ],
    "application/rtf": [".rtf"],
    "application/vnd.ms-powerpoint": [".ppt"],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": [
        ".pptx"
    ],
    "application/vnd.ms-excel": [".xls"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    "application/vnd.oasis.opendocument.text": [".odt"],
    "application/vnd.oasis.opendocument.spreadsheet": [".ods"],
    "application/vnd.oasis.opendocument.presentation": [".odp"],
}


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
