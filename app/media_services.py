"""Media inspection, proxy, waveform and subject-analysis helpers for VDODesk."""
from __future__ import annotations

from array import array
from functools import lru_cache
from pathlib import Path
import json
import math
import shutil
import struct
import subprocess
import zlib


def run(command, timeout=1200):
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    if result.returncode:
        error = result.stderr.decode("utf-8", "replace")[-1500:]
        raise ValueError(error or "Media command failed")
    return result


def probe_media(path: Path):
    result = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,format_name:stream=codec_type,codec_name,width,height,r_frame_rate",
        "-of", "json", str(path),
    ], timeout=30)
    payload = json.loads(result.stdout.decode("utf-8"))
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    video_codec = str((video or {}).get("codec_name") or "").lower()
    audio_codec = str((audio or {}).get("codec_name") or "").lower()
    suffix = path.suffix.lower()
    browser_playable = bool(video) and (
        (suffix in {".mp4", ".m4v"} and video_codec == "h264" and audio_codec in {"", "aac", "mp3"})
        or (suffix == ".webm" and video_codec in {"vp8", "vp9", "av1"} and audio_codec in {"", "opus", "vorbis"})
    )
    return {
        "duration": float(payload.get("format", {}).get("duration") or 0),
        "kind": "video" if video else "audio",
        "hasAudio": bool(audio),
        "width": int((video or {}).get("width") or 0),
        "height": int((video or {}).get("height") or 0),
        "videoCodec": video_codec,
        "audioCodec": audio_codec,
        "browserPlayable": browser_playable,
    }


def encoder_capabilities():
    result = run(["ffmpeg", "-hide_banner", "-encoders"], timeout=30)
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    return {
        "h264VideoToolbox": "h264_videotoolbox" in text,
        "hevcVideoToolbox": "hevc_videotoolbox" in text,
        "h264Nvenc": "h264_nvenc" in text,
        "hevcNvenc": "hevc_nvenc" in text,
        "vp9": "libvpx-vp9" in text,
        "h265": "libx265" in text,
    }


@lru_cache(maxsize=1)
def filter_capabilities():
    """Report optional FFmpeg filters used by VDODesk exports."""
    result = run(["ffmpeg", "-hide_banner", "-filters"], timeout=30)
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    names = set()
    for line in text.splitlines():
        columns = line.split()
        if len(columns) >= 2 and len(columns[0]) == 3:
            names.add(columns[1])
    return {
        "drawtext": "drawtext" in names,
        "ass": "ass" in names,
        "subtitles": "subtitles" in names,
    }


def audio_waveform(path: Path, points=240):
    points = max(32, min(1000, int(points)))
    result = run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-map", "0:a:0?", "-ac", "1", "-ar", "4000", "-f", "s16le", "pipe:1",
    ], timeout=120)
    samples = array("h")
    samples.frombytes(result.stdout)
    if not samples:
        return [0.0] * points
    stride = max(1, math.ceil(len(samples) / points))
    peaks = []
    for offset in range(0, len(samples), stride):
        window = samples[offset:offset + stride]
        peaks.append(round(max((abs(value) for value in window), default=0) / 32768, 4))
    if len(peaks) < points:
        peaks.extend([0.0] * (points - len(peaks)))
    return peaks[:points]


def create_proxy(source: Path, target: Path, hardware=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp.mp4")
    codec = "h264_videotoolbox" if hardware and encoder_capabilities()["h264VideoToolbox"] else "libx264"
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-vf", "scale='min(1280,iw)':-2", "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", codec,
    ]
    if codec == "libx264":
        command += ["-preset", "ultrafast", "-crf", "30"]
    else:
        command += ["-b:v", "3M"]
    command += ["-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(temp)]
    run(command)
    temp.replace(target)
    return target


def extract_freeze(source: Path, target: Path, at: float):
    target.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(max(0, at)),
        "-i", str(source), "-frames:v", "1", "-q:v", "2", str(target),
    ], timeout=120)
    return target


