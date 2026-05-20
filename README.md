# News Digest

A small Python script that pulls public RSS feeds across **cybersecurity**,
**foreign policy**, and **general current events**, filters to the last 24
hours, and writes a dated Markdown digest (also printed to the console).

No logins, no paywall scraping, no stored credentials.

## Install

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```sh
python digest.py                       # writes digest-YYYY-MM-DD.md in cwd
python digest.py --output-dir digests  # write into ./digests/
python digest.py --ai                  # use Anthropic for per-category synthesis
python digest.py --quiet               # suppress info logs
```

The `--ai` flag is silent-fallback: if `ANTHROPIC_API_KEY` is unset or the
`anthropic` package is missing, it uses the heuristic synthesis instead.

### Optional email delivery

`send_email()` is wired up but off by default. Pass `--email` and set:

| Var         | Required | Notes                                      |
|-------------|----------|--------------------------------------------|
| `SMTP_HOST` | yes      | e.g. `smtp.gmail.com`                      |
| `SMTP_FROM` | yes      | sender address                             |
| `SMTP_TO`   | yes      | comma-separated recipients                 |
| `SMTP_PORT` | no       | default `587`                              |
| `SMTP_USER` | no       | if your server requires auth               |
| `SMTP_PASS` | no       | use an app password, not your real one     |

## Daily scheduling — pick one

### Option A: macOS / Linux cron

Runs daily at 07:00 local time. Edit your crontab with `crontab -e` and add:

```cron
0 7 * * * cd /Users/lily/Documents/news-digest && /Users/lily/Documents/news-digest/.venv/bin/python digest.py --output-dir digests >> digest.log 2>&1
```

If you want the AI synthesis, put your key in the crontab's environment:

```cron
ANTHROPIC_API_KEY=sk-ant-...
0 7 * * * cd /Users/lily/Documents/news-digest && /Users/lily/Documents/news-digest/.venv/bin/python digest.py --ai --output-dir digests >> digest.log 2>&1
```

Note: on macOS, cron may need Full Disk Access (System Settings → Privacy &
Security → Full Disk Access → add `/usr/sbin/cron`) to write into `Documents`.

### Option B: GitHub Actions

Commit this repo to GitHub. The workflow at `.github/workflows/digest.yml`
runs daily at 12:00 UTC, commits the new `digest-YYYY-MM-DD.md` back to the
repo, and uploads it as a build artifact.

For AI synthesis, add `ANTHROPIC_API_KEY` under **Settings → Secrets and
variables → Actions → New repository secret**. The workflow already passes
it through; without the secret it falls back to the heuristic version.
