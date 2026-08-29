# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: Apache-2.0

"""Sphinx extension to build a ccbv-style code reference via classify.

We walk the pretalx apps, run classify on every qualified class and function,
and render one detail page per class and per domain module. Only used for
models and domain function for now, because view docs would be near-useless
and forms are weird.
..coderef-index) generates an overview including a search interface."""

import ast
import dataclasses
import functools
import importlib
import inspect
import logging as stdlib_logging
import pkgutil
import re
import textwrap
import time
from html import escape
from json import dumps as json_dumps
from pathlib import Path

import structlog
from docutils import nodes
from docutils.core import publish_from_doctree
from docutils.frontend import get_default_settings
from docutils.parsers.rst import Directive
from docutils.utils import new_document
from docutils.writers.html5_polyglot import Writer as HTML5Writer
from sphinx import addnodes
from sphinx.errors import NoUri
from sphinx.ext.intersphinx import missing_reference as intersphinx_reference
from sphinx.parsers import RSTParser
from sphinx.util import logging
from sphinx.util.docutils import sphinx_domains

logger = logging.getLogger(__name__)

GITHUB_REPO = "pretalx/pretalx"
GITHUB_BRANCH = "main"
INDEX_DOCNAME = "developer/interfaces/reference"
PAGE_PREFIX = "developer/interfaces/reference"

ENABLED_SEGMENTS = ("models", "domain")
MODEL_APPS = ("event", "submission", "schedule", "person", "mail", "common")
EXCLUDED_MODULES = frozenset(
    ("pretalx.common.models.fields", "pretalx.common.models.managers")
)

SEGMENTS = {
    "models": {
        "label": "Models",
        "roots": [f"pretalx.{app}.models" for app in MODEL_APPS],
    },
    "domain": {
        "label": "Domain",
        "roots": [f"pretalx.{app}.domain" for app in MODEL_APPS],
    },
    "interfaces": {
        "label": "Interfaces",
        "roots": [f"pretalx.{app}.interfaces" for app in MODEL_APPS]
        + [
            "pretalx.orga.forms",
            "pretalx.cfp.forms",
            "pretalx.common.forms",
            "pretalx.api.serializers",
        ],
    },
    "views": {
        "label": "Views",
        "roots": [
            "pretalx.orga.views",
            "pretalx.cfp.views",
            "pretalx.agenda.views",
            "pretalx.api.views",
            "pretalx.common.views",
        ],
    },
}
LIBRARY_LABELS = {
    "django": "Django",
    "django_tables2": "django-tables2",
    "formtools": "django-formtools",
    "hierarkey": "hierarkey",
    "i18nfield": "django-i18nfield",
    "rest_flex_fields": "drf-flex-fields",
    "rest_framework": "Django REST framework",
    "rules": "django-rules",
}
# grouping key for members Django adds to a class after the class body ran
GENERATED_GROUP = ("<generated>", "<generated>")

_ROLE_INLINE_RE = re.compile(r":[a-zA-Z0-9_.:+-]+:`([^`]+)`")
_LITERAL_INLINE_RE = re.compile(r"``([^`]+)``|`([^`]+)`")
_SELF_ARG_RE = re.compile(r"^\(self(?:, |(?=\)))")
_RELATIVE_HREF_RE = re.compile(r'href="(?!(?:[a-z][a-z0-9+.-]*:|//|/|#))')


@dataclasses.dataclass
class ClassEntry:
    segment: str
    app: str
    name: str
    module: str
    qualname: str
    pagename: str
    structure: object
    fields: list
    file: str = ""
    start: int = 0
    total: int = 0


@dataclasses.dataclass(frozen=True)
class _Lines:
    start: int
    total: int


@dataclasses.dataclass
class FunctionEntry:
    name: str
    signature: str
    docstring: str
    code: str
    file: str
    start: int
    total: int

    # mimic a classify definition, so _member_row renders functions too
    @property
    def arguments(self):
        return self.signature

    @property
    def lines(self):
        return _Lines(self.start, self.total)


@dataclasses.dataclass
class ModuleEntry:
    app: str
    module: str
    pagename: str
    functions: list


@dataclasses.dataclass
class Registry:
    classes: dict
    modules: list
    pages: dict
    subclasses: dict
    xref: dict
    short_xref: dict
    app: object = None

    @property
    def env(self):
        return self.app.env if self.app is not None else None


def iter_modules(root):
    if root in EXCLUDED_MODULES:
        return
    try:
        mod = importlib.import_module(root)
    except ImportError:
        logger.debug("coderef: no module %s", root)
        return
    yield mod
    if hasattr(mod, "__path__"):
        for info in pkgutil.walk_packages(mod.__path__, prefix=root + "."):
            if info.name in EXCLUDED_MODULES:
                continue
            try:
                yield importlib.import_module(info.name)
            except Exception as e:  # noqa: BLE001 -- arbitrary module import
                logger.warning("coderef: could not import %s: %s", info.name, e)


def describe_function(func):
    func = inspect.unwrap(func)
    try:
        lines, start = inspect.getsourcelines(func)
    except (OSError, TypeError):
        return None
    try:
        signature = str(inspect.signature(func))
    except (ValueError, TypeError):
        signature = "(…)"
    return FunctionEntry(
        name=func.__name__,
        signature=signature,
        docstring=inspect.getdoc(func) or "",
        code="".join(lines),
        file=inspect.getsourcefile(func),
        start=start,
        total=len(lines),
    )


