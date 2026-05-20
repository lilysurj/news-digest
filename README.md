# News Digest

A small Python script that pulls public RSS feeds across **cybersecurity**,
**foreign policy**, **China & US-China policy**, and **general current
events**, filters to the last 24 hours, ranks items by tunable keyword
boosts, and writes a dated Markdown digest (also printed to the console).

No logins, no paywall scraping, no stored credentials, no LLM API calls.

## Ranking

Within each category, items are sorted by a keyword score (then publish
time as a tiebreaker), so high-signal stories take the top slots. All
tunables live in a config block at the top of `digest.py`:

- `KEYWORD_WEIGHTS` — tiered boost lists (3 / 2 / 1) matched whole-word,
  case-insensitive, against title + summary.
- `CYBER_DOMAIN` / `GEO_DOMAIN` + `CROSS_DOMAIN_BONUS` — items that hit
  both a cyber and a geo keyword get an extra bump, so a "Chinese APT
  exploits zero-day in Taiwan" outranks a pure-cyber story.
- `MUTE_KEYWORDS` — drop any item whose title contains a muted term.
  Starts empty.

Edit these lists freely; no other code change needed.

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
python digest.py --html-preview        # also write a styled .html preview
python digest.py --quiet               # suppress info logs
```

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

Runs daily at 07:00 local time. Edit your crontab with `crontab -e` and add a
line that `cd`s into your local checkout and runs `digest.py` with the venv's
Python, redirecting output to a log file. On macOS, cron may need Full Disk
Access (System Settings → Privacy & Security → Full Disk Access → add
`/usr/sbin/cron`) to write into protected directories like `Documents`.

### Option B: GitHub Actions

The workflow at `.github/workflows/digest.yml` runs daily at 11:00 UTC
(7am Eastern during DST, 6am EST after DST ends), commits the new
`digest-YYYY-MM-DD.md` back to the repo, and uploads it as a build artifact.
To also receive the digest by email, add the `SMTP_*` secrets described above
under **Settings → Secrets and variables → Actions**.
