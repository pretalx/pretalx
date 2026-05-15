.. SPDX-FileCopyrightText: 2019-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

Coding standards
================

pretalx is a fairly standard Django project. This page lists the
project-specific style rules and how to make sure you apply them.
For a more high-level approach, see :doc:`architecture/structure` (how a
pretalx app is organised internally) and :doc:`architecture/testing` (testing
philosophy, layers, fixtures).

Backend
-------

- Run ``just fmt`` before committing to auto-format and lint your code.
  Fix any remaining errors that the linter cannot fix automatically.
- Mark all user-facing strings for **translation**, and avoid unnecessary
  changes to existing translations, as they require manual re-translation in
  all languages.
- Do not put any CSS or JS inline in HTML templates! Always use separate files
  to make sure your changes comply with our CSP headers.
- All user input is validated and rendered through Django's form layer. Any new
  input handling should use forms too.
- When building a new feature with visible user impact, add it to
  ``doc/changelog.rst``.

Frontend
--------

- pretalx is written in plain JS (no jQuery, no Bootstrap) and plain CSS,
  though we have some CSS class conventions that are similar to Bootstrap.
- Some libraries are vendored in ``src/pretalx/static/vendored``, most notably
  HTMX. Use HTMX for interactive UI, and use Django template partials to reduce
  code duplication in HTMX rendering.
- JavaScript code should be modern – arrow functions, ``const``, template
  literals, etc.