def _field_origin_class(obj, field):
    # Fields get straight-up copied from abstract base classes. The easiest
    # way of finding the correct ancestor is to check creation_counter so we
    # don't have to make sure we get ordering among multiple abstract parents
    # right.
    name = getattr(field, "name", None)
    counter = getattr(field, "creation_counter", None)
    if name is None or counter is None:
        return None
    origin = None
    for klass in obj.__mro__[1:]:
        meta = klass.__dict__.get("_meta")
        if meta is None:
            continue
        try:
            local = list(meta.local_fields) + list(meta.local_many_to_many)
        except Exception:  # noqa: BLE001, S112 -- arbitrary model metadata
            continue
        if any(
            f.name == name and getattr(f, "creation_counter", None) == counter
            for f in local
        ):
            origin = klass
    return origin


def _field_source(klass, name):
    # We want to show the actual field definition, but Django keeps no link
    # to the assignment statement, so we read it directly.
    # Generated fields (e.g. auto pk) do not have a source.
    try:
        lines, class_start = inspect.getsourcelines(klass)
        source = textwrap.dedent("".join(lines))
        dedented = source.splitlines(keepends=True)
        for node in ast.parse(source).body[0].body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
                continue
            return {
                "code": "".join(dedented[node.lineno - 1 : node.end_lineno]),
                "file": inspect.getsourcefile(klass) or "",
                "start": class_start + node.lineno - 1,
                "total": node.end_lineno - node.lineno + 1,
            }
    except Exception:  # noqa: BLE001 -- arbitrary model source
        return {}
    return {}


def model_fields(obj):
    from django.db import models  # noqa: PLC0415 -- optional at import time

    if not (isinstance(obj, type) and issubclass(obj, models.Model)):
        return []
    fields = []
    try:
        meta_fields = obj._meta.get_fields()
    except Exception:  # noqa: BLE001 -- arbitrary model metadata
        return []
    for field in meta_fields:
        related = getattr(field, "related_model", None)
        name = getattr(field, "name", str(field))
        concrete = getattr(field, "concrete", False)
        entry = {
            "name": name,
            "type": type(field).__name__,
            "related": related.__name__ if related else "",
            "related_module": related.__module__ if related else "",
            "concrete": concrete,
            "origin": "",
            "origin_module": "",
            "null": bool(getattr(field, "null", False)),
            "unique": bool(getattr(field, "unique", False)),
            "primary_key": bool(getattr(field, "primary_key", False)),
            "help_text": str(getattr(field, "help_text", "") or ""),
            "code": "",
            "file": "",
            "start": 0,
            "total": 0,
        }
        if concrete:
            origin = _field_origin_class(obj, field)
            if origin is not None:
                entry["origin"] = origin.__name__
                entry["origin_module"] = origin.__module__
            entry.update(_field_source(origin or obj, name))
        fields.append(entry)
    # our fields first, inherited after, reverse relations last
    return sorted(fields, key=lambda f: (not f["concrete"], bool(f["origin"])))


def public_members(mod):
    # Get explicit __all__ or every non-underscore name.
    contents = vars(mod)
    exported = contents.get("__all__")
    if exported is None:
        return [
            (name, obj) for name, obj in contents.items() if not name.startswith("_")
        ]
    members = []
    for name in exported:
        if name not in contents:
            logger.debug("coderef: %s.%s in __all__ but not set", mod.__name__, name)
            continue
        members.append((name, contents[name]))
    return members


def is_orm_helper(obj):
    from django.db import models  # noqa: PLC0415 -- optional at import time

    return issubclass(obj, (models.Manager, models.QuerySet))


def drop_machine_attributes(structure):
    # Ignore dunder methods and attributes, nobody needs to read docs for
    # __hash__, __slotnames__ etc.
    for name in [name for name in structure.attributes if name.startswith("__")]:
        del structure.attributes[name]


