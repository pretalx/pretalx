# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

ALLOWED_REASONS: dict[str, tuple[str, ...]] = {
    "slow import": ("**",),
    "optional dependency": ("**",),
    "circular import": ("**",),
    "thin method": ("src/pretalx/*/models/**.py", "src/pretalx/*/models.py"),
    "leaf": ("src/pretalx/*/tasks.py", "src/pretalx/*/signals.py"),
    "predicate": (
        "src/pretalx/*/rules.py",
        "src/pretalx/*/validators.py",
        "src/pretalx/*/validators/**.py",
    ),
    "receiver": ("src/pretalx/*/receivers.py", "src/pretalx/*/signals.py"),
    "app ready": ("src/pretalx/*/apps.py",),
}

# Matches a noqa directive at the end of a line; captures the code list and the
# optional trailing reason text after ``--``.
NOQA_RE = re.compile(
    r"#\s*noqa\s*:\s*(?P<codes>[A-Z0-9, ]+?)\s*(?:--\s*(?P<reason>.+?))?\s*$"
)


def find_violations(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent.parent)  # relative to project root
        rel_str = rel.as_posix()
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = NOQA_RE.search(line)
            if not match:
                continue
            codes = {c.strip() for c in match.group("codes").split(",")}
            if "PLC0415" not in codes:
                continue
            reason = (match.group("reason") or "").strip().rstrip(".")
            if not reason:
                errors.append(
                    f"{rel_str}:{lineno}: PLC0415 suppression has no reason; "
                    f"expected one of: {', '.join(sorted(ALLOWED_REASONS))}"
                )
                continue
            allowed_globs = ALLOWED_REASONS.get(reason)
            if allowed_globs is None:
                errors.append(
                    f"{rel_str}:{lineno}: PLC0415 reason {reason!r} not in schema; "
                    f"expected one of: {', '.join(sorted(ALLOWED_REASONS))}"
                )
                continue
            if not any(
                fnmatch.fnmatchcase(rel_str, pattern) for pattern in allowed_globs
            ):
                errors.append(
                    f"{rel_str}:{lineno}: PLC0415 reason {reason!r} not permitted "
                    f"here; allowed in: {', '.join(allowed_globs)}"
                )
    return errors


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    pretalx_root = project_root / "src" / "pretalx"
    errors = find_violations(pretalx_root)
    if errors:
        print("\n".join(errors))
        print(f"\n{len(errors)} PLC0415 reason violation(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
