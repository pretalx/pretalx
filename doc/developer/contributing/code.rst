.. SPDX-FileCopyrightText: 2019-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

Contributing Code to pretalx
============================

pretalx is a fairly standard Django project. This page only lists the
project-specific conventions and details that are easy to miss or get wrong.

Backend
-------

- Run ``just fmt`` before committing to auto-format and lint your code.
- Mark all user-facing strings for **translation**, and avoid unnecessary
  changes to existing translations, as they require manual re-translation in
  all languages.
- Do not put any CSS or JS inline in HTML templates, always use separate files,
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

Testing
-------

pretalx aims for 100% test coverage. Changes should be covered by tests – if
an existing test covers similar ground, add assertions to it instead of writing
a new test.

Tests are function-based using pytest fixtures. Do not use test classes.
Use ``pytest.mark.parametrize`` when you need to check multiple outcomes of the
same scenario. Do not write docstrings for tests.

If you need to set up reusable data, put it as a fixture into the
``conftest.py``, or into the test file if it won't be used elsewhere.

Run tests with::

    $ just test

You can append all the standard pytest flags, like ``--lf`` to repeat only
failing tests, ``-k something`` to run only tests called ``*something*``, and
``-x`` to stop on the first breaking test.

.. note:: If you have more than one CPU core and want to speed up the test
          suite, you can run ``just test-parallel`` (with an optional ``NUM``
          parameter to specify the number of threads, which you can leave
          empty for an automatic choice.)

Testing query counts
~~~~~~~~~~~~~~~~~~~~

It's easy to introduce N+1 queries in Django accidentally. To prevent this,
many view tests use ``django_assert_num_queries``. Any test for a view that can
contain multiple objects of the same type – like a list view, or a view showing
multiple related objects (e.g. multiple speakers on a session page) – should be
parametrized with ``item_count(1, 3)``. The test then generates that number of
items and asserts a constant number of SQL queries regardless.
