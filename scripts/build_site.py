#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape


ROOT = Path(__file__).resolve().parents[1]
SITE_SOURCE = ROOT / "site"
TEMPLATES = SITE_SOURCE / "templates"
CATALOG_PATH = SITE_SOURCE / "catalog.json"
H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
WORD = re.compile(r"\b[\w'-]+\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the SignalDesk static site.")
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    parser.add_argument("--base-url", default="")
    parser.add_argument(
        "--site-url",
        default="https://anilkulkarni87.github.io/SignalDesk",
    )
    return parser.parse_args()


def normalize_base_url(value: str) -> str:
    value = value.strip()
    if not value or value == "/":
        return ""
    return "/" + value.strip("/")


def read_markdown(path: Path) -> tuple[str, str, int]:
    source = path.read_text(encoding="utf-8")
    match = H1.search(source)
    if not match:
        raise ValueError(f"Markdown source has no H1: {path.relative_to(ROOT)}")
    title = match.group(1).strip()
    body = source[: match.start()] + source[match.end() :]
    html = markdown.markdown(
        body.strip(),
        extensions=["fenced_code", "tables", "toc"],
        output_format="html5",
    )
    reading_minutes = max(1, round(len(WORD.findall(body)) / 200))
    return title, html, reading_minutes


def write_page(output: Path, relative: str, html: str) -> None:
    destination = output / relative.strip("/") / "index.html"
    if relative in {"", "/"}:
        destination = output / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")


def validate_output(output: Path) -> Path:
    output = output.expanduser().resolve()
    protected = {ROOT, SITE_SOURCE, Path(output.anchor), *ROOT.parents}
    if output in protected:
        raise ValueError("refusing to use a protected directory as site output")
    marker = output / ".signaldesk-site-output"
    if (
        output.exists()
        and any(output.iterdir())
        and output.name != "_site"
        and not marker.is_file()
    ):
        raise ValueError(
            "refusing to replace a populated directory not owned by the site builder"
        )
    return output


def main() -> int:
    args = parse_args()
    output = validate_output(args.output)
    base_url = normalize_base_url(args.base_url)
    site_url = args.site_url.rstrip("/")
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    phases = catalog["phases"]
    articles = catalog["articles"]
    if [article["number"] for article in articles] != [
        f"{number:02d}" for number in range(1, 19)
    ]:
        raise ValueError("site catalog must contain ordered articles 01-18")

    phase_by_id = {phase["id"]: phase for phase in phases}
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.globals.update(base_url=base_url, site_url=site_url)

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / ".signaldesk-site-output").write_text("SignalDesk static site\n")
    shutil.copytree(SITE_SOURCE / "assets", output / "assets")

    rendered_articles = []
    for article in articles:
        source_path = ROOT / article["source"]
        title, content, reading_minutes = read_markdown(source_path)
        phase = phase_by_id[article["phase"]]
        url = f"/chapters/{article['slug']}/"
        enriched = {
            **article,
            "title": title,
            "content": content,
            "reading_minutes": reading_minutes,
            "phase_data": phase,
            "url": url,
        }
        rendered_articles.append(enriched)

    for index, article in enumerate(rendered_articles):
        previous = rendered_articles[index - 1] if index else None
        next_article = (
            rendered_articles[index + 1]
            if index + 1 < len(rendered_articles)
            else None
        )
        html = environment.get_template("article.html").render(
            page_title=article["title"],
            page_description=article["summary"],
            canonical_url=site_url + article["url"],
            active="journey",
            article=article,
            previous=previous,
            next_article=next_article,
        )
        write_page(output, article["url"], html)

    grouped = []
    for phase in phases:
        grouped.append(
            {
                **phase,
                "articles": [
                    article
                    for article in rendered_articles
                    if article["phase"] == phase["id"]
                ],
            }
        )

    home = environment.get_template("home.html").render(
        page_title="SignalDesk - From Data Engineer to FDE",
        page_description=catalog["site_description"],
        canonical_url=site_url + "/",
        active="home",
        phases=grouped,
        articles=rendered_articles,
    )
    write_page(output, "", home)

    for slug, source, title, description in (
        (
            "journey",
            "site/pages/journey.md",
            "The 18-Milestone Journey",
            "Six phases connecting customer discovery, AI engineering, operations, and FDE delivery.",
        ),
        (
            "experiments",
            "site/pages/experiments.md",
            "Experiments and Evidence",
            "The measured results, failed targets, and claim boundaries behind SignalDesk.",
        ),
        (
            "code",
            "site/pages/code.md",
            "Code Companion",
            "Connect SignalDesk concepts to selected source files, real commands, measured evidence, and explicit boundaries.",
        ),
        (
            "capstone",
            "site/pages/capstone.md",
            "FDE Capstone",
            "A ten-minute evidence-based presentation of what SignalDesk proved and what remains unknown.",
        ),
    ):
        _, content, reading_minutes = read_markdown(ROOT / source)
        html = environment.get_template("page.html").render(
            page_title=title,
            page_description=description,
            canonical_url=site_url + f"/{slug}/",
            active=slug,
            title=title,
            description=description,
            content=content,
            reading_minutes=reading_minutes,
            phases=grouped,
            articles=rendered_articles,
        )
        write_page(output, slug, html)

    urls = ["/", "/journey/", "/code/", "/experiments/", "/capstone/"] + [
        article["url"] for article in rendered_articles
    ]
    sitemap = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *[
                f"  <url><loc>{escape(site_url + url)}</loc></url>"
                for url in urls
            ],
            "</urlset>",
            "",
        ]
    )
    (output / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (output / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {site_url}/sitemap.xml\n",
        encoding="utf-8",
    )
    (output / ".nojekyll").write_text("", encoding="utf-8")
    (output / "build.json").write_text(
        json.dumps(
            {
                "articles": len(rendered_articles),
                "phases": len(grouped),
                "built_on": date.today().isoformat(),
                "base_url": base_url,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Built {len(rendered_articles)} articles across {len(grouped)} phases "
        f"at {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
