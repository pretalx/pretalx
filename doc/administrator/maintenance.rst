.. SPDX-FileCopyrightText: 2019-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _maintenance:

Maintenance and Updates
=======================

If you host your own pretalx instance, you also need to care about the
availability of your service and the safety about your data yourself.
This page gives you some information that you may need to do so.

Backups
-------

There are two things which you should create backups of:

Database
    Your SQL database (SQLite or PostgreSQL). This is critical and you must
    **always always create automatic backups of your database**. There are tons
    of tutorials on the internet on how to do this, and the process depends on
    the choice of your database. For PostgreSQL, see the ``pg_dump`` tool. For
    SQLite, it is sufficient to create a backup of the database file. You
    should create a cronjob or timer that does the backups for you on a regular
    schedule.

Data directory
    The data directory of your pretalx configuration may contain files that you
    want to back up. If you did not specify a secret in your config file, back
    up the ``.secret`` text file in the data directory. If you lose the secret,
    all active user sessions will be invalid. You should
    back up the ``media`` subdirectory of the data directory. It contains
    all user-uploaded and generated files. This includes files you could in
    theory regenerate (talk and speaker images for social media, html exports),
    but also files that you or your users would need to re-upload (event logos,
    profile pictures, etc.).

There is no need to create backups of the redis database, if you use it. We
only use it for non-critical, temporary or cached data.


Monitoring
----------

To monitor whether your pretalx instance is running, you can issue a GET
request to https://pretalx.example.org/healthcheck/. This endpoint tests if
the connection to the database and to the configured cache is working
correctly. If everything appears to work fine, an empty response with status
code ``200`` is returned. If there is a problem, a status code in the ``5xx``
range will be returned.


Updates
-------

.. warning:: While we try hard not to issue breaking updates, **please perform
             a backup before every upgrade**.

If you run your own pretalx instance, you will have to take care of updates,
including both system updates and pretalx updates. We highly recommend that you
update to the latest pretalx version as soon as it is available, as it may
contain security fixes as well as new features.

Release Cycle
~~~~~~~~~~~~~

pretalx uses the following versioning scheme:

- Feature releases have a version in the format ``YEAR.NUMBER.0``, so e.g.
  v2025.2.0 is the second release issued in 2025. Feature releases are
  issued every couple of months, and we aim to release at least two or three
  feature releases per year.
  These releases may contain new functionality, removal of functionality, or
  any other kind of change. We recommend studying the release notes before
  upgrading if you are concerned about API or plugin compatibility.
- Bugfix releases have a version in the format of ``year.number.PATCH``, so
  e.g. 2025.2.1 is the first bugfix release after 2025.2.0. Bugfix releases are
  not released on a schedule, but as required to fix a critical issue that
  cannot wait for the next feature release. These releases do not contain
  functional changes unless those functional changes are required to fix a
  security issue. Bugfix releases are only issued for the latest feature release.

pretalx provides an update check that is turned on by default, and that will
send you an email when a new update becomes available. We do not use this
update check to collect any identifiable data about your instance, and we
highly recommend that you do not turn it off, as skipping updates may introduce
security issues.

We also announce all our feature releases on our blog_. Additionally, you
can refer to our :ref:`changelog`, the release history on PyPI_, and the
release history on GitHub_.

When we issue a new feature release, we also provide compatible releases for
all plugins developed by us, so we recommend that you update your installed
plugins at the same time as the core pretalx system. Most plugins follow
a ``MAJOR.MINOR.PATCH`` version number scheme.

Performing Updates
~~~~~~~~~~~~~~~~~~

This guide assumes that you followed the :ref:`installation` documentation.

We try to make upgrades as painless as possible. To this end, we provide
:ref:`changelog` and our release `blog`_ post. Please read them – they contain
important upgrade notes and warnings. Also, make sure you have a current
backup.

Next, execute the following commands in the same environment as your
installation. This may be your pretalx user, or a virtualenv, if you chose a
different installation path.

.. highlight:: console

These commands update pretalx first, then the database, then the static files.
Once you have executed these steps without seeing any errors, do not forget to
restart your service(s)::

    (env)$ pip3 install --upgrade-strategy eager -U pretalx
    (env)$ python -m pretalx check --deploy
    (env)$ python -m pretalx migrate
    (env)$ python -m pretalx rebuild --npm-install
    # systemctl restart pretalx-web
    # systemctl restart pretalx-worker  # If you’re running celery

Installing a fixed release
~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to upgrade pretalx to a specific release, you can pin the version
in the pip command. Substitute ``pretalx`` with ``pretalx==1.2.3`` in the pip
install line above like this::

    (env)$ pip3 install --user --upgrade-strategy eager pretalx==1.2.3

.. _installing-a-commit:

Installing a commit or a branch version
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you’re sure that you know what you’re doing, you can also install a specific
commit or branch of pretalx. You can replace ``main`` with a short or long
commit ID for a specific commit::

    (env)$ pip3 install --user --upgrade-strategy eager -U "git+https://github.com/pretalx/pretalx.git@main#egg=pretalx"

.. _blog: https://pretalx.com/p/news/
.. _GitHub: https://github.com/pretalx/pretalx/releases
.. _PyPI: https://pypi.org/project/pretalx/#history
