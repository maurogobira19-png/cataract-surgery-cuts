#!/usr/bin/env python3
"""Step 4 of the cataract-surgery-cuts skill: render the edit from an EDL (JSON).
Usage: python render.py edl.json
EDL:
{
 "video": "/path/surgery.mp4",
 "output": "/path/surgery_edited.mp4",
 "format": "horizontal" | "vertical",           # vertical = 1080x1920 with a centered crop (or "crop" below)
 "crop": [x, y, w, h],                            # optional: fixed crop of the surgical field (removes patient name)
 "mask": [x, y, w, h],                            # optional: black box over an overlay with identifiers
 "audio": false,                                  # keep original audio?
 "quality": {"crf": 23, "maxrate": "3M"},         # optional; this is the default (~700 MB for a 30 min lecture).
                                                  # For an archival master: {"crf": 19, "maxrate": "50M"} (~2x the size).
 "title_style": {"size": 54},                     # optional
 "segments": [
   {"start": 12.0, "end": 48.5, "speed": 1.0, "title": "Main incision 2.2 mm"},
   {"start": 60.0, "end": 130.0, "speed": 3.0, "title": "Capsulorhexis"}
 ]
}
Each segment becomes a clip at the requested speed, with the title burned in for the first 3 s (fade). Then concatenated.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
FPS = 30


def load_font(size, bold=True):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size, index=(4 if bold else 10) if f.endswith(".ttc") else 0)
        except OSError:
            continue
    return ImageFont.load_default()


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-3000:], file=sys.stderr); raise SystemExit("ffmpeg failed")
    return r


def atempo_chain(v):
    """atempo only accepts 0.5-2.0 per instance; decompose any speed into a valid chain."""
    factors, rest = [], float(v)
    while rest > 2.0:
        factors.append(2.0); rest /= 2.0
    while rest < 0.5:
        factors.append(0.5); rest /= 0.5
    factors.append(rest)
    return ",".join(f"atempo={f:g}" for f in factors)


def need_tools():
    for t in ("ffmpeg", "ffprobe"):
        if not shutil.which(t):
            raise SystemExit(f"{t} not found in PATH (install with: brew install ffmpeg)")


def source_duration(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "default=nw=1:nk=1", str(video)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def validate(edl):
    """Fail loudly on an EDL that would silently render garbage."""
    errs = []
    video = Path(edl.get("video", ""))
    if not video.is_file():
        errs.append(f"video not found: {video}")
    if not edl.get("output"):
        errs.append("missing 'output'")
    segs = edl.get("segments") or []
    if not segs:
        errs.append("no segments")
    dur = source_duration(video) if video.is_file() else None
    prev_end = None
    for i, s in enumerate(segs):
        try:
            a, b, v = float(s["start"]), float(s["end"]), float(s.get("speed", 1.0))
        except (KeyError, TypeError, ValueError):
            errs.append(f"segment {i}: start/end/speed must be numbers"); continue
        if b <= a:
            errs.append(f"segment {i}: end ({b}) must be greater than start ({a})")
        if v <= 0:
            errs.append(f"segment {i}: speed must be positive, got {v}")
        if dur and b > dur + 0.5:
            errs.append(f"segment {i}: end {b}s is past the end of the video ({dur:.1f}s)")
        if prev_end is not None and a < prev_end - 0.01:
            print(f"warning: segment {i} starts at {a}s, before segment {i-1} ends ({prev_end}s)", file=sys.stderr)
        prev_end = b
    for key in ("mask", "crop"):
        box = edl.get(key)
        if box is not None and (len(box) != 4 or any(not isinstance(n, (int, float)) for n in box)):
            errs.append(f"'{key}' must be [x, y, w, h]")
    if errs:
        raise SystemExit("EDL invalid:\n- " + "\n- ".join(errs))


def title_png(text, W, H, path, size=54, speed=1.0):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f = load_font(size); sub = load_font(int(size * 0.55), bold=False)
    tw = d.textlength(text, font=f); pad = 22
    x, y = 60, H - size - 120
    d.rounded_rectangle((x - pad, y - 10, x + tw + pad, y + size + 12), 14, fill=(0, 0, 0, 200))
    d.text((x, y), text, font=f, fill="white")
    if speed != 1.0:
        lab = f"{speed:g}x"; lw = d.textlength(lab, font=sub)
        d.rounded_rectangle((x + tw + pad + 14, y + 4, x + tw + pad + 14 + lw + 24, y + 4 + sub.size + 14), 10, fill=(255, 214, 0, 235))
        d.text((x + tw + pad + 26, y + 8), lab, font=sub, fill="black")
    img.save(path)


def main(edl_path):
    need_tools()
    edl = json.loads(Path(edl_path).read_text())
    validate(edl)
    video, output = edl["video"], edl["output"]
    vertical = edl.get("format") == "vertical"
    q = edl.get("quality", {})
    crf = str(q.get("crf", 23))
    maxrate = q.get("maxrate", "2.5M" if vertical else "3M")
    bufsize = q.get("bufsize", "6M")
    W, H = (1080, 1920) if vertical else (1920, 1080)
    work = Path(output).with_suffix(""); work.mkdir(parents=True, exist_ok=True)
    pre = []
    if edl.get("mask"):
        x, y, w, h = edl["mask"]; pre.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black:t=fill")
    if edl.get("crop"):
        x, y, w, h = edl["crop"]; pre.append(f"crop={w}:{h}:{x}:{y}")
    pre.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
    segs = []
    for i, s in enumerate(edl["segments"]):
        v = float(s.get("speed", 1.0)); dur = (s["end"] - s["start"]) / v
        seg = work / f"seg_{i:02d}.mp4"
        chain = ",".join(pre) + f",setpts=PTS/{v},fps={FPS}"
        inputs = ["-ss", str(s["start"]), "-to", str(s["end"]), "-i", video]
        if s.get("title"):
            png = work / f"t_{i:02d}.png"; title_png(s["title"], W, H, png, edl.get("title_style", {}).get("size", 54), v)
            inputs += ["-loop", "1", "-i", str(png)]
            show = max(0.6, min(3.5, dur))
            fade_out = max(0.05, show - 0.4)
            chain = f"[0:v]{chain}[v0];[1:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st={fade_out:.2f}:d=0.4:alpha=1[t];[v0][t]overlay=0:0:shortest=1[v]"
        else:
            chain = f"[0:v]{chain}[v]"
        audio = ["-map", "0:a?", "-af", atempo_chain(v), "-c:a", "aac", "-b:a", "128k"] if edl.get("audio") else ["-an"]
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", chain, "-map", "[v]", *audio,
             "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", crf,
             "-maxrate", maxrate, "-bufsize", bufsize, "-pix_fmt", "yuv420p", "-r", str(FPS), str(seg)])
        segs.append(seg); print(f"seg {i:02d}: {s['start']:.1f}-{s['end']:.1f}s x{v:g} -> {dur:.1f}s  {s.get('title','')}")
    lst = work / "concat.txt"; lst.write_text("".join(f"file '{p}'\n" for p in segs))
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", output])
    total = sum((s["end"] - s["start"]) / float(s.get("speed", 1)) for s in edl["segments"])
    size_mb = Path(output).stat().st_size / 1e6
    print(f"OK {output}  {total/60:.1f} min ({len(segs)} segments, {size_mb:.0f} MB)")


if __name__ == "__main__":
    main(sys.argv[1])