def collect_registry():
    from classify.classification import classify  # noqa: PLC0415 -- optional dependency

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(stdlib_logging.WARNING)
    )

    start = time.time()
    classes = {}
    modules = []
    aliases = {}
    for segment in ENABLED_SEGMENTS:
        for root in SEGMENTS[segment]["roots"]:
            app = root.split(".")[1]
            for mod in iter_modules(root):
                functions = []
                for name, obj in public_members(mod):
                    if inspect.isclass(obj) or inspect.isfunction(obj):
                        key = f"{obj.__module__}.{obj.__qualname__}"
                        if obj.__module__ != mod.__name__:
                            aliases.setdefault(key, []).append(f"{mod.__name__}.{name}")
                            continue
                    if inspect.isclass(obj):
                        if key in classes:
                            continue
                        if segment == "models" and is_orm_helper(obj):
                            continue
                        try:
                            structure = classify(obj)
                        except Exception as e:  # noqa: BLE001 -- arbitrary code
                            logger.warning("coderef: could not classify %s: %s", key, e)
                            continue
                        drop_machine_attributes(structure)
                        try:
                            source_lines, source_start = inspect.getsourcelines(obj)
                            source_file = inspect.getsourcefile(obj) or ""
                        except (OSError, TypeError):
                            source_lines, source_start, source_file = [], 0, ""
                        classes[key] = ClassEntry(
                            segment=segment,
                            app=app,
                            name=obj.__name__,
                            module=obj.__module__,
                            qualname=obj.__qualname__,
                            pagename=f"{PAGE_PREFIX}/{key}",
                            structure=structure,
                            fields=model_fields(obj) if segment == "models" else [],
                            file=source_file,
                            start=source_start,
                            total=len(source_lines),
                        )
                    elif segment == "domain" and inspect.isfunction(obj):
                        described = describe_function(obj)
                        if described:
                            functions.append(described)
                if segment == "domain" and functions:
                    modules.append(
                        ModuleEntry(
                            app=app,
                            module=mod.__name__,
                            pagename=f"{PAGE_PREFIX}/{mod.__name__}",
                            functions=sorted(functions, key=lambda f: f.name),
                        )
                    )

    pages_by_module_name = {}
    subclasses = {}
    for entry in classes.values():
        pages_by_module_name[(entry.module, entry.name)] = entry.pagename
    for entry in classes.values():
        for parent in entry.structure.parents:
            key = (parent.__module__, parent.__name__)
            if key in pages_by_module_name:
                subclasses.setdefault(key, []).append(entry)

    # Provide dotted-path index, and short-name lookups
    xref = {}
    for key, entry in classes.items():
        structure = entry.structure
        for path in [key, *aliases.get(key, [])]:
            xref[path] = (entry.pagename, "")
            for member_dict, anchor in (
                (structure.methods, "method"),
                (structure.properties, "property"),
                (structure.attributes, "attribute"),
            ):
                for member in member_dict:
                    xref[f"{path}.{member}"] = (entry.pagename, f"{anchor}-{member}")
    for module in modules:
        for function in module.functions:
            key = f"{module.module}.{function.name}"
            for path in [key, *aliases.get(key, [])]:
                xref[path] = (module.pagename, f"function-{function.name}")

    short_xref = {}
    for path, hit in xref.items():
        _prefix, dot, short = path.rpartition(".")
        if dot:
            short_xref.setdefault(short, set()).add(hit)

    logger.info(
        "coderef: classified %d classes, %d domain modules in %.1fs",
        len(classes),
        len(modules),
        time.time() - start,
    )
    return Registry(
        classes=classes,
        modules=modules,
        pages=pages_by_module_name,
        subclasses=subclasses,
        xref=xref,
        short_xref=short_xref,
    )


@functools.cache
def _pretalx_src_root():
    import pretalx  # noqa: PLC0415 -- optional dependency

    return Path(pretalx.__file__).resolve().parent.parent


def _source_relpath(file):
    if not file:
        return None
    try:
        return Path(file).resolve().relative_to(_pretalx_src_root())
    except ValueError:
        return None


def _source_link(file, start=None, total=None):
    rel = _source_relpath(file)
    if rel is None:
        return ""
    url = f"https://github.com/{GITHUB_REPO}/blob/{GITHUB_BRANCH}/src/{rel.as_posix()}"
    if start:
        url += f"#L{start}"
        if total and total > 1:
            url += f"-L{start + total - 1}"
    if not url:
        return ""
    return f'<a class="cref-source" href="{escape(url, quote=True)}">source</a>'


def _highlight(registry, code):
    return registry.app.builder.highlighter.highlight_block(
        textwrap.dedent(code), "python"
    )


def _parse_docstring(app, text):
    parser = RSTParser()
    parser._config = app.config  # noqa: SLF001 -- set_application is deprecated
    parser._env = app.env  # noqa: SLF001
    settings = get_default_settings(RSTParser)
    settings.report_level = 5
    settings.halt_level = 5
    settings.env = app.env
    document = new_document("<coderef docstring>", settings)
    env = app.env
    env.temp_data["default_domain"] = env.domains.get(app.config.primary_domain)
    try:
        with sphinx_domains(env):
            parser.parse(text, document)
    finally:
        env.temp_data.pop("default_domain", None)
    for message in list(document.findall(nodes.system_message)):
        message.parent.remove(message)
    for problematic in list(document.findall(nodes.problematic)):
        for attribute in ("ids", "names", "dupnames", "backrefs"):
            problematic[attribute] = []
        problematic.replace_self(nodes.Text(problematic.astext()))
    for field_name in list(document.findall(nodes.field_name)):
        text = field_name.astext()
        if text.startswith("param "):
            field_name.replace_self(
                nodes.field_name("", nodes.Text(text.removeprefix("param ")))
            )
    return document


def _defer_xref(node, contnode, registry):
    env = registry.env
    if env is None:
        return None
    return intersphinx_reference(registry.app, env, node, contnode)


def _candidates(module, tail):
    parts = module.split(".")
    return [".".join([*parts[:index], tail]) for index in range(len(parts), 0, -1)]


def _external_reference(module, tail, reftype, registry):
    for candidate in _candidates(module, tail):
        node = addnodes.pending_xref(
            "", refdomain="py", reftype=reftype, reftarget=candidate, refexplicit=False
        )
        reference = _defer_xref(node, nodes.Text(candidate), registry)
        if reference is not None:
            return reference["refuri"], candidate
    return "", ""


def _xref_target(target, registry):
    if target in registry.xref:
        return registry.xref[target]
    if "." in target:
        return None
    hits = registry.short_xref.get(target)
    if hits and len(hits) == 1:
        return next(iter(hits))
    return None


def _resolve_xrefs(document, registry, get_uri):
    for node in list(document.findall(addnodes.pending_xref)):
        contnode = node[0] if node.children else nodes.Text(node.get("reftarget", ""))
        target = node.get("reftarget", "")
        newnode = None
        hit = _xref_target(target, registry)
        if hit:
            pagename, anchor = hit
            uri = get_uri(pagename)
            if anchor:
                uri += f"#{anchor}"
            newnode = nodes.reference("", "", contnode, internal=True, refuri=uri)
        else:
            newnode = _defer_xref(node, contnode, registry)
        node.replace_self(newnode or contnode)


