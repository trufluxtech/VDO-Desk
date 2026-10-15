"""FFmpeg project renderer for the VDODesk local architecture."""
from __future__ import annotations

from pathlib import Path
import json
import math
import shutil
import struct
import subprocess
import textwrap
import zlib

from media_services import encoder_capabilities, filter_capabilities, probe_media, run


TRANSITIONS = {
    "none": "fade",
    "dissolve": "fade",
    "fade": "fadeblack",
    "wipe": "wipeleft",
    "slide": "slideleft",
    "zoom": "zoomin",
}


def number(value, low, high, default):
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def safe_name(value):
    return Path(str(value or "")).name


def escaped_filter_path(path: Path):
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def write_text_file(directory: Path, name: str, content: str):
    path = directory / name
    path.write_text(str(content or "")[:500], encoding="utf-8")
    return path


def ass_time(seconds):
    value = max(0, float(seconds or 0))
    hours = int(value // 3600)
    minutes = int(value % 3600 // 60)
    remaining = value % 60
    return f"{hours}:{minutes:02d}:{remaining:05.2f}"


def ass_text(value):
    """Escape user text so it cannot be interpreted as ASS override markup."""
    return (str(value or "").replace("\\", "\\\\")
            .replace("{", "\\{").replace("}", "\\}")
            .replace("\r\n", "\\N").replace("\r", "\\N").replace("\n", "\\N"))


def ass_alpha(opacity):
    return round((1 - number(opacity, 0, 1, 1)) * 255)


def write_ass_file(directory: Path, name: str, width: int, height: int, styles, events):
    """Write an ASS subtitle document used when drawtext is unavailable."""
    style_rows = []
    for style in styles:
        primary = f"&H{ass_alpha(style.get('opacity', 1)):02X}FFFFFF"
        outline = f"&H{ass_alpha(style.get('boxOpacity', 0)):02X}000000"
        style_rows.append(
            "Style: {name},Arial,{size},{primary},&H000000FF,{outline},&H80000000,"
            "{bold},0,0,0,100,100,0,0,{border},{border_width},1,2,20,20,20,1".format(
                name=style["name"], size=max(8, round(style["size"])), primary=primary,
                outline=outline, bold=-1 if style.get("bold") else 0,
                border=3 if style.get("box") else 1,
                border_width=style.get("borderWidth", 2),
            )
        )
    event_rows = [
        "Dialogue: 0,{start},{end},{style},,0,0,0,,{text}".format(
            start=ass_time(event.get("start", 0)), end=ass_time(event.get("end", 0)),
            style=event["style"], text=event["text"],
        ) for event in events
    ]
    document = "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *style_rows, "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *event_rows, "",
    ])
    path = directory / name
    path.write_text(document, encoding="utf-8")
    return path


def ass_filter(path: Path, capabilities):
    name = "ass" if capabilities.get("ass") else "subtitles"
    return f"{name}=filename='{escaped_filter_path(path)}'"


def text_renderer(capabilities):
    if capabilities.get("drawtext"):
        return "drawtext"
    if capabilities.get("ass") or capabilities.get("subtitles"):
        return "libass"
    return "builtin-image"


# Dependency-free 5x7 fallback used only when FFmpeg has neither drawtext nor
# libass and Pillow is unavailable. Lowercase uses the matching uppercase glyph.
BITMAP_GLYPHS = {
    "A":("01110","10001","10001","11111","10001","10001","10001"),
    "B":("11110","10001","10001","11110","10001","10001","11110"),
    "C":("01111","10000","10000","10000","10000","10000","01111"),
    "D":("11110","10001","10001","10001","10001","10001","11110"),
    "E":("11111","10000","10000","11110","10000","10000","11111"),
    "F":("11111","10000","10000","11110","10000","10000","10000"),
    "G":("01111","10000","10000","10111","10001","10001","01111"),
    "H":("10001","10001","10001","11111","10001","10001","10001"),
    "I":("11111","00100","00100","00100","00100","00100","11111"),
    "J":("00111","00010","00010","00010","10010","10010","01100"),
    "K":("10001","10010","10100","11000","10100","10010","10001"),
    "L":("10000","10000","10000","10000","10000","10000","11111"),
    "M":("10001","11011","10101","10101","10001","10001","10001"),
    "N":("10001","11001","10101","10011","10001","10001","10001"),
    "O":("01110","10001","10001","10001","10001","10001","01110"),
    "P":("11110","10001","10001","11110","10000","10000","10000"),
    "Q":("01110","10001","10001","10001","10101","10010","01101"),
    "R":("11110","10001","10001","11110","10100","10010","10001"),
    "S":("01111","10000","10000","01110","00001","00001","11110"),
    "T":("11111","00100","00100","00100","00100","00100","00100"),
    "U":("10001","10001","10001","10001","10001","10001","01110"),
    "V":("10001","10001","10001","10001","10001","01010","00100"),
    "W":("10001","10001","10001","10101","10101","10101","01010"),
    "X":("10001","10001","01010","00100","01010","10001","10001"),
    "Y":("10001","10001","01010","00100","00100","00100","00100"),
    "Z":("11111","00001","00010","00100","01000","10000","11111"),
    "0":("01110","10001","10011","10101","11001","10001","01110"),
    "1":("00100","01100","00100","00100","00100","00100","01110"),
    "2":("01110","10001","00001","00010","00100","01000","11111"),
    "3":("11110","00001","00001","01110","00001","00001","11110"),
    "4":("00010","00110","01010","10010","11111","00010","00010"),
    "5":("11111","10000","10000","11110","00001","00001","11110"),
    "6":("01110","10000","10000","11110","10001","10001","01110"),
    "7":("11111","00001","00010","00100","01000","01000","01000"),
    "8":("01110","10001","10001","01110","10001","10001","01110"),
    "9":("01110","10001","10001","01111","00001","00001","01110"),
    " ":("00000",)*7,".":("00000","00000","00000","00000","00000","00110","00110"),
    ",":("00000","00000","00000","00000","00110","00110","00100"),
    ":":("00000","00110","00110","00000","00110","00110","00000"),
    "-":("00000","00000","00000","11111","00000","00000","00000"),
    "_":("00000","00000","00000","00000","00000","00000","11111"),
    "/":("00001","00010","00010","00100","01000","01000","10000"),
    "!":("00100","00100","00100","00100","00100","00000","00100"),
    "?":("01110","10001","00001","00010","00100","00000","00100"),
    "'":("00100","00100","00000","00000","00000","00000","00000"),
    '"':("01010","01010","00000","00000","00000","00000","00000"),
    "(":("00010","00100","01000","01000","01000","00100","00010"),
    ")":("01000","00100","00010","00010","00010","00100","01000"),
    "+":("00000","00100","00100","11111","00100","00100","00000"),
    "=":("00000","11111","00000","11111","00000","00000","00000"),
    "&":("01100","10010","10100","01000","10101","10010","01101"),
    "@":("01110","10001","10111","10101","10111","10000","01110"),
    "#":("01010","11111","01010","01010","11111","01010","00000"),
    "%":("11001","11010","00100","01000","10110","00110","00000"),
}


