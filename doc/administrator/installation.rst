.. _installation:

Installation
============

This guide will help you to install pretalx on a single Linux server.
This setup is suitable to support events in usual sizes, but the guide does not
go into performance tuning or customisation options beyond the standard
settings.

.. warning:: Even though we try to make it straightforward to run pretalx, it
             still requires some Linux experience to get it right, particularly
             to make sure that standard security practices are followed. If
             you’re not feeling comfortable managing a Linux server, check
             out our hosting and service offers at `pretalx.com`_.

For the more automation-savvy, we also provide an `Ansible role`_ that follows
this guide. If you prefer working with Docker, there is a `Docker setup`_.
Please note that the Docker setup is community provided and not officially
supported.

Step 0: Requirements
--------------------

To install pretalx, you will need to provide the following dependencies:

* **Python 3.10 or newer**
* Access to an SMTP server to send out mails
* A periodic task runner like ``cron``
* A database: pretalx supports `PostgreSQL`_ 14+ and SQLite 3. For production
  setups, we highly recommend using PostgreSQL.
* A reverse proxy like nginx to allow HTTPS connections and serve
  files from the filesystem
* A `redis`_ server. You can technically run pretalx without it, but you will
  experience major performance problems, as redis is used for caching and to
  run asynchronous tasks.
* `nodejs`_ and npm (usually bundled with nodejs). You’ll need a `supported
  version of nodejs`_.

.. highlight:: console

Please ensure that the environment used to run pretalx is configured to work
with non-ASCII file names. You can check this by running::

    $ python -c "import sys; print(sys.getfilesystemencoding())"
    utf-8

Step 1: Unix user
-----------------

As we do not want to run pretalx as root, we first create a new unprivileged user::

    # adduser pretalx --disabled-password --home /var/pretalx

In this guide, all code lines prepended with a ``#`` symbol are commands that
you need to execute on your server as the ``root`` user (e.g. using ``sudo``);
you should run all lines prepended with a ``$`` symbol as the ``pretalx`` user.
If the prompt reads ``(env)$``, your virtual Python environment should be
active.

Step 2: Database setup
----------------------

pretalx runs with PostgreSQL or SQLite. If you’re using SQLite, you can skip
this step, as there is no need to set up the database – but we highly recommend
that you use PostgreSQL for any production setup.

You will need a database and a user with full access to it. You can set them
up like this, for example::

  # sudo -u postgres createuser pretalx -P
  # sudo -u postgres createdb -O pretalx pretalx

Make sure that your database encoding is UTF-8. You can check with the
following command::

  # sudo -u postgres psql -c 'SHOW SERVER_ENCODING'


Step 3: Package dependencies
----------------------------

Besides the packages above, you will need local system packages to build and
run pretalx. We cannot maintain an up-to-date dependency list for all Linux
flavours – on Ubuntu-like systems, you will need packages like:

- ``build-essential``
- ``libssl-dev``
- ``python3-dev``
- ``python3-venv``
- ``gettext``


Step 4: Configuration
---------------------

.. highlight:: console

Now we’ll create a configuration directory and configuration file for pretalx::

    # mkdir /etc/pretalx
    # touch /etc/pretalx/pretalx.cfg
    # chown -R pretalx:pretalx /etc/pretalx/
    # chmod 0600 /etc/pretalx/pretalx.cfg

This snippet can get you started with a basic configuration in your
``/etc/pretalx/pretalx.cfg`` file:

.. literalinclude:: ../../src/pretalx.example.cfg
   :language: ini

Refer to :ref:`configure` for a full list of configuration options – the
options above are only the ones you’ll likely need to get started.

Step 5: Installation
--------------------

Now we will install pretalx itself – make sure to run the following steps
as the ``pretalx`` user.

Before we actually install pretix, we will create a virtual environment to
isolate the python packages from your global Python installation. You only have
to run the following command once, but when your Python version changes (e.g.
because you upgraded from Python 3.13 to 3.14), you will need to remove the old
``venv`` directory and create it again the same way::

    $ python3 -m venv /var/pretalx/venv

Now, activate the virtual environment – you’ll have to run this command once
per session whenever you’re interacting with ``python``, ``pip`` or
``pretalx``::

    $ source /var/pretalx/venv/bin/activate

Now, upgrade your pip and then install the required Python packages::

    (venv)$ python -m pip install -U pip setuptools wheel gunicorn

+-----------------+---------------------------------------------------------------------------+
| Database        | Command                                                                   |
+=================+===========================================================================+
| SQLite          | ``python -m pip install --upgrade-strategy eager -U pretalx``             |
+-----------------+---------------------------------------------------------------------------+
| PostgreSQL      | ``python -m pip install --upgrade-strategy eager -U "pretalx[postgres]"`` |
+-----------------+---------------------------------------------------------------------------+

If you intend to run pretalx with asynchronous task runners or with redis as
cache server, you can add ``[redis]`` to the installation command, which will
pull in the appropriate dependencies. Please note that you should also use
``pretalx[redis]`` when you upgrade pretalx in this case.