def _publish_body(document):
    writer = HTML5Writer()
    publish_from_doctree(
        document,
        writer=writer,
        settings_overrides={
            "output_encoding": "unicode",
            "report_level": 5,
            "halt_level": 5,
            "embed_stylesheet": False,
        },
    )
    return writer.parts["body"]


def _plain_docstring(text):
    paragraphs = "".join(
        f"<p>{escape(part.strip())}</p>" for part in text.split("\n\n") if part.strip()
    )
    return f'<div class="cref-docstring">{paragraphs}</div>'


def _docstring(text, registry=None, get_uri=None):
    if not text:
        return ""
    app = registry.app if registry else None
    if app is not None:
        try:
            document = _parse_docstring(app, text)
            _resolve_xrefs(document, registry, get_uri)
            return f'<div class="cref-docstring">{_publish_body(document)}</div>'
        except Exception as e:  # noqa: BLE001 -- arbitrary docstring markup
            logger.debug("coderef: rst rendering failed: %s", e)
    return _plain_docstring(text)


def _summary_html(text):
    def role(match):
        title = match.group(1)
        if "<" in title:
            title = title.split("<", 1)[0].strip() or title
        if title.startswith("~"):
            title = title[1:].rsplit(".", 1)[-1]
        return f"``{title}``"

    text = _ROLE_INLINE_RE.sub(role, text)
    parts = []
    pos = 0
    for match in _LITERAL_INLINE_RE.finditer(text):
        parts.append(escape(text[pos : match.start()]))
        parts.append(f"<code>{escape(match.group(1) or match.group(2))}</code>")
        pos = match.end()
    parts.append(escape(text[pos:]))
    return "".join(parts)


def _value_repr(value):
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    try:
        text = repr(value)
    except Exception:  # noqa: BLE001 -- arbitrary repr
        text = object.__repr__(value)
    if len(text) > 300:
        text = text[:300] + "…"
    return re.sub(r"^<(.+) object at 0x[0-9a-fA-F]+>$", r"<\1>", text)


def _class_ref(module, name, registry, get_uri):
    pagename = registry.pages.get((module, name))
    label = f"<code>{escape(module)}.<strong>{escape(name)}</strong></code>"
    if pagename:
        return f'<a href="{escape(get_uri(pagename), quote=True)}">{label}</a>'
    url, path = _external_reference(module, name, "class", registry)
    if url:
        prefix, _, short = path.rpartition(".")
        label = f"<code>{escape(prefix)}.<strong>{escape(short)}</strong></code>"
        return f'<a class="cref-external" href="{escape(url, quote=True)}">{label}</a>'
    return label


def _class_chip(simple, registry, get_uri):
    pagename = registry.pages.get((simple.module, simple.name))
    label = escape(simple.name)
    title = escape(simple.module, quote=True)
    if pagename:
        return (
            f'<a class="cref-defined" href="{escape(get_uri(pagename), quote=True)}"'
            f' title="{title}">{label}</a>'
        )
    url, _path = _external_reference(simple.module, simple.name, "class", registry)
    if url:
        return (
            f'<a class="cref-defined cref-external" href="{escape(url, quote=True)}"'
            f' title="{title}">{label}</a>'
        )
    return f'<span class="cref-defined" title="{title}">{label}</span>'


def _first_line(docstring):
    if not docstring:
        return ""
    paragraph = " ".join(docstring.strip().split("\n\n")[0].split())
    return re.split(r"(?<=[.!?])\s", paragraph)[0]


def _skip_first_line(docstring):
    if not docstring:
        return ""
    summary = _first_line(docstring)
    rest = " ".join(docstring.strip().split("\n\n")[0].split())[len(summary) :].strip()
    remainder = "\n\n".join(docstring.strip().split("\n\n")[1:])
    if rest:
        return f"{rest}\n\n{remainder}".strip()
    return remainder


def _render_definitions(definitions, registry, get_uri):
    # classify lists definitions base-first; show the most derived first.
    # The latest definition's docstring drops its first line, which the
    # collapsed member row already shows.
    parts = []
    show_origin = len(definitions) > 1
    for index, definition in enumerate(reversed(definitions)):
        parts.append('<div class="cref-definition">')
        if show_origin:
            defining = _class_ref(
                definition.defining_class.module,
                definition.defining_class.name,
                registry,
                get_uri,
            )
            source = _source_link(
                definition.file, definition.lines.start, definition.lines.total
            )
            parts.append(
                f'<p class="cref-definition-origin">on {defining} {source}</p>'
            )
        docstring = definition.docstring
        if index == 0:
            docstring = _skip_first_line(docstring)
        parts.append(_docstring(docstring, registry, get_uri))
        parts.append(_highlight(registry, definition.code))
        parts.append("</div>")
    return "".join(parts)


def _member_row(name, definitions, registry, get_uri, id_prefix):
    latest = definitions[-1]
    args = "" if id_prefix == "property" else _SELF_ARG_RE.sub("(", latest.arguments)
    source = _source_link(latest.file, latest.lines.start, latest.lines.total)
    summary = _first_line(latest.docstring)
    summary_html = (
        f'<span class="cref-summaryline">{_summary_html(summary)}</span>'
        if summary
        else ""
    )
    return (
        f'<details class="cref-member" id="{id_prefix}-{escape(name, quote=True)}">'
        f'<summary><span class="cref-member-head">'
        f'<code class="cref-name">{escape(name)}</code>'
        f'<code class="cref-args">{escape(args)}</code>{source}</span>'
        f"{summary_html}</summary>"
        f"{_render_definitions(definitions, registry, get_uri)}"
        "</details>"
    )