def write_rgba_png(path, width, height, pixels):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    rows = b"".join(b"\x00" + bytes(pixels[y * width * 4:(y + 1) * width * 4]) for y in range(height))
    raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    raw += chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
    path.write_bytes(raw)


def wrapped_text(value, maximum_characters):
    lines = []
    for paragraph in str(value or "")[:500].replace("\r", "").split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=max(1, maximum_characters),
                                   break_long_words=True, replace_whitespace=False) or [""])
    return "\n".join(lines)


def render_text_png(path, text, font_size, max_width, opacity=1, box_opacity=0,
                    bold=False, prefer_pillow=True):
    """Create a transparent text card without relying on an FFmpeg text filter."""
    font_size = max(10, round(font_size));max_width = max(60, round(max_width))
    value = wrapped_text(text, max(1, round(max_width / (font_size * .58))))
    if prefer_pillow:
        try:
            from PIL import Image, ImageDraw, ImageFont
            candidates = [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Supplemental/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
            font = next((ImageFont.truetype(name, font_size) for name in candidates if Path(name).is_file()), ImageFont.load_default())
            probe = Image.new("RGBA", (1, 1));drawer = ImageDraw.Draw(probe)
            stroke = max(1, round(font_size / 28))
            left, top, right, bottom = drawer.multiline_textbbox((0, 0), value, font=font, spacing=font_size // 5, stroke_width=stroke)
            padding = max(5, round(font_size * .28));width=max(2,right-left+padding*2);height=max(2,bottom-top+padding*2)
            image = Image.new("RGBA", (width, height), (0, 0, 0, round(255 * box_opacity)))
            drawer = ImageDraw.Draw(image)
            drawer.multiline_text((padding-left, padding-top), value, font=font, spacing=font_size//5,
                                  fill=(255,255,255,round(255*opacity)), stroke_width=stroke,
                                  stroke_fill=(0,0,0,round(230*opacity)), align="center")
            image.save(path, "PNG")
            return path, width, height
        except (ImportError, OSError, StopIteration):
            pass
    scale=max(1,round(font_size/7));char_width=6*scale;line_height=9*scale;padding=max(3,2*scale)
    value=wrapped_text(text,max(1,(max_width-padding*2)//char_width));lines=value.split("\n")
    width=min(max_width,max(2,max((len(line) for line in lines),default=1)*char_width-scale+padding*2))
    height=max(2,len(lines)*line_height-2*scale+padding*2);pixels=bytearray(width*height*4)
    background=(0,0,0,round(255*box_opacity));foreground=(255,255,255,round(255*opacity));shadow=(0,0,0,round(220*opacity))
    if background[3]:
        for offset in range(0,len(pixels),4):pixels[offset:offset+4]=bytes(background)
    def rectangle(x0,y0,x1,y1,color):
        for yy in range(max(0,y0),min(height,y1)):
            for xx in range(max(0,x0),min(width,x1)):
                offset=(yy*width+xx)*4;pixels[offset:offset+4]=bytes(color)
    def glyph(line_x,line_y,character,color,extra=0):
        pattern=BITMAP_GLYPHS.get(character.upper(),BITMAP_GLYPHS["?"])
        for row,bits in enumerate(pattern):
            for column,bit in enumerate(bits):
                if bit=="1":rectangle(line_x+column*scale,line_y+row*scale,line_x+(column+1)*scale+extra,line_y+(row+1)*scale,color)
    for row,line in enumerate(lines):
        line_width=max(0,len(line)*char_width-scale);start=max(padding,(width-line_width)//2);y=padding+row*line_height
        for column,character in enumerate(line):
            x=start+column*char_width;glyph(x+scale,y+scale,character,shadow);glyph(x,y,character,foreground,1 if bold else 0)
    write_rgba_png(path,width,height,pixels);return path,width,height


def output_dimensions(spec):
    export = spec.get("export") or {}
    custom_width = int(number(export.get("width"), 240, 7680, 0))
    custom_height = int(number(export.get("height"), 240, 4320, 0))
    if custom_width and custom_height:
        return custom_width // 2 * 2, custom_height // 2 * 2
    return {
        "16:9": (1920, 1080), "9:16": (1080, 1920), "4:3": (1440, 1080),
        "3:4": (1080, 1440), "1:1": (1080, 1080),
    }.get(spec.get("ratio"), (1920, 1080))


def clip_duration(clip, media_path):
    if clip.get("kind") == "freeze" or media_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        return number(clip.get("duration"), .1, 3600, 3)
    info = probe_media(media_path)
    start = number(clip.get("start"), 0, info["duration"], 0)
    end = number(clip.get("end"), start + .05, info["duration"], info["duration"])
    return max(.05, (end - start) / number(clip.get("speed"), .25, 4, 1))


def atempo_filters(speed):
    filters = []
    remaining = speed
    while remaining > 2:
        filters.append("atempo=2")
        remaining /= 2
    while remaining < .5:
        filters.append("atempo=.5")
        remaining /= .5
    filters.append(f"atempo={remaining:.6f}")
    return filters


def clip_filter_chain(clip):
    """Return deterministic FFmpeg filters for a selected clip preset."""
    preset = str(clip.get("filter") or "none").lower()
    strength = number(clip.get("filterIntensity"), 0, 1, 1)
    if preset == "none" or strength <= .0001:
        return []
    if preset == "cinematic":
        return [
            f"eq=contrast={1 + .14 * strength:.6f}:saturation={1 + .08 * strength:.6f}",
            f"colorbalance=rs={-.08 * strength:.6f}:bs={.10 * strength:.6f}:rh={.10 * strength:.6f}:bh={-.08 * strength:.6f}",
        ]
    if preset == "warm":
        return [
            f"colorbalance=rs={.14 * strength:.6f}:gs={.04 * strength:.6f}:bs={-.10 * strength:.6f}",
            f"eq=brightness={.02 * strength:.6f}:saturation={1 + .10 * strength:.6f}",
        ]
    if preset == "cool":
        return [
            f"colorbalance=rs={-.08 * strength:.6f}:gs={-.02 * strength:.6f}:bs={.14 * strength:.6f}",
            f"eq=contrast={1 + .05 * strength:.6f}:saturation={1 + .04 * strength:.6f}",
        ]
    if preset == "vintage":
        return [
            f"colorbalance=rs={.10 * strength:.6f}:gs={.03 * strength:.6f}:bs={-.08 * strength:.6f}",
            f"eq=brightness={.03 * strength:.6f}:contrast={1 - .08 * strength:.6f}:saturation={1 - .30 * strength:.6f}",
        ]
    if preset == "mono":
        return [f"hue=s={1 - strength:.6f}"]
    if preset == "noir":
        return [
            f"hue=s={1 - strength:.6f}",
            f"eq=brightness={-.06 * strength:.6f}:contrast={1 + .42 * strength:.6f}",
        ]
    if preset == "vivid":
        return [f"eq=contrast={1 + .12 * strength:.6f}:saturation={1 + .55 * strength:.6f}"]
    if preset == "soft":
        return [f"eq=brightness={.05 * strength:.6f}:contrast={1 - .12 * strength:.6f}:saturation={1 - .08 * strength:.6f}"]
    if preset == "teal_orange":
        return [
            f"colorbalance=rs={-.10 * strength:.6f}:bs={.14 * strength:.6f}:rh={.16 * strength:.6f}:gh={.04 * strength:.6f}:bh={-.12 * strength:.6f}",
            f"eq=contrast={1 + .08 * strength:.6f}:saturation={1 + .18 * strength:.6f}",
        ]
    return []


def render_piece(clip, index, source, target, width, height, fps, temp, overlay=False,
                 text_filters=None, warnings=None):
    text_filters = text_filters or {}
    warnings = warnings if warnings is not None else []
    still = clip.get("kind") == "freeze" or source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    duration = clip_duration(clip, source)
    speed = number(clip.get("speed"), .25, 4, 1)
    start = number(clip.get("start"), 0, 86400, 0)
    source_span = duration * speed
    if still:
        input_args = ["-loop", "1", "-t", str(duration), "-i", str(source)]
        info = {"hasAudio": False}
    else:
        info = probe_media(source)
        source_span = min(source_span, max(.05, info["duration"] - start))
        input_args = ["-ss", str(start), "-t", str(source_span), "-i", str(source)]

    crop = clip.get("crop") or {}
    crop_x = number(crop.get("x"), 0, .95, 0)
    crop_y = number(crop.get("y"), 0, .95, 0)
    crop_w = number(crop.get("w"), .05, 1 - crop_x, 1)
    crop_h = number(crop.get("h"), .05, 1 - crop_y, 1)
    zoom0 = number(clip.get("zoom"), 1, 8, 1)
    keyframes = clip.get("keyframes") or {}
    zoom1 = number(keyframes.get("zoomEnd"), 1, 8, zoom0)
    focus_x0 = number(clip.get("focusX"), 0, 1, .5)
    focus_y0 = number(clip.get("focusY"), 0, 1, .5)
    focus_x1 = number(keyframes.get("focusXEnd"), 0, 1, focus_x0)
    focus_y1 = number(keyframes.get("focusYEnd"), 0, 1, focus_y0)
    frames = max(1, round(duration * fps))

    brightness0 = number(clip.get("brightness"), -1, 1, 0)
    contrast0 = number(clip.get("contrast"), .1, 4, 1)
    saturation0 = number(clip.get("saturation"), 0, 4, 1)
    gamma0 = number(clip.get("gamma"), .1, 4, 1)
    brightness1 = number(keyframes.get("brightnessEnd"), -1, 1, brightness0)
    contrast1 = number(keyframes.get("contrastEnd"), .1, 4, contrast0)
    saturation1 = number(keyframes.get("saturationEnd"), 0, 4, saturation0)
    gamma1 = number(keyframes.get("gammaEnd"), .1, 4, gamma0)

    vf = ["setpts=PTS-STARTPTS"]
    if clip.get("reverse") and not still:
        vf += ["reverse", "setpts=PTS-STARTPTS"]
    if not still:
        vf.append(f"setpts=PTS/{speed:.6f}")
    if clip.get("stabilize") and not still:
        strength = int(number(clip.get("stabilizeStrength"), 4, 32, 12))
        vf.append(f"deshake=rx={strength}:ry={strength}:edge=mirror")
    vf.append(f"crop=iw*{crop_w:.6f}:ih*{crop_h:.6f}:iw*{crop_x:.6f}:ih*{crop_y:.6f}")
    if clip.get("mirrorH"):
        vf.append("hflip")
    if clip.get("mirrorV"):
        vf.append("vflip")
    rotation = number(clip.get("rotation"), -360, 360, 0)
    if abs(rotation) > .001:
        fill = "black@0" if overlay else "black"
        vf.append(f"rotate={rotation:.6f}*PI/180:ow=rotw(iw):oh=roth(ih):fillcolor={fill}")
    temperature = number(clip.get("temperature"), -100, 100, 0) / 200
    tint = number(clip.get("tint"), -100, 100, 0) / 200
    if abs(temperature) > .001 or abs(tint) > .001:
        vf.append(f"colorbalance=rs={temperature:.4f}:bs={-temperature:.4f}:gm={tint:.4f}:bm={-tint:.4f}")
    hue = number(clip.get("hue"), -180, 180, 0)
    if abs(hue) > .001:
        vf.append(f"hue=h={hue:.4f}")
    shadows = number(clip.get("shadows"), -100, 100, 0)
    highlights = number(clip.get("highlights"), -100, 100, 0)
    if abs(shadows) > .001 or abs(highlights) > .001:
        low = max(0, min(1, .25 + shadows / 500))
        high = max(0, min(1, .75 + highlights / 500))
        vf.append(f"curves=all='0/0 .25/{low:.4f} .75/{high:.4f} 1/1'")
    progress = f"min(t/{max(.05,duration):.6f},1)"
    vf.append(
        "eq="
        f"brightness='{brightness0:.6f}+({brightness1-brightness0:.6f})*{progress}':"
        f"contrast='{contrast0:.6f}+({contrast1-contrast0:.6f})*{progress}':"
        f"saturation='{saturation0:.6f}+({saturation1-saturation0:.6f})*{progress}':"
        f"gamma='{gamma0:.6f}+({gamma1-gamma0:.6f})*{progress}':eval=frame"
    )
    vf += clip_filter_chain(clip)
    lut_name = safe_name(clip.get("lut"))
    if lut_name:
        lut_path = source.parent / lut_name
        if lut_path.is_file():
            vf.append(f"lut3d=file='{escaped_filter_path(lut_path)}'")
    vf += [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
        (
            "zoompan="
            f"z='{zoom0:.6f}+({zoom1-zoom0:.6f})*on/{frames}':"
            f"x='(iw-iw/zoom)*({focus_x0:.6f}+({focus_x1-focus_x0:.6f})*on/{frames})':"
            f"y='(ih-ih/zoom)*({focus_y0:.6f}+({focus_y1-focus_y0:.6f})*on/{frames})':"
            f"d=1:s={width}x{height}:fps={fps}"
        ),
    ]
    if overlay:
        scale = number(clip.get("scale"), .05, 1, .45)
        pos_x = number(clip.get("positionX"), 0, 1, .5)
        pos_y = number(clip.get("positionY"), 0, 1, .5)
        opacity = number(clip.get("opacity"), 0, 1, 1)
        vf += [
            f"scale=iw*{scale:.6f}:ih*{scale:.6f}", "format=rgba",
            f"colorchannelmixer=aa={opacity:.6f}",
            f"pad={width}:{height}:(ow-iw)*{pos_x:.6f}:(oh-ih)*{pos_y:.6f}:color=black@0",
        ]
    tracking = clip.get("tracking") or {}
    tracking_box = tracking.get("box") or {}
    if tracking.get("outline") and tracking_box:
        box_x = number(tracking_box.get("x"), 0, 1, .2)
        box_y = number(tracking_box.get("y"), 0, 1, .15)
        box_w = number(tracking_box.get("w"), .01, 1, .6)
        box_h = number(tracking_box.get("h"), .01, 1, .7)
        vf.append(
            f"drawbox=x=iw*{box_x:.6f}:y=ih*{box_y:.6f}:w=iw*{box_w:.6f}:h=ih*{box_h:.6f}:"
            "color=cyan@.9:t=max(2\\,h/180)"
        )
    anchor = str(clip.get("anchorText") or "").strip()
    anchor_image = None
    anchor_motion = None
    if anchor:
        tracking_path = tracking.get("path") or []
        focus = tracking.get("focus") or {"x": .5, "y": .35}
        first_focus = tracking_path[0] if tracking_path else focus
        last_focus = tracking_path[-1] if tracking_path else focus
        x = number(first_focus.get("x"), 0, 1, .5)
        y = number(first_focus.get("y"), 0, 1, .35)
        end_x = number(last_focus.get("x"), 0, 1, x)
        end_y = number(last_focus.get("y"), 0, 1, y)
        if text_filters.get("drawtext"):
            anchor_path = write_text_file(temp, f"anchor-{index}.txt", anchor)
            vf.append(
                f"drawtext=textfile='{escaped_filter_path(anchor_path)}':fontcolor=white:fontsize=h/22:"
                f"box=1:boxcolor=black@.45:boxborderw=10:"
                f"x='w*({x:.6f}+({end_x-x:.6f})*min(t/{max(.05,duration):.6f}\\,1))-text_w/2':"
                f"y='h*({y:.6f}+({end_y-y:.6f})*min(t/{max(.05,duration):.6f}\\,1))-text_h-18'"
            )
        elif text_filters.get("ass") or text_filters.get("subtitles"):
            x0, y0 = round(width * x), round(height * y) - 18
            x1, y1 = round(width * end_x), round(height * end_y) - 18
            motion = f"\\move({x0},{y0},{x1},{y1},0,{round(duration * 1000)})"
            anchor_ass = write_ass_file(
                temp, f"anchor-{index}.ass", width, height,
                [{"name": "Anchor", "size": height / 22, "bold": True,
                  "box": True, "boxOpacity": .45, "borderWidth": 10}],
                [{"start": 0, "end": duration, "style": "Anchor",
                  "text": "{\\an2" + motion + "}" + ass_text(anchor)}],
            )
            vf.append(ass_filter(anchor_ass, text_filters))
        else:
            anchor_image, _, _ = render_text_png(
                temp / f"anchor-{index}.png", anchor, height / 22, width * .45,
                box_opacity=.45, bold=True,
            )
            anchor_motion = (x, y, end_x, end_y)
    vf.append("format=argb" if overlay else "format=yuv420p")

    muted = bool(clip.get("mute"))
    volume0 = 0 if muted else number(clip.get("volume"), 0, 4, 1)
    volume1 = 0 if muted else number(keyframes.get("volumeEnd"), 0, 4, volume0)
    af = ["asetpts=PTS-STARTPTS"]
    if clip.get("reverse") and not still:
        af += ["areverse", "asetpts=PTS-STARTPTS"]
    if not still:
        af += atempo_filters(speed)
    af += [
        f"volume='{volume0:.6f}+({volume1-volume0:.6f})*min(t/{max(.05,duration):.6f},1)':eval=frame",
        "aresample=48000:async=1:first_pts=0",
    ]

    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *input_args]
    audio_index = 0
    if still or not info.get("hasAudio"):
        command += ["-f", "lavfi", "-t", str(duration), "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        audio_index = 1
    if anchor_image:
        anchor_index = 2 if audio_index == 1 else 1
        command += ["-loop", "1", "-framerate", str(fps), "-t", str(duration), "-i", str(anchor_image)]
        x, y, end_x, end_y = anchor_motion
        progress = f"min(t/{max(.05,duration):.6f}\\,1)"
        graph = (
            f"[0:v]{','.join(vf)}[basev];[{anchor_index}:v]format=rgba[anchorv];"
            f"[basev][anchorv]overlay="
            f"x='main_w*({x:.6f}+({end_x-x:.6f})*{progress})-overlay_w/2':"
            f"y='main_h*({y:.6f}+({end_y-y:.6f})*{progress})-overlay_h-18':"
            "eof_action=pass[vout]"
        )
        command += ["-filter_complex", graph, "-af", ",".join(af), "-map", "[vout]", "-map", f"{audio_index}:a:0"]
    else:
        command += ["-vf", ",".join(vf), "-af", ",".join(af), "-map", "0:v:0", "-map", f"{audio_index}:a:0"]
    command += ["-t", str(duration)]
    if overlay:
        command += ["-c:v", "qtrle", "-pix_fmt", "argb", "-c:a", "pcm_s16le", str(target)]
    else:
        command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target)]
    run(command)
    return duration


def join_primary(pieces, clips, durations, target, width, height, fps, fallback_duration=1):
    if not pieces:
        total = max(1, fallback_duration)
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            f"color=c=black:s={width}x{height}:r={fps}:d={total}", "-f", "lavfi", "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=48000:d={total}", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(target),
        ])
        return total
    if len(pieces) == 1:
        shutil.copy2(pieces[0], target)
        return durations[0]
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for piece in pieces:
        command += ["-i", str(piece)]
    graph = []
    video_label, audio_label = "0:v", "0:a"
    elapsed = durations[0]
    for index in range(1, len(pieces)):
        incoming = clips[index]
        kind = str(incoming.get("transition") or "none")
        requested = number(incoming.get("transitionDuration"), .04, 3, .5)
        transition_duration = .04 if kind == "none" else min(requested, durations[index] / 2, elapsed / 2)
        offset = max(.01, elapsed - transition_duration)
        next_video, next_audio = f"v{index}", f"a{index}"
        graph.append(
            f"[{video_label}][{index}:v]xfade=transition={TRANSITIONS.get(kind,'fade')}:"
            f"duration={transition_duration:.6f}:offset={offset:.6f}[{next_video}]"
        )
        graph.append(f"[{audio_label}][{index}:a]acrossfade=d={transition_duration:.6f}:c1=tri:c2=tri[{next_audio}]")
        video_label, audio_label = next_video, next_audio
        elapsed += durations[index] - transition_duration
    command += [
        "-filter_complex", ";".join(graph), "-map", f"[{video_label}]", "-map", f"[{audio_label}]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target),
    ]
    run(command)
    return elapsed


def composite_overlays(base, overlays, target, total_duration):
    if not overlays:
        shutil.copy2(base, target)
        return
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(base)]
    for item in overlays:
        command += ["-i", str(item["path"])]
    graph = []
    video_label = "0:v"
    audio_labels = ["[0:a]"]
    for index, item in enumerate(overlays, 1):
        start = number(item.get("start"), 0, total_duration, 0)
        end = min(total_duration, start + item["duration"])
        graph.append(f"[{index}:v]setpts=PTS-STARTPTS+{start:.6f}/TB[ov{index}]")
        graph.append(f"[{video_label}][ov{index}]overlay=0:0:eof_action=pass:enable='between(t,{start:.6f},{end:.6f})'[mixv{index}]")
        video_label = f"mixv{index}"
        delay = round(start * 1000)
        graph.append(f"[{index}:a]adelay={delay}|{delay}[ova{index}]")
        audio_labels.append(f"[ova{index}]")
    graph.append("".join(audio_labels) + f"amix=inputs={len(audio_labels)}:duration=first:dropout_transition=0[mixa]")
    command += [
        "-filter_complex", ";".join(graph), "-map", f"[{video_label}]", "-map", "[mixa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-t", str(total_duration), "-movflags", "+faststart", str(target),
    ]
    run(command)


