#!/bin/bash
# Installed as /usr/local/bin/pretalx, so it also runs when wf-org/infra
# overrides the entrypoint (the cron task calls `pretalx cron`). Applies the
# app config this repository deploys, then hands off to the unchanged
# upstream script (pretalx.bash, from pretalx-docker).
#
#   PRETALX_APP_CONFIG  pretalx.cfg fragment (SSM /pretalx/app/config, from
#                       deploy/prod/pretalx.secrets.enc.ini). Written to
#                       ~/.pretalx.cfg, which pretalx reads after
#                       /etc/pretalx/pretalx.cfg (infra's), so it wins.
#   PRETALX_APP_ENV     KEY=value lines (SSM /pretalx/app/env, from
#                       deploy/prod/env). Exported unless already set, so a
#                       task definition's own environment wins.
set -euo pipefail

if [ -n "${PRETALX_APP_CONFIG:-}" ]; then
    (umask 077 && printf '%s\n' "$PRETALX_APP_CONFIG" > /pretalx/.pretalx.cfg)
fi
unset PRETALX_APP_CONFIG

if [ -n "${PRETALX_APP_ENV:-}" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"
        line="${line#"${line%%[![:space:]]*}"}"
        case "$line" in '' | '#'*) continue ;; esac
        line="${line#export }"
        key="${line%%=*}"
        value="${line#*=}"
        if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ && "$line" == *=* ]]; then
            echo "pretalx: ignoring malformed PRETALX_APP_ENV line for '${key}'" >&2
            continue
        fi
        if [[ "$value" =~ ^\"(.*)\"$ || "$value" =~ ^\'(.*)\'$ ]]; then value="${BASH_REMATCH[1]}"; fi
        if [ -z "${!key+x}" ]; then export "$key=$value"; fi
    done <<< "$PRETALX_APP_ENV"
fi
unset PRETALX_APP_ENV

exec /usr/local/lib/pretalx/pretalx.bash "$@"