def _is_generated(definition):
    # Django adds get_FOO_display() and get_next_by_FOO() and similar junk
    # to the body at runtime, so classify attributes them to our class.
    return bool(definition.file) and _source_relpath(definition.file) is None


def _member_groups(members, structure, current):
    # group by the class providing the most derived definition, ordered current
    # first, then along the MRO, generated last
    groups = {}
    for name, definitions in members.items():
        defining = definitions[-1].defining_class
        key = (defining.module, defining.name)
        if key == current and _is_generated(definitions[-1]):
            key = GENERATED_GROUP
        groups.setdefault(key, {})[name] = definitions
    order = [current] + [(a.module, a.name) for a in reversed(structure.ancestors)]
    ordered = [(key, groups.pop(key)) for key in order if key in groups]
    generated = groups.pop(GENERATED_GROUP, None)
    rest = list(groups.items())
    if generated:
        rest.append((GENERATED_GROUP, generated))
    return ordered + rest


def _sorted_member_names(group):
    return sorted(group, key=lambda name: (name.startswith("__"), name))


def _render_compact_group(module, name, group, registry, id_prefix):
    # For boring inherited stuff. Listing all this directly would make actually
    # relevant attributes and methods hard to find.
    names = _sorted_member_names(group)
    preferred = [
        n for n in ("save", "delete", "full_clean", "get", "clean") if n in group
    ]
    lead_names = (preferred + [n for n in names if n not in preferred])[:3]
    call = "()" if id_prefix == "method" else ""
    lead = ", ".join(f"<code>{escape(n)}{call}</code>" for n in lead_names)
    more = len(names) - len(lead_names)
    root = module.split(".")[0]
    library_label = LIBRARY_LABELS.get(root, root)
    note = f"Standard {library_label} API, unchanged &mdash; {lead}"
    if more > 0:
        note += f" and {more} more"
    note += "."
    chips = []
    for member in names:
        url, _path = _external_reference(module, f"{name}.{member}", "attr", registry)
        label = escape(member)
        if url:
            chips.append(
                f'<a class="cref-chip" href="{escape(url, quote=True)}">{label}</a>'
            )
        else:
            chips.append(f'<span class="cref-chip">{label}</span>')
    return _render_compact(note, chips)


def _render_compact(note, chips):
    return (
        f'<details class="cref-compact"><summary><span class="cref-compact-note">'
        f"{note}</span></summary>"
        f'<div class="cref-chipcloud">{"".join(chips)}</div></details>'
    )


def _render_generated_group(group):
    chips = [
        f'<span class="cref-chip">{escape(name)}</span>'
        for name in _sorted_member_names(group)
    ]
    note = "Added by Django or another library dynamically after class creation."
    return _render_compact(note, chips)


def _render_member_section(
    title, members, structure, registry, get_uri, id_prefix, current
):
    if not members:
        return "", []
    section_id = f"section-{id_prefix}"
    parts = [
        (
            f'<h2 class="cref-section" id="{section_id}">{title} '
            f'<span class="cref-count">{len(members)}</span></h2>'
        )
    ]
    nav = []
    for index, (key, group) in enumerate(_member_groups(members, structure, current)):
        module, name = key
        group_id = f"{section_id}-{index}"
        if key == GENERATED_GROUP:
            parts.append(
                f'<h3 class="cref-group" id="{group_id}">Added at runtime</h3>'
            )
            parts.append(_render_generated_group(group))
            nav.append((group_id, "Added at runtime"))
            continue
        if key == current:
            header = "Defined here"
            nav.append((group_id, "Defined here"))
        else:
            label = escape(name)
            if pagename := registry.pages.get((module, name)):
                label = f'<a href="{escape(get_uri(pagename), quote=True)}">{label}</a>'
            header = f'From {label} <span class="cref-groupmod">{escape(module)}</span>'
            nav.append((group_id, name))
        parts.append(f'<h3 class="cref-group" id="{group_id}">{header}</h3>')
        external = (module, name) not in registry.pages
        if external and not module.startswith("pretalx."):
            parts.append(
                _render_compact_group(module, name, group, registry, id_prefix)
            )
            continue
        parts.extend(
            _member_row(member_name, group[member_name], registry, get_uri, id_prefix)
            for member_name in _sorted_member_names(group)
        )
    return "".join(parts), nav


