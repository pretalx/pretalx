.. SPDX-FileCopyrightText: 2026-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

Project structure
=================

Apps
----

pretalx is a Django project. Django projects are commonly structured in “apps”.
Apps are technically just Python packages that can be reused across multiple
Django projects, which is a cool approach to framework design, and is how most
Django libraries work. It is also how the pretalx plugin system works: every
plugin is a Django app, which makes it trivial for plugins to include models
and migrations as well as other interfaces. It's a good system.

However. Non-library Django projects often also use apps for their general
project structure, even when they have no intention of being reused.
I was young and dumb when I started pretalx and did exactly that.

I would not set pretalx up the same way again were I starting today, but
migrating away from the fundamental project structure would be a huge
undertaking, and would break all existing pretalx plugins, so that is not an
option. Instead, pretalx now has an overall architecture that makes the best of
the existing structure by being very particular about how the apps are
structured (see below: :ref:`structure-layers`).

pretalx consists of ten apps in total, of which five are dedicated to the data
model and domain logic. They make the strictest use of our layering approach:

- ``event`` contains the foundational models for the tenant-like structure
  of pretalx, with the data models for organisers, events and teams.
- ``submission`` is the largest and central data app, as it contains the
  submission model as well as all directly related models, like tracks, tags,
  submission types, custom fields (“questions”), and much of the domain
  logic and query optimisation in pretalx.
- ``schedule`` is concerned with scheduling submissions and contains the
  models for schedules (schedule versions), schedule slots, rooms and
  availabilities. It contains domain logic concerned with scheduling,
  finding overlaps and problems, as well as optimisation focused on
  the central schedule view/widget.
- ``person`` contains the user model used for authentication as well as
  models for speaker data, preferences, and profile pictures. Its domain
  focus is largely on managing, inviting and adding speakers or users.
- ``mail`` only contains the models for emails and email templates, but
  has to do the heavy lifting for domain logic on email sending, retries,
  using per-event email settings as well as the safe rendering of emails,
  particularly when templates may include user-provided content.

Four apps are focused on different parts of the frontend. They contain views
and templates, and delegate most domain logic, like performing actions or
running permission checks, to the data apps:

- ``orga`` is the largest of the frontend apps and contains all views for
  the organiser area of pretalx.
- ``cfp`` serves to render the CfP itself, as well as pages for speakers
  and submitters.
- ``agenda`` is responsible for rendering the pretalx schedule and related
  pages, including the pretalx schedule widget and its data endpoints.
- ``api`` is a self-contained app for the pretalx API. It contains the API
  views and also the API serializers – serializers arguably properly
  belong in the various data apps, just like forms, but as API code is
  very coherent and tightly coupled in practice, we decided to keep all API
  specific code here.

Finally one app, ``common``, is a ~~junk-drawer~~ place where general utilities
and mixins are collected that are used in the other apps. It also contains
models that do not belong anywhere, particularly the model used for the pretalx
action history for per-object logging of user actions.

.. _`structure-layers`:

Layers
------

While the view apps contain primarily a ``views`` and a ``templates`` directory,
model apps follow a strict layout and layering approach.

``models/``
    The Django database model definitions live in ``models/``, which is
    standard practice. Changes to Django models generate database migrations
    in ``migrations/``.

    Apart from the actual model definition, most pretalx models come with a
    ``urls`` class, providing an easy and reliable way to access object-specific
    URLs (e.g. ``submission.urls.confirm`` or ``submission.orga_urls.review``).
    Models also often have additional computed ``@property`` and
    ``@cached_property`` fields that help to access e.g. pre-filtered or
    pre-rendered attributes. These are kept slim; all complex logic is placed
    in ``domain/``.

    Likewise, there are no complex actions or methods defined on models, but
    (both for compatibility with legacy code and for readability), some models
    expose some thin methods, like e.g. ``Submission.accept()``, that delegate
    directly to the corresponding domain functions.

``domain/``
    This is where our business logic lives, which serves to keep our
    model files at a readable size, to make common APIs easy to discover, and
    to have a clean surface for unit-testing.

    The domain directory contains files split roughly along the lines of the
    corresponding models files, though there can be additional files as needed;
    for example, there is ``schedule/domain/ical.py`` for calendar data generation.

    Apart from the business logic, the domain also contains data/data
    transforms. There is often a separate ``domain/queries/`` for complex
    database queries and annotations that are re-used across multiple callers,
    such as ``submissions_for_user``. Trivial queries or e.g. default managers
    do not need to live here.

