#!/usr/bin/env python3
"""Weekly AI news digest — fetches from RSS feeds and sends via Outlook."""

import os
import smtplib
import feedparser
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

OUTLOOK_USER = os.environ["OUTLOOK_USER"]
OUTLOOK_PASS = os.environ["OUTLOOK_PASS"]
RECIPIENT    = os.environ.get("RECIPIENT", OUTLOOK_USER)

RSS_FEEDS = [
    ("VentureBeat AI",       "https://venturebeat.com/category/ai/feed/"),
    ("TechCrunch AI",        "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("MIT Technology Review","https://www.technologyreview.com/feed/"),
    ("The Verge AI",         "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Ars Technica AI",      "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("Google DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
]

MAX_ITEMS_PER_FEED = 5
LOOKBACK_DAYS      = 7


def fetch_articles() -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    articles = []

    for source, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                # Parse publish date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                if published and published < cutoff:
                    continue

                summary = getattr(entry, "summary", "")
                # Strip basic HTML tags from summary
                import re
                summary = re.sub(r"<[^>]+>", "", summary).strip()
                if len(summary) > 300:
                    summary = summary[:297] + "..."

                articles.append({
                    "source":    source,
                    "title":     entry.get("title", "Без заглавие"),
                    "link":      entry.get("link", "#"),
                    "summary":   summary,
                    "published": published,
                })
        except Exception as e:
            print(f"[WARN] {source}: {e}")

    # Sort newest first
    articles.sort(key=lambda a: a["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return articles


def build_html(articles: list[dict]) -> str:
    today = datetime.now().strftime("%d %B %Y")
    rows = ""
    current_source = None

    for art in articles:
        if art["source"] != current_source:
            current_source = art["source"]
            rows += f"""
            <tr>
              <td colspan="1" style="padding:16px 0 4px 0;font-size:13px;
                  color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;
                  border-bottom:1px solid #e5e7eb;">
                {current_source}
              </td>
            </tr>"""

        pub = art["published"].strftime("%d %b") if art["published"] else ""
        rows += f"""
            <tr>
              <td style="padding:12px 0;border-bottom:1px solid #f3f4f6;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                  <a href="{art['link']}"
                     style="font-size:16px;font-weight:600;color:#1d4ed8;text-decoration:none;
                            line-height:1.4;">
                    {art['title']}
                  </a>
                  <span style="font-size:12px;color:#9ca3af;white-space:nowrap;margin-left:12px;">
                    {pub}
                  </span>
                </div>
                {f'<p style="margin:6px 0 0 0;font-size:14px;color:#4b5563;line-height:1.5;">{art["summary"]}</p>' if art["summary"] else ""}
              </td>
            </tr>"""

    if not rows:
        rows = """<tr><td style="padding:24px 0;color:#6b7280;text-align:center;">
                    Няма нови статии тази седмица.
                  </td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="bg">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;">
    <tr><td align="center" style="padding:32px 16px;">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;
                    box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);
                     padding:32px 40px;text-align:center;">
            <h1 style="margin:0;color:#ffffff;font-size:26px;font-weight:700;
                        letter-spacing:-0.5px;">🤖 AI Новини</h1>
            <p style="margin:8px 0 0 0;color:#bfdbfe;font-size:14px;">{today}</p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px 40px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {rows}
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 40px;background:#f8fafc;
                     border-top:1px solid #e5e7eb;text-align:center;">
            <p style="margin:0;font-size:12px;color:#9ca3af;">
              Автоматичен дайджест · източници: VentureBeat, TechCrunch, MIT Tech Review, The Verge, Ars Technica, DeepMind
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_email(html: str, article_count: int) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🤖 AI Новини — {datetime.now().strftime('%d %b %Y')} ({article_count} статии)"
    msg["From"]    = OUTLOOK_USER
    msg["To"]      = RECIPIENT

    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp-mail.outlook.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(OUTLOOK_USER, OUTLOOK_PASS)
        smtp.sendmail(OUTLOOK_USER, RECIPIENT, msg.as_string())
        print(f"[OK] Изпратен имейл до {RECIPIENT} ({article_count} статии)")


def main() -> None:
    print("[*] Зареждане на новини...")
    articles = fetch_articles()
    print(f"[*] Намерени {len(articles)} статии")

    html = build_html(articles)
    send_email(html, len(articles))


if __name__ == "__main__":
    main()
