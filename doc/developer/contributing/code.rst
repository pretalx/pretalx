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

Philosophy
~~~~~~~~~~

Our CI gate is `100% test coverage <https://jml.io/galahad-principle/>`_.
This is a forcing function, not a goal in itself — coverage without meaningful
assertions is worse than no coverage because it creates false confidence. Every
test verifies **behaviour**, not just that code runs without exceptions.

Tests are documentation. A developer reading a test should understand what the
code under test is supposed to do, including edge cases. Docstrings explaining
*why* a test exists and *why* it's set up a particular way are welcome,
especially for non-obvious arrangements — but a test called
``test_dictionary_not_empty`` does not need a docstring that says
``"""Make sure the dictionary is not empty."""``.

Tests are fast. Slow tests don't get run locally.

Testing layers
~~~~~~~~~~~~~~

We separate our tests into three layers: *Unit tests*, *Integration tests* and
*End-to-End tests*.

**Unit tests:** Every function, method, property, or class has at least one
test or one parameterization per exit condition. This includes particularly
models, forms, serializers, and all service and utility methods.

Unit testing for views is more tricky: we *include* methods and properties on
view classes that do not handle the actual request/response flow, except
trivial ``@context`` decorated properties. We *exclude* the request/response
handlers on view classes as well as plain view functions, as we test these in
integration tests. We use ``RequestFactory`` instances to replace requests in
unit tests (as opposed to the pytest ``client`` fixture in integration tests).

**Integration tests:** Every view has at least one integration test covering
the happy path, using the various ``client`` fixtures. Integration tests make
sure that views work in their full context of middlewares, rendering, routing,
etc.

**End-to-end tests:** Multi-step user flows that cross view boundaries, still
using pytest and the Django test client (no browser automation). These encode
the critical paths through pretalx — like the CfP submission process, event
creation, sending and accepting invites, building and releasing schedules, and
so on — by calling multiple views in sequence and following the resulting
redirects and state changes. These tests are expected to be slower than unit or
even integration tests.

Assertion quality
~~~~~~~~~~~~~~~~~

**Every test asserts something meaningful about the system's behaviour.**
Checking only ``response.status_code == 200`` does not count.

When we test for a negative — for example, data that is *not* leaking — we
make sure there is data that *could* leak.

View tests assert at least one of:

- Response context contains the expected data
  (``assert response.context['form'].instance == expected_obj``)
- Database state changed as expected
  (``assert Submission.objects.filter(state='accepted').count() == 1``, plus
  checking that the accepted submission is the one that **should** be accepted)
- The correct template was used
  (``assert 'agenda/schedule.html' in [t.name for t in response.templates]``)
  if the view does complex template handling rather than having a fixed template
  assigned
- Redirects go to the right place with the right state
  (``assert response.url == expected_url``)
- Response body contains expected content for API views
  (``assert response.json()['results'][0]['title'] == expected``)

Model/method tests assert:

- Return values match expected output for given input
- Side effects occurred (objects created, signals sent, state changed)
- Edge cases are handled (empty inputs, boundary values, ``None`` where
  applicable)
- Exceptions are raised for invalid states
  (``with pytest.raises(SpecificException):``)

Form tests assert:

- ``form.is_valid()`` returns the expected boolean *and* ``form.errors``
  contains the specific field and error
- ``form.save()`` creates/modifies the correct objects with the correct field
  values
- If choice fields have complex setups for the available options, the choices
  match expectations (e.g. only including objects the user is permitted to see)

**We prefer equality over membership checks.** Membership checks (``in``) hide
unexpected extras — we use ``==`` on lists or sets instead:

.. code-block:: python

    # Bad – passes even if other users snuck in
    assert user in mail.to_users.all()

    # Good – verifies the exact set
    assert list(mail.to_users.all()) == [user]
    assert set(mail.submissions.all()) == {sub1, sub2}

The same applies to dicts and strings — we compare the full value, not just a
fragment. When full equality is unwieldy, we compare the important fields
individually with ``==``.

