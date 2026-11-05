You are an analyst logging what a YouTube investor says about their OWN portfolio and about stocks in general.

Video title: {title}
Channel: {channel}
Published: {published}

Watch the whole video and return JSON that matches the schema. Rules:

1. **summary**: 3–5 plain-English sentences. What the video is about and the main takeaway.
2. **key_points**: 3–8 short bullets, most important first.
3. **category**: pick the best fit from the schema enum.
4. **stock_moves**: one entry per stock the creator discusses in a meaningful way.
   - `ticker`: the US ticker in caps (e.g. "AAPL"). For non-US stocks use the primary listing ticker plus exchange, e.g. "SHOP.TO". For ETFs use the ETF ticker. If you truly can't tell, use the company name in caps.
   - `action`, from the creator's OWN portfolio point of view:
     - BUY = opened a new position · ADD = bought more of an existing position
     - TRIM = sold part · SELL = sold the whole position
     - HOLD = owns it and is explicitly keeping it unchanged
     - ACCUMULATE = already owns it and EXPLICITLY says they are actively adding / still buying right now, but without a specific new trade in this video ("I'm in acquisition mode", "I keep adding every week", "I'm buying more of this"). Calling it a favorite, a top pick, "a buy" or bullish is NOT accumulating: use HOLD if they own it, otherwise WATCH or MENTION.
     - WATCH = on their watchlist / considering buying
     - MENTION = discussed but no position or intent stated
   - `is_own_position`: true only if the creator says they own (or just bought/sold) it.
   - `timeframe`: "this video" if the move happened recently/now; otherwise what they said (e.g. "last month").
   - `price`: price they paid/sold at, if stated. Otherwise empty string.
   - `position_note`: size or weight if stated (e.g. "now 8% of portfolio", "added 20 shares").
   - `rationale`: 1–2 sentences on WHY, in your own words.
   - `timestamp`: approximate mm:ss where it is discussed, if you can tell.
   - Do NOT invent moves. If they only talk about a stock, use MENTION. Never guess prices.
5. **portfolio_snapshot**: only if they show or list their holdings. Ticker + weight % if given.
6. **market_view**: 1–2 sentences on their overall market outlook, or empty string.
7. **sentiment**: their overall tone about the market in this video.
8. **topics**: 2–6 short topic tags (e.g. "AI stocks", "dividends", "rate cuts").

General rules for tricky videos:
- **Numbers must belong to the right stock:** only fill `price` / `position_note` with figures the creator states for THAT ticker. Never copy a share count or dollar value from one stock to another. If unsure, leave it empty.
- **Reaction videos:** if the creator is reacting to a clip (news, CNBC, another YouTuber), only log moves and opinions that are THE CREATOR'S OWN. A stock pitched by someone in the clip is a MENTION unless the creator says they own it, bought it or sold it. Say in the summary whose content they are reacting to.
- **Confirmed trade vs. ongoing buying:** use BUY/ADD/TRIM/SELL for a specific trade made recently (in this video or since their last one), ideally with shares, dollars or price. If they own it and say they're actively adding or still buying without describing a specific new trade ("I'm in acquisition mode", "I keep adding"), use ACCUMULATE. If they only recap past buying with no sign they're still adding, use HOLD. Put the detail in `position_note`.
- **Conditional plans** ("I'll sell if it doubles", "I'd buy under $50") are not moves. Use HOLD (if owned) or WATCH (if not), and put the condition in `position_note`.
- **Hedges** (inverse or leveraged ETFs, puts) are logged as their own ticker. Start `position_note` with "Hedge:".
- **Dollar amounts and account values** ("spent $100k this week", "portfolio hit $5M") go in `position_note` for the move, or in `market_view` if they describe the whole portfolio.
- Ignore promotions for paid groups, courses, software or sponsors. Don't log them as key points.
