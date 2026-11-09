#!/usr/bin/env python3
"""One-command local server for instagram-follows-back."""
from __future__ import annotations

import json
import re
import socket
import sys
import tempfile
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import cache as profile_cache
import import_export

HOST = "127.0.0.1"
PREFERRED_PORT = 8765
ROOT = Path(__file__).resolve().parent
HTML_NAME = "instagram-followback.html"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        path = getattr(self, "path", "")
        if path.startswith("/profile/") or path.startswith("/import"):
            return
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, payload: dict | list, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self) -> None:
        path = ROOT / HTML_NAME
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html", f"/{HTML_NAME}"):
            self._send_html()
            return

        if path == "/health":
            self._json({"ok": True, "cache": str(profile_cache.CACHE_PATH)})
            return

        if path in ("/cache", "/cache.json"):
            self._json(profile_cache.load_cache())
            return

        m = re.fullmatch(r"/profile/([^/]+)", path)
        if m:
            username = unquote(m.group(1)).strip()
            payload, status = profile_cache.get_profile(username)
            self._json(payload, status)
            return

        super().do_GET()

    def _import_result(self, result: dict) -> None:
        self._json(
            {
                "ok": True,
                "used": result["used"],
                "warn": result["warn"],
                "lists": result["built"],
            }
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/import-path":
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._json({"error": "invalid JSON"}, 400)
                return
            zip_path = _safe_local_zip(str(payload.get("path") or ""))
            if zip_path is None:
                self._json(
                    {
                        "error": "Invalid path. Use an absolute path to a .zip under your home folder."
                    },
                    400,
                )
                return
            try:
                self._import_result(import_export.parse_zip(zip_path))
            except zipfile.BadZipFile:
                self._json({"error": "Not a valid ZIP file."}, 400)
            except ValueError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        if path != "/import":
            self._json({"error": "not found"}, 404)
            return

        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            self._json({"error": "empty body"}, 400)
            return
        if length > MAX_UPLOAD_BYTES:
            self._json({"error": "file too large"}, 413)
            return

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="ig-export-", suffix=".zip", delete=False
            ) as tmp:
                tmp_path = Path(tmp.name)
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    tmp.write(chunk)
                    remaining -= len(chunk)

            self._import_result(import_export.parse_zip(tmp_path))
        except zipfile.BadZipFile:
            self._json({"error": "Not a valid ZIP file."}, 400)
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:
            self._json({"error": str(e)}, 500)
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


def _safe_local_zip(raw: str) -> Path | None:
    """Absolute .zip under the user's home (localhost personal tool)."""
    text = (raw or "").strip().strip('"').strip("'")
    if not text or "\x00" in text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        return None
    try:
        path = path.resolve(strict=True)
    except FileNotFoundError:
        return None
    if path.suffix.lower() != ".zip" or not path.is_file():
        return None
    home = Path.home().resolve()
    if home not in path.parents and path != home:
        return None
    return path


def pick_port(host: str, preferred: int, span: int = 20) -> int:
    for port in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free port in {preferred}–{preferred + span - 1}")


def main() -> None:
    profile_cache.ensure_cache_dir()
    port = pick_port(HOST, PREFERRED_PORT)
    httpd = ThreadingHTTPServer((HOST, port), Handler)
    # Large ZIP imports (full Meta dumps) can take minutes to stream.
    httpd.daemon_threads = True
    url = f"http://{HOST}:{port}/"
    print(f"Open {url}", flush=True)
    print("Data stays on this machine (localhost only). Do not tunnel this port.", flush=True)
    print("Ctrl+C to stop.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        httpd.server_close()


if __name__ == "__main__":
    main()
