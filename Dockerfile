# Modeled on the community pretalx-docker image:
# https://github.com/pretalx/pretalx-docker/blob/main/Dockerfile
# Differences: built from this repository (not a submodule), PostgreSQL only
# (no MariaDB/memcached), optional extra pip packages via PRETALX_PLUGINS, and
# `pretalx` is a small wrapper (deploy/docker/entrypoint.bash) that applies
# PRETALX_APP_CONFIG / PRETALX_APP_ENV before running the upstream script.
#
# Runtime contract (used by the ECS task definitions in wf-org/infra):
#   entrypoint `pretalx`; commands webworker | taskworker | cron | all | shell
#   | <any pretalx management command>; config at /etc/pretalx/pretalx.cfg;
#   volumes /etc/pretalx, /data, /public; uid/gid 999.

FROM python:3.14-slim-trixie AS builder

# Space-separated pip requirement specs installed alongside pretalx,
# e.g. plugins: --build-arg PRETALX_PLUGINS="pretalx-pages==1.6.0"
ARG PRETALX_PLUGINS=""

# Quiet down pip and npm so build logs stay readable.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_NO_INPUT=1 \
    PIP_PROGRESS_BAR=off \
    NPM_CONFIG_LOGLEVEL=error \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_PROGRESS=false

RUN DEBIAN_FRONTEND=noninteractive apt-get -qq update && \
    DEBIAN_FRONTEND=noninteractive apt-get -qq install -y --no-install-recommends \
        git gettext \
        libpq-dev build-essential \
        nodejs npm && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --chown=root:root pyproject.toml /pretalx/
COPY --chown=root:root _build /pretalx/_build
COPY --chown=root:root src /pretalx/src

RUN pip3 install --no-cache-dir -U pip setuptools wheel && \
    pip3 install --no-cache-dir -e /pretalx/[postgres] && \
    pip3 install --no-cache-dir gunicorn && \
    if [ -n "$PRETALX_PLUGINS" ]; then pip3 install --no-cache-dir $PRETALX_PLUGINS; fi

RUN python3 -m pretalx rebuild && \
    rm -rf /pretalx/src/pretalx.cfg /pretalx/src/data/.secret \
           /pretalx/src/pretalx/frontend/node_modules


FROM python:3.14-slim-trixie

RUN DEBIAN_FRONTEND=noninteractive apt-get -qq update && \
    DEBIAN_FRONTEND=noninteractive apt-get -qq install -y --no-install-recommends \
        gettext locales \
        nodejs npm \
        supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    dpkg-reconfigure locales && \
    locale-gen C.UTF-8 && \
    /usr/sbin/update-locale LANG=C.UTF-8 && \
    mkdir /etc/pretalx /data /public && \
    groupadd -g 999 pretalxuser && \
    useradd -r -u 999 -g pretalxuser -d /pretalx -ms /bin/bash pretalxuser

ENV LC_ALL=C.UTF-8

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/celery /usr/local/bin/
COPY --from=builder --chown=pretalxuser:pretalxuser /pretalx /pretalx

COPY --chown=root:root deploy/docker/pretalx.bash /usr/local/lib/pretalx/pretalx.bash
COPY --chown=root:root deploy/docker/entrypoint.bash /usr/local/bin/pretalx
COPY --chown=root:root deploy/docker/supervisord.conf /etc/supervisord.conf

RUN chmod +x /usr/local/bin/pretalx /usr/local/lib/pretalx/pretalx.bash && \
    chown pretalxuser:pretalxuser /data /public /etc/pretalx

USER pretalxuser

VOLUME ["/etc/pretalx", "/data", "/public"]
EXPOSE 80
ENTRYPOINT ["pretalx"]
CMD ["all"]
