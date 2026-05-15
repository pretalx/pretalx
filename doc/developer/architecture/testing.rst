.. SPDX-FileCopyrightText: 2026-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

Testing
=======

Philosophy
----------

Our CI gate is `100% test coverage <https://jml.io/galahad-principle/>`_. Of
course, tests must not treat coverage percentage as a goal in itself: Every
test must verify behaviour (see below: :ref:`test-assertion-quality`).

Tests are documentation. A developer reading a test should understand what the
code under test is supposed to do, including edge cases. As a result, we
accept more code repetition in tests, so that reading a test's setup involves
as little hunting for setup methods as possible.

Tests are fast because slow tests don't get run.

Testing layers
--------------

We separate our tests into three layers: *Unit tests*, *Integration tests* and
*End-to-End tests*.

**Unit tests:** Every function, method, property, or class has at least one
test or one parameterisation per exit condition. This includes particularly
models, forms, serializers, and all service and utility methods.

Unit testing for views is more tricky: we *include* methods and properties on
view classes that do not handle the actual request/response flow, except
trivial ``@context`` decorated properties. We *exclude* the request/response
handlers on view classes as well as plain view functions, as we test these in
integration tests. We use ``RequestFactory`` instances to replace requests in
unit tests (as opposed to the pytest ``client`` fixture in integration tests).

**Integration tests:** Every view has at least one integration test covering
the happy path, using the various ``client`` fixtures (see
:ref:`test-fixtures`). Integration tests make sure that views work in their
full context of middlewares, rendering, routing, etc.

**End-to-end tests:** End-to-end tests follow critical multi-step paths through
pretalx that cross view boundaries. This includes most prominently the full CfP
submission process, but also other multi-step processes like sending and
accepting invites, building and releasing and viewing schedules, and rendering
and following pretalx-provided links like e.g. on dashboard tiles. These tests
are expected to be slower than unit or integration tests.

.. _`test-assertion-quality`:

Assertion quality
-----------------

**Every test asserts something meaningful about the system's behaviour.**
Checking only ``response.status_code == 200`` does not count; the test has to
clearly show what changed, what is rendered (either in content or in structure,
like in an API response or a HTTP redirect), or what else makes it matter.

We make sure to test not only the happy path, but also known and assumed
potential problems and regressions, like faulty user input and common classes
of security vulnerabilities. This also means that when we test for a negative —
for example, data that is *not* leaking — we make sure there is data that
*could* leak.

Assertions should be specific, so **we prefer equality over membership
checks.** Membership checks (``in``) hide unexpected extras — we use ``==``
instead.

.. code-block:: python

    # Bad – passes even if other users snuck in
    assert user in mail.to_users.all()

    # Good – verifies the exact set
    assert list(mail.to_users.all()) == [user]
    assert set(mail.submissions.all()) == {sub1, sub2}

**Anti-patterns:**

- ``assert response.status_code == 200`` as the sole assertion (unless
  explicitly testing permission/routing *only*, with a separate test for the
  behaviour)
- ``assert obj is not None`` or similar existence checks without checking
  *what* the object is
- Testing implementation details (e.g. asserting a specific SQL query) rather
  than behaviour
- Asserting that another method was called — we test results, not call graphs.
- Mocks and monkeypatches — we use real factories and ``RequestFactory`` instead.

In the rare case that a line truly cannot be covered, we mark it with
``pragma: no cover`` and a comment explaining why.

Test layout
-----------

Tests live in ``src/tests/``, split into Django apps. Inside each app, the
tests are further split along the code structure and are named to match the
file they test. For example, the rules in ``src/pretalx/submission/rules.py``
are tested in ``src/tests/submission/test_rules.py``.

Some modules are tested on multiple layers: All views have at least unit and
integration tests. Here, we use subdirectories named after the layer instead of
filename suffixes: ``src/tests/agenda/views/unit/test_talk.py`` and
``src/tests/agenda/views/integration/test_talk.py`` rather than
``test_talk.py`` and ``test_talk_integration.py``.

Test files are marked with their testing layer at the top of the file,
directly after imports, e.g. ``pytestmark = pytest.mark.unit``, with possible
values being ``unit``, ``integration`` and ``e2e`` to aid in selective runs
of the test suite.

