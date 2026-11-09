"""Instagram public-embed profile cache (follower counts + avatars)."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

TTL = 7 * 24 * 3600
UA = "Mozilla/5.0"
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache"
CACHE_PATH = CACHE_DIR / "profiles.json"

_fetch_lock = threading.Lock()
_io_lock = threading.Lock()


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_cache() -> dict:
    ensure_cache_dir()
    if not CACHE_PATH.exists():
        return {}
    try:
        with _io_lock:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(data: dict) -> None:
    ensure_cache_dir()
    raw = json.dumps(data, ensure_ascii=False, indent=2)
    with _io_lock:
        CACHE_PATH.write_text(raw, encoding="utf-8")


def clean_url(raw: str) -> str:
    s = raw.replace("\\u0026", "&").replace("&amp;", "&")
    s = s.replace("\\/", "/")
    s = s.replace("\\\\", "\\")
    while "\\/" in s:
        s = s.replace("\\/", "/")
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    return s


def parse_embed(html: str) -> dict:
    out: dict = {"followers": None, "following": None, "avatar": None, "private": None}
    m = re.search(r'\\"edge_followed_by\\":\{\\"count\\":(\d+)\}', html)
    if not m:
        m = re.search(r'"edge_followed_by":\{"count":(\d+)\}', html)
    if m:
        out["followers"] = int(m.group(1))
    m = re.search(r'\\"edge_follow\\":\{\\"count\\":(\d+)\}', html)
    if not m:
        m = re.search(r'"edge_follow":\{"count":(\d+)\}', html)
    if m:
        out["following"] = int(m.group(1))
    m = re.search(r'\\"is_private\\":(true|false)', html)
    if not m:
        m = re.search(r'"is_private":(true|false)', html)
    if m:
        out["private"] = m.group(1) == "true"
    m = re.search(r'\\"profile_pic_url_hd\\":\\"([^"]+)\\"', html)
    if not m:
        m = re.search(r'\\"profile_pic_url\\":\\"([^"]+)\\"', html)
    if not m:
        m = re.search(r'"profile_pic_url(?:_hd)?":"([^"]+)"', html)
    if m:
        out["avatar"] = clean_url(m.group(1))
    return out


def fetch_embed(username: str) -> dict:
    url = f"https://www.instagram.com/{username}/embed/"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", "replace")
    parsed = parse_embed(html)
    parsed.update({"username": username, "ts": int(time.time())})
    return parsed


def get_profile(username: str) -> tuple[dict, int]:
    """Return (payload, http_status). Serializes Instagram fetches; does not sleep."""
    if not USERNAME_RE.fullmatch(username):
        return {"error": "bad username"}, 400

    cache = load_cache()
    key = username.lower()
    existing = cache.get(key)
    now = time.time()
    if (
        existing
        and now - existing.get("ts", 0) < TTL
        and (existing.get("followers") is not None or existing.get("avatar"))
    ):
        return existing, 200

    with _fetch_lock:
        # Re-check after waiting for the lock
        cache = load_cache()
        existing = cache.get(key)
        now = time.time()
        if (
            existing
            and now - existing.get("ts", 0) < TTL
            and (existing.get("followers") is not None or existing.get("avatar"))
        ):
            return existing, 200
        try:
            data = fetch_embed(username)
        except urllib.error.HTTPError as e:
            return {"error": f"http {e.code}"}, 502
        except Exception as e:
            return {"error": str(e)}, 502
        cache[key] = data
        save_cache(cache)
        return data, 200
