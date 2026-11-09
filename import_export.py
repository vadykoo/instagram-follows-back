"""Parse Instagram Followers and following export (ZIP / JSON / HTML)."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

USER_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
SKIP = {
    "accounts",
    "about",
    "legal",
    "explore",
    "reels",
    "direct",
    "p",
    "reel",
    "stories",
    "tv",
    "_u",
}
URL_RE = re.compile(
    r"instagram\.com/(?:_u/)?([A-Za-z0-9._]{1,30})",
    re.IGNORECASE,
)
HREF_RE = re.compile(
    r'href=["\']https?://(?:www\.)?instagram\.com/(?:_u/)?([A-Za-z0-9._]{1,30})/?["\']',
    re.IGNORECASE,
)
FOLLOWING_H2_RE = re.compile(
    r"<h2[^>]*>\s*([A-Za-z0-9._]{1,30})\s*</h2>[\s\S]{0,400}?instagram\.com/(?:_u/)?([A-Za-z0-9._]{1,30})",
    re.IGNORECASE,
)


def is_valid_user(u: str | None) -> bool:
    if not u or not USER_RE.fullmatch(u):
        return False
    low = u.lower()
    if low in SKIP or low.startswith("__deleted__"):
        return False
    return True


def from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = URL_RE.search(url)
    if not m:
        return None
    u = m.group(1)
    return u if is_valid_user(u) else None


def from_entry(entry: dict[str, Any]) -> tuple[str | None, int | None]:
    user = None
    ts = None
    sld = entry.get("string_list_data")
    if isinstance(sld, list) and sld:
        first = sld[0] if isinstance(sld[0], dict) else {}
        value = first.get("value")
        if isinstance(value, str) and USER_RE.fullmatch(value) and is_valid_user(value):
            user = value
        if not user:
            user = from_url(first.get("href"))
        if isinstance(first.get("timestamp"), int):
            ts = first["timestamp"]
    title = entry.get("title")
    if not user and isinstance(title, str) and USER_RE.fullmatch(title) and is_valid_user(title):
        user = title
    if ts is None and isinstance(entry.get("timestamp"), int):
        ts = entry["timestamp"]
    return user, ts


def add_user(bucket: dict[str, dict], user: str | None, ts: int | None) -> None:
    if not user or not is_valid_user(user):
        return
    key = user.lower()
    prev = bucket.get(key)
    if not prev:
        bucket[key] = {"user": user, "ts": ts}
        return
    if ts is not None and (prev.get("ts") is None or ts < prev["ts"]):
        prev["ts"] = ts


def parse_json_list(text: str, following: bool) -> tuple[dict[str, dict], list[int]]:
    data = json.loads(text)
    if isinstance(data, list):
        arr = data
    elif following:
        arr = data.get("relationships_following") or data.get("following") or []
    else:
        arr = data.get("relationships_followers") or data.get("followers") or []
    bucket: dict[str, dict] = {}
    timestamps: list[int] = []
    for entry in arr or []:
        if not isinstance(entry, dict):
            continue
        user, ts = from_entry(entry)
        add_user(bucket, user, ts)
        if ts is not None:
            timestamps.append(ts)
    return bucket, timestamps


def parse_html_followers(html: str) -> dict[str, dict]:
    bucket: dict[str, dict] = {}
    for m in HREF_RE.finditer(html):
        add_user(bucket, m.group(1), None)
    return bucket


def parse_html_following(html: str) -> dict[str, dict]:
    bucket: dict[str, dict] = {}
    seen: set[str] = set()
    for m in FOLLOWING_H2_RE.finditer(html):
        from_h2, from_url_u = m.group(1), m.group(2)
        u = from_h2 if is_valid_user(from_h2) else (from_url_u if is_valid_user(from_url_u) else None)
        if u:
            add_user(bucket, u, None)
            seen.add(u.lower())
    for m in HREF_RE.finditer(html):
        u = m.group(1)
        if is_valid_user(u) and u.lower() not in seen:
            add_user(bucket, u, None)
    return bucket


def build_sets(
    followers: dict[str, dict], following: dict[str, dict]
) -> dict[str, Any]:
    notback: list[str] = []
    fans: list[str] = []
    mutuals: list[str] = []
    order: dict[str, int] = {}
    i = 0
    for key, meta in following.items():
        order[key] = i
        i += 1
        if key in followers:
            mutuals.append(meta["user"])
        else:
            notback.append(meta["user"])
    for key, meta in followers.items():
        if key not in order:
            order[key] = i
            i += 1
        if key not in following:
            fans.append(meta["user"])
    return {
        "notback": notback,
        "fans": fans,
        "mutuals": mutuals,
        "followers": len(followers),
        "following": len(following),
        "order": order,
    }


def incomplete_warning(
    follower_ts: list[int],
    following_ts: list[int],
    follower_count: int,
    following_count: int,
) -> str | None:
    if follower_ts and following_ts:
        if min(follower_ts) - min(following_ts) > 180 * 24 * 3600:
            return (
                "This export looks incomplete: follower timestamps start much later than following. "
                "Re-request Followers and following with date range All time."
            )
    if following_count > 50 and follower_count > 0 and follower_count < following_count * 0.35:
        return (
            "Follower count looks small vs following. Prefer an All time JSON export — "
            "a 1-year range omits older followers."
        )
    return None


def _prefer_connections(paths: list[str]) -> list[str]:
    preferred = [p for p in paths if "followers_and_following" in p.replace("\\", "/").lower()]
    return preferred or paths


def parse_zip(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        follower_json = _prefer_connections(
            [n for n in names if re.search(r"(^|/)followers_\d+\.json$", n, re.I)]
        )
        following_json = _prefer_connections(
            [n for n in names if re.search(r"(^|/)following\.json$", n, re.I)]
        )
        follower_html = _prefer_connections(
            [n for n in names if re.search(r"(^|/)followers_\d+\.html$", n, re.I)]
        )
        following_html = _prefer_connections(
            [n for n in names if re.search(r"(^|/)following\.html$", n, re.I)]
        )

        followers: dict[str, dict] = {}
        following: dict[str, dict] = {}
        follower_ts: list[int] = []
        following_ts: list[int] = []
        used = None

        if follower_json and following_json:
            used = "json"
            for name in follower_json:
                text = zf.read(name).decode("utf-8", "replace")
                bucket, ts = parse_json_list(text, following=False)
                for k, v in bucket.items():
                    add_user(followers, v["user"], v.get("ts"))
                follower_ts.extend(ts)
            text = zf.read(following_json[0]).decode("utf-8", "replace")
            bucket, ts = parse_json_list(text, following=True)
            for k, v in bucket.items():
                add_user(following, v["user"], v.get("ts"))
            following_ts.extend(ts)
        elif follower_html and following_html:
            used = "html"
            for name in follower_html:
                html = zf.read(name).decode("utf-8", "replace")
                for k, v in parse_html_followers(html).items():
                    add_user(followers, v["user"], None)
            html = zf.read(following_html[0]).decode("utf-8", "replace")
            for k, v in parse_html_following(html).items():
                add_user(following, v["user"], None)
        else:
            raise ValueError(
                "No follower/following files found.\n"
                "Expected JSON: connections/followers_and_following/followers_1.json + following.json\n"
                "Or HTML: followers_1.html + following.html\n"
                "Make sure you selected Followers and following in Accounts Center."
            )

    if not followers and not following:
        raise ValueError("Files were found but no usernames could be parsed. Try the JSON export format.")

    built = build_sets(followers, following)
    warn = incomplete_warning(follower_ts, following_ts, built["followers"], built["following"])
    return {"built": built, "warn": warn, "used": used}