Next, check that your configuration is ready for production::

    (venv)$ python -m pretalx check --deploy

Now compile static files and translation data and create the database structure::

    (venv)$ python -m pretalx migrate
    (venv)$ python -m pretalx rebuild

Finally, create a user with administrator rights, an organiser and a team by running::

    (venv)$ python -m pretalx init

Step 6: Starting pretalx as a service
-------------------------------------

.. highlight:: ini

We recommend starting pretalx using systemd to make sure it starts up after a
reboot. Create a file named ``/etc/systemd/system/pretalx-web.service``, and
adjust the content to fit your system::

    [Unit]
    Description=pretalx web service
    After=network.target

    [Service]
    User=pretalx
    Group=pretalx
    WorkingDirectory=/var/pretalx
    ExecStart=/var/pretalx/venv/bin/gunicorn pretalx.wsgi \
                          --name pretalx --workers 4 \
                          --max-requests 1200  --max-requests-jitter 50 \
                          --log-level=info --bind=127.0.0.1:8345
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target

pretalx optionally runs with Celery, a service that allows for long-running
tasks (like sending many emails) to be performed asynchronously in the
background. We strongly recommend running pretalx with Celery workers, as some
things, like cleaning up unused files, are otherwise not going to work.

To run Celery workers, you’ll need a second service
``/etc/systemd/system/pretalx-worker.service`` with the following content::

    [Unit]
    Description=pretalx background worker
    After=network.target

    [Service]
    User=pretalx
    Group=pretalx
    WorkingDirectory=/var/pretalx
    ExecStart=/var/pretalx/venv/bin/celery -A pretalx.celery_app worker -l info
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target

.. highlight:: console

You can now run the following commands to enable and start the services::

    # systemctl daemon-reload
    # systemctl enable pretalx-web pretalx-worker
    # systemctl start pretalx-web pretalx-worker


Step 7: Provide periodic tasks
------------------------------

There are a couple of things in pretalx that should be run periodically. It
does not matter how you run them, so you can go with your choice of periodic
tasks, be they systemd timers, cron, or something else entirely.

In the same environment as you ran the previous pretalx commands (e.g. the
``pretalx`` user, using either the executable paths in the
``/var/pretalx/venv`` directory, or running ``/var/pretalx/venv/bin/activate``
first), you should run

- ``python -m pretalx runperiodic`` somewhere every five minutes and once per hour.
- ``python -m pretalx clearsessions`` about once a month.

You could for example configure the ``pretalx`` user cron like this::

  */10 * * * * /var/pretalx/venv/bin/python -m pretalx runperiodic


Step 8: Reverse proxy
---------------------

You’ll need to set up an HTTP reverse proxy to handle HTTPS connections. It
does not particularly matter which one you use, as long as you make sure to use
`strong encryption settings`_. Your proxy should

* serve all requests exclusively over HTTPS,
* follow established security practices regarding protocols and ciphers,
* optionally set best-practice headers like ``Referrer-Policy`` and
  ``X-Content-Type-Options``,
* set the ``X-Forwarded-For`` and ``X-Forwarded-Proto`` headers,
* set the ``Host`` header,
* serve all requests for the ``/static/`` and ``/media/`` paths from the
  directories you set up in the previous step, without permitting directory
  listings or traversal. Files in the ``/media/`` directory should be served
  as attachments. You can use fairly aggressive cache settings for these URLs, and
* pass all other requests to the gunicorn server you set up in the previous step.


Step 9: Check the installation
-------------------------------

You can make sure the web interface is up and look for any issues with::

    # journalctl -u pretalx-web

If you use Celery, you can do the same for the worker processes (for example in
case the emails are not sent)::

    # journalctl -u pretalx-worker

If you’re looking for errors, check the pretalx log. You can find the logging
directory in the start-up output.

Once pretalx is up and running, you can also find up to date administrator information
at https://pretalx.example.org/orga/admin/.

Next Steps
----------

You made it! You should now be able to reach pretalx at
https://pretalx.example.org/orga/ Log in with the administrator account you
configured above, and create your first event!

Check out :ref:`configure` for details on the available configuration options,
and read the :ref:`maintenance` documentation!

.. _Ansible role: https://github.com/pretalx/ansible-pretalx
.. _Let’s Encrypt: https://letsencrypt.org/
.. _PostgreSQL: https://www.postgresql.org/docs/
.. _redis: https://redis.io/docs/latest/
.. _ufw: https://en.wikipedia.org/wiki/Uncomplicated_Firewall
.. _strong encryption settings: https://mozilla.github.io/server-side-tls/ssl-config-generator/
.. _Docker setup: https://github.com/pretalx/pretalx-docker
.. _pretalx.com: https://pretalx.com/p/about/
.. _nodejs: https://github.com/nodesource/distributions/blob/master/README.md
.. _supported version of nodejs: https://nodejs.org/en/about/previous-releases