We use function-based tests. Test functions are named
``test_<thing>_<condition_or_behaviour>``, for example
``test_slot_overlaps_when_same_room_and_time`` or
``test_schedule_release_sends_speaker_notifications``. Apart from making tests
easy to find, it also makes it trivial to run selected tests for a changed
interface with ``-k``.

We use the Arrange/Act/Assert pattern for organising code within a test, and we
visually separate the three sections with blank lines when the test is longer
than a few lines.

Docstrings and comments explaining why a test exists or why it's set up a
particular way are welcome only for complex test cases. A test called
``test_dictionary_not_empty`` does not need a docstring that says ``"""Make
sure the dictionary is not empty."""``.

Tooling
-------

We use `pytest <https://docs.pytest.org/>`_ as the test runner and `coverage.py
<https://coverage.readthedocs.io/>`_ for coverage tracking. We use Django
testing helpers as well as `pytest-django
<https://pytest-django.readthedocs.io/>`_ for utilities like
``django.test.override_settings`` to change settings without impacting other
tests, or ``django.core.mail.outbox`` to track sent emails.

Factories
~~~~~~~~~

We use `FactoryBoy <https://factoryboy.readthedocs.io/>`_ for model factories
that live in ``tests/factories/``. Every model that appears in tests has a
factory. As factories are technically against our principle of making tests
readable without hunting for setup and build functions, we strive to keep them
free of any surprising behaviour, so that the reader ideally never has to read
a factory file.


.. _`test-fixtures`:

Fixtures
~~~~~~~~

When simple factories do not suffice to set up complex test data that is needed
in multiple tests (e.g. an event with a CfP, three submissions in different
states, and a partial schedule), we make sparing use of **pytest fixtures** for
composing test setups. Fixtures live in a ``conftest.py`` at the deepest
possible layer, so that only fixtures used across multiple test modules appear
in the root-level ``conftest.py``.

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

Utilities
~~~~~~~~~

We also provide some test utility functions for repeated tasks:

* ``tests.utils.make_orga_user(event=None, *, teams=None, **team_kwargs)``
  creates a user with organiser access.  When ``teams`` is given, the user is
  added to each existing team and no new team is created.  Otherwise a new team
  is created on ``event.organiser`` with ``all_events=True`` by default.  Pass
  keyword arguments to customise the teams.

* ``tests.utils.make_request(event, user=None, method="get", path="/", headers=None, **attrs)``
  creates a plain Django ``HttpRequest`` for view unit tests.  Sets ``event``
  and ``user`` (defaults to ``AnonymousUser``) as attributes on the request.
  Any extra keyword arguments are set as request attributes (e.g.
  ``resolver_match``).
* ``tests.utils.make_view(view_class, request, **kwargs)`` instantiates a
  Django class-based view with ``request`` and ``kwargs`` already set, without
  dispatching.
* ``tests.utils.make_api_request(event=None, user=None, path="/", data=None, **attrs)``
  creates a DRF ``Request`` for serializer and API unit tests. Sets ``event``,
  ``user``, and any additional keyword arguments (e.g. ``organiser``) as
  attributes on the underlying Django request.
* ``tests.utils.refresh(instance, **updates)`` updates a model with the
  optionally passed keyword arguments and then re-fetches it from the database,
  clearing any ``@cached_property`` data.

Parametrisation
---------------

We use ``pytest.mark.parametrize`` to collapse related scenarios into a single
test function rather than writing near-duplicate tests. If two tests share the
same arrange/act structure and only differ in inputs and expected outputs, they
become one parametrized test. If the *setup* differs significantly between
cases, they stay separate.

N+1 query prevention
--------------------

The most common performance problem in a Django project involves n+1 queries on
list views and other views that render collections.

To prevent any n+1 query behaviour from the beginning, all of these views have
at least one test that is parameterised with ``item_count`` values of **1 and
3** and wrapped in ``django_assert_num_queries`` with a literal integer. This
ensures the query count stays constant regardless of data size. When we make
changes to the view itself or to underlying middleware, signals, or even
plugins that add per-object queries, we catch the problem early. When the test
breaks, the type of breakage also clearly shows if we changed the number of
queries across all requests (which is often fine) or if we introduced an actual
n+1 query.

Running tests
-------------

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