**Anti-patterns:**

- ``assert response.status_code == 200`` as the sole assertion (unless
  explicitly testing permission/routing *only*, with a separate test for the
  behaviour)
- ``assert obj is not None`` or similar existence checks without checking
  *what* the object is
- Testing implementation details (e.g. asserting a specific SQL query) rather
  than behaviour
- Exact string matching on error messages — we match on error code or field
  name instead. If there is not enough structural data to do so, that's a sign
  to improve the structure.
- Asserting that another method was called — we test results, not call graphs.
- Unnecessary database saves — we avoid ``save()`` in unit tests when we can.
- Mocks and monkeypatches — we use real factories and ``RequestFactory`` instead.

In the rare case that a line truly cannot be covered, we mark it with
``pragma: no cover`` and a comment explaining why.

Test layout
~~~~~~~~~~~

Tests live in ``src/tests/``, split into Django apps. Inside each app, the
tests are further split along the code structure and are named to match the
file they test. For example, the views in
``src/pretalx/agenda/views/talk.py`` are tested in
``src/tests/agenda/views/test_talk.py``.

Test files are marked with their testing layer at the top of the file,
directly after imports, e.g. ``pytestmark = pytest.mark.unit``, with possible
values being ``unit``, ``integration`` and ``e2e``.

When a directory contains tests at multiple layers (most commonly ``views/``),
we use subdirectories named after the layer instead of filename suffixes:
``src/tests/agenda/views/unit/test_talk.py`` and
``src/tests/agenda/views/integration/test_talk.py`` rather than
``test_talk.py`` and ``test_talk_integration.py``. This keeps filenames clean
and makes it easy to run an entire layer at once
(``just test src/tests/agenda/views/integration/``).

Test functions are named ``test_<thing>_<condition_or_behaviour>``:

- ``test_slot_overlaps_when_same_room_and_time``
- ``test_cfp_submit_without_permission_returns_403``
- ``test_schedule_release_sends_speaker_notifications``

Not beautiful, but consistent, predictable, and friendly both for grep and for
running selected tests with ``-k``. We do not use test classes — all tests are
top-level functions.

We use the Arrange/Act/Assert pattern for organising code within a test.
Visually separate the three sections with blank lines when the test is longer
than a few lines.

Tooling
~~~~~~~

`pytest <https://docs.pytest.org/>`_ as the test runner and
`coverage.py <https://coverage.readthedocs.io/>`_ for
coverage tracking. 100% coverage is required for CI to pass.

`FactoryBoy <https://factoryboy.readthedocs.io/>`_ for model factories. All
factories live in ``tests/factories/`` and are importable from
``tests.factories``. Every model that appears in tests has a factory.
Factories produce minimal valid instances — we don't set optional fields unless
the factory's purpose requires it.

`pytest-django <https://pytest-django.readthedocs.io/>`_ bridges pytest and
Django, exposing ``client``, ``rf`` (RequestFactory), ``admin_client``, ``db``,
``transactional_db`` etc. as fixtures, and importantly
``pytest.mark.django_db``. We also use Django testing helpers like
``django.test.override_settings`` or ``django.core.mail.outbox`` (as
``djmail.outbox``).

**pytest fixtures** for composing test setups. Complex arrangements (e.g. an
event with a CfP, three submissions in different states, and a partial
schedule) live as fixtures in ``conftest.py`` at the appropriate level. For
example, we use fixtures for a base ``event`` object that requires a lot of
other objects to get set up. We do **not** use fixtures to wrap a single
factory call — those go directly in the test. ``conftest.py`` fixtures are
reserved for setups that involve multiple objects, relationships, or teardown
logic, or that are used very frequently across many tests.

Selected fixtures that build data:

* ``user_with_event`` yields a user with a team membership granting organiser
  access to an event.
* ``populated_event`` provides an event with as many related objects as
  possible.
