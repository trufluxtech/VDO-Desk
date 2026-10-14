#!/usr/bin/env python3
"""VDODesk local editor server. Python stdlib + FFmpeg; OpenCV is optional."""
from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import json
import mimetypes
import re
import shutil
import threading
import uuid
import webbrowser

from media_services import (
    analyze_subject, audio_waveform, create_proxy, encoder_capabilities,
    extract_freeze, ffmpeg_available, filter_capabilities, probe_media,
)
from render_engine import number, render_project, safe_name


VERSION = "1.3.0-beta.1"
ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"
MEDIA = PROJECTS / "media"
OUTPUT = PROJECTS / "exports"
PROXIES = PROJECTS / "proxies"
ANALYSIS = PROJECTS / "analysis"
RECENT_PATH = PROJECTS / "recent-files.json"
for folder in (MEDIA, OUTPUT, PROXIES, ANALYSIS):
    folder.mkdir(parents=True, exist_ok=True)

STATUS = {}
LOCK = threading.Lock()
RECENT_LOCK = threading.Lock()
PROXY_LOCK = threading.Lock()
PROXY_JOBS = set()
MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpg", ".mpeg",
    ".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".opus",
    ".jpg", ".jpeg", ".png", ".webp", ".cube",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".opus"}


def clean_filename(value, fallback="upload.bin"):
    name = Path(str(value or fallback)).name
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:160] or fallback


def media_item(path, display_name=None):
    suffix = path.suffix.lower()
    info = {"duration": 0, "kind": "file", "hasAudio": False, "width": 0, "height": 0,
            "videoCodec": "", "audioCodec": "", "browserPlayable": True}
    if suffix == ".cube":
        info["kind"] = "lut"
    elif suffix in IMAGE_EXTENSIONS:
        info["kind"] = "image"
    else:
        info.update(probe_media(path))
    proxy = PROXIES / f"{path.stem}.proxy.mp4"
    return {
        "file": path.name,
        "name": str(display_name or re.sub(r"^[0-9a-f]{10}-", "", path.name))[:180],
        "url": "/media/" + path.name,
        "duration": info["duration"],
        "kind": info["kind"],
        "hasAudio": info["hasAudio"],
        "width": info["width"],
        "height": info["height"],
        "videoCodec": info["videoCodec"],
        "audioCodec": info["audioCodec"],
        "browserPlayable": info["browserPlayable"],
        "proxy": "/proxies/" + proxy.name if proxy.is_file() else "",
        "proxyPending": path.name in PROXY_JOBS,
        "importedAt": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
    }


def clean_recent_item(item):
    if not isinstance(item, dict):
        return None
    path = MEDIA / safe_name(item.get("file"))
    if not path.is_file():
        return None
    try:
        result = media_item(path, item.get("name"))
        result["importedAt"] = str(item.get("importedAt") or result["importedAt"])
        return result
    except Exception:
        return None


def save_recent(items):
    RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RECENT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(items[:10], indent=2), encoding="utf-8")
    temporary.replace(RECENT_PATH)


def recent_files():
    with RECENT_LOCK:
        items = []
        if RECENT_PATH.is_file():
            try:
                items = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                items = []
        cleaned = [entry for entry in (clean_recent_item(item) for item in items) if entry]
        if not cleaned:
            paths = sorted(
                (path for path in MEDIA.iterdir() if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS),
                key=lambda path: path.stat().st_mtime, reverse=True,
            )[:10]
            for path in paths:
                try:
                    cleaned.append(media_item(path))
                except Exception:
                    pass
        save_recent(cleaned)
        return cleaned[:10]


