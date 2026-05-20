#!/usr/bin/env python3
"""Daily news digest: cybersecurity, foreign policy, general current events.

Fetches public RSS feeds, filters to the last 24 hours, groups by category,
and renders a Markdown digest both to stdout and to a dated file. Optionally
delivers a styled HTML version by email.

No logins, no paywall scraping, no stored credentials.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import smtplib
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import unescape
from pathlib import Path

import feedparser
import requests

# ---------------------------------------------------------------------------
# Config — edit feed URLs here. Any feed that 404s or times out is skipped.
# ---------------------------------------------------------------------------

FEEDS: dict[str, dict[str, str]] = {
    "Cybersecurity": {
        "Krebs on Security": "https://krebsonsecurity.com/feed/",
        "The Record":        "https://therecord.media/feed",
        "Bleeping Computer": "https://www.bleepingcomputer.com/feed/",
        "The Hacker News":   "https://feeds.feedburner.com/TheHackersNews",
        "CISA Advisories":   "https://www.cisa.gov/cybersecurity-advisories/all.xml",
    },
    "Foreign Policy": {
        "CFR":               "https://www.cfr.org/rss.xml",
        "War on the Rocks":  "https://warontherocks.com/feed/",
        "Lawfare":           "https://www.lawfaremedia.org/feed.xml",
        "Foreign Policy":    "https://foreignpolicy.com/feed/",
    },
    "China & US-China Policy": {
        "The Diplomat":         "https://thediplomat.com/feed/",
        "China Digital Times":  "https://chinadigitaltimes.net/feed/",
    },
    "General Current Events": {
        "NPR News":          "https://feeds.npr.org/1001/rss.xml",
        "BBC News":          "http://feeds.bbci.co.uk/news/rss.xml",
        "WSJ World":         "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "NYT Home":          "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    },
}

REQUEST_TIMEOUT = 15        # seconds per feed
WINDOW_HOURS = 24
ITEMS_PER_CATEGORY = 8
USER_AGENT = "news-digest/1.0 (+rss aggregator)"

log = logging.getLogger("digest")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    title: str
    summary: str
    link: str
    source: str
    category: str
    published: datetime  # tz-aware UTC


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        struct = entry.get(key)
        if not struct:
            continue
        try:
            return datetime(*struct[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def fetch_feed(category: str, name: str, url: str) -> list[Item]:
    """Fetch one feed. Returns items (possibly empty). Never raises."""
    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("skip %s: %s", name, exc)
        return []

    parsed = feedparser.parse(resp.content)
    items: list[Item] = []
    for entry in parsed.entries:
        pub = _parse_published(entry)
        if pub is None:
            continue
        title = _clean(entry.get("title", ""))
        if not title:
            continue
        summary = _clean(entry.get("summary", "") or entry.get("description", ""))
        if len(summary) > 220:
            summary = summary[:217].rstrip() + "..."
        items.append(Item(
            title=title,
            summary=summary,
            link=(entry.get("link") or "").strip(),
            source=name,
            category=category,
            published=pub,
        ))
    log.info("fetched %d items from %s", len(items), name)
    return items


def fetch_all(feeds: dict[str, dict[str, str]]) -> list[Item]:
    jobs = [
        (category, name, url)
        for category, sources in feeds.items()
        for name, url in sources.items()
    ]
    out: list[Item] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(fetch_feed, c, n, u) for c, n, u in jobs]
        for fut in as_completed(futures):
            out.extend(fut.result())
    return out


# ---------------------------------------------------------------------------
# Filter, dedupe, rank
# ---------------------------------------------------------------------------

def filter_recent(items: list[Item], hours: int) -> list[Item]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [i for i in items if i.published >= cutoff]


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", t.lower()).strip()


def dedupe(items: list[Item]) -> list[Item]:
    """Drop items with effectively identical titles, keeping the newest."""
    seen: set[str] = set()
    out: list[Item] = []
    for item in sorted(items, key=lambda x: x.published, reverse=True):
        key = _norm_title(item.title)[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def group_and_rank(items: list[Item], per_category: int) -> dict[str, list[Item]]:
    grouped: dict[str, list[Item]] = {cat: [] for cat in FEEDS}
    for item in items:
        grouped.setdefault(item.category, []).append(item)
    for cat in grouped:
        grouped[cat] = sorted(grouped[cat], key=lambda x: x.published, reverse=True)[:per_category]
    return grouped


# ---------------------------------------------------------------------------
# Topics — recurring proper-noun-ish words across headlines
# ---------------------------------------------------------------------------

_TOPIC_FILLER = {
    # Function words that sometimes start headlines (and so get capitalized)
    "the", "a", "an", "this", "that", "these", "those",
    "after", "before", "amid", "while", "when", "where", "what", "how", "why",
    "with", "into", "from", "about", "against", "across",
    "new", "first", "last", "next", "more", "most", "much",
    "is", "was", "were", "are", "be", "been", "have", "has", "had",
    "but", "and", "or", "for", "to", "in", "on", "at", "of", "by",
    # Generic news verbs that occasionally start a sentence in a title
    "report", "reports", "reported", "says", "said", "saying",
    "tells", "told", "warns", "warned",
    "claims", "claimed", "denies", "denied",
    "calls", "called", "urges", "urged",
    "announces", "announced", "expected", "according",
    "could", "would", "should", "may", "might",
    "today", "yesterday",
}


def extract_topics(items: list[Item], max_topics: int = 5) -> list[str]:
    """Return recurring topic words across the given headlines.

    Only considers words capitalized in the original headline (a proper-noun
    bias — catches Citrix, Russia, Treasury, etc., and ignores "according",
    "says", "report"). Word must be ≥4 chars, not in the filler list, and
    appear in ≥2 headlines.
    """
    if not items:
        return []
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for item in items:
        for word in re.findall(r"\b[A-Z][A-Za-z]{3,}\b", item.title):
            key = word.lower()
            if key in _TOPIC_FILLER:
                continue
            counts[key] += 1
            display.setdefault(key, word)
    return [display[k] for k, n in counts.most_common(max_topics) if n >= 2]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_markdown(
    when: datetime,
    grouped: dict[str, list[Item]],
) -> str:
    lines: list[str] = []
    lines.append(f"# News Digest — {when:%Y-%m-%d}")
    lines.append("")
    lines.append(f"_Generated {when:%Y-%m-%d %H:%M UTC}. Window: last {WINDOW_HOURS} hours._")
    lines.append("")
    for category in FEEDS:
        items = grouped.get(category, [])
        lines.append(f"## {category}")
        lines.append("")
        topics = extract_topics(items)
        if topics:
            lines.append(f"**Topics:** {' · '.join(topics)}")
            lines.append("")
        if not items:
            lines.append("_No items._")
            lines.append("")
            continue
        for n, item in enumerate(items, 1):
            tail = f" — [{item.source}]({item.link})" if item.link else f" — {item.source}"
            lines.append(f"{n}. **{item.title}**{tail}")
            if item.summary:
                lines.append(f"   {item.summary}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Optional email delivery (off by default — passes --email to enable)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>News Digest</title>
<style>
  body {{ margin: 0; padding: 0; background: #f6f8fa;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                      "Helvetica Neue", Arial, sans-serif;
         color: #1f2328; line-height: 1.55; }}
  .wrap {{ padding: 28px 14px; }}
  .card {{ max-width: 640px; margin: 0 auto; background: #ffffff;
          border: 1px solid #d0d7de; border-radius: 10px; }}
  .inner {{ padding: 28px 34px; }}
  h1 {{ font-size: 22px; margin: 0 0 6px 0; color: #0d1117;
       letter-spacing: -0.01em; }}
  h1 + p em {{ color: #6e7681; font-size: 13px; font-style: normal; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
       margin: 32px 0 12px 0; padding-bottom: 8px;
       border-bottom: 2px solid #0d1117; color: #0d1117; }}
  ol {{ padding-left: 22px; margin: 12px 0 0 0; }}
  li {{ margin-bottom: 14px; padding-left: 4px; }}
  li strong {{ color: #0d1117; font-weight: 600; }}
  a {{ color: #0969da; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .topics {{ margin: 4px 0 18px 0; }}
  .topics-label {{ display: inline-block; font-size: 11px;
                   letter-spacing: 0.1em; text-transform: uppercase;
                   color: #6e7681; font-weight: 600; margin-right: 6px;
                   vertical-align: middle; }}
  .topic-tag {{ display: inline-block; padding: 2px 10px;
                background: #ddf4ff; border: 1px solid #b6e3ff;
                border-radius: 999px; font-size: 12px; color: #0969da;
                font-weight: 500; margin-right: 4px; margin-bottom: 4px;
                vertical-align: middle; }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="inner">
{body}
      </div>
    </div>
  </div>
</body>
</html>
"""


