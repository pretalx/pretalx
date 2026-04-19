.. SPDX-FileCopyrightText: 2025-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _contributing:

Contribution Policy
===================

pretalx is open source software and we appreciate contributions from the
community. Contributions can come in many forms: Code, Documentation,
:ref:`Translations<translating>`, Graphics, Feedback … Here is how to get
started with a code contribution:

1. Find an existing issue you’d like to work on, or `open a new issue`_
   describing the bug you want to fix or the feature you want to add.
2. Comment on the issue to ask to be assigned. For new issues, please wait
   until a maintainer has applied the ``accepted`` label before starting work
   – this is how we confirm that the change fits the project.
3. Once the issue is labelled ``accepted`` and assigned to you, go ahead and
   open your pull request referencing the issue.

If you’re not sure whether an idea is a good fit, or how to make something
work, feel free to `open a GitHub Discussion`_ about it first.

.. important::

   We only accept pull requests that address a GitHub issue that has the
   `accepted`_ label and has been assigned to the contributor. This lets us
   agree on scope and approach before anyone writes code, and avoids
   situations where a PR has to be rejected after the fact.

   The only exception is trivial fixes such as typo corrections in
   documentation or comments – feel free to open a PR for those directly.

When you open your pull request, please remember to:

- Add tests that cover your changes.
- Update the documentation if your change affects it.
- Add an entry to ``doc/changelog.rst`` describing your change.
- Describe how you tested the change in the PR description, and include
  screenshots for UI changes.

Pull requests that don't follow this process, or that are missing these
pieces, will be closed without detailed review.

Don’t forget to head over to :ref:`devsetup` to read about how to set up your
local copy of pretalx for development and testing.

Please note that we bound ourselves to a :ref:`coc` that applies to all
communication around the project. We do not tolerate any form of harassment.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   code
   translating
   codeofconduct

.. _accepted: https://github.com/pretalx/pretalx/issues?q=is%3Aissue%20is%3Aopen%20label%3Aaccepted
.. _open a new issue: https://github.com/pretalx/pretalx/issues/new
.. _open a GitHub discussion: https://github.com/pretalx/pretalx/discussions/new