* ``organiser_user`` yields a user with organiser-level access
  (``all_events``) to the ``event`` fixture via ``make_orga_user``.
  Use with ``client.force_login(organiser_user)`` when a test needs an
  authenticated organiser.
* ``talk_slot`` provides a visible, confirmed talk slot on an event's WIP
  schedule (includes a speaker and submission), and ``published_talk_slot``
  its published sibling on the currently released schedule.
* ``make_image`` returns a factory function that creates a minimal valid 1×1
  PNG as a ``SimpleUploadedFile``. Call it as ``make_image()`` or
  ``make_image("custom_name.png")``.
* ``locmem_cache`` replaces the default ``DummyCache`` with a real
  ``LocMemCache`` so that cache operations actually store and retrieve data.
  The cache is cleared before each test for isolation.

Test utilities:

* ``tests.utils.make_orga_user(event=None, *, teams=None, **team_kwargs)``
  creates a user with organiser access.  When ``teams`` is given, the user is
  added to each existing team and no new team is created.  Otherwise a new team
  is created on ``event.organiser`` with ``all_events=True`` by default.  Pass
  keyword arguments to customise the team::

      # Minimal organiser
      user = make_orga_user(event)

      # Organiser with specific permissions
      user = make_orga_user(event, can_change_submissions=True)

      # Add to existing teams (no new team created)
      user = make_orga_user(teams=[team1, team2])

* ``tests.utils.make_request(event, user=None, method="get", path="/", headers=None, **attrs)``
  creates a plain Django ``HttpRequest`` for view unit tests.  Sets ``event``
  and ``user`` (defaults to ``AnonymousUser``) as attributes on the request.
  Any extra keyword arguments are set as request attributes (e.g.
  ``resolver_match``).
* ``tests.utils.make_view(view_class, request, **kwargs)`` instantiates a
  Django class-based view with ``request`` and ``kwargs`` already set, without
  dispatching.  Useful in unit tests to call individual view methods and
  properties directly::

      request = make_request(event, user=speaker)
      view = make_view(TalkView, request, slug=submission.code)
      assert view.object == submission

* ``tests.utils.make_api_request(event=None, user=None, path="/", data=None, **attrs)``
  creates a DRF ``Request`` for serializer and API unit tests. Sets ``event``,
  ``user``, and any additional keyword arguments (e.g. ``organiser``) as
  attributes on the underlying Django request.
* ``tests.utils.refresh(instance, **updates)`` updates a model with the
  optionally passed keyword arguments and then re-fetches it from the database,
  clearing any ``@cached_property`` data.
* We set up sensible test settings, including configuring Celery to run in
  eager mode.

Parametrization
~~~~~~~~~~~~~~~

We use ``pytest.mark.parametrize`` to collapse related scenarios into a single
test function rather than writing near-duplicate tests. If two tests share the
same arrange/act structure and only differ in inputs and expected outputs, they
become one parametrized test. If the *setup* differs significantly between
cases, they stay separate.

N+1 query prevention
~~~~~~~~~~~~~~~~~~~~~

List views and other views that render collections are parameterized with
``item_count`` values of **1 and 3** and wrapped in
``django_assert_num_queries`` with a literal integer. This ensures the query
count stays constant regardless of data size — when a middleware, signal, or
queryset change adds queries, the test breaks early.

Running tests
~~~~~~~~~~~~~

Run tests with::

    just test

Standard pytest flags all work:

- ``just test -k <pattern>``: run only tests matching a name pattern. Working
  on CfP views? ``just test -k cfp_submit``.
- ``just test --lf``: re-run only tests that failed last time.
- ``just test -x``: stop at first failure.
- ``just test --no-header -rN``: minimal output, useful when running the full
  suite.
- ``just test tests/schedule/``: run all tests for one app.
- ``just test -m "not e2e"``: run all tests except for e2e tests.

.. note:: For faster runs, ``just test-parallel`` uses multiple CPU cores (with
          an optional ``NUM`` parameter to specify the number of threads, or
          leave empty for an automatic choice).
