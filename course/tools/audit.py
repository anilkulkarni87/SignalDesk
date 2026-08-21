from __future__ import annotations

import re
from pathlib import Path
from typing import Any


MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REQUIRED_SECTIONS = (
    "## Outcome",
    "## Problem",
    "## First principles",
    "## Build",
    "## Measure",
    "## Break",
    "## Explain",
    "## Ship",
    "## Verify",
    "## Continue",
)


def audit_curriculum(root: Path, curriculum: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    lessons = curriculum.get("lessons", [])
    expected_ids = [f"{number:02d}" for number in range(1, 19)]
    actual_ids = [lesson.get("id") for lesson in lessons]
    if actual_ids != expected_ids:
        errors.append(f"lesson IDs must be ordered 01-18; got {actual_ids}")

    known_ids = set(actual_ids)
    for lesson in lessons:
        lesson_id = lesson.get("id", "unknown")
        status = lesson.get("status")
        if status not in {"available", "planned"}:
            errors.append(f"lesson {lesson_id}: invalid status {status!r}")
        for prerequisite in lesson.get("prerequisites", []):
            if prerequisite not in known_ids:
                errors.append(
                    f"lesson {lesson_id}: unknown prerequisite {prerequisite}"
                )
            elif prerequisite >= lesson_id:
                errors.append(
                    f"lesson {lesson_id}: prerequisite {prerequisite} must come earlier"
                )

        relative_path = lesson.get("lesson_path")
        if status == "planned":
            if relative_path is not None:
                errors.append(f"lesson {lesson_id}: planned lesson must not expose a path")
            continue
        if not relative_path:
            errors.append(f"lesson {lesson_id}: available lesson has no guide")
            continue
        path = root / relative_path
        if not path.is_file():
            errors.append(f"lesson {lesson_id}: missing guide {relative_path}")
            continue
        content = path.read_text(encoding="utf-8")
        if "Learning scope" not in content or "synthetic" not in content.lower():
            errors.append(f"lesson {lesson_id}: missing synthetic learning scope")
        for heading in REQUIRED_SECTIONS:
            if heading not in content:
                errors.append(f"lesson {lesson_id}: missing section {heading}")
        errors.extend(_broken_links(root, path, content))

    course_readme = root / "course" / "README.md"
    if not course_readme.is_file():
        errors.append("missing course/README.md")
    else:
        errors.extend(
            _broken_links(
                root,
                course_readme,
                course_readme.read_text(encoding="utf-8"),
            )
        )
    return errors


def _broken_links(root: Path, source: Path, content: str) -> list[str]:
    errors = []
    for raw_target in MARKDOWN_LINK.findall(content):
        target = raw_target.strip().split("#", maxsplit=1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (source.parent / target).resolve()
        if not resolved.exists():
            errors.append(
                f"{source.relative_to(root)}: broken local link {raw_target}"
            )
    return errors
