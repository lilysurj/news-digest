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