def _write_gray_png(path: Path, width: int, height: int, pixels):
    """Write an 8-bit grayscale PNG without adding a runtime dependency."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        start = y * width
        rows.extend(pixels[start:start + width])
    raw = b"\x89PNG\r\n\x1a\n"
    raw += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
    raw += chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")
    path.write_bytes(raw)


def create_photo_depth_map(source: Path, target: Path, focus_x=.5, focus_y=.45, radius=.36):
    """Create a soft foreground depth mask for single-photo parallax.

    OpenCV uses face-guided GrabCut when available. The dependency-free path
    creates a feathered focal-depth mask, so Photo Motion remains usable on a
    clean Windows/macOS installation.
    """
    focus_x = max(0.05, min(.95, float(focus_x)))
    focus_y = max(0.05, min(.95, float(focus_y)))
    radius = max(.12, min(.75, float(radius)))
    info = probe_media(source)
    source_width, source_height = int(info.get("width") or 0), int(info.get("height") or 0)
    if source_width < 2 or source_height < 2:
        raise ValueError("Unable to read image dimensions")
    scale = min(1, 1280 / max(source_width, source_height))
    width, height = max(2, round(source_width * scale)), max(2, round(source_height * scale))
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        import cv2
        import numpy as np
        frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("OpenCV could not read the image")
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, 1.12, 5, minSize=(30, 30))
        if len(faces):
            fx, fy, fw, fh = max(faces, key=lambda box: box[2] * box[3])
            x = max(1, fx - fw); y = max(1, fy - round(fh * .85))
            w = min(width - x - 1, fw * 3); h = min(height - y - 1, round(fh * 4.3))
            engine = "OpenCV face-guided depth"
        else:
            w, h = round(width * radius * 2), round(height * min(.9, radius * 2.5))
            x, y = round(width * focus_x - w / 2), round(height * focus_y - h / 2)
            x=max(1,min(width-3,x));y=max(1,min(height-3,y));w=max(2,min(width-x-1,w));h=max(2,min(height-y-1,h))
            engine = "OpenCV focal-subject depth"
        mask = np.zeros((height, width), np.uint8)
        background = np.zeros((1, 65), np.float64)
        foreground = np.zeros((1, 65), np.float64)
        cv2.grabCut(frame, mask, (x, y, w, h), background, foreground, 5, cv2.GC_INIT_WITH_RECT)
        mask = np.where((mask == 1) | (mask == 3), 255, 0).astype("uint8")
        sigma = max(2, round(max(width, height) * .012))
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=sigma, sigmaY=sigma)
        if int(mask.max()) < 64 or int(np.count_nonzero(mask)) < width * height * .01:
            raise ValueError("Subject mask was too small")
        if not cv2.imwrite(str(target), mask):
            raise ValueError("Unable to save depth map")
        return {"engine": engine, "width": width, "height": height}
    except Exception as error:
        pixels = bytearray(width * height)
        for y in range(height):
            normalized_y = ((y + .5) / height - focus_y) / (radius * 1.28)
            for x in range(width):
                normalized_x = ((x + .5) / width - focus_x) / radius
                distance = math.sqrt(normalized_x * normalized_x + normalized_y * normalized_y)
                fade = max(0, min(1, (1 - distance) / .72))
                fade = fade * fade * (3 - 2 * fade)
                pixels[y * width + x] = round(255 * fade)
        _write_gray_png(target, width, height, pixels)
        return {"engine": "Local focal-depth fallback", "width": width, "height": height,
                "warning": str(error)}


def analyze_subject(source: Path, at: float, manual_box=None, output_mask: Path | None = None, end: float | None = None):
    """Return a subject box and optional GrabCut mask; fall back to a centered box."""
    try:
        import cv2  # Optional advanced dependency.
        capture = cv2.VideoCapture(str(source))
        capture.set(cv2.CAP_PROP_POS_MSEC, max(0, at) * 1000)
        ok, frame = capture.read()
        capture.release()
        if not ok:
            raise ValueError("Unable to read analysis frame")
        height, width = frame.shape[:2]
        if manual_box:
            x = int(float(manual_box.get("x", .2)) * width)
            y = int(float(manual_box.get("y", .15)) * height)
            w = int(float(manual_box.get("w", .6)) * width)
            h = int(float(manual_box.get("h", .7)) * height)
            engine = "OpenCV GrabCut · manual correction"
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            faces = cascade.detectMultiScale(gray, 1.12, 5, minSize=(30, 30))
            if len(faces):
                fx, fy, fw, fh = max(faces, key=lambda box: box[2] * box[3])
                x = max(0, fx - fw); y = max(0, fy - int(fh * .8))
                w = min(width - x, fw * 3); h = min(height - y, int(fh * 4.2))
                engine = "OpenCV face-guided subject mask"
            else:
                x, y, w, h = int(width * .2), int(height * .12), int(width * .6), int(height * .76)
                engine = "OpenCV center-saliency fallback"
        x=max(0,min(width-2,x));y=max(0,min(height-2,y));w=max(2,min(width-x,w));h=max(2,min(height-y,h))
        path = []
        track_end = max(at, float(end or at))
        if track_end > at + .1:
            template_gray = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
            previous = (x, y, w, h)
            tracking_capture = cv2.VideoCapture(str(source))
            for sample_index in range(12):
                sample_time = at + (track_end - at) * sample_index / 11
                tracking_capture.set(cv2.CAP_PROP_POS_MSEC, sample_time * 1000)
                frame_ok, sample = tracking_capture.read()
                if not frame_ok:
                    continue
                sample_gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
                px, py, pw, ph = previous
                margin_x, margin_y = pw, ph
                sx, sy = max(0, px-margin_x), max(0, py-margin_y)
                ex, ey = min(width, px+pw+margin_x), min(height, py+ph+margin_y)
                search = sample_gray[sy:ey, sx:ex]
                if search.shape[0] >= template_gray.shape[0] and search.shape[1] >= template_gray.shape[1]:
                    response = cv2.matchTemplate(search, template_gray, cv2.TM_CCOEFF_NORMED)
                    _, confidence, _, location = cv2.minMaxLoc(response)
                    px, py = sx + location[0], sy + location[1]
                    previous = (px, py, pw, ph)
                else:
                    confidence = 0
                path.append({"t": sample_time-at, "x": (px+pw/2)/width, "y": (py+ph/2)/height, "confidence": round(float(confidence), 3)})
            tracking_capture.release()
        if not path:
            path = [{"t": 0, "x": (x+w/2)/width, "y": (y+h/2)/height, "confidence": 1}]
        mask = None
        if output_mask:
            import numpy as np
            mask = np.zeros(frame.shape[:2], np.uint8)
            background = np.zeros((1, 65), np.float64)
            foreground = np.zeros((1, 65), np.float64)
            cv2.grabCut(frame, mask, (x, y, w, h), background, foreground, 5, cv2.GC_INIT_WITH_RECT)
            mask = np.where((mask == 2) | (mask == 0), 0, 255).astype("uint8")
            output_mask.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output_mask), mask)
        return {
            "engine": engine,
            "box": {"x": x / width, "y": y / height, "w": w / width, "h": h / height},
            "focus": {"x": (x + w / 2) / width, "y": (y + h / 2) / height},
            "path": path,
            "mask": output_mask.name if mask is not None else "",
        }
    except Exception as error:
        box = manual_box or {"x": .2, "y": .15, "w": .6, "h": .7}
        return {
            "engine": "Manual/center fallback (install opencv-python for AI analysis)",
            "box": {key: float(box.get(key, default)) for key, default in (("x",.2),("y",.15),("w",.6),("h",.7))},
            "focus": {"x": float(box.get("x",.2)) + float(box.get("w",.6))/2, "y": float(box.get("y",.15)) + float(box.get("h",.7))/2},
            "path": [],
            "mask": "",
            "warning": str(error),
        }


def ffmpeg_available():
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
