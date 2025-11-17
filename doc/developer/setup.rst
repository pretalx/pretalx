.. SPDX-FileCopyrightText: 2017-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _`devsetup`:

The development setup
=====================

To contribute to pretalx, it’s useful to run pretalx locally on your device so you can test your
changes. First of all, you need install some packages on your operating system:

If you want to install pretalx on a server for actual usage, go to the :ref:`administrator-index`
instead.

External dependencies
---------------------

Please make sure you have the following dependencies installed:

+----------------------------------+------------------+
| Tool                             | Debian package   |
+==================================+==================+
| Python 3.10(!) or newer          |                  |
+----------------------------------+------------------+
| ``python-dev`` for Python 3      | ``python3-dev``  |
+----------------------------------+------------------+
| libffi                           | ``libffi-dev``   |
+----------------------------------+------------------+
| gettext                          | ``gettext``      |
+----------------------------------+------------------+
| git                              | ``git``          |
+----------------------------------+------------------+

Some Python dependencies might also need a compiler during installation, the Debian package
``build-essential`` or something similar should suffice.

Additionally, please install ``uv``. See the `uv installation guide`_ on how to do this,
and `just`_.

Get a copy of the source code
-----------------------------
You can clone our git repository::

    git clone https://github.com/pretalx/pretalx.git
    cd pretalx/


Working with the code
---------------------

First up, install all the main application dependencies::

    $ just install --extra dev

You can also run ``just install-all`` to include dependencies for
PostgreSQL, Redis, and building the documentation.

Next, you will have to copy the static files from the source folder to the
STATIC_ROOT directory, and create the local database::

    $ just run collectstatic --noinput
    $ just run migrate

To be able to log in, you should also create an admin user, organiser and team by running::

    $ just run init

Additionally, if you want to get started with an event right away, run the ``create_test_event`` command::

    $ just run create_test_event

This command will create a test event for you, with a set of test submissions,
and speakers, and the like.  With the ``--stage`` flag, you can determine which
stage the event in question should be in. The available choices are ``cfp``
(CfP still open, plenty of submissions, but no reviews), ``review``
(submissions have been reviewed and accepted/rejected), ``schedule`` (there is
a schedule and the event is currently running), and ``over``. ``schedule`` is
the default value.

If you want to see pretalx in a different language than English, you have to compile our language
files::

    $ just run compilemessages

If you need to test more complicated features, you should probably look into the
:doc:`setup</administrator/installation>` documentation to find the bits and pieces you
want to add to your development setup.

Run the development server
^^^^^^^^^^^^^^^^^^^^^^^^^^
To run the local development server, execute::

    $ just run

Now point your browser to http://127.0.0.1:8000/orga/ – You should be able to log in and use
all sites except those that use big custom JavaScript components, like the schedule editor.
In order to use those, you have two options – in any case, you will need to have ``node`` and
``npm`` installed on your system.

If you just need to use the JavaScript component, but don't need to change it,
compile the JavaScript files::

    $ just run rebuild --npm-install

If you want to change the JavaScript code, you can run the following command, which combines
the Python and the JavaScript development servers::

    $ just run devserver

.. _`checksandtests`:

Code checks and unit tests
^^^^^^^^^^^^^^^^^^^^^^^^^^
Before you check in your code into git, always run the static linters and style checkers::

    $ just fmt

Once you're done with those, run the tests::

    $ just test

Pytest, our test framework, has a lot of useful options, like ``--lf`` to repeat only failing
tests, ``-k something`` to run only tests called ``*something*``, and ``-x`` to stop on the
first breaking test.

.. note:: If you have more than one CPU core and want to speed up the test suite, you can run
          ``just test-parallel`` (with an optional ``NUM`` parameter to specify the number of
          threads, which you can leave empty for an automatic choice.)

Working with mails
^^^^^^^^^^^^^^^^^^

When running in development mode, Pretalx uses Django’s console email backend.
This means the development server will print any emails to its stdout, instead
of sending them via SMTP.

If you want to test sending event emails via a custom SMTP server, we recommend
starting Python’s debugging SMTP server in a separate shell::

    uv run python -m smtpd -n -c DebuggingServer localhost:1025

You can use this server by specifying host ``localhost`` and port ``1025`` in
the event email settings.

.. _`developer-translations`:

Working with translations
^^^^^^^^^^^^^^^^^^^^^^^^^
If you want to translate new strings that are not yet known to the translation system, you will
first include them in the ``.po`` files. As we share translations between both the JavaScript
frontend and the Python backend, you'll need to install the frontend dependencies first::

    $ cd src/pretalx/frontend/schedule-editor
    $ npm ci

Then, use the following command to scan the source code for strings we want to
translate and update the ``*.po`` files accordingly::

    $ just makemessages

To actually see pretalx in your language, you have to compile the ``*.po`` files to their optimised
binary ``*.mo`` counterparts::

    $ just run compilemessages

pretalx by default supports events in English, German, or French, or all three. To translate
pretalx to a new language, add the language code and natural name to the ``LANGUAGES`` variable in
the ``settings.py``. Depending on the completeness of your changes, and your commitment to maintain
them in the future, we can talk about merging them into core.


Working with the documentation
------------------------------

To build the documentation, the documentation dependencies will already be installed if you ran
``uv sync --all-extras`` earlier. If not, you can install them by running::

    $ uv sync --extra devdocs

Then, go to the ``doc`` directory and run ``make html`` to build the documentation::

    $ just docs

You will now find the generated documentation in the ``doc/_build/html/`` subdirectory.
If you find yourself working with the documentation more than a little, give the ``autobuild``
functionality a try::

    $ just serve-docs

Then, go to http://localhost:8001 for a version of the documentation that
automatically re-builds when you save a changed source file.
Please note that changes in the static files (stylesheets and JavaScript) will only be reflected
after a restart.

.. _uv installation guide: https://docs.astral.sh/uv/getting-started/installation/
.. _just: https://github.com/casey/just