def final_codec(spec, capabilities):
    export = spec.get("export") or {}
    container = str(export.get("container") or "mp4").lower()
    if container not in {"mp4", "mov", "webm"}:
        container = "mp4"
    codec = str(export.get("codec") or ("vp9" if container == "webm" else "h264")).lower()
    # Keep combinations playable and accepted by their containers even when a
    # hand-edited project manifest contains an incompatible pair.
    if container == "webm":
        codec = "vp9"
    elif codec not in {"h264", "h265"}:
        codec = "h264"
    hardware = export.get("hardware", True) is not False
    if codec == "h265":
        selected = "hevc_videotoolbox" if hardware and capabilities.get("hevcVideoToolbox") else "libx265"
    elif codec == "vp9":
        selected = "libvpx-vp9"
    else:
        selected = "h264_videotoolbox" if hardware and capabilities.get("h264VideoToolbox") else "libx264"
    return container, codec, selected


def finish_project(base, spec, media, output, temp, total_duration, text_filters=None, warnings=None):
    text_filters = text_filters or {}
    warnings = warnings if warnings is not None else []
    title = str(spec.get("title") or "").strip()
    text_watermark = str(spec.get("watermark") or "").strip()
    frame_width, frame_height = output_dimensions(spec)
    fps = int(number(spec.get("fps"), 12, 120, 30))
    builtin_text = not text_filters.get("drawtext") and not (
        text_filters.get("ass") or text_filters.get("subtitles"))
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(base)]
    input_index = 1
    image_watermark = spec.get("imageWatermark") or {}
    watermark_index = None
    watermark_name = safe_name(image_watermark.get("file"))
    if watermark_name and (media / watermark_name).is_file():
        watermark_index = input_index; input_index += 1
        command += ["-loop", "1", "-i", str(media / watermark_name)]
    stickers = []
    for sticker in spec.get("stickers") or []:
        name = safe_name(sticker.get("file"))
        source = media / name
        if not name or not source.is_file():
            if name:
                warnings.append(f"Skipped missing sticker: {name}.")
            continue
        stickers.append((input_index, sticker));input_index += 1
        command += ["-loop", "1", "-framerate", str(fps), "-i", str(source)]
    music_index = None
    music_name = safe_name(spec.get("audio"))
    if music_name and (media / music_name).is_file():
        music_index = input_index; input_index += 1
        command += ["-stream_loop", "-1", "-i", str(media / music_name)]
    timeline_audio = []
    for audio_clip in spec.get("audioClips") or []:
        name = safe_name(audio_clip.get("file"))
        source = media / name
        if audio_clip.get("mute") or not name or not source.is_file():
            continue
        try:
            if not probe_media(source).get("hasAudio"):
                warnings.append(f"Skipped A1 item without audio: {name}.")
                continue
        except (ValueError, subprocess.CalledProcessError):
            warnings.append(f"Skipped unreadable A1 audio: {name}.")
            continue
        source_start = number(audio_clip.get("sourceStart"), 0, 86400, 0)
        timeline_audio.append((input_index, audio_clip)); input_index += 1
        command += ["-stream_loop", "-1", "-ss", str(source_start), "-i", str(source)]
    voices = []
    for voice in spec.get("voiceovers") or []:
        name = safe_name(voice.get("file"))
        if name and (media / name).is_file():
            voices.append((input_index, voice)); input_index += 1
            command += ["-i", str(media / name)]

    title_image_index = None
    watermark_text_index = None
    if builtin_text and title:
        title_image, _, _ = render_text_png(
            temp / "project-title.png", title, frame_height / 15, frame_width * .82,
            box_opacity=.4, bold=True,
        )
        title_image_index = input_index;input_index += 1
        command += ["-loop", "1", "-framerate", str(fps), "-i", str(title_image)]
    if builtin_text and text_watermark:
        watermark_image, _, _ = render_text_png(
            temp / "text-watermark.png", text_watermark, frame_height / 28, frame_width * .55,
            opacity=number(spec.get("watermarkOpacity"), 0, 1, .55),
        )
        watermark_text_index = input_index;input_index += 1
        command += ["-loop", "1", "-framerate", str(fps), "-i", str(watermark_image)]

    graph = ["[0:v]null[v0]", "[0:a]anull[a0]"]
    video_label = "v0"
    if text_filters.get("drawtext") and title:
        title_path = write_text_file(temp, "project-title.txt", title)
        graph.append(
            f"[{video_label}]drawtext=textfile='{escaped_filter_path(title_path)}':fontcolor=white:fontsize=h/15:"
            "box=1:boxcolor=black@.4:boxborderw=18:x=(w-text_w)/2:y=h*.78:enable='between(t,0,5)'[vtitle]"
        ); video_label = "vtitle"
    if text_filters.get("drawtext") and text_watermark:
        watermark_path = write_text_file(temp, "text-watermark.txt", text_watermark)
        opacity = number(spec.get("watermarkOpacity"), 0, 1, .55)
        graph.append(
            f"[{video_label}]drawtext=textfile='{escaped_filter_path(watermark_path)}':fontcolor=white@{opacity:.4f}:"
            "fontsize=h/28:x=w-text_w-25:y=25[vtextwm]"
        ); video_label = "vtextwm"
    if (title or text_watermark) and not text_filters.get("drawtext"):
        if text_filters.get("ass") or text_filters.get("subtitles"):
            styles, events = [], []
            if title:
                styles.append({"name": "Title", "size": frame_height / 15, "bold": True,
                               "box": True, "boxOpacity": .4, "borderWidth": 18})
                events.append({
                    "start": 0, "end": min(5, total_duration), "style": "Title",
                    "text": f"{{\\an2\\pos({frame_width // 2},{round(frame_height * .78)})}}{ass_text(title)}",
                })
            if text_watermark:
                opacity = number(spec.get("watermarkOpacity"), 0, 1, .55)
                styles.append({"name": "Watermark", "size": frame_height / 28,
                               "opacity": opacity, "borderWidth": 1})
                events.append({
                    "start": 0, "end": total_duration, "style": "Watermark",
                    "text": f"{{\\an9\\pos({frame_width - 25},25)}}{ass_text(text_watermark)}",
                })
            text_ass = write_ass_file(temp, "project-text.ass", frame_width, frame_height, styles, events)
            graph.append(f"[{video_label}]{ass_filter(text_ass, text_filters)}[vtext]")
            video_label = "vtext"
        else:
            if title_image_index is not None:
                graph.append(f"[{title_image_index}:v]format=rgba[titleimg]")
                graph.append(
                    f"[{video_label}][titleimg]overlay=x=(main_w-overlay_w)/2:"
                    f"y=main_h*.78-overlay_h:enable='between(t,0,{min(5,total_duration):.6f})':eof_action=pass[vtitle]"
                );video_label = "vtitle"
            if watermark_text_index is not None:
                graph.append(f"[{watermark_text_index}:v]format=rgba[textwm]")
                graph.append(
                    f"[{video_label}][textwm]overlay=x=main_w-overlay_w-25:y=25:eof_action=pass[vtextwm]"
                );video_label = "vtextwm"
    if watermark_index is not None:
        scale = number(image_watermark.get("scale"), .03, 1, .2)
        opacity = number(image_watermark.get("opacity"), 0, 1, .7)
        x = number(image_watermark.get("x"), 0, 1, .8)
        y = number(image_watermark.get("y"), 0, 1, .08)
        graph.append(f"[{watermark_index}:v]scale={max(2, int(frame_width * scale))}:-1,format=rgba,colorchannelmixer=aa={opacity:.6f}[wm]")
        graph.append(f"[{video_label}][wm]overlay=x=(main_w-overlay_w)*{x:.6f}:y=(main_h-overlay_h)*{y:.6f}:shortest=1[vwm]")
        video_label = "vwm"
    for number_index, (source_index, sticker) in enumerate(stickers):
        start = number(sticker.get("start"), 0, total_duration, 0)
        duration = min(number(sticker.get("duration"), .05, 86400, 3),
                       max(.05, total_duration - start))
        end = start + duration
        scale = number(sticker.get("scale"), .03, .8, .18)
        opacity = number(sticker.get("opacity"), 0, 1, 1)
        x = number(sticker.get("x"), 0, 1, .5)
        y = number(sticker.get("y"), 0, 1, .5)
        rotation = math.radians(number(sticker.get("rotation"), -180, 180, 0))
        sticker_label = f"sticker{number_index}"
        filters = [f"scale={max(2, int(frame_width * scale))}:-1", "format=rgba",
                   f"colorchannelmixer=aa={opacity:.6f}"]
        if abs(rotation) > .000001:
            filters.append(f"rotate={rotation:.9f}:ow='rotw(iw)':oh='roth(ih)':fillcolor=black@0")
        graph.append(f"[{source_index}:v]{','.join(filters)}[{sticker_label}]")
        output_label = f"vsticker{number_index}"
        graph.append(
            f"[{video_label}][{sticker_label}]overlay="
            f"x='main_w*{x:.6f}-overlay_w/2':y='main_h*{y:.6f}-overlay_h/2':"
            f"enable='between(t,{start:.6f},{end:.6f})':eof_action=pass[{output_label}]"
        )
        video_label = output_label

    audio_label = "a0"
    if music_index is not None:
        music_volume = number(spec.get("musicVolume"), 0, 4, .5)
        graph.append(f"[{music_index}:a]atrim=duration={total_duration:.6f},asetpts=PTS-STARTPTS,volume={music_volume:.6f}[music]")
        graph.append(f"[{audio_label}][music]amix=inputs=2:duration=first:dropout_transition=0[bed]")
        audio_label = "bed"
    timeline_audio_labels = []
    for number_index, (source_index, audio_clip) in enumerate(timeline_audio):
        start = number(audio_clip.get("start"), 0, total_duration, 0)
        duration = min(number(audio_clip.get("duration"), .05, 86400, 3),
                       max(.05, total_duration - start))
        speed = number(audio_clip.get("speed"), .25, 4, 1)
        volume = number(audio_clip.get("volume"), 0, 4, 1)
        filters = [f"atrim=duration={duration * speed:.6f}", "asetpts=PTS-STARTPTS"]
        if audio_clip.get("reverse"):
            filters += ["areverse", "asetpts=PTS-STARTPTS"]
        filters += atempo_filters(speed)
        delay = round(start * 1000)
        filters += [f"atrim=duration={duration:.6f}", f"volume={volume:.6f}",
                    f"adelay={delay}|{delay}", "aresample=48000:async=1:first_pts=0"]
        label = f"timelineaudio{number_index}"
        graph.append(f"[{source_index}:a]{','.join(filters)}[{label}]")
        timeline_audio_labels.append(f"[{label}]")
    if timeline_audio_labels:
        graph.append(f"[{audio_label}]" + "".join(timeline_audio_labels) +
                     f"amix=inputs={len(timeline_audio_labels) + 1}:duration=first:dropout_transition=0[timelinebed]")
        audio_label = "timelinebed"
    voice_labels = []
    for number_index, (source_index, voice) in enumerate(voices):
        delay = round(number(voice.get("start"), 0, total_duration, 0) * 1000)
        volume = number(voice.get("volume"), 0, 4, 1)
        label = f"voice{number_index}"
        graph.append(f"[{source_index}:a]adelay={delay}|{delay},volume={volume:.6f}[{label}]")
        voice_labels.append(f"[{label}]")
    if voice_labels:
        graph.append("".join(voice_labels) + f"amix=inputs={len(voice_labels)}:duration=longest:dropout_transition=0[voices]")
        if spec.get("audioDucking", True):
            # The voice mix feeds both the sidechain detector and the audible
            # final mix. Filter outputs are single-use, so split it explicitly.
            graph.append("[voices]asplit=2[voices_sidechain][voices_audible]")
            graph.append(f"[{audio_label}][voices_sidechain]sidechaincompress=threshold=.025:ratio=8:attack=20:release=350[duck]")
            graph.append("[duck][voices_audible]amix=inputs=2:duration=first:dropout_transition=0[finala]")
        else:
            graph.append(f"[{audio_label}][voices]amix=inputs=2:duration=first:dropout_transition=0[finala]")
        audio_label = "finala"

    capabilities = encoder_capabilities()
    container, logical_codec, codec = final_codec(spec, capabilities)
    command += ["-filter_complex", ";".join(graph), "-map", f"[{video_label}]", "-map", f"[{audio_label}]", "-t", str(total_duration), "-c:v", codec]
    if codec == "libx264":
        command += ["-preset", "medium", "-crf", str(int(number((spec.get('export') or {}).get('quality'), 14, 35, 20)))]
    elif codec == "libx265":
        command += ["-preset", "medium", "-crf", str(int(number((spec.get('export') or {}).get('quality'), 16, 38, 24))), "-tag:v", "hvc1"]
    elif codec == "libvpx-vp9":
        command += ["-crf", str(int(number((spec.get('export') or {}).get('quality'), 15, 45, 28))), "-b:v", "0"]
    elif "videotoolbox" in codec:
        command += ["-b:v", "10M"]
        if logical_codec == "h265": command += ["-tag:v", "hvc1"]
    audio_codec = "libopus" if container == "webm" else ("pcm_s16le" if container == "mov" and (spec.get("export") or {}).get("pcmAudio") else "aac")
    command += ["-c:a", audio_codec]
    if audio_codec == "aac": command += ["-b:a", "192k"]
    command += ["-pix_fmt", "yuv420p"]
    if container in {"mp4", "mov"}:
        command += ["-movflags", "+faststart"]
    command += [str(output)]
    run(command)
    return {"codec": codec, "container": container,
            "hardware": "videotoolbox" in codec or "nvenc" in codec,
            "textRenderer": text_renderer(text_filters), "warnings": warnings}


