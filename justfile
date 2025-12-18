# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: Apache-2.0

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

# Install all dependencies (dev, devdocs, postgres, redis)
[group('development')]
[working-directory("src/pretalx/frontend/schedule-editor/")]
install-npm:
    npm ci

# Install a plugin
[group('development')]
install-plugin path="":
    uv pip install -e {{ path }}

# Run the development server or other commands, e.g. `just run makemigrations`
[group('development')]
[working-directory("src")]
run *args="runserver --skip-checks":
    uv run python manage.py {{ args }}

# Update translation files
[group('development')]
[working-directory("src")]
makemessages:
    just run collectstatic --npm-install
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

# Check codebase for licensing problems
[group('linting')]
reuse:
    uv run reuse lint

# Format code with black
[group('linting')]
black *args="src":
    uv run --extra=dev black {{ args }}

# Check code with black (check only)
[group('linting')]
black-check *args="src":
    just black --check {{ args }}

# Check import sorting with isort (check only)
[group('linting')]
isort-check *args="src":
    just isort --check {{ args }}

# Sort imports with isort
[group('linting')]
isort *args="src":
    uv run --extra=dev isort {{ args }}

# Run flake8 linter
[group('linting')]
flake8 *args="src":
    uv run --extra=dev flake8 {{ args }}

# Check Django templates with djhtml (check only)
[group('linting')]
djhtml-check:
    just djhtml --check

# Format Django templates with djhtml
[group('linting')]
djhtml *args="src":
    find {{ args }} -name "*.html" -not -path '*/vendored/*' -not -path '*/node_modules/*' -not -path '*/htmlcov/*' -not -path '*/local/*' -not -path '*dist/*' -not -path "*.min.html" -not -path '*/pretalx-schedule' -print | xargs uv run --extra=dev djhtml

# Run all formatters and linters
[group('linting')]
fmt: black isort djhtml flake8

# Run all code quality checks
[group('linting')]
check: black-check isort-check djhtml-check flake8

# Open Django shell with access to all events
[group('development')]
shell event="" *args:
    just run shell --event {{ event }} {{ args }}

# Open Django shell with access to all events
[group('development')]
unsafe-shell *args:
    just run shell --unsafe-disable-scopes {{ args }}

# Clean up generated files
[group('development')]
clean:
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    rm -rf .pytest_cache
    rm -rf .coverage htmlcov
    rm -rf dist build

# Run the test suite
[group('tests')]
test *args:
    uv run --extra=dev --extra=devdocs pytest {{ args }}

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
[working-directory("src")]
test-coverage-report: test-coverage
    open htmlcov/index.html || xdg-open htmlcov/index.html || echo "Coverage report generated in htmlcov/index.html"

# Run release checks
[group('release')]
release-checks:
    uv run check-manifest
    uv run python -m build
    uv run twine check dist/*
    unzip -l dist/pretalx*whl | grep frontend || exit 1
    unzip -l dist/pretalx*whl | grep node_modules && exit 1 || exit 0
    echo "All release checks successful"

# Release a new pretalx version
[group('release')]
release version:
    uv pip install build
    git commit -am "Release {{ version }}"
    git tag -m "Release {{ version }}" {{ version }}
    rm -rf dist/ build/ pretalx.egg-info
    uv run python -m build -n
    uvx twine upload dist/pretalx-*
    git push
    git push --tags
