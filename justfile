# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: Apache-2.0

set shell := ["bash", "-euo", "pipefail", "-c"]
set quiet

python := "uv run python"
uv_dev := "uv run --extra=dev"
uv_devdocs := "uv run --extra=devdocs"
src_dir := "src"

[private]
default:
    just --list

# Install dependencies (use --extras to include e.g. dev, devdocs, postgres)
[group('development')]
install *args:
    # Use --inexact so locally-installed plugins (via `just install-plugin`) and
    # their transitive deps survive the sync.
    uv sync --inexact {{ args }}

# Install all dependencies (dev, devdocs, postgres)
[group('development')]
install-all:
    uv sync --inexact --all-extras
    just install-npm

# Upgrade locked dependencies to their latest compatible versions
[group('development')]
upgrade *args:
    uv lock --upgrade
    uv sync --inexact {{ args }}

# Set up development environment (install deps, database, test event, start server)
[group('development')]
dev-setup: install-all
    just run collectstatic --noinput
    just run compilemessages
    just run migrate
    just run createsuperuser
    uv pip install faker
    just run create_test_event
    just run

# Install npm dependencies for the frontend apps
[group('development')]
[working-directory("src/pretalx/frontend")]
install-npm:
    npm ci

# Install/refresh npm dependencies and regenerate the lockfile
[group('development')]
[working-directory("src/pretalx/frontend")]
install-npm-update:
    npm install

# Run an npm script in the frontend project (e.g. `just npm build:wc`)
[group('development')]
[working-directory("src/pretalx/frontend")]
[positional-arguments]
npm *args:
    npm run "$@"

# Run the public schedule app dev server / widget test harness
[group('development')]
[working-directory("src/pretalx/frontend")]
dev-schedule:
    npm run dev:schedule

# Install a plugin
[group('development')]
install-plugin path:
    uv pip install -e {{ path }}