``interfaces/``
    This is our boundary surface. Its main use is for forms, which serve to
    take HTTP input, validate it and provide clean output. We also count
    exporters to the interfaces, which take data transformed by domain-level
    code and output everything needed for a HTTP response, including e.g.
    Content-Type information.

    This is also where API serializers would belong, had we not decided to keep
    them contained in the ``api`` app. We try to keep model-focused forms and
    serializers in step as much as possible, deferring validation to central
    validators and write actions to domain methods to make sure the API behaves
    as much like the frontend as possible.

Additionally, there are some top-level files that most apps (often including
view apps) have:

- ``enums.py`` contains enums used in model definition, like e.g.
  ``QuestionType``. It would be arguably nicer to keep these in the models
  using them in their field definitions – but keeping them in a separate
  file allows us to import them everywhere without worrying about circular
  imports.
- ``phrases.py`` allows each app to register some reusable strings that can
  be used in Python code as well as in HTML templates. The list of translated
  strings in pretalx is already large, and this helps us to keep it manageable
  by making reuse of existing translated strings easy.
- ``rules.py`` contains permission logic using the excellent ``django-rules``
  library. Models import predicates from here to define standard model-level
  permissions, but there are also permissions registered inside ``rules.py``
  for non-model-specific permission checks.
- ``signals.py`` contains pretalx-defined signals, which are our primary
  interface for plugins, and ``receivers.py`` contains consumers of those signals.
- ``tasks.py`` contains functions that can be called asynchronously via
  ``Celery``. We treat tasks as very thin wrapper functions that then delegate
  to domain functions – the task functions should only retrieve the necessary
  objects (task functions must only be passed primitive data types, so they
  have to fetch objects from the database) and handle error logging.
- ``validators.py`` contains model validation that may be called from models
  (e.g. in the ``clean()`` method), but also from forms and serializers, or
  even from views on occasion.

Import ordering
---------------

The layering approach results in the following import ordering:

0. **enums, rules, signals, tasks, validators**: Leaf nodes. Many
   of these are imported on startup. Any import of other layers
   has to be inline.
1. **models**: Can import Layer 0 freely.
   Thin methods that delegate to domain (e.g. ``Submission.accept()``)
   inline-import the domain function inside the method body.
2. **domain**: Can import Layers 0 and 1 freely.
   If you need inline imports here, that points to a design problem.
3. **interfaces**: Can import Layers 0-2 freely.
4. **views, api**: Uses everything else.

Inline imports and ``PLC0415``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ruff's ``PLC0415`` rule flags imports inside function bodies. We enforce the
rule, because we strongly prefer top-level imports. We then suppress it at
sites where deferring the import is intentional. Every suppression must carry a
short trailing reason:

.. code-block:: python

    from PIL import Image  # noqa: PLC0415 -- slow import

The reason has to come from the following list, which is enforced by the linter:

- ``slow import``: Some modules are heavy and slow down Django startup. This is
  usually of not much consequence on the server, but hurts during development when
  every code change triggers a restart. A list of modules that must be imported
  inline as slow modules is enforced by the linter.
- ``optional dependency``: Usually wrapped in ``try: import …; except ImportError``.
- ``thin method``: Only permitted in models, this is for our specific exception
  of models delegating to domain functions for readability (and, sigh, legacy
  compatibility).
- ``leaf`` (in ``tasks``, ``signals``, ``receivers``) and ``predicate`` (in ``rules``
  and ``validators``): See the per-app import ordering explanation above.
- ``app ready``: We have to import some modules at startup, which is done by way
  of the ``ready()`` method in ``apps.py``.
- ``circular import``: Even with our pretty layered design, there can be real
  circular imports, e.g. between different domain queries modules. Moving an
  import inline as a circular import should make you sceptical. Double-check that
  you are not violating the layering approach.


**This is it.** There is intentionally no allowance for importing interfaces
from models. If you find yourself doing this, your code is in the wrong place.
