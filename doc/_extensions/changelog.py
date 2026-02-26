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

import re
from collections import defaultdict
from html import escape as html_escape

from docutils import nodes, utils

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
        return self.get("category", None) or ""

    def __repr__(self):
        return f"<{self.type} #{self.number}>"


class Release(nodes.Element):
    @property
    def number(self):
        return self["number"]

    def __repr__(self):
        return f"<release {self.number}>"


def issues_role(name, rawtext, text, *args, **kwargs):
    attrs = [
        attr.strip()
        for attr in utils.unescape(text).split(",")
        if attr not in ("", "-", "0")
    ]

    categories = [c for c in attrs if c in CATEGORIES]
    category = categories[0] if categories else None

    issues = [i for i in attrs if i.isdigit()]
    issue = issues[0] if issues else None

    type_label_str = f'[<span style="color: #{ISSUE_TYPES[name]["color"]};">{ISSUE_TYPES[name]["label"]}</span>]'
    type_label = [nodes.raw(text=type_label_str, format="html")]

    nodelist = [*type_label, nodes.inline(text=" ")]
    node = Issue(number=issue, type_=name, nodelist=nodelist, category=category)
    return [node], []


year_arg_re = re.compile(r"^(.+?)\s*(?<!\x00)<(.*?)>$", re.DOTALL)


def _build_release_node(number, url, date=None, text=None):
    text = text or number
    datespan = f' <span style="font-size: 75%;">{date}</span>' if date else ""
    link = f'<a class="reference external" href="{url}">{text}</a>'
    header = f'<h2 style="margin-bottom: 0.3em;">{link}{datespan}</h2>'
    node = nodes.section(
        "", nodes.raw(rawtext="", text=header, format="html"), ids=[number]
    )
    return Release(number=number, date=date, nodelist=[node])


def release_role(name, rawtext, text, lineno, inliner, *args, **kwargs):
    match = year_arg_re.match(text)
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
                "https://github.com/pretalx/pretalx/commits/main/",
                text="Next Release",
            ),
            "entries": defaultdict(list),
        }
    ]

    for entry in entries:
        # Issue object is always found in obj (LI) index 0 (first, often only
        # P) and is the 1st item within that (index 0 again).
        # Preserve all other contents of 'obj'.
        obj = entry[0].pop(0)
        rest = entry
        if isinstance(obj, Release):
            # If the last release was empty, remove it
            if not releases[-1]["entries"]:
                releases.pop()
            releases.append({"release": obj, "entries": defaultdict(list)})
            continue
        if not isinstance(obj, Issue):
            msg = f"Found issue node ({obj}) which is not an Issue! Please double-check your ReST syntax!"
            msg += f"Context: {obj.parent!s}"
            raise TypeError(msg)

        releases[-1]["entries"][obj.category].append(
            {"issue": obj, "description": rest}
        )
    return releases


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
        ref = f"https://github.com/pretalx/pretalx/issues/{issue.number}"
        identifier = nodes.reference("", "#" + issue.number, refuri=ref)
        github_link = [nodes.inline(text=" ("), identifier, nodes.inline(text=")")]
        description[0].extend(github_link)

    for node in reversed(issue["nodelist"]):
        description[0].insert(0, node)

    return description


def construct_release_nodes(release, entries):
    show_category_headers = len(entries) > 1
    for category, cat_info in sorted(CATEGORIES.items(), key=lambda c: c[1]["order"]):
        issues = entries.get(category)
        if not issues:
            continue
        # add a sub-header for the category
        if show_category_headers:
            release["nodelist"][0].append(
                nodes.raw(
                    rawtext="",
                    text=f'<h4 style="margin-bottom: 0.3em;">{cat_info["label"]}</h4>',
                    format="html",
                )
            )
        issues = sorted(issues, key=lambda i: ISSUE_TYPES[i["issue"].type]["order"])
        issue_nodes = [
            construct_issue_nodes(issue["issue"], issue["description"])
            for issue in issues
        ]
        issue_ul = nodes.bullet_list("", *issue_nodes)
        release["nodelist"][0].append(issue_ul)

    return nodes.paragraph("", "", *release["nodelist"])


def format_release_title(release):
    """Format a release title for an HTML page."""
    version = release.number
    date = release["date"]
    if version == "next":
        return "Next Release"
    if date:
        return f"pretalx {version} ({date})"
    return f"pretalx {version}"


def _render_node(node):
    """Recursively render a docutils node to HTML."""
    if isinstance(node, nodes.Text):
        return html_escape(str(node))
    if isinstance(node, nodes.raw) and node.get("format", "") == "html":
        return node.astext()
    if isinstance(node, nodes.reference):
        href = html_escape(node.get("refuri", ""), quote=True)
        content = "".join(_render_node(c) for c in node)
        return f'<a class="reference external" href="{href}">{content}</a>'
    if isinstance(node, nodes.bullet_list):
        content = "".join(_render_node(c) for c in node)
        return f"<ul>\n{content}</ul>\n"
    if isinstance(node, nodes.list_item):
        content = "".join(_render_node(c) for c in node)
        return f"<li>{content}</li>\n"
    if isinstance(node, nodes.paragraph):
        content = "".join(_render_node(c) for c in node)
        if any(isinstance(c, (nodes.section, nodes.bullet_list)) for c in node):
            return content
        return f"<p>{content}</p>\n"
    if isinstance(node, nodes.section):
        content = "".join(_render_node(c) for c in node)
        ids = node.get("ids", [])
        if ids:
            return f'<section id="{html_escape(ids[0], quote=True)}">\n{content}</section>\n'
        return content
    # For inline and other container nodes: just render children
    if hasattr(node, "children"):
        return "".join(_render_node(c) for c in node)
    return ""


