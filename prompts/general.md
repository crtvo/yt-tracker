You are summarizing a YouTube video so it can be logged in a searchable research report.

Video title: {title}
Channel: {channel}
Published: {published}

Watch the whole video and return JSON that matches the schema. Rules:

1. **summary**: 3–5 plain-English sentences. What the video is about and the main takeaway.
2. **key_points**: 3–8 short bullets, most important first. Include concrete facts, numbers, names, recommendations.
3. **category**: pick the best fit from the schema enum.
4. **stock_moves**: only fill this if the creator talks about specific stocks or investments they own, bought or sold. Otherwise return an empty list. Never invent.
5. **portfolio_snapshot**: empty list unless holdings are shown.
6. **market_view**: empty string unless the video is about markets or the economy.
7. **sentiment**: overall tone of the video.
8. **topics**: 2–6 short topic tags.
