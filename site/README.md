# SignalDesk Learning Site

The site is a static reading layer over the repository's 18 canonical posts in
`docs/blog`. It does not duplicate the article content or require model calls.

## Build locally

```bash
pip install -r requirements-site.txt
python scripts/build_site.py
python -m http.server 4173 --directory _site
```

Open `http://127.0.0.1:4173/`.

To verify the repository-path version used by GitHub Pages:

```bash
python scripts/build_site.py \
  --base-url /SignalDesk \
  --output /tmp/signaldesk-pages-preview/SignalDesk
python -m http.server 4173 --directory /tmp/signaldesk-pages-preview
```

Open `http://127.0.0.1:4173/SignalDesk/`. The automated tests also validate the
repository prefix without starting a server.

## Publish with GitHub Pages

The workflow in `.github/workflows/pages.yml` builds and deploys the site after
a successful push to `main`.

1. Merge the site changes into `main`.
2. In GitHub, open **Settings > Pages**.
3. Set **Source** to **GitHub Actions**.
4. Open the `Deploy SignalDesk learning site` workflow and confirm that the
   build and deploy jobs pass.
5. Verify `https://anilkulkarni87.github.io/SignalDesk/` before publishing the
   LinkedIn sequence.

## Content ownership

- Edit long-form posts in `docs/blog`.
- Edit ordering, summaries, phases, and slugs in `site/catalog.json`.
- Edit page-specific copy in `site/pages`.
- Edit presentation in `site/templates` and `site/assets`.
- Never edit `_site`; it is generated and ignored.

Run the site tests before publishing:

```bash
python -m pytest tests/site -q
```
