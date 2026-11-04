"""Builds demo/index.html from made-up data so you can see the dashboard before the first real run.

    python scripts/make_demo.py
"""

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tracker import TEMPLATES_DIR  # noqa: E402
from tracker.report import build_payload  # noqa: E402

random.seed(7)
NOW = datetime.now(timezone.utc)

CHANNELS = [
    {"id": "UCdemoA", "title": "Northside Growth Investing (demo)", "handle": "@northsidegrowth", "profile": "stocks", "subscribers": 184000},
    {"id": "UCdemoB", "title": "Dividend Porch (demo)", "handle": "@dividendporch", "profile": "stocks", "subscribers": 62000},
]

# (days_ago, channel, title, category, sentiment, moves[(ticker, company, action, own, note, price, why)])
SCRIPT = [
    (2, "UCdemoA", "I SOLD Tesla and Bought This Instead | November Portfolio Update", "Portfolio Update", "bullish", [
        ("TSLA", "Tesla", "SELL", True, "Closed full position", "$248", "Thinks the robotaxi timeline is priced in and wants less single-name volatility."),
        ("NVDA", "NVIDIA", "ADD", True, "Now ~14% of portfolio", "", "Data-center demand still outrunning supply after the latest earnings."),
        ("CRWD", "CrowdStrike", "BUY", True, "Starter position, 2%", "$312", "Sees cybersecurity spending as recession-resistant; plans to build over 3 months."),
    ]),
    (4, "UCdemoB", "3 Dividend Stocks I'm Buying in November", "Buy/Sell Decision", "neutral", [
        ("O", "Realty Income", "ADD", True, "Reinvesting dividends + 15 shares", "", "Yield above 5.5% looks attractive if rates keep easing."),
        ("JNJ", "Johnson & Johnson", "BUY", True, "New position", "$151", "Litigation overhang reduced; wants healthcare exposure."),
        ("KO", "Coca-Cola", "HOLD", True, "", "", "No change; fairly valued at current levels."),
    ]),
    (9, "UCdemoA", "Is the AI Trade Over? My Honest Take", "Market Commentary", "mixed", [
        ("NVDA", "NVIDIA", "HOLD", True, "", "", "Keeps core position despite valuation concerns."),
        ("PLTR", "Palantir", "WATCH", False, "", "", "Likes commercial growth but won't buy at current multiple."),
        ("MSFT", "Microsoft", "MENTION", False, "", "", "Used as an example of AI monetization through cloud."),
    ]),
    (16, "UCdemoA", "Trimming My Biggest Winner (Here's Why)", "Buy/Sell Decision", "neutral", [
        ("META", "Meta Platforms", "TRIM", True, "Sold 1/3, now 7% of portfolio", "$585", "Position grew too large; taking profits to rebalance."),
        ("AMZN", "Amazon", "ADD", True, "Added 10 shares", "", "AWS reacceleration and retail margin improvement."),
    ]),
    (21, "UCdemoB", "October Dividend Income Report — New Record!", "Portfolio Update", "bullish", [
        ("O", "Realty Income", "HOLD", True, "Largest holding", "", "Monthly dividend payer anchoring income."),
        ("VZ", "Verizon", "SELL", True, "Exited position", "", "Dividend growth too slow; reallocating to healthcare."),
        ("SCHD", "Schwab US Dividend Equity ETF", "ADD", True, "Automatic biweekly buys", "", "Core holding for diversified dividend growth."),
    ]),
    (30, "UCdemoA", "Why I Bought Tesla Again", "Buy/Sell Decision", "bullish", [
        ("TSLA", "Tesla", "BUY", True, "4% position", "$221", "Energy storage business underappreciated."),
        ("CRWD", "CrowdStrike", "WATCH", False, "", "", "Waiting for a pullback before starting a position."),
    ]),
    (44, "UCdemoA", "My Full Portfolio Revealed (Every Stock)", "Portfolio Update", "bullish", [
        ("NVDA", "NVIDIA", "HOLD", True, "12% of portfolio", "", "Largest position, long-term AI thesis."),
        ("META", "Meta Platforms", "HOLD", True, "10% of portfolio", "", "Ad business strength."),
        ("AMZN", "Amazon", "BUY", True, "New 5% position", "$178", "Cloud plus advertising flywheel."),
    ]),
    (60, "UCdemoB", "Stocks I'll Never Sell", "Education", "neutral", [
        ("KO", "Coca-Cola", "HOLD", True, "", "", "60+ years of dividend increases."),
        ("VZ", "Verizon", "HOLD", True, "", "", "High yield, but watching debt levels."),
    ]),
]


def main():
    videos = {}
    for i, (d, cid, title, cat, sent, moves) in enumerate(SCRIPT):
        ch = next(c for c in CHANNELS if c["id"] == cid)
        vid = f"demo{i:04d}"
        videos[vid] = {
            "id": vid, "channel_id": cid, "channel_title": ch["title"], "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "published_at": (NOW - timedelta(days=d)).strftime("%Y-%m-%dT15:00:00Z"),
            "duration_sec": random.randint(9, 28) * 60, "thumbnail": "", "status": "ok", "method": "video",
            "analysis": {
                "summary": f"Demo summary for “{title}”. The creator walks through recent portfolio decisions, the reasoning behind each, "
                           f"and how they're thinking about the market over the next few months.",
                "key_points": [f"{m[2].title()} {m[0]}: {m[6]}" for m in moves] + ["Keeps roughly 5% in cash for opportunities."],
                "category": cat, "sentiment": sent,
                "topics": random.sample(["AI stocks", "dividends", "rebalancing", "rate cuts", "earnings", "valuation", "cash position"], 3),
                "market_view": "Cautiously optimistic; expects volatility around rate decisions.",
                "stock_moves": [
                    {"ticker": t, "company": c, "action": a, "is_own_position": own, "timeframe": "this video",
                     "price": p, "position_note": n, "rationale": w, "timestamp": f"{random.randint(1, 18)}:{random.randint(0, 59):02d}"}
                    for (t, c, a, own, n, p, w) in moves
                ],
                "portfolio_snapshot": [],
            },
        }
    # one queued and one failed video to show those states
    videos["demoQ"] = {"id": "demoQ", "channel_id": "UCdemoB", "channel_title": CHANNELS[1]["title"], "title": "Live Q&A: Your Dividend Questions",
                       "url": "https://www.youtube.com/watch?v=demoQ", "published_at": (NOW - timedelta(hours=5)).strftime("%Y-%m-%dT%H:00:00Z"),
                       "duration_sec": 5400, "thumbnail": "", "status": "pending"}

    class FakeStore:
        pass

    st = FakeStore()
    st.videos, st.channels = videos, {c["id"]: c for c in CHANNELS}
    payload = build_payload(st, "YouTube Channel Intelligence")
    payload["demo"] = True

    out = ROOT / "demo"
    out.mkdir(exist_ok=True)
    html = (TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(payload).replace("</", "<\\/")).replace("__TITLE__", payload["title"])
    (out / "index.html").write_text(html, encoding="utf-8")
    from tracker.digest import build_digest
    subject, body, _ = build_digest(st, days=14, title=payload["title"])
    (out / "digest.html").write_text(body, encoding="utf-8")
    print("Digest subject:", subject)
    print(f"Wrote {out / 'index.html'}: {len(payload['moves'])} moves, {len(payload['tickers'])} tickers")


if __name__ == "__main__":
    main()