def _render_attributes(attributes, registry, get_uri, current):
    if not attributes:
        return "", []

    def row(name, definition, muted):
        simple = definition.defining_class
        origin = "" if (simple.module, simple.name) == current else simple.name
        muted_class = " cref-muted" if muted else ""
        return (
            f'<div class="cref-row{muted_class}" id="attribute-{escape(name, quote=True)}">'
            f"<code>{escape(name)}</code>"
            f'<span class="cref-type"><code>{escape(_value_repr(definition.value))}</code></span>'
            f'<span class="cref-origin">{escape(origin)}</span></div>'
        )

    own = {}
    inherited = {}
    for name, definitions in attributes.items():
        simple = definitions[-1].defining_class
        target = own if (simple.module, simple.name) == current else inherited
        target[name] = definitions[-1]

    parts = []
    nav = []
    if own:
        parts.append(
            f'<h2 class="cref-section" id="section-attributes">Attributes '
            f'<span class="cref-count">{len(own)}</span></h2>'
            '<div class="cref-grid cref-grid-attrs">'
        )
        parts.extend(row(name, definition, False) for name, definition in own.items())
        parts.append("</div>")
        nav.append(("section-attributes", "Attributes"))
    if inherited:
        parts.append(
            '<details class="cref-collapse" id="inherited-attributes"><summary>'
            f'Inherited attributes <span class="cref-count">{len(inherited)}</span>'
            '</summary><div class="cref-grid cref-grid-attrs">'
        )
        parts.extend(row(name, inherited[name], True) for name in sorted(inherited))
        parts.append("</div></details>")
    return "".join(parts), nav


def _related_ref(field, registry, get_uri):
    pagename = registry.pages.get((field["related_module"], field["related"]))
    label = escape(field["related"])
    if pagename:
        return f'&rarr; <a href="{escape(get_uri(pagename), quote=True)}">{label}</a>'
    return f"&rarr; {label}"


def _field_badges(field):
    badges = ["null"] if field["null"] else []
    if field["primary_key"]:
        badges.append("pk")
    elif field["unique"]:
        badges.append("unique")
    return "".join(f'<span class="cref-badge">{badge}</span>' for badge in badges)


def _field_head(field, registry, get_uri):
    parts = [
        (
            '<span class="cref-member-head">'
            f'<code class="cref-name">{escape(field["name"])}</code>'
            f'<code class="cref-args">{escape(field["type"])}</code>'
        ),
        _field_badges(field),
    ]
    if field["related"]:
        parts.append(
            f'<span class="cref-related">{_related_ref(field, registry, get_uri)}</span>'
        )
    if field["origin"]:
        parts.append(f'<span class="cref-origin">{escape(field["origin"])}</span>')
    parts.append(_source_link(field["file"], field["start"], field["total"]))
    parts.append("</span>")
    return "".join(parts)


def _field_row(field, registry, get_uri):
    muted = " cref-muted" if field["origin"] else ""
    anchor = f'id="field-{escape(field["name"], quote=True)}"'
    head = _field_head(field, registry, get_uri)
    summary = (
        f'<span class="cref-summaryline">{escape(field["help_text"])}</span>'
        if field["help_text"]
        else ""
    )
    if not field["code"]:
        return f'<div class="cref-member cref-member-flat{muted}" {anchor}>{head}{summary}</div>'
    body = ['<div class="cref-definition">']
    if field["origin"]:
        defining = _class_ref(
            field["origin_module"], field["origin"], registry, get_uri
        )
        source = _source_link(field["file"], field["start"], field["total"])
        body.append(f'<p class="cref-definition-origin">on {defining} {source}</p>')
    body.append(_highlight(registry, field["code"]))
    body.append("</div>")
    return (
        f'<details class="cref-member{muted}" {anchor}>'
        f"<summary>{head}{summary}</summary>{''.join(body)}</details>"
    )


def _render_fields(fields, registry, get_uri):
    if not fields:
        return "", []
    concrete = [f for f in fields if f["concrete"]]
    reverse = [f for f in fields if not f["concrete"]]

    def row(field):
        details = []
        if field["related"]:
            details.append(_related_ref(field, registry, get_uri))
        if field["origin"]:
            details.append(
                f'<span class="cref-origin">{escape(field["origin"])}</span>'
            )
        muted = " cref-muted" if field["origin"] else ""
        return (
            f'<div class="cref-row{muted}" id="field-{escape(field["name"], quote=True)}">'
            f"<code>{escape(field['name'])}</code>"
            f'<span class="cref-type">{escape(field["type"])}</span>'
            f'<span class="cref-detail">{" ".join(details)}</span></div>'
        )

    parts = []
    nav = []
    if concrete:
        parts.append(
            f'<h2 class="cref-section" id="section-fields">Fields '
            f'<span class="cref-count">{len(concrete)}</span></h2>'
            '<div class="cref-fields">'
        )
        parts.extend(_field_row(field, registry, get_uri) for field in concrete)
        parts.append("</div>")
        nav.append(("section-fields", "Fields"))
    if reverse:
        parts.append(
            '<details class="cref-collapse"><summary>'
            f'Reverse relations <span class="cref-count">{len(reverse)}</span>'
            '</summary><div class="cref-grid">'
        )
        parts.extend(row(field) for field in reverse)
        parts.append("</div></details>")
    return "".join(parts), nav


def _chips_row(label, chips):
    if not chips:
        return ""
    return (
        f'<div class="cref-chips"><span class="cref-chips-label">{label}</span>'
        f"{''.join(chips)}</div>"
    )


def _pagenav(title, items):
    # Duplicate pretalx-theme local toc
    if not items:
        return ""
    parts = [f'<ul><li><a href="#">{escape(title)}</a><ul>']
    for anchor, label, children in items:
        parts.append(f'<li><a href="#{anchor}">{escape(label)}</a>')
        if children:
            parts.append("<ul>")
            parts.extend(
                f'<li><a href="#{sub_anchor}">{escape(sub_label)}</a></li>'
                for sub_anchor, sub_label in children
            )
            parts.append("</ul>")
        parts.append("</li>")
    parts.append("</ul></li></ul>")
    return "".join(parts)