def all_media_files():
    """Return every usable workspace asset, newest first.

    Project manifests intentionally store stable workspace filenames rather than
    browser-local File objects. Rebuilding this list at startup makes older
    project references visible and relinkable even when they are not in Recent 10.
    """
    items = []
    paths = sorted(
        (path for path in MEDIA.iterdir()
         if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in paths:
        try:
            items.append(media_item(path))
        except Exception:
            # A corrupt or partially copied asset should not prevent the editor
            # from opening and relinking the rest of the project.
            continue
    return items


def remember_file(path, display_name, duration=None):
    entry = media_item(path, display_name)
    if duration is not None:
        entry["duration"] = number(duration, 0, 86400, entry["duration"])
    with RECENT_LOCK:
        items = []
        if RECENT_PATH.is_file():
            try:
                items = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        cleaned = [value for value in (clean_recent_item(item) for item in items) if value and value["file"] != path.name]
        cleaned.insert(0, entry)
        save_recent(cleaned)
    return entry


def preview_proxy_required(item, source):
    return item.get("kind") == "video" and (
        not item.get("browserPlayable", False) or source.stat().st_size > 40_000_000
    )


def build_proxy_background(source, target):
    try:
        try:
            create_proxy(source, target, hardware=True)
        except Exception:
            create_proxy(source, target, hardware=False)
    except Exception as error:
        print(f"Preview proxy failed for {source.name}: {error}", flush=True)
    finally:
        with PROXY_LOCK:
            PROXY_JOBS.discard(source.name)


def start_proxy_background(source):
    target = PROXIES / f"{source.stem}.proxy.mp4"
    if target.is_file():
        return False
    with PROXY_LOCK:
        if source.name in PROXY_JOBS:
            return True
        PROXY_JOBS.add(source.name)
    threading.Thread(target=build_proxy_background, args=(source, target), daemon=True).start()
    return True


def update_status(job, progress, message, **extra):
    with LOCK:
        STATUS[job] = {"state": "done" if progress >= 100 else "working", "progress": progress, "message": message, **extra}


def render_worker(job, spec):
    try:
        output, details = render_project(job, spec, MEDIA, OUTPUT, lambda progress, message: update_status(job, progress, message))
        update_status(job, 100, "Export ready", url="/exports/" + output.name, details=details)
    except Exception as error:
        with LOCK:
            STATUS[job] = {"state": "error", "progress": 0, "message": str(error)}


class Handler(BaseHTTPRequestHandler):
    server_version = "VDODesk/" + VERSION

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.address_string(), format_string % args), flush=True)

    def json_response(self, code, value):
        raw = json.dumps(value).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def read_json(self, maximum=20_000_000):
        length = int(self.headers.get("Content-Length", 0))
        if length > maximum:
            raise ValueError("Request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def serve_file(self, path):
        if not path.is_file():
            return self.json_response(404, {"error": "Missing file"})
        size = path.stat().st_size
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        start, end, code = 0, size - 1, 200
        match = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if match:
            start = int(match.group(1) or 0)
            end = min(size - 1, int(match.group(2) or end))
            code = 206
        if start > end or start >= size:
            return self.json_response(416, {"error": "Invalid range"})
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        if path == "/api/status":
            try:
                capabilities = encoder_capabilities()
                capabilities.update(filter_capabilities())
            except Exception:
                capabilities = {}
            try:
                import cv2
                opencv = cv2.__version__
            except Exception:
                opencv = ""
            return self.json_response(200, {"ok": True, "ffmpeg": ffmpeg_available(), "version": VERSION, "capabilities": capabilities, "opencv": opencv})
        if path == "/api/recent":
            return self.json_response(200, {"items": recent_files()})
        if path == "/api/media":
            return self.json_response(200, {"items": all_media_files()})
        if path.startswith("/api/job/"):
            with LOCK:
                value = STATUS.get(path.rsplit("/", 1)[-1], {"state": "missing"})
            return self.json_response(200, value)
        if path.startswith("/api/waveform/"):
            source = MEDIA / safe_name(path.rsplit("/", 1)[-1])
            if not source.is_file():
                return self.json_response(404, {"error": "Missing media"})
            try:
                return self.json_response(200, {"peaks": audio_waveform(source, int(query.get("points", [240])[0]))})
            except Exception as error:
                return self.json_response(400, {"error": str(error)})
        if path == "/":
            return self.serve_file(ROOT / "assets" / "index.html")
        if path == "/assets/app.js":
            return self.serve_file(ROOT / "assets" / "app.js")
        if path == "/assets/styles.css":
            return self.serve_file(ROOT / "assets" / "styles.css")
        if path == "/assets/vdodesk-logo.png":
            return self.serve_file(ROOT / "assets" / "vdodesk-logo.png")
        roots = (("/media/", MEDIA), ("/proxies/", PROXIES), ("/analysis/", ANALYSIS), ("/exports/", OUTPUT))
        for prefix, root in roots:
            if path.startswith(prefix):
                return self.serve_file(root / safe_name(path[len(prefix):]))
        return self.json_response(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/upload":
            length = int(self.headers.get("Content-Length", 0))
            if length > 3_000_000_000:
                return self.json_response(413, {"error": "File too large"})
            name = clean_filename(self.headers.get("X-Filename"))
            if Path(name).suffix.lower() not in MEDIA_EXTENSIONS:
                return self.json_response(400, {"error": "Unsupported media type"})
            target = MEDIA / (uuid.uuid4().hex[:10] + "-" + name)
            with target.open("wb") as handle:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    handle.write(chunk)
                    remaining -= len(chunk)
            if remaining:
                target.unlink(missing_ok=True)
                return self.json_response(400, {"error": "Incomplete upload"})
            try:
                item = remember_file(target, name)
            except Exception as error:
                target.unlink(missing_ok=True)
                return self.json_response(400, {"error": str(error)})
            if preview_proxy_required(item, target):
                item["proxyPending"] = start_proxy_background(target)
            return self.json_response(200, item)
        if path == "/api/proxy":
            try:
                body = self.read_json()
                source = MEDIA / safe_name(body.get("file"))
                if not source.is_file():
                    raise ValueError("Missing source media")
                item = media_item(source)
                if item["kind"] != "video":
                    raise ValueError("Preview proxies are available for video clips")
                item["proxyPending"] = start_proxy_background(source)
                return self.json_response(200, item)
            except Exception as error:
                return self.json_response(400, {"error": str(error)})
        if path == "/api/freeze":
            try:
                body = self.read_json()
                source = MEDIA / safe_name(body.get("file"))
                if not source.is_file():
                    raise ValueError("Missing source media")
                target = MEDIA / f"{uuid.uuid4().hex[:10]}-freeze.jpg"
                extract_freeze(source, target, number(body.get("at"), 0, 86400, 0))
                item = remember_file(target, "Freeze frame")
                return self.json_response(200, item)
            except Exception as error:
                return self.json_response(400, {"error": str(error)})
        if path == "/api/analyze":
            try:
                body = self.read_json()
                source = MEDIA / safe_name(body.get("file"))
                if not source.is_file():
                    raise ValueError("Missing source media")
                mask = ANALYSIS / f"{source.stem}-{uuid.uuid4().hex[:6]}-mask.png"
                result = analyze_subject(
                    source, number(body.get("at"), 0, 86400, 0), body.get("manualBox"), mask,
                    number(body.get("end"), 0, 86400, 0),
                )
                if result.get("mask"):
                    result["maskUrl"] = "/analysis/" + result["mask"]
                return self.json_response(200, result)
            except Exception as error:
                return self.json_response(400, {"error": str(error)})
        if path in {"/api/render", "/api/preview"}:
            try:
                body = self.read_json()
                if path == "/api/preview":
                    body["export"] = {**(body.get("export") or {}), "container": "mp4", "codec": "h264", "width": 960, "height": 540, "quality": 28, "hardware": True}
                job = uuid.uuid4().hex[:12]
            except Exception as error:
                return self.json_response(400, {"error": str(error)})
            with LOCK:
                STATUS[job] = {"state": "queued", "progress": 0, "message": "Queued"}
            threading.Thread(target=render_worker, args=(job, body), daemon=True).start()
            return self.json_response(200, {"job": job})
        return self.json_response(404, {"error": "Not found"})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    arguments = parser.parse_args()
    if not ffmpeg_available():
        raise SystemExit("Install FFmpeg and FFprobe and add them to PATH. Windows users can run SETUP_WINDOWS.bat.")
    url = f"http://127.0.0.1:{arguments.port}"
    print(f"VDODesk {VERSION} ready at {url}", flush=True)
    threading.Timer(1, lambda: webbrowser.open(url)).start()
    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nVDODesk stopped.", flush=True)
    finally:
        server.server_close()
