# Handoff — News Digest

A pointer doc for a fresh coding agent (or future-you) picking this project
up. Read this first, then `digest.py`.

## What this is

A single-file Python script that fetches public RSS feeds across three
categories (cybersecurity / foreign policy / general current events),
filters to the last 24 hours, dedupes, and renders a dated Markdown
digest. Optional SMTP delivery with an HTML email body. Designed to be
run daily from cron or GitHub Actions.

## Hard constraints (from the original spec — do not violate)

- **Public RSS only.** No logins, no paid API keys for news sources, no
  scraping behind paywalls. WSJ / NYT are OK because their RSS endpoints
  are public — only the article bodies are gated.
- **No stored credentials.** All secrets come from env vars; nothing is
  committed.
- **Graceful failure.** A dead/timed-out feed must skip with a log line,
  never crash the run.
- **Single dependency-light script.** Don't split into packages or add
  frameworks. Type hints, `main()`, `if __name__ == "__main__"`.

## File map

```
news-digest/
├── digest.py                      # the whole script — fetch, filter, render, optional SMTP
├── requirements.txt               # feedparser, requests, markdown (all pinned)
├── README.md                      # user-facing: install + run + cron + GH Actions
├── handoff.md                     # this file
└── .github/workflows/digest.yml   # daily 12:00 UTC, runs script, commits dated .md back
```

The script is intentionally one file. Resist the urge to split it.

## Architecture (one-paragraph version)

`fetch_all()` runs `fetch_feed()` across a `ThreadPoolExecutor` (max 8) —
each feed is fetched via `requests` with a 15s timeout and parsed by
`feedparser`. Items are normalized into a frozen `Item` dataclass.
`filter_recent()` drops anything older than `WINDOW_HOURS` (24).
`dedupe()` collapses near-duplicate titles (stripped of punctuation,
first 80 chars) keeping the newest. `group_and_rank()` sorts each
category by publish time and caps at `ITEMS_PER_CATEGORY` (8). The
markdown digest is written to `digest-YYYY-MM-DD.md` and printed to
stdout. With `--email`, `send_email()` sends a multipart/alternative
message: the raw markdown as plain text + an HTML body rendered via
the `markdown` package using `_HTML_TEMPLATE`.

## CLI surface

```
python digest.py [--output-dir DIR] [--email] [--html-preview] [--quiet]
```

- `--output-dir` — where to write the `.md` (default: cwd)
- `--email` — also send via SMTP; reads `SMTP_*` env vars; silent no-op
  if `SMTP_HOST` is unset, so it's safe to wire up unconditionally
- `--html-preview` — also write `digest-YYYY-MM-DD.html` next to the .md
  so you can eyeball how the email body will render
- `--quiet` — drop log level from INFO to WARNING

## Env vars (SMTP)

| Var | Required | Notes |
|---|---|---|
| `SMTP_HOST` | yes (for `--email`) | e.g. `smtp.gmail.com`; if unset, email step no-ops |
| `SMTP_FROM` | yes | sender address |
| `SMTP_TO`   | yes | comma-separated recipients |
| `SMTP_PORT` | no  | default `587` |
| `SMTP_USER` | no  | if your server requires auth |
| `SMTP_PASS` | no  | use an app password, not the real password |

The GitHub Actions workflow already wires all six through from repo
secrets.

## Current state (as of 2026-05-20)

**Done:**
- Feed fetching with timeouts, thread pool, graceful skip on failures
- 24h window, dedupe, per-category cap of 8 items
- Markdown rendering — header, per-category sections, numbered items
  with source link
- HTML email template (styled card layout, GitHub-ish palette) +
  `--html-preview` for local previewing
- SMTP delivery with multipart text+HTML body
- GitHub Actions workflow: daily 12:00 UTC, commits the dated .md back
  to the repo, uploads as artifact, passes SMTP secrets through

**Removed deliberately:**
- The AI synthesis layer (Anthropic `--ai` flag, `heuristic_synthesis`,
  `ai_synthesis`, `_STOPWORDS`, `DEFAULT_MODEL`). The digest is now
  pure headlines + summaries, no per-category "throughline" paragraph.
  Don't add this back unless asked.
- Reuters World feed (the `feeds.reuters.com` endpoint was deprecated
  by Reuters years ago and silently returned zero items).

## Known stale / loose ends

- **`README.md` lines 58–60 still reference `ANTHROPIC_API_KEY` and
  "falls back to the heuristic version".** That's stale — AI synthesis
  was removed. Worth cleaning up next time someone touches the README.
- **macOS cron + Documents directory needs Full Disk Access.** Already
  documented in the README. If a digest cron silently produces no
  output on macOS, this is almost always why.
- **WSJ / NYT RSS endpoints occasionally return 403 or rate-limit.**
  The script logs and skips — expected behavior, not a bug. If they
  break permanently, swap in another general-news feed.

## How to verify a change

There's no test suite. Smoke test by:

```sh
source .venv/bin/activate
python digest.py --output-dir /tmp/digest-test
cat /tmp/digest-test/digest-*.md
```

For email changes:

```sh
python digest.py --html-preview --output-dir /tmp/digest-test
open /tmp/digest-test/digest-*.html   # eyeball the styled output
```

For workflow changes: use `workflow_dispatch` in the Actions tab to
trigger a manual run before relying on the schedule.

## Things to avoid

- Don't add scraping of paywalled article bodies. Headlines + RSS
  summaries only.
- Don't hardcode secrets, even in workflow files — secrets must come
  from `${{ secrets.* }}` or env.
- Don't introduce a `config.yaml` / settings module. The `FEEDS` dict
  at the top of `digest.py` is the config.
- Don't add retries with backoff to `fetch_feed()` — feeds that fail
  once today are usually fine tomorrow, and a retry storm against
  e.g. CISA isn't friendly.
