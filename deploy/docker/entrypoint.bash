#!/bin/bash
# Installed as /usr/local/bin/pretalx, so it also runs when wf-org/infra
# overrides the entrypoint (the cron task calls `pretalx cron`). Exports the
# app settings this repository deploys, then hands off to the unchanged
# upstream script (pretalx.bash, from pretalx-docker).
#
# Both variables hold KEY=value lines; each key is exported unless it is
# already set, so a task definition's own environment wins.
#   PRETALX_APP_CONFIG  secrets (SSM SecureString /pretalx/app/config, from
#                       deploy/prod/env.secrets.enc). Applied first,
#                       so it wins over PRETALX_APP_ENV.
#   PRETALX_APP_ENV     plain settings (SSM String /pretalx/app/env, from
#                       deploy/prod/env).
# pretalx settings: https://docs.pretalx.org/administrator/configure/
set -euo pipefail

# export_lines <variable name>: export each KEY=value line of that variable.
# Never prints values, since they may be secrets.
export_lines() {
    local source="$1" line key value
    [ -n "${!source:-}" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"
        line="${line#"${line%%[![:space:]]*}"}"
        case "$line" in '' | '#'*) continue ;; esac
        line="${line#export }"
        key="${line%%=*}"
        value="${line#*=}"
        if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ && "$line" == *=* ]]; then
            echo "pretalx: ignoring malformed $source line for '${key}'" >&2
            continue
        fi
        if [[ "$value" =~ ^\"(.*)\"$ || "$value" =~ ^\'(.*)\'$ ]]; then value="${BASH_REMATCH[1]}"; fi
        if [ -z "${!key+x}" ]; then export "$key=$value"; fi
    done <<< "${!source}"
}

export_lines PRETALX_APP_CONFIG
export_lines PRETALX_APP_ENV
unset PRETALX_APP_CONFIG PRETALX_APP_ENV

exec /usr/local/lib/pretalx/pretalx.bash "$@"