def _render_html(digest_md: str) -> str:
    """Render the digest as a styled HTML email body."""
    import markdown as _md

    body = _md.markdown(digest_md, extensions=["extra", "sane_lists"])

    def _topics_to_pills(match: re.Match[str]) -> str:
        topics = [t.strip() for t in match.group(1).split("·") if t.strip()]
        if not topics:
            return ""
        tags = "".join(f'<span class="topic-tag">{t}</span>' for t in topics)
        return (
            '<div class="topics">'
            '<span class="topics-label">Topics</span>'
            f"{tags}"
            "</div>"
        )

    body = re.sub(
        r"<p><strong>Topics:</strong>\s*(.*?)</p>",
        _topics_to_pills,
        body,
        flags=re.DOTALL,
    )
    return _HTML_TEMPLATE.format(body=body)


def send_email(digest_md: str, subject: str) -> None:
    """Send the digest via SMTP. All credentials read from env vars so nothing
    sensitive lives in source.

    Required env vars:
        SMTP_HOST              # e.g. smtp.gmail.com
        SMTP_FROM              # sender address
        SMTP_TO                # comma-separated recipients
    Optional:
        SMTP_PORT              # default 587
        SMTP_USER, SMTP_PASS   # if your server requires auth

    No-op (with a log line) if SMTP_HOST is missing, so this is safe to leave
    wired up.
    """
    host = os.environ.get("SMTP_HOST")
    if not host:
        log.info("SMTP_HOST not set; skipping email.")
        return
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")
    sender = os.environ.get("SMTP_FROM", user)
    recipients = [r.strip() for r in os.environ.get("SMTP_TO", "").split(",") if r.strip()]
    if not sender or not recipients:
        log.warning("SMTP_FROM / SMTP_TO not configured; skipping email.")
        return

    # Diagnostic: log lengths + last char of each value so we can spot trailing
    # whitespace, wrong-length pastes, or off-by-one typos without leaking the
    # secret itself (GitHub auto-redacts known secret values in logs anyway).
    def _suffix(s: str) -> str:
        return repr(s[-1]) if s else "''"
    log.warning(
        "SMTP DIAG: host=%r port=%d user_len=%d user_last=%s "
        "pass_len=%d pass_last=%s sender_len=%d to_count=%d",
        host, port, len(user), _suffix(user),
        len(password), _suffix(password),
        len(sender), len(recipients),
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(digest_md)
    msg.add_alternative(_render_html(digest_md), subtype="html")

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        if user:
            s.login(user, password)
        s.send_message(msg)
    log.info("emailed digest to %s", recipients)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily news digest.")
    parser.add_argument("--output-dir", default=".",
                        help="Directory for the digest .md file (default: cwd).")
    parser.add_argument("--email", action="store_true",
                        help="Also send via SMTP (reads SMTP_* env vars).")
    parser.add_argument("--html-preview", action="store_true",
                        help="Also write a styled HTML version next to the .md, "
                             "to preview how the email body will render.")
    parser.add_argument("--quiet", action="store_true", help="Suppress info logs.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    now = datetime.now(timezone.utc)
    log.info("fetching %d feeds...", sum(len(v) for v in FEEDS.values()))
    items = fetch_all(FEEDS)
    log.info("fetched %d items total", len(items))
    items = dedupe(filter_recent(items, WINDOW_HOURS))
    grouped = group_and_rank(items, ITEMS_PER_CATEGORY)

    md = render_markdown(now, grouped)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"digest-{now:%Y-%m-%d}.md"
    out_path.write_text(md, encoding="utf-8")
    log.info("wrote %s", out_path)

    if args.html_preview:
        html_path = out_dir / f"digest-{now:%Y-%m-%d}.html"
        html_path.write_text(_render_html(md), encoding="utf-8")
        log.info("wrote %s", html_path)

    print(md)

    if args.email:
        send_email(md, subject=f"News Digest — {now:%Y-%m-%d}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
