# instagram-follows-back

Local Instagram follow-back checker from an official data export. No login.

Drop Meta’s **Followers and following** ZIP into a page on your machine. The app builds **Not following back**, **Fans**, and **Mutuals** entirely locally — no Instagram password, no third-party upload.

## Requirements

- Python 3.10+
- A browser
- An Instagram data download (Followers and following)

## Run

```bash
python3 app.py
```

Open the printed URL (e.g. `http://127.0.0.1:8765/`). Data stays on this computer. Ctrl+C stops the server. Do not tunnel or expose this port.

## Get the export

1. [Accounts Center → Download your information](https://accountscenter.instagram.com/info_and_permissions/dyi/)
2. Select **Followers and following** only
3. Format **JSON** (HTML also works)
4. Date range **All time** (a 1-year range omits older followers and false-flags mutuals)
5. Download the ZIP and drop it on the page

## Tabs

| Tab | Meaning |
|---|---|
| Not following back | You follow them; they do not follow you |
| Fans | They follow you; you do not follow them |
| Mutuals | Both sides follow |

Search filters the active tab. Sort by **Most / Fewest followers** or **Original** order only when you click those buttons (sorting never runs automatically on cache writes).

## Hover preview & slow fill

Hover a row to load Instagram’s **public embed** iframe and optionally cache follower count / avatar via the local helper (`/profile/…`). Private accounts and profiles with embedding disabled stay blank — use **Open Instagram**.

**Fill cache slowly** walks public embeds with 15–25s gaps. It does **not** log in. Pause or stop if errors appear. Hover in the browser may use your Instagram session; slow fill does not — avoid running Fill in many tabs at once.

## Privacy

The ZIP is parsed in your browser. Profile cache lives under `.cache/` on your machine (gitignored). This project does not receive your export or lists.

## Limits

See the in-app **Limits** footnote for the short version. In short:

- **Not a login unfollower app.** No password, no OAuth, no “connect your account”.
- **Export quality matters.** Garbage in, garbage out — prefer JSON + All time over HTML or a 1-year window.
- **Embeds can fail.** Official `/embed/` URLs; Instagram may blank them.
- **Slow fill is paced on purpose** (15–25s). Stop on repeated errors. Not a guarantee against rate limits or blocks.
- **ToS.** Fetching public embed pages may still conflict with Instagram’s terms. You run it at your own risk. Personal local tool only.
- **Counts are scraped from embed HTML**, not a supported API. They can be missing, stale, or wrong.
- **Localhost only.** Never expose the helper to the internet.
- **Not affiliated with Meta / Instagram.**

## License

MIT — see `LICENSE`. Provided as-is. Not affiliated with Meta.