def render_project(job, spec, media: Path, output_dir: Path, status_callback):
    clips = spec.get("clips") or []
    if not clips:
        raise ValueError("Add at least one video clip")
    if len(clips) > 120:
        raise ValueError("Maximum 120 clips per render")
    if len(spec.get("stickers") or []) > 120:
        raise ValueError("Maximum 120 stickers per render")
    width, height = output_dimensions(spec)
    fps = int(number(spec.get("fps"), 12, 120, 30))
    temp = output_dir / f"temp-{job}"
    temp.mkdir(parents=True, exist_ok=False)
    try:
        text_filters = filter_capabilities()
        warnings = []
        primary, overlays = [], []
        primary_clips, primary_durations = [], []
        for index, clip in enumerate(clips):
            source = media / safe_name(clip.get("file"))
            if not source.is_file():
                raise ValueError("Missing source clip: " + source.name)
            is_overlay = int(number(clip.get("track"), 0, 8, 0)) > 0
            piece = temp / (f"overlay-{index:03}.mov" if is_overlay else f"clip-{index:03}.mp4")
            duration = render_piece(clip, index, source, piece, width, height, fps, temp, is_overlay,
                                    text_filters, warnings)
            if is_overlay:
                overlays.append({"path": piece, "start": number(clip.get("timelineStart"), 0, 86400, 0), "duration": duration})
            else:
                primary.append(piece); primary_clips.append(clip); primary_durations.append(duration)
            status_callback(int((index + 1) * 55 / len(clips)), f"Processed clip {index + 1}/{len(clips)}")
        overlay_duration = max((item["start"] + item["duration"] for item in overlays), default=1)
        timeline = temp / "timeline.mp4"
        total = join_primary(primary, primary_clips, primary_durations, timeline, width, height, fps, overlay_duration)
        total = max(total, overlay_duration)
        composite = temp / "composite.mp4"
        composite_overlays(timeline, overlays, composite, total)
        status_callback(75, "Compositing tracks, titles and audio")
        export = spec.get("export") or {}
        container = str(export.get("container") or "mp4").lower()
        if container not in {"mp4", "mov", "webm"}: container = "mp4"
        output = output_dir / f"VDODesk-{job}.{container}"
        details = finish_project(composite, spec, media, output, temp, total, text_filters, warnings)
        status_callback(100, "Export ready")
        return output, details
    finally:
        shutil.rmtree(temp, ignore_errors=True)