def _page_header(kind, title, module_line, source, docstring, registry, get_uri):
    module_html = ""
    if module_line:
        module_html = (
            f'<p class="cref-module"><code>{escape(module_line)}</code> {source}</p>'
        )
    return (
        '<div class="cref-head">'
        f'<span class="cref-kind">{kind}</span>'
        f"<h1>{escape(title)}</h1></div>"
        f"{module_html}"
        f"{_docstring(docstring, registry, get_uri)}"
    )


def render_class_body(entry, registry, get_uri):
    structure = entry.structure
    current = (entry.module, entry.name)
    breadcrumb = (
        f'<p class="cref-breadcrumb"><a href="{escape(get_uri(INDEX_DOCNAME), quote=True)}">'
        f"Code reference</a> &rsaquo; {escape(entry.segment)}"
        f" &rsaquo; {escape(entry.app)}</p>"
    )

    inherit_chips = [
        _class_chip(ancestor, registry, get_uri)
        for ancestor in reversed(structure.ancestors)
    ]
    children = registry.subclasses.get(current, [])
    subclass_chips = [
        _class_chip(child, registry, get_uri)
        for child in sorted(children, key=lambda c: (c.module, c.name))
    ]

    fields_html, fields_nav = _render_fields(entry.fields, registry, get_uri)
    attrs_html, attrs_nav = _render_attributes(
        structure.attributes, registry, get_uri, current
    )
    props_html, _props_nav = _render_member_section(
        "Properties",
        structure.properties,
        structure,
        registry,
        get_uri,
        "property",
        current,
    )
    methods_html, methods_nav = _render_member_section(
        "Methods", structure.methods, structure, registry, get_uri, "method", current
    )

    nav = [(anchor, label, []) for anchor, label in fields_nav + attrs_nav]
    if props_html:
        nav.append(("section-property", "Properties", []))
    if methods_html:
        nav.append(("section-method", "Methods", methods_nav))

    parts = [
        breadcrumb,
        '<div class="cref-page"><div class="cref-main">',
        _page_header(
            "class",
            entry.name,
            f"{entry.module}.{entry.qualname}",
            _source_link(entry.file, entry.start, entry.total),
            structure.docstring,
            registry,
            get_uri,
        ),
        _chips_row("Inherits", inherit_chips),
        _chips_row("Subclasses", subclass_chips),
        fields_html,
        attrs_html,
        props_html,
        methods_html,
        "</div></div>",
    ]
    return "".join(parts), _pagenav(entry.name, nav)


def render_module_body(entry, registry, get_uri):
    breadcrumb = (
        f'<p class="cref-breadcrumb"><a href="{escape(get_uri(INDEX_DOCNAME), quote=True)}">'
        f"Code reference</a> &rsaquo; domain &rsaquo; {escape(entry.app)}</p>"
    )
    parts = [
        breadcrumb,
        '<div class="cref-page"><div class="cref-main">',
        _page_header("module", entry.module, "", "", "", registry, get_uri),
        (
            f'<h2 class="cref-section" id="section-function">Functions '
            f'<span class="cref-count">{len(entry.functions)}</span></h2>'
        ),
    ]
    parts.extend(
        _member_row(function.name, [function], registry, get_uri, "function")
        for function in entry.functions
    )
    parts.append("</div></div>")
    nav = _pagenav(
        entry.module,
        [
            (
                "section-function",
                "Functions",
                [
                    (f"function-{function.name}", f"{function.name}()")
                    for function in entry.functions
                ],
            )
        ],
    )
    return "".join(parts), nav


def _short_module(module, app):
    return module.removeprefix(f"pretalx.{app}.")


def build_search_data(registry, get_uri):
    data = []
    for entry in registry.classes.values():
        structure = entry.structure
        data.append(
            {
                "name": entry.name,
                "module": entry.module,
                "url": get_uri(entry.pagename),
                "kind": "class",
                "segment": entry.segment,
                "methods": list(structure.methods),
                "properties": list(structure.properties),
                "attributes": list(structure.attributes),
            }
        )
    for module in registry.modules:
        url = get_uri(module.pagename)
        data.extend(
            {
                "name": function.name,
                "module": module.module,
                "url": f"{url}#function-{function.name}",
                "kind": "function",
                "segment": "domain",
            }
            for function in module.functions
        )
    return data


