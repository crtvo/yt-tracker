"""Weekly email digest: new buys/sells first, then every new video summary.

Env vars (GitHub secrets):
  SMTP_USER       e.g. you@gmail.com
  SMTP_PASSWORD   a Gmail *App Password* (not your normal password)
  DIGEST_TO       where to send (comma-separated OK)
  SMTP_HOST       optional, default smtp.gmail.com
  SMTP_PORT       optional, default 465
  DASHBOARD_URL   optional, adds a link to the live dashboard
"""

from __future__ import annotations

import html
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import DATA_DIR
from .positions import flatten_moves, local_date

ACTION_COLORS = {
    "BUY": "#0a7d3b", "ADD": "#2e9e5b", "TRIM": "#b86e00", "SELL": "#b42318",
    "HOLD": "#475467", "WATCH": "#3758c4", "MENTION": "#98a2b3",
}
ORDER = ["BUY", "ADD", "SELL", "TRIM", "HOLD", "WATCH", "MENTION"]


def _e(s) -> str:
    return html.escape(str(s or ""))


def build_digest(store, days: int = 7, title: str = "YouTube Channel Intelligence", tz: str | None = None) -> tuple[str, str, int]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    vids = [v for v in store.videos.values() if v.get("status") == "ok" and v["published_at"] >= since[:19]]
    vids.sort(key=lambda v: v["published_at"], reverse=True)
    moves = flatten_moves({v["id"]: v for v in vids}, tz=tz)
    key_moves = [m for m in moves if m["action"] in ("BUY", "ADD", "SELL", "TRIM")]
    key_moves.sort(key=lambda m: (ORDER.index(m["action"]), m["published_at"]))

    dash = os.environ.get("DASHBOARD_URL", "")
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%b %d")
    end = datetime.now(timezone.utc).strftime("%b %d, %Y")
    subject = f"{title}: {len(vids)} new video{'s' if len(vids) != 1 else ''}, {len(key_moves)} portfolio move{'s' if len(key_moves) != 1 else ''} ({start}–{end})"

    def pill(a):
        return (f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;'
                f'font-weight:600;color:#fff;background:{ACTION_COLORS.get(a, "#667085")}">{a}</span>')

    rows = "".join(
        f'<tr><td style="padding:8px 6px;border-bottom:1px solid #eaecf0;white-space:nowrap">{pill(m["action"])}</td>'
        f'<td style="padding:8px 6px;border-bottom:1px solid #eaecf0"><b>{_e(m["ticker"])}</b>'
        f'<div style="color:#667085;font-size:12px">{_e(m["company"])}</div></td>'
        f'<td style="padding:8px 6px;border-bottom:1px solid #eaecf0;font-size:13px">{_e(m["rationale"])}'
        f'{(" <span style=color:#667085>· " + _e(m["position_note"]) + "</span>") if m.get("position_note") else ""}'
        f'<div style="color:#667085;font-size:12px;margin-top:2px">{_e(m["channel_title"])} · {m["date"]} · '
        f'<a href="{_e(m["video_url"])}" style="color:#3758c4">video</a></div></td></tr>'
        for m in key_moves
    ) or '<tr><td style="padding:8px;color:#667085">No buys or sells announced this week.</td></tr>'

    cards = ""
    for v in vids:
        a = v["analysis"]
        pts = "".join(f"<li>{_e(p)}</li>" for p in a.get("key_points", [])[:5])
        tick = ", ".join(sorted({m["ticker"] for m in a.get("stock_moves", [])}))
        cards += (
            f'<div style="border:1px solid #eaecf0;border-radius:10px;padding:14px 16px;margin:0 0 12px">'
            f'<div style="font-size:12px;color:#667085">{_e(v["channel_title"])} · {local_date(v["published_at"], tz)} · {_e(a.get("category"))}</div>'
            f'<a href="{_e(v["url"])}" style="font-size:16px;font-weight:600;color:#101828;text-decoration:none">{_e(v["title"])}</a>'
            f'<p style="margin:8px 0;font-size:14px;line-height:1.5;color:#344054">{_e(a.get("summary"))}</p>'
            f'<ul style="margin:0 0 6px;padding-left:18px;font-size:13px;color:#344054;line-height:1.5">{pts}</ul>'
            + (f'<div style="font-size:12px;color:#667085">Tickers: {_e(tick)}</div>' if tick else "")
            + "</div>"
        )
    if not cards:
        cards = '<p style="color:#667085">No new videos this week.</p>'

    body = f"""<!doctype html><html><body style="margin:0;background:#f9fafb;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<div style="max-width:680px;margin:0 auto;padding:24px 16px">
 <h1 style="font-size:20px;margin:0 0 4px;color:#101828">{_e(title)} — weekly digest</h1>
 <div style="color:#667085;font-size:13px;margin-bottom:20px">{start} – {end}{f' · <a href="{_e(dash)}" style="color:#3758c4">Open dashboard</a>' if dash else ''}</div>
 <h2 style="font-size:15px;color:#101828;margin:0 0 8px">Portfolio moves</h2>
 <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #eaecf0;border-radius:10px;margin-bottom:24px">{rows}</table>
 <h2 style="font-size:15px;color:#101828;margin:0 0 8px">New videos</h2>
 {cards}
</div></body></html>"""
    return subject, body, len(vids)


def send_digest(store, days: int = 7, title: str = "YouTube Channel Intelligence", dry_run: bool = False,
                skip_if_empty: bool = True, tz: str | None = None) -> str:
    subject, body, n = build_digest(store, days, title, tz)
    (DATA_DIR / "last_digest.html").write_text(body, encoding="utf-8")
    if dry_run:
        return f"[dry run] {subject} → data/last_digest.html"
    if n == 0 and skip_if_empty:
        return "No new videos this week — digest not sent."

    user, pw, to = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD"), os.environ.get("DIGEST_TO")
    if not (user and pw and to):
        raise RuntimeError("SMTP_USER, SMTP_PASSWORD and DIGEST_TO must be set to send email")
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(body, "html", "utf-8"))
    host, port = os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=60) as s:
        s.login(user, pw)
        s.sendmail(user, [t.strip() for t in to.split(",")], msg.as_string())
    return f"Sent: {subject}"
