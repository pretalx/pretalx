# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: Apache-2.0

"""Sphinx extension to build a useful, pretty changelog.

Usage in ReST files:
    - :release:`v1 <yyyy-mm-dd>`
    - :bug:`admin,123` Descriptive text
    - :feature:`admin` More text
    - :announcement:`123` Even more text

Numbers will be replaced with links to the corresponding GitHub issues, other tags
will refer to the categories defined below for grouping.

This Sphinx extension is heavily inspired by the `releases` Sphinx extension by Jeff
'bitprophet' Forcier.
"""

import logging
import re
from collections import defaultdict
from html import escape as html_escape

from docutils import nodes, utils

logger = logging.getLogger(__name__)

GITHUB_REPO = "pretalx/pretalx"


def release_pagename(version):
    """Return the Sphinx document name for a release's detail page."""
    return f"changelog/v{version}"


ISSUE_TYPES = {
    "announcement": {"color": "4070A0", "label": "Announcement", "order": 2},
    "bug": {"color": "A04040", "label": "Fixed bug", "order": 1},
    "feature": {"color": "40A056", "label": "Feature", "order": 0},
}

CATEGORIES = {
    "": {"label": "General", "order": 10},
    "admin": {"label": "Administrators", "order": 11},
    "api": {"label": "API", "order": 8},
    "cfp": {"label": "Call for Papers", "order": 1},
    "dev": {"label": "Developers and plugins", "order": 12},
    "lang": {"label": "Languages and translations", "order": 9},
    "orga": {"label": "Organiser backend", "order": 2},
    "orga:email": {"label": "Organiser backend: E-Mails", "order": 3},
    "orga:review": {"label": "Organiser backend: Review process", "order": 6},
    "orga:schedule": {"label": "Organiser backend: Scheduling", "order": 7},
    "orga:speaker": {"label": "Organiser backend: Speaker management", "order": 4},
    "orga:submission": {"label": "Organiser backend: Session management", "order": 5},
    "schedule": {"label": "Schedule", "order": 0},
}


class Issue(nodes.Element):
    @property
    def type(self):
        return self["type_"]

    @property
    def number(self):
        return self.get("number", None)

    @property
    def category(self):
        return self.get("category", "")

    def __repr__(self):
        return f"<{self.type} #{self.number}>"


class Release(nodes.Element):
    @property
    def number(self):
        return self["number"]

    def __repr__(self):
        return f"<release {self.number}>"


def issue_role(name, rawtext, text, lineno, inliner, *args, **kwargs):
    attrs = [
        attr.strip()
        for attr in utils.unescape(text).split(",")
        if attr not in ("", "-", "0")
    ]

    categories = [c for c in attrs if c in CATEGORIES]
    category = categories[0] if categories else ""

    if len(categories) > 1:
        logger.warning(
            "Multiple categories in changelog entry (line %d): %s — using %r",
            lineno,
            ", ".join(repr(c) for c in categories),
            category,
        )

    issues = [i for i in attrs if i.isdigit()]
    issue = issues[0] if issues else None

    if len(issues) > 1:
        logger.warning(
            "Multiple issue numbers in changelog entry (line %d): %s — using #%s",
            lineno,
            ", ".join(f"#{i}" for i in issues),
            issue,
        )

    for attr in attrs:
        if attr not in CATEGORIES and not attr.isdigit():
            logger.warning(
                "Unrecognized changelog attribute %r (line %d). Known categories: %s",
                attr,
                lineno,
                ", ".join(sorted(CATEGORIES)),
            )

    node = Issue(
        number=issue,
        type_=name,
        nodelist=[
            nodes.raw(
                text=f'[<span class="changelog-label-{name}">{ISSUE_TYPES[name]["label"]}</span>]',
                format="html",
            ),
            nodes.inline(text=" "),
        ],
        category=category,
    )
    return [node], []


release_arg_re = re.compile(r"^(.+?)\s*(?<!\x00)<(.*?)>$", re.DOTALL)


def _build_release_node(number, url, date=None, text=None):
    text = html_escape(text or number)
    datespan = (
        f' <span class="changelog-date">{html_escape(date)}</span>' if date else ""
    )
    link = f'<a class="reference external" href="{html_escape(url, quote=True)}">{text}</a>'
    header = f'<h2 class="changelog-release-heading">{link}{datespan}</h2>'
    node = nodes.section(
        "", nodes.raw(rawtext="", text=header, format="html"), ids=[number]
    )
    return Release(number=number, date=date, nodelist=[node])


