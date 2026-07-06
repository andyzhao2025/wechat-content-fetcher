# wechat-content-fetcher

Export WeChat articles from Tencent IMA folders into a static website, and optionally emit NotebookLM-ready bundle pages that pack many articles into a smaller number of sources.

## What It Does

- Reads article entries from a target IMA knowledge-base folder
- Fetches each WeChat article via `url-md`
- Generates one HTML page per article
- Generates a human-browsable folder index and root index
- Generates NotebookLM bundle pages grouped by directory family
- Updates bundles incrementally so unchanged groups do not need to be rebuilt

## Quick Start

```bash
python -m pip install -r requirements.txt
python run_fetcher.py --config config.example.json --mode fixture
```

The default output directory is `site_output/`.

## Real IMA Mode

Real mode uses the local `ima_api.cjs` bridge and these IMA APIs:

- `search_knowledge_base`
- `get_knowledge_list`
- `search_knowledge`
- `get_media_info`

Example:

```bash
python run_fetcher.py --config config.ima.json --mode ima --reason scheduled_daily --ima-script C:\Users\Administrator\.openclaw-ima\workspace\skills\ima-skill\ima_api.cjs
```

Supported sync reasons:

- `scheduled_daily` - scan metadata and skip unchanged targets
- `manual` - force processing after a user-reported IMA edit
- `monthly_audit` - full deep rebuild for reconciliation

Examples:

```bash
python run_fetcher.py --config config.ima.json --mode ima --reason scheduled_daily --ima-script C:\Users\Administrator\.openclaw-ima\workspace\skills\ima-skill\ima_api.cjs
python run_fetcher.py --config config.ima.json --mode ima --reason manual --force --ima-script C:\Users\Administrator\.openclaw-ima\workspace\skills\ima-skill\ima_api.cjs
python run_fetcher.py --config config.ima.json --mode ima --reason monthly_audit --full-rescan --ima-script C:\Users\Administrator\.openclaw-ima\workspace\skills\ima-skill\ima_api.cjs
```

If IMA returns a daily quota exhaustion error, the run is recorded as `partial` and remaining article IDs stay queued for the next run.

## NotebookLM Bundles

NotebookLM website sources do not recursively follow links, so directory index pages are not enough by themselves. This project therefore emits bundle pages that inline article bodies directly.

By default the bundle output is enabled and written to:

```text
site_output/notebooklm/<target-slug>/
```

Each target bundle directory contains:

- `index.html` - bundle listing page
- `manifest.json` - bundle manifest for incremental rebuild
- `notebooklm-urls.txt` - one bundle URL per line
- `*.html` - the actual bundle pages

## Bundle Strategy

- Bundle family boundary: current article group name
- Incremental rebuild: only changed groups are rewritten
- Split conditions:
  - `max_bundle_articles`
  - `max_bundle_words`

Recommended publishing flow:

1. Publish the generated site to GitHub Pages
2. Use `notebooklm-urls.txt` as the import list for NotebookLM

## GitHub Pages

This project publishes prebuilt static output. GitHub Actions does not fetch IMA content itself.

Local flow:

```bash
python run_fetcher.py --config config.ima.json --mode ima --reason scheduled_daily --ima-script C:\Users\Administrator\.openclaw-ima\workspace\skills\ima-skill\ima_api.cjs
python run_fetcher.py --config config.ima.json --mode pages
```

After `pages` mode, the publish artifact is prepared at:

```text
site_output/_pages/
```

The included workflow publishes that directory to GitHub Pages on push to `main`.

### Set `base_url`

Before you want NotebookLM import URLs instead of relative filenames, set:

```json
{
  "base_url": "https://<github-username>.github.io/<repo-name>"
}
```

Then rerun:

```bash
python run_fetcher.py --config config.ima.json --mode ima --reason scheduled_daily --ima-script C:\Users\Administrator\.openclaw-ima\workspace\skills\ima-skill\ima_api.cjs
python run_fetcher.py --config config.ima.json --mode pages
```

The generated `notebooklm-urls.txt` will then contain public GitHub Pages URLs.

## Config Fields

```json
{
  "build_notebooklm_bundles": true,
  "notebooklm_dir_name": "notebooklm",
  "bundle_mode": "incremental",
  "max_bundle_articles": 25,
  "max_bundle_words": 120000
}
```

## Current Status

- Fixture mode is fully covered by tests
- IMA mode is wired to the local skill bridge
- NotebookLM bundle generation is available and tested
