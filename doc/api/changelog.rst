.. SPDX-FileCopyrightText: 2025-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _`api-changelog`:

API Changelog
=============

The pretalx API is versioned – see :ref:`api-versioning` for the full explanation.
The short version is that the pretalx API version change with a new pretalx release,
but it does not have to change, as there may be no (or no breaking) API changes in
a release.

Minor changes that don’t result in a new API version will not be listed here,
as this page is meant to support you in updating your API tokens to a new
version. To see all API changes in a pretalx release, please refer to the
general :ref:`changelog`.

If you want to test if your existing API client can deal with a new API version
before upgrading your API token, you can send a ``Pretalx-Version`` header with
your requests to temporarily change the API version you’re using.

v2 (unreleased)
----------------

These changes can currently be accessed using the development preview by sending
the ``Pretalx-Version: v-next`` header with your requests (see
:ref:`api-versioning`).

The ``/access-codes/`` endpoint fields ``track`` and ``submission_type`` have been
renamed to ``tracks`` and ``submission_types``, and now return arrays of IDs instead
of a single ID, as access codes can now be associated with multiple tracks and
session types.

.. warning::

   If you are using API v1, the ``/access-codes/`` endpoint will continue to use the
   old singular field names (``track``, ``submission_type``), but will only show the
   **first** associated track or session type. If your access codes use multiple tracks
   or session types, this data will be incomplete. Upgrade to API v2 once released to
   see all associated tracks and session types.

v1 (2025.1.0)
-------------

Before the API versioning outlined here, the API was read-only, and also inconsistent in
many ways. The v1 API released in pretalx v2025.1.0 makes sweeping changes to the API,
introduces the new auth tokens, allows organisers to use the writable API.
The changes are too numerous to list here – for example, related objects were included
in many places by name (e.g. a room name) instead of a reliable and fixed ID.
There was no option to expand nested resources, to coerce multi-lingual strings into
simple strings, and no versioning at all.

Old API tokens will continue to work and will continue to use the legacy API for the most
part. Any write actions (creating and updating objects) will require you to create a
new API token or to update your existing token to v1.

The only breaking change knowingly introduced in the v1 release concerns the
schedule endpoint, which has changed completely. As it was an undocumented
endpoint that we never advertised, the advantages of a rewrite outweighed the
maintenance burden of retaining the old endpoint.

Another change to the API is in the pagination mechanism: The legacy API used
pagination with a ``limit`` and ``offset`` parameter, whereas as of API v1,
pretalx uses a ``page`` parameter (with an optional ``page_size``). However,
the old pagination style will continue to work for as long as the legacy API is
still active. We have limited the page size to 50 now, though, as the
previously unlimited page size was already resource intensive, and even more so
with the more capable (but more involved) new API.
If you have always used the supplied ``next`` and ``previous`` URL fields in
paginated responses for navigation, this change should not affect you, as these
fields are still provided.