def release_role(name, rawtext, text, lineno, inliner, *args, **kwargs):
    match = release_arg_re.match(text)
    if not match:
        msg = inliner.reporter.error("Must specify release date!")
        return [inliner.problematic(rawtext, rawtext, msg)], [msg]
    number, date = match.group(1), match.group(2)
    text = number
    url = f"https://pypi.org/project/pretalx/{number.strip('v')}/"
    return [_build_release_node(number, url=url, date=date)], []


def collect_releases(entries):
    releases = [
        {
            "release": _build_release_node(
                "next",
                f"https://github.com/{GITHUB_REPO}/commits/main/",
                text="Next Release",
            ),
            "entries": defaultdict(list),
        }
    ]

    for entry in entries:
        # Issue object is always found in obj (LI) index 0 (first, often only
        # P) and is the 1st item within that (index 0 again).
        # Preserve all other contents of 'obj'.
        # We deepcopy here so we don't mutate the original doctree — it may
        # be traversed again (e.g. for release sub-pages).
        entry_copy = entry.deepcopy()
        if not entry_copy or not entry_copy[0]:
            logger.warning("Skipping empty changelog entry")
            continue
        obj = entry_copy[0].pop(0)
        rest = entry_copy
        if isinstance(obj, Release):
            releases.append({"release": obj, "entries": defaultdict(list)})
            continue
        if not isinstance(obj, Issue):
            msg = f"Found issue node ({obj}) which is not an Issue! Please double-check your ReST syntax!"
            msg += f"Context: {obj.parent!s}"
            raise TypeError(msg)

        releases[-1]["entries"][obj.category].append(
            {"issue": obj, "description": rest}
        )

    return [r for r in releases if r["entries"] or r["release"].number != "next"]


def construct_issue_nodes(issue, description):
    description = description.deepcopy()
    # Expand any other issue roles found in the description - sometimes we refer to related issues inline.
    # (They can't be left as issue() objects at render time since that's undefined.)
    # Use [:] slicing (even under modern Python; the objects here are docutils Nodes whose .copy() is weird)
    # to avoid mutation during the loops.
    for index, node in enumerate(description[:]):
        for subindex, subnode in enumerate(node[:]):
            if isinstance(subnode, Issue):
                lst = subnode["nodelist"]
                description[index][subindex : subindex + 1] = lst

    if issue.number:
        ref = f"https://github.com/{GITHUB_REPO}/issues/{issue.number}"
        identifier = nodes.reference("", "#" + issue.number, refuri=ref)
        github_link = [nodes.inline(text=" ("), identifier, nodes.inline(text=")")]
        description[0].extend(github_link)

    for node in reversed(issue["nodelist"]):
        description[0].insert(0, node)

    return description


def construct_release_nodes(release, entries):
    # Build a new section node from the release header, appending category
    # content to the copy instead of mutating the release in-place.
    section = release["nodelist"][0].deepcopy()
    show_category_headers = len(entries) > 1
    for category, cat_info in sorted(CATEGORIES.items(), key=lambda c: c[1]["order"]):
        cat_issues = entries.get(category)
        if not cat_issues:
            continue
        if show_category_headers:
            section.append(
                nodes.raw(
                    rawtext="",
                    text=f'<h4 class="changelog-category-heading">{cat_info["label"]}</h4>',
                    format="html",
                )
            )
        cat_issues = sorted(
            cat_issues, key=lambda i: ISSUE_TYPES[i["issue"].type]["order"]
        )
        issue_nodes = [
            construct_issue_nodes(issue["issue"], issue["description"])
            for issue in cat_issues
        ]
        issue_ul = nodes.bullet_list("", *issue_nodes)
        section.append(issue_ul)

    return nodes.paragraph("", "", section)


def format_release_title(version, date):
    """Format a release title for an HTML page."""
    if version == "next":
        return "Next Release"
    if date:
        return f"pretalx {version} ({date})"
    return f"pretalx {version}"


def _render_children(node):
    """Render all children of a docutils node to HTML."""
    return "".join(_render_node(c) for c in node)


def _render_text(node):
    return html_escape(str(node))