# Install every plugin in PATH
[group('development')]
install-plugins path:
    #!/usr/bin/env bash
    {{ assert(path_exists(path) == "true", path + " does not exist") }}
    set -euo pipefail
    shopt -s nullglob
    for d in {{ path }}/*/; do
        if [ -f "${d}pyproject.toml" ]; then
            just install-plugin "$d"
        fi
    done

# Check for outdated dependencies
[group('development')]
[script('python3')]
deps-outdated:
    import json, subprocess, tomllib
    from packaging.requirements import Requirement

    result = subprocess.run(['uv', 'pip', 'list', '--outdated', '--format=json'], capture_output=True, text=True)
    outdated = {p['name'].lower(): p for p in json.loads(result.stdout)}
    deps = tomllib.load(open('pyproject.toml', 'rb')).get('project', {}).get('dependencies', [])
    direct = {Requirement(d).name.lower() for d in deps}

    for name in sorted(outdated.keys() & direct):
        p = outdated[name]
        print(f"{p['name']}: {p['version']} → {p['latest_version']}")

# Bump a dependency version
[group('development')]
[script('python3')]
deps-bump package version:
    import subprocess, tomllib
    from pathlib import Path
    from packaging.requirements import Requirement

    p = Path('pyproject.toml')
    deps = tomllib.load(open('pyproject.toml', 'rb')).get('project', {}).get('dependencies', [])
    old = next((d for d in deps if Requirement(d).name.lower() == '{{ package }}'.lower()), None)
    if old:
        req = Requirement(old)
        extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
        p.write_text(p.read_text().replace(old, f'{req.name}{extras}~={{ version }}'))
    subprocess.run(['uv', 'lock', '--upgrade-package', '{{ package }}'])


# Run the development server or other commands, e.g. `just run makemigrations`
[group('development')]
[working-directory("src")]
run *args="devserver --skip-checks":
    {{ python }} manage.py {{ args }}

# Update translation files
[group('development')]
[working-directory("src")]
makemessages:
    just run rebuild --npm-install
    just run makemessages --keep-pot --all

# Run the background task worker
[group('development')]
[working-directory("src")]
worker:
    uv run celery -A pretalx.celery_app worker -l info

# Clean documentation build artifacts
[group('documentation')]
[working-directory("doc")]
@docs-clean:
    rm -rf _build/*

# Build documentation (use `just docs-build dirhtml` for production)
[group('documentation')]
[working-directory("doc")]
docs-build format="html" *args:
    just clean
    {{ uv_devdocs }} python -m sphinx -b {{ format }} -d _build/doctrees . _build/{{ format }} -j auto -a -q {{ args }}

# Build and deploy documentation to a target directory
[group('documentation')]
docs-deploy target:
    just docs-build dirhtml
    rsync -avu --delete doc/_build/dirhtml/ {{ target }}

# Check documentation for broken links
[group('documentation')]
[working-directory("doc")]
docs-linkcheck:
    {{ uv_devdocs }} python -m sphinx -b linkcheck -d _build/doctrees . _build/linkcheck

# Serve the documentation from a live server
[group('documentation')]
[working-directory("doc")]
docs-serve *args="--port 8001":
    rm -rf _build/html
    {{ uv_devdocs }} sphinx-autobuild . _build/html -q {{ args }}

# Update the API documentation
[group('documentation')]
api-docs:
    just run spectacular --color --file ../doc/api/schema.yml

# Check codebase for licensing compliance
[group('linting')]
reuse:
    uvx reuse lint

# Format Django templates with djangofmt.
[group('linting')]
djangofmt *args="":
    # Ignore powered_by.html to keep license warning in grep results
    -{{ uv_dev }} djangofmt \
        --extend-exclude doc \
        --extend-exclude frontend \
        --extend-exclude src/pretalx/common/templates/common/powered_by.html \
        {{ args }} .

[group('linting')]
djangofmt-check:
    just djangofmt
    git diff --exit-code -- '*.html' || (echo "HTML templates are not formatted. Run 'just djangofmt' to fix." && exit 1)

# Run ruff format
[group('linting')]
format *args="":
    {{ uv_dev }} ruff format {{ args }}

# Run ruff check
[group('linting')]
check *args="":
    {{ uv_dev }} ruff check {{ args }}

# Run all formatters and linters
[group('linting')]
[parallel]
fmt: format (check "--fix") djangofmt noqa-reasons-check

# Run all code quality checks
[group('linting')]
fmt-check: (format "--check") check noqa-reasons-check

# Lint and autofix the frontend apps with eslint
[group('linting')]
[working-directory("src/pretalx/frontend")]
fmt-npm:
    npm run lint:fix

# Lint the frontend apps with eslint without autofixing
[group('linting')]
[working-directory("src/pretalx/frontend")]
fmt-npm-check:
    npm run lint

# Check that every `# noqa: PLC0415` carries an allowed reason
[group('linting')]
noqa-reasons-check:
    {{ python }} tools/check_plc0415_reasons.py

# Check for untrimmed blocktranslate tags
[group('linting')]
blocktranslate-check:
    ! git grep ' blocktranslate ' -- '*.html' | grep -v trimmed

# Check documentation for spelling errors
[group('documentation')]
[working-directory("doc")]
docs-spelling:
    {{ uv_devdocs }} python -m sphinx -b spelling -d _build/doctrees . _build/spelling
    ! find _build -type f -name '*.spelling' | grep -q .

# Run most CI checks
[group('tests')]
ci: fmt reuse blocktranslate-check docs-spelling (run "compilemessages") install-npm release-check-package test-parallel && _ci-done

[private]
_ci-done:
    echo '{{ GREEN }}All CI checks passed{{ NORMAL }}'

# Open Django shell scoped to a specific event if given
[group('development')]
[no-exit-message]
shell event="" *args:
    just run shell {{ if event == "" { "--unsafe-disable-scopes" } else { "--event " + event } }} {{ args }}

# Open Django shell with all scopes disabled (unsafe, full database access)
[group('development')]
[no-exit-message]
[positional-arguments]
[working-directory("src")]
python *args:
    {{ python }} manage.py shell --no-pretalx-information --unsafe-disable-scopes "$@"

# Remove Python caches, build artifacts, and coverage reports
[group('development')]
clean:
    -find . -type d -name __pycache__ -exec rm -rf {} +
    -find . -type f -name "*.pyc" -delete
    -find . -type d -name "*.egg-info" -exec rm -rf {} +
    -rm -rf .pytest_cache .coverage htmlcov dist build
    -just docs-clean

# Run the test suite
[group('tests')]
[positional-arguments]
test *args:
    {{ uv_dev }} --extra=devdocs pytest "$@"; status=$?; git checkout -- src/pretalx/locale; exit $status

# Run tests in parallel (requires pytest-xdist)
[group('tests')]
[positional-arguments]
test-parallel n="auto" *args:
    shift; just test -n {{ n }} "$@"

# Run tests with coverage report
[group('tests')]
[positional-arguments]
test-coverage *args:
    just test --cov=src --cov-report=term-missing:skip-covered --cov-config=pyproject.toml "$@"

# Show test coverage report in browser
[group('tests')]
test-coverage-report: test-coverage
    #!/usr/bin/env sh
    if [ -f "src/htmlcov/index.html" ]; then
        open src/htmlcov/index.html 2>/dev/null || \
        xdg-open src/htmlcov/index.html 2>/dev/null || \
        echo "Coverage report: src/htmlcov/index.html"
    else
        echo "No coverage report found. Run just test-coverage first."
    fi

# Verify the built wheel is well-formed (check-manifest, twine, contents)
[group('release')]
release-check-package:
    uv pip install check-manifest twine wheel
    uv run check-manifest
    rm -rf dist
    {{ python }} -m build
    uv run twine check dist/*
    unzip -l dist/pretalx*whl > dist/.wheel-list.txt
    grep -q frontend dist/.wheel-list.txt || { echo "frontend source missing from the wheel"; exit 1; }
    grep -q node_modules dist/.wheel-list.txt && { echo "node_modules leaked into the wheel"; exit 1; } || true
    grep -q 'pretalx/frontend/schedule-editor/dist/pretalx-manifest.json' dist/.wheel-list.txt || { echo "prebuilt schedule editor bundle missing from the wheel"; exit 1; }
    grep -q 'pretalx/static/agenda/js/pretalx-schedule.min.js' dist/.wheel-list.txt || { echo "schedule widget missing from the wheel"; exit 1; }
    grep -q 'pretalx/static.dist/' dist/.wheel-list.txt && { echo "collected static.dist must not ship in the wheel (operators run rebuild)"; exit 1; } || true
    echo "{{ GREEN }}All release checks successful{{ NORMAL }}"

# Verify a clean-tree source rebuild produces a *current* frontend (needs npm)
[group('release')]
release-check-rebuild:
    #!/usr/bin/env bash
    set -euo pipefail
    export PRETALX_FILESYSTEM_STATIC="$PWD/ci_static"
    # Clean up the throwaway STATIC_ROOT on exit, pass or fail.
    trap 'rm -rf "$PRETALX_FILESYSTEM_STATIC"' EXIT
    rm -rf "$PRETALX_FILESYSTEM_STATIC"
    # Wipe the generated frontend so this is a genuine clean-tree,
    # single-`rebuild` test: with npm present it must build the editor
    # straight into STATIC_ROOT *and* build+collect the widget in one
    # pass. If rebuild collected before building (the historical bug),
    # the freshly built widget would never reach STATIC_ROOT.
    rm -f src/pretalx/static/agenda/js/pretalx-schedule.min.js
    rm -rf src/pretalx/frontend/schedule-editor/dist
    just run rebuild
    # Widget: built into the source static dir, then collected. The
    # collected copy must match the freshly built one (currency, not
    # just presence).
    test -f src/pretalx/static/agenda/js/pretalx-schedule.min.js
    test -f "$PRETALX_FILESYSTEM_STATIC/agenda/js/pretalx-schedule.min.js"
    cmp src/pretalx/static/agenda/js/pretalx-schedule.min.js \
        "$PRETALX_FILESYSTEM_STATIC/agenda/js/pretalx-schedule.min.js"
    # Editor: manifest-based Vite build straight into STATIC_ROOT.
    test -f "$PRETALX_FILESYSTEM_STATIC/pretalx-manifest.json"
    echo "{{ GREEN }}Clean-tree rebuild check successful{{ NORMAL }}"

# Build a venv from the wheel and verify it ships bundles + rebuilds without npm
[group('release')]
release-check-wheel:
    #!/usr/bin/env bash
    set -euo pipefail
    VENV="$PWD/test_venv"
    # Smoke-test the installed wheel against a throwaway data dir so a
    # local run never touches a developer's configured database, and a
    # throwaway STATIC_ROOT for the npm-less rebuild below.
    export PRETALX_DATA_DIR="$PWD/wheel_data"
    export PRETALX_FILESYSTEM_STATIC="$PWD/wheel_static"
    # Clean up all scratch artifacts on exit, pass or fail.
    trap 'rm -rf "$VENV" "$PRETALX_DATA_DIR" "$PRETALX_FILESYSTEM_STATIC"' EXIT
    rm -rf "$VENV" "$PRETALX_DATA_DIR" "$PRETALX_FILESYSTEM_STATIC"
    python3 -m venv "$VENV"
    . "$VENV/bin/activate"
    pip install dist/pretalx*whl
    python -m pretalx help
    python -m pretalx migrate
    SITE_PACKAGES="$(python -c 'import pretalx, os; print(os.path.dirname(pretalx.__file__))')"
    # The wheel must ship the prebuilt editor bundle and the source
    # widget, but NOT a collected static.dist (operators run rebuild).
    test -f "$SITE_PACKAGES/frontend/schedule-editor/dist/pretalx-manifest.json"
    test -f "$SITE_PACKAGES/static/agenda/js/pretalx-schedule.min.js"
    ! test -e "$SITE_PACKAGES/static.dist"
    # PRETALX_FILESYSTEM_STATIC is a fresh, empty STATIC_ROOT (wiped at
    # the top), so the assertions below genuinely exercise the npm-less
    # path: if it were broken the dir would stay empty and they'd fail.
    #
    # The venv's bin dir has python but never npm, and is npm-free on
    # every host (unlike a system PATH), so this proves the prebuilt
    # frontend is used without invoking npm.
    NPM_FREE_PATH="$VENV/bin"
    if PATH="$NPM_FREE_PATH" command -v npm; then
      echo "npm unexpectedly present on the restricted PATH; the no-npm check would be meaningless"
      exit 1
    fi
    PATH="$NPM_FREE_PATH" python -m pretalx rebuild
    # Editor copied verbatim into STATIC_ROOT; widget collected there.
    test -f "$PRETALX_FILESYSTEM_STATIC/pretalx-manifest.json"
    test -f "$PRETALX_FILESYSTEM_STATIC/staticfiles.json"
    test -f "$PRETALX_FILESYSTEM_STATIC/agenda/js/pretalx-schedule.min.js"
    cmp "$SITE_PACKAGES/frontend/schedule-editor/dist/pretalx-manifest.json" \
        "$PRETALX_FILESYSTEM_STATIC/pretalx-manifest.json"
    cmp "$SITE_PACKAGES/static/agenda/js/pretalx-schedule.min.js" \
        "$PRETALX_FILESYSTEM_STATIC/agenda/js/pretalx-schedule.min.js"
    echo "{{ GREEN }}Installed-wheel checks successful{{ NORMAL }}"

# Run the full release verification suite (matches CI exactly)
[group('release')]
release-check-all: release-check-package release-check-rebuild release-check-wheel
    echo "{{ GREEN }}All release verification successful{{ NORMAL }}"

# Set __version__ in src/pretalx/__init__.py
[private]
[script('python3')]
_set-version new_version:
    import re
    from pathlib import Path
    init = Path('src/pretalx/__init__.py')
    text, n = re.subn(r'__version__ = "[^"]+"', f'__version__ = "{{ new_version }}"', init.read_text(), 1)
    if n != 1:
        raise SystemExit(f"Could not find __version__ in {init}")
    init.write_text(text)

# Insert a :release: entry at the top of the changelog
[private]
[script('python3')]
_changelog-entry version:
    from datetime import date
    from pathlib import Path

    version = '{{ version }}'
    parts = version.split('.')
    slug = f'{parts[0]}-{parts[1]}-0'
    prefix = f'Bugfix release for pretalx {parts[0]}.{parts[1]}. ' if len(parts) >= 3 and parts[2].isdigit() and parts[2] != '0' else ''
    entry = f'- :release:`{version} <{date.today().isoformat()}>` {prefix}See the `release blog post <https://pretalx.com/p/news/releasing-pretalx-{slug}/>`_.\n'

    changelog = Path('doc/changelog.rst')
    marker = 'For already released changes, head over here:\n\n'
    body = changelog.read_text()
    if marker not in body:
        raise SystemExit(f"Could not find marker in {changelog}")
    changelog.write_text(body.replace(marker, marker + entry, 1))

# Compute the next-minor .dev0 version following the given release version
[private]
[script('python3')]
_next-dev-version version:
    parts = '{{ version }}'.split('-')[0].split('.')
    print(f'{parts[0]}.{int(parts[1]) + 1}.0.dev0')

# Release a new pretalx version (tag form: v2026.1.0)
[group('release')]
[confirm("This will publish to PyPI and push tags. Continue?")]
[arg('version', pattern='v\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?')]
release version:
    uv pip install build check-manifest twine wheel
    just _set-version {{ trim_start_match(version, "v") }}
    just _changelog-entry {{ trim_start_match(version, "v") }}
    git commit -am "Release {{ version }}"
    git tag -m "Release {{ version }}" {{ version }}
    rm -rf dist/ build/ pretalx.egg-info
    {{ python }} -m build -n
    uvx twine upload dist/pretalx-*
    just _set-version "$(just _next-dev-version {{ trim_start_match(version, "v") }})"
    git commit -am "Bump development version"
    git push --follow-tags
    gh release create {{ version }} --verify-tag --title "Release {{ version }}" --notes "[Blog post](https://pretalx.com/p/news/releasing-pretalx-$(echo "{{ trim_start_match(version, "v") }}" | cut -d. -f1-2 | tr . -)-0/)" dist/pretalx-*
