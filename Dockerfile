# Modeled on the community pretalx-docker image:
# https://github.com/pretalx/pretalx-docker/blob/main/Dockerfile
# Differences: installs a pinned pretalx release from PyPI (PRETALX_VERSION)
# instead of a source submodule, so no Node.js; PostgreSQL only (no
# MariaDB/memcached); local plugins from plugins/ and extra pip packages via
# PRETALX_PLUGINS; and `pretalx` is a small wrapper
# (deploy/docker/entrypoint.bash) that exports PRETALX_APP_CONFIG /
# PRETALX_APP_ENV (KEY=value lines from SSM) before running the upstream script.
#
# Runtime contract (used by the ECS task definitions in wf-org/infra):
#   entrypoint `pretalx`; commands webworker | taskworker | cron | all | shell
#   | <any pretalx management command>; config at /etc/pretalx/pretalx.cfg;
#   volumes /etc/pretalx, /data, /public; uid/gid 999.

FROM python:3.14-slim-trixie AS builder

# pretalx release from PyPI. Pinned: bump deliberately, together with the
# `pretalx>=…,<…` range in plugins/*/pyproject.toml (the plugins patch pretalx
# internals and are only tested against one release series).
ARG PRETALX_VERSION=2026.2.1

# Space-separated extra pip requirement specs, e.g. PyPI plugins:
# --build-arg PRETALX_PLUGINS="pretalx-pages==1.6.0"
ARG PRETALX_PLUGINS=""

# Quiet down pip so build logs stay readable.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_NO_INPUT=1 \
    PIP_PROGRESS_BAR=off \
    PRETALX_FILESYSTEM_STATIC=/pretalx/src/static.dist

RUN DEBIAN_FRONTEND=noninteractive apt-get -qq update && \
    DEBIAN_FRONTEND=noninteractive apt-get -qq install -y --no-install-recommends \
        gettext build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Local plugins: every plugins/<name>/ with a pyproject.toml or setup.py.
COPY --chown=root:root plugins /plugins

# One pip resolve for pretalx, the plugins and extras, so a plugin can't
# silently swap in another pretalx (or Django) version: an incompatible
# combination fails the build. Plugins are installed non-editable so they land
# in site-packages, which the runtime stage copies.
RUN set -e; \
    plugins=""; \
    for plugin in /plugins/*/; do \
        if [ -f "$plugin/pyproject.toml" ] || [ -f "$plugin/setup.py" ]; then plugins="$plugins $plugin"; fi; \
    done; \
    pip3 install --no-cache-dir -U pip setuptools wheel && \
    pip3 install --no-cache-dir \
        "pretalx[postgres]==${PRETALX_VERSION}" gunicorn $plugins $PRETALX_PLUGINS && \
    test "$(pip3 show pretalx | sed -n 's/^Version: //p')" = "$PRETALX_VERSION"

# The wheel ships the prebuilt frontend, so no npm is needed. /pretalx/src is
# the working directory of the upstream script and holds the collected static
# files (static.dist), where wf-org/infra expects them.
RUN mkdir -p /pretalx/src && \
    PRETALX_DATA_DIR=/tmp/build-data python3 -m pretalx rebuild && \
    rm -rf /tmp/build-data

FROM python:3.14-slim-trixie

RUN DEBIAN_FRONTEND=noninteractive apt-get -qq update && \
    DEBIAN_FRONTEND=noninteractive apt-get -qq install -y --no-install-recommends \
        gettext locales \
        supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    dpkg-reconfigure locales && \
    locale-gen C.UTF-8 && \
    /usr/sbin/update-locale LANG=C.UTF-8 && \
    mkdir /etc/pretalx /data /public && \
    groupadd -g 999 pretalxuser && \
    useradd -r -u 999 -g pretalxuser -d /pretalx -ms /bin/bash pretalxuser

ENV LC_ALL=C.UTF-8 \
    PRETALX_FILESYSTEM_STATIC=/pretalx/src/static.dist

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/celery /usr/local/bin/
COPY --from=builder --chown=pretalxuser:pretalxuser /pretalx /pretalx

COPY --chown=root:root deploy/docker/pretalx.bash /usr/local/lib/pretalx/pretalx.bash
COPY --chown=root:root deploy/docker/entrypoint.bash /usr/local/bin/pretalx
COPY --chown=root:root deploy/docker/supervisord.conf /etc/supervisord.conf
# pretalx settings plus overrides (database connections closed after each
# request, so an Aurora Serverless cluster can pause); see the module
COPY --chown=root:root deploy/docker/wildfire_settings.py /usr/local/lib/python3.14/site-packages/wildfire_settings.py
ENV DJANGO_SETTINGS_MODULE=wildfire_settings

RUN chmod +x /usr/local/bin/pretalx /usr/local/lib/pretalx/pretalx.bash && \
    chown pretalxuser:pretalxuser /data /public /etc/pretalx

USER pretalxuser

VOLUME ["/etc/pretalx", "/data", "/public"]
EXPOSE 80
ENTRYPOINT ["pretalx"]
CMD ["all"]
