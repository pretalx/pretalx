.. SPDX-FileCopyrightText: 2025-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

Release cycle
=============

.. note::

   This page is only relevant for self-hosted installations.
   `pretalx.com <https://pretalx.com>`_ users are always on the latest version – and sometimes even get early access to new features before they are included in a release.

pretalx follows a `calendar versioning <https://calver.org/>`_ scheme with
version numbers of the form ``YEAR.NUMBER.PATCH`` (e.g. 2025.2.0 is the second
feature release of 2025).

We publish several **feature releases** per year.
These releases may contain new functionality, removal of functionality, or any other kind of change.
We recommend reading the :doc:`release notes </changelog>` before upgrading if you are concerned about API or plugin compatibility.

**Patch releases** (e.g. 2025.2.1) are published when required to fix critical issues or security vulnerabilities.
Patch releases are only made available for the **current feature release**.
We therefore recommend staying up to date with feature releases to ensure you receive any necessary patches.

Plugins
-------

Plugins developed by us are released in sync with pretalx feature releases.
We recommend updating plugins and pretalx at the same time.
We cannot guarantee backwards compatibility of new releases with plugins not released by us.
However, we include changes to plugin APIs and potential breaking changes in our :doc:`detailed release notes </changelog>`, which plugin authors are encouraged to refer to.

Announcements
-------------

All releases are announced on `our blog <https://pretalx.com/p/news>`_, with a detailed changelog available in our :doc:`release notes </changelog>`.
Releases are also published on `GitHub <https://github.com/pretalx/pretalx/releases>`_ and `PyPI <https://pypi.org/project/pretalx/>`_.
