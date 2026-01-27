# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: Apache-2.0

set shell := ["bash", "-euo", "pipefail", "-c"]

_ := require("uv")
python := "uv run python"
uv_dev := "uv run --extra=dev"
src_dir := "src"

[private]
default:
    @just --list

# Install dependencies (use --extras to include e.g. dev, devdocs, postgres, redis)
[group('development')]
install *args:
    uv lock --upgrade
    uv sync {{ args }}

# Install all dependencies (dev, devdocs, postgres, redis)
[group('development')]
install-all:
    uv lock --upgrade
    uv sync --all-extras

# Install npm dependencies for the schedule editor frontend
[group('development')]
[working-directory("src/pretalx/frontend/schedule-editor/")]
install-npm:
    npm ci

# Install a plugin
[group('development')]
install-plugin path="":
    uv pip install -e {{ path }}

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
        p.write_text(p.read_text().replace(old, f'{Requirement(old).name}~={{ version }}'))
    subprocess.run(['uv', 'lock', '--upgrade-package', '{{ package }}'])


# Run the development server or other commands, e.g. `just run makemigrations`
[group('development')]
[working-directory("src")]
run *args="runserver --skip-checks":
    {{ python }} manage.py {{ args }}

# Update translation files
[group('development')]
[working-directory("src")]
makemessages:
    just run rebuild --npm-install
    just run makemessages --keep-pot --all

# Build the documentation
[group('documentation')]
[working-directory("doc")]
docs *args="html":
    uv run make {{ args }}

# Serve the documentation from a live server
[group('documentation')]
[working-directory("doc")]
docs-serve *args="--port 8001":
    rm -rf _build/html
    uv run sphinx-autobuild . _build/html {{ args }}

# Update the API documentation
[group('documentation')]
api-docs:
    just run spectacular --color --file ../doc/api/schema.yml

# Check codebase for licensing compliance
[group('linting')]
@reuse:
    uvx reuse lint

# Format code with black
[group('linting')]
black *args=src_dir:
    {{ uv_dev }} black {{ args }}

# Check code with black (check only)
[group('linting')]
black-check *args=src_dir:
    just black --check {{ args }}

# Check import sorting with isort (check only)
[group('linting')]
isort-check *args=src_dir:
    just isort --check {{ args }}

# Sort imports with isort
[group('linting')]
isort *args=src_dir:
    {{ uv_dev }} isort {{ args }}

# Run flake8 linter
[group('linting')]
flake8 *args=src_dir:
    {{ uv_dev }} flake8 {{ args }}

# Check Django templates with djhtml (check only)
[group('linting')]
djhtml-check:
    just djhtml --check

# Format Django templates with djhtml
[group('linting')]
djhtml *args="":
    find src -name "*.html" -not -path '*/vendored/*' -not -path '*/node_modules/*' -not -path '*/htmlcov/*' -not -path '*/local/*' -not -path '*dist/*' -not -path "*.min.html" -not -path '*/pretalx-schedule' -print | xargs {{ uv_dev }} djhtml {{ args }}

# Run all formatters and linters
[group('linting')]
[parallel]
fmt: black djhtml isort && flake8

# Run all code quality checks
[group('linting')]
[parallel]
check: black-check isort-check djhtml-check flake8 && _check-done

[private]
@_check-done:
    echo '{{ GREEN }}All checks passed{{ NORMAL }}'

# Open Django shell scoped to a specific event
[group('development')]
[no-exit-message]
shell event="" *args:
    just run shell --event {{ event }} {{ args }}

# Open Django shell with all scopes disabled (unsafe, full database access)
[group('development')]
[no-exit-message]
unsafe-shell *args:
    just run shell --unsafe-disable-scopes {{ args }}

# Remove Python caches, build artifacts, and coverage reports
[group('development')]
@clean:
    -find . -type d -name __pycache__ -exec rm -rf {} +
    -find . -type f -name "*.pyc" -delete
    -find . -type d -name "*.egg-info" -exec rm -rf {} +
    -rm -rf .pytest_cache .coverage htmlcov dist build

# Run the test suite
[group('tests')]
test *args:
    {{ uv_dev }} --extra=devdocs pytest {{ args }}
    git checkout -- src/pretalx/locale

# Run tests in parallel (requires pytest-xdist)
[group('tests')]
[working-directory("src")]
test-parallel n="auto" *args:
    just test -n {{ n }} {{ args }}

# Run tests with coverage report
[group('tests')]
[working-directory("src")]
test-coverage *args:
    just test {{ args }}

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

# Run release checks
[group('release')]
release-checks:
    uv run check-manifest
    {{ python }} -m build
    uv run twine check dist/*
    unzip -l dist/pretalx*whl | grep frontend || exit 1
    unzip -l dist/pretalx*whl | grep node_modules && exit 1 || exit 0
    @echo "{{ GREEN }}All release checks successful{{ NORMAL }}"

# Release a new pretalx version
[group('release')]
[confirm("This will publish to PyPI and push tags. Continue?")]
[arg('version', pattern='\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?')]
release version:
    uv pip install build
    git commit -am "Release {{ version }}"
    git tag -m "Release {{ version }}" {{ version }}
    rm -rf dist/ build/ pretalx.egg-info
    {{ python }} -m build -n
    uvx twine upload dist/pretalx-*
    git push
    git push --tags