def nodes_to_html(node_list):
    """Render a list of docutils nodes to an HTML body fragment."""
    return "".join(_render_node(node) for node in node_list)


def build_release_nav(releases, current_index):
    """Build navigation HTML for a release sub-page."""
    parts = ['<nav style="margin: 1em 0;">']
    parts.append('<a href="../changelog.html">&larr; Back to Release Notes</a>')
    newer = None
    older = None
    for i in range(current_index - 1, -1, -1):
        if releases[i]["entries"] and releases[i]["release"].number != "next":
            newer = releases[i]["release"]
            break
    for i in range(current_index + 1, len(releases)):
        if releases[i]["entries"]:
            older = releases[i]["release"]
            break
    if newer or older:
        parts.append(" &middot; ")
        if newer:
            v = newer.number
            parts.append(f'<a href="{v}.html">&larr; {v}</a>')
        if newer and older:
            parts.append(" &middot; ")
        if older:
            v = older.number
            parts.append(f'<a href="{v}.html">{v} &rarr;</a>')
    parts.append("</nav>")
    return "".join(parts)


def generate_changelog(app, doctree, docname):
    if docname != "changelog":
        return
    for bl in doctree.traverse(nodes.bullet_list):
        releases = collect_releases(bl.children)

        # Store release list for sidebar navigation (excluding "next")
        app.env.changelog_releases = [
            r["release"].number
            for r in releases
            if r["entries"] and r["release"].number != "next"
        ]

        released = [
            r for r in releases if r["release"].number != "next" and r["entries"]
        ]
        has_next = (
            releases
            and releases[0]["release"].number == "next"
            and releases[0]["entries"]
        )

        result = []
        # Link to latest release at top (before potentially long "next" section)
        if released:
            latest = released[0]["release"]
            v = latest.number
            d = latest["date"] or ""
            text = f"Latest release: {v} ({d})" if d else f"Latest release: {v}"
            ref = nodes.reference("", text, refuri=f"changelog/{v}.html")
            result.append(nodes.paragraph("", "", ref))
        # Show "next" (unreleased) entries inline if they exist
        if has_next:
            result.extend(
                construct_release_nodes(releases[0]["release"], releases[0]["entries"])
            )
        bl.replace_self(result)
        break


def generate_release_pages(app):
    """Generate individual HTML pages for each release."""
    try:
        doctree = app.env.get_doctree("changelog")
    except FileNotFoundError:
        return
    for bl in doctree.traverse(nodes.bullet_list):
        releases = collect_releases(bl.deepcopy().children)
        break
    else:
        return

    for i, release_data in enumerate(releases):
        if not release_data["entries"]:
            continue
        # "next" (unreleased) content lives on the main changelog page only
        if release_data["release"].number == "next":
            continue
        # Use docutils .deepcopy() instead of copy.deepcopy() — the latter
        # follows parent references and copies the entire connected doctree.
        release = release_data["release"].deepcopy()
        entries = release_data["entries"]
        version = release.number
        paragraph_node = construct_release_nodes(release, entries)
        body = nodes_to_html([paragraph_node])
        nav = build_release_nav(releases, i)
        context = {
            "title": format_release_title(release_data["release"]),
            "body": nav + body + nav,
            "metatags": "",
            "toc": "",
        }
        yield (f"changelog/{version}", context, "page.html")


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
    visible_count = 10
    current_idx = None
    for idx, version in enumerate(versions):
        if pagename == f"changelog/{version}":
            current_idx = idx
            break
    collapse = current_idx is None or current_idx < visible_count

    items = []
    for idx, version in enumerate(versions):
        current = " current" if idx == current_idx else ""
        extra_cls = ""
        style = ""
        if collapse and idx >= visible_count:
            extra_cls = " changelog-hidden"
            style = ' style="display:none"'
        href = pathto(f"changelog/{version}")
        items.append(
            f'<li class="toctree-l2{current}{extra_cls}"{style}>'
            f'<a class="reference internal" href="{href}">{version}</a></li>'
        )
    if collapse and len(versions) > visible_count:
        remaining = len(versions) - visible_count
        items.insert(
            visible_count,
            '<li class="toctree-l2" id="changelog-show-all">'
            f'<a href="#" onclick="'
            f"document.querySelectorAll('.changelog-hidden').forEach(e=>e.style.display='');"
            f"document.getElementById('changelog-show-all').remove();"
            f'return false"'
            f'">&hellip; {remaining} older releases</a></li>',
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

        return re.sub(
            r'(<li class="toctree-l1)([^"]*">)(<a [^>]*>Release Notes</a>)</li>',
            _inject,
            html,
            count=1,
        )

    context["toctree"] = _patched_toctree


def setup(app):
    for name in ISSUE_TYPES:
        app.add_role(name, issues_role)
    app.add_role("release", release_role)
    app.connect("doctree-resolved", generate_changelog)
    app.connect("html-collect-pages", generate_release_pages)
    app.connect("html-page-context", inject_changelog_sidebar)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
