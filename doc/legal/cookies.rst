.. SPDX-FileCopyrightText: 2025-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

Cookie usage
============

pretalx only sets technically necessary cookies – no tracking, no third-party cookies, no consent banner required.

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Name
     - Content
     - Lifetime
     - Reason
   * - ``pretalx_csrftoken``
     - Random ID
     - 365 days
     - Protects form submissions against `CSRF attacks <https://en.wikipedia.org/wiki/Cross-site_request_forgery>`_.
   * - ``pretalx_session``
     - Session ID
     - 14 days
     - Keeps you logged in and maintains state across page loads. Only set when needed.
   * - ``pretalx_language``
     - Language code
     - 10 years
     - Remembers your language preference. Only set when you change the language.

Schedule widget
---------------

The schedule widget sets no cookies. Preferences like favourited sessions are stored in local storage and never sent to the server.

Plugins may set additional cookies – check with the plugin documentation if you use any.