def _render_raw(node):
    if node.get("format", "") == "html":
        return node.astext()
    return _render_children(node)


def _render_reference(node):
    href = html_escape(node.get("refuri", ""), quote=True)
    return f'<a class="reference external" href="{href}">{_render_children(node)}</a>'


def _render_bullet_list(node):
    return f"<ul>\n{_render_children(node)}</ul>\n"


def _render_list_item(node):
    return f"<li>{_render_children(node)}</li>\n"


def _render_paragraph(node):
    content = _render_children(node)
    if any(isinstance(c, (nodes.section, nodes.bullet_list)) for c in node):
        return content
    return f"<p>{content}</p>\n"


def _render_section(node):
    content = _render_children(node)
    ids = node.get("ids", [])
    if ids:
        return (
            f'<section id="{html_escape(ids[0], quote=True)}">\n{content}</section>\n'
        )
    return content


_NODE_RENDERERS = {
    nodes.Text: _render_text,
    nodes.raw: _render_raw,
    nodes.reference: _render_reference,
    nodes.inline: _render_children,
    nodes.bullet_list: _render_bullet_list,
    nodes.list_item: _render_list_item,
    nodes.paragraph: _render_paragraph,
    nodes.section: _render_section,
}


def _render_node(node):
    """Recursively render a docutils node to HTML."""
    renderer = _NODE_RENDERERS.get(type(node))
    if renderer:
        return renderer(node)
    # For other container nodes: just render children
    if hasattr(node, "children"):
        return _render_children(node)
    return ""


def nodes_to_html(node_list):
    """Render a list of docutils nodes to an HTML body fragment."""
    return "".join(_render_node(node) for node in node_list)


def build_release_nav(releases, current_index, get_uri):
    """Build navigation HTML for a release sub-page.

    ``get_uri`` maps a docname to a relative URI from the current page
    (typically ``app.builder.get_relative_uri``).
    """
    parts = ['<nav class="changelog-nav">']
    newer = next(
        (
            releases[i]["release"]
            for i in range(current_index - 1, -1, -1)
            if releases[i]["release"].number != "next"
        ),
        None,
    )
    older = next(
        (
            releases[i]["release"]
            for i in range(current_index + 1, len(releases))
            if releases[i]["release"].number != "next"
        ),
        None,
    )
    if newer:
        v = html_escape(newer.number)
        href = html_escape(get_uri(release_pagename(newer.number)), quote=True)
        parts.append(f'<a href="{href}" class="changelog-nav-next">&larr; {v}</a>')
    if older:
        v = html_escape(older.number)
        href = html_escape(get_uri(release_pagename(older.number)), quote=True)
        parts.append(f'<a href="{href}" class="changelog-nav-prev">{v} &rarr;</a>')
    parts.append("</nav>")
    return "".join(parts)


def generate_changelog(app, doctree, docname):
    if docname != "changelog":
        return
    # Only the first bullet_list in the doctree is the changelog.
    bl = next(iter(doctree.traverse(nodes.bullet_list)), None)
    if bl is None:
        return
    releases = collect_releases(bl.children)

    # Cache parsed releases for generate_release_pages (avoids re-parsing
    # the doctree in the html-collect-pages phase).
    app.env.changelog_parsed_releases = releases

    # Store release list for sidebar navigation (excluding "next")
    app.env.changelog_releases = [
        r["release"].number for r in releases if r["release"].number != "next"
    ]

    released = [r for r in releases if r["release"].number != "next" and r["entries"]]
    has_next = (
        releases and releases[0]["release"].number == "next" and releases[0]["entries"]
    )

    result = []
    # Link to latest release at top (before potentially long "next" section)
    if released:
        latest = released[0]["release"]
        v = latest.number
        d = latest["date"] or ""
        text = f"Latest release: {v} ({d})" if d else f"Latest release: {v}"
        ref = nodes.reference("", text, refuri=f"{release_pagename(v)}.html")
        result.append(nodes.paragraph("", "", ref))
    # Show "next" (unreleased) entries inline if they exist
    if has_next:
        result.extend(
            construct_release_nodes(releases[0]["release"], releases[0]["entries"])
        )
    bl.replace_self(result)


