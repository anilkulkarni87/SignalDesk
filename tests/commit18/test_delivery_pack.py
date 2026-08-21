from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "docs" / "fde"
REQUIRED_DOCUMENTS = {
    "README.md",
    "discovery.md",
    "requirements.md",
    "architecture.md",
    "security.md",
    "evaluation.md",
    "deployment.md",
    "runbook.md",
    "roi.md",
    "known_limitations.md",
    "roadmap.md",
    "demo.md",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_delivery_pack_contains_every_required_document() -> None:
    actual = {path.name for path in PACK.glob("*.md")}
    assert REQUIRED_DOCUMENTS <= actual
    assert (ROOT / "README_COMMIT18.md").is_file()
    assert (
        ROOT
        / "docs"
        / "blog"
        / "18-from-ai-engineer-to-fde-delivering-evidence-not-a-demo.md"
    ).is_file()


def test_every_delivery_document_declares_the_learning_scope() -> None:
    for name in sorted(REQUIRED_DOCUMENTS):
        content = (PACK / name).read_text(encoding="utf-8").lower()
        assert "learning scope" in content, name
        assert "synthetic" in content, name


def test_frozen_behavior_is_explicit() -> None:
    overview = (ROOT / "README_COMMIT18.md").read_text(encoding="utf-8")
    assert "gpt-5.6-luna" in overview
    assert "reasoning effort  none" in overview
    assert "commit10_v4_campaign_evidence_budget" in overview
    assert "lexical_current_approved" in overview
    assert "No prompt, retriever, model, tool, workflow, API, or UI behavior" in overview


def test_local_markdown_links_resolve() -> None:
    markdown_files = [PACK / name for name in REQUIRED_DOCUMENTS]
    markdown_files.append(ROOT / "README_COMMIT18.md")

    broken: list[str] = []
    for source in markdown_files:
        for target in MARKDOWN_LINK.findall(source.read_text(encoding="utf-8")):
            target = target.strip().split("#", maxsplit=1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (source.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{source.relative_to(ROOT)} -> {target}")

    assert broken == []
