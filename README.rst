.. SPDX-FileCopyrightText: 2017-present Tobias Kunze
.. SPDX-License-Identifier: Apache-2.0

|logo|

.. image:: https://img.shields.io/github/actions/workflow/status/pretalx/pretalx/tests.yml?branch=main
   :target: https://github.com/pretalx/pretalx/actions/workflows/tests.yml?query=workflow%3ATests
   :alt: Continuous integration

.. image:: https://img.shields.io/pypi/v/pretalx.svg?colorB=3aa57c
   :target: https://pypi.python.org/pypi/pretalx
   :alt: PyPI

.. image:: https://img.shields.io/pypi/pyversions/pretalx.svg?colorB=3aa57c
   :target: https://pypi.python.org/pypi/pretalx
   :alt: Supported Python versions

.. image:: https://img.shields.io/badge/docs-passing-3aa57c
   :target: https://docs.pretalx.org/
   :alt: Documentation

.. image:: https://img.shields.io/badge/news-blog-3aa57c
   :target: https://pretalx.com/p/news/
   :alt: Website

**pretalx** is a conference planning tool focused on providing the best
experience for organisers, speakers, reviewers, and attendees alike.  It
handles the submission process with a configurable Call for Participation, the
reviewing and selection of submissions, and the scheduling and release
handling. After the event, pretalx allows speakers to receive feedback, upload
their slides, and organisers to embed recordings.

In short: pretalx takes a conference from "we should do a call for papers" all
the way to "here is the published schedule" – and everything in between.

What pretalx does for you:

- **Call for Participation** – a fully configurable submission process with
  custom questions, tracks, and session types.
- **Reviewing & selection** – collaborative reviews, scoring, and team-based
  workflows to curate your programme.
- **Scheduling** – build, version, and release schedules across rooms and
  days, with public agenda and per-speaker views.
- **Speaker communication** – templated, queued emails, invitations, and
  post-event feedback.
- **Integrations** – a documented REST API, an extensible plugin system, and
  full internationalisation.

Read our `feature list`_ on our main site to get a better idea of what pretalx
can do for you, but it typically involves everything you'll need to curate
submissions and contents for a conference with several tracks and conference
days.

🚀 Getting started
------------------

You can host pretalx yourself, as detailed in our `administrator
documentation`_, or use our public instance at `pretalx.com`_. Self-hosting
runs on Python (3.12+) with PostgreSQL and Redis; the docs walk you through
both a Docker-based and a manual setup. If you want to follow along with new
versions and upcoming features, we recommend `our blog`_.

📺 Look and feel
----------------

|screenshots|

Check out our `feature list`_ for more screenshots, or browse `pretalx.jetzt`_
to see pretalx running in the wild.

pretalx is highly configurable, so you can change its appearance and behaviour
in many ways if the defaults don't fit your event. If the settings are not
enough for you, you can even write plugins of your own.

🚦 Project status
-----------------

pretalx is under `active development`_ and used by `many events`_. It supports
everything required for talk submission, speaker communication, and scheduling.
You can see our supported features in the `feature list`_, and our planned
features in our open issues_. pretalx has regular releases – you can look at
the `changelog`_ to see upcoming and past changes, and install pretalx via
PyPI_. Our CI gate is 100% test coverage, so changes land with confidence.

🔨 Contributing
---------------

Contributions to pretalx are very welcome! You can contribute observations,
bugs or feature requests via the issues. If you want to contribute changes to
pretalx, please check our `developer documentation`_ on how to set up pretalx
and get started on development. Please bear in mind that our Code of Conduct
applies to the complete contribution process.

If you are interested in plugin development, check our documentation, and
bring or browse ideas in our `GitHub Discussions`_.

💡 Project information
----------------------

The pretalx source code is available on `GitHub`_, where you can also find the
issue tracker. The documentation is available at `docs.pretalx.org`_, and you
can find up to date information on `our blog`_ and on the Fediverse via
`Mastodon`_ (and on `LinkedIn`_). The pretalx package is available via `PyPI`_.

We publish pretalx under the terms of the Apache License. See the LICENSE file
for further information and the complete license text.

The primary maintainer of this project is Tobias Kunze <r@rixx.de> (who also
runs `pretalx.com`_).  See the `list of contributors`_ on GitHub for all the
awesome folks who contributed to this project.

🧭 Users
--------

If you want to see pretalx in use, head over to `pretalx.jetzt`_ for current
and upcoming events, or browse the wiki's `instances list`_ of self-hosted
pretalx installations.

.. |logo| image:: https://raw.githubusercontent.com/pretalx/pretalx/main/src/pretalx/static/common/img/logo.png
   :alt: pretalx logo
   :target: https://pretalx.com
.. |screenshots| image:: https://img.pretalx.com/docs/screenshots.png
   :target: https://pretalx.com/p/features
   :alt: Screenshots of pretalx pages
.. _issues: https://github.com/pretalx/pretalx/issues/
.. _feature list: https://pretalx.com/p/features
.. _developer documentation: https://docs.pretalx.org/developer/index.html
.. _administrator documentation: https://docs.pretalx.org/administrator/index.html
.. _pretalx.com: https://pretalx.com/
.. _pretalx.jetzt: https://pretalx.jetzt/
.. _active development: https://github.com/pretalx/pretalx/pulse
.. _changelog: https://docs.pretalx.org/changelog.html
.. _PyPI: https://pypi.python.org/pypi/pretalx
.. _GitHub Discussions: https://github.com/pretalx/pretalx/discussions
.. _instances list: https://github.com/pretalx/pretalx/wiki/Instances
.. _many events: https://pretalx.jetzt/
.. _list of contributors: https://github.com/pretalx/pretalx/graphs/contributors
.. _our blog: https://pretalx.com/p/news/
.. _GitHub: https://github.com/pretalx/pretalx
.. _docs.pretalx.org: https://docs.pretalx.org
.. _Mastodon: https://chaos.social/@pretalx
.. _LinkedIn: https://www.linkedin.com/company/pretalx/