def render_index_html(registry, get_uri):
    search_data = json_dumps(
        build_search_data(registry, get_uri), separators=(",", ":")
    )
    parts = [
        (
            '<div class="cref-search"><input type="search" id="cref-search-input" '
            'placeholder="Search classes, methods, functions…" autocomplete="off" spellcheck="false">'
            '<ul id="cref-search-results" hidden></ul></div>'
        ),
        f'<script type="application/json" id="cref-search-data">{search_data}</script>',
    ]

    modules_by_app = {}
    for module in registry.modules:
        modules_by_app.setdefault(module.app, []).append(module)

    for index, segment in enumerate(ENABLED_SEGMENTS):
        config = SEGMENTS[segment]
        entries = [e for e in registry.classes.values() if e.segment == segment]
        by_app = {}
        for entry in entries:
            by_app.setdefault(entry.app, []).append(entry)
        function_count = 0
        if segment == "domain":
            function_count = sum(len(m.functions) for m in registry.modules)
        count = len(entries) + function_count
        open_attr = " open" if index == 0 else ""
        parts.append(
            f'<details class="cref-segment"{open_attr}><summary><strong>{escape(config["label"])}</strong> '
            f'<span class="cref-count">{count}</span></summary><div class="cref-apps">'
        )
        for app in sorted(
            set(by_app) | (set(modules_by_app) if segment == "domain" else set())
        ):
            parts.append(f"<section><h3>{escape(app)}</h3>")
            app_entries = sorted(by_app.get(app, []), key=lambda e: e.name)
            if app_entries:
                parts.append('<ul class="cref-classlist">')
                for entry in app_entries:
                    href = escape(get_uri(entry.pagename), quote=True)
                    module = escape(_short_module(entry.module, app))
                    parts.append(
                        f'<li><a href="{href}">{escape(entry.name)}</a> '
                        f'<span class="cref-mod">{module}</span></li>'
                    )
                parts.append("</ul>")
            if segment == "domain":
                for module in sorted(
                    modules_by_app.get(app, []), key=lambda m: m.module
                ):
                    href = escape(get_uri(module.pagename), quote=True)
                    parts.append(
                        f'<h4 class="cref-modheading"><a href="{href}">'
                        f"{escape(_short_module(module.module, app))}</a></h4>"
                        '<ul class="cref-classlist cref-functionlist">'
                    )
                    parts.extend(
                        f'<li><a href="{href}#function-{escape(function.name, quote=True)}">'
                        f"{escape(function.name)}()</a></li>"
                        for function in module.functions
                    )
                    parts.append("</ul>")
            parts.append("</section>")
        parts.append("</div></details>")
    return "".join(parts)


class CodeRefIndexNode(nodes.General, nodes.Element):
    pass


class CodeRefIndexDirective(Directive):
    has_content = False

    def run(self):
        return [CodeRefIndexNode("")]


def get_registry(app):
    registry = getattr(app, "coderef_registry", None)
    if registry is None:
        registry = collect_registry()
        registry.app = app
        app.coderef_registry = registry
    return registry


def on_builder_inited(app):
    if app.builder.format != "html":
        return
    get_registry(app)


def on_env_get_outdated(app, env, added, changed, removed):
    # Always rebuild
    if INDEX_DOCNAME in env.found_docs and INDEX_DOCNAME not in (
        added | changed | removed
    ):
        return [INDEX_DOCNAME]
    return []


def on_missing_reference(app, env, node, contnode):
    if node.get("refdomain") != "py" or app.builder.format != "html":
        return None
    registry = getattr(app, "coderef_registry", None)
    if registry is None:
        return None
    hit = registry.xref.get(node["reftarget"])
    if hit is None:
        return None
    pagename, anchor = hit
    refdoc = node.get("refdoc", env.docname)
    try:
        uri = app.builder.get_relative_uri(refdoc, pagename)
    except NoUri:
        return None
    if anchor:
        uri += f"#{anchor}"
    return nodes.reference("", "", contnode, internal=True, refuri=uri)


def on_doctree_resolved(app, doctree, docname):
    placeholders = list(doctree.findall(CodeRefIndexNode))
    if not placeholders:
        return
    if app.builder.format != "html":
        for node in placeholders:
            node.replace_self([])
        return
    registry = get_registry(app)

    def get_uri(target):
        return app.builder.get_relative_uri(docname, target)

    html = render_index_html(registry, get_uri)
    for node in placeholders:
        node.replace_self(nodes.raw("", html, format="html"))


def on_html_page_context(app, pagename, templatename, context, doctree):
    if not pagename.startswith(f"{PAGE_PREFIX}/"):
        return
    if not hasattr(app.builder, "_get_local_toctree"):
        return

    # Force toctree to render uncollapsed like we're the ref index
    # page (generated pages are unknown and collapse the tree).
    def toctree(**kwargs):
        html = app.builder._get_local_toctree(INDEX_DOCNAME, **kwargs)  # noqa: SLF001 -- no public API for this
        if not html:
            return html
        index_page = INDEX_DOCNAME.rsplit("/", 1)[-1]
        html = _RELATIVE_HREF_RE.sub('href="../', html)
        return html.replace('href="#"', f'href="../{index_page}.html"')

    context["toctree"] = toctree


def collect_pages(app):
    if app.builder.format != "html":
        return
    registry = get_registry(app)

    def make_context(pagename, title, body, page_nav):
        return {
            "title": title,
            "body": body,
            "metatags": "",
            "toc": "",
            "page_nav": page_nav,
        }

    for entry in registry.classes.values():

        def get_uri(target, _from=entry.pagename):
            return app.builder.get_relative_uri(_from, target)

        body, page_nav = render_class_body(entry, registry, get_uri)
        yield (
            entry.pagename,
            make_context(entry.pagename, entry.name, body, page_nav),
            "page.html",
        )

    for module in registry.modules:

        def get_uri(target, _from=module.pagename):
            return app.builder.get_relative_uri(_from, target)

        body, page_nav = render_module_body(module, registry, get_uri)
        yield (
            module.pagename,
            make_context(module.pagename, module.module, body, page_nav),
            "page.html",
        )


def setup(app):
    app.add_directive("coderef-index", CodeRefIndexDirective)
    app.connect("builder-inited", on_builder_inited)
    app.connect("env-get-outdated", on_env_get_outdated)
    app.connect("doctree-resolved", on_doctree_resolved)
    app.connect("missing-reference", on_missing_reference)
    app.connect("html-collect-pages", collect_pages)
    app.connect("html-page-context", on_html_page_context)
    app.add_css_file("coderef.css")
    app.add_js_file("coderef.js")
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