def generate_release_pages(app):
    """Generate individual HTML pages for each release."""
    releases = getattr(app.env, "changelog_parsed_releases", None)
    if releases is None:
        return

    for i, release_data in enumerate(releases):
        # "next" (unreleased) content lives on the main changelog page only
        if release_data["release"].number == "next":
            continue
        release = release_data["release"]
        version = release.number
        if release_data["entries"]:
            paragraph_node = construct_release_nodes(release, release_data["entries"])
            body = nodes_to_html([paragraph_node])
        else:
            # Empty releases are maintenance-only (dependency updates, etc.)
            header_node = construct_release_nodes(release, {})
            body = nodes_to_html([header_node])
            body += '<p class="changelog-maintenance">This was a maintenance release with dependency updates and minor fixes.</p>\n'
        pagename = release_pagename(version)

        def get_uri(target, _from=pagename):
            return app.builder.get_relative_uri(_from, target)

        nav = build_release_nav(releases, i, get_uri)
        context = {
            "title": format_release_title(
                release_data["release"].number, release_data["release"]["date"]
            ),
            "body": nav + body + nav,
            "metatags": "",
            "toc": "",
        }
        yield (pagename, context, "page.html")


# Theme-dependent regex: matches the "Release Notes" entry in the rendered
# toctree HTML so we can inject per-release sub-links.  If a Sphinx theme
# changes its toctree markup, this will stop matching and the warning in
# inject_changelog_sidebar() will fire as a safety net.
TOCTREE_RELEASE_NOTES_RE = re.compile(
    r'(<li class="toctree-l1)([^"]*">)(<a [^>]*>Release Notes</a>)</li>'
)


def inject_changelog_sidebar(app, pagename, templatename, context, doctree):
    """Inject release sub-pages into the global toctree for changelog pages."""
    if not (pagename == "changelog" or pagename.startswith("changelog/")):
        return
    versions = getattr(app.env, "changelog_releases", None)
    if not versions:
        return
    original_toctree = context.get("toctree")
    if not original_toctree:
        return

    # Build the release sub-list to inject. Show the first N releases,
    # hide the rest behind a "show all" link. If the active page is a
    # hidden release, show everything expanded.
    pathto = context["pathto"]
    visible_count = app.config.changelog_sidebar_visible_count
    current_idx = None
    for idx, version in enumerate(versions):
        if pagename == release_pagename(version):
            current_idx = idx
            break
    collapse = current_idx is None or current_idx < visible_count

    items = []
    for idx, version in enumerate(versions):
        current = " current" if idx == current_idx else ""
        extra_cls = ""
        if collapse and idx >= visible_count:
            extra_cls = " changelog-hidden"
        href = pathto(release_pagename(version))
        items.append(
            f'<li class="toctree-l2{current}{extra_cls}">'
            f'<a class="reference internal" href="{href}">{version}</a></li>'
        )
    if collapse and len(versions) > visible_count:
        remaining = len(versions) - visible_count
        items.insert(
            visible_count,
            '<li class="toctree-l2" id="changelog-show-all">'
            f'<a href="#" class="changelog-show-all-link"'
            f' data-count="{remaining}">'
            f"&hellip; {remaining} older releases</a></li>",
        )
    children_html = f"<ul>{''.join(items)}</ul>"

    # Wrap the toctree function: when the template calls toctree(), inject
    # release children under the Release Notes entry in the result.
    def _patched_toctree(**kwargs):
        html = original_toctree(**kwargs)
        if not html:
            return html

        def _inject(m):
            prefix, cls_rest, link = m.group(1), m.group(2), m.group(3)
            if pagename.startswith("changelog/") and "current" not in cls_rest:
                cls_rest = " current" + cls_rest
            return f"{prefix}{cls_rest}{link}{children_html}</li>"

        result = TOCTREE_RELEASE_NOTES_RE.sub(_inject, html, count=1)
        if result == html:
            logger.warning(
                "changelog: could not inject release sidebar — "
                "toctree HTML did not match expected pattern. "
                "The sidebar will not show individual release links."
            )
        return result

    context["toctree"] = _patched_toctree


def setup(app):
    app.add_config_value("changelog_sidebar_visible_count", 10, "html")
    for name in ISSUE_TYPES:
        app.add_role(name, issue_role)
    app.add_role("release", release_role)
    app.connect("doctree-resolved", generate_changelog)
    app.connect("html-collect-pages", generate_release_pages)
    app.connect("html-page-context", inject_changelog_sidebar)
    app.add_js_file("changelog.js")
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
