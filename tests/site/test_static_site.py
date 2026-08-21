from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "site" / "catalog.json"
LOCAL_REFERENCE = re.compile(r"(?:href|src)=\"(/SignalDesk/[^\"]*)\"")


def build_site(tmp_path: Path) -> Path:
    output = tmp_path / "site"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_site.py",
            "--output",
            str(output),
            "--base-url",
            "/SignalDesk",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return output


def resolve_generated_reference(output: Path, reference: str) -> Path:
    relative = reference.removeprefix("/SignalDesk/").split("#", 1)[0]
    candidate = output / relative
    if reference.endswith("/"):
        candidate /= "index.html"
    return candidate


def test_catalog_maps_all_canonical_blog_sources() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    articles = catalog["articles"]
    assert [article["number"] for article in articles] == [
        f"{number:02d}" for number in range(1, 19)
    ]
    assert len(catalog["phases"]) == 6
    assert len({article["slug"] for article in articles}) == 18
    for article in articles:
        source = ROOT / article["source"]
        assert source.is_file()
        assert source.read_text(encoding="utf-8").startswith("# ")


def test_build_produces_home_pages_articles_and_metadata(tmp_path: Path) -> None:
    output = build_site(tmp_path)
    required = [
        output / "index.html",
        output / "journey" / "index.html",
        output / "experiments" / "index.html",
        output / "labs" / "index.html",
        output / "capstone" / "index.html",
        output / "sitemap.xml",
        output / "robots.txt",
        output / ".nojekyll",
        output / "assets" / "site.css",
        output / "assets" / "site.js",
        output / "assets" / "favicon.svg",
        output / "assets" / "signaldesk-observability.png",
    ]
    assert all(path.is_file() for path in required)
    assert len(list((output / "chapters").glob("*/index.html"))) == 18
    manifest = json.loads((output / "build.json").read_text(encoding="utf-8"))
    assert manifest["articles"] == 18
    assert manifest["phases"] == 6
    assert manifest["base_url"] == "/SignalDesk"


def test_generated_local_links_and_assets_resolve(tmp_path: Path) -> None:
    output = build_site(tmp_path)
    broken = []
    for html_path in output.rglob("*.html"):
        content = html_path.read_text(encoding="utf-8")
        for reference in LOCAL_REFERENCE.findall(content):
            if not resolve_generated_reference(output, reference).exists():
                broken.append(f"{html_path.relative_to(output)} -> {reference}")
    assert broken == []


def test_homepage_preserves_claim_boundaries_and_product_visual(tmp_path: Path) -> None:
    output = build_site(tmp_path)
    homepage = (output / "index.html").read_text(encoding="utf-8")
    assert "A learning system, not a production deployment" in homepage
    assert "98%" in homepage
    assert "&lt;8s, missed" in homepage
    assert "/SignalDesk/assets/signaldesk-observability.png" in homepage
    assert "From data engineer to forward deployed engineer" in homepage


def test_site_css_avoids_gradient_and_oversized_card_radii() -> None:
    css = (ROOT / "site" / "assets" / "site.css").read_text(encoding="utf-8")
    assert "gradient(" not in css
    assert "border-radius: 8px" not in css
    assert "letter-spacing: -" not in css
